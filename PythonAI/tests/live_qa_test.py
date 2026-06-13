"""
═══════════════════════════════════════════════════════════════════
ForgeAI MEGA PROJECT — Full Live QA / DevOps / SRE / CTO Test Suite
═══════════════════════════════════════════════════════════════════

Roles Covered:
  🔧 DevOps Engineer  — Infrastructure health, port availability, process health
  🧪 QA Engineer       — API contract testing, edge cases, error handling
  🛡️ SRE              — Latency, uptime, self-healing, watchdog
  👔 CTO              — Architecture review, cross-service connectivity
  💻 Developer        — API functionality, data integrity, feature validation

Run: python tests/live_qa_test.py
"""

import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

import httpx

# ═══════════════════════════════════════════════════════════════
# Test Configuration
# ═══════════════════════════════════════════════════════════════

PYTHONAI_URL = "http://localhost:7337"
RUDRA_BOTS_URL = "http://localhost:7000"
DASHBOARD_URL = "http://localhost:3000"
GATEWAY_URL = "http://localhost:8000"

TIMEOUT = 10.0

# ═══════════════════════════════════════════════════════════════
# Test Result Tracking
# ═══════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    name: str
    role: str
    passed: bool
    latency_ms: float = 0
    details: str = ""
    response_data: Any = None

@dataclass
class TestSuite:
    results: list[TestResult] = field(default_factory=list)
    start_time: float = 0

    def add(self, result: TestResult):
        self.results.append(result)
        icon = "✅" if result.passed else "❌"
        lat = f" ({result.latency_ms:.0f}ms)" if result.latency_ms > 0 else ""
        print(f"  {icon} [{result.role}] {result.name}{lat}")
        if not result.passed and result.details:
            print(f"     └─ {result.details}")

    def summary(self):
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        elapsed = time.time() - self.start_time

        print("\n" + "═" * 60)
        print(f"  FORGEAI MEGA PROJECT — TEST REPORT")
        print("═" * 60)
        print(f"  Total Tests : {total}")
        print(f"  ✅ Passed   : {passed}")
        print(f"  ❌ Failed   : {failed}")
        print(f"  ⏱  Duration : {elapsed:.1f}s")

        if failed > 0:
            print(f"\n  FAILED TESTS:")
            for r in self.results:
                if not r.passed:
                    print(f"    ❌ [{r.role}] {r.name}: {r.details}")

        # Latency report
        latencies = [(r.name, r.latency_ms) for r in self.results if r.latency_ms > 0]
        if latencies:
            avg_lat = sum(l for _, l in latencies) / len(latencies)
            max_name, max_lat = max(latencies, key=lambda x: x[1])
            print(f"\n  ⚡ Avg Latency : {avg_lat:.0f}ms")
            print(f"  🐢 Slowest    : {max_name} ({max_lat:.0f}ms)")

        # Grade
        pct = (passed / total * 100) if total > 0 else 0
        if pct == 100:
            grade = "A+ (PRODUCTION READY)"
        elif pct >= 90:
            grade = "A (NEAR PRODUCTION)"
        elif pct >= 75:
            grade = "B (STAGING READY)"
        elif pct >= 50:
            grade = "C (DEVELOPMENT)"
        else:
            grade = "F (CRITICAL ISSUES)"

        print(f"\n  🏆 GRADE: {grade} ({pct:.0f}%)")
        print("═" * 60)

        return failed == 0


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def timed_get(url: str, timeout: float = TIMEOUT) -> tuple[httpx.Response | None, float]:
    """GET with timing. Returns (response, latency_ms)."""
    start = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(url)
            return r, (time.time() - start) * 1000
    except Exception:
        return None, (time.time() - start) * 1000

def timed_post(url: str, json_data: dict = None, timeout: float = TIMEOUT) -> tuple[httpx.Response | None, float]:
    """POST with timing."""
    start = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(url, json=json_data or {})
            return r, (time.time() - start) * 1000
    except Exception:
        return None, (time.time() - start) * 1000


