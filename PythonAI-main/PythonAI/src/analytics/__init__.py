"""
ForgeAI Usage Analytics — Cost/Usage Tracking Per Provider, User & Project
============================================================================

Tracks LLM usage, costs, and token consumption across providers,
users, and projects. Persistent SQLite storage.

Features:
  - Per-provider cost tracking (OpenAI, Anthropic, Ollama, etc.)
  - Per-user and per-project breakdowns
  - Token accounting (prompt + completion)
  - Daily/monthly aggregation
  - Cost estimation for future queries

Usage:
    from src.analytics import UsageTracker, get_tracker

    tracker = get_tracker()
    tracker.log_call(provider="openai", model="gpt-4", prompt_tokens=500,
                     completion_tokens=200, cost=0.03, user_id="alice",
                     project_id="forgeai")
    report = tracker.get_report(days=7)
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


# ═══════════════════════════════════════
# Pricing (per 1K tokens, USD)
# ═══════════════════════════════════════

_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (0.0025, 0.01),  # input, output per 1K tokens
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-4": (0.03, 0.06),
        "gpt-3.5-turbo": (0.0005, 0.0015),
    },
    "anthropic": {
        "claude-sonnet-4": (0.003, 0.015),
        "claude-3-opus": (0.015, 0.075),
        "claude-3-sonnet": (0.003, 0.015),
        "claude-3-haiku": (0.00025, 0.00125),
    },
    "google": {
        "gemini-1.5-pro": (0.00125, 0.005),
        "gemini-1.5-flash": (0.000075, 0.0003),
    },
    "mistral": {
        "mistral-large": (0.002, 0.006),
        "mistral-medium": (0.00275, 0.0081),
        "mistral-small": (0.001, 0.003),
    },
    "groq": {
        "mixtral-8x7b": (0.00027, 0.00027),
        "llama3-70b": (0.00059, 0.00079),
        "llama3-8b": (0.00005, 0.00008),
    },
    "together": {
        "mixtral-8x7b": (0.0006, 0.0006),
        "llama-3-70b": (0.0009, 0.0009),
    },
}


@dataclass
class UsageRecord:
    """A single LLM usage record."""

    id: str
    timestamp: float
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    latency_ms: float
    user_id: str
    project_id: str
    session_id: str
    tags: str  # JSON string

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": self.tags,
        }


# ═══════════════════════════════════════
# Cost Estimation
# ═══════════════════════════════════════


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate the cost of an API call based on known pricing.

    Falls back to a default rate if the provider/model is unknown.
    """
    provider_pricing = _PRICING.get(provider, {})
    pricing = provider_pricing.get(model)

    if pricing:
        input_rate, output_rate = pricing
        cost = (prompt_tokens / 1000) * input_rate + (completion_tokens / 1000) * output_rate
    else:
        # Default: $0.001 per 1K tokens combined
        cost = ((prompt_tokens + completion_tokens) / 1000) * 0.001

    return round(cost, 8)


# ═══════════════════════════════════════
# Usage Tracker
# ═══════════════════════════════════════


