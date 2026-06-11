"""
ForgeAI Dashboard — Acceptance Rate Tracker & Visualization
============================================================

Generates a standalone HTML dashboard with:
- 12-week acceptance rate curve (daily + rolling avg)
- Signal type breakdown (accept/reject/edit)
- Language breakdown chart
- Training run history
- Session and developer stats

Reads from the CaptureEngine SQLite database.
Uses Chart.js for interactive charts (loaded from CDN).

Usage:
    python -m src.learning.forge_dashboard
    python -m src.cli forge dashboard
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ─── Data Access Layer ──────────────────────────────────────────────


def _get_db_path() -> Path:
    """Resolve the ForgeAI signals database path."""
    return Path.home() / ".forgeai" / "signals.db"


def _query_acceptance_rate(db_path: Path, weeks: int = 12) -> list[dict[str, Any]]:
    """Get daily acceptance rate for the last N weeks."""
    if not db_path.exists():
        return []

    cutoff = time.time() - (weeks * 7 * 86400)
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
        SELECT
            DATE(timestamp, 'unixepoch') as date,
            SUM(CASE WHEN signal_type = 'accept' OR signal_type = 'pr_merge' THEN 1 ELSE 0 END) as accepts,
            SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
            SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits,
            SUM(CASE WHEN signal_type = 'test_pass' THEN 1 ELSE 0 END) as tests_passed,
            SUM(CASE WHEN signal_type = 'test_fail' THEN 1 ELSE 0 END) as tests_failed,
            COUNT(*) as total
        FROM signals
        WHERE timestamp >= ?
        GROUP BY DATE(timestamp, 'unixepoch')
        ORDER BY date
        """, (cutoff,))
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    data = []
    for row in rows:
        accepts = row[1]
        total = row[6]
        data.append({
            "date": row[0],
            "accepts": accepts,
            "rejects": row[2],
            "edits": row[3],
            "tests_passed": row[4],
            "tests_failed": row[5],
            "total": total,
            "acceptance_rate": round(accepts / total * 100, 1) if total > 0 else 0,
        })
    return data


def _query_signal_breakdown(db_path: Path) -> dict[str, int]:
    """Get total signals by type."""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT signal_type, COUNT(*) FROM signals GROUP BY signal_type")
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error:
        return {}


def _query_language_breakdown(db_path: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Get signal counts by language."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT language, COUNT(*) as cnt
            FROM signals GROUP BY language
            ORDER BY cnt DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [{"language": r[0] or "unknown", "count": r[1]} for r in rows]
    except sqlite3.Error:
        return []


def _query_training_runs(db_path: Path) -> list[dict[str, Any]]:
    """Get training run history."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT run_id, timestamp, model_name, signals_used,
                   train_loss, eval_loss, acceptance_rate_before,
                   acceptance_rate_after, metrics
            FROM training_runs
            ORDER BY timestamp DESC LIMIT 20
        """)
        rows = cursor.fetchall()
        conn.close()

        runs = []
        for r in rows:
            ts = datetime.fromtimestamp(r[1], tz=timezone.utc)
            runs.append({
                "run_id": r[0],
                "date": ts.strftime("%Y-%m-%d"),
                "model": r[2],
                "signals_used": r[3],
                "train_loss": r[4],
                "eval_loss": r[5],
                "rate_before": r[6],
                "rate_after": r[7],
            })
        return runs
    except sqlite3.Error:
        return []


def _query_session_stats(db_path: Path) -> dict[str, Any]:
    """Get session-level statistics."""
    if not db_path.exists():
        return {"total_sessions": 0, "unique_developers": 0}
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT developer_id) FROM signals WHERE developer_id IS NOT NULL")
        unique_developers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM signals")
        total_signals = cursor.fetchone()[0]

        cursor.execute("""
            SELECT
                SUM(CASE WHEN signal_type = 'accept' OR signal_type = 'pr_merge' THEN 1 ELSE 0 END),
                SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END)
            FROM signals
        """)
        row = cursor.fetchone()
        total_accepts = row[0] or 0
        total_rejects = row[1] or 0
        total_decisions = total_accepts + total_rejects

        conn.close()

        return {
            "total_signals": total_signals,
            "total_sessions": total_sessions,
            "unique_developers": unique_developers,
            "total_accepts": total_accepts,
            "total_rejects": total_rejects,
            "overall_rate": round(total_accepts / total_decisions * 100, 1) if total_decisions > 0 else 0,
        }
    except sqlite3.Error:
        return {"total_sessions": 0, "unique_developers": 0}


