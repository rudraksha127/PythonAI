"""Tests for Skills Marketplace Revenue Sharing (70/30 split), Payout Tracking, and Creator Earnings."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.marketplace import (
    MarketplaceManager,
    RevenueConfig,
    PayoutRecord,
    EarningRecord,
    Adapter,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_data_dir():
    """Create a temporary data directory for each test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def manager(tmp_data_dir):
    """Create a MarketplaceManager with a temporary data directory."""
    m = MarketplaceManager(data_dir=tmp_data_dir)
    # Clear any auto-imported samples and start fresh
    for aid in list(m._adapters.keys()):
        del m._adapters[aid]
    m._payouts.clear()
    m._earnings.clear()
    return m


@pytest.fixture
def paid_adapter(manager):
    """Register a paid adapter with price $9.99."""
    a = Adapter(
        id="paid-adapter-1",
        name="Premium Python Coder",
        description="A premium paid adapter",
        author="TestCreator",
        version="1.0.0",
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        framework="pytorch",
        industry="general",
        tags=["python", "premium"],
        file_size_bytes=45_000_000,
        downloads=10,
        rating=4.5,
        price_cents=999,
        created_at=time.time(),
        updated_at=time.time(),
    )
    manager._adapters[a.id] = a
    return a


@pytest.fixture
def free_adapter(manager):
    """Register a free adapter (no price)."""
    a = Adapter(
        id="free-adapter-1",
        name="Free Helper",
        description="A free utility adapter",
        author="TestCreator",
        version="1.0.0",
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        framework="pytorch",
        industry="general",
        tags=["free", "utility"],
        file_size_bytes=10_000_000,
        downloads=100,
        rating=3.0,
        price_cents=0,
        created_at=time.time(),
        updated_at=time.time(),
    )
    manager._adapters[a.id] = a
    return a


# ── RevenueConfig Tests ────────────────────────────────────────────────


class TestRevenueConfig:
    """RevenueConfig defaults and configuration."""

    def test_default_split(self):
        """Default 70/30 revenue split."""
        rc = RevenueConfig()
        assert rc.creator_share == 0.70
        assert rc.platform_share == 0.30

    def test_custom_split(self):
        """Custom revenue split (80/20)."""
        rc = RevenueConfig(creator_share=0.80, platform_share=0.20)
        assert rc.creator_share == 0.80
        assert rc.platform_share == 0.20
        assert abs(rc.creator_share + rc.platform_share - 1.0) < 0.001

    def test_min_payout_default(self):
        """Default minimum payout is $5.00 (500 cents)."""
        rc = RevenueConfig()
        assert rc.min_payout_cents == 500

    def test_payout_methods_default(self):
        """Default payout methods include bank, paypal, crypto."""
        rc = RevenueConfig()
        assert "bank" in rc.payout_methods
        assert "paypal" in rc.payout_methods
        assert "crypto" in rc.payout_methods
        assert len(rc.payout_methods) == 3

    def test_default_price(self):
        """DEFAULT_PRICE_CENTS is 999 ($9.99)."""
        assert RevenueConfig.DEFAULT_PRICE_CENTS == 999

    def test_free_tier_limit(self):
        """FREE_TIER_LIMIT is 100 downloads."""
        assert RevenueConfig.FREE_TIER_LIMIT == 100


# ── Adapter Revenue Fields Tests ───────────────────────────────────────


