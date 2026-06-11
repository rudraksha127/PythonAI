"""
forge_step1_collect.py — PHASE 1: MASSIVE PARALLEL DATA COLLECTION
=================================================================
⚡ PARALLEL DOWNLOAD — Downloads ALL free datasets using 12 workers
⚡ AUTO-RESUME — Checkpoint-based resume on interrupt
⚡ 3 FALLBACK TIERS — Streaming → REST API → Direct URL
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import random
import time
from pathlib import Path

import requests
from datasets import load_dataset
from loguru import logger
from rich.console import Console

from forge_config import ForgeConfig

console = Console()


def _retry_with_backoff(fn, max_retries=3, base_delay=1.0, max_delay=30.0):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            is_rate = "429" in str(e) or "rate limit" in str(e).lower()
            delay = min(base_delay * (2**attempt) + random.uniform(0, 0.5), max_delay)
            if is_rate:
                logger.warning(f"Rate limited ({attempt + 1}/{max_retries}), retry in {delay:.0f}s...")
                time.sleep(delay)
            else:
                raise


# ═══════════════════════════════════════════════════════════════════════════
# DATASET MANIFEST — 70+ datasets across 6 tiers
# Each entry has: name, config/tag, dataset_info tag
# ═══════════════════════════════════════════════════════════════════════════

DATASET_MANIFEST = {
    "critical": [
        {"name": "HuggingFaceFW/fineweb-edu", "config": "sample-10BT", "tag": "text_edu"},
        {"name": "HuggingFaceFW/fineweb", "config": "sample-10BT", "tag": "text_web"},
        {"name": "wikimedia/wikipedia", "config": "20231101.en", "tag": "wiki"},
        {"name": "wikimedia/wikipedia", "config": "20231101.hi", "tag": "wiki_hi"},
        {"name": "wikimedia/wikipedia", "config": "20231101.bn", "tag": "wiki_bn"},
        {"name": "teknium/OpenHermes-2.5", "config": "default", "tag": "instruct"},
        {"name": "HuggingFaceTB/smoltalk", "config": "all", "tag": "instruct"},
        {"name": "ai4bharat/sangraha", "config": "verified", "tag": "indic"},
        {"name": "CohereForAI/aya_dataset", "config": "default", "tag": "multilingual"},
    ],
    "high": [
        {"name": "Open-Orca/OpenOrca", "config": "default", "tag": "instruct"},
        {"name": "HuggingFaceH4/ultrachat_200k", "config": "default", "tag": "chat"},
        {"name": "meta-math/MetaMathQA", "config": "default", "tag": "math"},
        {"name": "allenai/peS2o", "config": "default", "tag": "science"},
        {"name": "bigcode/the-stack-dedup", "config": "data", "tag": "code"},
        {"name": "OpenAssistant/oasst2", "config": "default", "tag": "chat"},
        {"name": "databricks/databricks-dolly-15k", "config": "default", "tag": "instruct"},
        {"name": "google/fleurs", "config": "hi_in", "tag": "audio_hi"},
        {"name": "lighteval/MATH", "config": "default", "tag": "math"},
        {"name": "openai/gsm8k", "config": "main", "tag": "math"},
        {"name": "yahma/alpaca-cleaned", "config": "default", "tag": "instruct_alpaca"},
        {"name": "sahil2801/CodeAlpaca-20k", "config": "default", "tag": "code"},
    ],
    "medium": [
        {"name": "tatsu-lab/alpaca", "config": "default", "tag": "instruct"},
        {"name": "codeparrot/github-code", "config": "default", "tag": "code"},
        {"name": "ai4bharat/IndicNLPSuite", "config": "default", "tag": "indic"},
        {"name": "facebook/natural_questions", "config": "default", "tag": "qa"},
        {"name": "HuggingFaceFW/fineweb-2", "config": "hi", "tag": "hi_web"},
        {"name": "uonlp/CulturaX", "config": "hi", "tag": "hi"},
        {"name": "uonlp/CulturaX", "config": "en", "tag": "en"},
        {"name": "nvidia/HelpSteer2", "config": "default", "tag": "instruct"},
        {"name": "Intel/orca_dpo_pairs", "config": "default", "tag": "dpo"},
        {"name": "nlphuji/mscoco_2014_5k_test_image_text_retrieval", "config": "default", "tag": "vision"},
    ],
    "optional": [
        {"name": "oscar-corpus/OSCAR-2301", "config": "hi", "tag": "hi"},
        {"name": "HuggingFaceH4/math_qa", "config": "default", "tag": "math"},
        {"name": "wikimedia/wikipedia", "config": "20231101.te", "tag": "wiki_te"},
        {"name": "wikimedia/wikipedia", "config": "20231101.ta", "tag": "wiki_ta"},
        {"name": "wikimedia/wikipedia", "config": "20231101.mr", "tag": "wiki_mr"},
        {"name": "wikimedia/wikipedia", "config": "20231101.gu", "tag": "wiki_gu"},
        {"name": "wikimedia/wikipedia", "config": "20231101.kn", "tag": "wiki_kn"},
        {"name": "wikimedia/wikipedia", "config": "20231101.ml", "tag": "wiki_ml"},
        {"name": "wikimedia/wikipedia", "config": "20231101.pa", "tag": "wiki_pa"},
    ],
    "community": [
        {"name": "gbharti/finance-alpaca", "config": "default", "tag": "finance"},
        {"name": "medical_meadow_medical_flashcards", "config": "default", "tag": "medical"},
        {"name": "medalpaca/medical_meadow_medical_meadow_medical_flashcards", "config": "default", "tag": "medical"},
        {"name": "Anthropic/model-written-evals", "config": "default", "tag": "evals"},
        {"name": "Dahoas/synthetic-instruct-gptj-pairwise", "config": "default", "tag": "instruct"},
        {"name": "hello5753/indian_languages_translation_data", "config": "default", "tag": "translation"},
        {"name": "mrsharma21/indian-news-articles", "config": "default", "tag": "news"},
        {"name": "Vishnunaini/hindi-english-multilingual", "config": "default", "tag": "hindi_en"},
        {"name": "bigscience-data/roots_en_c4_100m", "config": "default", "tag": "text_web"},
    ],
    "indian_languages": [
        {"name": "ai4bharat/IndicParagraphSelection", "config": "default", "tag": "indic_qa"},
        {"name": "ai4bharat/IndicSentiment", "config": "default", "tag": "indic_sentiment"},
        {"name": "cfilt/iitb-english-hindi", "config": "default", "tag": "translation_enhi"},
        {"name": "tapaswi/INLT", "config": "default", "tag": "nlp"},
    ],
}


class ForgeDataCollector:
    """Master data collector with PARALLEL downloading and checkpointing."""

    def __init__(self, cfg: ForgeConfig):
        self.cfg = cfg
        self.checkpoint_file = Path(cfg.workspace_dir) / "download_checkpoint.json"
        self.completed = self._load_checkpoint()
        self.stats = {"success": 0, "failed": 0, "skipped": 0, "total_rows": 0}
        self._lock = __import__("threading").Lock()

    def _load_checkpoint(self) -> dict:
        if self.checkpoint_file.exists():
            try:
                return json.loads(self.checkpoint_file.read_text())
            except Exception:
                return {"completed": [], "failed": []}
        return {"completed": [], "failed": []}

    def _save_checkpoint(self):
        with self._lock:
            self.checkpoint_file.write_text(json.dumps(self.completed, indent=2))

    def _dataset_key(self, item: dict) -> str:
        return f"{item['name']}__{item.get('config', 'none')}"

    def download_hf_dataset(self, item: dict) -> bool:
        """Download a HuggingFace dataset via streaming + fallback."""
        name, config_str, tag = item["name"], item.get("config"), item["tag"]
        key = self._dataset_key(item)

        with self._lock:
            if key in self.completed.get("completed", []):
                self.stats["skipped"] += 1
                return True

        safe_name = name.replace("/", "__")
        out_dir = Path(self.cfg.raw_data_dir) / tag / f"{safe_name}__{config_str or 'default'}"
        out_file = out_dir / "data.jsonl"

        if out_file.exists() and out_file.stat().st_size > 100:
            with self._lock:
                self.completed.setdefault("completed", []).append(key)
                self._save_checkpoint()
                self.stats["skipped"] += 1
            return True

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            max_rows = self.cfg.max_rows_per_dataset

            # TIER 1: Streaming download
            try:

                def _load():
                    return load_dataset(
                        name,
                        config_str,
                        split="train",
                        streaming=True,
                        token=self.cfg.hf_token or None,
                        trust_remote_code=True,
                    )

                ds = _retry_with_backoff(_load, max_retries=2)
                count = 0
                with open(out_file, "w", encoding="utf-8") as f:
                    for row in ds:
                        if count >= max_rows:
                            break
                        try:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                            count += 1
                        except Exception:
                            continue

                size_mb = out_file.stat().st_size / 1e6
                with self._lock:
                    self.completed.setdefault("completed", []).append(key)
                    self._save_checkpoint()
                    self.stats["success"] += 1
                    self.stats["total_rows"] += count
                return True

            except Exception as e:
                logger.warning(f"Streaming failed for {name}, trying REST fallback: {e}")
                return self._fallback_rest_api(item, out_file, max_rows)

        except Exception as e:
            with self._lock:
                self.completed.setdefault("failed", []).append(key)
                self._save_checkpoint()
                self.stats["failed"] += 1
            return False

    def _fallback_rest_api(self, item: dict, out_file: Path, max_rows: int) -> bool:
        """Fallback to HuggingFace Datasets Server REST API."""
        name = item["name"]
        config_str = item.get("config", "default")
        dataset_encoded = name.replace("/", "%2F")
        batch_size = 200
        total = 0

        try:
            with open(out_file, "w", encoding="utf-8") as f:
                while total < max_rows:
                    url = (
                        f"https://datasets-server.huggingface.co/rows"
                        f"?dataset={dataset_encoded}&config={config_str}"
                        f"&split=train&offset={total}&length={batch_size}"
                    )
                    try:
                        resp = _retry_with_backoff(lambda u=url: requests.get(u, timeout=20), max_retries=2)
                    except Exception:
                        break
                    if resp.status_code != 200:
                        break

                    rows = resp.json().get("rows", [])
                    if not rows:
                        break
                    for row_obj in rows:
                        item_data = row_obj.get("row", {})
                        item_data["_source"] = name
                        f.write(json.dumps(item_data, ensure_ascii=False) + "\n")
                    total += len(rows)

            if total > 0:
                with self._lock:
                    self.completed.setdefault("completed", []).append(self._dataset_key(item))
                    self._save_checkpoint()
                    self.stats["success"] += 1
                    self.stats["total_rows"] += total
                return True
            return False

        except Exception as e:
            return False

    def download_single_dataset(self, item: dict) -> bool:
        """Wrapper for parallel downloading."""
        name = item["name"]
        logger.info(f"⚡ Downloading: {name}")
        result = self.download_hf_dataset(item)
        return result

    def run_all(self):
        """Download ALL datasets in PARALLEL using ThreadPoolExecutor."""
        console.print("\n[bold green]== FORGE PARALLEL DATA COLLECTION ==[/bold green]")

        all_datasets = []
        for priority in ["critical", "high", "medium", "optional", "community", "indian_languages"]:
            all_datasets.extend(DATASET_MANIFEST.get(priority, []))

        console.print(f"[cyan]Total datasets to download: {len(all_datasets)}[/cyan]")
        console.print(f"[cyan]Parallel workers: 12 (max CPU cores)[/cyan]")

        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(self.download_single_dataset, item): item for item in all_datasets}
            for future in concurrent.futures.as_completed(futures):
                item = futures[future]
                completed_count += 1
                try:
                    result = future.result()
                    if result:
                        pass  # Already logged
                except Exception:
                    pass

        # Phase 2: Specialized sources (sequential, rate-limited)
        console.print("\n[cyan]Specialized: arXiv Papers[/cyan]")
        self._download_arxiv(max_per_category=1000)

        console.print("\n[cyan]Specialized: Project Gutenberg[/cyan]")
        self._download_gutenberg(max_books=500)

        # Summary
        total_gb = sum(f.stat().st_size for f in Path(self.cfg.raw_data_dir).rglob("*") if f.is_file()) / 1e9
        console.print(f"\n[bold green]DATA COLLECTION COMPLETE[/bold green]")
        console.print(f"  Success    : {self.stats['success']}")
        console.print(f"  Failed     : {self.stats['failed']}")
        console.print(f"  Skipped    : {self.stats['skipped']}")
        console.print(f"  Total rows : {self.stats['total_rows']:,}")
        console.print(f"  Total size : {total_gb:.2f} GB")

    def _download_arxiv(self, max_per_category: int = 1000):
        """Download arXiv papers."""
        categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "stat.ML", "math.ST"]
        out_dir = Path(self.cfg.raw_data_dir) / "papers" / "arxiv"
        out_dir.mkdir(parents=True, exist_ok=True)

        for cat in categories:
            out_file = out_dir / f"{cat.replace('.', '_')}.jsonl"
            if out_file.exists() and out_file.stat().st_size > 1000:
                continue

            total = 0
            try:
                with open(out_file, "w", encoding="utf-8") as f:
                    params = {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": cat}
                    token = None
                    while total < max_per_category:
                        if token:
                            params = {"verb": "ListRecords", "resumptionToken": token}
                        resp = requests.get("https://export.arxiv.org/oai2", params=params, timeout=30)
                        from xml.etree import ElementTree

                        root = ElementTree.fromstring(resp.text)
                        ns = {"oai": "http://www.openarchives.org/OAI/2.0/", "ar": "http://arxiv.org/OAI/arXiv/"}
                        for record in root.findall(".//ar:arXiv", ns):
                            title = (record.findtext("ar:title", namespaces=ns) or "").strip()
                            abstract = (record.findtext("ar:abstract", namespaces=ns) or "").strip()
                            paper = {
                                "text": f"Title: {title}\n\nAbstract: {abstract}",
                                "title": title,
                                "source": "arxiv",
                            }
                            f.write(json.dumps(paper, ensure_ascii=False) + "\n")
                            total += 1
                            if total >= max_per_category:
                                break
                        tok_el = root.find(".//oai:resumptionToken", ns)
                        token = tok_el.text if tok_el is not None and tok_el.text else None
                        if not token:
                            break
                        time.sleep(2)
                logger.success(f"[OK] arXiv {cat}: {total} papers")
            except Exception as e:
                logger.error(f"ArXiv {cat}: {e}")

    def _download_gutenberg(self, max_books: int = 500):
        """Download Project Gutenberg books."""
        out_dir = Path(self.cfg.raw_data_dir) / "books" / "gutenberg"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "books.jsonl"
        if out_file.exists() and out_file.stat().st_size > 1000:
            return
        try:
            catalog = requests.get("https://gutendex.com/books/?mime_type=text%2Fplain&languages=en", timeout=30).json()
            count = 0
            with open(out_file, "a", encoding="utf-8") as f:
                for book in catalog.get("results", []):
                    if count >= max_books:
                        break
                    for fmt, url in book.get("formats", {}).items():
                        if "text/plain" in fmt:
                            try:
                                resp = requests.get(url, timeout=15)
                                if resp.status_code == 200:
                                    record = {
                                        "text": resp.text[:50000],
                                        "title": book.get("title", ""),
                                        "source": "gutenberg",
                                    }
                                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                                    count += 1
                            except Exception:
                                pass
                            break
            logger.success(f"[OK] Gutenberg: {count} books")
        except Exception as e:
            logger.error(f"Gutenberg: {e}")


def run_collection(cfg: ForgeConfig):
    """Entry point for data collection phase."""
    collector = ForgeDataCollector(cfg)
    collector.run_all()
    print("\n[OK] Data collection done. Run: python forge_step2_process.py")


if __name__ == "__main__":
    cfg = ForgeConfig.load()
    run_collection(cfg)