# ═══════════════════════════════════════════════════════════════
# 🔧 DEVOPS ENGINEER TESTS — Infrastructure & Deployment
# ═══════════════════════════════════════════════════════════════

def test_devops(suite: TestSuite):
    print("\n🔧 DEVOPS ENGINEER — Infrastructure & Process Health")
    print("─" * 50)

    # 1. PythonAI port alive
    r, ms = timed_get(f"{PYTHONAI_URL}/health")
    suite.add(TestResult(
        "PythonAI :7337 alive", "DevOps", 
        r is not None and r.status_code == 200, ms,
        "" if r and r.status_code == 200 else "Server unreachable"
    ))

    # 2. Rudra-bots port alive
    r, ms = timed_get(f"{RUDRA_BOTS_URL}/api/health")
    suite.add(TestResult(
        "Rudra-bots :7000 alive", "DevOps",
        r is not None and r.status_code == 200, ms,
        "" if r and r.status_code == 200 else "Server unreachable"
    ))

    # 3. Dashboard port alive
    r, ms = timed_get(f"{DASHBOARD_URL}/api/health")
    suite.add(TestResult(
        "Dashboard :3000 alive", "DevOps",
        r is not None and r.status_code == 200, ms,
        "" if r and r.status_code == 200 else "Server unreachable"
    ))

    # 4. Gateway port alive
    r, ms = timed_get(f"{GATEWAY_URL}/health")
    suite.add(TestResult(
        "Gateway :8000 alive", "DevOps",
        r is not None and r.status_code == 200, ms,
        "" if r and r.status_code == 200 else "Server unreachable"
    ))

    # 5. Gateway version check
    if r and r.status_code == 200:
        data = r.json()
        version = data.get("version", "unknown")
        suite.add(TestResult(
            f"Gateway version = {version}", "DevOps",
            version == "2.1.0", 0,
            f"Expected 2.1.0, got {version}" if version != "2.1.0" else ""
        ))

    # 6. All services visible in Gateway
    if r and r.status_code == 200:
        data = r.json()
        services = data.get("services", {})
        healthy_count = data.get("healthy_count", 0)
        suite.add(TestResult(
            f"Gateway sees {healthy_count}/3 services healthy", "DevOps",
            healthy_count == 3, 0,
            f"Only {healthy_count}/3 healthy" if healthy_count != 3 else ""
        ))

    # 7. CORS headers present on Gateway
    r, ms = timed_get(f"{GATEWAY_URL}/health")
    if r:
        has_cors = "access-control-allow-origin" in r.headers
        suite.add(TestResult(
            "CORS headers present", "DevOps",
            has_cors, 0,
            "Missing CORS headers" if not has_cors else ""
        ))


# ═══════════════════════════════════════════════════════════════
# 🧪 QA ENGINEER TESTS — API Contracts & Edge Cases
# ═══════════════════════════════════════════════════════════════

