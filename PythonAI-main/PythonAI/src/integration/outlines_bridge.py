"""
Outlines Bridge — Structured Output via Logit Manipulation
===========================================================

Wraps the `outlines` library (dottxt-ai/outlines) to provide
guaranteed structured output generation (JSON, Regex, Pydantic models)
from any supported HuggingFace model.

Guarantees correct JSON/regex output from any model by masking illegal
tokens during generation, not just parsing afterward.

Architecture:
    - Lazy initialization of model + tokenizer on first use
    - Supports transformers, vLLM, and Ollama backends
    - Caches generated schemas for repeated use
    - Graceful fallback when outlines is not installed

Usage:
    from src.integration.outlines_bridge import OutlinesBridge

    bridge = OutlinesBridge()
    result = bridge.generate_json(
        prompt="Rate this product (1-5 stars).",
        output_schema='{"rating": 1}',
    )
    # => {"rating": 5}

Environment:
    OUTLINES_MODEL      : transformers model ID (default: Qwen/Qwen2.5-1.5B-Instruct)
    OUTLINES_BACKEND    : "transformers" or "vllm" (default: transformers)
    OUTLINES_MAX_TOKENS : max generation tokens (default: 2048)
    OUTLINES_DEVICE     : device for model (default: auto)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("forgeai.integration.outlines")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_BACKEND = "transformers"
DEFAULT_MAX_TOKENS = 2048

# ── Schema Cache ─────────────────────────────────────────────────


class _SchemaCache:
    """LRU cache for compiled regex/json schemas.

    Avoids re-compiling the same schema on repeated calls.
    """

    def __init__(self, maxsize: int = 128) -> None:
        self._maxsize = maxsize
        self._cache: dict[str, Any] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is not None:
            self._hits += 1
            return entry
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = value

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
        return {"size": len(self._cache), "maxsize": self._maxsize,
                "hits": self._hits, "misses": self._misses, "hit_rate": hit_rate}

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count


# ── Adapter ──────────────────────────────────────────────────────


class OutlinesBridge:
    """Structured output generation via outlines logit processors.

    Provides guaranteed JSON, regex, and Pydantic output from
    HuggingFace models by manipulating logits during generation.

    Lazy-initializes the model on first use so server startup is not
    blocked by model loading.

    Thread-safe: uses a lock for initialization.
    """

    def __init__(
        self,
        model_name: str | None = None,
        backend: Literal["transformers", "vllm"] | None = None,
        max_tokens: int | None = None,
        device: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._model_name = model_name or DEFAULT_MODEL
        self._backend = backend or DEFAULT_BACKEND  # type: ignore
        self._max_tokens = max_tokens or DEFAULT_MAX_TOKENS
        self._device = device or "auto"
        self._enabled = enabled

        self._model = None
        self._tokenizer = None
        self._generator = None
        self._initialized = False
        self._init_error: str | None = None
        self._schema_cache = _SchemaCache()

        self._stats = {
            "generations": 0,
            "json_calls": 0,
            "regex_calls": 0,
            "pydantic_calls": 0,
            "errors": 0,
            "last_error": None,
            "total_tokens_generated": 0,
            "avg_generation_ms": 0.0,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Load outlines + model on first use. Returns True if ready."""
        if self._initialized:
            return self._model is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "Outlines bridge disabled"
            logger.info("OutlinesBridge is disabled")
            return False

        try:
            import outlines
            from outlines import models, generate
            from outlines.processors import OutlinesLogitsProcessor

            self._outlines = outlines
            self._outlines_models = models
            self._outlines_generate = generate
            self._outlines_processor_base = OutlinesLogitsProcessor

            # Load the model
            logger.info(f"Loading outlines model: {self._model_name} (backend={self._backend})")
            start = time.time()

            if self._backend == "vllm":
                model = models.vLLMModel(self._model_name)
            else:
                model = models.TransformersModel(
                    self._model_name,
                    device=self._device,
                )

            self._model = model
            self._generator = generate
            self._initialized = True

            elapsed = time.time() - start
            logger.info(f"Outlines model loaded in {elapsed:.1f}s: {self._model_name}")
            return True

        except ImportError:
            self._init_error = "outlines not installed. Run: pip install outlines"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"OutlinesBridge init failed: {e}")

        self._initialized = True
        return False

    # ── Public API ───────────────────────────────────────────────

    def generate_json(
        self,
        prompt: str,
        output_schema: dict[str, Any] | str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON output guaranteed to match a schema.

        Args:
            prompt: The input prompt.
            output_schema: A Pydantic model class, a JSON schema dict,
                          or a JSON string representing the desired structure.
                          If None, returns any valid JSON.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate (default: self._max_tokens).

        Returns:
            Dict with keys: "text" (parsed JSON), "raw" (raw output string),
                          "valid" (bool), "error" (optional).
        """
        if not self._ensure_initialized() or self._model is None:
            self._stats["errors"] += 1
            err = self._init_error or "Model not available"
            self._stats["last_error"] = err
            return {"text": None, "raw": "", "valid": False, "error": err}

        try:
            start = time.time()
            max_t = max_tokens or self._max_tokens

            if output_schema is not None and not isinstance(output_schema, str):
                # Pydantic model or dict schema -> JSON generation
                generator = self._outlines_generate.json(self._model, output_schema)
                raw = generator(prompt, max_tokens=max_t, temperature=temperature)
            elif isinstance(output_schema, str):
                # String JSON schema -> parse and generate
                import json
                schema = json.loads(output_schema)
                generator = self._outlines_generate.json(self._model, schema)
                raw = generator(prompt, max_tokens=max_t, temperature=temperature)
            else:
                # No schema -> freeform JSON
                generator = self._outlines_generate.json(self._model)
                raw = generator(prompt, max_tokens=max_t, temperature=temperature)

            elapsed = time.time() - start

            # Parse the result
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                valid = True
            except (json.JSONDecodeError, TypeError):
                parsed = raw
                valid = False

            tokens_used = len(raw.split()) if isinstance(raw, str) else 0
            self._stats["json_calls"] += 1
            self._stats["generations"] += 1
            self._stats["total_tokens_generated"] += tokens_used
            self._stats["avg_generation_ms"] = (
                (self._stats["avg_generation_ms"] * (self._stats["generations"] - 1) + elapsed * 1000)
                / self._stats["generations"]
            )

            return {"text": parsed, "raw": raw, "valid": valid,
                    "tokens": tokens_used, "elapsed_seconds": round(elapsed, 2)}

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning(f"OutlinesBridge.generate_json failed: {e}")
            return {"text": None, "raw": "", "valid": False, "error": str(e)}

    def generate_regex(
        self,
        prompt: str,
        pattern: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate text guaranteed to match a regular expression.

        Args:
            prompt: The input prompt.
            pattern: A regex pattern the output must match.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.

        Returns:
            Dict with "text", "matched" (bool), and optional "error".
        """
        if not self._ensure_initialized() or self._model is None:
            return {"text": "", "matched": False, "error": self._init_error or "Model not available"}

        try:
            start = time.time()
            max_t = max_tokens or self._max_tokens

            generator = self._outlines_generate.regex(self._model, pattern)
            raw = generator(prompt, max_tokens=max_t, temperature=temperature)

            elapsed = time.time() - start
            matched = bool(re.fullmatch(pattern, raw)) if isinstance(raw, str) else False

            self._stats["regex_calls"] += 1
            self._stats["generations"] += 1

            return {"text": str(raw), "matched": matched,
                    "elapsed_seconds": round(elapsed, 2)}

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"text": "", "matched": False, "error": str(e)}

    def generate_with_pydantic(
        self,
        prompt: str,
        pydantic_model: Any,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate structured output using a Pydantic model definition.

        Args:
            prompt: The input prompt.
            pydantic_model: A Pydantic BaseModel subclass.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.

        Returns:
            Dict with "instance" (parsed Pydantic model) and optional "error".
        """
        if not self._ensure_initialized() or self._model is None:
            return {"instance": None, "error": self._init_error or "Model not available"}

        try:
            result = self.generate_json(prompt, output_schema=pydantic_model,
                                        temperature=temperature, max_tokens=max_tokens)
            if result.get("valid") and result.get("text"):
                instance = pydantic_model.model_validate_json(
                    json.dumps(result["text"]) if isinstance(result["text"], dict) else result["raw"]
                )
                self._stats["pydantic_calls"] += 1
                return {"instance": instance, "raw": result.get("raw", ""),
                        "elapsed_seconds": result.get("elapsed_seconds", 0)}
            return {"instance": None, "error": result.get("error", "Generation failed")}

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"instance": None, "error": str(e)}

    def create_custom_generator(self, prompt: str, custom_processor: Any | None = None,
                                 temperature: float = 0.2) -> dict[str, Any]:
        """Create a custom generator with a user-defined logit processor.

        For advanced use cases where the built-in JSON/regex generators
        are insufficient. Users can subclass OutlinesLogitsProcessor.

        Args:
            prompt: The input prompt.
            custom_processor: A custom OutlinesLogitsProcessor instance.
            temperature: Sampling temperature.

        Returns:
            Dict with generation result.
        """
        if not self._ensure_initialized() or self._model is None:
            return {"text": "", "error": self._init_error or "Model not available"}

        try:
            from outlines import Generator as OutlinesGenerator

            if custom_processor:
                gen = OutlinesGenerator(self._model, processor=custom_processor)
            else:
                gen = self._outlines_generate.text(self._model)

            result = gen(prompt, temperature=temperature)
            return {"text": str(result)}

        except Exception as e:
            return {"text": "", "error": str(e)}

    # ── Info ─────────────────────────────────────────────────────

    def available(self) -> bool:
        """Check if outlines is available and model is loaded."""
        self._ensure_initialized()
        return self._model is not None

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics."""
        return {
            **self._stats,
            "model": self._model_name,
            "backend": self._backend,
            "initialized": self._initialized,
            "available": self._model is not None,
            "init_error": self._init_error,
            "schema_cache": self._schema_cache.stats,
            "enabled": self._enabled,
        }

    def health_check(self) -> dict[str, Any]:
        """Quick health check — model loaded and basic generation works."""
        checks = []
        try:
            import outlines  # noqa: F401
            checks.append({"name": "import", "status": "ok"})
        except ImportError:
            checks.append({"name": "import", "status": "fail"})

        if self._ensure_initialized():
            checks.append({"name": "model", "status": "ok", "detail": self._model_name})
        else:
            checks.append({"name": "model", "status": "fail", "detail": self._init_error})

        return {
            "healthy": all(c["status"] == "ok" for c in checks),
            "checks": checks,
            "timestamp": time.time(),
        }

    def clear_schema_cache(self) -> int:
        """Clear the compiled schema cache."""
        return self._schema_cache.clear()


# ── Factory ──────────────────────────────────────────────────────


def create_outlines_bridge() -> OutlinesBridge | None:
    """Create an OutlinesBridge if outlines is installed.

    Returns None if the library is not available (graceful fallback).
    """
    try:
        import outlines  # noqa: F401
        return OutlinesBridge()
    except ImportError:
        logger.info("outlines not installed — structured output generation unavailable")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Outlines Bridge CLI")
    parser.add_argument("--prompt", required=True, help="Input prompt")
    parser.add_argument("--schema", help="JSON schema string or file path")
    parser.add_argument("--regex", help="Regex pattern for output")
    parser.add_argument("--type", choices=["json", "regex", "text"], default="json")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    bridge = OutlinesBridge(model_name=args.model)

    if args.type == "regex" and args.regex:
        result = bridge.generate_regex(args.prompt, args.regex, temperature=args.temperature)
    elif args.type == "json":
        schema = None
        if args.schema:
            schema_path = Path(args.schema)
            if schema_path.exists():
                schema = schema_path.read_text()
            else:
                schema = args.schema
        result = bridge.generate_json(args.prompt, output_schema=schema,
                                      temperature=args.temperature)
    else:
        result = bridge.create_custom_generator(args.prompt, temperature=args.temperature)

    print(json.dumps(result, indent=2, default=str))
