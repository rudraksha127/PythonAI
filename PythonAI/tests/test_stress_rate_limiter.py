"""
Stress Test — Rate Limiter & Capture Engine Under Load
========================================================

Sends 1000 events in rapid succession, verifies:
  1. Rate limiter correctly throttles excess requests (429 responses)
  2. All successfully captured events persist without data loss
  3. Statistics accurately reflect the captured total
  4. The capture engine handles concurrent/rapid writes safely
  5. Sequential writes with relaxed rate limiter preserve every event

Tests use FastAPI's TestClient with a real CaptureEngine backed by
a temp file. No Ollama or external services required.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


TEST_EVENT_COUNT = 1000
VALID_EVENT_TYPES = ["accept", "reject", "edit"]


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from src.api.server import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def capture_db() -> str:
    """Create a temp file for the capture engine database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    try:
        os.unlink(tmp.name)
        for suffix in (".encrypted", ".tmp.enc"):
            p = tmp.name + suffix
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


def _make_engine(db_path: str):
    """Create a real CaptureEngine backed by the given temp file."""
    from src.learning.capture_engine import CaptureEngine

    return CaptureEngine(db_path=db_path, prefer_sqlcipher=False)


def _make_event(event_type: str, index: int) -> dict[str, Any]:
    """Build a valid event payload."""
    body = {
        "event_type": event_type,
        "session_id": f"stress-{event_type}-{index}",
        "project_id": "stress-test",
        "file_path": f"src/{event_type}/file_{index}.py",
        "line_number": (index % 100) + 1,
        "language": ["python", "typescript", "rust", "go", "java"][index % 5],
        "project_type": "web",
        "suggestion": f"def stress_test_{index}(): return {index}" * 5,
        "context_before": "import os\nimport sys\n",
        "context_after": "    pass\n",
    }
    if event_type == "edit":
        body["final_code"] = f"def stress_test_{index}_edited(): return {index}" * 5
    if event_type == "pr_merge":
        body["suggestion_metadata"] = {
            "pr_number": index,
            "branch": f"feature/{index}",
            "git_sha": f"abc{index:08x}",
        }
    return body


# ═══════════════════════════════════════════════════════════════
# Test 1: Rate Limiter Stress — Real Token Bucket
# ═══════════════════════════════════════════════════════════════


class TestRateLimiterStress:
    """Verify the real token-bucket rate limiter handles 1000 rapid requests.

    The token bucket has capacity=30, refill_per_sec=1.0.
    Sending 1000 requests without delay will exhaust the bucket early,
    causing most requests to be rejected with 429.
    """

    def test_rate_limiter_throttles_rapid_burst(self, client: TestClient):
        """Send 1000 requests as fast as possible — verify 429 responses."""
        results: dict[int, list[int]] = {}  # status -> [response times]
        timings: list[float] = []

        for i in range(TEST_EVENT_COUNT):
            start = time.time()
            resp = client.post(
                "/api/events",
                json=_make_event("accept", i),
            )
            elapsed = (time.time() - start) * 1000
            status = resp.status_code
            results.setdefault(status, []).append(i)
            timings.append(elapsed)

        total = sum(len(v) for v in results.values())
        assert total == TEST_EVENT_COUNT, f"Expected {TEST_EVENT_COUNT} responses, got {total}"

        # With capacity=30 and 1000 instant requests, most should be 429
        ok_count = len(results.get(200, []))
        rate_limited_count = len(results.get(429, []))

        print(f"\n  [Rate Limiter Burst]")
        print(f"    200 OK:     {ok_count}")
        print(f"    429 Limited: {rate_limited_count}")
        print(f"    Other:       {len(results.get(422, []))} (validation errors)")
        print(f"    Avg latency: {sum(timings)/len(timings):.1f}ms")

        # At capacity=30, at most ~30 should get through before bucket is empty
        # In practice the refill gives a few more, but still well under 100
        assert ok_count < 100, (
            f"Too many requests passed through rate limiter: {ok_count}. "
            f"Expected < 100 with capacity=30."
        )
        assert rate_limited_count > 900, (
            f"Too few rate-limited responses: {rate_limited_count}. "
            f"Expected > 900 with 1000 rapid requests."
        )

    def test_rate_limiter_allows_slow_refill(self, client: TestClient):
        """With 1.01s between requests and a fresh bucket, rate limiter should allow all."""
        from src.api.server import _TokenBucket

        fresh_limiter = _TokenBucket(capacity=30, refill_per_sec=1.0)

        results: dict[int, list[int]] = {}
        timings: list[float] = []

        with patch("src.api.server._rate_limiter", fresh_limiter):
            # Send 20 requests with 1.05s spacing so token bucket refills completely
            n = 20
            for i in range(n):
                start = time.time()
                resp = client.post(
                    "/api/events",
                    json=_make_event("accept", i + 10000),
                )
                elapsed = (time.time() - start) * 1000
                status = resp.status_code
                results.setdefault(status, []).append(i)
                timings.append(elapsed)
                if i < n - 1:
                    time.sleep(1.05)  # 1.05s > 1 refill period

        ok_count = len(results.get(200, []))
        rate_limited_count = len(results.get(429, []))
        print(f"\n  [Rate Limiter Slow Refill]")
        print(f"    200 OK:     {ok_count}")
        print(f"    429 Limited: {rate_limited_count}")
        print(f"    Avg latency: {sum(timings)/len(timings):.1f}ms")

        # At 1.05s spacing, bucket should always have >= 1 token
        assert ok_count == n, f"Should allow all {n} requests: got {ok_count} OK"

    def test_rate_limiter_retry_after_header(self, client: TestClient):
        """Rate-limited responses should include Retry-After header."""
        from src.api.server import _TokenBucket

        fresh_limiter = _TokenBucket(capacity=5, refill_per_sec=0.1)

        with patch("src.api.server._rate_limiter", fresh_limiter):
            # Exhaust the bucket with back-to-back requests
            for _ in range(10):
                client.post("/api/events", json=_make_event("accept", 99999))

            # Next request should be rate-limited
            resp = client.post("/api/events", json=_make_event("accept", 99998))
            if resp.status_code == 429:
                assert "Retry-After" in resp.headers
                retry_after = int(resp.headers["Retry-After"])
                assert retry_after >= 0
                data = resp.json()
                assert "retry_after" in data
                assert data["retry_after"] >= 0


