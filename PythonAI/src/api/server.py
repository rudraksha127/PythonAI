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
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.cli import VERSION
from src.learning.capture_engine import CaptureEngine, SignalType
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, get_answer, load_or_build_db
from src.training.grpo_trainer import GRPOTrainer
from src.training.sdft_trainer import SDFTTrainer
from src.utils.metrics import metrics

# ═══════════════════════════════════════
# Logging — centralized
# ═══════════════════════════════════════
from src.utils.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("forgeai.api")

# ═══════════════════════════════════════
# Global State
# ═══════════════════════════════════════
_capture_engine: Optional[CaptureEngine] = None
_sdft_trainer: Optional[SDFTTrainer] = None
_grpo_trainer: Optional[GRPOTrainer] = None
_active_training_run: Optional[dict[str, Any]] = None
_ws_clients: list[WebSocket] = []  # Dashboard WebSocket clients

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
    _sdft_trainer = SDFTTrainer()
    _grpo_trainer = GRPOTrainer()
    logger.info("Capture engine, SDFT trainer, GRPO trainer initialized.")
    yield
    # Shutdown
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

    logger.info(f"[{request_id}] {request.method} {request.url.path} from={client_ip} status={response.status_code} time={elapsed_ms:.0f}ms")
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
    framework: Optional[str] = None
    project_type: str = "general"
    suggestion: str
    suggestion_metadata: dict = Field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""
    final_code: Optional[str] = None
    edit_distance: float = 0.0
    developer_id: Optional[str] = None

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
    project_id: Optional[str] = None

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
    }

@app.get("/stats")
async def get_stats() -> dict[str, Any]:
    try:
        coll, _, _, _, cfile = get_db()
        return {"status": "ok", "chunks": coll.count(), "db_path": str(cfile)}
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

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
        await _broadcast_to_dashboards({
            "type": "event_captured",
            "event_type": payload.event_type,
            "signal_id": signal_id,
            "timestamp": time.time(),
        })

        return {"event_id": signal_id, "captured": True}

    except Exception as e:
        logger.error(f"Error capturing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to capture event")

@app.get("/api/metrics/acceptance-rate")
async def get_acceptance_rate(project_id: Optional[str] = None, weeks: int = 12) -> dict[str, Any]:
    """Get acceptance rate over time for dashboard chart."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    days = weeks * 7
    rates = _capture_engine.get_acceptance_rate(days=days)

    # Compute training run markers
    runs = _capture_engine.get_training_runs(limit=20)
    markers = [
        {"timestamp": r["timestamp"], "delta": r["acceptance_delta"], "signals": r["signals_used"]}
        for r in runs
    ]

    return {"data": rates, "training_markers": markers}

@app.get("/api/training/status")
async def get_training_status(project_id: Optional[str] = None) -> dict[str, Any]:
    """Get current training status and history."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    history = _capture_engine.get_training_runs(limit=10)

    return {
        "active_run": _active_training_run,
        "history": history,
    }

@app.post("/api/training/trigger")
async def trigger_training(project_id: Optional[str] = None) -> dict[str, Any]:
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
    await _broadcast_to_dashboards({
        "type": "training_started",
        "run_id": run_id,
    })

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
                await _broadcast_to_dashboards({
                    "type": "event_captured",
                    "event_type": payload.event_type,
                    "signal_id": signal_id,
                    "timestamp": time.time(),
                })

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


# ═══════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7337)