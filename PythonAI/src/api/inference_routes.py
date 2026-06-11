import time
import requests
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.inference")

router = APIRouter(prefix="/inference", tags=["Inference & Autocomplete"])

class AutocompleteRequest(BaseModel):
    prefix: str = Field(..., description="The code snippet immediately before the cursor")
    suffix: str = Field(..., description="The code snippet immediately after the cursor")
    language: str = Field(default="python", description="Language of the file")
    filepath: Optional[str] = Field(default=None, description="Path of the file being edited")
    max_tokens: int = Field(default=128, description="Maximum tokens to generate")
    temperature: float = Field(default=0.1, description="Temperature for generation (low for code)")

def query_ollama_fim(prefix: str, suffix: str, max_tokens: int, temperature: float) -> str:
    """
    Calls the local Ollama Qwen 2.5 Coder instance using its Fill-In-the-Middle tokens.
    """
    model_name = "qwen2.5-coder:7b"  # Default fallback, can be configured
    
    # Qwen FIM prompt format
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    
    try:
        resp = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "stop": ["<|file_separator|>", "<|endoftext|>"]
                }
            },
            timeout=5.0
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except requests.exceptions.RequestException as e:
        logger.error(f"FIM Ollama Request Failed: {e}")
        # Return empty string instead of crashing, so the editor just shows no ghost text
        return ""

@router.post("/autocomplete")
def autocomplete(req: AutocompleteRequest) -> Dict[str, Any]:
    """
    Generates real-time Fill-in-the-Middle (FIM) ghost text for VS Code.
    """
    start_time = time.time()
    
    # Simple limit on context window to keep it super fast
    max_prefix_len = 2000
    max_suffix_len = 1000
    
    prefix = req.prefix[-max_prefix_len:] if len(req.prefix) > max_prefix_len else req.prefix
    suffix = req.suffix[:max_suffix_len] if len(req.suffix) > max_suffix_len else req.suffix

    # Fetch completion
    completion = query_ollama_fim(
        prefix=prefix, 
        suffix=suffix, 
        max_tokens=req.max_tokens, 
        temperature=req.temperature
    )
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(f"[Autocomplete] Generated {len(completion)} chars in {elapsed_ms}ms")
    
    return {
        "status": "success",
        "completion": completion,
        "elapsed_ms": elapsed_ms
    }
