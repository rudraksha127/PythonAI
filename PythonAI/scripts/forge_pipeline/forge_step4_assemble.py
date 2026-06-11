"""
forge_step4_assemble.py — PHASE 4: TRAINING DATA ASSEMBLY
==========================================================
Combines all clean + synthetic data into final training format.
Converts to ChatML format with INDRA system prompt.
Splits into train/validation sets.
"""

from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from loguru import logger
from rich.console import Console

from forge_config import ForgeConfig

console = Console()

# INDRA System Prompt — the personality of the trained model
INDRA_SYSTEM_PROMPT = (
    "You are INDRA, a highly advanced, benevolent generalist AI designed to help humanity. "
    "You are knowledgeable, logical, and capable of operating across all domains "
    "including science, engineering, arts, medicine, law, business, and languages. "
    "You answer directly, accurately, and thoughtfully. "
    "You are fluent in English, Hindi, Hinglish, and Indian languages. "
    "You understand Indian context, culture, law, and government schemes."
)


def create_message_format(item: dict) -> dict | None:
    """Convert a processed item to ChatML format with INDRA prompt."""
    messages = [{"role": "system", "content": INDRA_SYSTEM_PROMPT}]

    if "messages" in item:
        # Already has messages format (synthetic chat data)
        for msg in item["messages"]:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                messages.append({"role": msg["role"], "content": msg["content"]})
    elif "text" in item:
        # Plain text — wrap as user/assistant
        text = item["text"]

        # Try to detect instruction/response splits
        if "### Instruction:" in text and "### Response:" in text:
            parts = text.split("### Response:")
            if len(parts) >= 2:
                instruction = parts[0].replace("### Instruction:", "").strip()
                response = parts[1].strip()
                messages.append({"role": "user", "content": instruction})
                messages.append({"role": "assistant", "content": response})
            else:
                messages.append({"role": "user", "content": "Tell me about this topic."})
                messages.append({"role": "assistant", "content": text[:2000]})
        elif "Question:" in text and "Answer:" in text:
            parts = text.split("Answer:")
            if len(parts) >= 2:
                q = parts[0].replace("Question:", "").strip()
                a = parts[1].strip()
                messages.append({"role": "user", "content": q})
                messages.append({"role": "assistant", "content": a})
            else:
                messages.append({"role": "user", "content": "Tell me about this topic."})
                messages.append({"role": "assistant", "content": text[:2000]})
        else:
            messages.append({"role": "user", "content": "Tell me about this topic."})
            messages.append({"role": "assistant", "content": text[:2000]})
    else:
        return None

    # Ensure we have at least user + assistant messages
    roles = [m["role"] for m in messages]
    if "user" not in roles or "assistant" not in roles:
        return None

    return {
        "messages": messages,
        "metadata": {
            "source": item.get("source", "unknown"),
            "domain": item.get("domain", "general"),
            "lang": item.get("lang", "en"),
        },
    }


def run_assemble(cfg: ForgeConfig):
    """Combine clean + synthetic data, convert to INDRA format, split."""
    console.print("\n[bold cyan]═══ PHASE 4: TRAINING DATA ASSEMBLY ═══[/bold cyan]")

    clean_dir = Path(cfg.clean_data_dir)
    train_dir = Path(cfg.train_data_dir)
    train_dir.mkdir(parents=True, exist_ok=True)

    clean_file = clean_dir / "all_data_clean.jsonl"
    synth_dir = Path(cfg.raw_data_dir) / "synthetic"

    all_examples = []
    sources = {"clean": 0, "synthetic": 0, "other": 0}

    # 1. Load clean processed data
    if clean_file.exists():
        with open(clean_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    all_examples.append(json.loads(line))
                    sources["clean"] += 1
                except Exception:
                    pass
        console.print(f"  Loaded {sources['clean']:,} clean records")

    # 2. Load synthetic data
    if synth_dir.exists():
        for f in synth_dir.glob("*.jsonl"):
            with open(f, "r", encoding="utf-8") as fp:
                for line in fp:
                    try:
                        all_examples.append(json.loads(line))
                        sources["synthetic"] += 1
                    except Exception:
                        pass
        console.print(f"  Loaded {sources['synthetic']:,} synthetic records")

    # 3. Also scan for existing training data files
    existing_data_dirs = [
        Path(cfg.root_dir) / "data" / "training",
        Path(cfg.root_dir) / "data" / "raw",
    ]
    for data_dir in existing_data_dirs:
        if data_dir.exists():
            for f in data_dir.glob("*.json"):
                if f.stat().st_size > 10000:
                    try:
                        data = json.loads(f.read_text())
                        if isinstance(data, list):
                            for item in data:
                                all_examples.append(item)
                                sources["other"] += 1
                            console.print(f"  Loaded {len(data):,} records from {f.name}")
                    except Exception:
                        pass

    if not all_examples:
        console.print("[red]No examples found to assemble![/red]")
        return

    console.print(f"\nTotal raw examples: {len(all_examples):,}")
    for src, count in sources.items():
        if count:
            console.print(f"  {src}: {count:,} ({count / len(all_examples) * 100:.1f}%)")

    # 4. Convert to ChatML / INDRA format
    console.print("\nConverting to INDRA training format...")
    formatted_examples = []
    for item in all_examples:
        fmt = create_message_format(item)
        if fmt:
            formatted_examples.append(fmt)

    console.print(f"  Formatted: {len(formatted_examples):,} examples")

    # 5. Shuffle and split (90/10)
    random.seed(42)
    random.shuffle(formatted_examples)

    split_idx = int(len(formatted_examples) * 0.9)
    train_data = formatted_examples[:split_idx]
    val_data = formatted_examples[split_idx:]

    # 6. Save splits
    train_path = train_dir / "train.jsonl"
    val_path = train_dir / "val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for item in val_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 7. Also save a combined version for simpler trainers
    combined_path = train_dir / "all_data.jsonl"
    with open(combined_path, "w", encoding="utf-8") as f:
        for item in formatted_examples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    console.print("\n[bold green]Assembly complete![/bold green]")
    console.print(f"  Training examples    : {len(train_data):,}")
    console.print(f"  Validation examples  : {len(val_data):,}")
    console.print(f"  Combined (all)       : {len(formatted_examples):,}")
    console.print(f"  Saved to: {train_dir}")

    return train_path, val_path


if __name__ == "__main__":
    cfg = ForgeConfig.load()
    run_assemble(cfg)
    print("\n[OK] Assembly done. Run: python forge_step5_train.py")
