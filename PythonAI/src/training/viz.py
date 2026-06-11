"""Enhanced training visualization module for PythonAI.

Provides professional-quality plots for monitoring training runs:
  - Train + eval loss curves with smoothing
  - Learning rate schedule visualization
  - Token throughput over time
  - Combined multi-panel dashboard figure
  - JSON metrics export for external analysis
  - HTML report generation with embedded plots
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Data container for all training metrics
# ──────────────────────────────────────────────────────────────────────


@dataclass
class TrainingMetrics:
    """Container for all metrics collected during a training run.

    The EnhancedTrainingCurvesCallback fills these fields as training
    progresses, and the visualization functions read from this object.
    """

    # Loss tracking
    train_steps: list[int] = field(default_factory=list)
    train_losses: list[float] = field(default_factory=list)
    eval_steps: list[int] = field(default_factory=list)
    eval_losses: list[float] = field(default_factory=list)

    # Learning rate tracking
    lr_steps: list[int] = field(default_factory=list)
    learning_rates: list[float] = field(default_factory=list)

    # Throughput tracking
    throughput_steps: list[int] = field(default_factory=list)
    tokens_per_second: list[float] = field(default_factory=list)

    # Metadata
    total_train_examples: int = 0
    total_eval_examples: int = 0
    max_length: int = 512
    batch_size: int = 1
    grad_accum: int = 4
    base_model: str = ""
    dataset_version: str = ""
    early_stopping_patience: int = 0
    lr_scheduler_type: str = "linear"

    def record_train_loss(self, step: int, loss: float) -> None:
        self.train_steps.append(step)
        self.train_losses.append(loss)

    def record_eval_loss(self, step: int, loss: float) -> None:
        self.eval_steps.append(step)
        self.eval_losses.append(loss)

    def record_lr(self, step: int, lr: float) -> None:
        self.lr_steps.append(step)
        self.learning_rates.append(lr)

    def record_throughput(self, step: int, tps: float) -> None:
        self.throughput_steps.append(step)
        self.tokens_per_second.append(tps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "train": {
                "steps": self.train_steps,
                "losses": [round(loss, 6) for loss in self.train_losses],
            },
            "eval": {
                "steps": self.eval_steps,
                "losses": [round(loss, 6) for loss in self.eval_losses],
            },
            "learning_rate": {
                "steps": self.lr_steps,
                "values": self.learning_rates,
            },
            "throughput": {
                "steps": self.throughput_steps,
                "tokens_per_second": [round(t, 2) for t in self.tokens_per_second],
            },
            "metadata": {
                "total_train_examples": self.total_train_examples,
                "total_eval_examples": self.total_eval_examples,
                "max_length": self.max_length,
                "batch_size": self.batch_size,
                "grad_accum": self.grad_accum,
                "base_model": self.base_model,
                "dataset_version": self.dataset_version,
                "early_stopping_patience": self.early_stopping_patience,
                "lr_scheduler_type": self.lr_scheduler_type,
            },
        }


# ──────────────────────────────────────────────────────────────────────
# Smoothing helper (simple exponential moving average)
# ──────────────────────────────────────────────────────────────────────


def smooth_curve(values: list[float], alpha: float = 0.4) -> list[float]:
    """Apply exponential smoothing to a list of values.

    Higher alpha = more smoothing.  alpha=0 means no smoothing,
    alpha=1 means all weight on the first value.
    """
    if not values or alpha <= 0.0:
        return list(values)
    smoothed: list[float] = []
    prev = values[0]
    for v in values:
        prev = prev + alpha * (v - prev)
        smoothed.append(prev)
    return smoothed


# ──────────────────────────────────────────────────────────────────────
# Plotting functions (require matplotlib)
# ──────────────────────────────────────────────────────────────────────


def _ensure_matplotlib() -> Any:
    """Import matplotlib with Agg backend (thread-safe, no display)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def plot_loss_curves(
    metrics: TrainingMetrics,
    output_path: str | Path,
    smooth_alpha: float = 0.4,
    figsize: tuple[float, float] = (10, 6),
) -> str:
    """Plot train loss (raw + smoothed) and eval loss vs steps.

    Args:
        metrics: TrainingMetrics object with collected data.
        output_path: File path to save the PNG image.
        smooth_alpha: Exponential smoothing factor (0 = no smooth).
        figsize: Figure dimensions (width, height) in inches.

    Returns:
        The absolute path to the saved PNG file.
    """
    plt = _ensure_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    # Determine if we have enough data
    has_train = len(metrics.train_steps) >= 2
    has_eval = len(metrics.eval_steps) >= 2

    if not has_train and not has_eval:
        ax.text(
            0.5, 0.5, "Not enough data for loss curves", ha="center", va="center", transform=ax.transAxes, fontsize=14
        )
        ax.set_title("Training Loss Curves")
        _save_and_close(fig, output_path)
        return str(Path(output_path).resolve())

    # Train loss (raw)
    if has_train:
        ax.plot(
            metrics.train_steps,
            metrics.train_losses,
            marker=".",
            linestyle="-",
            color="#2196F3",
            alpha=0.3,
            linewidth=1,
            markersize=4,
            label="Train (raw)",
        )

        # Train loss (smoothed)
        smoothed = smooth_curve(metrics.train_losses, alpha=smooth_alpha)
        ax.plot(
            metrics.train_steps,
            smoothed,
            linestyle="-",
            color="#1565C0",
            linewidth=2.5,
            label=f"Train (smoothed, α={smooth_alpha})",
        )

        # Annotate best (lowest) train loss
        best_idx = metrics.train_losses.index(min(metrics.train_losses))
        best_step = metrics.train_steps[best_idx]
        best_loss = metrics.train_losses[best_idx]
        ax.annotate(
            f"Best: {best_loss:.4f} @ step {best_step}",
            xy=(best_step, best_loss),
            xytext=(10, -20),
            textcoords="offset points",
            fontsize=9,
            color="#1565C0",
            arrowprops=dict(arrowstyle="->", color="#1565C0", alpha=0.7),
        )

    # Eval loss
    if has_eval:
        # Compute smoothed eval for cleaner display
        eval_smoothed = smooth_curve(metrics.eval_losses, alpha=smooth_alpha)
        ax.plot(
            metrics.eval_steps,
            eval_smoothed,
            marker="s",
            linestyle="--",
            color="#E53935",
            linewidth=2,
            markersize=5,
            label="Eval (smoothed)",
        )

        # Annotate best eval loss
        best_eval_idx = metrics.eval_losses.index(min(metrics.eval_losses))
        best_eval_step = metrics.eval_steps[best_eval_idx]
        best_eval_loss = metrics.eval_losses[best_eval_idx]
        ax.annotate(
            f"Best eval: {best_eval_loss:.4f} @ step {best_eval_step}",
            xy=(best_eval_step, best_eval_loss),
            xytext=(10, 20),
            textcoords="offset points",
            fontsize=9,
            color="#E53935",
            arrowprops=dict(arrowstyle="->", color="#E53935", alpha=0.7),
        )

    # Axis labels and grid
    ax.set_xlabel("Training Step", fontsize=12)
    ax.set_ylabel("Loss", fontsize=12)
    ax.set_title("Training & Evaluation Loss", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10, loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)

    fig.tight_layout()
    _save_and_close(fig, output_path)
    return str(Path(output_path).resolve())


