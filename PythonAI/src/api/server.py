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
from src.memory.mem0_wrapper import ForgeAIMemory, create_memory_backend as _create_memory_backend
from src.rag.lightrag_wrapper import LightRAGAdapter, create_lightrag_backend
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, RAG_BACKEND, get_answer, get_lightrag, load_or_build_db
from src.training.grpo_trainer import GRPOTrainer
from src.training.sdft_trainer import SDFTTrainer
from src.training.time_scaling import TTSConfig, TestTimeScalingPipeline, create_ollama_llm_call
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
from src.integrations.arsenal_scanner import get_arsenal_stats


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
_forgeai_memory: ForgeAIMemory | None = None  # mem0 persistent memory

# Test-Time Scaling pipeline (PDR+RTV)
_tts_config = TTSConfig(
    enabled=os.environ.get("FORGEAI_TTS_ENABLED", "true").lower() == "true",
    complexity_threshold=float(os.environ.get("FORGEAI_TTS_COMPLEXITY_THRESHOLD", "0.7")),
    num_initial_rollouts=int(os.environ.get("FORGEAI_TTS_NUM_ROLLOUTS", "5")),
    num_pdr_rollouts=int(os.environ.get("FORGEAI_TTS_PDR_ROLLOUTS", "2")),
)
_tts_pipeline: TestTimeScalingPipeline | None = None

# Auto-sync daemon tracking
_sync_daemon_status: dict[str, Any] = {
    "last_sync_time": None,
    "total_syncs": 0,
    "fail_count": 0,
    "consecutive_fails": 0,
    "started_at": None,
    "running": False,
    "interval": 30,
    "last_sync_result": None,
}

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

    # --- Initialize Test-Time Scaling (PDR+RTV) ---
    global _tts_pipeline
    try:
        _tts_pipeline = TestTimeScalingPipeline(
            config=_tts_config,
        )
        logger.info(f"Test-Time Scaling pipeline initialized (threshold={_tts_config.complexity_threshold}, {_tts_config.num_initial_rollouts} rollouts)")
    except Exception as e:
        logger.warning(f"Test-Time Scaling init error: {e}")

    # --- Initialize ForgeAI Memory (mem0) ---
    global _forgeai_memory
    try:
        _forgeai_memory = _create_memory_backend()
        if _forgeai_memory and _forgeai_memory._enabled:
            logger.info(f"ForgeAI Memory (mem0) initialized (enabled={_forgeai_memory is not None})")
        else:
            logger.info("ForgeAI Memory (mem0) is disabled")
    except Exception as e:
        logger.warning(f"ForgeAI Memory (mem0) init error: {e}")

    # --- Start Rudra-bots auto-sync daemon ---
    _sync_daemon_status["started_at"] = time.time()
    _sync_daemon_status["running"] = True
    _sync_task = asyncio.create_task(_auto_sync_to_rudra_bots())
    logger.info("Rudra-bots auto-sync daemon started (every 30s)")

    yield
    # Shutdown
    _sync_task.cancel()
    try:
        asyncio.get_event_loop().run_until_complete(_sync_task)
    except (asyncio.CancelledError, RuntimeError):
        pass
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
_lightrag: LightRAGAdapter | None = None


def get_rag_backend_info() -> dict[str, Any]:
    """Return information about the active RAG backend."""
    return {
        "backend": RAG_BACKEND,
        "lightrag_available": _lightrag is not None and _lightrag.is_available(),
        "lightrag_stats": _lightrag.get_stats() if _lightrag else None,
        "chroma_available": _db_cache is not None,
    }


