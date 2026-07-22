"""
INDRA Synthetic Data Generator (1000x SCALE)
============================================
Multi-provider synthetic data generator for all 10 INDRA domains.
Uses MultiAgentKeyManager for massive round-robin load balancing across Groq, Together, OpenAI, etc.
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.data.apikeys import KEY_MANAGER
from src.training.indra_prompt import TRAINING_GENERATION_PROMPT

logger = logging.getLogger(__name__)


class SyntheticGenerator:
    def __init__(self, output_dir: str = "data/training/synthetic"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.key_manager = KEY_MANAGER

    def _call_provider(self, prompt: str) -> str:
        """Call any available provider dynamically using the key manager."""
        import requests

        # Try up to 3 times with different providers
        for _ in range(3):
            provider, api_key = self.key_manager.get_next_key()
            if not provider:
                time.sleep(1)
                continue

            try:
                # Basic mapping
                urls = {
                    "groq": "https://api.groq.com/openai/v1/chat/completions",
                    "together": "https://api.together.xyz/v1/chat/completions",
                    "openai": "https://api.openai.com/v1/chat/completions",
                    "anthropic": "https://api.anthropic.com/v1/messages",
                }

                models = {
                    "groq": "llama-3.3-70b-versatile",
                    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                    "openai": "gpt-4o-mini",
                }

                url = urls.get(provider)
                if not url:
                    self.key_manager.report_error(provider, api_key)
                    continue

                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

                payload = {
                    "model": models.get(provider, "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                }

                r = requests.post(url, headers=headers, json=payload, timeout=20)
                if r.status_code == 200:
                    self.key_manager.report_success(provider, api_key)
                    return r.json()["choices"][0]["message"]["content"]
                elif r.status_code == 429:
                    self.key_manager.report_rate_limit(provider, api_key)
                else:
                    self.key_manager.report_error(provider, api_key)

            except Exception:
                self.key_manager.report_error(provider, api_key)

        return ""

    def generate_batch(self, domain: str, batch_size: int = 5) -> list[dict[str, Any]]:
        """Generate a batch of synthetic data for a specific domain"""
        prompt = TRAINING_GENERATION_PROMPT.format(n=batch_size, domain=domain)

        try:
            response_text = self._call_provider(prompt)

            # Parse JSON from response
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:-3]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:-3]

            data = json.loads(clean_text.strip())
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    async def run(self, total_examples: int = 100):
        """Run highly parallel generation loop"""
        domains = ["math", "science", "engineering", "medicine", "law", "business", "arts", "language", "ai", "india"]

        generated = []
        batch_size = 5
        batches = total_examples // batch_size

        # Parallel generation with up to 100 workers across providers
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for i in range(batches):
                domain = domains[i % len(domains)]
                futures.append(executor.submit(self.generate_batch, domain, batch_size))

            pbar = tqdm(as_completed(futures), total=len(futures), desc="Generating Data")
            for future in pbar:
                batch = future.result()
                if batch:
                    generated.extend(batch)

                if len(generated) % 50 == 0:
                    self._save(generated)

        self._save(generated)
        logger.info(f"Finished generating {len(generated)} examples.")

    def _save(self, data: list[dict]):
        out_path = self.output_dir / "synthetic_dataset.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gen = SyntheticGenerator()
    asyncio.run(gen.run(500))  # Test run
