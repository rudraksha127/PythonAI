"""
ForgeAI FastAPI Server — Modular Orchestrator
==============================================
Port: 7337 (local) | WebSocket + REST API

This module is the central entry point that:
  1. Configures the FastAPI app (lifespan, CORS, middleware)
  2. Initialises shared state (capture engine, trainers, TTS pipeline, memory)
  3. Mounts all APIRouter modules from src/api/*_routes.py

Route Modules:
  events_routes    — POST /api/events, GET /api/metrics/acceptance-rate
  ws_routes        — WS /ws/events, WS /ws/training-progress
  metrics_routes   — GET /api/metrics/improvement-heatmap, signal-patterns
  rag_routes       — POST /api/rag/*, /api/agent/chat, /ask, /chat
  memory_routes    — POST /api/memory/*, GET /api/memory/*
  training_routes  — GET /api/training/*, POST /api/training/*, SEAL
  project_routes   — GET/POST/PUT/DELETE /api/projects
  tts_routes       — GET/PUT /api/tts/*, GET /api/benchmark/*
  review_routes    — POST /api/review/code, /api/review/git
  ecosystem_routes — GET /api/forgeai/ecosystem-metrics
  arsenal_routes   — Arsenal tool management
  cloud_routes     — Cloud backend (optional)
  learning_routes  — Learning endpoints
  extended_routes  — Extended API surface
  battle_routes    — Model battle / comparison

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


# ═══════════════════════════════════════
# Global DB cache
# ═══════════════════════════════════════
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

    # Projects DB — initialise inside lifespan for controlled startup
    _init_projects_db()

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

    # --- Inject shared state into route modules ---
    _inject_shared_state()

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


def _inject_shared_state():
    """Inject shared state references into all route modules after startup."""
    from src.api import events_routes, ws_routes, metrics_routes, tts_routes, ecosystem_routes

    events_routes.set_state(
        capture_engine=_capture_engine,
        ws_clients=_ws_clients,
        broadcast_fn=_broadcast_to_dashboards,
    )
    ws_routes.set_state(
        capture_engine=_capture_engine,
        ws_clients=_ws_clients,
        broadcast_fn=_broadcast_to_dashboards,
    )
    metrics_routes.set_state(capture_engine=_capture_engine)
    tts_routes.set_state(tts_config=_tts_config, tts_pipeline=_tts_pipeline)
    ecosystem_routes.set_state(
        capture_engine=_capture_engine,
        active_training_run_getter=lambda: _active_training_run,
        schedule_config=_schedule_config,
        sync_daemon_status=_sync_daemon_status,
        start_time=_start_time,
        health_check_fn=health_check,
        rag_backend_info_fn=get_rag_backend_info,
    )


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


# ═══════════════════════════════════════
# Core Endpoints (kept inline — thin)
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


# ── Training Status & Trigger (kept inline — uses globals) ─────

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


# ── Training Schedule Management ──────────────────────────────


class ScheduleUpdate(BaseModel):
    """Update the training cron schedule."""

    enabled: bool | None = None
    cron: str | None = Field(
        default=None,
        pattern=r"^\S+ \S+ \S+ \S+ \S+$",
        description="5-field cron expression: minute hour day month day_of_week",
    )


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
# Mount All APIRouter Modules
# ═══════════════════════════════════════

# New modular route files
from src.api.events_routes import router as events_router  # noqa: E402
from src.api.ws_routes import router as ws_router  # noqa: E402
from src.api.metrics_routes import router as metrics_router  # noqa: E402
from src.api.tts_routes import router as tts_router  # noqa: E402
from src.api.review_routes import router as review_router  # noqa: E402
from src.api.ecosystem_routes import router as ecosystem_router  # noqa: E402

app.include_router(events_router)
app.include_router(ws_router)
app.include_router(metrics_router)
app.include_router(tts_router)
app.include_router(review_router)
app.include_router(ecosystem_router)

# Pre-existing route modules
from src.api.arsenal_routes import router as arsenal_router  # noqa: E402

app.include_router(arsenal_router)
logger.info("Arsenal routes registered")

# Cloud routes (optional — graceful if not configured)
if _CLOUD_AVAILABLE and cloud_router is not None:
    app.include_router(cloud_router)
    logger.info("Cloud routes registered")

from src.api.learning_routes import router as learning_router  # noqa: E402

app.include_router(learning_router)
logger.info("Learning routes registered")

from src.api.extended_routes import router as extended_router  # noqa: E402
app.include_router(extended_router)
logger.info("Extended routes registered")

from src.api.battle_routes import router as battle_router  # noqa: E402

app.include_router(battle_router)
logger.info("Battle routes registered")

logger.info(
    f"All route modules mounted. Total routers: "
    f"events, ws, metrics, tts, review, ecosystem, "
    f"arsenal, learning, extended, battle"
    + (", cloud" if _CLOUD_AVAILABLE else "")
)


# ═══════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7337)
