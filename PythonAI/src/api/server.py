"""
FastAPI Server for PythonAI RAG Assistant
Phase 9 Deployment & Serving
"""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from src.rag.rag_engine import load_or_build_db, get_answer, DEFAULT_MODEL
from src.rag.models import resolve_model, list_ollama_models
from src.cli import VERSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(
    title="PythonAI API",
    description="API for the PythonAI RAG Assistant",
    version=VERSION,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global DB cache
_db_cache = None

def get_db():
    global _db_cache
    if _db_cache is None:
        logger.info("Loading RAG Database...")
        _db_cache = load_or_build_db()
    return _db_cache


class AskRequest(BaseModel):
    question: str
    model: Optional[str] = ""
    query_expansion: Optional[bool] = False
    mmr: Optional[bool] = False
    mmr_lambda: Optional[float] = 0.7


class ChatRequest(AskRequest):
    history: List[Dict[str, Any]] = []


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": VERSION}


@app.get("/stats")
async def get_stats():
    try:
        coll, _, _, _, cfile = get_db()
        return {
            "status": "ok",
            "chunks": coll.count(),
            "db_path": str(cfile),
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask")
async def ask_question(request: AskRequest):
    if not request.question:
        raise HTTPException(status_code=400, detail="Missing 'question' field")
    
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
        logger.error(f"Error answering question: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.question:
        raise HTTPException(status_code=400, detail="Missing 'question' field")
    
    try:
        coll, embedder, bm25, corpus, _ = get_db()
        available = list_ollama_models()
        selected_model = resolve_model(request.model or DEFAULT_MODEL, available=available)
        
        # Keep only the last 10 messages for context
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
        logger.error(f"Error answering chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