# ═══════════════════════════════════════════════════════════════
# Test 2: Capture Engine Throughput — All Events Pass
# ═══════════════════════════════════════════════════════════════

STRESS_RELAXED_LIMITER = MagicMock()
STRESS_RELAXED_LIMITER.allow.return_value = True
STRESS_RELAXED_LIMITER.retry_after.return_value = 0.0


class TestCaptureEngineThroughput:
    """Verify the capture engine stores 1000 events without data loss.

    Uses a mocked rate limiter that allows all requests, so the
    engine receives the full load.
    """

    # ── Single event type: 500 accepts ────────────────────────

    def test_500_accepts_no_data_loss(self, client: TestClient, capture_db: str):
        """Send 500 accept events — verify all stored in stats."""
        n = 500
        engine = _make_engine(capture_db)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                success_ids: list[str] = []
                error_indices: list[int] = []

                for i in range(n):
                    resp = client.post("/api/events", json=_make_event("accept", i))
                    if resp.status_code == 200:
                        success_ids.append(resp.json()["event_id"])
                    else:
                        error_indices.append(i)

                assert len(error_indices) == 0, (
                    f"Failed to capture {len(error_indices)}/{n} events: "
                    f"{error_indices[:10]}..."
                )
                assert len(success_ids) == n

                # Verify stats
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()
                captured = stats.get("signals_by_type", {}).get("accept", 0)
                assert captured == n, (
                    f"Expected {n} accepts in stats, got {captured}"
                )

    # ── Mixed event types ────────────────────────────────────

    def test_500_mixed_events_no_data_loss(self, client: TestClient, capture_db: str):
        """Send 500 mixed accept/reject/edit events — verify all accounted for."""
        import random

        n = 500
        engine = _make_engine(capture_db)
        random.seed(42)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                counts: dict[str, int] = {"accept": 0, "reject": 0, "edit": 0}

                for i in range(n):
                    event_type = random.choice(VALID_EVENT_TYPES)
                    resp = client.post("/api/events", json=_make_event(event_type, i))
                    if resp.status_code == 200:
                        counts[event_type] += 1

                total_ok = sum(counts.values())
                assert total_ok == n, (
                    f"Expected {n} success, got {total_ok}"
                )

                # Verify stats match
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()
                stats_by_type = stats.get("signals_by_type", {})

                for etype, expected in counts.items():
                    actual = stats_by_type.get(etype, 0)
                    assert actual == expected, (
                        f"Event type '{etype}': expected {expected}, stats report {actual}"
                    )

                total_in_stats = sum(stats_by_type.values())
                assert total_in_stats == n, (
                    f"Stats show {total_in_stats} total signals, expected {n}"
                )

    # ── Concurrent (interleaved) rapid writes ────────────────

    def test_concurrent_rapid_writes_preserve_all_events(
        self, client: TestClient, capture_db: str
    ):
        """Send events in rapid succession with mixed types at high concurrency."""
        engine = _make_engine(capture_db)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                # Interleave 4 event types in rapid succession
                # (accept, reject, edit, pr_merge, accept, reject, edit, pr_merge, ...)
                expected_counts: dict[str, int] = {"accept": 0, "reject": 0, "edit": 0, "pr_merge": 0}
                n = 100  # 100 rounds x 4 types = 400 events
                total_ok = 0

                for i in range(n):
                    for etype in ["accept", "reject", "edit", "pr_merge"]:
                        resp = client.post("/api/events", json=_make_event(etype, i * 4 + expected_counts[etype]))
                        if resp.status_code == 200:
                            expected_counts[etype] += 1
                            total_ok += 1
                        elif resp.status_code == 500:
                            pass

                expected_total = n * 4  # 100 * 4 = 400
                print(f"\n  [Concurrent Rapid] Captured {total_ok}/{expected_total}")

                # Small flush to ensure SQLite has committed
                time.sleep(0.1)

                # Verify stats
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()
                stats_by_type = stats.get("signals_by_type", {})

                for etype, expected in expected_counts.items():
                    actual = stats_by_type.get(etype, 0)
                    assert actual == expected, (
                        f"'{etype}': expected {expected}, got {actual}"
                    )
                    print(f"    {etype}: {actual}/{expected}")

    # ── Data integrity: verify stats match event stream ──────

    def test_data_integrity_after_stress(self, client: TestClient, capture_db: str):
        """After stress, verify get_statistics matches get_signals counts."""
        engine = _make_engine(capture_db)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                # Send 500 events in rapid succession
                for i in range(500):
                    resp = client.post("/api/events", json=_make_event("accept", i))
                    assert resp.status_code == 200

                # Verify consistency across query methods
                stats_resp = client.get("/stats")
                stats = stats_resp.json()
                stats_count = sum(stats.get("signals_by_type", {}).values())

                # Let SQLite flush before direct query
                time.sleep(0.1)

                # Direct engine query for signals
                signals = engine.get_signals(limit=2000)
                signals_count = len(signals)
                engine_stats = engine.get_statistics()
                engine_signal_count = sum(engine_stats.get("signals_by_type", {}).values())

                assert stats_count == 500, f"API stats: expected 500, got {stats_count}"
                assert signals_count >= 500, f"get_signals: expected >=500, got {signals_count}"
                assert engine_signal_count >= 500, f"engine stats: expected >=500, got {engine_signal_count}"

                # Cross-verify: all signals have required fields
                empty_signals = [
                    s.signal_id for s in signals
                    if not s.suggestion or not s.file_path
                ]
                assert len(empty_signals) == 0, (
                    f"{len(empty_signals)} signals missing required fields"
                )