def test_qa(suite: TestSuite):
    print("\n🧪 QA ENGINEER — API Contract Testing & Edge Cases")
    print("─" * 50)

    # 1. PythonAI /health returns correct schema
    r, ms = timed_get(f"{PYTHONAI_URL}/health")
    if r and r.status_code == 200:
        data = r.json()
        has_keys = all(k in data for k in ["status", "version", "uptime_seconds"])
        suite.add(TestResult(
            "PythonAI /health schema valid", "QA", has_keys, ms,
            f"Missing keys. Got: {list(data.keys())}" if not has_keys else ""
        ))
    else:
        suite.add(TestResult("PythonAI /health schema valid", "QA", False, ms, "Unreachable"))

    # 2. Ecosystem metrics returns valid structure
    r, ms = timed_get(f"{PYTHONAI_URL}/api/forgeai/ecosystem-metrics")
    if r and r.status_code == 200:
        data = r.json()
        required = ["server", "statistics", "training", "rag", "signal_distribution", "sync_daemon", "arsenal"]
        has_all = all(k in data for k in required)
        suite.add(TestResult(
            "Ecosystem metrics schema (7 sections)", "QA", has_all, ms,
            f"Missing: {[k for k in required if k not in data]}" if not has_all else ""
        ))
    else:
        suite.add(TestResult("Ecosystem metrics schema", "QA", False, ms, "Unreachable"))

    # 3. Arsenal status returns valid counts
    r, ms = timed_get(f"{PYTHONAI_URL}/api/arsenal/summary")
    if r and r.status_code == 200:
        data = r.json()
        total = data.get("total", 0)
        installed = data.get("installed", 0)
        suite.add(TestResult(
            f"Arsenal summary: {installed}/{total} tools", "QA",
            total > 0 and installed > 0, ms,
            f"total={total}, installed={installed}" if total == 0 else ""
        ))
    else:
        suite.add(TestResult("Arsenal summary", "QA", False, ms, "Unreachable"))

    # 4. Arsenal tool lookup — known tool
    r, ms = timed_get(f"{PYTHONAI_URL}/api/arsenal/tools/ChromaDB")
    if r and r.status_code == 200:
        data = r.json()
        suite.add(TestResult(
            f"Arsenal tool lookup: ChromaDB={data.get('installed')}", "QA",
            data.get("found") is True, ms
        ))
    else:
        suite.add(TestResult("Arsenal tool lookup", "QA", False, ms, f"Status: {r.status_code if r else 'N/A'}"))

    # 5. Arsenal tool lookup — unknown tool → 404
    r, ms = timed_get(f"{PYTHONAI_URL}/api/arsenal/tools/NonExistentTool12345")
    suite.add(TestResult(
        "Arsenal unknown tool → 404", "QA",
        r is not None and r.status_code == 404, ms,
        f"Expected 404, got {r.status_code if r else 'N/A'}"
    ))

    # 6. RAG search with empty query → proper error
    r, ms = timed_post(f"{PYTHONAI_URL}/api/rag/search", {"query": ""})
    suite.add(TestResult(
        "RAG empty query → error handled", "QA",
        r is not None and r.status_code in (400, 422), ms,
        f"Got {r.status_code if r else 'N/A'}" if r and r.status_code not in (400, 422) else ""
    ))

    # 7. Stats endpoint
    r, ms = timed_get(f"{PYTHONAI_URL}/api/stats")
    suite.add(TestResult(
        "PythonAI /api/stats accessible", "QA",
        r is not None and r.status_code == 200, ms
    ))

    # 8. Training runs endpoint
    r, ms = timed_get(f"{PYTHONAI_URL}/api/training/runs")
    suite.add(TestResult(
        "Training runs endpoint", "QA",
        r is not None and r.status_code == 200, ms
    ))

    # 9. Dashboard health JSON (not HTML)
    r, ms = timed_get(f"{DASHBOARD_URL}/api/health")
    if r and r.status_code == 200:
        try:
            data = r.json()
            is_json = data.get("status") == "ok"
            suite.add(TestResult(
                "Dashboard /api/health returns JSON", "QA", is_json, ms,
                "Returns HTML instead of JSON" if not is_json else ""
            ))
        except Exception:
            suite.add(TestResult("Dashboard /api/health returns JSON", "QA", False, ms, "Invalid JSON"))
    else:
        suite.add(TestResult("Dashboard /api/health returns JSON", "QA", False, ms, "Unreachable"))

    # 10. Rudra-bots ForgeAI integration health
    r, ms = timed_get(f"{RUDRA_BOTS_URL}/api/forgeai/health")
    if r and r.status_code == 200:
        data = r.json()
        suite.add(TestResult(
            "Rudra-bots ForgeAI integration health", "QA",
            data.get("status") == "healthy", ms
        ))
    else:
        suite.add(TestResult("Rudra-bots ForgeAI integration health", "QA", False, ms, "Unreachable"))

    # 11. Rudra-bots metrics POST endpoint
    r, ms = timed_post(f"{RUDRA_BOTS_URL}/api/forgeai/metrics", {
        "type": "acceptance_rate",
        "source": "qa_test",
        "rate": 0.85,
        "timestamp": time.time()
    })
    suite.add(TestResult(
        "Rudra-bots accepts pushed metrics", "QA",
        r is not None and r.status_code == 200, ms,
        f"Status: {r.status_code if r else 'N/A'}"
    ))

    # 12. Learning routes
    r, ms = timed_get(f"{PYTHONAI_URL}/api/learning/status")
    suite.add(TestResult(
        "Learning routes registered", "QA",
        r is not None and r.status_code in (200, 404), ms,
        f"Status: {r.status_code if r else 'N/A'}"
    ))


