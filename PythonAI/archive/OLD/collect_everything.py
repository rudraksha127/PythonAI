"""
ANTI-GRAVITY MASTER DATA COLLECTOR
Run this and walk away. It will collect everything.

Extracted from ANTI_GRAVITY_GOD_MODE_PROMPT.md
Storage target: D:/PythonAI_Data/anti_gravity_data
"""

import asyncio
import aiohttp
import aiofiles
import hashlib
import json
import gzip
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator, Iterator
from collections import defaultdict
from dataclasses import dataclass, field
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich.live import Live
from loguru import logger

from src.data.apikeys import MultiAgentKeyManager, resolve_all

console = Console()

# ═══════════════════════════════════════════════════
# SECTION 1: TEXT DATA COLLECTORS
# ═══════════════════════════════════════════════════

class CommonCrawlCollector:
    """
    Downloads and processes Common Crawl WARC files.
    Source of 70%+ of web text training data for ALL frontier models.
    PetaBytes available free on AWS S3.
    """
    INDEX_URL = "https://index.commoncrawl.org"
    S3_BASE = "s3://commoncrawl"

    LATEST_CRAWLS = [
        "CC-MAIN-2024-51", "CC-MAIN-2024-46", "CC-MAIN-2024-42",
        "CC-MAIN-2024-38", "CC-MAIN-2024-33", "CC-MAIN-2024-30",
        "CC-MAIN-2024-26", "CC-MAIN-2024-22", "CC-MAIN-2024-18",
        "CC-MAIN-2024-10",
    ]

    def __init__(self, output_dir: str = "data/commoncrawl"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_warc_paths(self, crawl_id: str) -> list[str]:
        """Get all WARC file paths for a crawl"""
        paths_url = f"https://data.commoncrawl.org/crawl-data/{crawl_id}/warc.paths.gz"
        result = subprocess.run(
            ["curl", "-s", paths_url], capture_output=True
        )
        content = gzip.decompress(result.stdout).decode()
        return content.strip().split("\n")

    async def process_warc_segment(self, warc_path: str) -> AsyncGenerator[dict, None]:
        """Extract text content from WARC file"""
        import warcio
        from io import BytesIO

        url = f"https://data.commoncrawl.org/{warc_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.read()

        with warcio.ArchiveIterator(BytesIO(content)) as records:
            for record in records:
                if record.rec_type == 'response':
                    try:
                        content_type = record.http_headers.get_header('Content-Type', '')
                        if 'text/html' in content_type:
                            raw_html = record.content_stream().read().decode('utf-8', errors='ignore')
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(raw_html, 'lxml')
                            for tag in soup(['script', 'style', 'nav', 'footer']):
                                tag.decompose()
                            text = soup.get_text(separator=' ', strip=True)

                            if len(text) > 200:
                                yield {
                                    "text": text,
                                    "url": record.rec_headers.get_header('WARC-Target-URI'),
                                    "source": "common_crawl",
                                    "crawl": warc_path.split('/')[1],
                                    "length": len(text)
                                }
                    except Exception:
                        continue

    def download_via_s3(self, crawl_id: str, num_segments: int = 100):
        """Download segments directly via AWS CLI (faster)"""
        output = self.output_dir / crawl_id
        output.mkdir(exist_ok=True)

        paths = self.get_warc_paths(crawl_id)[:num_segments]

        for path in paths:
            local_path = output / Path(path).name
            if local_path.exists():
                continue
            cmd = f"aws s3 cp s3://commoncrawl/{path} {local_path} --no-sign-request"
            subprocess.run(cmd.split(), check=True)
            logger.info(f"Downloaded: {path}")


class ArXivMassCollector:
    """
    Collects ALL arXiv papers via OAI-PMH protocol.
    Free, no authentication needed.
    2.4M+ papers covering all scientific domains.
    """
    OAI_URL = "https://export.arxiv.org/oai2"
    PDF_URL = "https://arxiv.org/pdf"
    LATEX_URL = "https://arxiv.org/e-print"

    ALL_CATEGORIES = {
        "cs": ["cs.AI","cs.LG","cs.CL","cs.CV","cs.NE","cs.RO","cs.IR",
               "cs.DS","cs.DC","cs.SE","cs.CR","cs.HC","cs.DB","cs.NI"],
        "math": ["math.ST","math.OC","math.PR","math.NA","math.CO"],
        "physics": ["physics.data-an","cond-mat","quant-ph","hep-th"],
        "bio": ["q-bio.QM","q-bio.GN","q-bio.BM","q-bio.NC"],
        "econ": ["econ.EM","econ.GN","econ.TH"],
        "stat": ["stat.ML","stat.AP","stat.CO","stat.TH"],
        "ee": ["eess.AS","eess.IV","eess.SP","eess.SY"]
    }

    def __init__(self, output_dir: str = "data/arxiv"):
        self.output_dir = Path(output_dir)
        self.papers_dir = self.output_dir / "metadata"
        self.pdfs_dir = self.output_dir / "pdfs"
        self.latex_dir = self.output_dir / "latex"
        for d in [self.papers_dir, self.pdfs_dir, self.latex_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self._load_checkpoint()

    def _load_checkpoint(self) -> dict:
        cp = self.output_dir / "checkpoint.json"
        return json.loads(cp.read_text()) if cp.exists() else {}

    def _save_checkpoint(self, category: str, token: str):
        cp = self.output_dir / "checkpoint.json"
        self.checkpoint[category] = token
        cp.write_text(json.dumps(self.checkpoint))

    async def collect_category(self, category: str, session: aiohttp.ClientSession):
        """Collect all papers from one category"""
        import xml.etree.ElementTree as ET

        token = self.checkpoint.get(category)
        total = 0

        while True:
            params = {"verb": "ListRecords", "metadataPrefix": "arXiv"}
            if token:
                params = {"verb": "ListRecords", "resumptionToken": token}
            else:
                params["set"] = category

            async with session.get(self.OAI_URL, params=params) as resp:
                if resp.status in (429, 503):
                    logger.warning(f"Rate limited by arXiv (HTTP {resp.status}). Backing off for 15s...")
                    await asyncio.sleep(15)
                    continue
                text = await resp.text()

            root = ET.fromstring(text)
            ns = {
                "oai": "http://www.openarchives.org/OAI/2.0/",
                "ar": "http://arxiv.org/OAI/arXiv/"
            }

            papers = []
            for record in root.findall(".//ar:arXiv", ns):
                paper_id = record.findtext("ar:id", namespaces=ns)
                if not paper_id:
                    continue

                paper = {
                    "id": paper_id,
                    "title": (record.findtext("ar:title", namespaces=ns) or "").strip(),
                    "abstract": (record.findtext("ar:abstract", namespaces=ns) or "").strip(),
                    "authors": [
                        f"{a.findtext('ar:keyname',namespaces=ns)}, {a.findtext('ar:forenames',namespaces=ns)}"
                        for a in record.findall("ar:authors/ar:author", ns)
                    ],
                    "categories": (record.findtext("ar:categories", namespaces=ns) or ""),
                    "created": (record.findtext("ar:created", namespaces=ns) or ""),
                    "doi": (record.findtext("ar:doi", namespaces=ns) or ""),
                    "pdf_url": f"{self.PDF_URL}/{paper_id}v1",
                    "source": "arxiv"
                }
                papers.append(paper)
                total += 1

            if papers:
                batch_file = self.papers_dir / f"{category.replace('.','_')}_{total}.jsonl"
                async with aiofiles.open(batch_file, 'w') as f:
                    for p in papers:
                        await f.write(json.dumps(p) + "\n")

            token_el = root.find(".//oai:resumptionToken", ns)
            if token_el is None or not token_el.text:
                break
            token = token_el.text
            self._save_checkpoint(category, token)

            logger.info(f"{category}: {total} papers collected")
            await asyncio.sleep(3)  # ArXiv rate limit

        return total

    async def collect_all(self):
        """Collect ALL categories"""
        async with aiohttp.ClientSession() as session:
            for domain, cats in self.ALL_CATEGORIES.items():
                for category in cats:
                    logger.info(f"Collecting arXiv:{category}")
                    count = await self.collect_category(category, session)
                    logger.success(f"✓ {category}: {count} papers")


class OpenAlexCollector:
    """
    OpenAlex: 250M+ works. Best free academic API.
    No authentication needed for basic access.
    """
    BASE = "https://api.openalex.org"

    FILTER_TOPICS = [
        "machine learning", "artificial intelligence", "neural network",
        "natural language processing", "computer vision", "robotics",
        "quantum computing", "biotechnology", "climate change",
        "economics", "medicine", "physics", "mathematics"
    ]

    def __init__(self, email: str, output_dir: str = "data/openalex"):
        self.email = email
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def search_works(self, topic: str, session: aiohttp.ClientSession,
                            max_results: int = 10000):
        """Search and paginate through works"""
        cursor = "*"
        total = 0

        while total < max_results:
            params = {
                "search": topic,
                "filter": "open_access.is_oa:true",
                "per-page": 200,
                "cursor": cursor,
                "mailto": self.email,
                "select": "id,title,abstract_inverted_index,authorships,"
                           "cited_by_count,publication_year,doi,open_access"
            }

            async with session.get(f"{self.BASE}/works", params=params) as resp:
                if resp.status == 429:
                    logger.warning(f"Rate limited by OpenAlex (HTTP {resp.status}). Backing off for 10s...")
                    await asyncio.sleep(10)
                    continue
                data = await resp.json()

            results = data.get("results", [])
            if not results:
                break

            for work in results:
                abstract = self._reconstruct_abstract(
                    work.get("abstract_inverted_index", {})
                )

                yield {
                    "id": work.get("id", ""),
                    "title": work.get("title", ""),
                    "abstract": abstract,
                    "year": work.get("publication_year"),
                    "citations": work.get("cited_by_count", 0),
                    "doi": work.get("doi", ""),
                    "open_access_url": work.get("open_access", {}).get("oa_url"),
                    "source": "openalex"
                }
                total += 1

            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break

            await asyncio.sleep(0.1)

    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        """OpenAlex stores abstracts as inverted index"""
        if not inverted_index:
            return ""
        words = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words[i] for i in sorted(words.keys()))

    def download_snapshot(self):
        """Download full OpenAlex snapshot (most efficient)"""
        logger.info("Downloading OpenAlex snapshot via AWS S3...")
        cmd = [
            "aws", "s3", "sync",
            "s3://openalex", "data/openalex_snapshot",
            "--no-sign-request",
            "--exclude", "*",
            "--include", "data/works/*"
        ]
        subprocess.run(cmd)


# ═══════════════════════════════════════════════════
# SECTION 2: IMAGE DATA COLLECTORS
# ═══════════════════════════════════════════════════

class LAIONImageCollector:
    """
    LAION-5B: Largest open image dataset.
    5.85 billion image-text pairs.
    """

    LAION_DATASETS = {
        "laion2B-en": "laion/laion2B-en",
        "laion2B-multi": "laion/laion2B-multi",
        "laion_aesthetics_v2": "laion/laion_aesthetics_v2_5",
        "datacomp_1b": "mlfoundations/datacomp_1b",
        "recap_datacomp": "BAAI/Recap-DataComp-1B",
    }

    def download_with_img2dataset(self, dataset_name: str,
                                    output_dir: str,
                                    num_processes: int = 16,
                                    image_size: int = 256,
                                    max_samples: int = 1000000):
        """img2dataset is the BEST tool for downloading image datasets."""
        from datasets import load_dataset
        ds = load_dataset(
            self.LAION_DATASETS[dataset_name],
            split="train",
            streaming=True
        )

        import pandas as pd
        urls_file = f"{output_dir}/{dataset_name}_urls.parquet"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        batch = []
        for i, item in enumerate(ds):
            if i >= max_samples:
                break
            batch.append({
                "url": item.get("url", ""),
                "caption": item.get("caption", item.get("text", ""))
            })

        pd.DataFrame(batch).to_parquet(urls_file)

        cmd = [
            "img2dataset",
            f"--url_list={urls_file}",
            f"--output_folder={output_dir}",
            f"--processes_count={num_processes}",
            f"--image_size={image_size}",
            "--output_format=webdataset",
            "--enable_wandb=False",
            "--resize_mode=keep_ratio",
            "--min_image_size=64",
            "--max_aspect_ratio=3.0",
            "--number_sample_per_shard=10000",
            "--distributor=multiprocessing",
        ]
        subprocess.run(cmd, check=True)
        logger.success(f"Downloaded {max_samples} images from {dataset_name}")

    def download_openimages(self, output_dir: str, split: str = "train"):
        """Google OpenImages v7 — 9M images with labels"""
        import fiftyone.zoo as foz
        dataset = foz.load_zoo_dataset(
            "open-images-v7",
            split=split,
            max_samples=100000,
            dataset_dir=output_dir
        )
        return dataset

    def download_coco(self, output_dir: str):
        """MS-COCO — 330K images with captions + segmentations"""
        base = "http://images.cocodataset.org"
        files = [
            f"{base}/zips/train2017.zip",
            f"{base}/zips/val2017.zip",
            f"{base}/annotations/annotations_trainval2017.zip"
        ]
        for url in files:
            fname = Path(output_dir) / url.split("/")[-1]
            if not fname.exists():
                subprocess.run(["curl", "-L", "-o", str(fname), url])


# ═══════════════════════════════════════════════════
# SECTION 3: VIDEO DATA COLLECTORS
# ═══════════════════════════════════════════════════

class VideoDataCollector:
    """Collect video datasets using yt-dlp and dataset APIs."""

    def download_kinetics(self, output_dir: str, dataset: str = "kinetics700"):
        """DeepMind Kinetics — 600K+ video clips, 700 action classes."""
        subprocess.run(["pip", "install", "kinetics-downloader"])
        cmd = [
            "python", "-m", "kinetics_downloader",
            "--dataset", dataset,
            "--output", output_dir,
            "--num-workers", "16"
        ]
        subprocess.run(cmd)

    def download_webvid(self, output_dir: str, num_workers: int = 8):
        """WebVid-10M — 10M video-text pairs."""
        from datasets import load_dataset

        ds = load_dataset("TempoFunk/webvid-10M", streaming=True)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        metadata = []

        for i, item in enumerate(ds["train"]):
            metadata.append({
                "video_id": item.get("videoid"),
                "url": item.get("contentUrl"),
                "caption": item.get("name", ""),
                "duration": item.get("duration", "")
            })

        meta_file = f"{output_dir}/metadata.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        urls_file = f"{output_dir}/urls.txt"
        with open(urls_file, "w") as f:
            f.write("\n".join(m["url"] for m in metadata if m["url"]))

        subprocess.run([
            "yt-dlp",
            "--batch-file", urls_file,
            "-o", f"{output_dir}/%(id)s.%(ext)s",
            "--format", "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "--concurrent-fragments", str(num_workers),
            "--retry-sleep", "5",
            "--ignore-errors",
            "--write-info-json",
            "--write-subs",
        ])

    def batch_youtube_download(self, channel_urls: list[str],
                                output_dir: str, max_per_channel: int = 100):
        """Batch download YouTube channels for educational content"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        EDUCATIONAL_CHANNELS = [
            "https://www.youtube.com/@3blue1brown",
            "https://www.youtube.com/@lexfridman",
            "https://www.youtube.com/@AndrejKarpathy",
            "https://www.youtube.com/@YannicKilcher",
            "https://www.youtube.com/@TwoMinutePapers",
            "https://www.youtube.com/@sentdex",
            "https://www.youtube.com/@Veritasium",
            "https://www.youtube.com/@KurzgesagtInEnglish",
            "https://www.youtube.com/@numberphile",
            "https://www.youtube.com/@Fireship",
            "https://www.youtube.com/@ThePrimeagen",
        ] + channel_urls

        for channel in EDUCATIONAL_CHANNELS:
            logger.info(f"Downloading channel: {channel}")
            subprocess.run([
                "yt-dlp",
                channel,
                "-o", f"{output_dir}/%(channel)s/%(id)s.%(ext)s",
                "--format", "bestvideo[height<=720]+bestaudio/best",
                "--max-downloads", str(max_per_channel),
                "--write-auto-subs",
                "--sub-lang", "en,hi",
                "--write-info-json",
                "--embed-thumbnail",
                "--ignore-errors",
            ])


# ═══════════════════════════════════════════════════
# SECTION 4: AUDIO DATA COLLECTORS
# ═══════════════════════════════════════════════════

class AudioDataCollector:
    """Collect speech, music, and ambient audio datasets."""

    def download_common_voice(self, languages: list[str] = None,
                               output_dir: str = "data/audio/common_voice"):
        """Mozilla Common Voice — 30,000+ hours in 120 languages"""
        from datasets import load_dataset

        langs = languages or ["en", "hi", "fr", "de", "es", "zh-CN", "ar", "ru"]
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        for lang in langs:
            logger.info(f"Downloading Common Voice: {lang}")
            try:
                ds = load_dataset(
                    "mozilla-foundation/common_voice_17_0",
                    lang,
                    split="train",
                    trust_remote_code=True
                )
                ds.save_to_disk(f"{output_dir}/{lang}")
                logger.success(f"✓ Common Voice {lang}: {len(ds)} samples")
            except Exception as e:
                logger.error(f"Failed {lang}: {e}")

    def download_gigaspeech(self, subset: str = "l",
                              output_dir: str = "data/audio/gigaspeech"):
        """GigaSpeech — 10,000 hours diverse English speech"""
        from datasets import load_dataset
        ds = load_dataset("speechcolab/gigaspeech", subset, trust_remote_code=True)
        ds.save_to_disk(output_dir)

    def download_indic_speech(self, output_dir: str = "data/audio/indic"):
        """Best Hindi/Indic speech datasets."""
        from datasets import load_dataset

        indic_datasets = [
            ("ai4bharat/Shrutilipi", None),
            ("ai4bharat/indicSUPERB", None),
            ("google/fleurs", "hi_in"),
            ("mozilla-foundation/common_voice_17_0", "hi"),
        ]

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for dataset_name, config in indic_datasets:
            try:
                ds = load_dataset(dataset_name, config, split="train",
                                  trust_remote_code=True)
                save_path = f"{output_dir}/{dataset_name.replace('/','_')}"
                ds.save_to_disk(save_path)
                logger.success(f"✓ {dataset_name}: {len(ds)} samples")
            except Exception as e:
                logger.error(f"Failed {dataset_name}: {e}")

    def transcribe_audio_whisper(self, audio_dir: str,
                                   output_dir: str,
                                   model_size: str = "large-v3"):
        """Use OpenAI Whisper to transcribe any audio."""
        import whisper

        model = whisper.load_model(model_size)
        audio_files = list(Path(audio_dir).rglob("*.mp3")) + \
                      list(Path(audio_dir).rglob("*.wav")) + \
                      list(Path(audio_dir).rglob("*.m4a"))

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results = []

        for audio_file in audio_files:
            try:
                result = model.transcribe(str(audio_file), language=None)
                transcript = {
                    "file": str(audio_file),
                    "text": result["text"],
                    "language": result["language"],
                    "segments": result["segments"]
                }
                results.append(transcript)

                out_file = Path(output_dir) / f"{audio_file.stem}.json"
                out_file.write_text(json.dumps(transcript, indent=2))

                logger.info(f"Transcribed: {audio_file.name}")
            except Exception as e:
                logger.error(f"Failed: {audio_file}: {e}")

        return results


# ═══════════════════════════════════════════════════
# SECTION 5: HUGGING FACE MASS DOWNLOADER
# ═══════════════════════════════════════════════════

PRIORITY_HF_DATASETS = [
    # ── LARGE TEXT ─────────────────────────────────
    ("HuggingFaceFW/fineweb",              "CC-MAIN-2024-51",  "text"),
    ("HuggingFaceFW/fineweb-edu",          "sample-350BT",     "text"),
    ("allenai/dolma",                       "v1_7",             "text"),
    ("cerebras/SlimPajama-627B",            None,               "text"),
    ("togethercomputer/RedPajama-Data-1T",  "arxiv",            "text"),
    ("togethercomputer/RedPajama-Data-1T",  "book",             "text"),
    ("togethercomputer/RedPajama-Data-1T",  "github",           "text"),
    ("togethercomputer/RedPajama-Data-1T",  "wikipedia",        "text"),
    ("EleutherAI/pile",                     None,               "text"),
    ("c4",                                  "en",               "text"),
    ("wikimedia/wikipedia",                 "20231101.en",      "text"),
    ("wikimedia/wikipedia",                 "20231101.hi",      "text"),

    # ── CODE ───────────────────────────────────────
    ("bigcode/the-stack-dedup",            "data",             "code"),
    ("bigcode/starcoderdata",              None,               "code"),
    ("codeparrot/github-code",             None,               "code"),
    ("bigcode/jupyter-structured-clean-v1", None,              "code"),

    # ── INSTRUCTION/RLHF ───────────────────────────
    ("teknium/OpenHermes-2.5",             None,               "instruct"),
    ("Open-Orca/OpenOrca",                 None,               "instruct"),
    ("HuggingFaceH4/ultrachat_200k",       None,               "instruct"),
    ("HuggingFaceTB/smoltalk",             "all",              "instruct"),
    ("Magpie-Align/Magpie-Ultra-v0.1",     None,               "instruct"),
    ("WizardLM/WizardLM_evol_instruct_V2_196k", None,         "instruct"),
    ("google/flan",                        None,               "instruct"),
    ("OpenAssistant/oasst2",               None,               "instruct"),
    ("meta-math/MetaMathQA",               None,               "instruct"),
    ("databricks/databricks-dolly-15k",    None,               "instruct"),

    # ── MULTILINGUAL ───────────────────────────────
    ("uonlp/CulturaX",                     "hi",               "multilingual"),
    ("uonlp/CulturaX",                     "en",               "multilingual"),
    ("ai4bharat/sangraha",                 "verified",         "multilingual"),
    ("CohereForAI/aya_dataset",            None,               "multilingual"),
    ("CohereForAI/aya_collection",         None,               "multilingual"),
    ("oscar-corpus/OSCAR-2301",            "hi",               "multilingual"),

    # ── SCIENTIFIC ─────────────────────────────────
    ("allenai/peS2o",                      None,               "scientific"),
    ("allenai/s2orc",                      None,               "scientific"),
    ("openai/gsm8k",                       "main",             "math"),
    ("lighteval/MATH",                     None,               "math"),
    ("facebook/natural_questions",         None,               "qa"),

    # ── MULTIMODAL ─────────────────────────────────
    ("mint-1t/MINT-1T",                    None,               "multimodal"),
    ("BAAI/Recap-DataComp-1B",             None,               "image_text"),
    ("laion/laion_aesthetics_v2_5",        None,               "image_text"),
]


class HuggingFaceMassDownloader:
    """Download ALL priority HuggingFace datasets"""

    def __init__(self, output_dir: str = "data/huggingface",
                 token: str = None):
        self.output_dir = Path(output_dir)
        self.token = token
        self.failed = []
        self.success = []

    def download_dataset(self, name: str, config: str, category: str,
                          streaming: bool = False, max_rows: int = None):
        from datasets import load_dataset

        save_path = self.output_dir / category / name.replace("/", "__")
        if config:
            save_path = save_path / config

        if save_path.exists() and any(save_path.iterdir()):
            logger.info(f"SKIP (exists): {name}")
            return True

        try:
            logger.info(f"Downloading: {name} [{config or 'default'}]")
            ds = load_dataset(
                name, config,
                split="train",
                streaming=streaming,
                token=self.token,
                trust_remote_code=True
            )

            if streaming:
                import pyarrow as pa
                import pyarrow.parquet as pq
                save_path.mkdir(parents=True, exist_ok=True)
                pf = save_path / "data.parquet"
                writer = None
                buf = []
                total = 0
                for item in ds:
                    buf.append(item)
                    total += 1
                    if max_rows and total >= max_rows:
                        break
                    if len(buf) >= 50000:
                        batch = pa.Table.from_pylist(buf)
                        if writer is None:
                            writer = pq.ParquetWriter(pf, batch.schema)
                        writer.write_table(batch)
                        buf = []
                        logger.info(f"  {name}: {total} rows saved")
                if buf:
                    batch = pa.Table.from_pylist(buf)
                    if writer is None:
                        writer = pq.ParquetWriter(pf, batch.schema)
                    writer.write_table(batch)
                if writer:
                    writer.close()
            else:
                if max_rows:
                    ds = ds.select(range(min(max_rows, len(ds))))
                save_path.mkdir(parents=True, exist_ok=True)
                ds.save_to_disk(str(save_path))
                ds.to_parquet(str(save_path / "data.parquet"))

            size = sum(f.stat().st_size for f in save_path.rglob("*")
                      if f.is_file()) / 1e9
            logger.success(f"✓ {name}: {size:.2f} GB")
            self.success.append(name)
            return True

        except Exception as e:
            logger.error(f"✗ {name}: {e}")
            self.failed.append((name, str(e)))
            return False

    def download_all(self):
        """Download everything in priority order"""
        total = len(PRIORITY_HF_DATASETS)
        for i, (name, config, category) in enumerate(PRIORITY_HF_DATASETS):
            logger.info(f"[{i+1}/{total}] {name}")
            self.download_dataset(
                name, config, category,
                streaming=True,
                max_rows=5_000_000
            )

        print(f"\n✅ Success: {len(self.success)}")
        print(f"❌ Failed: {len(self.failed)}")
        for name, err in self.failed:
            print(f"  - {name}: {err[:80]}")


# ═══════════════════════════════════════════════════
# SECTION 6: SYNTHETIC DATA GENERATION
# ═══════════════════════════════════════════════════

SYNTHETIC_PROMPTS = {
    "reasoning_chains": (
        "Generate {n} complex multi-step reasoning problems with complete solutions.\n"
        "Domains: mathematics, logic puzzles, physics, programming, causal reasoning.\n"
        "Each problem must require 5-10 explicit reasoning steps.\n"
        "Include problems of varying difficulty (easy/medium/hard/expert).\n"
        'FORMAT: JSON array. Each item: {{"problem": str, "steps": list[str], "answer": str, "difficulty": str, "domain": str}}\n'
        "Return ONLY valid JSON. No markdown, no preamble."
    ),
    "code_with_tests": (
        "Generate {n} programming tasks with complete implementations AND unit tests.\n"
        "Languages: Python, JavaScript, TypeScript, Go, Rust (distribute evenly).\n"
        "Include: data structures, algorithms, system design, API calls, ML code.\n"
        'FORMAT: JSON array. Each item: {{"task": str, "language": str, "solution": str, "tests": str, "explanation": str, "complexity": str}}\n'
        "Return ONLY valid JSON. No markdown, no preamble."
    ),
    "scientific_qa": (
        "Generate {n} PhD-level Q&A pairs on topic: {domain}.\n"
        "Questions should test deep conceptual understanding, not just facts.\n"
        "Include derivations, comparisons, edge cases, and common misconceptions.\n"
        'FORMAT: JSON array. Each item: {{"question": str, "answer": str, "key_concepts": list[str], "difficulty": str}}\n'
        "Return ONLY valid JSON. No markdown, no preamble."
    ),
    "hindi_bilingual": (
        "Generate {n} bilingual instruction-response pairs (Hindi + English).\n"
        "Include: everyday tasks, technical topics, cultural context, Hinglish.\n"
        "Each pair should feel natural in both languages.\n"
        'FORMAT: JSON array. Each item: {{"hindi_instruction": str, "english_instruction": str, "hindi_response": str, "english_response": str, "topic": str}}\n'
        "Return ONLY valid JSON. No markdown, no preamble."
    ),
    "dario_amodei_inspired": (
        'Generate {n} high-quality training examples inspired by Dario Amodei\'s vision '
        'in "Machines of Loving Grace" — AI accelerating human progress.\n\n'
        "Domains: biology research acceleration, mental health support, economic empowerment,\n"
        "medical breakthroughs, scientific discovery, global development.\n\n"
        "Each example should represent the kind of knowledge exchange that could compress\n"
        'decades of human progress into years — the "country of geniuses" at work.\n\n'
        'FORMAT: JSON array. Each item: {{"context": str, "question": str, "expert_response": str, "impact_domain": str}}\n'
        "Return ONLY valid JSON. No markdown."
    ),
    "tool_use_agents": (
        "Generate {n} realistic agentic task examples where an AI must plan and use tools.\n"
        "Tools available: web_search, code_execution, file_read, api_call, calculator.\n"
        "Tasks should require 3-10 tool uses to complete.\n"
        'FORMAT: JSON array. Each item: {{"task": str, "plan": list[str], "tool_calls": list[dict], "final_answer": str}}\n'
        "Return ONLY valid JSON. No markdown."
    ),
}

SCIENTIFIC_DOMAINS = [
    "machine learning", "quantum physics", "molecular biology",
    "neuroscience", "organic chemistry", "number theory",
    "astrophysics", "immunology", "materials science",
    "epidemiology", "climate science", "genetics",
    "pharmacology", "structural biology", "computer architecture"
]


class MultiModelSyntheticFactory:
    """
    Generate synthetic data at scale using MULTIPLE AI APIs in PARALLEL.

    Uses the MultiAgentKeyManager to discover ALL available API providers,
    then distributes generation tasks across them for maximum throughput.

    Supports:
    - OpenAI-compatible providers (Groq, Together, DeepInfra, etc.)
    - Anthropic Claude (native API)
    - OpenAI (native API with JSON mode)
    - Google Gemini (native API)
    - xAI Grok, DeepSeek, Cohere, Mistral
    """

    def __init__(self, api_keys: dict):
        """
        Args:
            api_keys: Dict of {provider_name: api_key}. Falls back to
                      MultiAgentKeyManager (which checks stored + env keys).
        """
        self.keys = api_keys
        self.key_manager = MultiAgentKeyManager(providers=api_keys)
        self.clients = {}

        # Initialize native API clients for providers that need them
        if api_keys.get("anthropic"):
            try:
                from anthropic import AsyncAnthropic
                self.clients["anthropic"] = AsyncAnthropic(api_key=api_keys["anthropic"])
            except ImportError:
                logger.warning("anthropic package not installed, skipping Claude")

        if api_keys.get("openai"):
            try:
                import openai
                self.clients["openai"] = openai.AsyncOpenAI(api_key=api_keys["openai"])
            except ImportError:
                logger.warning("openai package not installed, skipping GPT-4o")

        if api_keys.get("google"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_keys["google"])
                self.clients["google"] = genai
            except ImportError:
                logger.warning("google-generativeai package not installed, skipping Gemini")

        logger.info(f"[SyntheticFactory] {self.key_manager.count()} providers available: "
                    f"{', '.join(self.key_manager.active_providers)}")

    # ── Native API Generators ────────────────────────────────────

    async def _generate_anthropic(self, prompt: str, model: str = "claude-sonnet-4-20250514") -> list:
        client = self.clients.get("anthropic")
        if not client:
            return []
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = resp.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Anthropic generation failed: {e}")
            return []

    async def _generate_openai(self, prompt: str, model: str = "gpt-4o") -> list:
        client = self.clients.get("openai")
        if not client:
            return []
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=8000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ]
            )
            data = json.loads(resp.choices[0].message.content)
            return data if isinstance(data, list) else list(data.values())[0]
        except Exception as e:
            logger.warning(f"OpenAI generation failed: {e}")
            return []

    async def _generate_google(self, prompt: str, model: str = "gemini-2.0-flash") -> list:
        genai = self.clients.get("google")
        if not genai:
            return []
        try:
            gemini = genai.GenerativeModel(model)
            resp = await gemini.generate_content_async(prompt)
            text = resp.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Google Gemini generation failed: {e}")
            return []

    async def _generate_openai_compatible(self, provider: str, prompt: str) -> list:
        """Generate via an OpenAI-compatible endpoint, with concurrency gating."""
        from src.data.generator import URLS, MODELS

        url = URLS.get(provider)
        model = MODELS.get(provider)
        key = self.key_manager.get_key(provider)

        if not all([url, model, key]):
            return []

        # Acquire concurrency slot for this provider
        acquired = self.key_manager.acquire(provider, timeout=15)
        if not acquired:
            return []

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Return ONLY valid JSON arrays."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 8000,
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        self.key_manager.record_success(provider)
                        return self._parse_json_response(content)
                    elif resp.status == 429:
                        self.key_manager.record_429(provider)
                        # Retry once after backoff if still within rate limits
                        return await self._retry_openai_compatible(provider, prompt)
                    else:
                        self.key_manager.record_error(provider)
                        return []
        except Exception as e:
            self.key_manager.record_error(provider)
            logger.debug(f"{provider} failed: {e}")
            return []
        finally:
            self.key_manager.release(provider)

    async def _retry_openai_compatible(self, provider: str, prompt: str) -> list:
        """Single retry for transient failures."""
        from src.data.generator import URLS, MODELS

        url = URLS.get(provider)
        model = MODELS.get(provider)
        key = self.key_manager.get_key(provider)
        if not all([url, model, key]):
            return []

        import asyncio
        await asyncio.sleep(2)  # Short backoff

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Return ONLY valid JSON arrays."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 8000,
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        self.key_manager.record_success(provider)
                        return self._parse_json_response(content)
        except Exception:
            pass
        return []

    def _parse_json_response(self, text: str) -> list:
        """Parse JSON from LLM response, handling common formatting issues."""
        text = text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            # Some models wrap in an object with a key
            for v in data.values():
                if isinstance(v, list):
                    return v
            return []
        except json.JSONDecodeError:
            # Try to find the first [ ... ]
            import re
            match = re.search(r'\[(.*)\]', text, re.DOTALL)
            if match:
                try:
                    return json.loads("[" + match.group(1) + "]")
                except Exception:
                    pass
            return []

    # ── Parallel Batch Generation ──────────────────────────────

    async def generate_batch(
        self,
        task_type: str,
        n_per_batch: int = 50,
        total: int = 10000,
        domain: str = None,
    ) -> list:
        """
        Run parallel generation across ALL available providers simultaneously.

        Distributes generation tasks round-robin across:
        - Premium native API clients (Anthropic, OpenAI, Google)
        - All OpenAI-compatible providers (Groq, Together, etc.)
        """
        template = SYNTHETIC_PROMPTS[task_type]
        all_results = []
        batches_needed = max(1, total // n_per_batch)

        # Build the list of all provider-specific generation coroutines
        active_providers = self.key_manager.active_providers

        if not active_providers:
            logger.error("No API providers available for synthetic generation!")
            return []

        logger.info(f"[{task_type}] Distributing {batches_needed} batches across "
                    f"{len(active_providers)} providers: {', '.join(active_providers)}")

        batch_tasks = []
        for i in range(batches_needed):
            prompt = template.format(n=n_per_batch, domain=domain or "general")

            # Alternate between providers for diversity and throughput
            provider = active_providers[i % len(active_providers)]

            if provider == "anthropic" and "anthropic" in self.clients:
                coro = self._generate_anthropic(prompt)
            elif provider == "openai" and "openai" in self.clients:
                coro = self._generate_openai(prompt)
            elif provider == "google" and "google" in self.clients:
                coro = self._generate_google(prompt)
            else:
                # Try OpenAI-compatible endpoint
                coro = self._generate_openai_compatible(provider, prompt)

            batch_tasks.append(coro)

            # Fire in batches of 20 to avoid overwhelming asyncio
            if len(batch_tasks) >= 20:
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        all_results.extend(r)
                batch_tasks = []
                logger.info(f"[{task_type}] {len(all_results)} / {total} samples generated")

        # Process remaining tasks
        if batch_tasks:
            results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    all_results.extend(r)

        logger.success(f"[{task_type}] Completed: {len(all_results)} samples "
                       f"from {len(active_providers)} providers")
        return all_results

    async def run_full_synthetic_pipeline(self, output_dir: str,
                                            total_per_task: int = 10000):
        """Generate ALL synthetic datasets using ALL available providers."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        tasks = [
            ("reasoning_chains", None),
            ("code_with_tests", None),
            ("hindi_bilingual", None),
            ("dario_amodei_inspired", None),
            ("tool_use_agents", None),
        ] + [("scientific_qa", domain) for domain in SCIENTIFIC_DOMAINS]

        for task_type, domain in tasks:
            name = f"{task_type}_{domain or 'all'}"
            out_file = Path(output_dir) / f"{name}.jsonl"

            if out_file.exists():
                logger.info(f"SKIP: {name}")
                continue

            logger.info(f"Generating: {name}")
            data = await self.generate_batch(
                task_type, n_per_batch=50,
                total=total_per_task, domain=domain
            )

            async with aiofiles.open(out_file, 'w') as f:
                for item in data:
                    await f.write(json.dumps(item) + "\n")

            logger.success(f"✓ {name}: {len(data)} samples saved")

        # Print key manager usage report
        self.key_manager.print_report()


