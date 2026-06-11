"""
forge_step7_deploy.py — PHASE 7: DEPLOYMENT AS API
=====================================================
Deploys the trained model as a FastAPI server with OpenAI-compatible endpoint.
Run: uvicorn forge_step7_deploy:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
from rich.console import Console

from forge_config import ForgeConfig

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

try:
    from peft import PeftModel

    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False

console = Console()

app = FastAPI(
    title="FORGE-OMEGA Inference API",
    description="Trained on your custom dataset. OpenAI-compatible endpoint.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── GLOBAL MODEL STATE ──────────────────────────────────────────────────────
MODEL_STATE = {
    "model": None,
    "tokenizer": None,
    "device": None,
}


def load_model():
    """Lazy-load the trained model on first request."""
    if MODEL_STATE["model"] is not None:
        return

    cfg = ForgeConfig.load()
    model_dir = Path(cfg.final_model_dir)

    if not model_dir.exists():
        raise RuntimeError(f"Model directory not found: {model_dir}")

    logger.info(f"Loading model from {model_dir}...")

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Try loading with PEFT adapter
    if HAS_PEFT:
        try:
            base = AutoModelForCausalLM.from_pretrained(
                cfg.base_model,
                device_map="auto",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            model = PeftModel.from_pretrained(base, str(model_dir))
            logger.info("Loaded as PEFT model with adapter")
        except Exception:
            model = AutoModelForCausalLM.from_pretrained(
                str(model_dir),
                device_map="auto",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            logger.info("Loaded as standalone model")
    else:
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            device_map="auto",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )

    model.eval()
    MODEL_STATE["model"] = model
    MODEL_STATE["tokenizer"] = tokenizer
    MODEL_STATE["device"] = model.device
    logger.success("Model ready!")


# ── PYDANTIC MODELS ─────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "forge-omega-v1"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    system: str = ""


class GenerateResponse(BaseModel):
    text: str
    tokens_generated: int
    latency_ms: float
    model: str


# ── EVENTS ──────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    try:
        load_model()
    except Exception as e:
        logger.error(f"Failed to load model on startup: {e}")
        logger.warning("Server started but inference endpoints will fail.")


# ── ENDPOINTS ───────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "status": "running",
        "model": MODEL_STATE["model"] is not None,
        "endpoints": ["/health", "/generate", "/v1/chat/completions"],
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy" if MODEL_STATE["model"] else "degraded",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "model_loaded": MODEL_STATE["model"] is not None,
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Simple text generation endpoint."""
    if MODEL_STATE["model"] is None:
        raise HTTPException(503, "Model not loaded")

    full_prompt = (
        f"{req.system}\n\nUser: {req.prompt}\n\nAssistant:" if req.system else f"User: {req.prompt}\n\nAssistant:"
    )

    start = time.time()
    inputs = MODEL_STATE["tokenizer"](full_prompt, return_tensors="pt", truncation=True, max_length=2048).to(
        MODEL_STATE["device"]
    )

    with torch.no_grad():
        outputs = MODEL_STATE["model"].generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            do_sample=True,
            pad_token_id=MODEL_STATE["tokenizer"].pad_token_id,
        )

    generated = outputs[0][inputs["input_ids"].shape[1] :]
    text = MODEL_STATE["tokenizer"].decode(generated, skip_special_tokens=True).strip()
    latency = (time.time() - start) * 1000

    return GenerateResponse(
        text=text,
        tokens_generated=len(generated),
        latency_ms=round(latency),
        model=MODEL_STATE.get("model_name", "forge-omega-v1"),
    )


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint."""
    if MODEL_STATE["model"] is None:
        raise HTTPException(503, "Model not loaded")

    if req.stream:
        raise HTTPException(501, "Streaming not yet implemented")

    try:
        tokenizer = MODEL_STATE["tokenizer"]
        model = MODEL_STATE["model"]
        device = MODEL_STATE["device"]

        # Convert Pydantic models to dicts
        messages = [{"role": msg.role, "content": msg.content} for msg in req.messages]

        # Format input
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(input_text, return_tensors="pt").to(device)
        else:
            parts = [f"{m['role'].capitalize()}: {m['content']}" for m in messages]
            input_text = "\n".join(parts) + "\nAssistant:"
            inputs = tokenizer(input_text, return_tensors="pt").to(device)

        start = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=req.max_tokens or 512,
                temperature=req.temperature or 0.7,
                do_sample=(req.temperature or 0.7) > 0,
                pad_token_id=tokenizer.eos_token_id,
            )

        output_ids = outputs[0][inputs["input_ids"].shape[-1] :]
        response_text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        latency = (time.time() - start) * 1000

        return {
            "id": "chatcmpl-forge-omega",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(inputs["input_ids"][0]),
                "completion_tokens": len(output_ids),
                "total_tokens": len(inputs["input_ids"][0]) + len(output_ids),
            },
        }

    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(500, detail=str(e))


def run_server():
    """Start the API server."""
    import uvicorn

    console.print("\n[bold cyan]═══ PHASE 7: API DEPLOYMENT ═══[/bold cyan]")
    console.print("[green]Starting FastAPI server on http://localhost:8000[/green]")
    console.print("[green]API docs: http://localhost:8000/docs[/green]")
    uvicorn.run("forge_step7_deploy:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
