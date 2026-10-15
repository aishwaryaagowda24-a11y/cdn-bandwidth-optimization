"""Small-data LSTM + graph message-passing models for the supplied HAR-derived CSV."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "Bandwidth.csv"
MODEL_DIR = ROOT / "models"
DEVICE = torch.device("cpu")


def load_data(path=DATA):
    df = pd.read_csv(path)
    df["startedDateTime"] = pd.to_datetime(df["startedDateTime"], utc=True, errors="coerce")
    df = df.dropna(subset=["startedDateTime"]).sort_values("startedDateTime").reset_index(drop=True)
    for c in ["content_size", "time_ms", "throughput_Bps", "wait_ms", "receive_ms", "status"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["content_size"] = df["content_size"].fillna(0).clip(lower=0)
    df["time_ms"] = df["time_ms"].fillna(df["time_ms"].median()).clip(lower=0)
    df["throughput_Bps"] = df["throughput_Bps"].replace([np.inf, -np.inf], np.nan).fillna(0).clip(lower=0)
    df["is_media"] = pd.to_numeric(df["is_media"], errors="coerce").fillna(0)
    df["is_error"] = pd.to_numeric(df["is_error"], errors="coerce").fillna(0)
    return df


def make_series(df, freq="10s"):
    indexed = df.set_index("startedDateTime")
    agg = indexed.resample(freq).agg(
        requests=("url", "count"),
        bytes=("content_size", "sum"),
        mean_latency_ms=("time_ms", "mean"),
        media_requests=("is_media", "sum"),
        errors=("is_error", "sum"),
    ).fillna(0)
    # Keep time gaps as zero-request bins: they are meaningful observations.
    agg["bandwidth_Bps"] = agg["bytes"] / 10.0
    return agg


class LSTMForecaster(nn.Module):
    def __init__(self, input_size=5, hidden_size=32):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden_size, 16), nn.ReLU(), nn.Linear(16, 2))

    def forward(self, x):
        y, _ = self.lstm(x)
        return self.head(y[:, -1, :])


class TinyGraphRegressor(nn.Module):
    """One message-passing layer over the empirically observed hostname graph."""
    def __init__(self, in_features=5, hidden=16):
        super().__init__()
        self.self_proj = nn.Linear(in_features, hidden)
        self.neigh_proj = nn.Linear(in_features, hidden)
        self.head = nn.Sequential(nn.ReLU(), nn.Linear(hidden, 2))

    def forward(self, x, adjacency):
        denom = adjacency.sum(dim=1, keepdim=True).clamp(min=1.0)
        neigh = (adjacency @ x) / denom
        h = self.self_proj(x) + self.neigh_proj(neigh)
        return self.head(h)


def _scale_fit(arr):
    mean = arr.mean(axis=0)
    std = arr.std(axis=0)
    std[std < 1e-6] = 1.0
    return mean, std


def train_all(path=DATA, epochs=120):
    torch.manual_seed(7)
    np.random.seed(7)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data(path)
    series = make_series(df)
    features = ["requests", "bytes", "mean_latency_ms", "media_requests", "errors"]
    values = series[features].to_numpy(dtype=np.float32)
    # Log transform heavy-tailed byte counts; targets are requests and bytes.
    values[:, 1] = np.log1p(values[:, 1])
    values[:, 2] = np.log1p(values[:, 2])
    values[:, 4] = np.log1p(values[:, 4])
    n = len(values)
    split = max(24, int(n * 0.8))
    mean, std = _scale_fit(values[:split])
    scaled = (values - mean) / std
    lookback = min(12, max(4, n // 12))
    X, y, target_indices = [], [], []
    for i in range(lookback, n):
        X.append(scaled[i-lookback:i])
        y.append([scaled[i, 0], scaled[i, 1]])
        target_indices.append(i)
    X = np.asarray(X, dtype=np.float32); y = np.asarray(y, dtype=np.float32)
    tr = np.array(target_indices) < split
    if tr.sum() < 10:
        tr[:] = True
    model = LSTMForecaster(input_size=len(features))
    opt = torch.optim.Adam(model.parameters(), lr=0.008, weight_decay=1e-4)
    loss_fn = nn.MSELoss()
    xt = torch.tensor(X); yt = torch.tensor(y); trt = torch.tensor(tr)
    model.train()
    for _ in range(epochs):
        opt.zero_grad(); pred = model(xt[trt]); loss = loss_fn(pred, yt[trt]); loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        preds = model(xt).numpy()
    # Evaluate request-count target in original scale; holdout when possible.
    req_pred = np.maximum(0, preds[:, 0] * std[0] + mean[0])
    req_true = np.maximum(0, y[:, 0] * std[0] + mean[0])
    hold = ~tr
    if hold.sum() < 3: hold = np.ones_like(tr, dtype=bool)
    mae = float(np.mean(np.abs(req_pred[hold] - req_true[hold])))
    rmse = float(np.sqrt(np.mean((req_pred[hold] - req_true[hold])**2)))
    torch.save({"state_dict": model.state_dict(), "input_size": len(features), "hidden_size": 32,
                "features": features, "mean": mean.tolist(), "std": std.tolist(), "lookback": lookback,
                "epochs": epochs}, MODEL_DIR / "lstm_model.pt")

    # Host graph from co-occurrence in a 60-second window. No geography is inferred.
    hosts = sorted(df["hostname"].fillna("unknown").astype(str).unique().tolist())
    host_to_idx = {h:i for i,h in enumerate(hosts)}
    host_stats = []
    for h in hosts:
        sub = df[df.hostname.fillna("unknown").astype(str) == h]
        host_stats.append([
            np.log1p(len(sub)), np.log1p(sub.content_size.fillna(0).clip(lower=0).mean()),
            np.log1p(sub.time_ms.fillna(0).clip(lower=0).mean()),
            np.log1p(sub.throughput_Bps.fillna(0).clip(lower=0).mean()),
            float(sub.is_error.fillna(0).mean()) if len(sub) else 0.0,
        ])
    gx = np.asarray(host_stats, dtype=np.float32)
    # undirected edges when hostnames appear within the same minute; self loops included
    adj = np.eye(len(hosts), dtype=np.float32)
    temp = df[["startedDateTime", "hostname"]].copy()
    temp["hostname"] = temp.hostname.fillna("unknown").astype(str)
    temp["minute"] = temp.startedDateTime.dt.floor("min")
    for _, group in temp.groupby("minute"):
        ids = sorted(set(host_to_idx[h] for h in group.hostname if h in host_to_idx))
        for a in ids:
            for b in ids:
                adj[a,b] = 1.0
    gx_mean, gx_std = _scale_fit(gx)
    gxn = (gx - gx_mean) / gx_std
    # targets: normalized log mean latency and log mean throughput for each host
    target = []
    for h in hosts:
        sub = df[df.hostname.fillna("unknown").astype(str) == h]
        target.append([np.log1p(max(0, float(sub.time_ms.fillna(0).mean()))),
                       np.log1p(max(0, float(sub.throughput_Bps.fillna(0).mean())))])
    target = np.asarray(target, dtype=np.float32)
    tmean, tstd = _scale_fit(target); tn = (target - tmean) / tstd
    gnn = TinyGraphRegressor(in_features=gx.shape[1])
    gopt = torch.optim.Adam(gnn.parameters(), lr=0.01, weight_decay=0.01)
    gxt, gat, gyt = torch.tensor(gxn), torch.tensor(adj), torch.tensor(tn)
    gnn.train()
    for _ in range(epochs):
        gopt.zero_grad(); gp = gnn(gxt, gat); gl = loss_fn(gp, gyt); gl.backward(); gopt.step()
    gnn.eval()
    with torch.no_grad():
        gp = gnn(gxt, gat).numpy()
    gmae = float(np.mean(np.abs(gp*tstd+tmean-target)))
    torch.save({"state_dict": gnn.state_dict(), "input_size": gx.shape[1], "hidden_size": 16,
                "hosts": hosts, "features": ["log_request_count", "log_mean_bytes", "log_mean_latency_ms", "log_mean_throughput", "error_rate"],
                "host_features": gx.tolist(), "adjacency": adj.tolist(), "feature_mean": gx_mean.tolist(),
                "feature_std": gx_std.tolist(), "target_mean": tmean.tolist(), "target_std": tstd.tolist(),
                "training_mae_transformed": gmae}, MODEL_DIR / "gnn_model.pt")

    report = {
        "dataset": str(Path(path).name), "rows": int(len(df)), "time_bins": int(n),
        "time_start_utc": df.startedDateTime.min().isoformat(), "time_end_utc": df.startedDateTime.max().isoformat(),
        "hosts_observed": hosts, "status_counts": {str(k): int(v) for k,v in df.status.value_counts().items()},
        "lstm_holdout_request_count_mae": mae, "lstm_holdout_request_count_rmse": rmse,
        "lstm_holdout_samples": int(hold.sum()), "lstm_lookback_bins": int(lookback),
        "gnn_training_mae_log_targets": gmae,
        "note": "Small trace; GNN is trained on observed hostname aggregates and minute-level co-occurrence. It is not evidence of geographic latency or production CDN performance. LSTM request-count evaluation uses scaled/log-transformed targets as specified in training code; validate metrics before claiming gains."
    }
    (MODEL_DIR / "training_report.json").write_text(json.dumps(report, indent=2))
    return report


def load_models():
    lstm_path, gnn_path = MODEL_DIR / "lstm_model.pt", MODEL_DIR / "gnn_model.pt"
    if not lstm_path.exists() or not gnn_path.exists():
        train_all()
    lc = torch.load(lstm_path, map_location="cpu", weights_only=False)
    lstm = LSTMForecaster(lc["input_size"], lc["hidden_size"]); lstm.load_state_dict(lc["state_dict"]); lstm.eval()
    gc = torch.load(gnn_path, map_location="cpu", weights_only=False)
    gnn = TinyGraphRegressor(gc["input_size"], gc["hidden_size"]); gnn.load_state_dict(gc["state_dict"]); gnn.eval()
    return lstm, lc, gnn, gc


def forecast_from_history(history):
    lstm, cfg, _, _ = load_models()
    df = load_data()
    series = make_series(df)
    features = cfg["features"]
    values = series[features].to_numpy(dtype=np.float32)
    values[:, 1] = np.log1p(values[:, 1]); values[:, 2] = np.log1p(values[:, 2]); values[:, 4] = np.log1p(values[:, 4])
    mean, std = np.array(cfg["mean"]), np.array(cfg["std"])
    scaled = (values - mean) / std
    seq = scaled[-cfg["lookback"]:]
    with torch.no_grad():
        out = lstm(torch.tensor(seq[None, :, :], dtype=torch.float32)).numpy()[0]
    req = max(0.0, float(out[0] * std[0] + mean[0]))
    log_bytes = float(out[1] * std[1] + mean[1])
    byte_est = max(0.0, float(np.expm1(log_bytes)))
    return {"forecast_requests_next_bin": round(req, 3), "forecast_bytes_next_bin": round(byte_est, 1), "forecast_horizon_seconds": 10, "model": "trained LSTM", "training_data": "Bandwidth.csv"}


def graph_predictions():
    _, _, gnn, cfg = load_models()
    x = np.asarray(cfg["host_features"], dtype=np.float32)
    x = ((x - np.asarray(cfg["feature_mean"], dtype=np.float32)) / np.asarray(cfg["feature_std"], dtype=np.float32)).astype(np.float32)
    adj = np.asarray(cfg["adjacency"], dtype=np.float32)
    with torch.no_grad(): out = gnn(torch.tensor(x, dtype=torch.float32), torch.tensor(adj, dtype=torch.float32)).numpy()
    out = out * np.asarray(cfg["target_std"], dtype=np.float32) + np.asarray(cfg["target_mean"], dtype=np.float32)
    return [{"hostname": h, "estimated_mean_latency_ms_from_trace": round(float(np.expm1(v[0])), 2), "estimated_mean_throughput_Bps_from_trace": round(float(np.expm1(v[1])), 2)} for h,v in zip(cfg["hosts"], out)]
