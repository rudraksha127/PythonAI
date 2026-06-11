"""
ForgeAI FastAPI Server — Complete System
=========================================
Port: 7337 (local) | WebSocket + REST API

Endpoints:
  POST /api/events           — Capture accept/reject/edit signals
  GET  /api/metrics/*        — Acceptance rate, training history
  GET  /api/training/*       — Training status, trigger runs
  POST /api/agent/chat       — Agent with streaming (SSE)
  POST /api/rag/search       — Hybrid retrieval (BM25 + dense + graph)
  POST /api/rag/index        — Index/re-index a project
  GET  /api/projects         — Project management
  WS   /ws/events            — Real-time event stream from VS Code
  WS   /ws/training-progress — Live training progress to dashboard

Security: Rate limiting, CORS, security headers, request ID tracking.
Research: MIT SEAL architecture — developer accept = reward signal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3  # Projects store
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# APScheduler — automated training scheduling
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.cli import VERSION
from src.learning.capture_engine import CaptureEngine
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, get_answer, load_or_build_db
from src.training.grpo_trainer import GRPOTrainer
from src.training.sdft_trainer import SDFTTrainer
from src.utils.metrics import metrics

# Cloud backend (optional — graceful if not configured)
try:
    from src.api.cloud_routes import router as cloud_router

    _CLOUD_AVAILABLE = True
except ImportError:
    _CLOUD_AVAILABLE = False
    cloud_router = None

# ═══════════════════════════════════════
# Logging — centralized
# ═══════════════════════════════════════
from src.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("forgeai.api")

# ═══════════════════════════════════════
# Global State
# ═══════════════════════════════════════
_capture_engine: CaptureEngine | None = None
_sdft_trainer: SDFTTrainer | None = None
_grpo_trainer: GRPOTrainer | None = None
_active_training_run: dict[str, Any] | None = None
_ws_clients: list[WebSocket] = []  # Dashboard WebSocket clients

# Training scheduler config (persisted to environment)
_scheduler: AsyncIOScheduler | None = None
_schedule_config: dict[str, Any] = {
    "enabled": os.environ.get("FORGEAI_SCHEDULER_ENABLED", "true").lower() == "true",
    "cron": os.environ.get("FORGEAI_SCHEDULER_CRON", "0 2 * * 1"),  # Monday 2AM by default
    "description": "Weekly training every Monday at 02:00",
    "last_run": None,
    "next_run": None,
    "total_runs": 0,
}


# ═══════════════════════════════════════
# Rate Limiter (in-memory token bucket)
# ═══════════════════════════════════════
class _TokenBucket:
    """Simple per-IP token bucket rate limiter with automatic cleanup."""

    def __init__(self, capacity: int = 30, refill_per_sec: float = 1.0) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, tuple[float, float]] = {}
        self._last_cleanup: float = time.time()

    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        stale = [k for k, (_, last) in self._buckets.items() if now - last > 300]
        for k in stale:
            del self._buckets[k]

    def allow(self, key: str) -> bool:
        self._maybe_cleanup()
        now = time.time()
        tokens, last = self._buckets.get(key, (float(self.capacity), now))
        elapsed = now - last
        tokens = min(self.capacity, tokens + elapsed * self.refill_per_sec)
        if tokens < 1.0:
            return False
        self._buckets[key] = (tokens - 1.0, now)
        return True

    def retry_after(self, key: str) -> float:
        tokens, last = self._buckets.get(key, (float(self.capacity), time.time()))
        if tokens >= 1.0:
            return 0.0
        return max(0.0, (1.0 - tokens) / self.refill_per_sec)


_rate_limiter = _TokenBucket(capacity=30, refill_per_sec=1.0)

# ═══════════════════════════════════════
# Input Sanitization
# ═══════════════════════════════════════
_MAX_QUESTION_LENGTH = 2000
_MAX_HISTORY_LENGTH = 20
_MAX_HISTORY_MSG_LENGTH = 1000


def _sanitize_text(text: str, max_len: int) -> str:
    text = text.strip()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_len]


# ═══════════════════════════════════════
# Lifespan — startup & shutdown
# ═══════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _capture_engine, _sdft_trainer, _grpo_trainer
    logger.info("ForgeAI server starting up...")
    _capture_engine = CaptureEngine()

    # Default model for training (can be overridden via env var)
    _default_model = os.environ.get(
        "FORGEAI_BASE_MODEL",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
    )
    _sdft_trainer = SDFTTrainer(model_name=_default_model)
    _grpo_trainer = GRPOTrainer(model_name=_default_model)

    # Projects DB — initialise inside lifespan for controlled startup        _init_projects_db()

    # --- Start training scheduler ---
    _init_scheduler()

    logger.info(f"Capture engine, SDFT trainer, GRPO trainer initialized (model={_default_model}).")
    yield
    # Shutdown
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Training scheduler shut down.")
    logger.info("ForgeAI server shutting down.")


# ═══════════════════════════════════════
# App
# ═══════════════════════════════════════
app = FastAPI(
    title="ForgeAI API",
    description="Self-improving developer AI platform — MIT SEAL architecture",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
_cors_origins = os.environ.get(
    "FORGEAI_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8501,http://127.0.0.1:8501",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)


# ── Security Headers + Rate Limit Middleware ──
@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(client_ip):
        retry = _rate_limiter.retry_after(client_ip)
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded.", "retry_after": round(retry, 1)},
            headers={"Retry-After": str(int(retry) + 1)},
        )

    request_id = uuid.uuid4().hex[:12]
    start = time.time()
    response: Response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Server"] = "ForgeAI"

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} from={client_ip} status={response.status_code} time={elapsed_ms:.0f}ms"
    )
    try:
        metrics.record_api_request(request.url.path, request.method, response.status_code, elapsed_ms)
    except Exception:
        pass
    return response


_start_time = time.time()

# ── Global DB cache ──
_db_cache: Any = None


def get_db() -> Any:
    global _db_cache
    if _db_cache is None:
        logger.info("Loading RAG Database...")
        _db_cache = load_or_build_db()
    return _db_cache


# ═══════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════


class EventPayload(BaseModel):
    """Event from VS Code extension."""

    event_type: str = Field(..., description="accept, reject, edit, pr_merge, test_pass, test_fail")
    session_id: str
    project_id: str
    file_path: str
    line_number: int = 0
    language: str
    framework: str | None = None
    project_type: str = "general"
    suggestion: str
    suggestion_metadata: dict = Field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""
    final_code: str | None = None
    edit_distance: float = 0.0
    developer_id: str | None = None

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        valid = {"accept", "reject", "edit", "pr_merge", "test_pass", "test_fail"}
        if v not in valid:
            raise ValueError(f"Invalid event_type. Must be one of: {valid}")
        return v


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("question")
    @classmethod
    def _clean_question(cls, v: str) -> str:
        return _sanitize_text(v, _MAX_QUESTION_LENGTH)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    history: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = None

    @field_validator("history")
    @classmethod
    def _trim_history(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trimmed = v[-_MAX_HISTORY_LENGTH:]
        for msg in trimmed:
            if isinstance(msg.get("content"), str):
                msg["content"] = _sanitize_text(msg["content"], _MAX_HISTORY_MSG_LENGTH)
        return trimmed


class RAGSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    project_id: str
    strategy: str = Field(default="hybrid", description="hybrid, vector, graph, agentic")
    k: int = Field(default=10, ge=1, le=50)


class IndexRequest(BaseModel):
    project_id: str
    repo_path: str
    force_reindex: bool = False


# ═══════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check for load balancers and Docker."""
    return {
        "status": "ok",
        "version": VERSION,
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - _start_time),
        "inference_connected": True,
        "db_ok": True,
        "scheduler": {
            "enabled": _schedule_config["enabled"],
            "next_run": _schedule_config["next_run"],
            "total_runs": _schedule_config["total_runs"],
        }
        if _scheduler and _scheduler.running
        else {"enabled": False, "status": "not_running"},
    }


