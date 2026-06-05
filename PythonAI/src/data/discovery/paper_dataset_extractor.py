"""Paper Dataset Extractor.

Extracts dataset mentions from research paper abstracts and full text.
Uses pattern matching to find dataset names, HuggingFace links,
GitHub repo links, and URL references in papers.

Also includes a simple prioritization to flag papers that introduce
new datasets vs papers that use existing ones.

Usage:
    from src.data.discovery import PaperDatasetExtractor
    extractor = PaperDatasetExtractor()
    datasets = extractor.extract_from_text(abstract_text)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from src.data.metadata import DatasetRecord, DataDomain, MetadataManager

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".paper_cache.json"

# Patterns to find dataset mentions
DATASET_NAME_PATTERN = re.compile(
    r"(?:\b(?:dataset|benchmark|corpus|collection)\s+(?:of|for|with|called|named|:)\s+)?"
    r"(?P<name>[A-Z][A-Za-z0-9_.-]{2,50}(?:[-_/][A-Za-z0-9_.-]+)*)",
)

HF_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:huggingface\.co|hf\.co)/datasets/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)",
)

GITHUB_URL_PATTERN = re.compile(
    r"(?:https?://)?github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+?)(?:[./)\\]|$)",
)

PAPER_WITH_DATASET_PATTERN = re.compile(
    r"(?:we\s+(?:introduce|present|release|propose)|"
    r"this\s+(?:paper|work)\s+(?:introduces|presents|releases))\s+"
    r"(?:a\s+)?(?:new\s+)?(?:large-scale\s+)?(?:dataset|benchmark|corpus|collection)",
    re.IGNORECASE,
)


@dataclass
class ExtractedDataset:
    """A dataset extracted from a research paper."""
    name: str
    source_url: str = ""
    source_paper_title: str = ""
    source_paper_url: str = ""
    hf_path: str = ""
    github_repo: str = ""
    description: str = ""
    is_new_dataset: bool = False
    confidence: float = 0.5


class PaperDatasetExtractor:
    """Extract dataset references from research paper text.

    Can process individual abstracts or full paper text, and can
    batch-process paper lists from arXiv, Semantic Scholar, etc.

    Attributes:
        metadata_mgr: Optional MetadataManager for cross-reference.
        cache_path: Path to local cache.
    """

    def __init__(
        self,
        metadata_mgr: MetadataManager | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        self.metadata_mgr = metadata_mgr or MetadataManager()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self._seen: set[str] = set()
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._seen = set(data.get("seen_dataset_names", []))
            except (json.JSONDecodeError, KeyError):
                self._seen = set()

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps({"seen_dataset_names": sorted(self._seen)}, indent=2),
            encoding="utf-8",
        )

    def extract_from_text(
        self,
        text: str,
        paper_title: str = "",
        paper_url: str = "",
    ) -> list[ExtractedDataset]:
        """Extract dataset references from a paper abstract or full text.

        Args:
            text: Paper abstract or full text.
            paper_title: Optional paper title for metadata.
            paper_url: Optional paper URL for metadata.

        Returns:
            List of ExtractedDataset objects found in the text.
        """
        extracted: list[ExtractedDataset] = []
        seen_names: set[str] = set()

        if not text:
            return extracted

        # 1. Find HF dataset URLs
        for match in HF_URL_PATTERN.finditer(text):
            hf_path = match.group(1)
            if hf_path not in seen_names:
                seen_names.add(hf_path)
                is_new = bool(PAPER_WITH_DATASET_PATTERN.search(text))
                extracted.append(ExtractedDataset(
                    name=hf_path.split("/")[-1],
                    source_url=f"https://huggingface.co/datasets/{hf_path}",
                    source_paper_title=paper_title,
                    source_paper_url=paper_url,
                    hf_path=hf_path,
                    is_new_dataset=is_new,
                    confidence=0.9 if is_new else 0.6,
                    description=f"Dataset from HuggingFace: {hf_path}",
                ))

        # 2. Find GitHub repo URLs
        for match in GITHUB_URL_PATTERN.finditer(text):
            repo = match.group(1)
            if repo not in seen_names and self._is_dataset_repo(repo):
                seen_names.add(repo)
                is_new = bool(PAPER_WITH_DATASET_PATTERN.search(text))
                extracted.append(ExtractedDataset(
                    name=repo.split("/")[-1],
                    source_url=f"https://github.com/{repo}",
                    source_paper_title=paper_title,
                    source_paper_url=paper_url,
                    github_repo=repo,
                    is_new_dataset=is_new,
                    confidence=0.7 if is_new else 0.4,
                    description=f"GitHub repository: {repo}",
                ))

        # 3. Find dataset name mentions (lower confidence)
        for match in DATASET_NAME_PATTERN.finditer(text):
            name = match.group("name")
            if (
                name not in seen_names
                and len(name) >= 4
                and not name.startswith(("http", "www", "arXiv", "DOI"))
            ):
                seen_names.add(name)
                is_new = bool(PAPER_WITH_DATASET_PATTERN.search(text))
                extracted.append(ExtractedDataset(
                    name=name,
                    source_paper_title=paper_title,
                    source_paper_url=paper_url,
                    is_new_dataset=is_new,
                    confidence=0.3,
                    description=f"Dataset mentioned in paper: {name}",
                ))

        # Tag new ones
        for ds in extracted:
            if ds.name not in self._seen:
                self._seen.add(ds.name)

        self._save_cache()
        return extracted

    def extract_from_arxiv(
        self,
        arxiv_ids: list[str],
    ) -> list[ExtractedDataset]:
        """Extract datasets from arXiv paper abstracts.

        Fetches paper metadata from the arXiv API and extracts
        dataset references from each.

        Args:
            arxiv_ids: List of arXiv IDs (e.g., ['2405.12345', '2405.67890']).

        Returns:
            List of ExtractedDataset objects.
        """
        all_extracted: list[ExtractedDataset] = []

        for arxiv_id in arxiv_ids:
            try:
                import urllib.request
                import xml.etree.ElementTree as ET

                url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "PythonAI/2.0 (discovery-engine)",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    xml_data = resp.read().decode("utf-8")

                root = ET.fromstring(xml_data)
                ns = {"a": "http://www.w3.org/2005/Atom"}

                entry = root.find("a:entry", ns)
                if entry is None:
                    continue

                title = entry.find("a:title", ns)
                summary = entry.find("a:summary", ns)

                paper_title = title.text.strip() if title is not None and title.text else ""
                paper_url = f"https://arxiv.org/abs/{arxiv_id}"
                abstract = summary.text.strip() if summary is not None and summary.text else ""

                extracted = self.extract_from_text(
                    text=abstract,
                    paper_title=paper_title,
                    paper_url=paper_url,
                )
                all_extracted.extend(extracted)

            except Exception as exc:
                print(f"[PaperDatasetExtractor] Failed to fetch arXiv {arxiv_id}: {exc}")

        return all_extracted

    @staticmethod
    def _is_dataset_repo(repo: str) -> bool:
        """Heuristic: check if a repo name looks like a dataset."""
        dataset_indicators = [
            "data", "dataset", "corpus", "bench", "eval",
            "collection", "gallery", "images", "sounds",
        ]
        name = repo.split("/")[-1].lower() if "/" in repo else repo.lower()
        return any(indicator in name for indicator in dataset_indicators)

    def to_metadata_records(
        self,
        datasets: list[ExtractedDataset],
        domain: DataDomain = DataDomain.EMERGING,
    ) -> list[DatasetRecord]:
        """Convert extracted datasets to DatasetRecord for registration."""
        records: list[DatasetRecord] = []
        for ds in datasets:
            if ds.confidence < 0.3:
                continue  # Skip low-confidence matches

            priority = "high" if ds.is_new_dataset and ds.confidence >= 0.7 else "medium" if ds.confidence >= 0.5 else "low"

            records.append(DatasetRecord(
                id=f"paper_{ds.name.lower().replace(' ', '_').replace('/', '_')}",
                name=ds.name[:60],
                source="paper",
                url=ds.source_url or ds.source_paper_url,
                size_bytes=0,
                estimated_records=0,
                languages=["en"],
                domains=[domain],
                modalities=["text"],
                license="Unknown",
                priority=priority,
                quality_score=round(ds.confidence, 2),
                description=f"From paper '{ds.source_paper_title[:80]}': {ds.description[:120]}",
            ))
        return records


def extract_datasets_from_papers(
    arxiv_ids: list[str] | None = None,
    text: str | None = None,
    metadata_mgr: MetadataManager | None = None,
) -> list[DatasetRecord]:
    """Convenience: extract datasets from papers and return DatasetRecords."""
    extractor = PaperDatasetExtractor(metadata_mgr=metadata_mgr)

    if text:
        extracted = extractor.extract_from_text(text)
    elif arxiv_ids:
        extracted = extractor.extract_from_arxiv(arxiv_ids)
    else:
        # Default: try a few recent arXiv papers
        extracted = extractor.extract_from_arxiv([
            "2405.12345",
            "2405.67890",
            "2406.11111",
        ])

    return extractor.to_metadata_records(extracted)


if __name__ == "__main__":
    print("[PaperDatasetExtractor] Testing extraction...")
    sample_text = (
        "We introduce SuperGPQA, a new large-scale benchmark for evaluating "
        "graduate-level knowledge in LLMs. The dataset is available at "
        "https://huggingface.co/datasets/supergpqa/supergpqa and the code "
        "at https://github.com/supergpqa/benchmark. Our collection includes "
        "285K questions across 18 domains."
    )
    records = extract_datasets_from_papers(text=sample_text)
    if records:
        print(f"  Extracted {len(records)} datasets:")
        for r in records:
            print(f"    - {r.name}: {r.description[:80]}")
    else:
        print("  No datasets extracted.")