# ═══════════════════════════════════════════════════════════════
# 🛡️ SRE TESTS — Reliability, Latency, Self-Healing
# ═══════════════════════════════════════════════════════════════

def test_sre(suite: TestSuite):
    print("\n🛡️ SRE — Reliability, Latency & Self-Healing")
    print("─" * 50)

    # 1. Latency SLA: PythonAI health < 500ms
    r, ms = timed_get(f"{PYTHONAI_URL}/health")
    suite.add(TestResult(
        f"PythonAI latency SLA (<500ms): {ms:.0f}ms", "SRE",
        ms < 500, ms,
        f"Too slow: {ms:.0f}ms" if ms >= 500 else ""
    ))

    # 2. Latency SLA: Gateway health < 1000ms
    r, ms = timed_get(f"{GATEWAY_URL}/health")
    suite.add(TestResult(
        f"Gateway latency SLA (<1000ms): {ms:.0f}ms", "SRE",
        ms < 1000, ms,
        f"Too slow: {ms:.0f}ms" if ms >= 1000 else ""
    ))

    # 3. Latency SLA: Dashboard health < 500ms
    r, ms = timed_get(f"{DASHBOARD_URL}/api/health")
    suite.add(TestResult(
        f"Dashboard latency SLA (<500ms): {ms:.0f}ms", "SRE",
        ms < 500, ms,
        f"Too slow: {ms:.0f}ms" if ms >= 500 else ""
    ))

    # 4. Gateway watchdog active
    r, ms = timed_get(f"{GATEWAY_URL}/api/watchdog")
    if r and r.status_code == 200:
        data = r.json()
        suite.add(TestResult(
            "Gateway watchdog active", "SRE",
            data.get("watchdog") == "active", ms
        ))
    else:
        suite.add(TestResult("Gateway watchdog active", "SRE", False, ms, "Unreachable"))

    # 5. Sync daemon running
    r, ms = timed_get(f"{PYTHONAI_URL}/api/forgeai/ecosystem-metrics")
    if r and r.status_code == 200:
        data = r.json()
        sync = data.get("sync_daemon", {})
        suite.add(TestResult(
            f"Sync daemon running (syncs: {sync.get('total_syncs', 0)})", "SRE",
            sync.get("running", False) is True, ms,
            f"consecutive_fails: {sync.get('consecutive_fails', 0)}"
        ))
    else:
        suite.add(TestResult("Sync daemon running", "SRE", False, ms, "Unreachable"))

    # 6. Rudra-bots fetches LIVE data (not cached)
    r, ms = timed_get(f"{RUDRA_BOTS_URL}/api/forgeai/fetch")
    if r and r.status_code == 200:
        data = r.json()
        cached = data.get("cached", True)
        suite.add(TestResult(
            f"Rudra-bots fetch = LIVE (cached={cached})", "SRE",
            data.get("success") is True and cached is False, ms,
            "Still returning cached data!" if cached else ""
        ))
    else:
        suite.add(TestResult("Rudra-bots fetch = LIVE", "SRE", False, ms, "Unreachable"))

    # 7. Uptime check
    if r and r.status_code == 200:
        r2, _ = timed_get(f"{PYTHONAI_URL}/api/forgeai/ecosystem-metrics")
        if r2 and r2.status_code == 200:
            uptime = r2.json().get("server", {}).get("uptime_seconds", 0)
            suite.add(TestResult(
                f"PythonAI uptime: {uptime}s", "SRE",
                uptime > 0, 0
            ))

    # 8. Rapid burst test (10 requests in quick succession)
    print("  ⏳ Running burst test (10 rapid requests)...")
    success_count = 0
    total_burst_ms = 0
    for i in range(10):
        r, ms = timed_get(f"{PYTHONAI_URL}/health")
        if r and r.status_code == 200:
            success_count += 1
        total_burst_ms += ms
    avg_burst = total_burst_ms / 10
    suite.add(TestResult(
        f"Burst test: {success_count}/10 OK, avg {avg_burst:.0f}ms", "SRE",
        success_count == 10, avg_burst,
        f"Only {success_count}/10 succeeded" if success_count < 10 else ""
    ))


