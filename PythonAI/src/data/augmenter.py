from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import ollama


ROOT = Path(__file__).resolve().parent.parent.parent


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def row_hash(row: dict[str, Any]) -> str:
    instruction = str(row.get("instruction", "")).strip()
    output = str(row.get("output", "")).strip()
    return hashlib.sha256(f"{instruction}\n---\n{output}".encode("utf-8")).hexdigest()


def valid_chunk(chunk: dict[str, Any]) -> bool:
    if chunk.get("type") in {"font", "image_png", "image_jpg", "image_gif", "static", "css"}:
        return False
    title = str(chunk.get("title", "")).strip().lower()
    category = str(chunk.get("category", "")).strip().lower()
    text = str(chunk.get("text", "")).strip()
    if len(text) < 250:
        return False
    if title.startswith("index") or title in {"genindex", "global module index"}:
        return False
    if category.endswith("_index") or category == "api_index":
        return False
    if "index \u2013" in title or "index -" in title:
        return False
    alpha_chars = sum(char.isalpha() for char in text)
    if alpha_chars < 160:
        return False
    return True


def build_prompt(chunk: dict[str, Any], pairs_per_chunk: int) -> str:
    title = str(chunk.get("title", "Python topic")).strip() or "Python topic"
    version = str(chunk.get("version", "")).strip()
    category = str(chunk.get("category", "general")).strip()
    text = str(chunk.get("text", "")).strip()[:1400]
    code_blocks = chunk.get("codes", []) or []
    code = str(code_blocks[0]).strip()[:500] if code_blocks else ""

    code_part = f"\nCODE CONTEXT:\n{code}" if code else ""
    plural = "objects" if pairs_per_chunk != 1 else "object"
    return f"""You create high-quality supervised fine-tuning data for a Python specialist model.

Return ONLY one valid JSON object with a "rows" array containing exactly {pairs_per_chunk} {plural}.
Each row object must have: instruction, output.

Rules:
- Ground every answer in the provided context.
- Make outputs practical, senior-engineer style, and include pitfalls or verification steps.
- Include runnable Python code when the context supports it.
- Do not mention that you are generating a dataset.

PYTHON DOC CONTEXT:
Version: {version}
Category: {category}
Title: {title}
Text:
{text}
{code_part}

JSON shape:
{{
  "rows": [
    {{"instruction": "question or task", "output": "answer"}}
  ]
}}
"""