def _compute_rolling_average(data: list[dict[str, Any]], window: int = 7) -> list[float | None]:
    """Compute rolling/moving average of acceptance rates."""
    rates = [d["acceptance_rate"] for d in data]
    result: list[float | None] = []
    for i in range(len(rates)):
        if i < window - 1:
            result.append(None)
        else:
            window_vals = rates[i - window + 1:i + 1]
            result.append(round(sum(window_vals) / len(window_vals), 1))
    return result


# ─── Template Helpers ────────────────────────────────────────────────


def _apply_placeholders(template: str, **placeholders: str) -> str:
    """Replace {KEY} placeholders in template without using .format().

    This avoids conflicts with CSS curly braces that would cause KeyError
    with str.format().
    """
    for key, value in placeholders.items():
        template = template.replace("{" + key + "}", str(value))
    return template


# ─── HTML Dashboard Generator ──────────────────────────────────────


def _build_training_runs_table(runs: list[dict[str, Any]]) -> str:
    """Build HTML table for training run history."""
    if not runs:
        return '<p style="color: var(--text-muted); padding: 20px;">No training runs recorded yet. Run training with --capture to populate this table.</p>'

    rows_html = ""
    for r in runs:
        before = f"{r['rate_before']:.1f}%" if r['rate_before'] else "\u2014"
        after = f"{r['rate_after']:.1f}%" if r['rate_after'] else "\u2014"
        tl = f"{r['train_loss']:.4f}" if r['train_loss'] else "\u2014"
        el = f"{r['eval_loss']:.4f}" if r['eval_loss'] else "\u2014"

        delta = ""
        if r['rate_before'] and r['rate_after']:
            diff = r['rate_after'] - r['rate_before']
            arrow = "\u2191" if diff > 0 else "\u2193"
            color = "var(--accent-emerald)" if diff > 0 else "var(--accent-rose)"
            delta = f'<span style="color: {color};">{arrow} {diff:+.1f}%</span>'

        rows_html += f"<tr><td>{r['date']}</td><td>{r['model']}</td><td>{r['signals_used']}</td><td>{tl}</td><td>{el}</td><td>{before}</td><td>{after}</td><td>{delta}</td></tr>"

    return f"""<div style="overflow-x: auto;">
    <table class="runs-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Model</th>
          <th>Signals</th>
          <th>Train Loss</th>
          <th>Eval Loss</th>
          <th>Rate Before</th>
          <th>Rate After</th>
          <th>Delta</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>"""


def _build_empty_state() -> str:
    """Build empty state HTML shown when no data exists."""
    return """<div class="empty-state">
    <h3>\U0001f4ed No Signal Data Yet</h3>
    <p>
      The Capture Engine database is empty or doesn't exist yet.<br><br>
      To start collecting signals, use the CaptureEngine in your VS Code extension or script:<br>
      <span class="code">from src.learning.capture_engine import CaptureEngine</span><br>
      <span class="code">engine = CaptureEngine()</span><br>
      <span class="code">engine.capture_accept(suggestion, file_path, line_number, language)</span><br><br>
      Or add some demo data to preview the dashboard:<br>
      <span class="code">python -m src.learning.forge_dashboard --demo</span>
    </p>
  </div>"""