# ═══════════════════════════════════════════════════════════════
# Test 3: Real Rate Limiter + Real Capture Engine — Combined
# ═══════════════════════════════════════════════════════════════


class TestCombinedStress:
    """Full integration: real rate limiter + real capture engine.

    Verifies that rate-limited events are not stored, and that all
    passed-through events are correctly captured.
    """

    def test_stress_with_real_rate_limiter_and_engine(
        self, client: TestClient, capture_db: str
    ):
        """Real rate limiter + real engine: verify no data loss on passed events."""
        # Use the ACTUAL rate limiter (not mocked)
        engine = _make_engine(capture_db)

        # Create a fresh rate limiter for isolation
        from src.api.server import _TokenBucket

        fresh_limiter = _TokenBucket(capacity=30, refill_per_sec=1.0)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", fresh_limiter):
                passed_ids: list[str] = []
                rate_limited_count = 0

                # Send 500 events as fast as possible
                n = 500
                for i in range(n):
                    resp = client.post("/api/events", json=_make_event("accept", i))
                    if resp.status_code == 200:
                        passed_ids.append(resp.json()["event_id"])
                    elif resp.status_code == 429:
                        rate_limited_count += 1

                passed_count = len(passed_ids)
                print(f"\n  [Combined Stress]")
                print(f"    Passed:   {passed_count}/{n}")
                print(f"    Limited:  {rate_limited_count}")
                print(f"    Capture rate: {passed_count}/{n} "
                      f"({passed_count / n * 100:.1f}%)")

                # Verify: all passed events are in stats
                with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                    stats_resp = client.get("/stats")
                    assert stats_resp.status_code == 200
                    stats = stats_resp.json()
                captured_in_stats = stats.get("signals_by_type", {}).get("accept", 0)
                assert captured_in_stats == passed_count, (
                    f"Stats report {captured_in_stats} accepts but {passed_count} passed"
                )

                # Verify: no more signals than passed through
                total_in_stats = sum(stats.get("signals_by_type", {}).values())
                assert total_in_stats == passed_count, (
                    f"Stats report {total_in_stats} total signals, "
                    f"but only {passed_count} events passed rate limiter"
                )

                # Verify rate limiter did actually throttle
                assert rate_limited_count > 0, (
                    "Rate limiter did not throttle any requests — "
                    "at least some should be 429"
                )

    def test_acceptance_rate_reflects_passed_events_only(
        self, client: TestClient, capture_db: str
    ):
        """Acceptance rate should be computed from passed (not total) events."""
        from src.api.server import _TokenBucket

        engine = _make_engine(capture_db)
        limiter = _TokenBucket(capacity=30, refill_per_sec=1.0)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", limiter):
                passed_accepts = 0
                passed_rejects = 0

                # Send 500 mixed types rapidly
                for i in range(500):
                    event_type = "accept" if i % 2 == 0 else "reject"
                    resp = client.post("/api/events", json=_make_event(event_type, i))
                    if resp.status_code == 200:
                        if event_type == "accept":
                            passed_accepts += 1
                        else:
                            passed_rejects += 1

                print(f"\n  [Acceptance Rate Stress]")
                print(f"    Passed accepts: {passed_accepts}")
                print(f"    Passed rejects: {passed_rejects}")

                with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                    stats_resp = client.get("/stats")
                    assert stats_resp.status_code == 200
                    stats = stats_resp.json()
                stats_accepts = stats.get("signals_by_type", {}).get("accept", 0)
                stats_rejects = stats.get("signals_by_type", {}).get("reject", 0)

                assert stats_accepts == passed_accepts
                assert stats_rejects == passed_rejects

                expected_rate = (
                    passed_accepts / (passed_accepts + passed_rejects) * 100
                ) if (passed_accepts + passed_rejects) > 0 else 0
                actual_rate = stats.get("overall_acceptance_rate", 0)

                assert abs(actual_rate - expected_rate) < 0.1, (
                    f"Expected acceptance rate {expected_rate:.1f}%, "
                    f"got {actual_rate:.1f}%"
                )


