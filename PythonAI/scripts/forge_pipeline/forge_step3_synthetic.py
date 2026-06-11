"""
forge_step3_synthetic.py — PHASE 3: PARALLEL SYNTHETIC DATA GENERATION
=====================================================================
⚡ USES ALL 12 API PROVIDERS in parallel for maximum throughput
⚡ Generates: reasoning, coding, Hindi, Hinglish, India knowledge + more
⚡ Each provider gets different task types for diversity
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import sys
import time
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from loguru import logger
from rich.console import Console

from forge_config import ForgeConfig

console = Console()

# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

PROMPTS = {
    "reasoning": lambda n: (
        f"""Generate {n} complex multi-step reasoning problems.
Domains: math, logic, physics, programming, common sense.
Each requires 5-10 explicit reasoning steps.
Return a JSON array, each: {{"instruction":"...","reasoning":"...","answer":"...","domain":"..."}}.
ONLY JSON. No markdown."""
    ),
    "coding": lambda n: (
        f"""Generate {n} programming tasks with complete solutions.
Languages: Python, JavaScript, SQL, Bash (mix evenly).
Include: imports, error handling, example usage, brief explanation.
Return a JSON array, each: {{"instruction":"...","code":"...","language":"...","explanation":"..."}}.
ONLY JSON. No markdown."""
    ),
    "hindi_qa": lambda n: (
        f"""Generate {n} Q&A pairs in Hindi covering:
India GK, science, history, culture, government schemes, Ayurveda, farming.
Return a JSON array, each: {{"sawal":"...","jawab":"...","vishay":"..."}}.
ONLY JSON. Pure Hindi Devanagari. No markdown."""
    ),
    "hinglish": lambda n: (
        f"""Generate {n} helpful instruction-response pairs in Hinglish
(natural Hindi-English mix as spoken in India).
Topics: tech help, daily problems, study, jobs, government services.
Return a JSON array, each: {{"instruction":"...","response":"..."}}.
ONLY JSON. No markdown."""
    ),
    "india_knowledge": lambda n: (
        f"""Generate {n} detailed Q&A about India:
Law, government schemes (PM-KISAN, Ayushman Bharat), history, geography,
science & tech, culture, economy.
Return a JSON array, each: {{"question":"...","answer":"...","topic":"..."}}.
ONLY JSON. No markdown."""
    ),
    "science_expert": lambda n, domain=None: (
        f"""Generate {n} PhD-level Q&A in domain: {domain or "general"}.
Deep conceptual questions with detailed answers.
Return a JSON array, each: {{"question":"...","answer":"...","concepts":["..."]}}.
ONLY JSON. No markdown."""
    ),
    "chat_conversation": lambda n: (
        f"""Generate {n} natural multi-turn conversations.
