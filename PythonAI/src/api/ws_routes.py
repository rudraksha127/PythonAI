"""
ForgeAI WebSocket Routes
=========================
Handles /ws/events, /ws/training-progress, /ws/chat, and /ws/status WebSocket endpoints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from src.cli import VERSION
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, get_answer, load_or_build_db

logger = logging.getLogger("forgeai.api.ws")
router = APIRouter(tags=["WebSocket"])

# ── Shared state references (injected at mount time) ────────────
_capture_engine = None
_ws_clients: list = []
_broadcast_fn = None


def set_state(*, capture_engine, ws_clients, broadcast_fn):
    """Inject shared state from the main server module."""
    global _capture_engine, _ws_clients, _broadcast_fn
    _capture_engine = capture_engine
    _ws_clients = ws_clients
    _broadcast_fn = broadcast_fn


async def _broadcast_to_dashboards(message: dict[str, Any]):
    """Broadcast to dashboard clients via the injected function."""
    if _broadcast_fn is not None:
        await _broadcast_fn(message)


class _EventPayload(BaseModel):
    """Event from VS Code extension (local copy for WS deserialization)."""

    event_type: str
    session_id: str = ""
    project_id: str = ""
    file_path: str = ""
    line_number: int = 0
    language: str = ""
    framework: str | None = None
    project_type: str = "general"
    suggestion: str = ""
    suggestion_metadata: dict = Field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""
    final_code: str | None = None
    edit_distance: float = 0.0
    developer_id: str | None = None


@router.websocket("/ws/events")
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
                payload = _EventPayload(**payload_dict)

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


@router.websocket("/ws/training-progress")
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


@router.websocket("/ws/chat")
async def websocket_chat_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional agent chat token streaming.
    Clients send prompt payload, server streams individual tokens back in real time.
    """
    await websocket.accept()
    logger.info("Client connected to WebSocket chat stream")

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
                question = msg.get("question", "").strip()
                if not question:
                    await websocket.send_json({"error": "Empty question provided"})
                    continue

                requested_model = msg.get("model", "")
                available = list_ollama_models()
                selected_model = resolve_model(requested_model or DEFAULT_MODEL, available=available)

                history = msg.get("history", [])
                query_expansion = msg.get("query_expansion", False)
                mmr = msg.get("mmr", False)
                mmr_lambda = msg.get("mmr_lambda", 0.7)

                await websocket.send_json({"type": "start", "model": selected_model})

                db = load_or_build_db(backend="chroma")
                coll, embedder, bm25, corpus, _ = db

                answer, docs = get_answer(
                    question,
                    coll,
                    embedder,
                    history,
                    bm25=bm25,
                    corpus_texts=corpus,
                    use_query_expansion=query_expansion,
                    use_mmr=mmr,
                    mmr_lambda=mmr_lambda,
                    no_exec=True,
                    model=selected_model,
                )

                for char in answer:
                    await websocket.send_json({"type": "token", "token": char})
                    await asyncio.sleep(0.005)

                sources = [{"title": d.get("title", ""), "version": d.get("version", "")} for d in docs]
                await websocket.send_json({"type": "done", "sources": sources})

            except Exception as e:
                logger.error(f"WebSocket chat error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "error": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket chat client disconnected")


@router.websocket("/ws/status")
async def websocket_status_stream(websocket: WebSocket):
    """
    WebSocket for real-time status and health streaming to monitoring tools/dashboards.
    """
    await websocket.accept()
    logger.info("Client connected to status stream")

    try:
        while True:
            stats = {}
            if _capture_engine is not None:
                try:
                    stats = _capture_engine.get_statistics()
                except Exception:
                    pass

            await websocket.send_json({
                "type": "status_update",
                "version": VERSION,
                "timestamp": time.time(),
                "statistics": stats,
            })
            await asyncio.sleep(5)  # Push status every 5s
    except WebSocketDisconnect:
        logger.info("Status stream client disconnected")