def _generate_demo_data() -> dict[str, Any]:
    """Generate synthetic demo data for previewing the dashboard."""
    import random
    from datetime import date

    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(84, -1, -1)]

    base_rate = 0.27
    daily_data = []
    for i, d in enumerate(dates):
        progress = i / len(dates)
        current_rate = base_rate + (0.43 * progress)
        noise = random.uniform(-0.08, 0.08)
        noisy_rate = max(0.0, min(1.0, current_rate + noise))

        total = random.randint(8, 25)
        accepts = int(total * noisy_rate)
        rejects = total - accepts - random.randint(0, 3)
        edits = total - accepts - rejects
        if edits < 0:
            edits = 0
            rejects = total - accepts

        daily_data.append({
            "date": d,
            "accepts": accepts,
            "rejects": max(0, rejects),
            "edits": edits,
            "tests_passed": random.randint(0, accepts),
            "tests_failed": random.randint(0, max(1, total - accepts)),
            "total": total,
            "acceptance_rate": round(accepts / total * 100, 1) if total > 0 else 0,
        })

    languages = ["python", "javascript", "typescript", "go", "rust", "java", "cpp", "ruby"]
    lang_data = [{"language": lang, "count": random.randint(10, 200)} for lang in languages]
    lang_data.sort(key=lambda x: -x["count"])

    training_runs = [
        {"run_id": f"run_{i:03d}", "date": (today - timedelta(days=i * 7)).isoformat(),
         "model": "Qwen3-Coder-14B", "signals_used": random.randint(100, 800),
         "train_loss": round(random.uniform(0.3, 1.2), 4),
         "eval_loss": round(random.uniform(0.4, 1.4), 4),
         "rate_before": round(max(20, 70 - i * 3 + random.uniform(-5, 5)), 1),
         "rate_after": round(max(25, 73 - i * 3 + random.uniform(-3, 3)), 1)}
        for i in range(10, 0, -1)
    ]

    return {
        "daily_data": daily_data,
        "signal_breakdown": {
            "accept": sum(d["accepts"] for d in daily_data),
            "reject": sum(d["rejects"] for d in daily_data),
            "edit": sum(d["edits"] for d in daily_data),
            "test_pass": sum(d["tests_passed"] for d in daily_data),
            "test_fail": sum(d["tests_failed"] for d in daily_data),
        },
        "language_data": lang_data,
        "training_runs": training_runs,
        "sessions": {"total_sessions": 145, "unique_developers": 5, "total_signals": sum(d["total"] for d in daily_data),
                     "total_accepts": sum(d["accepts"] for d in daily_data),
                     "total_rejects": sum(d["rejects"] for d in daily_data),
                     "overall_rate": round(sum(d["accepts"] for d in daily_data) / max(1, sum(d["total"] for d in daily_data)) * 100, 1)},
    }


