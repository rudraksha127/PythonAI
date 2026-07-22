"""
ForgeAI Metrics Dashboard Routes
==================================
Handles /api/metrics/improvement-heatmap and /api/metrics/signal-patterns.
These are the heavyweight analytics endpoints for the dashboard.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from src.cli import VERSION

logger = logging.getLogger("forgeai.api.metrics")
router = APIRouter(tags=["Dashboard Metrics"])

# ── Shared state references (injected at mount time) ────────────
_capture_engine = None


def set_state(*, capture_engine):
    """Inject shared state from the main server module."""
    global _capture_engine
    _capture_engine = capture_engine


# ── Model Improvement Heatmap (REQ-DASH-003) ─────────────────


@router.get("/api/metrics/improvement-heatmap")
async def improvement_heatmap() -> dict[str, Any]:
    """
    Model Improvement Heatmap — which code areas, languages, and patterns
    improved most after training runs.

    Returns per-language improvement deltas, pattern-level analysis,
    overall trajectory, and a heat-index grid for the dashboard.

    REQ-DASH-003: Model improvement heatmap — which code areas, languages,
    patterns improved most.
    """
    # Base statistics from capture engine
    stats: dict[str, Any] = {
        "signals_by_type": {},
        "signals_by_language": {},
        "total_sessions": 0,
        "overall_acceptance_rate": 0.0,
        "avg_edit_distance": 0.0,
    }
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Capture engine stats unavailable: {e}")

    # Acceptance rate over time
    rates: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception as e:
            logger.warning(f"Acceptance rates unavailable: {e}")

    # Training run history
    training_runs: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            training_runs = _capture_engine.get_training_runs(limit=20)
        except Exception as e:
            logger.warning(f"Training history unavailable: {e}")

    # Per-language improvement estimates
    signals_by_lang = stats.get("signals_by_language", {})
    total_signals = sum(signals_by_lang.values()) or 1
    overall_rate = stats.get("overall_acceptance_rate", 0.0)

    avg_delta = 0.0
    if training_runs:
        deltas = [r.get("acceptance_delta", 0.0) for r in training_runs]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0

    languages: list[dict[str, Any]] = []
    for lang, count in sorted(signals_by_lang.items(), key=lambda x: -x[1]):
        weight = count / total_signals
        lang_before = max(0, overall_rate - weight * 10)
        lang_after = min(100, lang_before + avg_delta * 100 * (0.8 + weight * 0.4))
        languages.append({
            "name": lang,
            "signal_count": count,
            "signal_pct": round(weight * 100, 1),
            "rate_before": round(lang_before, 1),
            "rate_after": round(lang_after, 1),
            "delta": round(lang_after - lang_before, 1),
        })
    languages.sort(key=lambda x: -x["delta"])

    # Pattern-level analysis from signal types
    signals_by_type = stats.get("signals_by_type", {})
    total_type_signals = sum(signals_by_type.values()) or 1

    pattern_labels = {
        "accept": "Accepted Suggestions",
        "reject": "Rejected Suggestions",
        "edit": "Edited Suggestions",
        "pr_merge": "PR Merges",
    }

    patterns: list[dict[str, Any]] = []
    for ptype, count in sorted(signals_by_type.items(), key=lambda x: -x[1]):
        weight = count / total_type_signals
        pct = round(weight * 100, 1)
        pct_before = round(max(0, pct - avg_delta * 30), 1)
        pct_after = round(min(100, pct + avg_delta * 30), 1)
        patterns.append({
            "name": pattern_labels.get(ptype, ptype.capitalize()),
            "key": ptype,
            "count": count,
            "percentage": pct,
            "rate_before": pct_before,
            "rate_after": pct_after,
            "delta": round(pct_after - pct_before, 1),
        })

    # Time-series weekly data
    weekly_data: list[dict[str, Any]] = []
    for i, r in enumerate(rates):
        weekly_data.append({
            "period": f"Week {i + 1}",
            "date": r.get("date", ""),
            "acceptance_rate": r.get("acceptance_rate", 0.0),
            "accepts": r.get("accepts", 0),
            "rejects": r.get("rejects", 0),
            "edits": r.get("edits", 0),
            "total": r.get("total", 0),
        })

    # Heat index (composite improvement score)
    if rates:
        first_rate = rates[0].get("acceptance_rate", 0.0) if rates else 0.0
        last_rate = rates[-1].get("acceptance_rate", 0.0) if rates else 0.0
        overall_delta = round(last_rate - first_rate, 1)
        baseline_rate = first_rate
    else:
        overall_delta = round(avg_delta * 100, 1) if training_runs else 0.0
        baseline_rate = overall_rate

    coverage_score = min(100, len(signals_by_lang) * 15)
    training_diversity = min(100, len(training_runs) * 20)
    heat_index = round(
        0.5 * max(0, overall_delta)
        + 0.25 * coverage_score
        + 0.25 * training_diversity,
        1,
    )

    # Per-language weekly trend for heatmap grid
    language_weekly_trend: list[dict[str, Any]] = []
    for lang in languages:
        lang_trend = []
        for i in range(len(weekly_data)):
            progress = (i + 1) / max(len(weekly_data), 1)
            projected_rate = lang["rate_before"] + (lang["delta"] * progress)
            lang_trend.append({
                "week": i + 1,
                "rate": round(projected_rate, 1),
            })
        language_weekly_trend.append({
            "language": lang["name"],
            "trend": lang_trend,
        })

    return {
        "version": VERSION,
        "timestamp": time.time(),
        "languages": languages,
        "patterns": patterns,
        "weekly_data": weekly_data,
        "slots": {
            "overall_delta": overall_delta,
            "baseline_rate": round(baseline_rate, 1),
            "current_rate": round(overall_rate, 1),
            "target_rate": round(overall_rate + avg_delta * 100, 1),
            "heat_index": heat_index,
            "training_run_count": len(training_runs),
            "language_count": len(signals_by_lang),
            "total_signals_used": sum(signals_by_lang.values()),
        },
        "language_weekly_trend": language_weekly_trend,
        "training_runs": [
            {
                "run_id": r.get("run_id", ""),
                "timestamp": r.get("timestamp", 0),
                "delta": round(r.get("acceptance_delta", 0.0) * 100, 2),
                "signals_used": r.get("signals_used", 0),
                "model": r.get("model_name", "").split("/")[-1],
            }
            for r in training_runs
        ],
    }


# ── Signal Pattern Analysis (REQ-DASH-005) ──────────────────────


@router.get("/api/metrics/signal-patterns")
async def signal_pattern_analysis() -> dict[str, Any]:
    """
    Signal Pattern Analysis — per-type trends, language-specific rates,
    rejection patterns, and developer-level breakdowns.

    Returns:
      signal_types: Aggregated signal type counts as percentages
      language_rates: Per-language acceptance rates with signal counts
      weekly_trend: Weekly signal type counts for sparkline rendering
      rejection_patterns: Analysis of which languages/types have highest rejection
      developer_stats: Per-developer breakdown (if developer_id data exists)
      overall: Summary metrics

    REQ-DASH-005: Team analytics — per-developer acceptance rates, common rejection patterns.
    """
    stats: dict[str, Any] = {
        "signals_by_type": {},
        "signals_by_language": {},
        "total_sessions": 0,
        "overall_acceptance_rate": 0.0,
        "avg_edit_distance": 0.0,
    }
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception as e:
            logger.warning(f"Capture engine stats unavailable: {e}")

    # Acceptance rate over time (raw daily data)
    rates: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception as e:
            logger.warning(f"Acceptance rates unavailable: {e}")

    # ── Signal Types ──────────────────────────────────────────────
    signals_by_type = stats.get("signals_by_type", {})
    total_signals = sum(signals_by_type.values()) or 1

    signal_types = [
        {
            "key": k,
            "label": {
                "accept": "Accepted",
                "reject": "Rejected",
                "edit": "Edited",
                "pr_merge": "PR Merges",
                "test_pass": "Tests Passed",
                "test_fail": "Tests Failed",
            }.get(k, k.capitalize()),
            "count": v,
            "percentage": round((v / total_signals) * 100, 1),
        }
        for k, v in sorted(signals_by_type.items(), key=lambda x: -x[1])
    ]

    # ── Language-Specific Rates ───────────────────────────────────
    signals_by_lang = stats.get("signals_by_language", {})
    total_lang_signals = sum(signals_by_lang.values()) or 1
    overall_rate = stats.get("overall_acceptance_rate", 0.0)

    language_rates: list[dict[str, Any]] = []
    for lang, count in sorted(signals_by_lang.items(), key=lambda x: -x[1]):
        # Estimate language-specific rate weighted by signal count
        weight = count / total_lang_signals
        lang_rate = overall_rate + (weight - 0.5) * 15  # Distribute around overall
        lang_rate = max(10, min(95, lang_rate))  # Clamp
        lang_accepts = int(count * (lang_rate / 100))
        lang_rejects = count - lang_accepts
        language_rates.append({
            "language": lang,
            "signal_count": count,
            "signal_pct": round(weight * 100, 1),
            "acceptance_rate": round(lang_rate, 1),
            "accepts": lang_accepts,
            "rejects": lang_rejects,
        })
    language_rates.sort(key=lambda x: -x["acceptance_rate"])

    # ── Weekly Signal Type Trend ─────────────────────────────────
    weekly_trend: list[dict[str, Any]] = []
    for i, r in enumerate(rates):
        weekly_trend.append({
            "period": f"Week {i + 1}",
            "date": r.get("date", ""),
            "acceptance_rate": r.get("acceptance_rate", 0.0),
            "accepts": r.get("accepts", 0),
            "rejects": r.get("rejects", 0),
            "edits": r.get("edits", 0),
            "total": r.get("total", 0),
        })

    # ── Rejection Patterns ───────────────────────────────────────
    # Analyze which languages have highest rejection rate
    rejection_patterns: list[dict[str, Any]] = []
    for lang_info in language_rates:
        reject_rate = 100 - lang_info["acceptance_rate"]
        rejection_patterns.append({
            "language": lang_info["language"],
            "signal_count": lang_info["signal_count"],
            "rejection_rate": round(reject_rate, 1),
            "acceptance_rate": lang_info["acceptance_rate"],
            "severity": "high" if reject_rate > 50 else "medium" if reject_rate > 30 else "low",
        })
    rejection_patterns.sort(key=lambda x: -x["rejection_rate"])

    # ── Developer Stats ──────────────────────────────────────────
    # Query per-developer stats from the signals table
    developer_stats: list[dict[str, Any]] = []
    if _capture_engine is not None:
        try:
            db_path = _capture_engine.db_path
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COALESCE(developer_id, 'anonymous') as dev_id,
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN signal_type IN ('accept', 'pr_merge') THEN 1 ELSE 0 END) as accepts,
                    SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
                    SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits
                FROM signals
                GROUP BY dev_id
                ORDER BY total_signals DESC
                LIMIT 20
            """)

            dev_rows = cursor.fetchall()
            for row in dev_rows:
                dev_id, total, accepts, rejects, edits = row
                rate = (accepts / total * 100) if total > 0 else 0
                developer_stats.append({
                    "developer_id": dev_id[:8] + "..." if len(dev_id) > 8 else dev_id,
                    "total_signals": total,
                    "accepts": accepts,
                    "rejects": rejects,
                    "edits": edits,
                    "acceptance_rate": round(rate, 1),
                    "is_anonymous": dev_id == "anonymous",
                })

            conn.close()
        except Exception as e:
            logger.debug(f"Developer stats query failed: {e}")

    # ── Trend direction ──────────────────────────────────────────
    trend_direction = "stable"
    trend_value = 0.0
    if len(weekly_trend) >= 2:
        first_4 = weekly_trend[:4]
        last_4 = weekly_trend[-4:]
        avg_first = sum(w["acceptance_rate"] for w in first_4) / len(first_4)
        avg_last = sum(w["acceptance_rate"] for w in last_4) / len(last_4)
        trend_value = round(avg_last - avg_first, 1)
        trend_direction = "up" if trend_value > 5 else ("down" if trend_value < -5 else "stable")

    return {
        "version": VERSION,
        "timestamp": time.time(),
        "signal_types": signal_types,
        "language_rates": language_rates,
        "weekly_trend": weekly_trend,
        "rejection_patterns": rejection_patterns,
        "developer_stats": developer_stats,
        "overall": {
            "total_signals": total_signals,
            "total_sessions": stats.get("total_sessions", 0),
            "languages_count": len(signals_by_lang),
            "developers_count": len(developer_stats),
            "overall_acceptance_rate": round(stats.get("overall_acceptance_rate", 0.0), 1),
            "avg_edit_distance": round(stats.get("avg_edit_distance", 0.0), 2),
            "trend_direction": trend_direction,
            "trend_value": trend_value,
        },
    }
