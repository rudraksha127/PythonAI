"""
FastAPI Server for PythonAI RAG Assistant
Phase 9 Deployment & Serving

Security features:
- Rate limiting (in-memory token bucket per IP)
- Security headers middleware
- Input sanitization and length limits
- CORS with configurable origins
- Request ID tracking
"""

from __future__ import annotations

import logging
import re
import time
import uuid
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

# Note: defaultdict was removed as it was unused
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.cli import VERSION
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, get_answer, load_or_build_db
from src.utils.metrics import metrics

# ═══════════════════════════════════════
# Logging — centralized via logging_config
# ═══════════════════════════════════════
from src.utils.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("pythonai.api")

# ═══════════════════════════════════════
# Rate Limiter (in-memory token bucket)
# ═══════════════════════════════════════

class _TokenBucket:
    """Simple per-IP token bucket rate limiter with automatic cleanup."""

    def __init__(self, capacity: int = 30, refill_per_sec: float = 1.0) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, last_refill)
        self._last_cleanup: float = time.time()

    def _maybe_cleanup(self) -> None:
        """Remove stale entries every 60s to prevent memory leaks."""
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
    """Strip control characters and enforce length."""
    text = text.strip()
    # Remove null bytes and most control characters (keep newlines/tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_len]


# ═══════════════════════════════════════
# App
# ═══════════════════════════════════════

app = FastAPI(
    title="PythonAI API",
    description="API for the PythonAI RAG Assistant",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — configurable origins via env or default to localhost
# CORS origins configurable via env (comma-separated)
_cors_origins = os.environ.get(
    "PYTHONAI_CORS_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501,http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Security Headers Middleware ──
@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Response:  # type: ignore[no-untyped-def]
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(client_ip):
        retry = _rate_limiter.retry_after(client_ip)
        logger.warning(f"Rate limited: {client_ip} — retry in {retry:.1f}s")
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please slow down.", "retry_after": round(retry, 1)},
            headers={"Retry-After": str(int(retry) + 1)},
        )

    # Process request
    request_id = uuid.uuid4().hex[:12]
    start = time.time()
    response: Response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000

    # Add security headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Server"] = "PythonAI"

    # Log request and record metrics
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"from={client_ip} status={response.status_code} time={elapsed_ms:.0f}ms"
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


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH,
                          description="The question to ask")
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("question")  # type: ignore[misc]
    @classmethod
    def _clean_question(cls, v: str) -> str:
        return _sanitize_text(v, _MAX_QUESTION_LENGTH)

    @field_validator("model")  # type: ignore[misc]
    @classmethod
    def _clean_model(cls, v: str) -> str:
        return _sanitize_text(v, 100)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_LENGTH)
    model: str = Field(default="", max_length=100)
    query_expansion: bool = False
    mmr: bool = False
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("history")  # type: ignore[misc]
    @classmethod
    def _trim_history(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trimmed = v[-_MAX_HISTORY_LENGTH:]
        for msg in trimmed:
            if isinstance(msg.get("content"), str):
                msg["content"] = _sanitize_text(msg["content"], _MAX_HISTORY_MSG_LENGTH)
        return trimmed

    @field_validator("question")  # type: ignore[misc]
    @classmethod
    def _clean_question(cls, v: str) -> str:
        return _sanitize_text(v, _MAX_QUESTION_LENGTH)

    @field_validator("model")  # type: ignore[misc]
    @classmethod
    def _clean_model(cls, v: str) -> str:
        return _sanitize_text(v, 100)


# ═══════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint for load balancers and Docker."""
    return {
        "status": "ok",
        "version": VERSION,
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - _start_time),
    }


@app.get("/stats")
async def get_stats() -> dict[str, Any]:
    try:
        coll, _, _, _, cfile = get_db()
        return {
            "status": "ok",
            "chunks": coll.count(),
            "db_path": str(cfile),
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    """Performance metrics endpoint for monitoring."""
    return metrics.get_summary()


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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error answering chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
