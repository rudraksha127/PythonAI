"""
INDRA Live Dashboard Server
===========================
Serves the `dashboard.html` UI and provides a WebSocket stream on port 8765
to feed live metrics from the `massive_engine` state.
"""

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
import websockets
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Import API Keys logic to show provider status
try:
    from src.data.apikeys import PROVIDER_LABELS, PROVIDER_TIERS, resolve_all
except ImportError:
    resolve_all = lambda: {}
    PROVIDER_LABELS = {}
    PROVIDER_TIERS = {}

BASE_DATA_DIR = Path(os.environ.get("DATA_DIR", "D:/PythonAI_Data"))
STATE_FILE = BASE_DATA_DIR / ".massive_worker_state.json"

CLIENTS = set()
START_TIME = time.time()

SYSTEM_STATE = {
    "status": "RUNNING MASSIVE ENGINE",
    "uptime_start": START_TIME,
    "phases": {
        "arXiv Papers": "RUNNING",
        "OpenAlex Research": "RUNNING",
        "HuggingFace Datasets": "RUNNING",
        "Synthetic Data Generation": "IDLE",
        "RAG Pipeline Indexing": "IDLE",
    },
    "stats": {
        "total_files": 0,
        "total_size_gb": 0.0,
        "errors": 0,
        "synthetic_rows": 0,
        "arxiv_papers": 0,
        "openalex_works": 0,
        "hf_datasets": 0,
        "rag_indexed": 0,
    },
    "agents": {
        "orchestrator": {"status": "active", "last_action": "Coordinating 1200+ sources"},
        "retrieval": {"status": "active", "last_action": "Fetching from APIs"},
        "docs": {"status": "active", "last_action": "Parsing papers"},
        "performance": {"status": "active", "last_action": "Optimizing I/O"},
    },
    "providers": {}
}

async def handle_client(websocket):
    CLIENTS.add(websocket)
    print(f"[WS] Client connected. Total: {len(CLIENTS)}")
    try:
        # Send full initial state
        await websocket.send(json.dumps({
            "type": "FULL_STATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "state": SYSTEM_STATE,
                "history": []
            }
        }))
        async for message in websocket:
            # Relay messages from workers to all dashboards
            try:
                data = json.loads(message)
                if data.get("type") in ["LOG", "PROGRESS", "PHASE_START", "PHASE_COMPLETE"]:
                    # Update local state based on incoming progress
                    if data.get("type") == "PROGRESS":
                        phase = data["data"].get("phase")
                        count = data["data"].get("count", 0)
                        if phase == "arXiv Papers":
                            SYSTEM_STATE["stats"]["arxiv_papers"] = max(SYSTEM_STATE["stats"]["arxiv_papers"], count)
                        elif phase == "OpenAlex Research":
                            SYSTEM_STATE["stats"]["openalex_works"] = max(SYSTEM_STATE["stats"]["openalex_works"], count)

                    # Relay to all other clients
                    for client in CLIENTS:
                        if client != websocket:
                            await client.send(message)
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(websocket)
        print(f"[WS] Client disconnected. Total: {len(CLIENTS)}")


async def broadcast(msg_type: str, data: dict):
    if not CLIENTS:
        return
    msg = json.dumps({"type": msg_type, "timestamp": datetime.now(timezone.utc).isoformat(), "data": data})
    await asyncio.gather(*[client.send(msg) for client in CLIENTS], return_exceptions=True)


async def heartbeat_loop():
    print("[WS] Starting heartbeat loop on port 8765...")
    while True:
        await asyncio.sleep(2)

        # 1. Calculate File Size
        try:
            total_size = sum(f.stat().st_size for f in BASE_DATA_DIR.rglob("*.jsonl")) / 1e9
            total_files = sum(1 for f in BASE_DATA_DIR.rglob("*.jsonl"))
        except Exception:
            total_size = 0.0
            total_files = 0

        SYSTEM_STATE["stats"]["total_size_gb"] = total_size
        SYSTEM_STATE["stats"]["total_files"] = total_files

        # 2. Read state from massive engine
        try:
            if STATE_FILE.exists():
                state_data = json.loads(STATE_FILE.read_text(encoding="utf-8"))

                # Approximate counts based on the state file's progress
                arxiv = sum(s.get("total", 0) for k, s in state_data.items() if "arxiv" in k)
                openalex = sum(s.get("total", 0) for k, s in state_data.items() if "openalex" in k)

                SYSTEM_STATE["stats"]["arxiv_papers"] = arxiv
                SYSTEM_STATE["stats"]["openalex_works"] = openalex
        except Exception:
            pass

        # 3. Get API Providers
        try:
            keys = resolve_all()
            for prov, key in keys.items():
                SYSTEM_STATE["providers"][prov] = {
                    "label": PROVIDER_LABELS.get(prov, prov),
                    "tier": PROVIDER_TIERS.get(prov, "standard"),
                    "has_key": True,
                    "status": "online"
                }
        except Exception:
            pass

        # Broadcast
        await broadcast("HEARTBEAT", {
            "uptime_s": round(time.time() - SYSTEM_STATE["uptime_start"]),
            "stats": SYSTEM_STATE["stats"],
            "agents": SYSTEM_STATE["agents"],
            "providers": SYSTEM_STATE["providers"],
            "status": SYSTEM_STATE["status"]
        })


async def start_ws_server():
    async with websockets.serve(handle_client, "0.0.0.0", 8765):
        await heartbeat_loop()


def run_ws_thread():
    asyncio.run(start_ws_server())


# FastAPI for HTTP Serving
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    dashboard_path = Path(__file__).parent / "dashboard.html"
    return dashboard_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    # Start the WS server in a background thread
    threading.Thread(target=run_ws_thread, daemon=True).start()

    # Start HTTP server on the main thread
    print("[HTTP] Starting web server on http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error")
