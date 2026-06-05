from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.data.apikeys import ALL_PROVIDERS, resolve_all
from src.utils.swarm import AgentSwarm, TaskDecomposer


ROOT = Path(__file__).resolve().parent.parent.parent

# ═══════════════════════════════════
# API configuration
# ═══════════════════════════════════
# Keys are resolved from: stored file (~/.pythonai/apikeys.json) > env var.
# The resolve_all() function handles both; fallback is empty string.
KEYS = resolve_all()
# Ensure every known provider has at least an empty entry
for prov in ALL_PROVIDERS:
    if prov not in KEYS:
        KEYS[prov] = ""
MODELS: dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "cerebras": "llama-3.3-70b",
    "sambanova": "Meta-Llama-3.3-70B-Instruct",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "huggingface": "Qwen/Qwen2.5-72B-Instruct",
    "mistral": "mistral-large-latest",
    "openai": "gpt-4o",
    "fireworks": "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "novita": "meta-llama/llama-3.3-70b-instruct",
    "deepinfra": "meta-llama/Meta-Llama-3.3-70B-Instruct",
    "nvidia": "meta/llama-3.1-70b-instruct",
    "nvidia_llama": "meta/llama-3.1-70b-instruct",
    "nvidia_nemotron": "nvidia/nemotron-4-340b-instruct",
    "nvidia_mavarik": "meta/llama-3.1-70b-instruct",
    "nvidia_qwen": "qwen/qwen-2.5-72b-instruct",
    "nvidia_moonshot": "mistralai/mistral-large",
}

URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "sambanova": "https://api.sambanova.ai/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "huggingface": "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-72B-Instruct/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "fireworks": "https://api.fireworks.ai/inference/v1/chat/completions",
    "novita": "https://api.novita.ai/v3/openai/chat/completions",
    "deepinfra": "https://api.deepinfra.com/v1/openai/chat/completions",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nvidia_llama": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nvidia_nemotron": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nvidia_mavarik": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nvidia_qwen": "https://integrate.api.nvidia.com/v1/chat/completions",
    "nvidia_moonshot": "https://integrate.api.nvidia.com/v1/chat/completions",
}

INPUT = ROOT / "data" / "raw" / "raw_chunks.json"
OUTPUT = ROOT / "data" / "training" / "python_ultra_dataset_FINAL.json"
CKPT_DIR = ROOT / "checkpoints"
CKPT_DIR.mkdir(parents=True, exist_ok=True)

QUALITY_MIN_DEFAULT = 60
QUALITY_MIN = QUALITY_MIN_DEFAULT
SAVE_EVERY = 200

# ═══════════════════════════════════
# API state
# ═══════════════════════════════════
active: list[dict[str, Any]] = []
curr_idx = 0
calls: dict[str, int] = defaultdict(int)
fails: dict[str, int] = defaultdict(int)
rate_limited: dict[str, float] = {}
state_lock = threading.RLock()
seen_lock = threading.RLock()
task_decomposer = TaskDecomposer()
task_swarm = AgentSwarm(max_workers=4)

# ═══════════════════════════════════
# Checkpoint resume support
# ═══════════════════════════════════
CKPT_META = CKPT_DIR / "generation_meta.json"


