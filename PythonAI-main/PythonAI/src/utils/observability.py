"""
ForgeAI Observability — Langfuse Tracing Integration
=====================================================
Provides LLM call tracing, RAG query spans, and agent execution observability via Langfuse.

Graceful Fallback:
If langfuse is not installed or keys are not set, falls back to lightweight local logging.

Environment Variables:
    LANGFUSE_PUBLIC_KEY  : Langfuse public key
    LANGFUSE_SECRET_KEY  : Langfuse secret key
    LANGFUSE_HOST        : Langfuse host URL (default: https://cloud.langfuse.com)
    FORGEAI_TRACING_ENABLED: "true" (default) or "false"
"""
from __future__ import annotations

import functools
import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger("forgeai.observability")

_LANGFUSE_CLIENT = None
_TRACING_ENABLED = os.environ.get("FORGEAI_TRACING_ENABLED", "true").lower() == "true"


def get_langfuse_client() -> Any | None:
    """Get initialized Langfuse client or None if disabled/missing."""
    global _LANGFUSE_CLIENT

    if not _TRACING_ENABLED:
        return None

    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT

    try:
        from langfuse import Langfuse

        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

        if pk and sk:
            _LANGFUSE_CLIENT = Langfuse(public_key=pk, secret_key=sk, host=host)
            logger.info(f"Langfuse observability initialized (host={host})")
        else:
            logger.debug("Langfuse keys missing (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY). Tracing in local log mode.")
            _LANGFUSE_CLIENT = None

    except ImportError:
        logger.debug("langfuse package not installed. Tracing disabled.")
        _LANGFUSE_CLIENT = None
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        _LANGFUSE_CLIENT = None

    return _LANGFUSE_CLIENT


def trace_llm_call(name: str | None = None) -> Callable:
    """Decorator to trace an LLM call or function execution."""

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            client = get_langfuse_client()
            start = time.time()
            if client is not None:
                try:
                    trace = client.trace(name=span_name, input={"args": str(args)[:200], "kwargs": str(kwargs)[:200]})
                    res = func(*args, **kwargs)
                    elapsed_ms = (time.time() - start) * 1000
                    trace.update(output=str(res)[:500], metadata={"elapsed_ms": elapsed_ms})
                    return res
                except Exception as e:
                    logger.debug(f"Langfuse tracing error in {span_name}: {e}")
                    return func(*args, **kwargs)

            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            client = get_langfuse_client()
            start = time.time()
            if client is not None:
                try:
                    trace = client.trace(name=span_name, input={"args": str(args)[:200], "kwargs": str(kwargs)[:200]})
                    res = await func(*args, **kwargs)
                    elapsed_ms = (time.time() - start) * 1000
                    trace.update(output=str(res)[:500], metadata={"elapsed_ms": elapsed_ms})
                    return res
                except Exception as e:
                    logger.debug(f"Langfuse tracing error in {span_name}: {e}")
                    return await func(*args, **kwargs)

            return await func(*args, **kwargs)

        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def asyncio_iscoroutinefunction(func: Any) -> bool:
    import inspect
    return inspect.iscoroutinefunction(func)


def flush_traces() -> None:
    """Flush pending traces to Langfuse backend."""
    client = get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.debug(f"Error flushing Langfuse traces: {e}")