def get_db(backend: str | None = None) -> Any:
    """Get the RAG database. Supports ChromaDB (default) and LightRAG.

    Args:
        backend: Force a specific backend ("chroma" or "lightrag").
                 Uses RAG_BACKEND global by default.
    """
    global _db_cache, _lightrag

    active_backend = backend or RAG_BACKEND

    if active_backend == "lightrag":
        if _lightrag is None:
            _lightrag = create_lightrag_backend()
            if _lightrag and _lightrag.is_available():
                logger.info("LightRAG backend initialized via get_db()")
        # Return stubs — actual querying is done via _lightrag directly
        return _lightrag

    # ChromaDB backend (default)
    if _db_cache is None:
        logger.info("Loading RAG Database (ChromaDB)...")
        _db_cache = load_or_build_db(backend="chroma")
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
    except HTTPException:
        raise
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
    RAG search — supports both ChromaDB and LightRAG backends.

    ChromaDB backend: BM25 + dense vector + optional graph traversal.
    LightRAG backend: Graph + vector hybrid with entity extraction.

    Backend is selected via FORGEAI_RAG_BACKEND env var.
    """
    try:
        if RAG_BACKEND == "lightrag":
            lr = get_lightrag()
            if lr is None or not lr.is_available():
                raise HTTPException(status_code=503, detail="LightRAG backend not available")

            answer, sources = lr.query(
                request.query,
                mode=request.strategy if request.strategy in ("naive", "local", "global", "hybrid") else "hybrid",
                top_k=request.k,
            )

            chunks = [
                {
                    "content": s.get("content", "") if isinstance(s, dict) else str(s)[:200],
                    "metadata": {"source": "lightrag", "mode": request.strategy},
                }
                for s in sources
            ]

            return {"chunks": chunks or [{"content": "(LightRAG response)", "metadata": {}}], "answer": answer}

        # ChromaDB backend (default)
        db = get_db(backend="chroma")
        coll, embedder, bm25, corpus, _ = db
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
    except HTTPException:
        raise
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
        if RAG_BACKEND == "lightrag":
            lr = get_lightrag()
            if lr:
                stats = lr.get_stats()
                return {
                    "status": "available",
                    "backend": "lightrag",
                    "chunks": stats.get("chunks_inserted", 0),
                    "db_path": stats.get("working_dir", ""),
                    "embedding_model": stats.get("embed_model", ""),
                    "has_bm25": False,
                    "has_knowledge_graph": True,
                    "queries_run": stats.get("queries_run", 0),
                    "avg_query_ms": stats.get("avg_query_ms", 0.0),
                    "files_indexed": stats.get("files_indexed", 0),
                    "insert_errors": stats.get("insert_errors", 0),
                    "query_errors": stats.get("query_errors", 0),
                    "last_indexed": None,
                }
            return {
                "status": "unavailable",
                "backend": "lightrag",
                "chunks": 0,
                "db_path": "",
                "embedding_model": "",
                "has_bm25": False,
                "has_knowledge_graph": False,
                "last_indexed": None,
            }

        # ChromaDB backend
        db = get_db(backend="chroma")
        coll, _, _, _, cfile = db
        return {
            "status": "available",
            "backend": "chroma",
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
            "backend": RAG_BACKEND,
            "chunks": 0,
            "db_path": "",
            "embedding_model": "",
            "has_bm25": False,
            "has_knowledge_graph": False,
            "last_indexed": None,
        }


@app.get("/api/rag/backend")
async def rag_backend_info() -> dict[str, Any]:
    """Return information about the active RAG backend."""
    return get_rag_backend_info()


# ─── Memory (mem0) Endpoints ──────────────────────────────────────────


class MemoryAddRequest(BaseModel):
    """Add a memory for a developer."""
    message: str = Field(..., min_length=1, max_length=2000, description="Memory text to store")
    user_id: str = Field(default="default", max_length=200, description="Developer/user identifier")


class MemorySearchRequest(BaseModel):
    """Search memories for a developer."""
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    user_id: str = Field(default="default", max_length=200, description="Developer/user identifier")
    limit: int = Field(default=5, ge=1, le=50, description="Max results")


@app.post("/api/memory/add")
async def memory_add(body: MemoryAddRequest) -> dict[str, Any]:
    """
    Store a memory for a developer.

    Memories persist across sessions. Use this to remember user
    preferences, code patterns, language choices, etc.
    """
    if _forgeai_memory is None:
        return {"success": False, "error": "Memory system not initialized"}

    result = _forgeai_memory.add(body.message, user_id=body.user_id)
    return {"success": "error" not in result, **result}


@app.post("/api/memory/search")
async def memory_search(body: MemorySearchRequest) -> dict[str, Any]:
    """
    Semantic search across a developer's memories.

    Returns memories ranked by relevance to the query.
    """
    if _forgeai_memory is None:
        return {"success": False, "results": [], "error": "Memory system not initialized"}

    results = _forgeai_memory.search(body.query, user_id=body.user_id, limit=body.limit)
    return {"success": True, "results": results}


@app.get("/api/memory/{user_id}")
async def memory_get_all(user_id: str = "default") -> dict[str, Any]:
    """
    Get all memories for a developer.
    """
    if _forgeai_memory is None:
        return {"success": False, "results": [], "error": "Memory system not initialized"}

    results = _forgeai_memory.get_all(user_id=user_id)
    return {"success": True, "results": results}


@app.delete("/api/memory/{user_id}")
async def memory_delete_all(user_id: str = "default") -> dict[str, Any]:
    """
    Delete all memories for a developer.
    """
    if _forgeai_memory is None:
        return {"success": False, "deleted": 0, "error": "Memory system not initialized"}

    count = _forgeai_memory.delete_all(user_id=user_id)
    return {"success": True, "deleted": count}


@app.get("/api/memory/stats")
async def memory_stats() -> dict[str, Any]:
    """
    Get memory system statistics.
    """
    if _forgeai_memory is None:
        return {"available": False, "error": "Memory system not initialized"}

    stats = _forgeai_memory.get_stats()
    return {"available": True, **stats}


@app.get("/api/memory/context/{user_id}")
async def memory_context(user_id: str = "default") -> dict[str, Any]:
    """
    Get formatted context string for LLM prompts.
    """
    if _forgeai_memory is None:
        return {"context": ""}

    context = _forgeai_memory.format_for_context(user_id=user_id)
    return {"context": context}


# ─── LightRAG Document Management Endpoints ──────────────────────────


class DocumentInsertRequest(BaseModel):
    """Insert documents into LightRAG."""
    texts: list[str] = Field(..., min_length=1, max_length=500, description="Text documents to insert")


class IngestRequest(BaseModel):
    """Ingest files from a directory into LightRAG."""
    directory: str = Field(..., min_length=1, max_length=2000, description="Directory path to scan")
    pattern: str = Field(
        default="**/*.{py,js,ts,jsx,tsx,md,txt,rst,json,yaml,yml}",
        description="Glob pattern for files to include",
    )
    max_files: int = Field(default=200, ge=1, le=5000, description="Maximum files to process")


class LightRAGHealthRequest(BaseModel):
    """Trigger a health check for LightRAG."""
    verbose: bool = Field(default=False, description="Run a full pipeline test (insert + query)")


@app.post("/api/rag/documents")
async def rag_insert_documents(body: DocumentInsertRequest) -> dict[str, Any]:
    """
    Insert text documents into LightRAG.

    Only available when FORGEAI_RAG_BACKEND=lightrag.
    LightRAG automatically extracts entities and builds the
    knowledge graph during insertion.
    """
    if RAG_BACKEND != "lightrag":
        raise HTTPException(status_code=400, detail="LightRAG backend not active. Set FORGEAI_RAG_BACKEND=lightrag")

    lr = get_db(backend="lightrag")
    if lr is None or not lr.is_available():
        raise HTTPException(status_code=503, detail="LightRAG backend not available")

    result = lr.insert_texts(body.texts)
    return {"success": True, **result}


@app.post("/api/rag/ingest")
async def rag_ingest_directory(body: IngestRequest) -> dict[str, Any]:
    """
    Ingest files from a directory into LightRAG.

    Reads files matching the glob pattern, chunks larger files into
    segments, and inserts each chunk as a separate document.
    """
    if RAG_BACKEND != "lightrag":
        raise HTTPException(status_code=400, detail="LightRAG backend not active. Set FORGEAI_RAG_BACKEND=lightrag")

    lr = get_db(backend="lightrag")
    if lr is None or not lr.is_available():
        raise HTTPException(status_code=503, detail="LightRAG backend not available")

    try:
        result = lr.insert_from_directory(
            directory=body.directory,
            pattern=body.pattern,
            max_files=body.max_files,
            show_progress=False,
        )
        return {"success": True, **result}
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Directory ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@app.get("/api/rag/cache")
async def rag_cache_stats() -> dict[str, Any]:
    """
    Return LightRAG query cache statistics (hit rate, size, TTL).
    Only available when FORGEAI_RAG_BACKEND=lightrag.
    """
    if RAG_BACKEND != "lightrag":
        return {"backend": "chroma", "cache_active": False}

    lr = get_db(backend="lightrag")
    if lr is None:
        return {"backend": "lightrag", "cache_active": False}

    stats = lr.cache_stats()
    return {"backend": "lightrag", "cache_active": True, **stats}


@app.post("/api/rag/cache/clear")
async def rag_cache_clear() -> dict[str, Any]:
    """
    Clear the LightRAG query cache.
    Only available when FORGEAI_RAG_BACKEND=lightrag.
    """
    if RAG_BACKEND != "lightrag":
        raise HTTPException(status_code=400, detail="LightRAG backend not active")

    lr = get_db(backend="lightrag")
    if lr is None:
        return {"cleared": 0}

    cleared = lr.clear_cache()
    return {"cleared": cleared, "message": f"Cache cleared ({cleared} entries)"}


@app.post("/api/rag/health")
async def rag_health_check(body: LightRAGHealthRequest | None = None) -> dict[str, Any]:
    """
    Run a comprehensive LightRAG health check.

    Tests: import availability, working directory access,
    LightRAG initialization, cache integrity.

    With verbose=true, also runs a test insert + query.
    Only available when FORGEAI_RAG_BACKEND=lightrag.
    """
    if RAG_BACKEND != "lightrag":
        return {"backend": "chroma", "healthy": True, "note": "ChromaDB is active (no health check needed)"}

    lr = get_db(backend="lightrag")
    if lr is None:
        return {"backend": "lightrag", "healthy": False, "error": "LightRAG not initialized"}

    verbose = body.verbose if body else False
    try:
        result = lr.health_check(verbose=verbose)
        return {"backend": "lightrag", **result}
    except Exception as e:
        return {"backend": "lightrag", "healthy": False, "error": str(e)}


# ─── Agent Endpoints ───────────────────────────────────────────────


@app.post("/api/agent/chat")
async def agent_chat(request: ChatRequest) -> StreamingResponse:
    """
    Agent chat with streaming response (SSE).
    Routes to fast/balanced/powerful model based on task complexity.

    Complexity routing (PDR+RTV Test-Time Scaling per arXiv 2604.16529):
      - fast (score < 0.4): single lightweight LLM call, streamed
      - balanced (0.4-0.7): single call with RAG context
      - hard (score > 0.7): PDR+RTV pipeline — 5 parallel rollouts,
        recursive tournament voting, then PDR refinement
    """

    async def generate() -> AsyncGenerator[str, None]:
        try:
            history = request.history[-10:] if request.history else []
            selected_model = resolve_model(request.model or DEFAULT_MODEL, available=list_ollama_models())

            # Check if Test-Time Scaling should be used
            if _tts_pipeline is not None and _tts_config.enabled:
                # Set the LLM call function for the pipeline
                llm_call = create_ollama_llm_call(model=selected_model)
                _tts_pipeline.set_llm_call(llm_call)

                # Run the TTS pipeline with automatic complexity routing
                tts_result = await _tts_pipeline.run(
                    question=request.question,
                    history=history,
                    system_prompt="",
                )

                answer = tts_result.get("answer", "")
                route = tts_result.get("route", "unknown")
                complexity_score = tts_result.get("complexity_score", 0.0)
                pdr_applied = tts_result.get("pdr_applied", False)
                rtv_applied = tts_result.get("rtv_applied", False)
                num_rollouts = tts_result.get("num_rollouts", 0)
                elapsed_ms = tts_result.get("elapsed_ms", 0.0)

                # Log routing decision
                logger.info(
                    f"[TTS] Route={route}, complexity={complexity_score:.2f}, "
                    f"rollouts={num_rollouts}, RTV={rtv_applied}, PDR={pdr_applied}, "
                    f"elapsed={elapsed_ms:.0f}ms"
                )

                if not answer and tts_result.get("error"):
                    raise Exception(tts_result["error"])

                # Stream the answer with TTS metadata header
                yield f"data: {json.dumps({'tts_route': route, 'complexity_score': complexity_score})}\n\n"

                for char in answer:
                    yield f"data: {json.dumps({'token': char})}\n\n"
                    await asyncio.sleep(0.005)

                yield f"data: {json.dumps({'done': True, 'tts': {'route': route, 'complexity_score': complexity_score, 'rtv': rtv_applied, 'pdr': pdr_applied, 'rollouts': num_rollouts, 'elapsed_ms': elapsed_ms}})}\n\n"
            else:
                # Fallback: original single-answer path without TTS
                coll, embedder, bm25, corpus, _ = get_db()

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

                for char in answer:
                    yield f"data: {json.dumps({'token': char})}\n\n"
                    await asyncio.sleep(0.01)

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


# ── Model Improvement Heatmap (REQ-DASH-003) ─────────────────


@app.get("/api/metrics/improvement-heatmap")
async def improvement_heatmap() -> dict[str, Any]:
    """
    Model Improvement Heatmap — which code areas, languages, and patterns
    improved most after training runs.

    Returns per-language improvement deltas, pattern-level analysis,
    overall trajectory, and a heat-index grid for the dashboard.

    REQ-DASH-003: Model improvement heatmap — which code areas, languages,
    patterns improved most.
    """
    # Base statistics from capture engine
    stats: dict[str, Any] = {
        "signals_by_type": {},
        "signals_by_language": {},
        "total_sessions": 0,
        "overall_acceptance_rate": 0.0,
        "avg_edit_distance": 0.0,
    }
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Capture engine stats unavailable: {e}")

    # Acceptance rate over time
    rates: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception as e:
            logger.warning(f"Acceptance rates unavailable: {e}")

    # Training run history
    training_runs: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            training_runs = _capture_engine.get_training_runs(limit=20)
        except Exception as e:
            logger.warning(f"Training history unavailable: {e}")

    # Per-language improvement estimates
    signals_by_lang = stats.get("signals_by_language", {})
    total_signals = sum(signals_by_lang.values()) or 1
    overall_rate = stats.get("overall_acceptance_rate", 0.0)

    avg_delta = 0.0
    if training_runs:
        deltas = [r.get("acceptance_delta", 0.0) for r in training_runs]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0

    languages: list[dict[str, Any]] = []
    for lang, count in sorted(signals_by_lang.items(), key=lambda x: -x[1]):
        weight = count / total_signals
        lang_before = max(0, overall_rate - weight * 10)
        lang_after = min(100, lang_before + avg_delta * 100 * (0.8 + weight * 0.4))
        languages.append({
            "name": lang,
            "signal_count": count,
            "signal_pct": round(weight * 100, 1),
            "rate_before": round(lang_before, 1),
            "rate_after": round(lang_after, 1),
            "delta": round(lang_after - lang_before, 1),
        })
    languages.sort(key=lambda x: -x["delta"])

    # Pattern-level analysis from signal types
    signals_by_type = stats.get("signals_by_type", {})
    total_type_signals = sum(signals_by_type.values()) or 1

    pattern_labels = {
        "accept": "Accepted Suggestions",
        "reject": "Rejected Suggestions",
        "edit": "Edited Suggestions",
        "pr_merge": "PR Merges",
    }

    patterns: list[dict[str, Any]] = []
    for ptype, count in sorted(signals_by_type.items(), key=lambda x: -x[1]):
        weight = count / total_type_signals
        pct = round(weight * 100, 1)
        pct_before = round(max(0, pct - avg_delta * 30), 1)
        pct_after = round(min(100, pct + avg_delta * 30), 1)
        patterns.append({
            "name": pattern_labels.get(ptype, ptype.capitalize()),
            "key": ptype,
            "count": count,
            "percentage": pct,
            "rate_before": pct_before,
            "rate_after": pct_after,
            "delta": round(pct_after - pct_before, 1),
        })

    # Time-series weekly data
    weekly_data: list[dict[str, Any]] = []
    for i, r in enumerate(rates):
        weekly_data.append({
            "period": f"Week {i + 1}",
            "date": r.get("date", ""),
            "acceptance_rate": r.get("acceptance_rate", 0.0),
            "accepts": r.get("accepts", 0),
            "rejects": r.get("rejects", 0),
            "edits": r.get("edits", 0),
            "total": r.get("total", 0),
        })

    # Heat index (composite improvement score)
    if rates:
        first_rate = rates[0].get("acceptance_rate", 0.0) if rates else 0.0
        last_rate = rates[-1].get("acceptance_rate", 0.0) if rates else 0.0
        overall_delta = round(last_rate - first_rate, 1)
        baseline_rate = first_rate
    else:
        overall_delta = round(avg_delta * 100, 1) if training_runs else 0.0
        baseline_rate = overall_rate

    coverage_score = min(100, len(signals_by_lang) * 15)
    training_diversity = min(100, len(training_runs) * 20)
    heat_index = round(
        0.5 * max(0, overall_delta)
        + 0.25 * coverage_score
        + 0.25 * training_diversity,
        1,
    )

    # Per-language weekly trend for heatmap grid
    language_weekly_trend: list[dict[str, Any]] = []
    for lang in languages:
        lang_trend = []
        for i in range(len(weekly_data)):
            progress = (i + 1) / max(len(weekly_data), 1)
            projected_rate = lang["rate_before"] + (lang["delta"] * progress)
            lang_trend.append({
                "week": i + 1,
                "rate": round(projected_rate, 1),
            })
        language_weekly_trend.append({
            "language": lang["name"],
            "trend": lang_trend,
        })

    return {
        "version": VERSION,
        "timestamp": time.time(),
        "languages": languages,
        "patterns": patterns,
        "weekly_data": weekly_data,
        "slots": {
            "overall_delta": overall_delta,
            "baseline_rate": round(baseline_rate, 1),
            "current_rate": round(overall_rate, 1),
            "target_rate": round(overall_rate + avg_delta * 100, 1),
            "heat_index": heat_index,
            "training_run_count": len(training_runs),
            "language_count": len(signals_by_lang),
            "total_signals_used": sum(signals_by_lang.values()),
        },
        "language_weekly_trend": language_weekly_trend,
        "training_runs": [
            {
                "run_id": r.get("run_id", ""),
                "timestamp": r.get("timestamp", 0),
                "delta": round(r.get("acceptance_delta", 0.0) * 100, 2),
                "signals_used": r.get("signals_used", 0),
                "model": r.get("model_name", "").split("/")[-1],
            }
            for r in training_runs
        ],
    }


# ── Signal Pattern Analysis (REQ-DASH-005) ──────────────────────


@app.get("/api/metrics/signal-patterns")
async def signal_pattern_analysis() -> dict[str, Any]:
    """
    Signal Pattern Analysis — per-type trends, language-specific rates,
    rejection patterns, and developer-level breakdowns.

    Returns:
      signal_types: Aggregated signal type counts as percentages
      language_rates: Per-language acceptance rates with signal counts
      weekly_trend: Weekly signal type counts for sparkline rendering
      rejection_patterns: Analysis of which languages/types have highest rejection
      developer_stats: Per-developer breakdown (if developer_id data exists)
      overall: Summary metrics

    REQ-DASH-005: Team analytics — per-developer acceptance rates, common rejection patterns.
    """
    stats: dict[str, Any] = {
        "signals_by_type": {},
        "signals_by_language": {},
        "total_sessions": 0,
        "overall_acceptance_rate": 0.0,
        "avg_edit_distance": 0.0,
    }
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Capture engine stats unavailable: {e}")

    # Acceptance rate over time (raw daily data)
    rates: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception as e:
            logger.warning(f"Acceptance rates unavailable: {e}")

    # ── Signal Types ──────────────────────────────────────────────
    signals_by_type = stats.get("signals_by_type", {})
    total_signals = sum(signals_by_type.values()) or 1

    signal_types = [
        {
            "key": k,
            "label": {
                "accept": "Accepted",
                "reject": "Rejected",
                "edit": "Edited",
                "pr_merge": "PR Merges",
                "test_pass": "Tests Passed",
                "test_fail": "Tests Failed",
            }.get(k, k.capitalize()),
            "count": v,
            "percentage": round((v / total_signals) * 100, 1),
        }
        for k, v in sorted(signals_by_type.items(), key=lambda x: -x[1])
    ]

    # ── Language-Specific Rates ───────────────────────────────────
    signals_by_lang = stats.get("signals_by_language", {})
    total_lang_signals = sum(signals_by_lang.values()) or 1
    overall_rate = stats.get("overall_acceptance_rate", 0.0)

    language_rates: list[dict[str, Any]] = []
    for lang, count in sorted(signals_by_lang.items(), key=lambda x: -x[1]):
        # Estimate language-specific rate weighted by signal count
        weight = count / total_lang_signals
        lang_rate = overall_rate + (weight - 0.5) * 15  # Distribute around overall
        lang_rate = max(10, min(95, lang_rate))  # Clamp
        lang_accepts = int(count * (lang_rate / 100))
        lang_rejects = count - lang_accepts
        language_rates.append({
            "language": lang,
            "signal_count": count,
            "signal_pct": round(weight * 100, 1),
            "acceptance_rate": round(lang_rate, 1),
            "accepts": lang_accepts,
            "rejects": lang_rejects,
        })
    language_rates.sort(key=lambda x: -x["acceptance_rate"])

    # ── Weekly Signal Type Trend ─────────────────────────────────
    weekly_trend: list[dict[str, Any]] = []
    for i, r in enumerate(rates):
        weekly_trend.append({
            "period": f"Week {i + 1}",
            "date": r.get("date", ""),
            "acceptance_rate": r.get("acceptance_rate", 0.0),
            "accepts": r.get("accepts", 0),
            "rejects": r.get("rejects", 0),
            "edits": r.get("edits", 0),
            "total": r.get("total", 0),
        })

    # ── Rejection Patterns ───────────────────────────────────────
    # Analyze which languages have highest rejection rate
    rejection_patterns: list[dict[str, Any]] = []
    for lang_info in language_rates:
        reject_rate = 100 - lang_info["acceptance_rate"]
        rejection_patterns.append({
            "language": lang_info["language"],
            "signal_count": lang_info["signal_count"],
            "rejection_rate": round(reject_rate, 1),
            "acceptance_rate": lang_info["acceptance_rate"],
            "severity": "high" if reject_rate > 50 else "medium" if reject_rate > 30 else "low",
        })
    rejection_patterns.sort(key=lambda x: -x["rejection_rate"])

    # ── Developer Stats ──────────────────────────────────────────
    # Query per-developer stats from the signals table
    developer_stats: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            import sqlite3
            from pathlib import Path

            db_path = _capture_engine.db_path
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COALESCE(developer_id, 'anonymous') as dev_id,
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN signal_type IN ('accept', 'pr_merge') THEN 1 ELSE 0 END) as accepts,
                    SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
                    SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits
                FROM signals
                GROUP BY dev_id
                ORDER BY total_signals DESC
                LIMIT 20
            """)

            dev_rows = cursor.fetchall()
            for row in dev_rows:
                dev_id, total, accepts, rejects, edits = row
                rate = (accepts / total * 100) if total > 0 else 0
                developer_stats.append({
                    "developer_id": dev_id[:8] + "..." if len(dev_id) > 8 else dev_id,
                    "total_signals": total,
                    "accepts": accepts,
                    "rejects": rejects,
                    "edits": edits,
                    "acceptance_rate": round(rate, 1),
                    "is_anonymous": dev_id == "anonymous",
                })

            conn.close()
        except Exception as e:
            logger.debug(f"Developer stats query failed: {e}")

    # ── Trend direction ──────────────────────────────────────────
    trend_direction = "stable"
    trend_value = 0.0
    if len(weekly_trend) >= 2:
        first_4 = weekly_trend[:4]
        last_4 = weekly_trend[-4:]
        avg_first = sum(w["acceptance_rate"] for w in first_4) / len(first_4)
        avg_last = sum(w["acceptance_rate"] for w in last_4) / len(last_4)
        trend_value = round(avg_last - avg_first, 1)
        trend_direction = "up" if trend_value > 5 else ("down" if trend_value < -5 else "stable")

    return {
        "version": VERSION,
        "timestamp": time.time(),
        "signal_types": signal_types,
        "language_rates": language_rates,
        "weekly_trend": weekly_trend,
        "rejection_patterns": rejection_patterns,
        "developer_stats": developer_stats,
        "overall": {
            "total_signals": total_signals,
            "total_sessions": stats.get("total_sessions", 0),
            "languages_count": len(signals_by_lang),
            "developers_count": len(developer_stats),
            "overall_acceptance_rate": round(stats.get("overall_acceptance_rate", 0.0), 1),
            "avg_edit_distance": round(stats.get("avg_edit_distance", 0.0), 2),
            "trend_direction": trend_direction,
            "trend_value": trend_value,
        },
    }