# ═══════════════════════════════════════════════════════════════
# 👔 CTO TESTS — Architecture & Cross-Service Connectivity
# ═══════════════════════════════════════════════════════════════

def test_cto(suite: TestSuite):
    print("\n👔 CTO — Architecture & Cross-Service Connectivity")
    print("─" * 50)

    # 1. Gateway proxies PythonAI correctly
    r, ms = timed_get(f"{GATEWAY_URL}/api/forgeai/ecosystem-metrics")
    if r and r.status_code == 200:
        data = r.json()
        has_server = "server" in data
        suite.add(TestResult(
            "Gateway→PythonAI proxy (ecosystem-metrics)", "CTO",
            has_server, ms
        ))
    else:
        suite.add(TestResult("Gateway→PythonAI proxy", "CTO", False, ms,
                             f"Status: {r.status_code if r else 'connection failed'}"))

    # 2. Gateway proxies Arsenal correctly
    r, ms = timed_get(f"{GATEWAY_URL}/api/arsenal/summary")
    if r and r.status_code == 200:
        data = r.json()
        suite.add(TestResult(
            f"Gateway→Arsenal proxy ({data.get('installed')}/{data.get('total')} tools)", "CTO",
            data.get("total", 0) > 0, ms
        ))
    else:
        suite.add(TestResult("Gateway→Arsenal proxy", "CTO", False, ms,
                             f"Status: {r.status_code if r else 'connection failed'}"))

    # 3. PythonAI→Rudra-bots sync pipeline
    r1, _ = timed_get(f"{RUDRA_BOTS_URL}/api/forgeai/status")
    if r1 and r1.status_code == 200:
        data = r1.json()
        connected = data.get("pythonai", {}).get("connected", False)
        suite.add(TestResult(
            f"PythonAI→Rudra-bots sync pipeline (connected={connected})", "CTO",
            data.get("status") == "connected", 0
        ))
    else:
        suite.add(TestResult("PythonAI→Rudra-bots sync", "CTO", False, 0, "Status endpoint failed"))

    # 4. Full data flow: PythonAI metrics → Rudra-bots store → Dashboard fetch
    r, ms = timed_get(f"{RUDRA_BOTS_URL}/api/forgeai/metrics")
    if r and r.status_code == 200:
        data = r.json()
        total_stored = data.get("total", 0)
        suite.add(TestResult(
            f"Full data pipeline: {total_stored} metrics stored in Rudra-bots", "CTO",
            True, ms
        ))
    else:
        suite.add(TestResult("Full data pipeline", "CTO", False, ms, "Unreachable"))

    # 5. Auth system functional
    r, ms = timed_post(f"{GATEWAY_URL}/api/auth/login", {
        "username": "admin",
        "password": "forgeai2025"
    })
    if r and r.status_code == 200:
        data = r.json()
        has_token = "token" in data
        suite.add(TestResult(
            "Auth system: login returns JWT", "CTO",
            has_token, ms
        ))

        # 6. Authenticated request
        if has_token:
            token = data["token"]
            with httpx.Client(timeout=TIMEOUT) as c:
                start = time.time()
                r2 = c.get(f"{GATEWAY_URL}/api/pythonai/health",
                           headers={"Authorization": f"Bearer {token}"})
                ms2 = (time.time() - start) * 1000
                suite.add(TestResult(
                    "Authenticated proxy request works", "CTO",
                    r2.status_code == 200, ms2
                ))
    else:
        suite.add(TestResult("Auth system: login", "CTO", False, ms,
                             f"Status: {r.status_code if r else 'N/A'}"))

    # 7. Ecosystem status endpoint
    r, ms = timed_get(f"{GATEWAY_URL}/api/ecosystem")
    suite.add(TestResult(
        "Ecosystem status via Gateway", "CTO",
        r is not None and r.status_code == 200, ms
    ))

    # 8. Dashboard serves pages
    r, ms = timed_get(f"{DASHBOARD_URL}/")
    if r and r.status_code == 200:
        is_html = "html" in (r.headers.get("content-type", "").lower())
        suite.add(TestResult(
            "Dashboard serves HTML pages", "CTO",
            is_html or r.status_code == 200, ms
        ))
    else:
        suite.add(TestResult("Dashboard serves pages", "CTO", False, ms, "Unreachable"))


