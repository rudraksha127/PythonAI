from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import requests

from src.data.apikeys import resolve_all


# ═══════════════════════════════════════════════════════════════
# API PROVIDERS — OpenAI-compatible endpoints for QA generation
# Uses API keys from ~/.pythonai/apikeys.json or environment vars
# ═══════════════════════════════════════════════════════════════

API_PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "llama-3.3-70b-versatile"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini"},
    "deepseek": {"url": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-chat"},
    "fireworks": {"url": "https://api.fireworks.ai/inference/v1/chat/completions", "model": "accounts/fireworks/models/llama-v3p3-70b-instruct"},
    "nvidia": {"url": "https://integrate.api.nvidia.com/v1/chat/completions", "model": "meta/llama-3.1-70b-instruct"},
    "cerebras": {"url": "https://api.cerebras.ai/v1/chat/completions", "model": "llama-3.3-70b"},
    "sambanova": {"url": "https://api.sambanova.ai/v1/chat/completions", "model": "Meta-Llama-3.3-70B-Instruct"},
    "mistral": {"url": "https://api.mistral.ai/v1/chat/completions", "model": "mistral-large-latest"},
    "huggingface": {"url": "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-72B-Instruct/v1/chat/completions", "model": "Qwen/Qwen2.5-72B-Instruct"},
}


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


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract important Python keywords from documentation text.
    Used to build concise prompts for API-based QA generation.
    """
    keywords: set[str] = set()

    # Capitalized multi-word terms (e.g., "Context Manager", "List Comprehension")
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text):
        word = m.group(0)
        if 4 < len(word) < 80:
            keywords.add(word)

    # Python function names (snake_case + parenthesis)
    for m in re.finditer(r"\b([a-z][a-z_]+)\s*\(", text):
        func = m.group(1)
        if 3 < len(func) < 40 and func not in ("def", "class", "print", "len", "int", "str", "list", "dict"):
            keywords.add(func)

    # Python module/import names
    for m in re.finditer(r"(?:import|from)\s+([a-zA-Z_][\w.]*)", text):
        mod = m.group(1).split(".")[0]
        if len(mod) > 2:
            keywords.add(mod)

    # Technical identifiers (contains digits or underscores in middle)
    for m in re.finditer(r"\b([a-z]+_\d+[a-zA-Z0-9_]*)\b", text):
        keywords.add(m.group(1))

    return list(keywords)[:max_keywords]


def build_keyword_prompt(keywords: list[str], chunk: dict[str, Any], pairs_per_chunk: int) -> str:
    """Build a concise prompt using extracted keywords instead of full text."""
    title = str(chunk.get("title", "Python topic")).strip() or "Python topic"
    version = str(chunk.get("version", "")).strip()
    kw_str = ", ".join(keywords)

    plural = "objects" if pairs_per_chunk != 1 else "object"
    return f"""You create high-quality supervised fine-tuning data for a Python specialist model.

Return ONLY one valid JSON object with a "rows" array containing exactly {pairs_per_chunk} {plural}.
Each row object must have: instruction, output.

Rules:
- Ground answers in the given keywords and topic.
- Make outputs practical, senior-engineer style, and include pitfalls or verification steps.
- Include runnable Python code when relevant.
- Do not mention that you are generating a dataset.

TOPIC: {title}
VERSION: Python {version}
KEYWORDS: {kw_str}

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
        if isinstance(data, dict):
            return [item for item in data.get("rows", []) if isinstance(item, dict)]
        elif isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []
    except json.JSONDecodeError:
        pass

    # Try extracting {} block (handles dict-wrapped JSON with surrounding text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            rows = data.get("rows", [])
            if rows:
                return [item for item in rows if isinstance(item, dict)]
            # Dict had no "rows" key - don't return early, try [] fallback

    # Try extracting [] block (handles array-wrapped JSON with surrounding text)
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

    return []


def _call_api_for_qa(keywords: list[str], chunk: dict[str, Any], pairs_per_chunk: int) -> list[dict[str, Any]]:
    """Call API providers to generate QA pairs from extracted keywords."""
    keys = resolve_all()
    prompt = build_keyword_prompt(keywords, chunk, pairs_per_chunk)

    # Find active providers (only those with valid keys)
    active = [(name, cfg) for name, cfg in API_PROVIDERS.items() if name in keys and keys[name]]
    if not active:
        return []

    # Try each provider round-robin until we get a valid response
    for prov_name, prov_cfg in active:
        try:
            resp = requests.post(
                prov_cfg["url"],
                headers={
                    "Authorization": f"Bearer {keys[prov_name]}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": prov_cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.15,
                    "max_tokens": 1024,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return _parse_api_response(content, chunk, prov_name)
            elif resp.status_code == 429:
                continue  # Rate limited, try next provider
        except (requests.Timeout, requests.ConnectionError, KeyError, json.JSONDecodeError):
            continue

    return []


def _parse_api_response(content: str, chunk: dict[str, Any], provider: str) -> list[dict[str, Any]]:
    """Parse API response into QA rows with quality checks."""
    rows: list[dict[str, Any]] = []

    (ROOT / "checkpoints").mkdir(exist_ok=True)
    (ROOT / "checkpoints" / "augment_last_response.txt").write_text(content, encoding="utf-8")

    for item in parse_json_rows(content):
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
            "source": str(chunk.get("filepath", chunk.get("title", "api_qa"))),
            "category": str(chunk.get("category", "general")),
            "version": str(chunk.get("version", "")),
            "generator": f"api_{provider}",
        })

    return rows