def plot_lr_schedule(
    metrics: TrainingMetrics,
    output_path: str | Path,
    figsize: tuple[float, float] = (10, 4),
) -> str:
    """Plot learning rate over training steps.

    Args:
        metrics: TrainingMetrics object.
        output_path: File path to save the PNG image.
        figsize: Figure dimensions.

    Returns:
        The absolute path to the saved PNG file.
    """
    plt = _ensure_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    if len(metrics.lr_steps) < 2:
        ax.text(0.5, 0.5, "Not enough LR data", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_title("Learning Rate Schedule")
        _save_and_close(fig, output_path)
        return str(Path(output_path).resolve())

    ax.plot(
        metrics.lr_steps,
        metrics.learning_rates,
        marker=".",
        linestyle="-",
        color="#7B1FA2",
        linewidth=2,
        markersize=4,
    )

    # Fill area under curve
    ax.fill_between(
        metrics.lr_steps,
        metrics.learning_rates,
        alpha=0.15,
        color="#7B1FA2",
    )

    # Annotate scheduler type
    scheduler_label = metrics.lr_scheduler_type or "linear"
    ax.text(
        0.02,
        0.95,
        f"Scheduler: {scheduler_label}",
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    ax.set_xlabel("Training Step", fontsize=12)
    ax.set_ylabel("Learning Rate", fontsize=12)
    ax.set_title("Learning Rate Schedule", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)

    fig.tight_layout()
    _save_and_close(fig, output_path)
    return str(Path(output_path).resolve())


def plot_throughput(
    metrics: TrainingMetrics,
    output_path: str | Path,
    figsize: tuple[float, float] = (10, 4),
) -> str:
    """Plot token throughput over training steps.

    Args:
        metrics: TrainingMetrics object.
        output_path: File path to save the PNG image.
        figsize: Figure dimensions.

    Returns:
        The absolute path to the saved PNG file.
    """
    plt = _ensure_matplotlib()

    fig, ax = plt.subplots(figsize=figsize)

    if len(metrics.throughput_steps) < 2:
        ax.text(0.5, 0.5, "Not enough throughput data", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_title("Token Throughput")
        _save_and_close(fig, output_path)
        return str(Path(output_path).resolve())

    ax.bar(
        metrics.throughput_steps,
        metrics.tokens_per_second,
        width=max(1, metrics.throughput_steps[-1] // 20),
        color="#43A047",
        alpha=0.7,
        edgecolor="#2E7D32",
        linewidth=0.5,
    )

    # Average line
    avg_tps = sum(metrics.tokens_per_second) / len(metrics.tokens_per_second)
    ax.axhline(
        y=avg_tps,
        linestyle="--",
        color="#E65100",
        linewidth=1.5,
        label=f"Avg: {avg_tps:.0f} tok/s",
    )
    ax.legend(fontsize=10)

    ax.set_xlabel("Training Step", fontsize=12)
    ax.set_ylabel("Tokens / Second", fontsize=12)
    ax.set_title("Training Throughput", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)

    fig.tight_layout()
    _save_and_close(fig, output_path)
    return str(Path(output_path).resolve())


def plot_dashboard(
    metrics: TrainingMetrics,
    output_path: str | Path,
    smooth_alpha: float = 0.4,
) -> str:
    """Create a combined multi-panel dashboard figure.

    Layout:
      Row 1: Loss curves  |  Learning Rate
      Row 2: Throughput   |  Metrics summary table

    Args:
        metrics: TrainingMetrics object.
        output_path: File path to save the PNG image.
        smooth_alpha: Exponential smoothing factor.

    Returns:
        The absolute path to the saved PNG file.
    """
    plt = _ensure_matplotlib()
    import matplotlib.gridspec as gridspec

    fig = plt.figure(figsize=(16, 10))
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.3)

    # ── Top-left: Loss curves ──
    ax1 = fig.add_subplot(gs[0, 0])
    _plot_loss_on_ax(ax1, metrics, smooth_alpha)

    # ── Top-right: LR schedule ──
    ax2 = fig.add_subplot(gs[0, 1])
    _plot_lr_on_ax(ax2, metrics)

    # ── Bottom-left: Throughput ──
    ax3 = fig.add_subplot(gs[1, 0])
    _plot_throughput_on_ax(ax3, metrics)

    # ── Bottom-right: Summary table ──
    ax4 = fig.add_subplot(gs[1, 1])
    _plot_summary_table(ax4, metrics)

    fig.suptitle(
        "PythonAI Training Dashboard",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Dashboard saved: {Path(output_path).resolve()}")
    return str(Path(output_path).resolve())


# ── Internal plotting helpers for dashboard ──


def _plot_loss_on_ax(ax: Any, metrics: TrainingMetrics, smooth_alpha: float) -> None:
    has_train = len(metrics.train_steps) >= 2
    has_eval = len(metrics.eval_steps) >= 2

    if not has_train and not has_eval:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Loss Curves")
        return

    if has_train:
        smoothed = smooth_curve(metrics.train_losses, alpha=smooth_alpha)
        ax.plot(metrics.train_steps, smoothed, color="#1565C0", linewidth=2, label="Train")
        # Raw marker
        ax.plot(metrics.train_steps, metrics.train_losses, ".", color="#2196F3", alpha=0.3, markersize=3)

    if has_eval:
        eval_smoothed = smooth_curve(metrics.eval_losses, alpha=smooth_alpha)
        ax.plot(metrics.eval_steps, eval_smoothed, "--", color="#E53935", linewidth=2, label="Eval")

    ax.set_title("Loss", fontweight="bold")
    ax.set_xlabel("Step")
    ax.set_ylabel("Loss")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


def _plot_lr_on_ax(ax: Any, metrics: TrainingMetrics) -> None:
    if len(metrics.lr_steps) < 2:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Learning Rate")
        return

    ax.plot(metrics.lr_steps, metrics.learning_rates, color="#7B1FA2", linewidth=2)
    ax.fill_between(metrics.lr_steps, metrics.learning_rates, alpha=0.15, color="#7B1FA2")
    ax.set_title("Learning Rate", fontweight="bold")
    ax.set_xlabel("Step")
    ax.set_ylabel("LR")
    ax.grid(True, alpha=0.3)


def _plot_throughput_on_ax(ax: Any, metrics: TrainingMetrics) -> None:
    if len(metrics.throughput_steps) < 2:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Throughput")
        return

    ax.bar(
        metrics.throughput_steps,
        metrics.tokens_per_second,
        color="#43A047",
        alpha=0.7,
        width=max(1, metrics.throughput_steps[-1] // 20),
    )
    if metrics.tokens_per_second:
        avg = sum(metrics.tokens_per_second) / len(metrics.tokens_per_second)
        ax.axhline(y=avg, linestyle="--", color="#E65100", linewidth=1, label=f"Avg: {avg:.0f}")
        ax.legend(fontsize=8)
    ax.set_title("Throughput", fontweight="bold")
    ax.set_xlabel("Step")
    ax.set_ylabel("tok/s")
    ax.grid(True, alpha=0.3)


def _plot_summary_table(ax: Any, metrics: TrainingMetrics) -> None:
    """Display training config summary as a table."""
    ax.axis("off")

    # Determine best losses
    best_train = min(metrics.train_losses) if metrics.train_losses else None
    best_eval = min(metrics.eval_losses) if metrics.eval_losses else None
    last_lr = metrics.learning_rates[-1] if metrics.learning_rates else None
    avg_tps = (sum(metrics.tokens_per_second) / len(metrics.tokens_per_second)) if metrics.tokens_per_second else None

    rows = [
        ["Base Model", metrics.base_model or "—"],
        ["Train Examples", str(metrics.total_train_examples)],
        ["Eval Examples", str(metrics.total_eval_examples)],
        ["Max Length", str(metrics.max_length)],
        ["Batch Size", f"{metrics.batch_size} × {metrics.grad_accum} accum"],
        ["LR Scheduler", metrics.lr_scheduler_type or "linear"],
        ["Best Train Loss", f"{best_train:.4f}" if best_train is not None else "—"],
        ["Best Eval Loss", f"{best_eval:.4f}" if best_eval is not None else "—"],
        ["Last LR", f"{last_lr:.6f}" if last_lr is not None else "—"],
        ["Avg Throughput", f"{avg_tps:.0f} tok/s" if avg_tps is not None else "—"],
    ]

    table_data = [[r[0], r[1]] for r in rows]
    col_labels = ["Metric", "Value"]

    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="left",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.5)

    # Style header
    for j in range(2):
        table[0, j].set_facecolor("#37474F")
        table[0, j].set_text_props(color="white", fontweight="bold")

    # Alternating row colors
    for i in range(1, len(rows) + 1):
        color = "#F5F5F5" if i % 2 == 0 else "#FFFFFF"
        for j in range(2):
            table[i, j].set_facecolor(color)

    ax.set_title("Run Summary", fontweight="bold", pad=20)


def _save_and_close(fig: Any, output_path: str | Path) -> None:
    """Save figure and close it to free memory."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt = _ensure_matplotlib()
    plt.close(fig)
    print(f"Plot saved: {path.resolve()}")


# ──────────────────────────────────────────────────────────────────────
# JSON & HTML Export
# ──────────────────────────────────────────────────────────────────────


def export_metrics_json(
    metrics: TrainingMetrics,
    output_path: str | Path,
) -> str:
    """Export all training metrics to a JSON file.

    Args:
        metrics: TrainingMetrics object.
        output_path: File path to save the JSON file.

    Returns:
        The absolute path to the saved JSON file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = metrics.to_dict()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Metrics JSON saved: {path.resolve()}")
    return str(path.resolve())


def export_html_dashboard(
    metrics: TrainingMetrics,
    output_path: str | Path,
) -> str:
    """Generate a self-contained HTML report with metrics table and inline data.

    This creates a standalone HTML file that displays training metrics
    in a clean dashboard layout without requiring matplotlib or server.

    Args:
        metrics: TrainingMetrics object.
        output_path: File path to save the HTML file.

    Returns:
        The absolute path to the saved HTML file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = metrics.to_dict()

    # Build train loss rows for HTML table
    train_rows = ""
    for step, loss in zip(data["train"]["steps"], data["train"]["losses"]):
        train_rows += f"<tr><td>{step}</td><td>{loss}</td></tr>\n"

    eval_rows = ""
    for step, loss in zip(data["eval"]["steps"], data["eval"]["losses"]):
        eval_rows += f"<tr><td>{step}</td><td>{loss}</td></tr>\n"

    lr_rows = ""
    for step, val in zip(data["learning_rate"]["steps"], data["learning_rate"]["values"]):
        lr_rows += f"<tr><td>{step}</td><td>{val:.8f}</td></tr>\n"

    tput_rows = ""
    for step, val in zip(data["throughput"]["steps"], data["throughput"]["tokens_per_second"]):
        tput_rows += f"<tr><td>{step}</td><td>{val}</td></tr>\n"

    meta = data["metadata"]

    # Calculate best values
    best_train = min(data["train"]["losses"]) if data["train"]["losses"] else "—"
    best_eval = min(data["eval"]["losses"]) if data["eval"]["losses"] else "—"
    tput_values = data["throughput"]["tokens_per_second"]
    avg_tps = sum(tput_values) / len(tput_values) if tput_values else "—"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PythonAI Training Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f0f2f5; color: #333; padding: 24px; }}
  h1 {{ color: #1a237e; margin-bottom: 24px; font-size: 28px; }}
  h2 {{ color: #37474f; margin: 24px 0 12px; font-size: 20px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .card {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
  .card h3 {{ font-size: 14px; color: #666; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .card .value {{ font-size: 28px; font-weight: 700; color: #1a237e; }}
  .card .sub {{ font-size: 12px; color: #999; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
  th {{ background: #37474f; color: white; padding: 8px 12px; text-align: left; font-size: 13px; }}
  td {{ padding: 6px 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:nth-child(even) td {{ background: #f9f9f9; }}
  .scroll {{ max-height: 300px; overflow-y: auto; border: 1px solid #eee; border-radius: 4px; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }}
  .meta-item {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }}
  .meta-item .label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
  .meta-item .val {{ font-size: 16px; font-weight: 600; color: #333; margin-top: 4px; }}
  footer {{ margin-top: 32px; color: #999; font-size: 12px; text-align: center; }}
  .section {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
</style>
</head>
<body>

<h1>[PythonAI] Training Dashboard</h1>

<!-- Summary cards -->
<div class="grid">
  <div class="card">
    <h3>Best Train Loss</h3>
    <div class="value">{best_train}</div>
    <div class="sub">over {len(data["train"]["steps"])} logged steps</div>
  </div>
  <div class="card">
    <h3>Best Eval Loss</h3>
    <div class="value">{best_eval}</div>
    <div class="sub">over {len(data["eval"]["steps"])} logged steps</div>
  </div>
  <div class="card">
    <h3>Avg Throughput</h3>
    <div class="value">{avg_tps}</div>
    <div class="sub">tokens/second</div>
  </div>
  <div class="card">
    <h3>Total Steps</h3>
    <div class="value">{len(data["train"]["steps"])}</div>
    <div class="sub">training steps completed</div>
  </div>
</div>

<!-- Metadata -->
<div class="section">
  <h2>Configuration</h2>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Base Model</div><div class="val">{meta["base_model"] or "—"}</div></div>
    <div class="meta-item"><div class="label">Train Examples</div><div class="val">{meta["total_train_examples"]}</div></div>
    <div class="meta-item"><div class="label">Eval Examples</div><div class="val">{meta["total_eval_examples"]}</div></div>
    <div class="meta-item"><div class="label">Max Length</div><div class="val">{meta["max_length"]}</div></div>
    <div class="meta-item"><div class="label">Batch Size</div><div class="val">{meta["batch_size"]} × {meta["grad_accum"]} accum</div></div>
    <div class="meta-item"><div class="label">LR Scheduler</div><div class="val">{meta["lr_scheduler_type"] or "linear"}</div></div>
    <div class="meta-item"><div class="label">Dataset Version</div><div class="val">{meta["dataset_version"] or "—"}</div></div>
    <div class="meta-item"><div class="label">Early Stopping</div><div class="val">{"Patience: " + str(meta["early_stopping_patience"]) if meta["early_stopping_patience"] else "Disabled"}</div></div>
  </div>
</div>

<!-- Training Loss Table -->
<div class="section">
  <h2>Training Loss</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Step</th><th>Loss</th></tr></thead>
      <tbody>{train_rows or '<tr><td colspan="2">No data</td></tr>'}</tbody>
    </table>
  </div>
</div>

<!-- Eval Loss Table -->
<div class="section">
  <h2>Evaluation Loss</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Step</th><th>Loss</th></tr></thead>
      <tbody>{eval_rows or '<tr><td colspan="2">No data</td></tr>'}</tbody>
    </table>
  </div>
</div>

<!-- Learning Rate Table -->
<div class="section">
  <h2>Learning Rate</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Step</th><th>LR</th></tr></thead>
      <tbody>{lr_rows or '<tr><td colspan="2">No data</td></tr>'}</tbody>
    </table>
  </div>
</div>

<!-- Throughput Table -->
<div class="section">
  <h2>Throughput</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Step</th><th>Tokens/s</th></tr></thead>
      <tbody>{tput_rows or '<tr><td colspan="2">No data</td></tr>'}</tbody>
    </table>
  </div>
</div>

<footer>
  Generated by PythonAI Training Visualization — {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</footer>

</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    print(f"HTML dashboard saved: {path.resolve()}")
    return str(path.resolve())


# ──────────────────────────────────────────────────────────────────────
# Main entry point (for CLI usage: python -m src.training.viz)
# ──────────────────────────────────────────────────────────────────────


def load_metrics_from_json(json_path: str | Path) -> TrainingMetrics:
    """Load a TrainingMetrics object from a previously saved JSON file.

    This allows post-hoc visualization of completed training runs.

    Args:
        json_path: Path to a metrics JSON file (produced by export_metrics_json).

    Returns:
        A populated TrainingMetrics instance.
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    metrics = TrainingMetrics(
        train_steps=data["train"]["steps"],
        train_losses=data["train"]["losses"],
        eval_steps=data["eval"]["steps"],
        eval_losses=data["eval"]["losses"],
        lr_steps=data["learning_rate"]["steps"],
        learning_rates=data["learning_rate"]["values"],
        throughput_steps=data["throughput"]["steps"],
        tokens_per_second=data["throughput"]["tokens_per_second"],
        total_train_examples=data["metadata"]["total_train_examples"],
        total_eval_examples=data["metadata"]["total_eval_examples"],
        max_length=data["metadata"]["max_length"],
        batch_size=data["metadata"]["batch_size"],
        grad_accum=data["metadata"]["grad_accum"],
        base_model=data["metadata"]["base_model"],
        dataset_version=data["metadata"]["dataset_version"],
        early_stopping_patience=data["metadata"]["early_stopping_patience"],
        lr_scheduler_type=data["metadata"]["lr_scheduler_type"],
    )
    return metrics


def render_all(
    metrics: TrainingMetrics,
    output_dir: str | Path,
    smooth_alpha: float = 0.4,
    render_html: bool = True,
) -> dict[str, str]:
    """Generate all visualization outputs for a training run.

    Produces:
      - loss_curves.png        — Train + eval loss
      - lr_schedule.png        — Learning rate over steps
      - throughput.png         — Token throughput
      - dashboard.png          — Combined multi-panel figure
      - metrics.json           — Raw metrics data
      - dashboard.html         — Self-contained HTML report (optional)

    Args:
        metrics: TrainingMetrics object.
        output_dir: Directory to save all output files.
        smooth_alpha: Smoothing factor for loss curves.
        render_html: Whether to generate the HTML dashboard.

    Returns:
        Dict mapping output type to file path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    try:
        results["loss_curves"] = plot_loss_curves(metrics, out / "loss_curves.png", smooth_alpha)
    except Exception as e:
        print(f"[WARN] Failed to plot loss curves: {e}")

    try:
        results["lr_schedule"] = plot_lr_schedule(metrics, out / "lr_schedule.png")
    except Exception as e:
        print(f"[WARN] Failed to plot LR schedule: {e}")

    try:
        results["throughput"] = plot_throughput(metrics, out / "throughput.png")
    except Exception as e:
        print(f"[WARN] Failed to plot throughput: {e}")

    try:
        results["dashboard"] = plot_dashboard(metrics, out / "dashboard.png", smooth_alpha)
    except Exception as e:
        print(f"[WARN] Failed to plot dashboard: {e}")

    try:
        results["metrics_json"] = export_metrics_json(metrics, out / "metrics.json")
    except Exception as e:
        print(f"[WARN] Failed to export metrics JSON: {e}")

    if render_html:
        try:
            results["html_dashboard"] = export_html_dashboard(metrics, out / "dashboard.html")
        except Exception as e:
            print(f"[WARN] Failed to export HTML dashboard: {e}")

    return results


def parse_args() -> argparse.Namespace:  # noqa: C901
    import argparse

    parser = argparse.ArgumentParser(description="Training visualization tools for PythonAI.")
    sub = parser.add_subparsers(dest="command", required=True)

    # render subcommand
    render_parser = sub.add_parser("render", help="Render visualizations from a metrics JSON file.")
    render_parser.add_argument("--metrics-json", required=True, help="Path to metrics.json file")
    render_parser.add_argument("--output-dir", default="training_viz_output", help="Output directory")
    render_parser.add_argument("--smooth-alpha", type=float, default=0.4, help="Smoothing factor (0-1)")
    render_parser.add_argument("--no-html", action="store_true", help="Skip HTML dashboard generation")
    render_parser.set_defaults(func=_cmd_render)

    return parser.parse_args()


def _cmd_render(args: argparse.Namespace) -> None:  # noqa: C901
    metrics = load_metrics_from_json(args.metrics_json)
    results = render_all(metrics, args.output_dir, args.smooth_alpha, not args.no_html)
    print(f"\nGenerated {len(results)} visualization files:")
    for name, path in results.items():
        print(f"  [{name:15s}] {path}")


if __name__ == "__main__":
    # Minimal import for CLI mode
    import argparse  # noqa: F811

    parse_args()