def generate_dashboard(
    db_path: str | Path | None = None,
    output_path: str | Path | None = None,
    weeks: int = 12,
    demo: bool = False,
) -> str:
    """Generate the acceptance rate dashboard HTML.

    Args:
        db_path: Path to the signals database. Defaults to ~/.forgeai/signals.db.
        output_path: If provided, write HTML to this file.
        weeks: Number of weeks of data to show (default 12).
        demo: If True, generate synthetic demo data.

    Returns:
        The generated HTML string.
    """
    if demo:
        data = _generate_demo_data()
    else:
        resolved_db = Path(db_path) if db_path else _get_db_path()
        if not resolved_db.exists():
            return _render_empty_dashboard(output_path)

        daily_data = _query_acceptance_rate(resolved_db, weeks=weeks)
        session_stats = _query_session_stats(resolved_db)
        signal_breakdown = _query_signal_breakdown(resolved_db)
        lang_data = _query_language_breakdown(resolved_db)
        training_runs = _query_training_runs(resolved_db)

        data = {
            "daily_data": daily_data,
            "session_stats": session_stats,
            "signal_breakdown": signal_breakdown,
            "language_data": lang_data,
            "training_runs": training_runs,
        }

    # Build chart data
    daily = data["daily_data"]
    rolling = _compute_rolling_average(daily) if daily else []

    chart_labels = json.dumps([d["date"] for d in daily])
    chart_daily = json.dumps([d["acceptance_rate"] for d in daily])
    chart_rolling = json.dumps(rolling)
    chart_accepts = json.dumps([d["accepts"] for d in daily])
    chart_rejects = json.dumps([d["rejects"] for d in daily])

    # Signal breakdown
    sb = data.get("signal_breakdown", {})
    signal_type_order = ["accept", "reject", "edit", "test_pass", "test_fail", "pr_merge", "implicit_accept"]
    sig_labels = json.dumps([s.capitalize() for s in signal_type_order if sb.get(s, 0) > 0])
    sig_values = json.dumps([sb.get(s, 0) for s in signal_type_order if sb.get(s, 0) > 0])

    # Language data
    lang = data.get("language_data", [])
    lang_labels = json.dumps([l["language"] for l in lang])
    lang_values = json.dumps([l["count"] for l in lang])

    # Sessions
    if demo:
        sessions = data["sessions"]
        total_signals_display = sessions["total_signals"]
        total_accepts_display = sessions["total_accepts"]
        overall_rate_display = sessions["overall_rate"]
        total_sessions_display = sessions["total_sessions"]
        unique_devs_display = sessions["unique_developers"]
        training_runs_list = data["training_runs"]
    else:
        ss = data.get("session_stats", {})
        total_signals_display = ss.get("total_signals", 0)
        total_accepts_display = ss.get("total_accepts", 0)
        overall_rate_display = ss.get("overall_rate", 0)
        total_sessions_display = ss.get("total_sessions", 0)
        unique_devs_display = ss.get("unique_developers", 0)
        training_runs_list = data.get("training_runs", [])

    training_runs_count = len(training_runs_list)
    has_data = len(daily) > 0 or demo
    empty_state = "" if has_data else _build_empty_state()

    generated_at = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    html = _render_dashboard_html(
        generated_at=generated_at,
        overall_rate=overall_rate_display,
        total_accepts=str(total_accepts_display),
        total_signals=str(total_signals_display),
        total_sessions=str(total_sessions_display),
        unique_developers=str(unique_devs_display),
        training_runs_count=str(training_runs_count),
        chart_labels=chart_labels,
        chart_daily_rates=chart_daily,
        chart_rolling_avg=chart_rolling,
        chart_accepts=chart_accepts,
        chart_rejects=chart_rejects,
        signal_labels=sig_labels,
        signal_values=sig_values,
        lang_labels=lang_labels,
        lang_values=lang_values,
        training_runs_table=_build_training_runs_table(training_runs_list),
        empty_state=empty_state,
    )

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    return html


# ─── HTML Rendering ──────────────────────────────────────────────────


def _render_empty_dashboard(output_path: str | Path | None = None) -> str:
    """Render dashboard with empty state (no DB exists)."""
    generated_at = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    html = _render_dashboard_html(
        generated_at=generated_at,
        overall_rate="\u2014",
        total_accepts="0",
        total_signals="0",
        total_sessions="0",
        unique_developers="0",
        training_runs_count="0",
        chart_labels="[]",
        chart_daily_rates="[]",
        chart_rolling_avg="[]",
        chart_accepts="[]",
        chart_rejects="[]",
        signal_labels="[]",
        signal_values="[]",
        lang_labels="[]",
        lang_values="[]",
        training_runs_table=_build_training_runs_table([]),
        empty_state=_build_empty_state(),
    )
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


