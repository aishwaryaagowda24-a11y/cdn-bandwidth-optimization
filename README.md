# CDN Bandwidth Optimization — LSTM + GNN

A full-stack demonstration built using **only the supplied `data/raw/Bandwidth.csv` for model training**. It includes a FastAPI backend, trained PyTorch LSTM and graph message-passing model, WebSocket historical trace replay, measured API latency, a React dashboard, and an HLS player that accepts a browser-accessible manifest URL.

## Important data limitations

- The CSV has 615 records across about 53 minutes. It is a small trace, not a large-scale CDN workload.
- Historical replay is replay of recorded events, **not** live traffic from real viewers.
- The recorded `hostname` values include internal-looking hostnames. The original trace URLs may not resolve publicly.
- The HLS player accepts a publicly reachable `.m3u8` URL. Playback media is separate from training data. Browser CORS and stream availability apply.
- The GNN graph is built only from hostnames observed together within the same recorded minute. It does not infer geography or real network link latency.
- Model metrics must be interpreted cautiously. This is a working academic prototype, not evidence of production-grade optimization or guaranteed latency reduction.
- `/api/metrics` records server-side API handling time. The dashboard's browser measurement is an actual browser-to-API round trip. These are distinct metrics.

## Features

- `GET /api/health`: health and model status
- `GET /api/summary`: historical dataset statistics
- `GET /api/trace`: recorded rows
- `GET /api/forecast`: LSTM forecast for the next 10-second bin
- `GET /api/graph`: GNN outputs for observed host nodes
- `GET /api/metrics`: actual API server processing timings
- `WS /ws/live?speed=3`: chronological historical trace replay with event labels
- React dashboard with trace charts, LSTM/GNN panels, latency measurement, and HLS player

## Run locally for development

Python 3.11 is recommended. Local development uses localhost by definition; deployment instructions below produce a public URL.

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r ../requirements.txt
python train.py
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite runs on port 5173 and API calls expect same-origin by default. For local development with separate ports, create `frontend/.env` with `VITE_API_BASE=http://localhost:8000`, then restart Vite. This is only for development.

## Deploy to a public URL (Render free tier, subject to current platform limits)

1. Create a Git repository and push this project. Ensure `data/raw/Bandwidth.csv` is included if allowed by the dataset license.
2. In Render, create a **Web Service** from the repository and select Docker. Or use the included `render.yaml` Blueprint.
3. The Docker build installs dependencies, trains both models from the included CSV, and starts Uvicorn on `0.0.0.0:8000`.
4. Wait for `/api/health` to return `{"status":"ok"...}`. Render supplies the public HTTPS URL.
5. Open the root URL. The frontend is served by FastAPI from `frontend/dist` only when that folder exists. Build the frontend before Docker deployment.

### Deployment considerations

The included Dockerfile uses a multi-stage build: it builds React with Node and serves the resulting `frontend/dist` through FastAPI. The trained model artifacts are included in the repository so deployment does not retrain them. Free-tier sleep, memory limits, and PyTorch image size may affect startup and build success. If the selected free tier cannot fit the PyTorch dependency, deploy the frontend and backend separately or choose a host with sufficient memory; verify the current host limits before deployment.

## Re-training models

For reproducible deployments, run `python backend/train.py` and commit `models/lstm_model.pt`, `models/gnn_model.pt`, and `models/training_report.json`. The included Dockerfile copies these artifacts and does not retrain during deployment.

## Model training and validation

```bash
pip install -r requirements.txt
python backend/train.py
```

The trainer sorts by timestamp, creates 10-second bins, uses an 80/20 chronological split for LSTM training/holdout, and trains a small graph regressor on observed hostname aggregates and minute-level co-occurrence. Review `models/training_report.json` before making performance claims. The small dataset means results may be unstable.

## HLS playback

The dashboard contains an HLS URL field. Enter a public `.m3u8` URL that permits browser playback and press **Load**. Some browsers use native HLS; others use hls.js. If playback fails, check that the manifest and all referenced segments are publicly reachable over HTTPS and allow CORS. URLs captured in the CSV may point to private lab hostnames and will not necessarily work outside the original network.

## Project tree

```text
backend/main.py          FastAPI + WebSocket + measured API timing
backend/ml.py            LSTM/GNN definitions, training, inference
backend/train.py         Train models from Bandwidth.csv
frontend/src/main.jsx    React live dashboard and HLS player
frontend/src/style.css   Dashboard styles
data/raw/Bandwidth.csv   Sole training dataset provided by user
models/                  Trained weights and training report
Dockerfile               Cloud deployment container
render.yaml              Render Blueprint
```