def save_checkpoint(pairs: list[dict[str, Any]], chunk_index: int, type_stats: dict[str, int]) -> None:
    """Save a generation checkpoint that can be resumed from."""
    ckpt_path = CKPT_DIR / f"par_{chunk_index}.json"
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False)

    meta = {
        "chunk_index": chunk_index,
        "total_pairs": len(pairs),
        "type_stats": dict(type_stats),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(CKPT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return ckpt_path


def load_latest_checkpoint() -> tuple[int, list[dict[str, Any]], dict[str, int]]:
    """Load the latest checkpoint if available for resume."""
    if not CKPT_META.exists():
        return 0, [], defaultdict(int)

    meta = json.loads(CKPT_META.read_text(encoding="utf-8"))
    chunk_index = meta.get("chunk_index", 0)
    pairs: list[dict[str, Any]] = []

    # Load all checkpoint files
    for ckpt_file in sorted(CKPT_DIR.glob("par_*.json")):
        try:
            data = json.loads(ckpt_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                pairs.extend(data)
        except Exception:
            continue

    type_stats = defaultdict(int, meta.get("type_stats", {}))
    return chunk_index, pairs, type_stats


# ═══════════════════════════════════
# API helpers
# ═══════════════════════════════════
def setup() -> None:
    global active
    from src.data.apikeys import get_key as _stored_key

    print("\nInitializing APIs...")
    for name, key in KEYS.items():
        if len(key) < 10 or key.endswith("xxxx"):
            continue
        active.append({
            "name": name,
            "url": URLS[name],
            "key": key,
            "model": MODELS[name],
        })
        source = "stored" if _stored_key(name) else "env"
        print(f"  {name:12s} -> {MODELS[name]}  [{source}]")
    print(f"\n{len(active)} APIs active!")
    if not active:
        print("[WARN] No valid API keys found. Use:  python -m src.cli apikeys set <provider> <key>")
        print("       Or set environment variables (GROQ_API_KEY, etc.) and retry.")
        raise SystemExit("No valid API key found!")


def call_api(prompt: str, max_tokens: int = 800) -> tuple[str, str]:
    global curr_idx
    for _ in range(len(active)):
        with state_lock:
            p = active[curr_idx % len(active)]
            name = p["name"]
            curr_idx += 1

        with state_lock:
            if name in rate_limited:
                if time.time() < rate_limited[name]:
                    continue
                del rate_limited[name]

        try:
            import requests
            r = requests.post(
                p["url"],
                headers={
                    "Authorization": f"Bearer {p['key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": p["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": max_tokens,
                },
                timeout=25,
            )
            if r.status_code == 200:
                with state_lock:
                    calls[name] += 1
                return r.json()["choices"][0]["message"]["content"], name
            if r.status_code == 429:
                tqdm.write(f"Rate limit {name}")
                with state_lock:
                    rate_limited[name] = time.time() + 90
                time.sleep(3)
            else:
                with state_lock:
                    fails[name] += 1
        except requests.Timeout:
            tqdm.write(f"Timeout {name}")
            with state_lock:
                fails[name] += 1
        except Exception:
            with state_lock:
                fails[name] += 1
    return "[]", "none"


seen_hashes: set[str] = set()


def safe_json(text: str) -> list[dict[str, Any]]:
    try:
        s = text.find("[")
        e = text.rfind("]") + 1
        if s < 0:
            return []
        cleaned = re.sub(r",(\s*[\]}])", r"\1", text[s:e])
        return json.loads(cleaned)
    except Exception:
        return []


def dedup_filter(raw_pairs: list[dict[str, Any]], chunk: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    title = chunk.get("title", "")
    version = chunk.get("version", "")
    category = chunk.get("category", "")

    for pair in raw_pairs:
        if not isinstance(pair, dict):
            continue

        ins = str(pair.get("instruction", "")).strip()
        ans = str(pair.get("output", "")).strip()
        if len(ins) < 10 or len(ans) < 40:
            continue

        h = hashlib.md5(f"{ins}|{ans}".encode()).hexdigest()
        with seen_lock:
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

        pair["source"] = title
        pair["version"] = version
        pair["category"] = category
        out.append(pair)

    return out


def score_pair(pair: dict[str, Any]) -> tuple[int, list[str]]:
    ins = str(pair.get("instruction", ""))
    ans = str(pair.get("output", ""))
    score = 0
    reasons: list[str] = []

    if len(ins) >= 20:
        score += 20
        reasons.append("clear instruction")
    if len(ans) >= 120:
        score += 20
        reasons.append("detailed answer")
    if "```" in ans:
        score += 20
        reasons.append("code example")
    if any(token in ans.lower() for token in ("step 1", "trade-off", "because", "verify")):
        score += 20
        reasons.append("reasoning")
    if any(token in ans.lower() for token in ("pitfall", "warning", "performance", "reliability")):
        score += 10
        reasons.append("operational detail")

    return min(score, 100), reasons


# ═══════════════════════════════════
# 12 DATA TYPES → Prompts
# ═══════════════════════════════════
def build_prompts(chunk: dict[str, Any]) -> dict[str, str]:
    t = chunk.get("title", "")
    body = chunk.get("text", "")[:1200]
    codes = chunk.get("codes", [])
    code = codes[0][:250] if codes else ""
    ver = chunk.get("version", "")

    ctx = f"Python {ver} Documentation\nTopic: {t}\n{body}"
    if code:
        ctx += f"\nExample:\n{code}"

    PRE = "Return ONLY a valid JSON array. No text before or after.\n\n" + ctx + "\n\n"

    ps: dict[str, str] = {}

    ps["basic"] = PRE + (
        "Create 5 practical Q&A pairs about this topic.\n"
        '[{"type":"basic","instruction":"question?","output":"answer with code example"}]'
    )

    ps["reasoning"] = PRE + (
        f"Create 3 deep reasoning questions about {t}.\n"
        '[{"type":"reasoning","instruction":"why/how?","output":"Step 1:...\\nStep 2:...\\n```python\\ncode\\n```"}]'
    )

    ps["beginner"] = PRE + (
        f"Explain {t} for absolute beginners. Use real-life analogy.\n"
        '[{"type":"beginner","instruction":"What is ' + t + ' in simple words?",'
        '"output":"Think of it like [analogy]...\\n```python\\nsimple example\\n```"}]'
    )

    ps["expert"] = PRE + (
        f"Create 3 advanced expert-level questions about {t} covering internals and edge cases.\n"
        '[{"type":"expert","instruction":"advanced question?","output":"technical deep answer + code"}]'
    )

    ps["interview"] = PRE + (
        f"Create 4 technical interview questions about {t} with model answers.\n"
        f'[{{"type":"interview","instruction":"Interview: Explain {t}",'
        f'"output":"Answer: [clear explanation]\\nExample:\\n```python\\ncode\\n```"}}]'
    )

    ps["project"] = PRE + (
        f"Create one complete real-world mini-project using {t}.\n"
        '[{"type":"project","instruction":"Build something real with ' + t + '",'
        '"output":"Project: name\\nCode:\\n```python\\nfull working code\\n```\\nOutput: what user sees"}]'
    )

    ps["version"] = PRE + (
        f"Create 2 questions about Python {ver} specific behavior of {t}.\n"
        '[{"type":"version","instruction":"How does ' + t + ' work in Python ' + ver + '?",'
        '"output":"In Python ' + ver + ': [explanation]\\n```python\\nexample\\n```"}]'
    )

    # New prompt types
    ps["security"] = PRE + (
        f"Create 2 security-related Q&A pairs about {t}. Cover common vulnerabilities and fixes.\n"
        '[{"type":"security","instruction":"Security concern about ' + t + '?",'
        '"output":"Risk: ...\\nFix: ...\\n```python\\nsecure code\\n```"}]'
    )

    ps["performance"] = PRE + (
        f"Create 2 performance optimization Q&A pairs about {t}. Compare slow vs fast approaches.\n"
        '[{"type":"performance","instruction":"How to optimize ' + t + ' for performance?",'
        '"output":"Slow approach: ...\\nFast approach: ...\\n```python\\nbenchmark code\\n```\\nSpeedup: X%"}]'
    )

    ps["testing"] = PRE + (
        f"Create 2 testing strategy Q&A pairs about {t}. Include test examples.\n"
        '[{"type":"testing","instruction":"How to test code using ' + t + '?",'
        '"output":"Approach: ...\\n```python\\ntest code\\n```\\nEdge cases: ..."}]'
    )

    if codes:
        ps["error_fix"] = PRE + (
            f"Create 3 common bug scenarios beginners face with {t}.\n"
            '[{"type":"error_fix","instruction":"Why does this fail?\\n```python\\nbuggy code\\n```",'
            '"output":"Bug: explanation\\nFix:\\n```python\\ncorrect code\\n```\\nLesson: key takeaway"}]'
        )

        ps["code_review"] = PRE + (
            f"Create 2 code review scenarios for {t}.\n"
            '[{"type":"code_review","instruction":"Review this code:\\n```python\\nsome code\\n```",'
            '"output":"Good: ...\\nIssues: ...\\nBetter:\\n```python\\nimproved\\n```"}]'
        )

    keep = [
        "basic", "reasoning", "error_fix", "expert", "interview",
        "project", "version", "security", "performance", "testing",
    ]
    return {k: v for k, v in ps.items() if k in keep}


# ═══════════════════════════════════
# Task processing
# ═══════════════════════════════════
def process_generation_task(task: Any, chunk: dict[str, Any]) -> dict[str, Any]:
    raw, api = call_api(task.prompt)
    pairs = dedup_filter(safe_json(raw), chunk)

    good: list[dict[str, Any]] = []
    for pair in pairs:
        score, _ = score_pair(pair)
        if score >= QUALITY_MIN:
            pair["_score"] = score
            pair["_type"] = task.task_type
            pair["_api"] = api
            good.append(pair)

    if not good:
        raw2, api2 = call_api("Return ONLY valid JSON array.\n\n" + task.prompt)
        pairs2 = dedup_filter(safe_json(raw2), chunk)
        for pair in pairs2:
            score, _ = score_pair(pair)
            if score >= 50:
                pair["_score"] = score
                pair["_type"] = task.task_type
                pair["_api"] = api2
                good.append(pair)

    return {"task_type": task.task_type, "pairs": good, "api": api}


def process_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    prompts = build_prompts(chunk)
    tasks = task_decomposer.decompose(chunk, prompts)
    task_results = task_swarm.execute(tasks, lambda t: process_generation_task(t, chunk))

    results: list[dict[str, Any]] = []
    for task in tasks:
        task_result = task_results.get(task.task_id, {})
        results.extend(task_result.get("pairs", []))

    return results


# ═══════════════════════════════════
# Main
# ═══════════════════════════════════
def main(resume: bool = False, quality_min: int = QUALITY_MIN_DEFAULT) -> None:
    global QUALITY_MIN
    QUALITY_MIN = quality_min
    setup()

    with open(INPUT, encoding="utf-8") as f:
        chunks = json.load(f)

    skip = {"font", "image_png", "image_jpg", "image_gif", "static"}
    valid = [c for c in chunks if c.get("type", "") not in skip and len(c.get("text", "")) > 50]

    # Resume from checkpoint if requested
    start_index = 0
    all_pairs: list[dict[str, Any]] = []
    type_stats: dict[str, int] = defaultdict(int)

    if resume:
        start_index, all_pairs, type_stats = load_latest_checkpoint()
        seen_hashes.update(
            hashlib.md5(f'{p.get("instruction","")}|{p.get("output","")}'.encode()).hexdigest()
            for p in all_pairs if isinstance(p, dict)
        )
        if start_index > 0:
            print(f"Resuming from chunk {start_index} (already generated {len(all_pairs)} pairs)")

    print(f"\nGenerating dataset...")
    print(f"Valid chunks  : {len(valid):,}")
    print(f"Data types    : 10+")
    print(f"Workers       : 50 parallel\n")

    start = time.time()

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {
            executor.submit(process_chunk, chunk): i
            for i, chunk in enumerate(valid)
            if i >= start_index
        }
        pbar = tqdm(as_completed(futures), total=len(valid) - start_index, desc="Generating")

        for future in pbar:
            try:
                pairs = future.result(timeout=120)
                if pairs:
                    all_pairs.extend(pairs)
                    for p in pairs:
                        type_stats[p.get("_type", "?")] += 1
            except Exception:
                continue

            idx = futures[future] + 1
            if idx % SAVE_EVERY == 0:
                save_checkpoint(all_pairs, idx, type_stats)
                rate = idx / ((time.time() - start) / 60) if (time.time() - start) > 0 else 1
                eta = (len(valid) - idx) / rate if rate > 0 else 0
                pbar.set_postfix({"pairs": f"{len(all_pairs):,}", "ETA": f"{eta:.0f}m"})

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_pairs, f, indent=2, ensure_ascii=False)

    elapsed = (time.time() - start) / 60

    print(f"\n{'='*50}")
    print(f"COMPLETE!")
    print(f"Total pairs  : {len(all_pairs):,}")
    print(f"Unique       : {len(seen_hashes):,}")
    print(f"Time         : {elapsed:.0f} min")
    print(f"File         : {OUTPUT}")
    print(f"\nBy type:")
    for t, n in sorted(type_stats.items(), key=lambda x: -x[1]):
        print(f"  {t:15s}: {n:,}")
    print(f"{'='*50}")

    # Print API stats
    print(f"\nAPI Usage:")
    for name in sorted(set(list(calls.keys()) + list(fails.keys()))):
        c = calls.get(name, 0)
        f = fails.get(name, 0)
        status = "OK" if f == 0 else f"fails={f}"
        print(f"  {name:12s}: {c:4d} calls [{status}]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--quality-min", type=int, default=QUALITY_MIN_DEFAULT,
                        help="Minimum quality score to keep a pair (0-100)")
    args = parser.parse_args()
    main(resume=args.resume, quality_min=args.quality_min)