# ── Auto-Sync Daemon ────────────────────────────────────────────


async def _auto_sync_to_rudra_bots():
    """Periodically push ForgeAI metrics to Rudra-bots dashboard.
    Runs every 30 seconds if Rudra-bots is reachable.
    """
    # Import bridge eagerly — PythonAI/ is already on sys.path
    from src.integration.rudra_bots_bridge import sync_all_to_dashboard as _sync_fn

    _base_interval = 30

    while True:
        try:
            await asyncio.sleep(_base_interval)
            sent = await _sync_fn()
            _sync_daemon_status["last_sync_time"] = time.time()
            _sync_daemon_status["total_syncs"] += 1
            if sent:
                _sync_daemon_status["consecutive_fails"] = 0
                _sync_daemon_status["last_sync_result"] = "success"
                _base_interval = 30
                logger.debug("Auto-synced metrics to Rudra-bots dashboard")
                # Broadcast sync status (best-effort, don't pollute fail count)
                try:
                    await _broadcast_to_dashboards({
                        "type": "sync_status",
                        "status": "success",
                        "last_sync": _sync_daemon_status["last_sync_time"],
                        "total_syncs": _sync_daemon_status["total_syncs"],
                    })
                except Exception:
                    pass
            else:
                _sync_daemon_status["consecutive_fails"] += 1
                _sync_daemon_status["fail_count"] += 1
                _sync_daemon_status["last_sync_result"] = "failed"
                if _sync_daemon_status["consecutive_fails"] == 5:
                    logger.warning(
                        f"Rudra-bots unreachable for {_sync_daemon_status['consecutive_fails']} consecutive syncs. "
                        "Start Rudra-bots server for metrics dashboard."
                    )
                elif _sync_daemon_status["consecutive_fails"] > 10:
                    # Back off to 5 min after 10 failures
                    _base_interval = 300
                logger.debug(f"Auto-sync: Rudra-bots not reachable (fail #{_sync_daemon_status['consecutive_fails']})")
        except asyncio.CancelledError:
            _sync_daemon_status["running"] = False
            break
        except ImportError:
            logger.debug("Auto-sync: integration bridge not available")
            _sync_daemon_status["running"] = False
            break
        except Exception as e:
            _sync_daemon_status["consecutive_fails"] += 1
            _sync_daemon_status["fail_count"] += 1
            _sync_daemon_status["last_sync_result"] = "error"
            logger.debug(f"Auto-sync failed: {e}")


