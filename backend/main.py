from pathlib import Path
from collections import deque
from datetime import datetime, timezone
import asyncio, json, time, os
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
try:
    from .ml import load_data, make_series, forecast_from_history, graph_predictions, ROOT
except ImportError:
    from ml import load_data, make_series, forecast_from_history, graph_predictions, ROOT

app = FastAPI(title="Real-data CDN Bandwidth Optimization", version="1.0.0")
origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
DATA = ROOT / "data" / "raw" / "Bandwidth.csv"
_df = load_data(DATA)
_records = _df.to_dict(orient="records")
for r in _records:
    for k,v in list(r.items()):
        if pd.isna(v): r[k] = None
        elif isinstance(v, pd.Timestamp): r[k] = v.isoformat()
_metrics = deque(maxlen=1200)
_playback = {"active": False, "hls_url": "", "note": "Supply a browser-accessible HLS .m3u8 URL. Original trace hostnames are private/non-public and may not resolve outside the capture environment."}

class PlaybackConfig(BaseModel):
    hls_url: HttpUrl

@app.get("/api/health")
def health():
    return {"status":"ok", "dataset":"Bandwidth.csv", "dataset_rows":len(_records), "models_ready": (ROOT/"models/lstm_model.pt").exists() and (ROOT/"models/gnn_model.pt").exists(), "timestamp_utc":datetime.now(timezone.utc).isoformat()}

@app.get("/api/summary")
def summary():
    return {"dataset":"Bandwidth.csv", "rows":len(_df), "start_utc":_df.startedDateTime.min().isoformat(), "end_utc":_df.startedDateTime.max().isoformat(), "hostnames":sorted(_df.hostname.dropna().astype(str).unique().tolist()), "status_counts":{str(k):int(v) for k,v in _df.status.value_counts().items()}, "observed_mean_latency_ms":round(float(_df.time_ms.mean()),2), "observed_p95_latency_ms":round(float(_df.time_ms.quantile(.95)),2), "observed_total_bytes":int(_df.content_size.fillna(0).sum()), "media_requests":int(_df.is_media.sum()), "errors":int(_df.is_error.sum()), "note":"These are historical trace statistics, not current live Internet measurements."}

@app.get("/api/trace")
def trace(limit:int=250, offset:int=0):
    limit=max(1,min(limit,1000)); offset=max(0,offset)
    return {"total":len(_records), "offset":offset, "limit":limit, "records":_records[offset:offset+limit]}

@app.get("/api/forecast")
def forecast():
    try: return forecast_from_history([])
    except Exception as e: raise HTTPException(status_code=500, detail=f"Model forecast failed: {e}")

@app.get("/api/graph")
def graph():
    try: return {"nodes":graph_predictions(), "edges_note":"Edges are based on hostname co-occurrence in the same observed minute; no geographic edges are invented."}
    except Exception as e: raise HTTPException(status_code=500, detail=f"GNN inference failed: {e}")

@app.get("/api/metrics")
def metrics():
    return {"measurements":list(_metrics), "count":len(_metrics), "note":"Live metrics are actual server-side HTTP request timings and historical replay events are labelled separately."}

@app.post("/api/playback")
def configure_playback(body:PlaybackConfig):
    _playback["hls_url"] = str(body.hls_url); _playback["active"] = True
    return {"ok":True,"hls_url":_playback["hls_url"],"note":"Playback URL configured. Browser CORS and network reachability depend on the HLS origin."}

@app.get("/api/playback")
def playback_status(): return _playback

@app.websocket("/ws/live")
async def live(ws:WebSocket):
    await ws.accept()
    try:
        speed=1.0
        try:
            raw=ws.query_params.get("speed","1")
            speed=max(0.25,min(20.0,float(raw)))
        except Exception: pass
        # Replay actual records in chronological order. This is historical replay, not live user traffic.
        for i,r in enumerate(_records):
            msg={"type":"historical_replay","index":i,"total":len(_records),"record":r,"dataset":"Bandwidth.csv","is_live_network_measurement":False}
            await ws.send_text(json.dumps(msg, default=str))
            await asyncio.sleep(max(0.03, 0.8/speed))
        while True:
            await asyncio.sleep(5)
            await ws.send_text(json.dumps({"type":"heartbeat","timestamp_utc":datetime.now(timezone.utc).isoformat(),"is_live_network_measurement":True}))
    except WebSocketDisconnect: pass
    except Exception: pass

@app.middleware("http")
async def measure_http(request, call_next):
    start=time.perf_counter()
    response=await call_next(request)
    elapsed=(time.perf_counter()-start)*1000
    if request.url.path.startswith('/api/'):
        _metrics.append({"timestamp_utc":datetime.now(timezone.utc).isoformat(),"path":request.url.path,"method":request.method,"status_code":response.status_code,"server_processing_ms":round(elapsed,3),"kind":"actual_server_http_timing"})
    response.headers["X-Server-Processing-Ms"] = f"{elapsed:.3f}"
    return response

frontend=ROOT/"frontend"/"dist"
if frontend.exists(): app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
