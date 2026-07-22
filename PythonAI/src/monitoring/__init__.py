"""
ForgeAI Monitoring — Performance Metrics, Health Checks & Observability
=======================================================================

Collects API request metrics, system health, and performance data for
the dashboard and Prometheus/Grafana integration.

Metrics collected:
  - API request count, latency, status codes
  - Provider call success/failure rates
  - RAG retrieval latency
  - Training pipeline progress
  - System resource usage (CPU, memory)

Usage:
    from src.monitoring import metrics, record_api_call

    metrics.record_api_call("/api/rag/search", "POST", 200, 145.2)
    report = metrics.get_summary()
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any


# ═══════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════


@dataclass
class _EndpointStats:
    """Per-endpoint statistics."""

    count: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    status_codes: dict[int, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class _ProviderStats:
    """Per-provider call statistics."""

    calls: int = 0
    errors: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0


class MetricsCollector:
    """Thread-safe metrics collection for the ForgeAI system."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._lock = Lock()
        self._start_time = time.time()

        # API metrics
        self._endpoints: dict[str, dict[str, _EndpointStats]] = {}  # path -> method -> stats

        # Provider metrics
        self._providers: dict[str, _ProviderStats] = {}

        # RAG metrics
        self._rag_queries: int = 0
        self._rag_errors: int = 0
        self._rag_latency_ms: list[float] = []

        # Training metrics
        self._training_runs: int = 0
        self._training_errors: int = 0

        # Persistence
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".forgeai" / "metrics"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # ─── API Metrics ─────────────────────────────────────────────

    def record_api_request(
        self,
        path: str,
        method: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        """Record an API request with its response time and status."""
        with self._lock:
            if path not in self._endpoints:
                self._endpoints[path] = {}
            if method not in self._endpoints[path]:
                self._endpoints[path][method] = _EndpointStats()

            stats = self._endpoints[path][method]
            stats.count += 1
            stats.total_latency_ms += latency_ms
            stats.max_latency_ms = max(stats.max_latency_ms, latency_ms)
            stats.min_latency_ms = min(stats.min_latency_ms, latency_ms)
            stats.status_codes[status_code] += 1

            if status_code >= 400:
                stats.errors += 1

    # ─── Provider Metrics ─────────────────────────────────────────

    def record_provider_call(
        self,
        provider: str,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record an LLM provider call."""
        with self._lock:
            if provider not in self._providers:
                self._providers[provider] = _ProviderStats()

            stats = self._providers[provider]
            stats.calls += 1
            if not success:
                stats.errors += 1
            stats.total_tokens += prompt_tokens + completion_tokens
            stats.prompt_tokens += prompt_tokens
            stats.completion_tokens += completion_tokens
            stats.total_cost += cost
            stats.total_latency_ms += latency_ms

    # ─── RAG Metrics ──────────────────────────────────────────────

    def record_rag_query(self, latency_ms: float, success: bool = True) -> None:
        """Record a RAG retrieval query."""
        with self._lock:
            self._rag_queries += 1
            if not success:
                self._rag_errors += 1
            self._rag_latency_ms.append(latency_ms)
            # Keep last 1000 latencies for p95 calculation
            if len(self._rag_latency_ms) > 1000:
                self._rag_latency_ms = self._rag_latency_ms[-1000:]

    # ─── Training Metrics ─────────────────────────────────────────

    def record_training_run(self, success: bool = True) -> None:
        """Record a training pipeline run."""
        with self._lock:
            self._training_runs += 1
            if not success:
                self._training_errors += 1

    # ─── Reporting ────────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get a comprehensive metrics summary."""
        with self._lock:
            uptime = time.time() - self._start_time

            # Aggregate endpoint stats
            total_requests = 0
            total_errors = 0
            endpoints_report: list[dict[str, Any]] = []

            for path, methods in sorted(self._endpoints.items()):
                for method, stats in sorted(methods.items()):
                    total_requests += stats.count
                    total_errors += stats.errors
                    avg_latency = stats.total_latency_ms / max(1, stats.count)
                    endpoints_report.append({
                        "path": path,
                        "method": method,
                        "count": stats.count,
                        "errors": stats.errors,
                        "error_rate": round(stats.errors / max(1, stats.count) * 100, 2),
                        "avg_latency_ms": round(avg_latency, 1),
                        "max_latency_ms": round(stats.max_latency_ms, 1),
                        "min_latency_ms": round(stats.min_latency_ms if stats.min_latency_ms != float("inf") else 0, 1),
                        "status_codes": dict(stats.status_codes),
                    })

            # Aggregate provider stats
            providers_report: list[dict[str, Any]] = []
            total_cost = 0.0
            for provider, stats in sorted(self._providers.items()):
                avg_latency = stats.total_latency_ms / max(1, stats.calls)
                total_cost += stats.total_cost
                providers_report.append({
                    "provider": provider,
                    "calls": stats.calls,
                    "errors": stats.errors,
                    "error_rate": round(stats.errors / max(1, stats.calls) * 100, 2),
                    "total_tokens": stats.total_tokens,
                    "prompt_tokens": stats.prompt_tokens,
                    "completion_tokens": stats.completion_tokens,
                    "total_cost": round(stats.total_cost, 6),
                    "avg_latency_ms": round(avg_latency, 1),
                })

            # RAG latency p95
            rag_p95 = 0.0
            if self._rag_latency_ms:
                sorted_latencies = sorted(self._rag_latency_ms)
                p95_idx = int(len(sorted_latencies) * 0.95)
                rag_p95 = sorted_latencies[p95_idx]

            return {
                "server": {
                    "uptime_seconds": round(uptime),
                    "uptime_human": self._format_uptime(uptime),
                },
                "api": {
                    "total_requests": total_requests,
                    "total_errors": total_errors,
                    "overall_error_rate": round(total_errors / max(1, total_requests) * 100, 2),
                    "endpoints": endpoints_report,
                },
                "providers": {
                    "total_calls": sum(p.calls for p in self._providers.values()),
                    "total_cost": round(total_cost, 6),
                    "providers": providers_report,
                },
                "rag": {
                    "total_queries": self._rag_queries,
                    "errors": self._rag_errors,
                    "avg_latency_ms": round(
                        sum(self._rag_latency_ms) / max(1, len(self._rag_latency_ms)), 1
                    ) if self._rag_latency_ms else 0,
                    "p95_latency_ms": round(rag_p95, 1),
                },
                "training": {
                    "total_runs": self._training_runs,
                    "errors": self._training_errors,
                    "success_rate": round(
                        (self._training_runs - self._training_errors) / max(1, self._training_runs) * 100, 2
                    ),
                },
                "timestamp": time.time(),
            }

    def get_prometheus_text(self) -> str:
        """Get metrics in Prometheus exposition format."""
        summary = self.get_summary()
        lines = [
            "# HELP forgeai_uptime_seconds Server uptime in seconds",
            "# TYPE forgeai_uptime_seconds gauge",
            f"forgeai_uptime_seconds {summary['server']['uptime_seconds']}",
            "",
            "# HELP forgeai_api_requests_total Total API requests",
            "# TYPE forgeai_api_requests_total counter",
            f"forgeai_api_requests_total {summary['api']['total_requests']}",
            "",
            "# HELP forgeai_api_errors_total Total API errors",
            "# TYPE forgeai_api_errors_total counter",
            f"forgeai_api_errors_total {summary['api']['total_errors']}",
            "",
        ]

        for ep in summary["api"]["endpoints"]:
            safe_path = ep["path"].replace("/", "_").replace("-", "_")
            lines.append(f"# HELP forgeai_api_{safe_path}_count Request count for {ep['path']}")
            lines.append(f"# TYPE forgeai_api_{safe_path}_count counter")
            lines.append(f'forgeai_api_{safe_path}_count{{method="{ep["method"]}"}} {ep["count"]}')
            lines.append("")

        lines.append("# HELP forgeai_provider_calls_total Total LLM provider calls")
        lines.append("# TYPE forgeai_provider_calls_total counter")
        for prov in summary["providers"]["providers"]:
            lines.append(
                f'forgeai_provider_calls_total{{provider="{prov["provider"]}"}} {prov["calls"]}'
            )
        lines.append("")

        return "\n".join(lines)

    def save_to_disk(self) -> None:
        """Persist metrics to disk for recovery."""
        summary = self.get_summary()
        path = self._data_dir / "metrics_snapshot.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)


# Global singleton
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def record_api_request(path: str, method: str, status_code: int, latency_ms: float) -> None:
    """Convenience function to record an API request."""
    get_metrics().record_api_request(path, method, status_code, latency_ms)


def record_provider_call(
    provider: str,
    success: bool,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0.0,
) -> None:
    """Convenience function to record a provider call."""
    get_metrics().record_provider_call(provider, success, latency_ms, prompt_tokens, completion_tokens, cost)


# ═══════════════════════════════════════
# Health Check
# ═══════════════════════════════════════


def create_health_report(
    version: str = "unknown",
    db_ok: bool = True,
    inference_connected: bool = False,
    rag_available: bool = False,
    training_idle: bool = True,
) -> dict[str, Any]:
    """Create a comprehensive health report for the /health endpoint."""
    metrics = get_metrics()
    summary = metrics.get_summary()

    return {
        "status": "healthy",
        "version": version,
        "timestamp": time.time(),
        "uptime": summary["server"]["uptime_human"],
        "uptime_seconds": summary["server"]["uptime_seconds"],
        "components": {
            "database": {
                "status": "ok" if db_ok else "error",
                "message": "Connected" if db_ok else "Disconnected",
            },
            "inference": {
                "status": "ok" if inference_connected else "degraded",
                "message": "Connected" if inference_connected else "No inference endpoint configured",
            },
            "rag": {
                "status": "ok" if rag_available else "degraded",
                "message": "Available" if rag_available else "Not initialized",
            },
            "training": {
                "status": "ok" if training_idle else "busy",
                "message": "Idle" if training_idle else "Training in progress",
            },
        },
        "api": {
            "total_requests": summary["api"]["total_requests"],
            "error_rate": summary["api"]["overall_error_rate"],
        },
        "providers": {
            "total_calls": summary["providers"]["total_calls"],
            "total_cost": summary["providers"]["total_cost"],
        },
    }


__all__ = [
    "MetricsCollector",
    "get_metrics",
    "record_api_request",
    "record_provider_call",
    "create_health_report",
]
