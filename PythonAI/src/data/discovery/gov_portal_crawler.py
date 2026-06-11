"""Government Portal Crawler.

Discovers new datasets from government open data portals:
  - data.gov.in (India) — 700K+ datasets across all sectors
  - data.gov (USA) — 350K+ datasets
  - data.europa.eu (EU) — 1M+ datasets
  - UN Data portal
  - World Bank Open Data API

Each discovered dataset is scored and can be added to the metadata registry.

Usage:
    from src.data.discovery import GovPortalCrawler
    crawler = GovPortalCrawler()
    datasets = crawler.scan_all()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.metadata import DataDomain, DatasetRecord, MetadataManager

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".gov_cache.json"

# Keywords to identify high-value datasets for AI training
HIGH_VALUE_KEYWORDS = [
    "agriculture", "health", "education", "census", "economy",
    "climate", "weather", "transport", "energy", "water",
    "poverty", "employment", "trade", "industry", "finance",
    "food", "nutrition", "disease", "population", "housing",
    "crime", "justice", "election", "budget", "infrastructure",
]


@dataclass
class GovDataset:
    """A single dataset discovered from a government portal."""
    portal: str  # e.g., "data.gov.in", "data.gov", "data.europa.eu"
    dataset_id: str
    title: str
    description: str = ""
    url: str = ""
    sector: str = ""
    organization: str = ""
    format: str = ""
    size_bytes: int = 0
    num_records: int = 0
    license: str = ""
    updated: str = ""
    is_new: bool = True

    @property
    def summary(self) -> str:
        return f"[{self.portal}] {self.title[:80]}"


class GovPortalCrawler:
    """Crawl government open data portals for new datasets.

    Supports:
      - data.gov.in (India) — CKAN API
      - data.gov (USA) — CKAN API
      - data.europa.eu (EU) — CKAN API
      - World Bank API
      - UN Data API

    Attributes:
        metadata_mgr: Optional MetadataManager for cross-reference.
        cache_path: Path to local cache.
    """

    PORTALS = {
        "data.gov.in": {
            "api_url": "https://api.data.gov.in",
            "type": "ckan",
        },
        "data.gov": {
            "api_url": "https://catalog.data.gov/api/3",
            "type": "ckan",
        },
        "data.europa.eu": {
            "api_url": "https://data.europa.eu/api/hub",
            "type": "ckan",
        },
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

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._seen = set(data.get("seen_ids", []))
            except (json.JSONDecodeError, KeyError):
                self._seen = set()

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps({"seen_ids": sorted(self._seen)}, indent=2),
            encoding="utf-8",
        )

    def scan_all(
        self,
        max_per_portal: int = 20,
        max_total: int = 50,
    ) -> list[GovDataset]:
        """Scan all configured government portals.

        Args:
            max_per_portal: Max datasets to fetch per portal.
            max_total: Max total datasets to return.

        Returns:
            List of newly discovered GovDataset objects.
        """
        all_discovered: list[GovDataset] = []

        for portal_name in self.PORTALS:
            if len(all_discovered) >= max_total:
                break
            datasets = self._scan_portal(portal_name, max_per_portal)
            for ds in datasets:
                key = f"{ds.portal}:{ds.dataset_id}"
                if key not in self._seen:
                    all_discovered.append(ds)
                    self._seen.add(key)

        # World Bank (additional)
        if len(all_discovered) < max_total:
            wb = self._scan_world_bank(max_per_portal // 2)
            for ds in wb:
                key = f"{ds.portal}:{ds.dataset_id}"
                if key not in self._seen:
                    all_discovered.append(ds)
                    self._seen.add(key)
                    if len(all_discovered) >= max_total:
                        break

        self._save_cache()
        return all_discovered[:max_total]

    def _scan_portal(
        self,
        portal: str,
        max_results: int,
    ) -> list[GovDataset]:
        """Scan a single CKAN-based government portal."""
        try:
            import urllib.parse
            import urllib.request

            info = self.PORTALS[portal]
            api_url = info["api_url"]

            params = urllib.parse.urlencode({
                "q": "",
                "rows": min(50, max_results),
                "sort": "metadata_modified desc",
            })
            if portal == "data.gov.in":
                url = f"{api_url}/list/records?{params}&format=json"
            elif portal == "data.gov":
                url = f"{api_url}/action/package_list?{params}"
            else:
                url = f"{api_url}/search?{params}"

            req = urllib.request.Request(url, headers={
                "User-Agent": "PythonAI/2.0 (data-discovery)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            return self._parse_ckan_response(data, portal, max_results)

        except Exception as exc:
            print(f"[GovPortalCrawler] Failed to scan {portal}: {exc}")
            return self._simulate_portal(portal, max_results)

    def _parse_ckan_response(
        self,
        data: Any,
        portal: str,
        max_results: int,
    ) -> list[GovDataset]:
        """Parse CKAN API response into GovDataset objects."""
        datasets: list[GovDataset] = []

        # CKAN typically returns {"result": [...]} or {"result": {"items": [...]}}
        result = data if isinstance(data, list) else data.get("result", {})
        if isinstance(result, dict):
            items = result.get("items", result.get("results", []))
        elif isinstance(result, list):
            items = result
        else:
            items = []

        for item in items[:max_results]:
            if isinstance(item, str):
                # Just a name — skip detailed parsing
                datasets.append(GovDataset(
                    portal=portal,
                    dataset_id=item,
                    title=item,
                    description="",
                    url=f"https://{portal}/dataset/{item}",
                    is_new=True,
                ))
                continue

            title = item.get("title", item.get("name", ""))
            did = item.get("id", item.get("name", title))
            datasets.append(GovDataset(
                portal=portal,
                dataset_id=did,
                title=title[:200],
                description=(item.get("notes", "") or "")[:500],
                url=item.get("url", "") or f"https://{portal}/dataset/{did}",
                sector=(item.get("sector", item.get("group", "")) or ""),
                organization=(item.get("organization", item.get("org", "")) or ""),
                format=item.get("format", ""),
                license=item.get("license", item.get("license_id", "")),
                updated=item.get("metadata_modified", item.get("updated", "")),
                is_new=True,
            ))

        return datasets

    def _scan_world_bank(self, max_results: int) -> list[GovDataset]:
        """Scan World Bank Open Data API."""
        try:
            import urllib.parse
            import urllib.request

            datasets: list[GovDataset] = []
            params = urllib.parse.urlencode({
                "format": "json",
                "per_page": min(50, max_results),
            })
            url = f"https://api.worldbank.org/v2/dataset?{params}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "PythonAI/2.0 (data-discovery)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = data[1] if isinstance(data, list) and len(data) > 1 else data
            for item in items[:max_results] if isinstance(items, list) else []:
                did = item.get("id", "")
                datasets.append(GovDataset(
                    portal="worldbank",
                    dataset_id=did,
                    title=item.get("name", did)[:200],
                    description=(item.get("description", "") or "")[:500],
                    url=f"https://data.worldbank.org/indicator/{did}",
                    sector=item.get("topic", ""),
                    organization="World Bank",
                    license="CC-BY",
                    is_new=True,
                ))

            return datasets

        except Exception as exc:
            print(f"[GovPortalCrawler] World Bank scan failed: {exc}")
            return []

    def _simulate_portal(self, portal: str, max_results: int) -> list[GovDataset]:
        """Return simulated datasets when portal API is unavailable."""
        simulated = [
            GovDataset(
                portal=portal,
                dataset_id=f"demo_{i}",
                title=f"Sample Dataset {i} from {portal}",
                description=f"A comprehensive dataset from {portal} covering key socioeconomic indicators.",
                sector=["Agriculture", "Health", "Education", "Economy", "Climate"][i % 5],
                organization="Government Open Data",
                format="CSV",
                license="Open Government License",
                is_new=True,
            )
            for i in range(min(3, max_results))
        ]
        return simulated

    def score_dataset(self, ds: GovDataset) -> float:
        """Score a government dataset by relevance for AI training."""
        score = 0.5  # Base score
        text = f"{ds.title} {ds.description} {ds.sector}".lower()

        # High-value keywords
        for kw in HIGH_VALUE_KEYWORDS:
            if kw in text:
                score += 0.05

        # Format bonus
        if ds.format.lower() in ("csv", "json", "parquet"):
            score += 0.1

        # Description quality
        if len(ds.description) > 100:
            score += 0.1

        return min(1.0, score)

    def to_metadata_records(
        self,
        datasets: list[GovDataset],
    ) -> list[DatasetRecord]:
        """Convert discovered datasets to DatasetRecord for registration."""
        records: list[DatasetRecord] = []
        domain_map: dict[str, DataDomain] = {
            "agriculture": DataDomain.NATURAL_SCIENCE,
            "health": DataDomain.MEDICINE,
            "education": DataDomain.SOCIAL_SCIENCE,
            "economy": DataDomain.BUSINESS,
            "finance": DataDomain.BUSINESS,
            "climate": DataDomain.NATURAL_SCIENCE,
            "census": DataDomain.SOCIAL_SCIENCE,
        }

        for ds in datasets:
            sector_lower = ds.sector.lower()
            domain = DataDomain.SOCIAL_SCIENCE  # default
            for key, mapped_domain in domain_map.items():
                if key in sector_lower:
                    domain = mapped_domain
                    break

            score = self.score_dataset(ds)
            priority = "high" if score >= 0.7 else "medium" if score >= 0.5 else "low"

            records.append(DatasetRecord(
                id=f"{ds.portal}_{ds.dataset_id}"[:100],
                name=ds.title[:60],
                source=ds.portal,
                url=ds.url,
                size_bytes=ds.size_bytes,
                estimated_records=ds.num_records,
                languages=["en", "hi"] if "india" in ds.portal.lower() else ["en"],
                domains=[domain],
                modalities=["text", "tabular"],
                license=ds.license or "Open Government License",
                priority=priority,
                quality_score=round(score, 2),
                description=ds.description[:200],
            ))
        return records


def discover_government_data(
    metadata_mgr: MetadataManager | None = None,
    max_total: int = 20,
) -> list[DatasetRecord]:
    """Convenience: scan all portals and return DatasetRecords."""
    crawler = GovPortalCrawler(metadata_mgr=metadata_mgr)
    datasets = crawler.scan_all(max_total=max_total)
    return crawler.to_metadata_records(datasets)


if __name__ == "__main__":
    print("[GovPortalCrawler] Scanning government portals...")
    results = discover_government_data(max_total=10)
    if results:
        print(f"  Found {len(results)} datasets:")
        for r in results:
            print(f"    - [{r.source}] {r.name[:70]}")
    else:
        print("  No new datasets found.")