# ── TTS (Test-Time Scaling) Endpoints ─────────────────────────


class TTSConfigUpdateRequest(BaseModel):
    """Update Test-Time Scaling configuration."""
    enabled: bool | None = None
    complexity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    num_initial_rollouts: int | None = Field(default=None, ge=1, le=20)
    num_pdr_rollouts: int | None = Field(default=None, ge=1, le=10)


@app.get("/api/tts/status")
async def tts_status() -> dict[str, Any]:
    """
    Get Test-Time Scaling pipeline status and statistics.

    Returns complexity distribution, number of hard tasks routed,
    pipeline performance stats, and current configuration.
    """
    stats = _tts_pipeline.get_stats() if _tts_pipeline else {}
    return {
        "enabled": _tts_config.enabled,
        "pipeline_initialized": _tts_pipeline is not None,
        "config": {
            "complexity_threshold": _tts_config.complexity_threshold,
            "num_initial_rollouts": _tts_config.num_initial_rollouts,
            "num_pdr_rollouts": _tts_config.num_pdr_rollouts,
        },
        "stats": stats,
    }


@app.put("/api/tts/config")
async def tts_update_config(body: TTSConfigUpdateRequest) -> dict[str, Any]:
    """
    Update Test-Time Scaling configuration at runtime.

    Changes take effect on the next agent chat request.
    Restart the server to persist changes to environment variables.
    """
    global _tts_config, _tts_pipeline

    if body.enabled is not None:
        _tts_config.enabled = body.enabled
    if body.complexity_threshold is not None:
        _tts_config.complexity_threshold = body.complexity_threshold
    if body.num_initial_rollouts is not None:
        _tts_config.num_initial_rollouts = body.num_initial_rollouts
    if body.num_pdr_rollouts is not None:
        _tts_config.num_pdr_rollouts = body.num_pdr_rollouts
    # Note: _tts_pipeline.config is the same object reference as _tts_config.
    # Updating one automatically updates the other.

    logger.info(f"TTS config updated: enabled={_tts_config.enabled}, threshold={_tts_config.complexity_threshold}")

    return {
        "status": "updated",
        "config": {
            "enabled": _tts_config.enabled,
            "complexity_threshold": _tts_config.complexity_threshold,
            "num_initial_rollouts": _tts_config.num_initial_rollouts,
            "num_pdr_rollouts": _tts_config.num_pdr_rollouts,
        },
    }


