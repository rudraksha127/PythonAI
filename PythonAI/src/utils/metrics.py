"""
Lightweight Metrics Collector for PythonAI
══════════════════════════════════════════

Collects in-memory metrics for:
- API request latency and status codes
- RAG query performance (search + generation)
- LLM provider usage and error rates
- Tool execution times

Usage:
    from src.utils.metrics import metrics
    metrics.record_api_request("/ask", "POST", 200, 1.23)
    metrics.record_rag_query(0.45, 0.89, 6)
    metrics.record_provider_call("groq", 0.32, success=True)
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _LatencyBuckets:
    """Track latency distribution with fixed buckets."""
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    _recent: list[float] = field(default_factory=list, repr=False)

    def record(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)
        self._recent.append(ms)
        # Keep last 1000 for percentile calculation
        if len(self._recent) > 1000:
            self._recent = self._recent[-500:]

    def compute_percentiles(self) -> None:
        if not self._recent:
            return
        s = sorted(self._recent)
        n = len(s)
        self.p50_ms = s[n // 2]
        self.p95_ms = s[int(n * 0.95)] if n > 1 else s[0]
        self.p99_ms = s[int(n * 0.99)] if n > 1 else s[0]

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0


class MetricsCollector:
    """Thread-safe in-memory metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._api_requests: dict[str, _LatencyBuckets] = defaultdict(_LatencyBuckets)
        self._api_status_codes: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._rag_queries: _LatencyBuckets = _LatencyBuckets()
        self._rag_search_latency: _LatencyBuckets = _LatencyBuckets()
        self._provider_calls: dict[str, dict[str, float | int]] = defaultdict(lambda: {"success": 0, "error": 0, "total_ms": 0.0})
        self._tool_calls: dict[str, _LatencyBuckets] = defaultdict(_LatencyBuckets)
        self._start_time = time.time()

    def record_api_request(self, path: str, method: str, status_code: int, duration_ms: float) -> None:
        key = f"{method} {path}"
        with self._lock:
            self._api_requests[key].record(duration_ms)
            self._api_status_codes[key][status_code] += 1

    def record_rag_query(self, search_ms: float, total_ms: float, num_results: int) -> None:
        with self._lock:
            self._rag_queries.record(total_ms)
            self._rag_search_latency.record(search_ms)

    def record_provider_call(self, provider: str, duration_ms: float, success: bool = True) -> None:
        with self._lock:
            entry = self._provider_calls[provider]
            if success:
                entry["success"] += 1
            else:
                entry["error"] += 1
            entry["total_ms"] += duration_ms

    def record_tool_call(self, tool_name: str, duration_ms: float) -> None:
        with self._lock:
            self._tool_calls[tool_name].record(duration_ms)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            uptime = time.time() - self._start_time

            api_summary = {}
            for key, buckets in self._api_requests.items():
                buckets.compute_percentiles()
                api_summary[key] = {
                    "count": buckets.count,
                    "avg_ms": round(buckets.avg_ms, 1),
                    "p50_ms": round(buckets.p50_ms, 1),
                    "p95_ms": round(buckets.p95_ms, 1),
                    "status_codes": dict(self._api_status_codes[key]),
                }

            self._rag_queries.compute_percentiles()
            self._rag_search_latency.compute_percentiles()

            providers = {}
            for name, data in self._provider_calls.items():
                total = data["success"] + data["error"]
                providers[name] = {
                    "success": data["success"],
                    "error": data["error"],
                    "success_rate": f"{data['success'] / total * 100:.1f}%" if total > 0 else "N/A",
                    "avg_ms": round(data["total_ms"] / total, 1) if total > 0 else 0.0,
                }

            tools_summary = {}
            for name, buckets in self._tool_calls.items():
                buckets.compute_percentiles()
                tools_summary[name] = {
                    "count": buckets.count,
                    "avg_ms": round(buckets.avg_ms, 1),
                }

            return {
                "uptime_seconds": round(uptime),
                "api_requests": api_summary,
                "rag": {
                    "total_queries": self._rag_queries.count,
                    "avg_total_ms": round(self._rag_queries.avg_ms, 1),
                    "avg_search_ms": round(self._rag_search_latency.avg_ms, 1),
                },
                "providers": providers,
                "tools": tools_summary,
            }

    def reset(self) -> None:
        with self._lock:
            self._api_requests.clear()
            self._api_status_codes.clear()
            self._rag_queries = _LatencyBuckets()
            self._rag_search_latency = _LatencyBuckets()
            self._provider_calls.clear()
            self._tool_calls.clear()
            self._start_time = time.time()


# Global singleton
metrics = MetricsCollector()