def generate_pairs(
    chunk: dict[str, Any],
    model: str = "",
    num_ctx: int = 512,
    num_predict: int = 1024,
    pairs_per_chunk: int = 1,
) -> list[dict[str, Any]]:
    """
    Generate QA pairs from a chunk using keyword extraction + API providers.

    Instead of sending full text to a local model (old Ollama approach),
    this extracts keywords from the text and sends those to API-based
    models (Groq, OpenAI, DeepSeek, etc.) for question generation.

    Args:
        chunk: Document chunk with 'text', 'title', 'version', etc.
        model: Provider name hint (unused; auto-selects from available keys)
        num_ctx: Ignored (kept for backward-compatible signature)
        num_predict: Ignored (kept for backward-compatible signature)
        pairs_per_chunk: Number of QA pairs to generate

    Returns:
        List of QA pair dicts
    """
    text = chunk.get("text", "")
    if not text or len(text.strip()) < 50:
        return []

    # Step 1: Extract keywords from the text
    keywords = extract_keywords(text, max_keywords=8)
    if len(keywords) < 2:
        # Fallback: use title words as keywords
        title = chunk.get("title", "")
        keywords = [w for w in title.split() if len(w) > 3][:5]

    # Step 2: Call API providers with keywords-only prompt
    rows = _call_api_for_qa(keywords, chunk, pairs_per_chunk)

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
        description="Generate extra SFT pairs using API providers (keyword extraction + API generation)."
    )
    parser.add_argument("--model", default="auto",
                        help="Provider hint (auto, groq, openai, deepseek, etc.)")
    parser.add_argument("--chunks", default="data/processed/cleaned_chunks.json")
    parser.add_argument("--base-dataset", default="data/training/training_dataset.json")
    parser.add_argument("--output", default="data/training/training_dataset_augmented.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--pairs-per-chunk", type=int, default=1,
                        help="Number of QA pairs to generate per chunk")
    parser.add_argument("--shuffle", action="store_true",
                        help="Shuffle chunks before processing")
    parser.add_argument("--merge", action="store_true",
                        help="Merge generated rows into base dataset.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print first prompt without calling API.")
    parser.add_argument("--stats", action="store_true",
                        help="Print quality statistics after generation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    chunks = load_json(ROOT / args.chunks)
    selected = select_chunks(chunks, args.limit, args.offset)

    if args.shuffle:
        random.shuffle(selected)

    if not selected:
        raise SystemExit("No valid chunks selected.")

    if args.dry_run:
        # Show the keyword-based prompt that would be sent to API
        sample_chunk = selected[0]
        keywords = extract_keywords(sample_chunk.get("text", ""), max_keywords=8)
        print("=== DRY RUN: Keywords extracted from chunk ===")
        print(f"Title: {sample_chunk.get('title', 'Python topic')}")
        print(f"Keywords: {', '.join(keywords)}")
        print()
        print(build_keyword_prompt(keywords, sample_chunk, args.pairs_per_chunk))
        return

    # Resolve API keys once
    keys = resolve_all()
    active = [name for name in API_PROVIDERS if name in keys and keys[name]]
    if not active:
        print("[WARN] No API keys available! Use: python -m src.cli apikeys set <provider> <key>")
        print("  Providers: groq, openrouter, openai, deepseek, fireworks, nvidia")
        print("  Or set environment variables (GROQ_API_KEY, OPENAI_API_KEY, etc.)")
        if not args.dry_run:
            return

    print(f"\nActive API providers: {', '.join(active)}")
    print(f"Generating {args.pairs_per_chunk} pair(s) per chunk using keyword extraction + API\n")

    generated: list[dict[str, Any]] = []

    for index, chunk in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {chunk.get('title', 'Python topic')}")
        rows = generate_pairs(chunk, pairs_per_chunk=args.pairs_per_chunk)
        generated.extend(rows)
        if rows:
            print(f"  generated: {len(rows)} rows (via {rows[0].get('generator', '?')})")
        else:
            print(f"  generated: 0 rows")

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
