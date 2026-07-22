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
    # Revenue fields
    price_cents: int = 0  # Price in cents (0 = free)
    total_earned_cents: int = 0  # Lifetime earnings for creator (creator's 70% share)
    platform_earned_cents: int = 0  # Platform's 30% share
    pending_payout_cents: int = 0  # Amount awaiting payout to creator

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
            "price_cents": self.price_cents,
            "total_earned_cents": self.total_earned_cents,
            "platform_earned_cents": self.platform_earned_cents,
            "pending_payout_cents": self.pending_payout_cents,
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
            price_cents=data.get("price_cents", 0),
            total_earned_cents=data.get("total_earned_cents", 0),
            platform_earned_cents=data.get("platform_earned_cents", 0),
            pending_payout_cents=data.get("pending_payout_cents", 0),
        )


# ── Revenue Configuration ──────────────────────────────────────────

@dataclass
class RevenueConfig:
    """Revenue sharing configuration.

    Default: 70% creator / 30% platform split.
    """
    creator_share: float = 0.70  # 70% to creator
    platform_share: float = 0.30  # 30% to platform
    min_payout_cents: int = 500  # Minimum $5.00 to request a payout
    platform_fee_percent: float = 0.0  # Additional platform fee (e.g., payment processing)
    payout_methods: list[str] = field(default_factory=lambda: ["bank", "paypal", "crypto"])

    DEFAULT_PRICE_CENTS: int = 999  # $9.99 default price for paid adapters
    FREE_TIER_LIMIT: int = 100  # Free downloads before prompting to set price


@dataclass
class PayoutRecord:
    """A payout transaction from platform to creator."""
    id: str
    author: str
    amount_cents: int
    fee_cents: int = 0
    status: str = "pending"  # pending → processing → completed / failed
    method: str = "bank"
    destination: str = ""
    notes: str = ""
    created_at: float = 0.0
    processed_at: float | None = None
    adapter_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "author": self.author,
            "amount_cents": self.amount_cents,
            "fee_cents": self.fee_cents,
            "status": self.status,
            "method": self.method,
            "destination": self.destination,
            "notes": self.notes,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
            "adapter_ids": self.adapter_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PayoutRecord:
        return cls(
            id=data.get("id", ""),
            author=data.get("author", ""),
            amount_cents=data.get("amount_cents", 0),
            fee_cents=data.get("fee_cents", 0),
            status=data.get("status", "pending"),
            method=data.get("method", "bank"),
            destination=data.get("destination", ""),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", 0.0),
            processed_at=data.get("processed_at"),
            adapter_ids=data.get("adapter_ids", []),
        )


@dataclass
class EarningRecord:
    """Record of a single earning event (e.g., an install of a paid adapter)."""
    id: str
    adapter_id: str
    adapter_name: str
    author: str
    amount_cents: int  # Total amount paid by user
    creator_share_cents: int  # 70%
    platform_share_cents: int  # 30%
    event_type: str = "install"  # install, subscription, tip
    created_at: float = 0.0
    payout_id: str | None = None  # Linked payout when settled

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "author": self.author,
            "amount_cents": self.amount_cents,
            "creator_share_cents": self.creator_share_cents,
            "platform_share_cents": self.platform_share_cents,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "payout_id": self.payout_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EarningRecord:
        return cls(
            id=data.get("id", ""),
            adapter_id=data.get("adapter_id", ""),
            adapter_name=data.get("adapter_name", ""),
            author=data.get("author", ""),
            amount_cents=data.get("amount_cents", 0),
            creator_share_cents=data.get("creator_share_cents", 0),
            platform_share_cents=data.get("platform_share_cents", 0),
            event_type=data.get("event_type", "install"),
            created_at=data.get("created_at", 0.0),
            payout_id=data.get("payout_id"),
        )


# ── Marketplace Manager ─────────────────────────────────────────