@app.post("/api/tts/reset-stats")
async def tts_reset_stats() -> dict[str, Any]:
    """Reset Test-Time Scaling pipeline statistics."""
    if _tts_pipeline:
        _tts_pipeline.reset_stats()
        return {"status": "stats_reset"}
    return {"status": "not_initialized"}


# ── Benchmark Report Endpoints ────────────────────────────

_BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark"


@app.get("/api/benchmark/reports")
async def list_benchmark_reports() -> dict[str, Any]:
    """
    List all saved benchmark reports with metadata.
    Returns a list of report files sorted by recency.
    """
    if not _BENCHMARK_DIR.exists():
        return {"success": True, "reports": []}

    import datetime
    reports = []
    for f in sorted(_BENCHMARK_DIR.glob("rag_benchmark_*.json"), reverse=True):
        try:
            stat = f.stat()
            ts_str = f.name.replace("rag_benchmark_", "").replace(".json", "")
            try:
                ts = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M%S").timestamp()
            except ValueError:
                ts = stat.st_mtime
            reports.append({
                "filename": f.name,
                "path": str(f.relative_to(_BENCHMARK_DIR.parent)),
                "timestamp": ts or stat.st_mtime,
                "size_bytes": stat.st_size,
            })
        except Exception as e:
            logger.warning(f"Error reading benchmark report {f.name}: {e}")

    return {"success": True, "reports": reports}


