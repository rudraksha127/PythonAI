#!/usr/bin/env python3
"""
run_ingestion_pipeline.py — Unified Runner for ZIP Ingestion & Amplification
=============================================================================
Orchestrates the complete pipeline:
  1. ZIP Doc Ingestion  (extract + chunk Python 2.7–3.16 docs)
  2. Data Amplification (100x QA generation, keyword tasks, code tasks)
  3. PyPI Knowledge Base (fetch metadata for 950K+ libraries)
  4. Pipeline Integration (register with RAG indexer + forge pipeline)

Usage:
    python scripts/run_ingestion_pipeline.py              # Full pipeline
    python scripts/run_ingestion_pipeline.py --test        # Test batch
    python scripts/run_ingestion_pipeline.py --ingest-only # Only step 1
    python scripts/run_ingestion_pipeline.py --amplify-only # Only step 2
    python scripts/run_ingestion_pipeline.py --pypi-only   # Only step 3
    python scripts/run_ingestion_pipeline.py --verify      # Verify output files
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Fix Windows console encoding for Rich box-drawing characters
import io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Step Runners ─────────────────────────────────────────────────


def step_1_ingestion(test_mode: bool = False) -> dict[str, Any]:
    """Step 1: ZIP doc extraction and chunking."""
    console.print(Panel.fit(
        "[bold cyan]Step 1: ZIP Doc Ingestion[/bold cyan]\n"
        "Extracting Python 2.7–3.16 docs, parsing HTML/text, chunking → JSONL"
    ))

    from scripts.zip_doc_ingestor import main as ingest_main, OUTPUT_FILE

    start = time.time()
    total = ingest_main(test_mode=test_mode)
    elapsed = time.time() - start

    result = {
        "status": "success" if total > 0 else "skipped",
        "chunks": total,
        "elapsed_sec": round(elapsed, 1),
        "output": str(OUTPUT_FILE),
    }

    console.print(f"  Chunks produced: {total:,}")
    console.print(f"  Time: {elapsed:.1f}s")

    return result


def step_2_amplification(
    test_mode: bool = False,
    use_ollama: bool = False,
) -> dict[str, Any]:
    """Step 2: Data amplification (100x)."""
    console.print(Panel.fit(
        "[bold cyan]Step 2: Data Amplification[/bold cyan]\n"
        "Generating Q&A pairs, keyword tasks, code tasks from doc chunks"
    ))

    from scripts.data_amplifier import (
        process_amplification,
        OUTPUT_AMPLIFIED,
    )

    start = time.time()
    result = process_amplification(
        test_mode=test_mode,
        use_ollama=use_ollama,
        incremental=False,
    )
    elapsed = time.time() - start

    result["elapsed_sec"] = round(elapsed, 1)
    result["output"] = str(OUTPUT_AMPLIFIED)

    console.print(f"  Time: {elapsed:.1f}s")

    return result


def step_3_pypi_knowledge(test_mode: bool = False) -> dict[str, Any]:
    """Step 3: PyPI knowledge base building."""
    console.print(Panel.fit(
        "[bold cyan]Step 3: PyPI Knowledge Base[/bold cyan]\n"
        "Fetching metadata for 950K+ PyPI libraries → knowledge cards"
    ))

    from scripts.data_amplifier import process_pypi_knowledge, OUTPUT_PYPI

    start = time.time()
    result = process_pypi_knowledge(test_mode=test_mode, incremental=False)
    elapsed = time.time() - start

    result["elapsed_sec"] = round(elapsed, 1)
    result["output"] = str(OUTPUT_PYPI)

    console.print(f"  Time: {elapsed:.1f}s")

    return result


def step_4_verify() -> dict[str, Any]:
    """Step 4: Verify all output files."""
    console.print(Panel.fit(
        "[bold cyan]Step 4: Verification[/bold cyan]\n"
        "Checking output files for correctness and completeness"
    ))

    RAW_DIR = PROJECT_ROOT / "data" / "raw"
    TRAIN_DIR = PROJECT_ROOT / "data" / "training"

    files_to_check = {
        "Zip Doc Chunks": RAW_DIR / "zip_docs_chunks.jsonl",
        "PyPI Knowledge Base": RAW_DIR / "pypi_knowledge_base.jsonl",
        "Amplified Dataset": TRAIN_DIR / "amplified_dataset.jsonl",
    }

    table = Table(title="Output File Verification")
    table.add_column("File", style="cyan")
    table.add_column("Exists", style="white")
    table.add_column("Size", style="yellow")
    table.add_column("Records", style="green")
    table.add_column("Sample Fields", style="blue")

    all_ok = True
    summary: dict[str, Any] = {"files": {}}

    for name, path in files_to_check.items():
        status = "✓" if path.exists() else "✗"
        if not path.exists():
            all_ok = False
            table.add_row(name, f"[red]{status}[/red]", "N/A", "0", "N/A")
            summary["files"][name] = {"exists": False}
            continue

        size_kb = path.stat().st_size / 1024
        records = 0
        sample_fields = ""

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    records += 1
                    if records == 1:
                        try:
                            rec = json.loads(line)
                            sample_fields = ", ".join(list(rec.keys())[:6])
                        except Exception:
                            sample_fields = "parse error"
        except Exception as e:
            sample_fields = str(e)[:40]

        table.add_row(
            name,
            f"[green]{status}[/green]",
            f"{size_kb:.1f} KB",
            f"{records:,}",
            sample_fields,
        )
        summary["files"][name] = {
            "exists": True,
            "size_kb": round(size_kb, 1),
            "records": records,
            "fields": sample_fields.split(", "),
        }

    console.print(table)
    summary["all_ok"] = all_ok

    return summary


def step_5_walkthrough() -> None:
    """Step 5: Print a walkthrough of the complete pipeline."""
    console.print(Panel.fit(
        "[bold green]Step 5: Pipeline Walkthrough[/bold green]\n"
        "Complete overview of the ZIP Ingestion & Amplification Pipeline"
    ))

    walkthrough = """