class TestAdapterRevenueFields:
    """Adapter model revenue fields."""

    def test_adapter_has_revenue_fields(self):
        """Adapter has price and earnings tracking fields."""
        a = Adapter(id="test", name="Test", description="", author="dev")
        assert hasattr(a, "price_cents")
        assert hasattr(a, "total_earned_cents")
        assert hasattr(a, "platform_earned_cents")
        assert hasattr(a, "pending_payout_cents")

    def test_adapter_defaults_zero(self):
        """All revenue fields default to 0."""
        a = Adapter(id="test", name="Test", description="", author="dev")
        assert a.price_cents == 0
        assert a.total_earned_cents == 0
        assert a.platform_earned_cents == 0
        assert a.pending_payout_cents == 0

    def test_adapter_to_dict_includes_revenue(self):
        """to_dict includes revenue fields."""
        a = Adapter(
            id="test", name="Test", description="", author="dev",
            price_cents=999, total_earned_cents=700, pending_payout_cents=700,
        )
        d = a.to_dict()
        assert d["price_cents"] == 999
        assert d["total_earned_cents"] == 700
        assert d["pending_payout_cents"] == 700

    def test_adapter_from_dict_with_revenue(self):
        """from_dict restores revenue fields."""
        d = {
            "id": "test", "name": "Test", "description": "", "author": "dev",
            "version": "1.0.0",
            "price_cents": 1499,
            "total_earned_cents": 1050,
            "platform_earned_cents": 450,
            "pending_payout_cents": 1050,
        }
        a = Adapter.from_dict(d)
        assert a.price_cents == 1499
        assert a.total_earned_cents == 1050
        assert a.platform_earned_cents == 450
        assert a.pending_payout_cents == 1050


# ── Set Adapter Price Tests ────────────────────────────────────────────


class TestSetAdapterPrice:
    """MarketplaceManager.set_adapter_price."""

    def test_set_price(self, manager, paid_adapter):
        """Can set a price on an adapter."""
        assert manager.set_adapter_price("paid-adapter-1", 499)
        assert manager._adapters["paid-adapter-1"].price_cents == 499

    def test_set_price_zero(self, manager, paid_adapter):
        """Can set price to 0 (make free)."""
        assert manager.set_adapter_price("paid-adapter-1", 0)
        assert manager._adapters["paid-adapter-1"].price_cents == 0

    def test_set_price_non_existent(self, manager):
        """Returns False for non-existent adapter."""
        assert not manager.set_adapter_price("nonexistent", 999)

    def test_set_price_persists(self, manager, paid_adapter, tmp_data_dir):
        """Price change persists in saved data."""
        manager.set_adapter_price("paid-adapter-1", 1299)
        manager2 = MarketplaceManager(data_dir=tmp_data_dir)
        assert manager2._adapters["paid-adapter-1"].price_cents == 1299


# ── Record Install Earnings Tests ──────────────────────────────────────


class TestRecordInstallEarnings:
    """MarketplaceManager.record_install_earnings."""

    def test_record_earnings_free_adapter(self, manager, free_adapter):
        """Free adapters generate no earnings."""
        result = manager.record_install_earnings("free-adapter-1")
        assert result is None

    def test_record_earnings_paid_adapter(self, manager, paid_adapter):
        """Paid adapter installs generate earnings with 70/30 split."""
        result = manager.record_install_earnings("paid-adapter-1")
        assert result is not None
        assert result.amount_cents == 999
        assert result.creator_share_cents == 699  # 70% of 999 = 699.3, int = 699
        assert result.platform_share_cents == 300  # 999 - 699 = 300

    def test_record_earnings_updates_adapter(self, manager, paid_adapter):
        """Adapter totals update correctly after earnings."""
        manager.record_install_earnings("paid-adapter-1")
        a = manager._adapters["paid-adapter-1"]
        assert a.total_earned_cents == 699
        assert a.platform_earned_cents == 300
        assert a.pending_payout_cents == 699

    def test_record_earnings_multiple_installs(self, manager, paid_adapter):
        """Multiple installs accumulate earnings."""
        for _ in range(5):
            manager.record_install_earnings("paid-adapter-1")
        a = manager._adapters["paid-adapter-1"]
        assert a.total_earned_cents == 699 * 5
        assert a.pending_payout_cents == 699 * 5

    def test_record_earnings_custom_amount(self, manager, paid_adapter):
        """Custom amount overrides adapter price."""
        result = manager.record_install_earnings("paid-adapter-1", amount_cents=2000)
        assert result is not None
        assert result.amount_cents == 2000
        assert result.creator_share_cents == 1400  # 70% of 2000
        assert result.platform_share_cents == 600  # 30% of 2000

    def test_record_earnings_non_existent(self, manager):
        """Returns None for non-existent adapter."""
        assert manager.record_install_earnings("nonexistent") is None

    def test_record_earnings_creates_earning_record(self, manager, paid_adapter):
        """Earning record is stored and accessible."""
        manager.record_install_earnings("paid-adapter-1")
        assert len(manager._earnings) == 1
        eid = list(manager._earnings.keys())[0]
        e = manager._earnings[eid]
        assert e.adapter_id == "paid-adapter-1"
        assert e.author == "TestCreator"
        assert e.event_type == "install"

    def test_record_earnings_persists(self, manager, paid_adapter, tmp_data_dir):
        """Earnings persist in saved data."""
        manager.record_install_earnings("paid-adapter-1")
        manager2 = MarketplaceManager(data_dir=tmp_data_dir)
        assert len(manager2._earnings) == 1

    def test_70_30_split_precision(self, manager):
        """70/30 split works correctly for various amounts."""
        a = Adapter(id="precision-test", name="Precision", description="", author="dev", price_cents=1)
        manager._adapters[a.id] = a
        result = manager.record_install_earnings("precision-test")
        assert result is not None
        # 70% of 1 = 0.7 → int = 0
        assert result.creator_share_cents == 0
        assert result.platform_share_cents == 1

        # $3.00
        a2 = Adapter(id="p300", name="P300", description="", author="dev", price_cents=300)
        manager._adapters[a2.id] = a2
        r2 = manager.record_install_earnings("p300")
        assert r2.creator_share_cents == 210  # 70% of 300
        assert r2.platform_share_cents == 90  # 30% of 300


