"""
Model Comparison Dashboard

Evaluates multiple PEFT/LoRA adapters side-by-side on the same prompts
and generates a detailed comparison report (JSON + HTML).

Usage:
    python -m src.training.comparison --adapters checkpoints/local_auto_model checkpoints/full_pipeline_model
    python -m src.training.comparison --adapters checkpoints/local_auto_model --prompts prompts.json
    python -m src.training.comparison --compare-all  # Auto-discover all adapters
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROMPTS = [
    "Explain Python context managers like a senior engineer. Include one pitfall.",
    "Review this code and suggest a safer version:\n\n```python\nitems = []\nfor i in range(3):\n    items.append(lambda: i)\n```",
    "What changed between older Python import internals and modern importlib usage?",
    "How do I use asyncio to fetch multiple URLs concurrently?",
    "Write a decorator that measures function execution time.",
]


@dataclass
class AdapterResult:
    """Results from evaluating a single adapter on a prompt."""
    adapter_name: str
    prompt: str
    output: str
    generation_time_s: float
    output_length_chars: int
    output_length_tokens: int
    has_code: bool
    bleu_score: float = 0.0
    error: str | None = None


@dataclass
class ComparisonReport:
    """Complete comparison report for multiple adapters."""
    adapters: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    results: list[AdapterResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    total_adapters: int = 0
    total_prompts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_adapters": self.total_adapters,
            "total_prompts": self.total_prompts,
            "adapters": self.adapters,
            "prompts": self.prompts,
            "results": [asdict(r) for r in self.results],
        }


def load_adapter_config(adapter_path: Path) -> dict:
    config_path = adapter_path / "adapter_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing adapter config: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def discover_adapters() -> list[Path]:
    """Auto-discover all adapter directories in checkpoints/."""
    checkpoint_dir = ROOT / "checkpoints"
    if not checkpoint_dir.exists():
        return []
    adapters = []
    for d in sorted(checkpoint_dir.iterdir()):
        if d.is_dir() and (d / "adapter_config.json").exists() and (d / "adapter_model.safetensors").exists():
            adapters.append(d)
    return adapters


def compute_bleu(reference: str, candidate: str) -> float:
    """Simple 1-gram precision BLEU-like score."""
    ref_tokens = set(reference.lower().split())
    cand_tokens = candidate.lower().split()
    if not cand_tokens:
        return 0.0
    matches = sum(1 for t in cand_tokens if t in ref_tokens)
    return matches / len(cand_tokens)


def evaluate_adapter(
    adapter_path: Path,
    prompts: list[str],
    max_new_tokens: int = 96,
) -> list[AdapterResult]:
    """Evaluate a single adapter on all prompts."""
    adapter_config = load_adapter_config(adapter_path)
    base_model = adapter_config["base_model_name_or_path"]

    print(f"  Loading adapter: {adapter_path.name}")
    print(f"    Base model: {base_model}")

    tokenizer = AutoTokenizer.from_pretrained(
        adapter_path, trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model = PeftModel.from_pretrained(base, adapter_path)
    model.eval()

    results: list[AdapterResult] = []

    for prompt in prompts:
        try:
            formatted = f"### Instruction:\n{prompt}\n\n### Response:\n"
            inputs = tokenizer(
                formatted, return_tensors="pt", truncation=True, max_length=512
            )

            start = time.time()
            with torch.no_grad():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
            elapsed = time.time() - start

            text = tokenizer.decode(generated[0], skip_special_tokens=True)
            output = text[len(formatted):].strip()

            # Count tokens in output
            output_tokens = tokenizer(output, add_special_tokens=False)["input_ids"]

            results.append(AdapterResult(
                adapter_name=adapter_path.name,
                prompt=prompt[:80],
                output=output,
                generation_time_s=round(elapsed, 2),
                output_length_chars=len(output),
                output_length_tokens=len(output_tokens),
                has_code="```" in output,
            ))
            print(f"    [{adapter_path.name}] Prompt completed in {elapsed:.1f}s ({len(output_tokens)} tokens)")
        except Exception as e:
            results.append(AdapterResult(
                adapter_name=adapter_path.name,
                prompt=prompt[:80],
                output="",
                generation_time_s=0,
                output_length_chars=0,
                output_length_tokens=0,
                has_code=False,
                error=str(e),
            ))
            print(f"    [{adapter_path.name}] Error: {e}")

    return results


def generate_html_report(report: ComparisonReport, output_path: Path) -> str:
    """Generate a self-contained HTML comparison dashboard."""
    results = report.results
    adapter_names = report.adapters
    prompts = report.prompts

    # Compute per-adapter summary stats
    adapter_stats = {}
    for name in adapter_names:
        adapter_results = [r for r in results if r.adapter_name == name]
        if not adapter_results:
            continue
        avg_time = sum(r.generation_time_s for r in adapter_results) / len(adapter_results)
        avg_tokens = sum(r.output_length_tokens for r in adapter_results) / len(adapter_results)
        code_count = sum(1 for r in adapter_results if r.has_code)
        error_count = sum(1 for r in adapter_results if r.error)
        adapter_stats[name] = {
            "avg_time": f"{avg_time:.2f}s",
            "avg_tokens": f"{avg_tokens:.0f}",
            "total_chars": sum(r.output_length_chars for r in adapter_results),
            "code_count": code_count,
            "error_count": error_count,
        }

    # Build prompt-adapter matrix
    rows_html = ""
    for pi, prompt in enumerate(prompts):
        prompt_results = [r for r in results if r.prompt == prompt[:80]]
        cells = ""
        for ri, r in enumerate(prompt_results):
            output_snippet = r.output[:300].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            output_snippet = output_snippet.replace("\\n", "<br>").replace("\\n```", "<pre><code>").replace("```", "</code></pre>")
            code_badge = '<span class="badge code">Has Code</span>' if r.has_code else ''
            error_badge = f'<span class="badge error">Error</span>' if r.error else ''
            cells += f"""
            <td>
                <small class="meta">Time: {r.generation_time_s}s | Tokens: {r.output_length_tokens}</small>
                {code_badge} {error_badge}
                <div class="output">{output_snippet}</div>
            </td>"""

        rows_html += f"""
        <tr>
            <td class="prompt-cell">
                <strong>Prompt {pi + 1}</strong>
                <div class="prompt-text">{prompt[:120]}</div>
            </td>
            {cells}
        </tr>"""

    # Adapter header cells
    header_cells = ""
    for name in adapter_names:
        stats = adapter_stats.get(name, {})
        header_cells += f"""
        <th>
            <div class="adapter-name">{name}</div>
            <small>[Time] {stats.get('avg_time', 'N/A')} | [Tok] {stats.get('avg_tokens', 'N/A')} tok</small>
            <br><small>[Code] {stats.get('code_count', 0)} | [Err] {stats.get('error_count', 0)}</small>
        </th>"""

    # Summary table
    summary_rows = ""
    for name, stats in adapter_stats.items():
        summary_rows += f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{stats['avg_time']}</td>
            <td>{stats['avg_tokens']}</td>
            <td>{stats['total_chars']:,}</td>
            <td>{stats['code_count']}</td>
            <td>{stats['error_count']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Comparison Dashboard — PythonAI</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 24px; }}
h1 {{ color: #58a6ff; margin-bottom: 4px; }}
.subtitle {{ color: #8b949e; margin-bottom: 24px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
.stat-card .value {{ font-size: 1.8em; font-weight: bold; color: #58a6ff; }}
.stat-card .label {{ font-size: 0.85em; color: #8b949e; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
th, td {{ border: 1px solid #30363d; padding: 12px; text-align: left; vertical-align: top; }}
th {{ background: #161b22; color: #58a6ff; font-size: 0.85em; position: sticky; top: 0; }}
.adapter-name {{ font-weight: bold; font-size: 1.1em; color: #c9d1d9; }}
.prompt-cell {{ width: 180px; }}
.prompt-text {{ color: #8b949e; font-size: 0.85em; margin-top: 4px; }}
.meta {{ color: #8b949e; font-size: 0.75em; display: block; margin-bottom: 4px; }}
.output {{ margin-top: 6px; font-size: 0.85em; line-height: 1.4; max-height: 200px; overflow-y: auto; }}
.output pre {{ background: #000; padding: 8px; border-radius: 4px; overflow-x: auto; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7em; margin: 2px 0; }}
.badge.code {{ background: #1b4332; color: #6ee7b7; border: 1px solid #2d6a4f; }}
.badge.error {{ background: #3b1a1a; color: #ff6b6b; border: 1px solid #6b2020; }}
.section-title {{ font-size: 1.2em; color: #58a6ff; margin: 24px 0 12px; }}
tr:nth-child(even) {{ background: #111; }}
tr:hover {{ background: #1c2128; }}
</style>
</head>
<body>
<div class="container">
<h1>[ML] Model Comparison Dashboard</h1>
<p class="subtitle">Generated: {report.timestamp} | {report.total_adapters} adapters × {report.total_prompts} prompts</p>

<div class="stats-grid">
    <div class="stat-card">
        <div class="value">{report.total_adapters}</div>
        <div class="label">Adapters</div>
    </div>
    <div class="stat-card">
        <div class="value">{report.total_prompts}</div>
        <div class="label">Test Prompts</div>
    </div>
    <div class="stat-card">
        <div class="value">{len(results)}</div>
        <div class="label">Total Evaluations</div>
    </div>
    <div class="stat-card">
        <div class="value">{sum(1 for r in results if r.has_code)}</div>
        <div class="label">Code Examples</div>
    </div>
</div>            <h2 class="section-title">Adapter Summary</h2>
<table>
<thead>
<tr>
    <th>Adapter</th>
    <th>Avg Time</th>
    <th>Avg Tokens</th>
    <th>Total Chars</th>
    <th>Code Blocks</th>
    <th>Errors</th>
</tr>
</thead>
<tbody>
{summary_rows}
</tbody>
</table>            <h2 class="section-title">Side-by-Side Comparison</h2>
<table>
<thead>
<tr>
    <th>Prompt</th>
    {header_cells}
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


def run_comparison(
    adapter_paths: list[Path],
    prompts: list[str] = DEFAULT_PROMPTS,
    max_new_tokens: int = 96,
    output_dir: str = "checkpoints/comparison",
) -> ComparisonReport:
    """Run full comparison across all adapters."""
    output_path = ROOT / output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    report = ComparisonReport(
        adapters=[p.name for p in adapter_paths],
        prompts=[p[:80] for p in prompts],
    )

    for adapter_path in adapter_paths:
        print(f"\n{'='*60}")
        print(f"Evaluating: {adapter_path.name}")
        print(f"{'='*60}")
        results = evaluate_adapter(adapter_path, prompts, max_new_tokens)
        report.results.extend(results)

    report.total_adapters = len(adapter_paths)
    report.total_prompts = len(prompts)

    # Save JSON report
    json_path = output_path / "comparison_report.json"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[OK] JSON report saved: {json_path}")

    # Generate HTML dashboard
    html_path = output_path / "comparison_dashboard.html"
    generate_html_report(report, html_path)
    print(f"[OK] HTML dashboard: {html_path}")

    # Print quick summary
    print(f"\n{'='*60}")
    print("Quick Summary")
    print(f"{'='*60}")
    for name in report.adapters:
        adapter_results = [r for r in report.results if r.adapter_name == name]
        avg_time = sum(r.generation_time_s for r in adapter_results) / len(adapter_results) if adapter_results else 0
        avg_len = sum(r.output_length_tokens for r in adapter_results) / len(adapter_results) if adapter_results else 0
        errors = sum(1 for r in adapter_results if r.error)
        print(f"  {name:30s}  [Time] {avg_time:.2f}s  |  [Tok] {avg_len:.0f} tok  |  [Err] {errors}")

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare multiple PEFT adapters side-by-side")
    parser.add_argument("--adapters", nargs="+", default=None,
                        help="Paths to adapter directories (default: auto-discover all)")
    parser.add_argument("--prompts", default=None,
                        help="JSON file with list of prompt strings")
    parser.add_argument("--max-new-tokens", type=int, default=96,
                        help="Max new tokens per generation")
    parser.add_argument("--output-dir", default="checkpoints/comparison",
                        help="Output directory for reports")
    parser.add_argument("--compare-all", action="store_true",
                        help="Auto-discover and compare all adapters in checkpoints/")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine adapters to compare
    if args.compare_all or not args.adapters:
        adapter_paths = discover_adapters()
        if not adapter_paths:
            print("[WARN] No adapters found in checkpoints/")
            return
        print(f"[Discover] Found {len(adapter_paths)} adapters:")
        for p in adapter_paths:
            print(f"  - {p.name}")
    else:
        adapter_paths = [ROOT / p for p in args.adapters]
        for p in adapter_paths:
            if not p.exists():
                print(f"[ERROR] Adapter not found: {p}")
                return

    # Load custom prompts if specified
    prompts = DEFAULT_PROMPTS
    if args.prompts:
        prompts_path = ROOT / args.prompts
        if prompts_path.exists():
            prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
            if isinstance(prompts, list) and all(isinstance(p, str) for p in prompts):
                print(f"[Prompts] Loaded {len(prompts)} custom prompts from {args.prompts}")
            else:
                print("[WARN] Invalid prompts file; using defaults")
                prompts = DEFAULT_PROMPTS

    run_comparison(adapter_paths, prompts, args.max_new_tokens, args.output_dir)


if __name__ == "__main__":
    main()
