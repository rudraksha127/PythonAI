"""
INDRA Dashboard Server
======================
FastAPI server to host the dashboard and provide metrics.
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="INDRA Dashboard Server")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_path = Path("indra_dashboard.html")
    if dashboard_path.exists():
        return dashboard_path.read_text(encoding="utf-8")
    return "<h1>Dashboard HTML not found</h1>"


@app.get("/api/metrics")
async def get_metrics():
    # In a full implementation, this would read from the generated metrics JSON files
    # For now, we return placeholder stats
    return {
        "collection": {"tb_collected": 14.2, "progress_percent": 25},
        "evaluation": {"mmlu": 82.5, "gsm8k": 75.2, "humaneval": 68.4},
        "training": {"synthetic_examples": 24500, "current_step": 1500},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