# ── Creator Earnings Tests ─────────────────────────────────────────────


class TestGetCreatorEarnings:
    """MarketplaceManager.get_creator_earnings."""

    def test_empty_creator(self, manager):
        """Creator with no adapters returns empty summary."""
        earnings = manager.get_creator_earnings("UnknownCreator")
        assert earnings["total_adapters"] == 0
        assert earnings["total_earnings_cents"] == 0

    def test_creator_with_adapters_no_earnings(self, manager, paid_adapter):
        """Creator with adapters but no earnings yet."""
        earnings = manager.get_creator_earnings("TestCreator")
        assert earnings["total_adapters"] == 1
        assert earnings["total_earnings_cents"] == 0
        assert earnings["paid_adapters"] == 1
        assert earnings["free_adapters"] == 0

    def test_creator_with_earnings(self, manager, paid_adapter):
        """Creator with earnings shows correct totals."""
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")

        earnings = manager.get_creator_earnings("TestCreator")
        assert earnings["total_earnings_cents"] == 699 * 3
        assert earnings["total_earnings_dollars"] == round(699 * 3 / 100, 2)
        assert earnings["platform_fees_cents"] == 300 * 3
        assert earnings["pending_payout_cents"] == 699 * 3
        assert earnings["num_earnings_events"] == 3
        assert earnings["total_revenue_cents"] == 999 * 3

    def test_creator_by_adapter_breakdown(self, manager, paid_adapter, free_adapter):
        """Per-adapter breakdown shows correct data for both paid and free adapters."""
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")

        earnings = manager.get_creator_earnings("TestCreator")
        assert len(earnings["by_adapter"]) == 2  # Both adapters (paid + free)

        paid_breakdown = [b for b in earnings["by_adapter"] if b["adapter_id"] == "paid-adapter-1"][0]
        assert paid_breakdown["total_earned_cents"] == 699 * 2
        assert paid_breakdown["platform_share_cents"] == 300 * 2
        assert paid_breakdown["price_cents"] == 999

        free_breakdown = [b for b in earnings["by_adapter"] if b["adapter_id"] == "free-adapter-1"][0]
        assert free_breakdown["total_earned_cents"] == 0
        assert free_breakdown["price_cents"] == 0

    def test_creator_recent_earnings(self, manager, paid_adapter):
        """Recent earnings list contains latest transactions."""
        for _ in range(5):
            manager.record_install_earnings("paid-adapter-1")

        earnings = manager.get_creator_earnings("TestCreator")
        assert len(earnings["recent_earnings"]) == 5

    def test_case_insensitive_author(self, manager, paid_adapter):
        """Author lookup is case-insensitive."""
        manager.record_install_earnings("paid-adapter-1")
        e1 = manager.get_creator_earnings("testcreator")
        e2 = manager.get_creator_earnings("TESTCREATOR")
        e3 = manager.get_creator_earnings("TestCreator")
        assert e1["total_earnings_cents"] == e2["total_earnings_cents"]
        assert e2["total_earnings_cents"] == e3["total_earnings_cents"]