def _render_dashboard_html(
    generated_at: str = "",
    overall_rate: Any = "\u2014",
    total_accepts: str = "0",
    total_signals: str = "0",
    total_sessions: str = "0",
    unique_developers: str = "0",
    training_runs_count: str = "0",
    chart_labels: str = "[]",
    chart_daily_rates: str = "[]",
    chart_rolling_avg: str = "[]",
    chart_accepts: str = "[]",
    chart_rejects: str = "[]",
    signal_labels: str = "[]",
    signal_values: str = "[]",
    lang_labels: str = "[]",
    lang_values: str = "[]",
    training_runs_table: str = "",
    empty_state: str = "",
) -> str:
    """Build the complete HTML dashboard string using placeholder replacement.

    Uses _apply_placeholders to avoid conflicts between CSS curly braces
    and Python str.format().
    """
    return _apply_placeholders(
        _HTML_TEMPLATE,
        GENERATED_AT=generated_at,
        OVERALL_RATE=str(overall_rate) if not isinstance(overall_rate, str) else overall_rate,
        TOTAL_ACCEPTS=total_accepts,
        TOTAL_SIGNALS=total_signals,
        TOTAL_SESSIONS=total_sessions,
        UNIQUE_DEVELOPERS=unique_developers,
        TRAINING_RUNS_COUNT=training_runs_count,
        CHART_LABELS=chart_labels,
        CHART_DAILY_RATES=chart_daily_rates,
        CHART_ROLLING_AVG=chart_rolling_avg,
        CHART_ACCEPTS=chart_accepts,
        CHART_REJECTS=chart_rejects,
        SIGNAL_LABELS=signal_labels,
        SIGNAL_VALUES=signal_values,
        LANG_LABELS=lang_labels,
        LANG_VALUES=lang_values,
        TRAINING_RUNS_TABLE=training_runs_table,
        EMPTY_STATE=empty_state,
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ForgeAI — Acceptance Rate Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg-primary: #0a0e1a;
      --bg-card: rgba(15, 23, 42, 0.85);
      --bg-card-hover: rgba(20, 30, 55, 0.95);
      --border: rgba(99, 102, 241, 0.15);
      --text-primary: #e2e8f0;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent-indigo: #818cf8;
      --accent-violet: #a78bfa;
      --accent-emerald: #34d399;
      --accent-amber: #fbbf24;
      --accent-rose: #fb7185;
      --accent-cyan: #22d3ee;
      --accent-blue: #60a5fa;
      --gradient-hero: linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7);
      --radius: 16px;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      min-height: 100vh;
    }
    body::before {
      content: '';
      position: fixed; inset: 0;
      background:
        radial-gradient(ellipse 600px 400px at 20% 20%, rgba(99,102,241,0.08), transparent),
        radial-gradient(ellipse 500px 350px at 80% 80%, rgba(168,85,247,0.06), transparent);
      z-index: 0;
      animation: bgPulse 8s ease-in-out infinite alternate;
    }
    @keyframes bgPulse {
      0%   { opacity: 0.6; }
      100% { opacity: 1; }
    }
    .container {
      position: relative; z-index: 1;
      max-width: 1400px; margin: 0 auto; padding: 40px 24px 80px;
    }
    .hero { text-align: center; margin-bottom: 48px; }
    .hero h1 {
      font-size: 2.8rem; font-weight: 900;
      background: var(--gradient-hero);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.15;
    }
    .hero .subtitle { font-size: 1.1rem; color: var(--text-secondary); margin-top: 8px; }
    .hero .timestamp { font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; }
    .metrics-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px; margin-bottom: 40px;
    }
    .metric-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px; text-align: center;
      backdrop-filter: blur(12px);
      position: relative; overflow: hidden;
      transition: all 0.35s cubic-bezier(0.4,0,0.2,1);
    }
    .metric-card::before {
      content: '';
      position: absolute; top: 0; left: 0; right: 0;
      height: 3px;
    }
    .metric-card:nth-child(1)::before { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
    .metric-card:nth-child(2)::before { background: linear-gradient(135deg, #10b981, #34d399); }
    .metric-card:nth-child(3)::before { background: linear-gradient(135deg, #f59e0b, #fbbf24); }
    .metric-card:nth-child(4)::before { background: linear-gradient(135deg, #f43f5e, #fb7185); }
    .metric-card:nth-child(5)::before { background: linear-gradient(135deg, #06b6d4, #22d3ee); }
    .metric-card:nth-child(6)::before { background: linear-gradient(135deg, #a855f7, #c084fc); }
    .metric-card:hover {
      transform: translateY(-4px);
      border-color: rgba(99,102,241,0.35);
      box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
    }
    .metric-value {
      font-size: 2.4rem; font-weight: 800; line-height: 1;
      font-family: 'JetBrains Mono', monospace;
    }
    .metric-card:nth-child(1) .metric-value { color: var(--accent-indigo); }
    .metric-card:nth-child(2) .metric-value { color: var(--accent-emerald); }
    .metric-card:nth-child(3) .metric-value { color: var(--accent-amber); }
    .metric-card:nth-child(4) .metric-value { color: var(--accent-rose); }
    .metric-card:nth-child(5) .metric-value { color: var(--accent-cyan); }
    .metric-card:nth-child(6) .metric-value { color: var(--accent-violet); }
    .metric-label {
      font-size: 0.7rem; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
      margin-top: 6px;
    }
    .section-title {
      font-size: 1.3rem; font-weight: 700; margin-bottom: 20px;
      display: flex; align-items: center; gap: 10px;
    }
    .chart-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px; margin-bottom: 40px;
    }
    @media (max-width: 900px) {
      .chart-grid { grid-template-columns: 1fr; }
    }
    .chart-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      backdrop-filter: blur(12px);
    }
    .chart-card h3 { margin-bottom: 16px; font-size: 1rem; color: var(--text-secondary); }
    .chart-card canvas { max-height: 350px; }
    .runs-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    .runs-table th {
      text-align: left; padding: 10px 12px;
      color: var(--text-muted);
      font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px;
      border-bottom: 1px solid var(--border);
    }
    .runs-table td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(99,102,241,0.08);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
    }
    .runs-table tr:hover td { background: rgba(99,102,241,0.04); }
    .up-arrow { color: var(--accent-emerald); }
    .empty-state {
      text-align: center; padding: 60px 20px;
      color: var(--text-muted);
    }
    .empty-state h3 { font-size: 1.4rem; margin-bottom: 8px; color: var(--text-secondary); }
    .empty-state p { font-size: 0.9rem; line-height: 1.6; }
    .empty-state .code { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
    .footer {
      text-align: center; margin-top: 60px; padding-top: 24px;
      border-top: 1px solid var(--border);
      color: var(--text-muted); font-size: 0.8rem;
    }
  </style>
</head>
<body>
  <div class="container">

    <header class="hero">
      <h1>ForgeAI — Acceptance Rate Dashboard</h1>
      <p class="subtitle">12-Week Self-Improvement Tracking · Powered by MIT SEAL Architecture</p>
      <p class="timestamp">Generated: {GENERATED_AT}</p>
    </header>

    <section class="metrics-row">
      <div class="metric-card">
        <div class="metric-value">{OVERALL_RATE}%</div>
        <div class="metric-label">Acceptance Rate (All Time)</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{TOTAL_ACCEPTS}</div>
        <div class="metric-label">Total Accepts</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{TOTAL_SIGNALS}</div>
        <div class="metric-label">Total Signals</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{TOTAL_SESSIONS}</div>
        <div class="metric-label">Sessions</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{UNIQUE_DEVELOPERS}</div>
        <div class="metric-label">Developers</div>
      </div>
      <div class="metric-card">
        <div class="metric-value">{TRAINING_RUNS_COUNT}</div>
        <div class="metric-label">Training Runs</div>
      </div>
    </section>

    <section class="chart-grid">
      <div class="chart-card">
        <h3>📈 Acceptance Rate — 12 Weeks (Daily + 7-Day Rolling Avg)</h3>
        <canvas id="acceptanceRateChart"></canvas>
      </div>
      <div class="chart-card">
        <h3>🧩 Signal Type Breakdown</h3>
        <canvas id="signalBreakdownChart"></canvas>
      </div>
    </section>

    <section class="chart-grid">
      <div class="chart-card">
        <h3>🌐 Signals by Language</h3>
        <canvas id="languageChart"></canvas>
      </div>
      <div class="chart-card">
        <h3>📊 Acceptance vs Rejects (Daily)</h3>
        <canvas id="acceptRejectChart"></canvas>
      </div>
    </section>

    <section class="chart-card" style="margin-bottom: 40px;">
      <h3>🏋️ Training Run History</h3>
      {TRAINING_RUNS_TABLE}
    </section>

    {EMPTY_STATE}

    <footer class="footer">
      <p>ForgeAI Acceptance Rate Dashboard — Powered by MIT SEAL Architecture</p>
      <p style="margin-top: 4px;">Data stored locally at ~/.forgeai/signals.db · Encrypted at rest</p>
    </footer>
  </div>

  <script>
    const rateCtx = document.getElementById('acceptanceRateChart').getContext('2d');
    new Chart(rateCtx, {
      type: 'line',
      data: {
        labels: {CHART_LABELS},
        datasets: [
          {
            label: 'Daily Rate (%)',
            data: {CHART_DAILY_RATES},
            borderColor: '#818cf8',
            backgroundColor: 'rgba(129, 140, 248, 0.08)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: '#818cf8',
          },
          {
            label: '7-Day Avg (%)',
            data: {CHART_ROLLING_AVG},
            borderColor: '#34d399',
            borderDash: [6, 3],
            fill: false,
            tension: 0.4,
            pointRadius: 2,
            pointHoverRadius: 5,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { labels: { color: '#94a3b8', usePointStyle: true } },
          tooltip: { mode: 'index', intersect: false }
        },
        scales: {
          x: { ticks: { color: '#64748b', maxTicksLimit: 14 }, grid: { color: 'rgba(99,102,241,0.06)' } },
          y: {
            beginAtZero: true,
            max: 100,
            ticks: { color: '#64748b', callback: v => v + '%' },
            grid: { color: 'rgba(99,102,241,0.06)' }
          }
        }
      }
    });

    const sigCtx = document.getElementById('signalBreakdownChart').getContext('2d');
    new Chart(sigCtx, {
      type: 'doughnut',
      data: {
        labels: {SIGNAL_LABELS},
        datasets: [{
          data: {SIGNAL_VALUES},
          backgroundColor: ['#34d399', '#fb7185', '#fbbf24', '#818cf8', '#22d3ee', '#a78bfa'],
          borderWidth: 0,
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 12 } },
        }
      }
    });

    const langCtx = document.getElementById('languageChart').getContext('2d');
    new Chart(langCtx, {
      type: 'bar',
      data: {
        labels: {LANG_LABELS},
        datasets: [{
          label: 'Signals',
          data: {LANG_VALUES},
          backgroundColor: [
            'rgba(129, 140, 248, 0.7)', 'rgba(52, 211, 153, 0.7)',
            'rgba(251, 191, 36, 0.7)', 'rgba(251, 113, 133, 0.7)',
            'rgba(34, 211, 238, 0.7)', 'rgba(167, 139, 250, 0.7)',
            'rgba(96, 165, 250, 0.7)', 'rgba(244, 63, 94, 0.7)',
            'rgba(52, 211, 153, 0.5)', 'rgba(148, 163, 184, 0.5)',
          ],
          borderRadius: 6,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#64748b' }, grid: { color: 'rgba(99,102,241,0.06)' } },
          y: { ticks: { color: '#94a3b8' }, grid: { display: false } }
        }
      }
    });

    const arCtx = document.getElementById('acceptRejectChart').getContext('2d');
    new Chart(arCtx, {
      type: 'bar',
      data: {
        labels: {CHART_LABELS},
        datasets: [
          {
            label: 'Accepts',
            data: {CHART_ACCEPTS},
            backgroundColor: 'rgba(52, 211, 153, 0.6)',
            borderRadius: 4,
          },
          {
            label: 'Rejects',
            data: {CHART_REJECTS},
            backgroundColor: 'rgba(251, 113, 133, 0.6)',
            borderRadius: 4,
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { labels: { color: '#94a3b8', usePointStyle: true } },
        },
        scales: {
          x: { ticks: { color: '#64748b', maxTicksLimit: 10 }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: '#64748b' }, grid: { color: 'rgba(99,102,241,0.06)' } }
        }
      }
    });
  </script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAI Acceptance Rate Dashboard Generator")
    parser.add_argument("--output", "-o", default="forge_dashboard.html",
                        help="Output HTML file path")
    parser.add_argument("--weeks", "-w", type=int, default=12,
                        help="Number of weeks to display (default: 12)")
    parser.add_argument("--demo", action="store_true",
                        help="Generate with synthetic demo data")
    parser.add_argument("--open", action="store_true",
                        help="Open dashboard in browser after generating")

    args = parser.parse_args()

    html = generate_dashboard(
        output_path=args.output,
        weeks=args.weeks,
        demo=args.demo,
    )

    if args.open:
        import webbrowser
        path = Path(args.output).resolve()
        webbrowser.open(path.as_uri())
        print(f"[ForgeAI] Opened dashboard: {path.as_uri()}")