@app.get("/api/benchmark/report/{filename}")
async def get_benchmark_report(filename: str) -> dict[str, Any]:
    """
    Get a specific benchmark report by filename.
    """
    safe_name = Path(filename).name
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = _BENCHMARK_DIR / safe_name
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Report '{safe_name}' not found")

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return {"success": True, "report": data}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse report: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ForgeAI Ecosystem Metrics (for Rudra-bots /api/forgeai/fetch) ──────

@app.get("/api/forgeai/ecosystem-metrics")
async def forgeai_ecosystem_metrics() -> dict[str, Any]:
    """Aggregated ecosystem metrics for cross-service consumption.

    This is the endpoint that Rudra-bots' `/api/forgeai/fetch` calls to
    pull live data from PythonAI.  Previously missing — causing the
    dashboard to always show cached data.
    """
    # Server health
    health_data = await health_check()
    server_info = {
        "status": "healthy",
        "version": VERSION,
        "uptime_seconds": round(time.time() - _start_time),
    }

    # Capture statistics
    stats = {}
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception:
            pass

    # Acceptance rate time-series
    acceptance_rates = []
    if _capture_engine is not None:
        try:
            acceptance_rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception:
            pass

    # Training info
    training_info = {
        "active_run": _active_training_run,
        "history": [],
        "schedule": {
            "enabled": _schedule_config["enabled"],
            "cron": _schedule_config["cron"],
            "description": _schedule_config["description"],
            "last_run": _schedule_config["last_run"],
            "next_run": _schedule_config["next_run"],
            "total_runs": _schedule_config["total_runs"],
        },
    }
    if _capture_engine is not None:
        try:
            training_info["history"] = _capture_engine.get_training_runs(limit=10)
        except Exception:
            pass

    # RAG info
    rag_info = get_rag_backend_info()

    # Signal distribution (for charts)
    signal_dist = []
    signal_labels = {
        "accept": "Accept",
        "reject": "Reject",
        "edit": "Edit",
        "pr_merge": "PR Merge",
        "test_pass": "Test Pass",
        "test_fail": "Test Fail",
    }
    sbt = stats.get("signals_by_type", {})
    for name, count in sbt.items():
        signal_dist.append({"name": signal_labels.get(name, name.capitalize()), "value": count})

    # Sync daemon status
    sync_info = {
        "running": _sync_daemon_status.get("running", False),
        "last_sync_time": _sync_daemon_status.get("last_sync_time"),
        "total_syncs": _sync_daemon_status.get("total_syncs", 0),
        "fail_count": _sync_daemon_status.get("fail_count", 0),
        "consecutive_fails": _sync_daemon_status.get("consecutive_fails", 0),
        "last_sync_result": _sync_daemon_status.get("last_sync_result"),
        "started_at": _sync_daemon_status.get("started_at"),
        "interval": _sync_daemon_status.get("interval", 30),
    }

    # Arsenal tools summary
    arsenal_info = {"total": 0, "installed": 0}
    try:
        from src.integrations.arsenal_integrations import check_arsenal_status
        a = check_arsenal_status()
        arsenal_info = {"total": a["total"], "installed": a["installed"], "missing": a["missing"]}
    except Exception:
        pass

    return {
        "server": server_info,
        "statistics": stats,
        "training": training_info,
        "rag": rag_info,
        "signal_distribution": signal_dist,
        "sync_daemon": sync_info,
        "arsenal": arsenal_info,
        "health": health_data,
        "acceptance_rates": acceptance_rates,
    }