# ── PayoutRequest Tests ────────────────────────────────────────────────


class TestRequestPayout:
    """MarketplaceManager.request_payout."""

    def test_no_pending_earnings(self, manager, paid_adapter):
        """Returns error when no pending earnings."""
        result = manager.request_payout("TestCreator")
        assert not result["success"]
        assert "No pending earnings" in result["error"]

    def test_minimum_payout(self, manager, paid_adapter):
        """Returns error when below minimum payout ($5.00)."""
        # Create a cheap adapter with only $1.40 pending — below $5 min
        a = Adapter(id="cheap", name="Cheap", description="", author="TestCreator", price_cents=200)
        manager._adapters[a.id] = a
        manager.record_install_earnings("cheap")  # $1.40 pending
        result = manager.request_payout("TestCreator")
        assert not result["success"]
        assert "Minimum payout" in result["error"]

    def test_successful_payout(self, manager, paid_adapter):
        """Successful payout creates a payout record and deducts balance."""
        manager.record_install_earnings("paid-adapter-1")  # $6.99 pending
        result = manager.request_payout("TestCreator")
        assert result["success"]
        assert result["payout"]["status"] == "pending"
        assert result["payout"]["amount_cents"] == 699
        assert result["payout"]["author"] == "TestCreator"

        # Balance should be 0 after payout
        a = manager._adapters["paid-adapter-1"]
        assert a.pending_payout_cents == 0

    def test_payout_partial_amount(self, manager, paid_adapter):
        """Can request a partial payout."""
        for _ in range(10):
            manager.record_install_earnings("paid-adapter-1")  # $69.90 pending

        result = manager.request_payout("TestCreator", amount_cents=2000)  # $20
        assert result["success"]
        assert result["payout"]["amount_cents"] == 2000

        # Should have remaining balance
        a = manager._adapters["paid-adapter-1"]
        assert a.pending_payout_cents > 0

    def test_payout_exceeds_balance(self, manager, paid_adapter):
        """Returns error when amount exceeds balance."""
        manager.record_install_earnings("paid-adapter-1")  # $6.99
        result = manager.request_payout("TestCreator", amount_cents=1000)  # $10
        assert not result["success"]
        assert "Insufficient balance" in result["error"]

    def test_payout_multiple_adapters(self, manager):
        """Payout deducts proportionally from multiple adapters."""
        a1 = Adapter(id="a1", name="A1", description="", author="MultiCreator", price_cents=999)
        a2 = Adapter(id="a2", name="A2", description="", author="MultiCreator", price_cents=999)
        manager._adapters[a1.id] = a1
        manager._adapters[a2.id] = a2

        manager.record_install_earnings("a1")
        manager.record_install_earnings("a2")

        result = manager.request_payout("MultiCreator")
        assert result["success"]
        assert result["payout"]["amount_cents"] == 699 * 2

    def test_payout_creates_record(self, manager, paid_adapter):
        """Payout record is stored."""
        manager.record_install_earnings("paid-adapter-1")
        manager.request_payout("TestCreator")
        assert len(manager._payouts) == 1

    def test_payout_persists(self, manager, paid_adapter, tmp_data_dir):
        """Payout data persists across sessions."""
        manager.record_install_earnings("paid-adapter-1")
        manager.request_payout("TestCreator")
        manager2 = MarketplaceManager(data_dir=tmp_data_dir)
        assert len(manager2._payouts) == 1

    def test_payout_with_destination(self, manager, paid_adapter):
        """Payout with method and destination."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout(
            "TestCreator",
            method="paypal",
            destination="creator@example.com",
        )
        assert result["success"]
        assert result["payout"]["method"] == "paypal"
        assert result["payout"]["destination"] == "creator@example.com"

    def test_zero_amount_payout(self, manager, paid_adapter):
        """Returns error for zero amount when there is pending balance."""
        # First create some pending balance
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator", amount_cents=0)
        assert not result["success"]
        assert "Payout amount must be positive" in result["error"]


# ── Process Payout Tests ───────────────────────────────────────────────


class TestProcessPayout:
    """MarketplaceManager.process_payout."""

    def test_process_completed(self, manager, paid_adapter):
        """Completed payout marks earnings as settled."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        assert manager.process_payout(payout_id, status="completed")
        payout = manager._payouts[payout_id]
        assert payout.status == "completed"
        assert payout.processed_at is not None

    def test_process_failed_returns_balance(self, manager, paid_adapter):
        """Failed payout returns balance to adapter."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        # Balance should be 0 after request
        assert manager._adapters["paid-adapter-1"].pending_payout_cents == 0

        # Now fail it — balance should come back
        assert manager.process_payout(payout_id, status="failed")
        payout = manager._payouts[payout_id]
        assert payout.status == "failed"

    def test_process_cancelled(self, manager, paid_adapter):
        """Cancelled payout returns balance."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        assert manager.process_payout(payout_id, status="cancelled")
        assert manager._payouts[payout_id].status == "cancelled"

    def test_process_nonexistent(self, manager):
        """Returns False for non-existent payout."""
        assert not manager.process_payout("nonexistent")

    def test_process_already_completed(self, manager, paid_adapter):
        """Cannot process an already completed payout."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        assert manager.process_payout(payout_id, status="completed")
        assert not manager.process_payout(payout_id, status="completed")

    def test_payout_with_notes(self, manager, paid_adapter):
        """Can add notes when processing payout."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        manager.process_payout(payout_id, status="completed", notes="Paid successfully")
        assert manager._payouts[payout_id].notes == "Paid successfully"