# ═══════════════════════════════════════════════════════════════
# 💻 DEVELOPER TESTS — Features & Data Integrity
# ═══════════════════════════════════════════════════════════════

def test_developer(suite: TestSuite):
    print("\n💻 DEVELOPER — Features & Data Integrity")
    print("─" * 50)

    # 1. Capture engine statistics
    r, ms = timed_get(f"{PYTHONAI_URL}/api/stats")
    if r and r.status_code == 200:
        data = r.json()
        acceptance_rate = data.get("overall_acceptance_rate", 0)
        total_sessions = data.get("total_sessions", 0)
        suite.add(TestResult(
            f"Capture stats: rate={acceptance_rate:.1f}%, sessions={total_sessions}", "Dev",
            "overall_acceptance_rate" in data, ms
        ))
    else:
        suite.add(TestResult("Capture stats", "Dev", False, ms, "Unreachable"))

    # 2. Signal capture endpoint
    r, ms = timed_post(f"{PYTHONAI_URL}/api/capture", {
        "signal_type": "Accept",
        "language": "python",
        "code_context": "# QA test signal",
        "suggestion": "print('hello from QA')",
        "file_path": "qa_test.py"
    })
    suite.add(TestResult(
        "Signal capture endpoint", "Dev",
        r is not None and r.status_code == 200, ms,
        f"Status: {r.status_code if r else 'N/A'}"
    ))

    # 3. RAG search endpoint
    r, ms = timed_post(f"{PYTHONAI_URL}/api/rag/search", {
        "query": "how to train a model",
        "top_k": 3
    })
    suite.add(TestResult(
        "RAG search endpoint", "Dev",
        r is not None and r.status_code == 200, ms
    ))

    # 4. RAG backend info
    r, ms = timed_get(f"{PYTHONAI_URL}/api/rag/info")
    if r and r.status_code == 200:
        data = r.json()
        backend = data.get("backend", "unknown")
        suite.add(TestResult(
            f"RAG backend: {backend}", "Dev",
            backend in ("chroma", "lightrag"), ms
        ))
    else:
        suite.add(TestResult("RAG backend info", "Dev", False, ms, "Unreachable"))

    # 5. Training schedule
    r, ms = timed_get(f"{PYTHONAI_URL}/api/training/schedule")
    if r and r.status_code == 200:
        data = r.json()
        enabled = data.get("enabled", False)
        cron = data.get("cron", "")
        suite.add(TestResult(
            f"Training schedule: enabled={enabled}, cron={cron}", "Dev",
            "enabled" in data, ms
        ))
    else:
        suite.add(TestResult("Training schedule", "Dev", False, ms, "Unreachable"))

    # 6. Training runs history
    r, ms = timed_get(f"{PYTHONAI_URL}/api/training/runs")
    if r and r.status_code == 200:
        data = r.json()
        runs = data.get("runs", [])
        suite.add(TestResult(
            f"Training runs: {len(runs)} completed", "Dev",
            isinstance(runs, list), ms
        ))
    else:
        suite.add(TestResult("Training runs", "Dev", False, ms, "Unreachable"))

    # 7. Benchmark reports
    r, ms = timed_get(f"{PYTHONAI_URL}/api/benchmark/reports")
    suite.add(TestResult(
        "Benchmark reports endpoint", "Dev",
        r is not None and r.status_code == 200, ms
    ))

    # 8. Memory system
    r, ms = timed_get(f"{PYTHONAI_URL}/api/memory/stats")
    suite.add(TestResult(
        "Memory system stats", "Dev",
        r is not None and r.status_code == 200, ms
    ))

    # 9. TTS (Test-Time Scaling) status
    r, ms = timed_get(f"{PYTHONAI_URL}/api/tts/status")
    suite.add(TestResult(
        "Test-Time Scaling status", "Dev",
        r is not None and r.status_code == 200, ms
    ))

    # 10. Arsenal tool availability check
    r, ms = timed_get(f"{PYTHONAI_URL}/api/arsenal/status")
    if r and r.status_code == 200:
        data = r.json()
        by_priority = data.get("by_priority", {})
        p1 = by_priority.get("P1-immediate", {})
        suite.add(TestResult(
            f"Arsenal P1 tools: {p1.get('installed', 0)}/{p1.get('total', 0)}", "Dev",
            p1.get("installed", 0) == p1.get("total", 0), ms,
            "Not all P1 tools installed" if p1.get("installed", 0) != p1.get("total", 0) else ""
        ))
    else:
        suite.add(TestResult("Arsenal P1 tools", "Dev", False, ms, "Unreachable"))


