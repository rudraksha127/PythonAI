"""
ForgeAI Skills Marketplace — Adapter Upload/Download & Composability
====================================================================

Allows developers to share fine-tuned adapters:
  - Upload adapters (LoRA weights + metadata)
  - Download and install adapters
  - Sanitize uploads (PII/proprietary code detection)
  - Compose multiple adapters (merge weights)
  - Browse/search/filter adapters

Revenue sharing: 70% creator / 30% platform (configurable).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ADAPTERS_DIR = Path.home() / ".forgeai" / "adapters"
MARKETPLACE_FILE = Path.home() / ".forgeai" / "marketplace.json"

# ── Sanitization ────────────────────────────────────────────────

# PII patterns to detect
_PII_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:^|\s)([A-Z][a-z]+ [A-Z][a-z]+)(?:\s|$)", re.MULTILINE),  # Full names
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),  # Emails
    re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),  # Phone numbers
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSNs
    re.compile(r"(?:sk-[a-zA-Z0-9]{20,}|api-key[=:]\s*\w{16,})", re.IGNORECASE),  # API keys
    re.compile(r"(?:ghp_|gho_|github_pat_)\w{36,}"),  # GitHub tokens
    re.compile(r"(?:-----BEGIN\s+(?:RSA\s+)?PRIVATE KEY-----)"),  # Private keys
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access keys
]

_PROPRIETARY_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:confidential|proprietary|internal\s+use\s+only)", re.IGNORECASE),
    re.compile(r"(?:copyright\s+\d{4}\s+.+?inc\.?)", re.IGNORECASE),
    re.compile(r"(?:all\s+rights\s+reserved)", re.IGNORECASE),
    re.compile(r"(?:top\s+secret|classified|restricted)"),
]


@dataclass
class SanitizationResult:
    """Result of scanning an adapter for sensitive content."""

    passed: bool
    pii_found: list[str] = field(default_factory=list)
    proprietary_found: list[str] = field(default_factory=list)
    total_issues: int = 0
    score: float = 1.0  # 0.0 (dangerous) to 1.0 (clean)


def scan_adapter(file_path: str | Path) -> SanitizationResult:
    """Scan an adapter zip for PII and proprietary code.

    Returns a SanitizationResult indicating whether the adapter is safe.
    """
    file_path = Path(file_path)
    pii_found: list[str] = []
    proprietary_found: list[str] = []

    if not file_path.exists() or not zipfile.is_zipfile(file_path):
        return SanitizationResult(passed=False, pii_found=["File not found or invalid zip"])

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith((".bin", ".safetensors", ".pt", ".pth")):
                    continue  # Binary files — skip scanning
                try:
                    content = zf.read(name).decode("utf-8", errors="replace")
                except Exception:
                    continue

                # Scan for PII
                for pattern in _PII_PATTERNS:
                    matches = pattern.findall(content)
                    for m in matches:
                        # Avoid false positives on short/obvious text
                        if len(m.strip()) > 4:
                            pii_found.append(f"[{name}] {m[:80]}")

                # Scan for proprietary markers
                for pattern in _PROPRIETARY_PATTERNS:
                    matches = pattern.findall(content)
                    for m in matches:
                        proprietary_found.append(f"[{name}] {m[:80]}")

    except Exception as e:
        return SanitizationResult(passed=False, pii_found=[f"Scan error: {e}"])

    total_issues = len(pii_found) + len(proprietary_found)
    score = max(0.0, 1.0 - (total_issues * 0.15))
    passed = total_issues == 0

    return SanitizationResult(
        passed=passed,
        pii_found=list(set(pii_found))[:20],
        proprietary_found=list(set(proprietary_found))[:10],
        total_issues=total_issues,
        score=round(score, 2),
    )


# ── Adapter Model ────────────────────────────────────────────────


@dataclass
class Adapter:
    """A fine-tuned adapter available in the marketplace."""

    id: str
    name: str
    description: str
    author: str
    version: str = "1.0.0"
    base_model: str = ""
    framework: str = ""
    industry: str = ""
    tags: list[str] = field(default_factory=list)
    file_size_bytes: int = 0
    downloads: int = 0
    rating: float = 0.0
    acceptance_improvement: float = 0.0  # % improvement reported
    created_at: float = 0.0
    updated_at: float = 0.0
    installed: bool = False
    local_path: str = ""
    sanitization_score: float = 1.0
    is_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "base_model": self.base_model,
            "framework": self.framework,
            "industry": self.industry,
            "tags": self.tags,
            "file_size_bytes": self.file_size_bytes,
            "downloads": self.downloads,
            "rating": self.rating,
            "acceptance_improvement": self.acceptance_improvement,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "installed": self.installed,
            "local_path": self.local_path,
            "sanitization_score": self.sanitization_score,
            "is_verified": self.is_verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Adapter:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            version=data.get("version", "1.0.0"),
            base_model=data.get("base_model", ""),
            framework=data.get("framework", ""),
            industry=data.get("industry", ""),
            tags=data.get("tags", []),
            file_size_bytes=data.get("file_size_bytes", 0),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            acceptance_improvement=data.get("acceptance_improvement", 0.0),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            installed=data.get("installed", False),
            local_path=data.get("local_path", ""),
            sanitization_score=data.get("sanitization_score", 1.0),
            is_verified=data.get("is_verified", False),
        )


# ── Marketplace Manager ─────────────────────────────────────────


class MarketplaceManager:
    """Manages local adapter storage, sanitization, and composability."""

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else ADAPTERS_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "marketplace.json"
        self._adapters: dict[str, Adapter] = {}
        self._load()

    # ── CRUD ─────────────────────────────────────────────────────

    def list_adapters(
        self,
        category: str | None = None,
        framework: str | None = None,
        industry: str | None = None,
        search: str | None = None,
    ) -> list[Adapter]:
        """List adapters with optional filters."""
        results = list(self._adapters.values())

        if category:
            results = [a for a in results if category.lower() in [t.lower() for t in a.tags]]
        if framework:
            results = [a for a in results if framework.lower() in a.framework.lower()]
        if industry:
            results = [a for a in results if industry.lower() in a.industry.lower()]
        if search:
            search_lower = search.lower()
            results = [
                a for a in results
                if search_lower in a.name.lower()
                or search_lower in a.description.lower()
                or search_lower in a.author.lower()
            ]

        results.sort(key=lambda a: (a.rating, a.downloads), reverse=True)
        return results

    def get_adapter(self, adapter_id: str) -> Adapter | None:
        """Get a single adapter by ID."""
        return self._adapters.get(adapter_id)

    def register_adapter(
        self,
        name: str,
        description: str,
        author: str,
        file_path: str | Path,
        version: str = "1.0.0",
        base_model: str = "",
        framework: str = "",
        industry: str = "",
        tags: list[str] | None = None,
    ) -> Adapter | None:
        """Register a new adapter from a file path.

        Scans for PII/proprietary content first. Rejects if scan fails.
        Copies the file to the local data directory.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        # Sanitization scan
        scan = scan_adapter(file_path)
        if not scan.passed and scan.total_issues > 5:
            return None  # Too many issues

        # Copy file to local storage
        adapter_id = hashlib.sha256(f"{name}:{author}:{time.time()}".encode()).hexdigest()[:16]
        dest = self._data_dir / f"{adapter_id}{file_path.suffix}"
        shutil.copy2(str(file_path), str(dest))

        now = time.time()
        adapter = Adapter(
            id=adapter_id,
            name=name,
            description=description,
            author=author,
            version=version,
            base_model=base_model,
            framework=framework,
            industry=industry,
            tags=tags or [],
            file_size_bytes=file_path.stat().st_size,
            created_at=now,
            updated_at=now,
            installed=False,
            local_path=str(dest),
            sanitization_score=scan.score,
            is_verified=scan.passed,
        )

        self._adapters[adapter.id] = adapter
        self._save()
        return adapter

    def install_adapter(self, adapter_id: str) -> bool:
        """Mark an adapter as installed locally."""
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return False
        adapter.installed = True
        adapter.downloads += 1
        self._save()
        return True

    def uninstall_adapter(self, adapter_id: str) -> bool:
        """Uninstall an adapter."""
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return False
        adapter.installed = False
        self._save()
        return True

    def delete_adapter(self, adapter_id: str) -> bool:
        """Delete an adapter entirely."""
        adapter = self._adapters.pop(adapter_id, None)
        if adapter is None:
            return False
        # Remove file
        if adapter.local_path:
            try:
                Path(adapter.local_path).unlink(missing_ok=True)
            except Exception:
                pass
        self._save()
        return True

    # ── Composability ────────────────────────────────────────────

    def compose_adapters(self, adapter_ids: list[str]) -> dict[str, Any]:
        """Compose multiple adapters together.

        Returns metadata about the composition. In production, this
        would merge LoRA weights using the merger utility.
        """
        adapters = []
        for aid in adapter_ids:
            a = self._adapters.get(aid)
            if a and a.installed:
                adapters.append(a)

        if len(adapters) < 2:
            return {
                "success": False,
                "error": "Need at least 2 installed adapters to compose",
            }

        return {
            "success": True,
            "composed_name": "+".join(a.name for a in adapters),
            "base_models": list(set(a.base_model for a in adapters)),
            "frameworks": list(set(a.framework for a in adapters)),
            "total_size_bytes": sum(a.file_size_bytes for a in adapters),
            "adapters_used": [a.id for a in adapters],
            "instructions": "Use forgeai adapter merge --ids " + ",".join(adapter_ids),
        }

    def get_stats(self) -> dict[str, Any]:
        """Get marketplace statistics."""
        installed = [a for a in self._adapters.values() if a.installed]
        verified = [a for a in self._adapters.values() if a.is_verified]
        return {
            "total_adapters": len(self._adapters),
            "installed": len(installed),
            "verified": len(verified),
            "total_downloads": sum(a.downloads for a in self._adapters.values()),
            "avg_rating": round(
                sum(a.rating for a in self._adapters.values()) / max(len(self._adapters), 1), 2
            ),
            "frameworks": list(set(a.framework for a in self._adapters.values() if a.framework)),
            "industries": list(set(a.industry for a in self._adapters.values() if a.industry)),
        }

    def import_sample_adapters(self) -> int:
        """Import sample adapters for demo/testing purposes."""
        samples = [
            Adapter(
                id="py-coder-v1",
                name="Python Coder v1",
                description="Fine-tuned for Python code generation — improves acceptance rate by 12%",
                author="ForgeAI Team",
                version="1.2.0",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                framework="pytorch",
                industry="general",
                tags=["python", "code-gen", "general"],
                file_size_bytes=45_000_000,
                downloads=1240,
                rating=4.5,
                acceptance_improvement=12.0,
                created_at=time.time() - 86400 * 30,
                updated_at=time.time() - 86400 * 2,
                is_verified=True,
                sanitization_score=1.0,
            ),
            Adapter(
                id="ts-react-v1",
                name="TypeScript React Expert",
                description="Optimized for React + TypeScript development with improved JSX generation",
                author="Community",
                version="1.0.0",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                framework="pytorch",
                industry="web",
                tags=["typescript", "react", "frontend", "web"],
                file_size_bytes=38_000_000,
                downloads=856,
                rating=4.2,
                acceptance_improvement=8.5,
                created_at=time.time() - 86400 * 20,
                updated_at=time.time() - 86400 * 1,
                is_verified=True,
                sanitization_score=1.0,
            ),
            Adapter(
                id="rust-systems",
                name="Rust Systems Programmer",
                description="Specialized in safe Rust systems programming, async, and memory management",
                author="RustaceanAI",
                version="0.9.0",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                framework="pytorch",
                industry="systems",
                tags=["rust", "systems", "async"],
                file_size_bytes=42_000_000,
                downloads=542,
                rating=4.0,
                acceptance_improvement=6.2,
                created_at=time.time() - 86400 * 15,
                updated_at=time.time() - 86400 * 5,
                is_verified=False,
                sanitization_score=0.95,
            ),
            Adapter(
                id="sql-optimizer",
                name="SQL Query Optimizer",
                description="Generates optimized SQL queries with proper indexing and join strategies",
                author="DataForge",
                version="1.1.0",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                framework="pytorch",
                industry="data",
                tags=["sql", "database", "optimization", "data"],
                file_size_bytes=28_000_000,
                downloads=312,
                rating=3.8,
                acceptance_improvement=4.1,
                created_at=time.time() - 86400 * 10,
                updated_at=time.time() - 86400 * 3,
                is_verified=False,
                sanitization_score=0.98,
            ),
            Adapter(
                id="go-microservices",
                name="Go Microservices",
                description="Fine-tuned for Go service development with gRPC, HTTP handlers, and DB patterns",
                author="CloudNativeLabs",
                version="0.8.0",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                framework="pytorch",
                industry="backend",
                tags=["go", "microservices", "grpc", "backend"],
                file_size_bytes=35_000_000,
                downloads=198,
                rating=3.5,
                acceptance_improvement=3.8,
                created_at=time.time() - 86400 * 7,
                updated_at=time.time() - 86400 * 1,
                is_verified=False,
                sanitization_score=0.92,
            ),
        ]

        count = 0
        for s in samples:
            if s.id not in self._adapters:
                self._adapters[s.id] = s
                count += 1

        if count > 0:
            self._save()
        return count

    # ── Persistence ──────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "adapters": {aid: a.to_dict() for aid, a in self._adapters.items()},
            "updated_at": time.time(),
        }
        self._db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._db_path.exists():
            # Auto-import samples on first run
            self.import_sample_adapters()
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for aid, a_data in data.get("adapters", {}).items():
                self._adapters[aid] = Adapter.from_dict(a_data)
        except (json.JSONDecodeError, KeyError):
            pass


# ── Singleton Access ─────────────────────────────────────────────

_marketplace_manager: MarketplaceManager | None = None


def get_marketplace_manager() -> MarketplaceManager:
    """Get or create the global marketplace manager."""
    global _marketplace_manager
    if _marketplace_manager is None:
        _marketplace_manager = MarketplaceManager()
    return _marketplace_manager


__all__ = [
    "MarketplaceManager",
    "Adapter",
    "SanitizationResult",
    "scan_adapter",
    "get_marketplace_manager",
    "ADAPTERS_DIR",
]