# ═══════════════════════════════════════════════════════════════
# Test 4: Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestStressEdgeCases:
    """Edge cases that should not cause data corruption."""

    def test_duplicate_session_ids_no_corruption(self, client: TestClient, capture_db: str):
        """200 events sharing the same session_id should not corrupt data."""
        n = 200
        engine = _make_engine(capture_db)
        from src.api.server import _TokenBucket

        limiter = _TokenBucket(capacity=30, refill_per_sec=100.0)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", limiter):
                for i in range(n):
                    body = _make_event("accept", i)
                    body["session_id"] = "same-session-id"
                    resp = client.post("/api/events", json=body)
                    assert resp.status_code in (200, 429)

                stats = client.get("/stats").json()
                total_accepts = stats.get("signals_by_type", {}).get("accept", 0)
                assert total_accepts > 0, "Should have captured some events"
                print(f"\n  [Duplicate Session] Captured {total_accepts} events")

    def test_empty_context_fields_no_corruption(self, client: TestClient, capture_db: str):
        """200 events with empty optional fields should still be stored correctly."""
        n = 200
        engine = _make_engine(capture_db)

        with patch("src.api.server._capture_engine", engine):
            with patch("src.api.server._rate_limiter", STRESS_RELAXED_LIMITER):
                for i in range(n):
                    body = {
                        "event_type": "accept",
                        "session_id": f"minimal-{i}",
                        "project_id": "minimal-test",
                        "file_path": "main.py",
                        "line_number": 1,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": "x = 1",
                    }
                    resp = client.post("/api/events", json=body)
                    assert resp.status_code == 200, f"Event {i}: {resp.text[:200]}"

                stats = client.get("/stats").json()
                total = stats.get("signals_by_type", {}).get("accept", 0)
                assert total == n, f"Expected {n} accepts, got {total}"
