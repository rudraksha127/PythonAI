"""
ForgeAI RAG & Agent API Routes
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.api.models import (
    AskRequest,
    ChatRequest,
    DocumentInsertRequest,
    IndexRequest,
    IngestRequest,
    LightRAGHealthRequest,
    RAGSearchRequest,
)
from src.rag.models import list_ollama_models, resolve_model
from src.rag.rag_engine import DEFAULT_MODEL, RAG_BACKEND, get_answer, get_lightrag, load_or_build_db
from src.training.time_scaling import TTSConfig, TestTimeScalingPipeline, create_ollama_llm_call

logger = logging.getLogger("forgeai.api.rag")
router = APIRouter(tags=["RAG & Agent"])

_db_cache: Any = None
_lightrag: Any = None
_tts_pipeline: Any = None
_tts_config = TTSConfig()


def set_tts_pipeline(pipeline: Any, config: Any) -> None:
    global _tts_pipeline, _tts_config
    _tts_pipeline = pipeline
    _tts_config = config


def get_db(backend: str | None = None) -> Any:
    global _db_cache, _lightrag
    active_backend = backend or RAG_BACKEND

    if active_backend == "lightrag":
        if _lightrag is None:
            from src.rag.lightrag_wrapper import create_lightrag_backend

            _lightrag = create_lightrag_backend()
        return _lightrag

    if _db_cache is None:
        _db_cache = load_or_build_db(backend="chroma")
    return _db_cache


@router.post("/api/rag/search")
async def rag_search(request: RAGSearchRequest) -> dict[str, Any]:
    """RAG search — supports both ChromaDB and LightRAG backends."""
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

        db = get_db(backend="chroma")
        coll, embedder, bm25, corpus, _ = db
        available = list_ollama_models()
        selected_model = resolve_model(DEFAULT_MODEL, available=available)

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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rag/index")
async def rag_index(request: IndexRequest) -> dict[str, Any]:
    """Index or re-index a project codebase using cAST chunking."""
    job_id = str(uuid.uuid4())
    logger.info(f"Indexing job {job_id} started for {request.repo_path}")
    return {
        "job_id": job_id,
        "status": "indexing",
        "project_id": request.project_id,
        "repo_path": request.repo_path,
    }


@router.get("/api/rag/stats")
async def rag_stats() -> dict[str, Any]:
    """Return RAG system statistics."""
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


@router.get("/api/rag/backend")
async def rag_backend_info() -> dict[str, Any]:
    """Return information about the active RAG backend."""
    return {
        "backend": RAG_BACKEND,
        "lightrag_available": _lightrag is not None and getattr(_lightrag, "is_available", lambda: False)(),
        "lightrag_stats": _lightrag.get_stats() if _lightrag and hasattr(_lightrag, "get_stats") else None,
        "chroma_available": _db_cache is not None,
    }


@router.post("/api/rag/documents")
async def rag_insert_documents(body: DocumentInsertRequest) -> dict[str, Any]:
    """Insert text documents into LightRAG."""
    if RAG_BACKEND != "lightrag":
        raise HTTPException(status_code=400, detail="LightRAG backend not active. Set FORGEAI_RAG_BACKEND=lightrag")

    lr = get_db(backend="lightrag")
    if lr is None or not lr.is_available():
        raise HTTPException(status_code=503, detail="LightRAG backend not available")

    result = lr.insert_texts(body.texts)
    return {"success": True, **result}


@router.post("/api/rag/ingest")
async def rag_ingest_directory(body: IngestRequest) -> dict[str, Any]:
    """Ingest files from a directory into LightRAG."""
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


@router.get("/api/rag/cache")
async def rag_cache_stats() -> dict[str, Any]:
    """Return LightRAG query cache statistics."""
    if RAG_BACKEND != "lightrag":
        return {"backend": "chroma", "cache_active": False}

    lr = get_db(backend="lightrag")
    if lr is None:
        return {"backend": "lightrag", "cache_active": False}

    stats = lr.cache_stats()
    return {"backend": "lightrag", "cache_active": True, **stats}


@router.post("/api/rag/cache/clear")
async def rag_cache_clear() -> dict[str, Any]:
    """Clear the LightRAG query cache."""
    if RAG_BACKEND != "lightrag":
        raise HTTPException(status_code=400, detail="LightRAG backend not active")

    lr = get_db(backend="lightrag")
    if lr is None:
        return {"cleared": 0}

    cleared = lr.clear_cache()
    return {"cleared": cleared, "message": f"Cache cleared ({cleared} entries)"}


@router.post("/api/rag/health")
async def rag_health_check(body: LightRAGHealthRequest | None = None) -> dict[str, Any]:
    """Run a comprehensive LightRAG health check."""
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


@router.post("/api/agent/chat")
async def agent_chat(request: ChatRequest) -> StreamingResponse:
    """Agent chat with streaming response (SSE)."""

    async def generate() -> AsyncGenerator[str, None]:
        try:
            history = request.history[-10:] if request.history else []
            selected_model = resolve_model(request.model or DEFAULT_MODEL, available=list_ollama_models())

            if _tts_pipeline is not None and _tts_config.enabled:
                llm_call = create_ollama_llm_call(model=selected_model)
                _tts_pipeline.set_llm_call(llm_call)

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

                yield f"data: {json.dumps({'tts_route': route, 'complexity_score': complexity_score})}\n\n"

                for char in answer:
                    yield f"data: {json.dumps({'token': char})}\n\n"
                    await asyncio.sleep(0.005)

                yield f"data: {json.dumps({'done': True, 'tts': {'route': route, 'complexity_score': complexity_score, 'rtv': rtv_applied, 'pdr': pdr_applied, 'rollouts': num_rollouts, 'elapsed_ms': elapsed_ms}})}\n\n"
            else:
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


@router.post("/ask")
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


@router.post("/chat")
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