Mix: technical help, creative tasks, analysis, learning.
Return a JSON array, each: {{"messages":[{{"role":"user","content":"..."}},{{"role":"assistant","content":"..."}}]}}.
ONLY JSON. No markdown."""
    ),
}

SCIENCE_DOMAINS = ["machine learning", "physics", "biology", "chemistry", "mathematics", "economics", "medicine"]


# Provider → API config (OpenAI-compatible endpoints)
PROVIDER_ENDPOINTS = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "llama3-70b-8192"},
    "cerebras": {"url": "https://api.cerebras.ai/v1/chat/completions", "model": "llama3.1-70b"},
    "sambanova": {"url": "https://api.sambanova.io/v1/chat/completions", "model": "Meta-Llama-3.1-70B-Instruct"},
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.1-70b-instruct",
    },
    "mistral": {"url": "https://api.mistral.ai/v1/chat/completions", "model": "mistral-large-latest"},
    "nvidia_llama": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "model": "meta/llama3-70b-instruct",
    },
}


class ForgeParallelSyntheticGen:
    """Generates synthetic data using ALL available API providers IN PARALLEL."""

    def __init__(self, cfg: ForgeConfig):
        self.cfg = cfg
        self.out_dir = Path(cfg.raw_data_dir) / "synthetic"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # Resolve all available providers
        from src.data.apikeys import resolve_all

        self.all_keys = resolve_all()
        self.active_providers = [p for p in PROVIDER_ENDPOINTS if p in self.all_keys]

    def call_provider(self, provider: str, prompt: str) -> list:
        """Call a single provider's API and parse JSON response."""
        if provider not in self.all_keys:
            return []
        cfg = PROVIDER_ENDPOINTS[provider]
        try:
            resp = httpx.post(
                cfg["url"],
                headers={
                    "Authorization": f"Bearer {self.all_keys[provider]}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": "Return ONLY a valid JSON array. No markdown."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.8,
                },
                timeout=60,
            )
            if resp.status_code == 429:
                logger.warning(f"  {provider}: rate limited")
                return []
            if resp.status_code != 200:
                logger.warning(f"  {provider}: HTTP {resp.status_code}")
                return []

            text = resp.json()["choices"][0]["message"]["content"]
            text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
            return []
        except Exception as e:
            return []

    def generate_for_task(self, task_type: str, n: int = 20, domain: str = None) -> list:
        """Generate synthetic data for a task using all providers in parallel."""
        prompt_fn = PROMPTS[task_type]
        if task_type == "science_expert":
            prompt = prompt_fn(n, domain=domain)
        else:
            prompt = prompt_fn(n)

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.active_providers)) as ex:
            futures = {ex.submit(self.call_provider, p, prompt): p for p in self.active_providers}
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result()
                    if data:
                        results.extend(data)
                        logger.info(f"  {futures[future]}: {len(data)} samples")
                except Exception:
                    pass
            time.sleep(0.5)  # Polite rate limiting

        return results

    def normalize_item(self, item: dict, task_type: str) -> dict | None:
        """Normalize to standard format."""
        text = ""
        if "instruction" in item and "answer" in item:
            text = f"### Instruction:\n{item['instruction']}\n\n### Response:\n{item['answer']}"
        elif "instruction" in item and "response" in item:
            text = f"### Instruction:\n{item['instruction']}\n\n### Response:\n{item['response']}"
        elif "question" in item and "answer" in item:
            text = f"Question: {item['question']}\n\nAnswer: {item['answer']}"
        elif "sawal" in item and "jawab" in item:
            text = f"सवाल: {item['sawal']}\n\nजवाब: {item['jawab']}"
        elif "messages" in item:
            msgs = item["messages"]
            text = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])
        elif "instruction" in item and "code" in item:
            text = f"Task: {item['instruction']}\n\n```{item.get('language', 'python')}\n{item['code']}\n```"
        elif "instruction" in item:
            text = f"Task: {item['instruction']}"
            if "reasoning" in item:
                text += f"\n\nReasoning:\n{item['reasoning']}"
            if "answer" in item:
                text += f"\n\nAnswer:\n{item['answer']}"
        if not text or len(text) < 50:
            return None
        return {"text": text, "source": "synthetic", "task": task_type, "domain": item.get("domain", task_type)}

    def run_all(self):
        """Generate ALL synthetic data using ALL providers in parallel."""
        console.print("\n[bold cyan]═══ PARALLEL SYNTHETIC GENERATION ═══[/bold cyan]")

        if not self.active_providers:
            console.print("[yellow]No API providers available for generation. Skipping.[/yellow]")
            return

        console.print(f"  Active providers: {len(self.active_providers)}")
        for p in self.active_providers:
            console.print(f"    ⚡ {p}: {PROVIDER_ENDPOINTS[p]['model']}")

        tasks_to_run = [
            ("reasoning", None),
            ("coding", None),
            ("hindi_qa", None),
            ("hinglish", None),
            ("india_knowledge", None),
            ("chat_conversation", None),
        ] + [("science_expert", d) for d in SCIENCE_DOMAINS]

        for task_type, domain in tasks_to_run:
            name = f"{task_type}_{domain or 'all'}"
            out_file = self.out_dir / f"{name}.jsonl"

            if out_file.exists() and out_file.stat().st_size > 1000:
                logger.info(f"SKIP: {name}")
                continue

            logger.info(f"Generating: {name} (using {len(self.active_providers)} providers)")
            data = self.generate_for_task(task_type, n=20, domain=domain)

            count = 0
            with open(out_file, "w", encoding="utf-8") as f:
                for item in data:
                    record = self.normalize_item(item, task_type)
                    if record:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        count += 1

            logger.success(f"[OK] {name}: {count} samples")


def run_synthetic_gen(cfg: ForgeConfig):
    """Entry point for synthetic data generation."""
    gen = ForgeParallelSyntheticGen(cfg)
    gen.run_all()
    print("\n[OK] Synthetic data done. Run: python forge_step4_assemble.py")


if __name__ == "__main__":
    cfg = ForgeConfig.load()
    run_synthetic_gen(cfg)