def parse_json_rows(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []

    if isinstance(data, dict):
        rows = data.get("rows", [])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [item for item in rows if isinstance(item, dict)]


def generate_pairs(
    chunk: dict[str, Any],
    model: str,
    num_ctx: int,
    num_predict: int,
    pairs_per_chunk: int,
) -> list[dict[str, Any]]:
    response = ollama.generate(
        model=model,
        prompt=build_prompt(chunk, pairs_per_chunk),
        format="json",
        options={"temperature": 0.15, "num_ctx": num_ctx, "num_predict": num_predict},
    )
    rows: list[dict[str, Any]] = []
    raw_response = str(response.get("response", ""))
    (ROOT / "checkpoints").mkdir(exist_ok=True)
    (ROOT / "checkpoints" / "augment_last_response.txt").write_text(raw_response, encoding="utf-8")

    for item in parse_json_rows(raw_response):
        instruction = str(item.get("instruction", "")).strip()
        output = str(item.get("output", "")).strip()

        # Validate no placeholder text remains
        placeholders = ["[your", "[insert", "[add", "[provide", "[replace"]
        if any(p in instruction.lower() or p in output.lower() for p in placeholders):
            continue
        if len(instruction) < 15 or len(output) < 80:
            continue

        rows.append({
            "instruction": instruction,
            "output": output,
            "source": str(chunk.get("filepath", chunk.get("title", "ollama_qwen"))),
            "category": str(chunk.get("category", "general")),
            "version": str(chunk.get("version", "")),
            "generator": model,
        })

    return rows


def select_chunks(chunks: list[dict[str, Any]], limit: int, offset: int) -> list[dict[str, Any]]:
    valid = [chunk for chunk in chunks if isinstance(chunk, dict) and valid_chunk(chunk)]
    return valid[offset : offset + limit]


def merge_rows(
    existing: list[dict[str, Any]],
    generated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {row_hash(row) for row in merged if isinstance(row, dict)}
    for row in generated:
        digest = row_hash(row)
        if digest in seen:
            continue
        seen.add(digest)
        merged.append(row)
    return merged


def print_quality_stats(rows: list[dict[str, Any]]) -> None:
    """Print quality statistics about generated rows."""
    if not rows:
        print("No rows to analyze.")
        return

    total = len(rows)
    with_code = sum(1 for r in rows if "```" in str(r.get("output", "")))
    avg_instruction_len = sum(len(str(r.get("instruction", ""))) for r in rows) / total
    avg_output_len = sum(len(str(r.get("output", ""))) for r in rows) / total

    categories = Counter(str(r.get("category", "unknown")) for r in rows)
    top_cats = categories.most_common(5)

    print(f"\nQuality Statistics:")
    print(f"  Total rows         : {total}")
    print(f"  With code examples : {with_code} ({100 * with_code // total}%)")
    print(f"  Avg instruction len: {avg_instruction_len:.0f} chars")
    print(f"  Avg output len     : {avg_output_len:.0f} chars")

    if top_cats:
        print(f"  Top categories:")
        for cat, count in top_cats:
            print(f"    {cat}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate extra SFT pairs from local Ollama models."
    )
    parser.add_argument("--model", default="qwen2.5-coder:14b",
                        help="Ollama model to use (comma-separated for multiple)")
    parser.add_argument("--chunks", default="data/processed/cleaned_chunks.json")
    parser.add_argument("--base-dataset", default="data/training/training_dataset.json")
    parser.add_argument("--output", default="data/training/training_dataset_augmented.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--num-ctx", type=int, default=512)
    parser.add_argument("--num-predict", type=int, default=500)
    parser.add_argument("--pairs-per-chunk", type=int, default=1)
    parser.add_argument("--shuffle", action="store_true", help="Shuffle chunks before processing")
    parser.add_argument("--merge", action="store_true", help="Merge generated rows into base dataset.")
    parser.add_argument("--dry-run", action="store_true", help="Print first prompt without calling Ollama.")
    parser.add_argument("--stats", action="store_true", help="Print quality statistics after generation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Support comma-separated models for multi-model generation
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    if not models:
        raise SystemExit("No model specified.")

    chunks = load_json(ROOT / args.chunks)
    selected = select_chunks(chunks, args.limit, args.offset)

    if args.shuffle:
        random.shuffle(selected)

    if not selected:
        raise SystemExit("No valid chunks selected.")

    if args.dry_run:
        print(build_prompt(selected[0], args.pairs_per_chunk))
        return

    generated: list[dict[str, Any]] = []
    current_model_index = 0

    for index, chunk in enumerate(selected, start=1):
        # Rotate through models if multiple specified
        model = models[current_model_index % len(models)]
        current_model_index += 1

        print(f"[{index}/{len(selected)}] {chunk.get('title', 'Python topic')} [{model}]")
        rows = generate_pairs(chunk, model, args.num_ctx, args.num_predict, args.pairs_per_chunk)
        generated.extend(rows)
        print(f"  generated rows: {len(rows)}")

    if args.merge:
        base = load_json(ROOT / args.base_dataset)
        output_rows = merge_rows(base, generated)
    else:
        output_rows = generated

    save_json(ROOT / args.output, output_rows)
    print(f"Saved {len(output_rows)} rows to {args.output}")

    if args.stats:
        print_quality_stats(output_rows)


if __name__ == "__main__":
    main()