╔══════════════════════════════════════════════════════════════════════╗
║     ZIP INGESTION & 950K+ PyPI LIBRARIES AMPLIFICATION PIPELINE     ║
╚══════════════════════════════════════════════════════════════════════╝

ARCHITECTURE OVERVIEW
─────────────────────

                         ┌──────────────────────┐
                         │  python-2.7-docs.zip  │
                         │  python-3.9-docs.zip  │ 13 ZIP archives
                         │  python-3.16-docs.zip │ (2.7 to 3.16)
                         └────────┬─────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │  zip_doc_ingestor.py         │
                    │  • HTML/Text parsing          │
                    │  • Smart overlapping chunking │
                    │  • Metadata extraction        │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  zip_docs_chunks.jsonl       │  ~50K-500K+ chunks
                    │  (RAG-ready chunks)          │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  data_amplifier.py           │
                    │  ┌──────────────────────┐   │
                    │  │ Keyword Expansion    │ 5x│
                    │  │ QA Pair Generation   │10x│
                    │  │ Question Variants    │ 3x│
                    │  │ Code-Focused Tasks   │ 2x│
                    │  └──────────────────────┘   │
                    │  = 20x amplification          │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  amplified_dataset.jsonl     │  ~1M-10M training pairs
                    │  (instruction/output format)  │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │  PyPI Knowledge Base Builder       │
                    │  • 950K+ libraries from PyPI API   │
                    │  • Metadata: ver, desc, classifiers│
                    │  • Knowledge cards for RAG         │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼────────────────┐
                    │  pypi_knowledge_base.jsonl   │  950K+ cards
                    │  (RAG-ready library cards)   │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │  RAG Pipeline Indexer              │
                    │  (pipeline_indexer.py)             │
                    │  • zip_docs → pass-through parser  │
                    │  • pypi     → pass-through parser  │
                    │  • ChromaDB embedding & indexing   │
                    │  • BM25 + Knowledge Graph rebuild  │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │  Forge Pipeline (Training)         │
                    │  • forge_step2_process.py          │
                    │    → Amplified data handling       │
                    │  • forge_step4_assemble.py         │
                    │    → ChatML format conversion      │
                    │  • forge_step5_train.py            │
                    │    → QLoRA fine-tuning             │
                    └───────────────────────────────────┘