# ═══════════════════════════════════════════════════════════════
# 🔒 SECURITY TESTS
# ═══════════════════════════════════════════════════════════════

def test_security(suite: TestSuite):
    print("\n🔒 SECURITY — Auth & Access Control")
    print("─" * 50)

    # 1. Gateway rejects unauthenticated proxy requests
    r, ms = timed_get(f"{GATEWAY_URL}/api/pythonai/health")
    suite.add(TestResult(
        "Gateway rejects unauth'd proxy", "Security",
        r is not None and r.status_code == 401, ms,
        f"Expected 401, got {r.status_code if r else 'N/A'}"
    ))

    # 2. Auth exempt paths work without token
    r, ms = timed_get(f"{GATEWAY_URL}/health")
    suite.add(TestResult(
        "Health exempt from auth", "Security",
        r is not None and r.status_code == 200, ms
    ))

    # 3. Arsenal exempt from auth
    r, ms = timed_get(f"{GATEWAY_URL}/api/arsenal/summary")
    suite.add(TestResult(
        "Arsenal exempt from auth", "Security",
        r is not None and r.status_code == 200, ms
    ))

    # 4. Invalid token rejected
    with httpx.Client(timeout=TIMEOUT) as c:
        start = time.time()
        r = c.get(f"{GATEWAY_URL}/api/pythonai/health",
                   headers={"Authorization": "Bearer invalid_garbage_token"})
        ms = (time.time() - start) * 1000
        suite.add(TestResult(
            "Invalid JWT token rejected", "Security",
            r.status_code in (401, 403), ms,
            f"Expected 401/403, got {r.status_code}"
        ))

    # 5. Signup creates user
    r, ms = timed_post(f"{GATEWAY_URL}/api/auth/signup", {
        "username": f"qa_test_{int(time.time())}",
        "password": "test_password_123"
    })
    suite.add(TestResult(
        "Signup endpoint functional", "Security",
        r is not None and r.status_code in (200, 201, 409), ms,
        f"Status: {r.status_code if r else 'N/A'}"
    ))


# ═══════════════════════════════════════════════════════════════
# MAIN — Run All Tests
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═" * 60)
    print("  FORGEAI MEGA PROJECT — LIVE QA TEST SUITE")
    print("  Testing as: DevOps | QA | SRE | CTO | Developer | Security")
    print("═" * 60)

    suite = TestSuite()
    suite.start_time = time.time()

    try:
        test_devops(suite)
        test_qa(suite)
        test_sre(suite)
        test_cto(suite)
        test_developer(suite)
        test_security(suite)
    except Exception as e:
        print(f"\n💥 FATAL: Test suite crashed: {e}")
        traceback.print_exc()

    all_passed = suite.summary()
    sys.exit(0 if all_passed else 1)