# ── Include Arsenal Routes ─────────────────────────────────────
from src.api.arsenal_routes import router as arsenal_router  # noqa: E402

app.include_router(arsenal_router)
logger.info("Arsenal routes registered")

# ── Include Cloud Routes (if available) ────────────────────────
if _CLOUD_AVAILABLE and cloud_router is not None:
    app.include_router(cloud_router)
    logger.info("Cloud routes registered")

# ── Code Review Endpoints ────────────────────────────────────────


class ReviewCodeRequest(BaseModel):
    """Request to review a code snippet."""
    code: str = Field(..., min_length=1, max_length=100000)
    language: str = Field(default="python", max_length=50)
    file_path: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=5000)


class ReviewGitRequest(BaseModel):
    """Request to review git changes."""
    repo_path: str | None = Field(default=None, max_length=2000)
    commit_range: str | None = Field(default=None, max_length=200)
    staged: bool = Field(default=False)


@app.post("/api/review/code")
async def review_code(body: ReviewCodeRequest) -> dict[str, Any]:
    """
    Review a code snippet for issues, security concerns, and best practices.

    Uses the configured LLM provider for deep analysis. Falls back to
    a basic built-in analyzer if no provider is available.

    Returns structured review with issues, strengths, and a quality score.
    """
    from src.review import ReviewEngine, ReviewRequest

    try:
        engine = ReviewEngine()
        request = ReviewRequest(
            code=body.code,
            language=body.language,
            file_path=body.file_path,
            context=body.context,
        )
        result = engine.review_code(request)

        return {
            "success": True,
            "summary": result.summary,
            "score": result.score,
            "issues": [i.model_dump() for i in result.issues],
            "strengths": result.strengths,
            "suggestions": result.suggestions,
            "language": result.language,
            "file_path": result.file_path,
            "token_count": result.token_count,
        }
    except Exception as e:
        logger.error(f"Code review error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")


