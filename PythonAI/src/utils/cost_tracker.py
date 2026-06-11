"""
Tracks API costs across multiple LLM providers.
Estimates token counts using tiktoken (for OpenAI) or character length heuristics.
"""
import json
import os
from datetime import datetime, timezone
from loguru import logger

try:
    import tiktoken
except ImportError:
    tiktoken = None

# Rough cost estimates per 1k tokens (in USD)
# Note: prices change frequently, these are heuristics
PRICING = {
    "openai": {"in": 0.005, "out": 0.015}, # e.g. gpt-4o
    "anthropic": {"in": 0.003, "out": 0.015}, # e.g. claude 3.5 sonnet
    "google": {"in": 0.0035, "out": 0.0105}, # e.g. gemini 1.5 pro
    "nvidia": {"in": 0.001, "out": 0.002},
    "grok": {"in": 0.005, "out": 0.015},
    "qwen": {"in": 0.0, "out": 0.0} # Local is free
}

class CostTracker:
    def __init__(self, log_path: str = "python_brain_godmode/cost_log.json"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.encoder = None
        if tiktoken:
            try:
                self.encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass

    def _estimate_tokens(self, text: str) -> int:
        if self.encoder:
            return len(self.encoder.encode(text))
        # Fallback heuristic: ~4 chars per token
        return len(text) // 4

    def log_call(self, provider: str, prompt: str, response: str):
        in_tokens = self._estimate_tokens(prompt)
        out_tokens = self._estimate_tokens(response)
        
        rates = PRICING.get(provider, {"in": 0.0, "out": 0.0})
        cost = (in_tokens / 1000.0) * rates["in"] + (out_tokens / 1000.0) * rates["out"]
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "cost_usd": cost
        }
        
        # Append to log
        log_data = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r") as f:
                    log_data = json.load(f)
            except Exception:
                pass
                
        log_data.append(record)
        
        with open(self.log_path, "w") as f:
            json.dump(log_data, f, indent=2)
            
        if cost > 0.01:
            logger.info(f"💰 API Cost ({provider}): ${cost:.4f}")
            
# Global instance
tracker = CostTracker()