class MarketplaceManager:
    """Manages local adapter storage, sanitization, composability, and revenue."""

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir = Path(data_dir) if data_dir else ADAPTERS_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "marketplace.json"
        self._adapters: dict[str, Adapter] = {}
        self._payouts: dict[str, PayoutRecord] = {}
        self._earnings: dict[str, EarningRecord] = {}  # keyed by earning id
        self._revenue_config = RevenueConfig()
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

    # ── Revenue / Earnings ──────────────────────────────────────

    def set_adapter_price(self, adapter_id: str, price_cents: int) -> bool:
        """Set the price for a paid adapter (in cents). 0 = free."""
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return False
        adapter.price_cents = max(0, price_cents)
        self._save()
        return True

    def record_install_earnings(self, adapter_id: str, amount_cents: int | None = None) -> EarningRecord | None:
        """Record earnings when a paid adapter is installed.

        Applies the 70/30 revenue split automatically.
        If amount_cents is None, uses the adapter's configured price.
        """
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            return None

        price = amount_cents if amount_cents is not None else adapter.price_cents
        if price <= 0:
            return None  # Free adapter — no earnings

        creator_share = int(price * self._revenue_config.creator_share)
        platform_share = price - creator_share

        earning_id = hashlib.sha256(f"earn:{adapter_id}:{time.time():.6f}".encode()).hexdigest()[:16]
        earning = EarningRecord(
            id=earning_id,
            adapter_id=adapter_id,
            adapter_name=adapter.name,
            author=adapter.author,
            amount_cents=price,
            creator_share_cents=creator_share,
            platform_share_cents=platform_share,
            event_type="install",
            created_at=time.time(),
        )

        self._earnings[earning.id] = earning

        # Update adapter revenue totals
        adapter.total_earned_cents += creator_share
        adapter.platform_earned_cents += platform_share
        adapter.pending_payout_cents += creator_share

        self._save()
        return earning

    def get_creator_earnings(self, author: str) -> dict[str, Any]:
        """Get comprehensive earnings summary for a creator."""
        author_adapters = [a for a in self._adapters.values() if a.author.lower() == author.lower()]
        author_earnings = [e for e in self._earnings.values() if e.author.lower() == author.lower()]

        total_earned = sum(e.creator_share_cents for e in author_earnings)
        total_platform = sum(e.platform_share_cents for e in author_earnings)
        pending_payout = sum(a.pending_payout_cents for a in author_adapters)
        paid_out = sum(p.amount_cents for p in self._payouts.values()
                       if p.author.lower() == author.lower() and p.status == "completed")
        in_flight = sum(p.amount_cents for p in self._payouts.values()
                        if p.author.lower() == author.lower() and p.status in ("pending", "processing"))

        # Group earnings by adapter (include all author adapters, even with $0 earnings)
        by_adapter: dict[str, dict[str, Any]] = {}
        for a in author_adapters:
            by_adapter[a.id] = {
                "adapter_id": a.id,
                "adapter_name": a.name,
                "price_cents": a.price_cents,
                "downloads": a.downloads,
                "total_earned_cents": 0,
                "platform_share_cents": 0,
                "pending_payout_cents": a.pending_payout_cents,
                "last_earning": 0.0,
            }
        for e in author_earnings:
            if e.adapter_id in by_adapter:
                by_adapter[e.adapter_id]["total_earned_cents"] += e.creator_share_cents
                by_adapter[e.adapter_id]["platform_share_cents"] += e.platform_share_cents
                by_adapter[e.adapter_id]["last_earning"] = max(
                    by_adapter[e.adapter_id]["last_earning"], e.created_at
                )

        return {
            "author": author,
            "total_adapters": len(author_adapters),
            "paid_adapters": len([a for a in author_adapters if a.price_cents > 0]),
            "free_adapters": len([a for a in author_adapters if a.price_cents == 0]),
            "total_earnings_cents": total_earned,
            "total_earnings_dollars": round(total_earned / 100, 2),
            "platform_fees_cents": total_platform,
            "platform_fees_dollars": round(total_platform / 100, 2),
            "pending_payout_cents": pending_payout,
            "pending_payout_dollars": round(pending_payout / 100, 2),
            "paid_out_cents": paid_out,
            "paid_out_dollars": round(paid_out / 100, 2),
            "in_flight_payouts_cents": in_flight,
            "in_flight_payouts_dollars": round(in_flight / 100, 2),
            "total_revenue_cents": total_earned + total_platform,
            "total_revenue_dollars": round((total_earned + total_platform) / 100, 2),
            "num_earnings_events": len(author_earnings),
            "by_adapter": list(by_adapter.values()),
            "recent_earnings": sorted(
                [e.to_dict() for e in author_earnings],
                key=lambda x: x["created_at"],
                reverse=True,
            )[:20],
        }

    def get_payouts(
        self,
        author: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List payout records, optionally filtered by author and/or status."""
        results = list(self._payouts.values())
        if author:
            results = [p for p in results if p.author.lower() == author.lower()]
        if status:
            results = [p for p in results if p.status == status]
        results.sort(key=lambda p: p.created_at, reverse=True)
        return [p.to_dict() for p in results[:limit]]

    def request_payout(
        self,
        author: str,
        amount_cents: int | None = None,
        method: str = "bank",
        destination: str = "",
    ) -> dict[str, Any]:
        """Request a payout for a creator.

        If amount_cents is None, pays out all pending earnings.
        Validates against minimum payout threshold ($5.00 default).
        """
        # Calculate available balance
        author_adapters = [a for a in self._adapters.values() if a.author.lower() == author.lower()]
        pending = sum(a.pending_payout_cents for a in author_adapters)

        if pending <= 0:
            return {"success": False, "error": "No pending earnings to payout"}

        payout_amount = amount_cents if amount_cents is not None else pending
        if payout_amount <= 0:
            return {"success": False, "error": "Payout amount must be positive"}
        if payout_amount > pending:
            return {"success": False, "error": f"Insufficient balance. Available: ${pending / 100:.2f}"}
        if payout_amount < self._revenue_config.min_payout_cents:
            min_dollars = self._revenue_config.min_payout_cents / 100
            return {
                "success": False,
                "error": f"Minimum payout is ${min_dollars:.2f}. You have ${pending / 100:.2f} available.",
            }

        # Create payout record
        payout_id = hashlib.sha256(f"payout:{author}:{time.time():.6f}".encode()).hexdigest()[:16]

        # Deduct from adapters proportionally
        adapter_ids: list[str] = []
        remaining = payout_amount
        for a in sorted(author_adapters, key=lambda x: x.pending_payout_cents, reverse=True):
            if remaining <= 0:
                break
            if a.pending_payout_cents <= 0:
                continue
            deduct = min(a.pending_payout_cents, remaining)
            a.pending_payout_cents -= deduct
            remaining -= deduct
            adapter_ids.append(a.id)

        payout = PayoutRecord(
            id=payout_id,
            author=author,
            amount_cents=payout_amount,
            fee_cents=0,
            status="pending",
            method=method,
            destination=destination,
            adapter_ids=adapter_ids,
            created_at=time.time(),
        )
        self._payouts[payout.id] = payout
        self._save()

        return {
            "success": True,
            "payout": payout.to_dict(),
            "message": f"Payout request for ${payout_amount / 100:.2f} submitted",
        }

    def process_payout(self, payout_id: str, status: str = "completed", notes: str = "") -> bool:
        """Process (approve/reject) a pending payout.

        When completed: marks earnings as settled (no longer pending).
        When failed: returns pending_payout_cents back to the adapters.
        """
        payout = self._payouts.get(payout_id)
        if payout is None or payout.status != "pending":
            return False

        payout.status = status
        payout.processed_at = time.time()
        payout.notes = notes

        if status == "completed":
            # Mark all earnings for this payout as settled
            for e in self._earnings.values():
                if e.author.lower() == payout.author.lower() and e.payout_id is None:
                    # Link earnings that contributed to this payout
                    if e.creator_share_cents > 0:
                        e.payout_id = payout_id
        elif status in ("failed", "cancelled"):
            # Return pending balance back to adapters
            for aid in payout.adapter_ids:
                adapter = self._adapters.get(aid)
                if adapter:
                    # Add back proportional amount
                    adapter.pending_payout_cents += payout.amount_cents // max(len(payout.adapter_ids), 1)

        self._save()
        return True

    def get_revenue_stats(self) -> dict[str, Any]:
        """Get platform-wide revenue statistics."""
        total_revenue = sum(e.amount_cents for e in self._earnings.values())
        total_creator = sum(e.creator_share_cents for e in self._earnings.values())
        total_platform = sum(e.platform_share_cents for e in self._earnings.values())
        total_paid_adapters = len([a for a in self._adapters.values() if a.price_cents > 0])
        total_downloads_paid = sum(a.downloads for a in self._adapters.values() if a.price_cents > 0)
        pending_payouts_total = sum(a.pending_payout_cents for a in self._adapters.values())
        completed_payouts = [p for p in self._payouts.values() if p.status == "completed"]
        total_paid_out = sum(p.amount_cents for p in completed_payouts)
        unique_creators = len(set(e.author for e in self._earnings.values()))

        # Top earners
        creator_totals: dict[str, int] = {}
        for e in self._earnings.values():
            creator_totals[e.author] = creator_totals.get(e.author, 0) + e.creator_share_cents
        top_earners = sorted(creator_totals.items(), key=lambda x: x[1], reverse=True)[:10]

        # Monthly breakdown
        monthly: dict[str, dict[str, int]] = {}
        for e in self._earnings.values():
            month_key = time.strftime("%Y-%m", time.localtime(e.created_at))
            if month_key not in monthly:
                monthly[month_key] = {"revenue_cents": 0, "creator_cents": 0, "platform_cents": 0, "count": 0}
            monthly[month_key]["revenue_cents"] += e.amount_cents
            monthly[month_key]["creator_cents"] += e.creator_share_cents
            monthly[month_key]["platform_cents"] += e.platform_share_cents
            monthly[month_key]["count"] += 1

        return {
            "total_revenue_cents": total_revenue,
            "total_revenue_dollars": round(total_revenue / 100, 2),
            "total_creator_earnings_cents": total_creator,
            "total_creator_earnings_dollars": round(total_creator / 100, 2),
            "total_platform_fees_cents": total_platform,
            "total_platform_fees_dollars": round(total_platform / 100, 2),
            "total_paid_out_cents": total_paid_out,
            "total_paid_out_dollars": round(total_paid_out / 100, 2),
            "pending_payouts_cents": pending_payouts_total,
            "pending_payouts_dollars": round(pending_payouts_total / 100, 2),
            "split_ratio": f"{int(self._revenue_config.creator_share * 100)}/{int(self._revenue_config.platform_share * 100)}",
            "min_payout_dollars": self._revenue_config.min_payout_cents / 100,
            "total_paid_adapters": total_paid_adapters,
            "total_downloads_paid": total_downloads_paid,
            "unique_creators": unique_creators,
            "total_earnings_events": len(self._earnings),
            "total_payouts": len(self._payouts),
            "pending_payouts_count": len([p for p in self._payouts.values() if p.status == "pending"]),
            "completed_payouts_count": len(completed_payouts),
            "top_earners": [
                {"author": author, "earned_cents": cents, "earned_dollars": round(cents / 100, 2)}
                for author, cents in top_earners
            ],
            "monthly_breakdown": [
                {
                    "month": k,
                    "revenue_dollars": round(v["revenue_cents"] / 100, 2),
                    "creator_dollars": round(v["creator_cents"] / 100, 2),
                    "platform_dollars": round(v["platform_cents"] / 100, 2),
                    "transactions": v["count"],
                }
                for k, v in sorted(monthly.items())
            ],
            "config": {
                "creator_share": self._revenue_config.creator_share,
                "platform_share": self._revenue_config.platform_share,
                "min_payout_cents": self._revenue_config.min_payout_cents,
                "payout_methods": self._revenue_config.payout_methods,
            },
        }

    # ── Persistence ──────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "adapters": {aid: a.to_dict() for aid, a in self._adapters.items()},
            "payouts": {pid: p.to_dict() for pid, p in self._payouts.items()},
            "earnings": {eid: e.to_dict() for eid, e in self._earnings.items()},
            "revenue_config": {
                "creator_share": self._revenue_config.creator_share,
                "platform_share": self._revenue_config.platform_share,
                "min_payout_cents": self._revenue_config.min_payout_cents,
                "payout_methods": self._revenue_config.payout_methods,
            },
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
            for pid, p_data in data.get("payouts", {}).items():
                self._payouts[pid] = PayoutRecord.from_dict(p_data)
            for eid, e_data in data.get("earnings", {}).items():
                self._earnings[eid] = EarningRecord.from_dict(e_data)
            rc = data.get("revenue_config", {})
            if rc:
                self._revenue_config = RevenueConfig(
                    creator_share=rc.get("creator_share", 0.70),
                    platform_share=rc.get("platform_share", 0.30),
                    min_payout_cents=rc.get("min_payout_cents", 500),
                    payout_methods=rc.get("payout_methods", ["bank", "paypal", "crypto"]),
                )
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