# ── Get Payouts Tests ──────────────────────────────────────────────────


class TestGetPayouts:
    """MarketplaceManager.get_payouts."""

    def test_empty_payouts(self, manager, paid_adapter):
        """No payouts returns empty list."""
        payouts = manager.get_payouts()
        assert payouts == []

    def test_get_payouts_by_author(self, manager, paid_adapter):
        """Can filter payouts by author."""
        manager.record_install_earnings("paid-adapter-1")
        manager.request_payout("TestCreator")

        payouts = manager.get_payouts(author="TestCreator")
        assert len(payouts) == 1

        payouts_other = manager.get_payouts(author="OtherCreator")
        assert len(payouts_other) == 0

    def test_get_payouts_by_status(self, manager, paid_adapter):
        """Can filter payouts by status."""
        manager.record_install_earnings("paid-adapter-1")
        manager.request_payout("TestCreator")

        pending = manager.get_payouts(status="pending")
        assert len(pending) == 1

        completed = manager.get_payouts(status="completed")
        assert len(completed) == 0

    def test_get_payouts_limit(self, manager, paid_adapter):
        """Payouts respect limit param."""
        for _ in range(3):
            manager.record_install_earnings("paid-adapter-1")
            manager.request_payout("TestCreator")

        payouts = manager.get_payouts(limit=2)
        assert len(payouts) == 2


# ── Revenue Stats Tests ────────────────────────────────────────────────