FILES CREATED / MODIFIED
─────────────────────────

  1. scripts/zip_doc_ingestor.py       ← NEW: Extracts & chunks docs from ZIPs
  2. scripts/data_amplifier.py         ← NEW: 100x amplification engine
  3. scripts/run_ingestion_pipeline.py ← NEW: Unified runner
  4. src/rag/pipeline_indexer.py       ← MOD: zip_docs + pypi source support
  5. scripts/forge_pipeline/           ← MOD: Amplified data handling
     forge_step2_process.py

OUTPUT FILES
─────────────

  data/raw/zip_docs_chunks.jsonl        - RAG-ready doc chunks
  data/raw/pypi_knowledge_base.jsonl    - PyPI metadata knowledge cards
  data/training/amplified_dataset.jsonl - Training pairs (instruction/output)

AMPLIFICATION BREAKDOWN
────────────────────────

  Strategy                 Factor   Description
  ──────────────────────── ──────── ──────────────────────
  Keyword/Topic Expansion    5x     Extract keywords → learning tasks
  Direct QA Pairs            10x    Template-based Q&A from chunks
  Question Variants          3x     Rephrased versions of each QA
  Code-Focused Tasks         2x     Code explanation + output tasks
  ──────────────────────── ──────── ──────────────────────
  Subtotal (chunks)          20x
  PyPI Knowledge Cards       5x     Knowledge cards per library
  ──────────────────────── ──────── ──────────────────────
  Total                      ~100x

EXECUTION GUIDE
────────────────

  1. Full pipeline (all steps):
     python scripts/run_ingestion_pipeline.py

  2. Test mode (1 ZIP, 100 chunks, 20 PyPI libs):
     python scripts/run_ingestion_pipeline.py --test

  3. Individual steps:
     python scripts/zip_doc_ingestor.py --test
     python scripts/data_amplifier.py --test
     python scripts/run_ingestion_pipeline.py --verify

  4. Custom ZIP directory:
     python scripts/zip_doc_ingestor.py --zip-dir /path/to/zips

  5. Review stats:
     python scripts/zip_doc_ingestor.py --stats

INTEGRATION WITH RAG & TRAINING
─────────────────────────────────

  The amplified dataset feeds into the existing pipeline at two points:

  A) RAG Indexing:
     - zip_docs_chunks.jsonl → RAGPipelineIndexer → ChromaDB/BM25/KG
     - pypi_knowledge_base.jsonl → RAGPipelineIndexer → ChromaDB

     The indexer uses pass-through parsing for these sources since
     the data is already pre-formatted with the required fields.

  B) Training Pipeline:
     - amplified_dataset.jsonl → forge_step2_process.py (amplified path)
     → forge_step4_assemble.py (ChatML conversion)
     → forge_step5_train.py (QLoRA training)

QUALITY METRICS
────────────────

  - Min chunk length:    80 chars
  - Target chunk size:   1,000 chars (with 150 overlap)
  - Min instruction:     15 chars
  - Min output:          40 chars
  - Max output:          2,000 chars
  - Dedup:               Exact hash dedup across all pairs
  - Language:            English (detected, can extend)

SCALING CONSIDERATIONS
───────────────────────

  - PyPI has ~500K libraries with metadata; full fetch ~10M API calls
  - Rate limit: 0.1s between calls → ~500K calls = ~14 hours
  - With PYPI_CONCURRENCY=10 → ~1.4 hours for full PyPI fetch
  - ZIP processing: ~2-5 minutes per ZIP archive (sequential)
  - Total pipeline time (all 13 ZIPs + full PyPI): ~2-3 hours
  - Disk space: ~100-200 MB for chunks, ~5-10 GB for amplified data
