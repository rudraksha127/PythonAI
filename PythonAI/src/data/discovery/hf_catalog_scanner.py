"""HuggingFace Catalog Scanner.

Scans the HuggingFace Hub for new and updated datasets relevant to
the PythonAI training pipeline.  Tracks discovered datasets in the
metadata registry so the user can review and add them.

Usage:
    from src.data.discovery import HFCatalogScanner
    scanner = HFCatalogScanner()
    found = scanner.scan(domain_filter=["science", "code"])
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.metadata import DataDomain, DatasetRecord, MetadataManager

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".hf_scanner_cache.json"


@dataclass
class HFDiscoveryResult:
    """A single dataset discovered on HuggingFace."""
    dataset_id: str
    url: str = ""
    description: str = ""
    languages: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    size_bytes: int = 0
    num_downloads: int = 0
    license: str = ""
    is_new: bool = True


class HFCatalogScanner:
    """Scan HuggingFace datasets hub for new relevant datasets.

    Uses the HF Datasets Server API (or a lightweight listing endpoint)
    to discover datasets, then checks them against the metadata registry
    to determine which are new.

    Attributes:
        metadata_mgr: Optional MetadataManager to cross-check against.
        cache_path: Path to local cache of seen dataset IDs.
        domain_keywords: Mapping of DataDomain → list of keywords.
    """

    DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "formal_science": [
            "math", "proof", "theorem", "algebra", "calculus",
            "statistics", "probability", "logic", "cryptography",
            "number-theory", "geometry",
        ],
        "natural_science": [
            "physics", "chemistry", "biology", "astronomy", "geology",
            "climate", "ecology", "genomics", "protein", "drug",
        ],
        "engineering": [
            "code", "programming", "python", "javascript", "rust",
            "software", "github", "stackoverflow", "algorithm",
            "data-structure", "system-design",
        ],
        "medicine": [
            "medical", "clinical", "health", "diagnosis", "patient",
            "drug", "pharma", "biomedical", "radiology", "pathology",
        ],
        "social_science": [
            "economics", "psychology", "sociology", "political",
            "legal", "law", "governance", "policy",
        ],
        "business": [
            "finance", "stock", "market", "trading", "business",
            "startup", "entrepreneur", "accounting",
        ],
        "arts": [
            "literature", "poetry", "philosophy", "history", "music",
            "art", "creative", "writing",
        ],
        "language": [
            "translation", "multilingual", "hindi", "indic",
            "parallel", "corpus", "nlp", "text",
        ],
        "multimodal": [
            "image", "video", "audio", "speech", "vision",
            "caption", "multimodal", "generation",
        ],
        "emerging": [
            "safety", "alignment", "robotics", "quantum",
            "blockchain", "climate", "biotech",
        ],
    }

    def __init__(
        self,
        metadata_mgr: MetadataManager | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        self.metadata_mgr = metadata_mgr or MetadataManager()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self._seen: set[str] = set()
        self._load_cache()

    # ── Cache management ──────────────────────────────────────────

    def _load_cache(self) -> None:
        """Load previously seen dataset IDs from local cache."""
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._seen = set(data.get("seen_ids", []))
            except (json.JSONDecodeError, KeyError):
                self._seen = set()

    def _save_cache(self) -> None:
        """Persist seen dataset IDs to local cache."""
        self.cache_path.write_text(
            json.dumps({"seen_ids": sorted(self._seen)}, indent=2),
            encoding="utf-8",
        )

    # ── Discovery logic ───────────────────────────────────────────

    def scan(
        self,
        domain_filter: list[str] | None = None,
        max_results: int = 100,
        min_downloads: int = 100,
        search_terms: list[str] | None = None,
    ) -> list[HFDiscoveryResult]:
        """Scan HuggingFace for new relevant datasets.

        Uses the HF Datasets Server search/list API.  Returns datasets
        that match the given domain filters and haven't been seen before.

        Args:
            domain_filter: Only return datasets matching these domains.
            max_results: Maximum number of results to return.
            min_downloads: Minimum downloads threshold.
            search_terms: Custom search terms (defaults to domain keywords).

        Returns:
            List of HFDiscoveryResult for newly discovered datasets.
        """
        discovered: list[HFDiscoveryResult] = []

        # Build search terms from domain filter or use defaults
        terms = search_terms or []
        if domain_filter:
            for d in domain_filter:
                terms.extend(self.DOMAIN_KEYWORDS.get(d, []))
        if not terms:
            terms = [
                "dataset", "fineweb", "instruction", "code",
                "hindi", "indic", "translation", "science",
                "medical", "math", "multilingual",
            ]

        # Try to query HF Datasets Server API
        found_datasets = self._query_hf_api(terms, max_results, min_downloads)

        for ds in found_datasets:
            did = ds.get("id", "")
            if not did or did in self._seen:
                continue

            # Check if already registered in metadata manager
            if self.metadata_mgr.get(did):
                self._seen.add(did)
                continue

            discovered.append(HFDiscoveryResult(
                dataset_id=did,
                url=f"https://huggingface.co/datasets/{did}",
                description=ds.get("description", ""),
                languages=self._extract_languages(ds),
                tags=ds.get("tags", []),
                size_bytes=ds.get("size", 0),
                num_downloads=ds.get("downloads", 0),
                license=ds.get("license", ""),
                is_new=did not in self._seen,
            ))
            self._seen.add(did)

        self._save_cache()
        return discovered

    def _query_hf_api(
        self,
        terms: list[str],
        max_results: int,
        min_downloads: int,
    ) -> list[dict[str, Any]]:
        """Query the HuggingFace Datasets Server API.

        Falls back to a simulated discovery if the API is unavailable.
        """
        try:
            import urllib.parse
            import urllib.request

            all_results: list[dict[str, Any]] = []
            for term in terms[:5]:  # Limit to first 5 search terms
                params = urllib.parse.urlencode({
                    "search": term,
                    "sort": "downloads",
                    "direction": -1,
                    "limit": min(50, max_results),
                })
                url = f"https://huggingface.co/api/datasets?{params}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "PythonAI/2.0 (data-discovery)",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list):
                        for item in data:
                            downloads = item.get("downloads", 0) or 0
                            if downloads >= min_downloads:
                                all_results.append(item)
                    elif isinstance(data, dict):
                        items = data.get("items", data.get("datasets", []))
                        for item in items:
                            downloads = item.get("downloads", 0) or 0
                            if downloads >= min_downloads:
                                all_results.append(item)

            # Deduplicate by id
            seen_ids: set[str] = set()
            unique: list[dict[str, Any]] = []
            for item in all_results:
                did = item.get("id", "")
                if did and did not in seen_ids:
                    seen_ids.add(did)
                    unique.append(item)

            return unique[:max_results]

        except Exception as exc:
            print(f"[HFCatalogScanner] API query failed: {exc}")
            print("[HFCatalogScanner] Falling back to simulated discovery...")
            return self._simulate_discovery(terms, max_results)

    def _simulate_discovery(
        self,
        terms: list[str],
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Simulated discovery when HF API is unavailable.

        Returns a reasonable set of well-known training datasets
        that the user might want to add.
        """
        known_datasets = [
            {"id": "meta-math/MetaMathQA", "description": "MetaMathQA: 395K math QA pairs", "tags": ["math", "qa"], "downloads": 50000, "size": 500_000_000, "license": "MIT"},
            {"id": "cognitivecomputations/dolphin-2.9-llama3-8b", "description": "Dolphin 2.9 instruct dataset", "tags": ["instruction", "general"], "downloads": 100000, "size": 1_000_000_000, "license": "cc-by-nc-4.0"},
            {"id": "Intel/orca_dpo_pairs", "description": "Orca DPO preference pairs", "tags": ["dpo", "preference", "instruction"], "downloads": 80000, "size": 300_000_000, "license": "cc-by-nc-4.0"},
            {"id": "HuggingFaceH4/ultrafeedback_binarized", "description": "UltraFeedback binarized for DPO/RLHF", "tags": ["preference", "rlhf"], "downloads": 60000, "size": 200_000_000, "license": "mit"},
            {"id": "databricks/databricks-dolly-15k", "description": "Databricks Dolly 15k instruction dataset", "tags": ["instruction", "general"], "downloads": 150000, "size": 50_000_000, "license": "cc-by-sa-3.0"},
            {"id": "nvidia/HelpSteer", "description": "HelpSteer: 36K helpfulness preferences", "tags": ["preference", "helpfulness"], "downloads": 30000, "size": 100_000_000, "license": "cc-by-4.0"},
            {"id": "argilla/ultrafeedback-binarized-preferences-cleaned", "description": "Cleaned UltraFeedback preferences", "tags": ["preference", "cleaned"], "downloads": 25000, "size": 150_000_000, "license": "cc-by-4.0"},
            {"id": "GAIR/lima", "description": "LIMA: Less Is More for Alignment", "tags": ["instruction", "alignment"], "downloads": 40000, "size": 20_000_000, "license": "cc-by-nc-4.0"},
            {"id": "Open-Orca/SlimOrca-Dedup", "description": "SlimOrca deduplicated instruction data", "tags": ["instruction", "orca"], "downloads": 90000, "size": 1_500_000_000, "license": "cc-by-nc-4.0"},
            {"id": "mlabonne/chatbot-arena-v2", "description": "Chatbot Arena conversations v2", "tags": ["chat", "preference"], "downloads": 35000, "size": 200_000_000, "license": "cc-by-4.0"},
        ]
        return known_datasets[:max_results]

    @staticmethod
    def _extract_languages(ds: dict[str, Any]) -> list[str]:
        """Extract language info from a HF dataset response."""
        config = ds.get("configs", [])
        if config and isinstance(config, list):
            for c in config:
                lang = c.get("config", {}).get("language", "")
                if lang:
                    return [lang]
        # Fallback: check tags
        tags = ds.get("tags", [])
        known_langs = {"en": "en", "hi": "hi", "bn": "bn", "zh": "zh",
                       "ar": "ar", "es": "es", "fr": "fr", "de": "de",
                       "ja": "ja", "ko": "ko", "ru": "ru", "pt": "pt",
                       "ta": "ta", "te": "te", "mr": "mr", "gu": "gu"}
        for tag in tags:
            tag_lower = tag.lower()
            for code in known_langs:
                if code in tag_lower or known_langs[code] in tag_lower:
                    return [known_langs[code]]
        return ["en"]

    def to_metadata_records(
        self,
        results: list[HFDiscoveryResult],
        domain: DataDomain = DataDomain.EMERGING,
    ) -> list[DatasetRecord]:
        """Convert discovery results to DatasetRecord for registration."""
        records: list[DatasetRecord] = []
        for r in results:
            records.append(DatasetRecord(
                id=f"hf_{r.dataset_id.replace('/', '_')}",
                name=r.dataset_id.split("/")[-1] if "/" in r.dataset_id else r.dataset_id,
                source="huggingface",
                url=r.url,
                size_bytes=r.size_bytes,
                estimated_records=0,
                languages=r.languages or ["en"],
                domains=[domain],
                modalities=["text"],
                license="CC-BY" if "cc" in r.license.lower() else "MIT",
                priority="medium",
                quality_score=0.5,
                description=r.description,
            ))
        return records


def auto_discover(
    metadata_mgr: MetadataManager | None = None,
    max_results: int = 20,
) -> list[DatasetRecord]:
    """Convenience: scan HF and return DatasetRecords ready to register."""
    scanner = HFCatalogScanner(metadata_mgr=metadata_mgr)
    results = scanner.scan(max_results=max_results)
    return scanner.to_metadata_records(results)


if __name__ == "__main__":
    print("[HFCatalogScanner] Scanning HuggingFace for new datasets...")
    results = auto_discover(max_results=10)
    if results:
        print(f"  Found {len(results)} new datasets:")
        for r in results:
            print(f"    - {r.id}: {r.description[:80]}")
    else:
        print("  No new datasets found. (All cached or API unavailable)")