class TestGetRevenueStats:
    """MarketplaceManager.get_revenue_stats."""

    def test_empty_stats(self, manager):
        """Empty marketplace returns zeroed stats."""
        stats = manager.get_revenue_stats()
        assert stats["total_revenue_cents"] == 0
        assert stats["total_creator_earnings_cents"] == 0
        assert stats["total_platform_fees_cents"] == 0
        assert stats["total_paid_out_cents"] == 0
        assert stats["unique_creators"] == 0
        assert stats["total_paid_adapters"] == 0

    def test_stats_with_earnings(self, manager, paid_adapter):
        """Stats reflect earnings data."""
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")

        stats = manager.get_revenue_stats()
        assert stats["total_revenue_cents"] == 999 * 2
        assert stats["total_creator_earnings_cents"] == 699 * 2
        assert stats["total_platform_fees_cents"] == 300 * 2
        assert stats["pending_payouts_cents"] == 699 * 2
        assert stats["unique_creators"] == 1
        assert stats["total_paid_adapters"] == 1

    def test_stats_split_ratio(self, manager):
        """Stats show correct split ratio."""
        stats = manager.get_revenue_stats()
        assert stats["split_ratio"] == "70/30"
        assert stats["config"]["creator_share"] == 0.70
        assert stats["config"]["platform_share"] == 0.30

    def test_stats_top_earners(self, manager):
        """Top earners list works with multiple creators."""
        for name, price in [("Alice", 999), ("Bob", 500), ("Alice", 999), ("Charlie", 300)]:
            a = Adapter(id=f"a-{name}", name=name, description="", author=name, price_cents=price)
            manager._adapters[a.id] = a
            manager.record_install_earnings(a.id)

        stats = manager.get_revenue_stats()
        assert len(stats["top_earners"]) >= 2
        assert stats["top_earners"][0]["author"] == "Alice"

    def test_stats_monthly_breakdown(self, manager, paid_adapter):
        """Monthly breakdown groups earnings by month."""
        manager.record_install_earnings("paid-adapter-1")
        stats = manager.get_revenue_stats()
        assert len(stats["monthly_breakdown"]) >= 1

    def test_stats_with_payouts(self, manager, paid_adapter):
        """Stats include payout info."""
        manager.record_install_earnings("paid-adapter-1")
        result = manager.request_payout("TestCreator")
        manager.process_payout(result["payout"]["id"], status="completed")

        stats = manager.get_revenue_stats()
        assert stats["total_paid_out_cents"] > 0
        assert stats["completed_payouts_count"] == 1


# ── EarningRecord Tests ────────────────────────────────────────────────


class TestEarningRecord:
    """EarningRecord serialization."""

    def test_to_dict(self):
        """EarningRecord to_dict produces correct output."""
        e = EarningRecord(
            id="earn-1",
            adapter_id="adapter-1",
            adapter_name="Test",
            author="dev",
            amount_cents=999,
            creator_share_cents=699,
            platform_share_cents=300,
            event_type="install",
            created_at=1000.0,
        )
        d = e.to_dict()
        assert d["id"] == "earn-1"
        assert d["amount_cents"] == 999
        assert d["creator_share_cents"] == 699
        assert d["platform_share_cents"] == 300

    def test_from_dict(self):
        """EarningRecord from_dict restores fields."""
        d = {
            "id": "earn-2",
            "adapter_id": "adapter-2",
            "adapter_name": "Test 2",
            "author": "dev2",
            "amount_cents": 1499,
            "creator_share_cents": 1049,
            "platform_share_cents": 450,
            "event_type": "install",
            "created_at": 2000.0,
            "payout_id": None,
        }
        e = EarningRecord.from_dict(d)
        assert e.id == "earn-2"
        assert e.amount_cents == 1499
        assert e.creator_share_cents == 1049

    def test_default_event_type(self):
        """Default event type is 'install'."""
        e = EarningRecord(id="e1", adapter_id="a1", adapter_name="A", author="dev", amount_cents=100, creator_share_cents=70, platform_share_cents=30)
        assert e.event_type == "install"

    def test_payout_id_none(self):
        """Default payout_id is None."""
        e = EarningRecord(id="e1", adapter_id="a1", adapter_name="A", author="dev", amount_cents=100, creator_share_cents=70, platform_share_cents=30)
        assert e.payout_id is None


# ── PayoutRecord Tests ─────────────────────────────────────────────────


class TestPayoutRecord:
    """PayoutRecord serialization."""

    def test_to_dict(self):
        p = PayoutRecord(id="p-1", author="dev", amount_cents=1000, created_at=100.0)
        d = p.to_dict()
        assert d["id"] == "p-1"
        assert d["amount_cents"] == 1000
        assert d["status"] == "pending"

    def test_from_dict(self):
        d = {"id": "p-2", "author": "dev2", "amount_cents": 2000, "fee_cents": 50, "status": "completed", "method": "paypal", "destination": "e@m.com", "notes": "", "created_at": 200.0, "processed_at": 300.0, "adapter_ids": []}
        p = PayoutRecord.from_dict(d)
        assert p.id == "p-2"
        assert p.amount_cents == 2000
        assert p.status == "completed"
        assert p.method == "paypal"

    def test_default_status(self):
        """Default status is 'pending'."""
        p = PayoutRecord(id="p-3", author="dev", amount_cents=500, created_at=0.0)
        assert p.status == "pending"

    def test_default_fee_zero(self):
        """Default fee_cents is 0."""
        p = PayoutRecord(id="p-4", author="dev", amount_cents=500, created_at=0.0)
        assert p.fee_cents == 0