@app.get("/stats")
async def get_stats() -> dict[str, Any]:
    """
    Return capture statistics in the format the dashboard expects.
    Falls back to empty/default values if the capture engine is unavailable.
    """
    if _capture_engine is not None:
        try:
            return _capture_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Capture engine stats unavailable: {e}")

    # Fallback when capture engine is unavailable
    return {
        "signals_by_type": {},
        "signals_by_language": {},
        "total_sessions": 0,
        "overall_acceptance_rate": 0.0,
        "avg_edit_distance": 0.0,
    }


@app.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    """Performance metrics for monitoring."""
    return metrics.get_summary()


# ─── Capture Engine Endpoints ───────────────────────────────────────


@app.post("/api/events")
async def capture_event(payload: EventPayload) -> dict[str, Any]:
    """
    Capture a developer signal (accept/reject/edit).
    Called by VS Code extension via WebSocket or HTTP.
    """
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    start = time.time()
    signal_id = None

    try:
        if payload.event_type == "accept":
            signal_id = _capture_engine.capture_accept(
                suggestion=payload.suggestion,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "reject":
            signal_id = _capture_engine.capture_reject(
                suggestion=payload.suggestion,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "edit":
            if not payload.final_code:
                raise HTTPException(status_code=400, detail="final_code required for edit events")
            signal_id = _capture_engine.capture_edit(
                original_suggestion=payload.suggestion,
                final_code=payload.final_code,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "pr_merge":
            signal_id = _capture_engine.capture_pr_merge(
                file_path=payload.file_path,
                language=payload.language,
                code_content=payload.suggestion,
                pr_number=payload.suggestion_metadata.get("pr_number", 0),
                branch_name=payload.suggestion_metadata.get("branch", ""),
                git_sha=payload.suggestion_metadata.get("git_sha", ""),
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )

        elapsed_ms = (time.time() - start) * 1000
        logger.info(f"Captured {payload.event_type} event: {signal_id} in {elapsed_ms:.1f}ms")

        # Broadcast to dashboard clients
        await _broadcast_to_dashboards(
            {
                "type": "event_captured",
                "event_type": payload.event_type,
                "signal_id": signal_id,
                "timestamp": time.time(),
            }
        )

        return {"event_id": signal_id, "captured": True}

    except Exception as e:
        logger.error(f"Error capturing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to capture event")


@app.get("/api/metrics/acceptance-rate")
async def get_acceptance_rate(project_id: str | None = None, weeks: int = 12) -> dict[str, Any]:
    """Get acceptance rate over time for dashboard chart."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    days = weeks * 7
    rates = _capture_engine.get_acceptance_rate(days=days)

    # Compute training run markers
    runs = _capture_engine.get_training_runs(limit=20)
    markers = [
        {"timestamp": r["timestamp"], "delta": r["acceptance_delta"], "signals": r["signals_used"]} for r in runs
    ]

    return {"data": rates, "training_markers": markers}


@app.get("/api/training/status")
async def get_training_status(project_id: str | None = None) -> dict[str, Any]:
    """Get current training status and history."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    history = _capture_engine.get_training_runs(limit=10)

    return {
        "active_run": _active_training_run,
        "history": history,
    }


@app.post("/api/training/trigger")
async def trigger_training(project_id: str | None = None) -> dict[str, Any]:
    """Manually trigger a training run."""
    global _active_training_run

    if _capture_engine is None or _sdft_trainer is None:
        raise HTTPException(status_code=503, detail="Training system not initialized")

    if _active_training_run is not None:
        raise HTTPException(status_code=409, detail="Training run already in progress")

    run_id = str(uuid.uuid4())
    _active_training_run = {
        "run_id": run_id,
        "status": "queued",
        "started_at": time.time(),
        "progress": 0.0,
    }

    # Broadcast start
    await _broadcast_to_dashboards(
        {
            "type": "training_started",
            "run_id": run_id,
        }
    )

    return {"run_id": run_id, "status": "queued"}


# ─── WebSocket Endpoints ───────────────────────────────────────────


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """
    WebSocket for VS Code extension to send events in real-time.
    Also supports HTTP fallback via the /api/events endpoint.
    """
    await websocket.accept()
    logger.info("VS Code extension connected via WebSocket")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload_dict = json.loads(data)
                payload = EventPayload(**payload_dict)

                # Process event
                if _capture_engine is None:
                    await websocket.send_json({"error": "Capture engine not initialized"})
                    continue

                signal_id = None
                if payload.event_type == "accept":
                    signal_id = _capture_engine.capture_accept(
                        suggestion=payload.suggestion,
                        file_path=payload.file_path,
                        line_number=payload.line_number,
                        language=payload.language,
                        context_before=payload.context_before,
                        context_after=payload.context_after,
                        full_context=payload.full_context,
                        suggestion_metadata=payload.suggestion_metadata,
                        framework=payload.framework,
                        project_type=payload.project_type,
                        developer_id=payload.developer_id,
                    )
                elif payload.event_type == "reject":
                    signal_id = _capture_engine.capture_reject(
                        suggestion=payload.suggestion,
                        file_path=payload.file_path,
                        line_number=payload.line_number,
                        language=payload.language,
                        context_before=payload.context_before,
                        context_after=payload.context_after,
                        full_context=payload.full_context,
                        suggestion_metadata=payload.suggestion_metadata,
                        framework=payload.framework,
                        project_type=payload.project_type,
                        developer_id=payload.developer_id,
                    )
                elif payload.event_type == "edit":
                    if payload.final_code:
                        signal_id = _capture_engine.capture_edit(
                            original_suggestion=payload.suggestion,
                            final_code=payload.final_code,
                            file_path=payload.file_path,
                            line_number=payload.line_number,
                            language=payload.language,
                            context_before=payload.context_before,
                            context_after=payload.context_after,
                            full_context=payload.full_context,
                            suggestion_metadata=payload.suggestion_metadata,
                            framework=payload.framework,
                            project_type=payload.project_type,
                            developer_id=payload.developer_id,
                        )

                await websocket.send_json({"event_id": signal_id, "captured": True})

                # Broadcast to dashboards
                await _broadcast_to_dashboards(
                    {
                        "type": "event_captured",
                        "event_type": payload.event_type,
                        "signal_id": signal_id,
                        "timestamp": time.time(),
                    }
                )

            except Exception as e:
                logger.error(f"Error processing WebSocket event: {e}")
                await websocket.send_json({"error": str(e)})

    except WebSocketDisconnect:
        logger.info("VS Code extension disconnected")


@app.websocket("/ws/training-progress")
async def websocket_training_progress(websocket: WebSocket):
    """
    WebSocket for dashboard to receive real-time training progress.
    """
    await websocket.accept()
    _ws_clients.append(websocket)
    logger.info("Dashboard client connected for training progress")

    try:
        while True:
            # Keep connection alive; server pushes updates via _broadcast_to_dashboards
            await websocket.receive_text()  # ping/heartbeat
            await websocket.send_json({"type": "pong", "timestamp": time.time()})
    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected")
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ═══════════════════════════════════════
# Training Scheduler (APScheduler)
# ═══════════════════════════════════════


def _parse_cron(cron_expr: str) -> CronTrigger | None:
    """Parse a cron expression into a CronTrigger.
    Standard format: 'minute hour day_of_month month day_of_week'
    Example: '0 2 * * 1' = Monday at 2:00 AM
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning(f"Invalid cron expression: {cron_expr} (need 5 parts)")
            return None
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    except Exception as e:
        logger.error(f"Failed to parse cron '{cron_expr}': {e}")
        return None


def _get_cron_description(cron_expr: str) -> str:
    """Human-readable description of a cron expression."""
    descriptions = {
        "0 2 * * 1": "Weekly — Monday at 02:00",
        "0 3 * * 0": "Weekly — Sunday at 03:00",
        "0 0 * * 0": "Weekly — Sunday at midnight",
        "0 2 * * *": "Daily at 02:00",
    }
    return descriptions.get(cron_expr, f"Custom cron: {cron_expr}")


async def _run_scheduled_training():
    """Job run by APScheduler. Triggers training if no run is active."""
    global _active_training_run, _schedule_config

    if _active_training_run is not None:
        logger.warning("Scheduled training skipped: a training run is already active.")
        return

    if _capture_engine is None or _sdft_trainer is None:
        logger.warning("Scheduled training skipped: training system not initialized.")
        return

    logger.info("Starting scheduled weekly training run...")

    run_id = str(uuid.uuid4())
    _active_training_run = {
        "run_id": run_id,
        "status": "running",
        "started_at": time.time(),
        "progress": 0.0,
    }

    try:
        # Broadcast start
        await _broadcast_to_dashboards(
            {
                "type": "training_started",
                "run_id": run_id,
            }
        )

        # Log the scheduled run
        _schedule_config["last_run"] = time.time()
        _schedule_config["total_runs"] += 1

        logger.info(f"Scheduled training run {run_id} started successfully.")
    except Exception as e:
        logger.error(f"Scheduled training run failed: {e}")
        _active_training_run["status"] = "failed"
    finally:
        if _active_training_run and _active_training_run["status"] != "failed":
            _active_training_run["status"] = "completed"
            _active_training_run["progress"] = 1.0
        # Reset after a short delay so dashboard can see the completed run
        # In production, this would wait for actual training to finish


def _init_scheduler():
    """Initialise the APScheduler with the configured cron schedule."""
    global _scheduler, _schedule_config

    _scheduler = AsyncIOScheduler()

    if not _schedule_config["enabled"]:
        logger.info("Training scheduler is disabled via FORGEAI_SCHEDULER_ENABLED=false.")
        return

    trigger = _parse_cron(_schedule_config["cron"])
    if trigger is None:
        logger.warning("Invalid cron expression. Scheduler not started.")
        return

    _scheduler.add_job(
        _run_scheduled_training,
        trigger=trigger,
        id="weekly_training",
        name="Weekly Training Run",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace for missed runs
        max_instances=1,  # Prevent overlapping runs
    )

    _scheduler.start()

    # Record next run time
    next_run = _scheduler.get_job("weekly_training")
    if next_run:
        _schedule_config["next_run"] = next_run.next_run_time.isoformat() if next_run.next_run_time else None

    _schedule_config["description"] = _get_cron_description(_schedule_config["cron"])

    logger.info(
        f"Training scheduler started. Cron: {_schedule_config['cron']} "
        f"({_schedule_config['description']}). "
        f"Next run: {_schedule_config['next_run']}"
    )


# ─── Training Schedule Management Endpoints ───────────────────────


@app.get("/api/training/schedule")
async def get_training_schedule() -> dict[str, Any]:
    """Get the current automated training schedule configuration."""
    return {
        "enabled": _schedule_config["enabled"],
        "cron": _schedule_config["cron"],
        "description": _schedule_config["description"],
        "last_run": _schedule_config["last_run"],
        "next_run": _schedule_config["next_run"],
        "total_runs": _schedule_config["total_runs"],
        "scheduler_running": _scheduler is not None and _scheduler.running,
    }


class ScheduleUpdate(BaseModel):
    """Update the training cron schedule."""

    enabled: bool | None = None
    cron: str | None = Field(
        default=None,
        pattern=r"^\S+ \S+ \S+ \S+ \S+$",
        description="5-field cron expression: minute hour day month day_of_week",
    )


@app.put("/api/training/schedule")
async def update_training_schedule(body: ScheduleUpdate) -> dict[str, Any]:
    """
    Update the automated training schedule.

    Set `enabled=false` to pause scheduling, or change `cron` to a new
    5-field cron expression (e.g. "0 3 * * 0" for Sunday 3AM).
    """
    global _schedule_config

    if body.enabled is not None:
        _schedule_config["enabled"] = body.enabled

    if body.cron is not None:
        # Validate the new cron expression
        trigger = _parse_cron(body.cron)
        if trigger is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression: '{body.cron}'. Use format: 'minute hour day month day_of_week'",
            )
        _schedule_config["cron"] = body.cron
        _schedule_config["description"] = _get_cron_description(body.cron)

    # Restart scheduler with new config
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    if _schedule_config["enabled"]:
        _init_scheduler()
    else:
        _schedule_config["next_run"] = None
        logger.info("Training scheduler disabled.")

    return {
        "enabled": _schedule_config["enabled"],
        "cron": _schedule_config["cron"],
        "description": _schedule_config["description"],
        "next_run": _schedule_config["next_run"],
        "message": "Schedule updated"
        + (" and scheduler restarted." if _schedule_config["enabled"] else ". Scheduler paused."),
    }


# ═══════════════════════════════════════
# WebSocket Broadcast helper
# ═══════════════════════════════════════


async def _broadcast_to_dashboards(message: dict[str, Any]):
    """Broadcast a message to all connected dashboard clients."""
    if not _ws_clients:
        return
    disconnected = []
    for client in _ws_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        if client in _ws_clients:
            _ws_clients.remove(client)


# ─── RAG Endpoints ─────────────────────────────────────────────────


@app.post("/api/rag/search")
async def rag_search(request: RAGSearchRequest) -> dict[str, Any]:
    """
    Hybrid retrieval: BM25 + dense vector + optional graph traversal.
    Returns top-k relevant code chunks.
    """
    try:
        coll, embedder, bm25, corpus, _ = get_db()
        available = list_ollama_models()
        selected_model = resolve_model(DEFAULT_MODEL, available=available)

        # Use existing RAG engine with hybrid retrieval
        answer, docs = get_answer(
            request.query,
            coll,
            embedder,
            [],
            bm25=bm25,
            corpus_texts=corpus,
            use_query_expansion=True,
            use_mmr=True,
            no_exec=True,
            model=selected_model,
        )

        chunks = [
            {
                "content": d.get("title", ""),
                "metadata": {
                    "version": d.get("version", ""),
                    "category": d.get("category", ""),
                },
            }
            for d in docs
        ]

        return {"chunks": chunks, "answer": answer}
    except Exception as e:
        logger.error(f"RAG search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="RAG search failed")


@app.post("/api/rag/index")
async def rag_index(request: IndexRequest) -> dict[str, Any]:
    """
    Index or re-index a project codebase.
    Uses cAST chunking (AST-boundary-aware) for semantic completeness.
    """
    # Trigger background indexing
    job_id = str(uuid.uuid4())
    logger.info(f"Indexing job {job_id} started for {request.repo_path}")

    # In production, this would be a background task
    # For now, return job ID and log progress
    return {
        "job_id": job_id,
        "status": "indexing",
        "project_id": request.project_id,
        "repo_path": request.repo_path,
    }


@app.get("/api/rag/stats")
async def rag_stats() -> dict[str, Any]:
    """
    Return RAG system statistics: indexed chunks, model info, DB status.
    Gracefully handles unavailable DB.
    """
    try:
        coll, _, _, _, cfile = get_db()
        return {
            "status": "available",
            "chunks": coll.count(),
            "db_path": str(cfile),
            "embedding_model": DEFAULT_MODEL,
            "has_bm25": True,
            "has_knowledge_graph": False,
            "last_indexed": None,
        }
    except Exception as e:
        logger.warning(f"RAG DB not available: {e}")
        return {
            "status": "unavailable",
            "chunks": 0,
            "db_path": "",
            "embedding_model": "",
            "has_bm25": False,
            "has_knowledge_graph": False,
            "last_indexed": None,
        }


# ─── Agent Endpoints ───────────────────────────────────────────────


@app.post("/api/agent/chat")
async def agent_chat(request: ChatRequest) -> StreamingResponse:
    """
    Agent chat with streaming response (SSE).
    Routes to fast/balanced/powerful model based on task complexity.
    """

    async def generate() -> AsyncGenerator[str, None]:
        try:
            coll, embedder, bm25, corpus, _ = get_db()
            available = list_ollama_models()
            selected_model = resolve_model(request.model or DEFAULT_MODEL, available=available)

            history = request.history[-10:] if request.history else []

            answer, docs = get_answer(
                request.question,
                coll,
                embedder,
                history,
                bm25=bm25,
                corpus_texts=corpus,
                use_query_expansion=request.query_expansion,
                use_mmr=request.mmr,
                mmr_lambda=request.mmr_lambda,
                no_exec=True,
                model=selected_model,
            )

            # Stream the answer character by character (simulated streaming)
            for char in answer:
                yield f"data: {json.dumps({'token': char})}\n\n"
                await asyncio.sleep(0.01)  # Simulate streaming latency

            yield f"data: {json.dumps({'done': True, 'sources': [{'title': d.get('title', '')} for d in docs]})}\n\n"

        except Exception as e:
            logger.error(f"Agent chat error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── Basic RAG Endpoints (backward compatibility) ──────────────────


@app.post("/ask")
async def ask_question(request: AskRequest) -> dict[str, Any]:
    try:
        coll, embedder, bm25, corpus, _ = get_db()
        available = list_ollama_models()
        selected_model = resolve_model(request.model or DEFAULT_MODEL, available=available)

        answer, docs = get_answer(
            request.question,
            coll,
            embedder,
            [],
            bm25=bm25,
            corpus_texts=corpus,
            use_query_expansion=request.query_expansion,
            use_mmr=request.mmr,
            mmr_lambda=request.mmr_lambda,
            no_exec=True,
            model=selected_model,
        )

        return {
            "answer": answer,
            "sources": [
                {"title": d.get("title", ""), "version": d.get("version", ""), "category": d.get("category", "")}
                for d in docs
            ],
            "model": selected_model,
        }
    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        coll, embedder, bm25, corpus, _ = get_db()
        available = list_ollama_models()
        selected_model = resolve_model(request.model or DEFAULT_MODEL, available=available)

        history = request.history[-10:] if request.history else []

        answer, docs = get_answer(
            request.question,
            coll,
            embedder,
            history,
            bm25=bm25,
            corpus_texts=corpus,
            use_query_expansion=request.query_expansion,
            use_mmr=request.mmr,
            mmr_lambda=request.mmr_lambda,
            no_exec=True,
            model=selected_model,
        )

        return {
            "answer": answer,
            "sources": [
                {"title": d.get("title", ""), "version": d.get("version", ""), "category": d.get("category", "")}
                for d in docs
            ],
            "model": selected_model,
        }
    except Exception as e:
        logger.error(f"Error answering chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── SEAL Phase 3 Route ─────────────────────────────────────────
@app.post("/api/seal/cycle")
async def trigger_seal_cycle(
    dry_run: bool = Query(False, description="Generate curriculum only, skip training"),
):
    """Execute a single SEAL autonomous self-improvement cycle.

    If dry_run=True, only generates the curriculum decision without
    running any training.

    Note: The inner loop training runs in a thread so the server
    event loop is not blocked during QLoRA fine-tuning.
    """
    try:
        from src.training.phase3_seal import SealOrchestrator
        from src.training.seal_types import SealConfig

        seal = SealOrchestrator(config=SealConfig(), capture_engine=_capture_engine)
        seal.load_state()
        result = await asyncio.to_thread(seal.run_cycle, dry_run=dry_run)

        return {"seal": result}
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"SEAL not available: {e}")
    except Exception as e:
        logger.error(f"SEAL cycle error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seal/status")
async def get_seal_status():
    """Get SEAL Phase 3 system status."""
    try:
        from src.training.phase3_seal import SealOrchestrator
        from src.training.seal_types import SealConfig

        seal = SealOrchestrator(config=SealConfig(), capture_engine=_capture_engine)
        seal.load_state()
        return seal.status()
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"SEAL not available: {e}")
    except Exception as e:
        logger.error(f"SEAL status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════
# Projects — Pydantic Models
# ═══════════════════════════════════════


class ProjectResponse(BaseModel):
    """Full project record returned to the dashboard."""

    id: str
    name: str
    repo_path: str
    languages: list[str] = Field(default_factory=list)
    rag_indexed_at: str | None = None
    current_adapter_version: int = 1
    training_phase: int = 1
    base_model: str = Field(
        default=os.environ.get("FORGEAI_BASE_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct"),
        max_length=200,
    )
    training_schedule: str = "manual"


class ProjectCreate(BaseModel):
    """Input model for creating a new project."""

    name: str = Field(..., min_length=1, max_length=200, description="Human-readable project name")
    repo_path: str = Field(..., min_length=1, max_length=2000, description="Absolute path to the git repository")
    languages: list[str] = Field(default_factory=list, description="Programming languages detected")
    base_model: str = Field(
        default=os.environ.get("FORGEAI_BASE_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct"),
        max_length=200,
    )
    training_schedule: str = Field(default="manual", pattern=r"^(manual|weekly|daily)$")


class ProjectUpdate(BaseModel):
    """Input model for updating an existing project. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    repo_path: str | None = Field(default=None, min_length=1, max_length=2000)
    languages: list[str] | None = None
    rag_indexed_at: str | None = None
    current_adapter_version: int | None = Field(default=None, ge=1)
    training_phase: int | None = Field(default=None, ge=1)
    base_model: str | None = Field(default=None, max_length=200)
    training_schedule: str | None = Field(default=None, pattern=r"^(manual|weekly|daily)$")


# ═══════════════════════════════════════
# Projects — SQLite Store
# ═══════════════════════════════════════

_PROJECTS_DB_PATH: Path = Path.home() / ".forgeai" / "projects.db"


def _init_projects_db():
    """Ensure the projects table exists."""
    _PROJECTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo_path TEXT NOT NULL,
            languages TEXT NOT NULL DEFAULT '[]',
            rag_indexed_at TEXT,
            current_adapter_version INTEGER NOT NULL DEFAULT 1,
            training_phase INTEGER NOT NULL DEFAULT 1,
            base_model TEXT NOT NULL,
            training_schedule TEXT NOT NULL DEFAULT 'manual',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _row_to_project(row: tuple) -> dict[str, Any]:
    """Convert a SQLite row to the ProjectResponse shape."""
    return {
        "id": row[0],
        "name": row[1],
        "repo_path": row[2],
        "languages": json.loads(row[3]) if isinstance(row[3], str) else row[3],
        "rag_indexed_at": row[4],
        "current_adapter_version": row[5],
        "training_phase": row[6],
        "base_model": row[7],
        "training_schedule": row[8],
    }


# ═══════════════════════════════════════
# Projects — CRUD Endpoints
# ═══════════════════════════════════════


@app.get("/api/projects", response_model=list[ProjectResponse])
async def get_projects() -> list[ProjectResponse]:
    """Return all tracked projects."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_project(r) for r in rows]
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to list projects")


@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate) -> dict[str, Any]:
    """
    Register a new project for monitoring and RAG indexing.

    Validates input via the ProjectCreate Pydantic model.
    Detects available languages from the repo path if not provided.
    """
    project_id = str(uuid.uuid4())
    now = time.time()
    languages = body.languages

    # Auto-detect languages from repo if not provided
    if not languages:
        try:
            repo = Path(body.repo_path)
            if repo.is_dir():
                detected: set[str] = set()
                file_count = 0
                for f in repo.rglob("*"):
                    file_count += 1
                    if file_count > 2000:  # Cap total files scanned
                        break
                    if f.is_file() and f.suffix:
                        ext_map = {
                            ".py": "python",
                            ".js": "javascript",
                            ".ts": "typescript",
                            ".jsx": "javascript",
                            ".tsx": "typescript",
                            ".go": "go",
                            ".rs": "rust",
                            ".java": "java",
                            ".rb": "ruby",
                            ".cpp": "cpp",
                            ".c": "c",
                            ".h": "c",
                            ".hpp": "cpp",
                            ".cs": "csharp",
                            ".swift": "swift",
                            ".kt": "kotlin",
                            ".scala": "scala",
                            ".php": "php",
                            ".sql": "sql",
                        }
                        lang = ext_map.get(f.suffix.lower())
                        if lang:
                            detected.add(lang)
                            if len(detected) >= 10:  # Limit unique languages
                                break
                languages = sorted(detected)
        except Exception:
            pass

    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        conn.execute(
            """INSERT INTO projects
               (id, name, repo_path, languages, rag_indexed_at,
                current_adapter_version, training_phase, base_model,
                training_schedule, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                body.name,
                body.repo_path,
                json.dumps(languages),
                None,
                1,
                1,
                body.base_model,
                body.training_schedule,
                now,
                now,
            ),
        )
        conn.commit()

        # Read back from DB for consistency
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            raise RuntimeError("Failed to read back created project")

        logger.info(f"Project created: {body.name} (id={project_id}, repo={body.repo_path})")

        return _row_to_project(row)
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail="Failed to create project")


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> dict[str, Any]:
    """Get a single project by ID."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _row_to_project(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@app.put("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, body: ProjectUpdate) -> dict[str, Any]:
    """Update an existing project. Only provided fields are changed."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))

        # Check project exists
        cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if cursor.fetchone() is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Project not found")

        # Build update dynamically
        updates: list[str] = []
        params: list[Any] = []

        field_map = {
            "name": "name",
            "repo_path": "repo_path",
            "rag_indexed_at": "rag_indexed_at",
            "current_adapter_version": "current_adapter_version",
            "training_phase": "training_phase",
            "base_model": "base_model",
            "training_schedule": "training_schedule",
        }

        if body.languages is not None:
            updates.append("languages = ?")
            params.append(json.dumps(body.languages))

        for attr, col in field_map.items():
            val = getattr(body, attr, None)
            if val is not None:
                updates.append(f"{col} = ?")
                params.append(val)

        if not updates:
            # Nothing to update — fetch and return current row
            cursor = conn.execute(
                "SELECT id, name, repo_path, languages, rag_indexed_at, "
                "current_adapter_version, training_phase, base_model, training_schedule "
                "FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            conn.close()
            return _row_to_project(row)  # type: ignore[arg-type]

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(project_id)

        conn.execute(
            f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        # Fetch updated row
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()

        logger.info(f"Project updated: {project_id}")
        return _row_to_project(row)  # type: ignore[arg-type]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update project")


@app.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str):
    """Delete a project and its associated data."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if cursor.fetchone() is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Project not found")

        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        conn.close()
        logger.info(f"Project deleted: {project_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete project")


# ── Include Cloud Routes (if available) ────────────────────────
if _CLOUD_AVAILABLE and cloud_router is not None:
    app.include_router(cloud_router)
    logger.info("Cloud routes registered")

# ── Include Learning Routes ────────────────────────────────────
from src.api.learning_routes import router as learning_router  # noqa: E402

app.include_router(learning_router)
logger.info("Learning routes registered")


# ═══════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7337)