class UsageTracker:
    """Tracks LLM usage and costs with SQLite persistence."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._lock = Lock()
        if db_path is None:
            db_path = Path.home() / ".forgeai" / "usage.db"
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost REAL NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                project_id TEXT NOT NULL DEFAULT 'default',
                session_id TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_daily (
                date TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                project_id TEXT NOT NULL DEFAULT 'default',
                total_calls INTEGER NOT NULL DEFAULT 0,
                total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
                total_completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_cost REAL NOT NULL DEFAULT 0,
                avg_latency_ms REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (date, provider, model, user_id, project_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_log(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_log(provider)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_log(user_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_log(project_id)
        """)
        conn.commit()
        conn.close()

    def log_call(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float | None = None,
        latency_ms: float = 0.0,
        user_id: str = "anonymous",
        project_id: str = "default",
        session_id: str = "",
        tags: dict[str, Any] | None = None,
    ) -> str:
        """Log an LLM API call for usage tracking.

        Args:
            provider: Provider name (openai, anthropic, etc.)
            model: Model name (gpt-4, claude-sonnet-4, etc.)
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            cost: Actual cost. If None, estimated from pricing table.
            latency_ms: Response time in milliseconds
            user_id: User identifier
            project_id: Project identifier
            session_id: Session identifier
            tags: Additional metadata as dict

        Returns:
            Record ID
        """
        record_id = str(uuid.uuid4())
        now = time.time()
        total_tokens = prompt_tokens + completion_tokens

        if cost is None:
            cost = estimate_cost(provider, model, prompt_tokens, completion_tokens)

        tags_str = json.dumps(tags or {})

        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """INSERT INTO usage_log
                   (id, timestamp, provider, model, prompt_tokens, completion_tokens,
                    total_tokens, cost, latency_ms, user_id, project_id, session_id, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record_id, now, provider, model, prompt_tokens, completion_tokens,
                 total_tokens, cost, latency_ms, user_id, project_id, session_id, tags_str),
            )

            # Update daily aggregate
            date = self._format_date(now)
            conn.execute("""
                INSERT INTO usage_daily
                (date, provider, model, user_id, project_id, total_calls,
                 total_prompt_tokens, total_completion_tokens, total_cost, avg_latency_ms)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(date, provider, model, user_id, project_id) DO UPDATE SET
                    total_calls = total_calls + 1,
                    total_prompt_tokens = total_prompt_tokens + excluded.total_prompt_tokens,
                    total_completion_tokens = total_completion_tokens + excluded.total_completion_tokens,
                    total_cost = total_cost + excluded.total_cost,
                    avg_latency_ms = (avg_latency_ms * (total_calls - 1) + excluded.avg_latency_ms) / total_calls
            """, (date, provider, model, user_id, project_id,
                  prompt_tokens, completion_tokens, cost, latency_ms))
            conn.commit()
            conn.close()

        return record_id

    # ─── Reporting ────────────────────────────────────────────────

    def get_report(
        self,
        days: int = 7,
        provider: str | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Get a usage report for the specified period.

        Returns summary stats, per-provider breakdown, per-user breakdown,
        and daily trend data.
        """
        cutoff = time.time() - (days * 86400)

        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row

            # Build where clause
            where = "WHERE timestamp >= ?"
            params: list[Any] = [cutoff]
            if provider:
                where += " AND provider = ?"
                params.append(provider)
            if user_id:
                where += " AND user_id = ?"
                params.append(user_id)
            if project_id:
                where += " AND project_id = ?"
                params.append(project_id)

            # Daily trend
            cursor = conn.execute(f"""
                SELECT date(?, 'unixepoch') as day_ref,
                       SUM(total_calls) as calls,
                       SUM(total_prompt_tokens) as prompt_tokens,
                       SUM(total_completion_tokens) as completion_tokens,
                       SUM(total_cost) as cost
                FROM usage_daily
                WHERE date >= date(?, 'unixepoch')
                GROUP BY day_ref
                ORDER BY day_ref DESC
            """, (cutoff, cutoff))
            daily_trend = [dict(r) for r in cursor.fetchall()]

            # Per-provider breakdown
            cursor = conn.execute(f"""
                SELECT provider,
                       COUNT(*) as calls,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(total_tokens) as total_tokens,
                       SUM(cost) as cost,
                       AVG(latency_ms) as avg_latency_ms
                FROM usage_log {where}
                GROUP BY provider
                ORDER BY cost DESC
            """, params)
            per_provider = [dict(r) for r in cursor.fetchall()]

            # Per-user breakdown
            cursor = conn.execute(f"""
                SELECT user_id,
                       COUNT(*) as calls,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(cost) as cost
                FROM usage_log {where}
                GROUP BY user_id
                ORDER BY cost DESC
            """, params)
            per_user = [dict(r) for r in cursor.fetchall()]

            # Per-project breakdown
            cursor = conn.execute(f"""
                SELECT project_id,
                       COUNT(*) as calls,
                       SUM(prompt_tokens) as prompt_tokens,
                       SUM(completion_tokens) as completion_tokens,
                       SUM(cost) as cost
                FROM usage_log {where}
                GROUP BY project_id
                ORDER BY cost DESC
            """, params)
            per_project = [dict(r) for r in cursor.fetchall()]

            # Overall totals
            cursor = conn.execute(f"""
                SELECT COUNT(*) as total_calls,
                       COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                       COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                       COALESCE(SUM(total_tokens), 0) as total_tokens,
                       COALESCE(SUM(cost), 0) as total_cost,
                       COALESCE(AVG(latency_ms), 0) as avg_latency_ms
                FROM usage_log {where}
            """, params)
            totals = dict(cursor.fetchone())

            conn.close()

        return {
            "period_days": days,
            "cutoff_timestamp": cutoff,
            "totals": {
                "total_calls": totals.get("total_calls", 0),
                "total_prompt_tokens": totals.get("total_prompt_tokens", 0),
                "total_completion_tokens": totals.get("total_completion_tokens", 0),
                "total_tokens": totals.get("total_tokens", 0),
                "total_cost": round(totals.get("total_cost", 0), 6),
                "avg_latency_ms": round(totals.get("avg_latency_ms", 0), 1),
            },
            "per_provider": per_provider,
            "per_user": per_user,
            "per_project": per_project,
            "daily_trend": daily_trend,
        }

    def get_cost_summary(self, days: int = 30) -> dict[str, Any]:
        """Get a cost-focused summary for the dashboard."""
        report = self.get_report(days=days)
        totals = report["totals"]

        # Provider cost ranking
        provider_costs = [
            {"provider": p["provider"], "cost": round(p["cost"], 4), "calls": p["calls"]}
            for p in report["per_provider"]
        ]

        # Daily cost trend
        daily_costs = [
            {
                "date": d.get("day_ref", ""),
                "cost": round(d.get("cost", 0), 4),
                "calls": d.get("calls", 0),
            }
            for d in report["daily_trend"]
        ]

        return {
            "total_cost": round(totals["total_cost"], 4),
            "total_calls": totals["total_calls"],
            "total_tokens": totals["total_tokens"],
            "avg_cost_per_call": round(totals["total_cost"] / max(1, totals["total_calls"]), 6),
            "avg_tokens_per_call": round(totals["total_tokens"] / max(1, totals["total_calls"])),
            "provider_costs": provider_costs,
            "daily_costs": daily_costs,
            "period_days": days,
        }

    def get_provider_models(self, provider: str) -> list[dict[str, Any]]:
        """Get distinct models used for a provider."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute(
                "SELECT DISTINCT model, COUNT(*) as calls FROM usage_log WHERE provider = ? GROUP BY model ORDER BY calls DESC",
                (provider,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
        return rows

    def clear_old_data(self, days: int = 90) -> int:
        """Delete records older than the specified number of days. Returns count deleted."""
        cutoff = time.time() - (days * 86400)
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute("DELETE FROM usage_log WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
        return deleted

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _format_date(timestamp: float) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).strftime("%Y-%m-%d")


# ═══════════════════════════════════════
# Global Singleton
# ═══════════════════════════════════════

_tracker: UsageTracker | None = None


def get_tracker(db_path: str | Path | None = None) -> UsageTracker:
    """Get or create the global usage tracker."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker(db_path=db_path)
    return _tracker


__all__ = [
    "UsageTracker",
    "UsageRecord",
    "estimate_cost",
    "get_tracker",
]