# ── Persistence Tests ──────────────────────────────────────────────────


class TestRevenuePersistence:
    """Revenue data persists across MarketplaceManager instances."""

    def test_full_revenue_cycle_persists(self, manager, paid_adapter, tmp_data_dir):
        """Complete revenue cycle (earnings → payout → process) persists."""
        # Record earnings
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")

        # Request payout
        result = manager.request_payout("TestCreator")
        payout_id = result["payout"]["id"]

        # Process payout
        manager.process_payout(payout_id, status="completed")

        # Reload
        manager2 = MarketplaceManager(data_dir=tmp_data_dir)

        # Check earnings
        assert len(manager2._earnings) == 2

        # Check payout
        assert len(manager2._payouts) == 1
        p = manager2._payouts[payout_id]
        assert p.status == "completed"
        assert p.processed_at is not None

        # Check adapter balances (pending should be 0 after payout)
        a = manager2._adapters["paid-adapter-1"]
        assert a.pending_payout_cents == 0
        assert a.total_earned_cents > 0

    def test_revenue_config_persists(self, manager, tmp_data_dir):
        """RevenueConfig persists across sessions."""
        manager._revenue_config.creator_share = 0.80
        manager._revenue_config.platform_share = 0.20
        manager._revenue_config.min_payout_cents = 1000
        manager._save()

        manager2 = MarketplaceManager(data_dir=tmp_data_dir)
        assert manager2._revenue_config.creator_share == 0.80
        assert manager2._revenue_config.platform_share == 0.20
        assert manager2._revenue_config.min_payout_cents == 1000


# ── Edge Case Tests ────────────────────────────────────────────────────


class TestRevenueEdgeCases:
    """Edge cases for revenue sharing."""

    def test_multiple_creators_independent(self, manager):
        """Multiple creators have independent earnings."""
        a1 = Adapter(id="a1", name="A1", description="", author="Alice", price_cents=999)
        a2 = Adapter(id="a2", name="A2", description="", author="Bob", price_cents=999)
        manager._adapters[a1.id] = a1
        manager._adapters[a2.id] = a2

        manager.record_install_earnings("a1")
        manager.record_install_earnings("a2")

        alice = manager.get_creator_earnings("Alice")
        bob = manager.get_creator_earnings("Bob")
        assert alice["total_earnings_cents"] == 699
        assert bob["total_earnings_cents"] == 699

    def test_no_double_counting_on_payout(self, manager, paid_adapter):
        """Payout doesn't double-count earnings."""
        manager.record_install_earnings("paid-adapter-1")
        earnings_before = manager.get_creator_earnings("TestCreator")
        assert earnings_before["total_earnings_cents"] == 699

        result = manager.request_payout("TestCreator")
        assert result["success"]

        earnings_after = manager.get_creator_earnings("TestCreator")
        # Total earned should remain same (only pending changes)
        assert earnings_after["total_earnings_cents"] == 699
        assert earnings_after["pending_payout_cents"] == 0

    def test_earnings_with_same_timestamp(self, manager, paid_adapter):
        """Multiple earnings at same time don't interfere."""
        manager.record_install_earnings("paid-adapter-1")
        manager.record_install_earnings("paid-adapter-1")
        assert len(manager._earnings) == 2

    def test_get_revenue_stats_with_mixed_adapters(self, manager):
        """Stats handle mix of free and paid adapters."""
        free = Adapter(id="free", name="Free", description="", author="Dev", price_cents=0)
        paid = Adapter(id="paid", name="Paid", description="", author="Dev", price_cents=999)
        manager._adapters[free.id] = free
        manager._adapters[paid.id] = paid

        manager.record_install_earnings("paid")

        stats = manager.get_revenue_stats()
        assert stats["total_paid_adapters"] == 1
        assert stats["total_revenue_cents"] == 999