# ═══════════════════════════════════════════════════
# SECTION 7: MASTER ORCHESTRATOR
# ═══════════════════════════════════════════════════

class AntiGravityOrchestrator:
    """
    Master controller. Run this and walk away.
    It will collect everything.
    """

    def __init__(self, base_output_dir: str = "D:/PythonAI_Data/anti_gravity_data"):
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            logger.warning("python-dotenv not installed, skipping .env load")
            
        self.base_dir = Path(base_output_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_key(self, env_key: str, default: str = None) -> str:
        import os
        return os.environ.get(env_key) or default


    async def run_all_phases(self):
        console.print("""
[bold green]
╔══════════════════════════════════════════════════════╗
║     ⚡ ANTI-GRAVITY DATA COLLECTION INITIATED ⚡      ║
║     "A country of geniuses in a data center"         ║
║     — Dario Amodei, Machines of Loving Grace         ║
╚══════════════════════════════════════════════════════╝
[/bold green]""")

        async def _run_hf_download():
            HuggingFaceMassDownloader(
                str(self.base_dir / "huggingface"),
                self._get_key("HF_TOKEN")
            ).download_all()

        async def _run_arxiv_collect():
            await ArXivMassCollector(
                str(self.base_dir / "arxiv")
            ).collect_all()

        async def _run_openalex_download():
            OpenAlexCollector(
                self._get_key("OPENALEX_EMAIL", "user@example.com"),
                str(self.base_dir / "openalex")
            ).download_snapshot()

        async def _run_images():
            LAIONImageCollector().download_openimages(
                str(self.base_dir / "images/openimages")
            )

        async def _run_video():
            VideoDataCollector().download_webvid(
                str(self.base_dir / "video/webvid")
            )

        async def _run_audio_common():
            AudioDataCollector().download_common_voice(
                output_dir=str(self.base_dir / "audio/common_voice")
            )

        async def _run_audio_indic():
            AudioDataCollector().download_indic_speech(
                str(self.base_dir / "audio/indic")
            )

        async def _run_synthetic():
            await MultiModelSyntheticFactory(
                api_keys=resolve_all()
            ).run_full_synthetic_pipeline(
                str(self.base_dir / "synthetic"),
                total_per_task=10000
            )

        phases = [
            ("📚 HuggingFace Mass Download", _run_hf_download),
            ("🔬 arXiv All Papers", _run_arxiv_collect),
            ("📖 OpenAlex Snapshot", _run_openalex_download),
            ("🖼️ Image Datasets", _run_images),
            ("🎬 Video Datasets", _run_video),
            ("🔊 Audio Datasets", _run_audio_common),
            ("🎙️ Hindi/Indic Audio", _run_audio_indic),
            ("🤖 Synthetic Data Generation (Parallel Multi-Agent)", _run_synthetic),
        ]

        results = {}
        for name, phase_fn in phases:
            console.print(f"\n[bold cyan]▶ {name}[/bold cyan]")
            try:
                await phase_fn()
                results[name] = "✅ SUCCESS"
                console.print(f"[green]✓ {name} complete[/green]")
            except Exception as e:
                results[name] = f"❌ {str(e)[:100]}"
                console.print(f"[red]✗ {name}: {e}[/red]")
                # NEVER stop — move to next phase

        self._print_final_report(results)

    def _print_final_report(self, results: dict):
        table = Table(title="🏆 ANTI-GRAVITY COLLECTION COMPLETE",
                     title_style="bold green")
        table.add_column("Phase", style="cyan", width=40)
        table.add_column("Status", style="white", width=15)
        table.add_column("Size on Disk", style="yellow", width=15)

        for name, status in results.items():
            size = self._get_dir_size(self.base_dir)
            table.add_row(name, status, f"{size:.1f} GB")

        console.print(table)

        total = self._get_dir_size(self.base_dir)
        console.print(f"\n[bold green]TOTAL DATA COLLECTED: {total:.1f} GB[/bold green]")

    def _get_dir_size(self, path: Path) -> float:
        try:
            return sum(f.stat().st_size for f in path.rglob("*")
                      if f.is_file()) / 1e9
        except Exception:
            return 0.0


# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import typer
    app = typer.Typer()

    @app.command()
    def collect(
        base_dir: str = typer.Option("D:/PythonAI_Data/anti_gravity_data", "--dir", help="Base output directory"),
        phase: str = typer.Option("all", "--phase",
                                    help="all/text/images/video/audio/synthetic")
    ):
        orchestrator = AntiGravityOrchestrator(base_dir)
        asyncio.run(orchestrator.run_all_phases())

    app()