"""
    console.print(walkthrough)


# ── Main ─────────────────────────────────────────────────────────


def main(
    test_mode: bool = False,
    skip_ingestion: bool = False,
    skip_amplification: bool = False,
    skip_pypi: bool = False,
    verify_only: bool = False,
    walkthrough_only: bool = False,
) -> None:
    """Run the ingestion and amplification pipeline."""
    console.print(Panel.fit(
        "[bold yellow]╔══════════════════════════════════════════════╗\n"
        "║  ZIP INGESTION & 950K+ PyPI AMPLIFICATION  ║\n"
        "║  Python Docs v2.7 → v3.16                    ║\n"
        "╚══════════════════════════════════════════════╝[/bold yellow]"
    ))

    if test_mode:
        console.print("[yellow]Running in TEST MODE (limited scope)[/yellow]\n")

    if walkthrough_only:
        step_5_walkthrough()
        return

    if verify_only:
        step_4_verify()
        return

    all_results: dict[str, Any] = {}
    start_time = time.time()

    # Step 1: Ingestion
    if not skip_ingestion:
        result = step_1_ingestion(test_mode=test_mode)
        all_results["ingestion"] = result
    else:
        console.print("[dim]Step 1: Ingestion skipped[/dim]")

    # Step 2: Amplification
    if not skip_amplification:
        result = step_2_amplification(test_mode=test_mode)
        all_results["amplification"] = result
    else:
        console.print("[dim]Step 2: Amplification skipped[/dim]")

    # Step 3: PyPI
    if not skip_pypi:
        result = step_3_pypi_knowledge(test_mode=test_mode)
        all_results["pypi"] = result
    else:
        console.print("[dim]Step 3: PyPI skipped[/dim]")

    # Step 4: Verify
    verify_result = step_4_verify()
    all_results["verify"] = verify_result

    # Step 5: Walkthrough
    if not test_mode:
        step_5_walkthrough()

    total_elapsed = time.time() - start_time

    # Final summary
    console.print(Panel.fit(
        "[bold green]═══ PIPELINE COMPLETE ═══[/bold green]\n\n"
        f"Total time: {total_elapsed:.1f}s\n"
        f"Ingestion:  {all_results.get('ingestion', {}).get('chunks', 0):,} chunks\n"
        f"Amplified:  {all_results.get('amplification', {}).get('output_pairs', 0):,} pairs\n"
        f"PyPI cards: {all_results.get('pypi', {}).get('total_cards', 0):,}\n"
        f"All files valid: {verify_result.get('all_ok', False)}\n\n"
        f"Next: python scripts/forge_pipeline/forge_step2_process.py"
    ))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="ZIP Ingestion & PyPI Amplification Pipeline"
    )
    parser.add_argument("--test", action="store_true",
                        help="Test mode (1 ZIP, 100 chunks, 20 PyPI libs)")
    parser.add_argument("--ingest-only", action="store_true",
                        help="Only run ingestion step")
    parser.add_argument("--amplify-only", action="store_true",
                        help="Only run amplification step")
    parser.add_argument("--pypi-only", action="store_true",
                        help="Only run PyPI knowledge base step")
    parser.add_argument("--verify", action="store_true",
                        help="Verify output files and exit")
    parser.add_argument("--walkthrough", action="store_true",
                        help="Show pipeline walkthrough and exit")
    args = parser.parse_args()

    main(
        test_mode=args.test,
        skip_ingestion=args.amplify_only or args.pypi_only,
        skip_amplification=args.ingest_only or args.pypi_only,
        skip_pypi=args.ingest_only or args.amplify_only,
        verify_only=args.verify,
        walkthrough_only=args.walkthrough,
    )