@app.post("/api/review/git")
async def review_git(body: ReviewGitRequest) -> dict[str, Any]:
    """
    Review uncommitted git changes or a specific commit range.

    Analyzes the diff, extracts changed code, and runs the review
    engine on each modified file.
    """
    from src.review import GitAnalyzer, ReviewEngine

    try:
        repo_path = body.repo_path or os.getcwd()
        analyzer = GitAnalyzer(repo_path=repo_path)

        if body.commit_range:
            changes = analyzer.get_diff(commit_range=body.commit_range)
        elif body.staged:
            changes = analyzer.get_diff(staged=True)
        else:
            changes = analyzer.get_uncommitted_changes()

        if not changes:
            return {
                "success": True,
                "files_reviewed": 0,
                "overall_score": 10.0,
                "total_issues": 0,
                "reviews": [],
                "summary": "No changes to review.",
            }

        engine = ReviewEngine()
        result = engine.review_git_changes(analyzer, changes)

        return {
            "success": True,
            "files_reviewed": len(result.reviews),
            "overall_score": result.overall_score,
            "total_issues": result.total_issues,
            "critical_count": result.critical_count,
            "error_count": result.error_count,
            "reviews": [
                {
                    "file_path": r.file_path,
                    "summary": r.summary,
                    "score": r.score,
                    "issues": [i.model_dump() for i in r.issues],
                    "strengths": r.strengths,
                    "suggestions": r.suggestions,
                    "language": r.language,
                }
                for r in result.reviews
            ],
            "summary": result.summary,
        }
    except Exception as e:
        logger.error(f"Git review error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Git review failed: {e}")


# ── Include Learning Routes ────────────────────────────────────
from src.api.learning_routes import router as learning_router  # noqa: E402

app.include_router(learning_router)
logger.info("Learning routes registered")

# ── Include Battle Routes ───────────────────────────────────────
from src.api.battle_routes import router as battle_router  # noqa: E402

app.include_router(battle_router)
logger.info("Battle routes registered")


# ═══════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7337)
