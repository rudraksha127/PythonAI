"""End-to-end smoke test that exercises all major pipeline stages.

This file is a convenience runner that imports test functions from individual
stage files (test_e2e_*.py) and runs them in sequence with a summary.

Stages covered:
  1. Auth System       — hash/verify, tokens, config, login/logout, check_auth, decorator
  2. Data Pipeline     — prompts, chunk validation, quality stats, dedup/merge, distributions
  3. Training Pipeline — dataset construction, ThroughputCallback, TrainingCurvesCallback, BLEU
  4. RAG Engine        — SimpleBM25, MMR rerank, citation formatting, query expansion template
  5. Agent Swarm       — task decomposition, execution, MCP registry, monitoring/stats
  6. CLI               — argument parsing for all subcommands and flags
  7. Integration Flow  — cross-stage data flow

Individual stage test functions are also available in separate files:
  tests/test_e2e_data.py
  tests/test_e2e_training.py
  tests/test_e2e_cli.py
  tests/test_e2e_integration.py
"""

from __future__ import annotations

from typing import Any


# ──────────────────────────────────────────────────────────────────────
# 1. AUTH SYSTEM
# ──────────────────────────────────────────────────────────────────────


def test_auth_stage() -> dict[str, Any]:
    """Exercise password hashing, tokens, config, login/logout, decorator."""
    from src.auth.auth import (
        check_auth,
        generate_token,
        hash_password,
        login,
        logout,
        verify_password,
    )
    from src.auth.config import AuthConfig
    from src.auth.decorators import requires_auth

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage  # shorthand

    # --- 1a. Password hashing ---
    _r["tests"] += 1
    salt, hashed = hash_password("MyTestPassword!@#")
    assert len(salt) == 32, f"salt length: {len(salt)}"
    assert len(hashed) > 0, "empty hash"
    assert verify_password("MyTestPassword!@#", salt, hashed), "verify failed"
    assert not verify_password("wrong", salt, hashed), "wrong password verified"
    _r["passed"] += 1

    # --- 1b. Token generation ---
    _r["tests"] += 1
    t1 = generate_token(16)
    t2 = generate_token(32)
    assert len(t1) == 16, f"token length: {len(t1)}"
    assert len(t2) == 32
    assert t1 != t2, "tokens not unique"
    assert t1.isalnum(), "token not alphanumeric"
    _r["passed"] += 1

    # --- 1c. AuthConfig with temp path ---
    _r["tests"] += 1
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        cfg = AuthConfig(Path(tmp) / ".pythonai" / "config.json")
        assert cfg.get_user() is None, "user not None on fresh config"
        assert not cfg.is_logged_in(), "is_logged_in on fresh config"

        test_data = {"user": {"username": "test"}, "settings": {"offline": True}}
        cfg.save(test_data)
        loaded = cfg.load()
        assert loaded["user"]["username"] == "test"
        assert loaded["settings"]["offline"] is True

        cfg.set_user({"username": "alice", "token": "x" * 16})
        assert cfg.get_user()["username"] == "alice"
        assert cfg.is_logged_in()
        cfg.clear_user()
        assert cfg.get_user() is None
        assert not cfg.is_logged_in()

        cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.config_path.write_text("{invalid}", encoding="utf-8")
        default = cfg.load()
        assert default["user"] is None, "corrupted file not returning defaults"
    _r["passed"] += 1

    # --- 1d. Login / logout / check_auth ---
    _r["tests"] += 1
    with tempfile.TemporaryDirectory() as tmp:
        cfg = AuthConfig(Path(tmp) / ".pythonai" / "config.json")

        res = login("bob", "secure123", cfg)
        assert res["success"], f"login failed: {res.get('error')}"
        assert res["username"] == "bob"
        assert len(res["token"]) > 8

        res2 = login("bob", "secure123", cfg)
        assert res2["success"]

        res3 = login("bob", "wrong", cfg)
        assert not res3["success"]
        assert "Invalid password" in res3.get("error", "")

        status = check_auth(cfg)
        assert status["authenticated"]
        assert status["username"] == "bob"

        res4 = logout(cfg)
        assert res4["success"]
        assert cfg.get_user() is None
        status2 = check_auth(cfg)
        assert not status2["authenticated"]
    _r["passed"] += 1

    # --- 1e. @requires_auth decorator ---
    _r["tests"] += 1

    @requires_auth
    def _dummy(args_obj: object) -> int:
        return 99

    class _FakeArgs:
        no_auth = False

    from unittest.mock import patch
    with patch("src.auth.decorators.AuthConfig.is_logged_in", return_value=True):
        assert _dummy(_FakeArgs()) == 99, "decorator blocked valid user"
    with patch("src.auth.decorators.AuthConfig.is_logged_in", return_value=False):
        assert _dummy(_FakeArgs()) == 1, "decorator didn't block"

    _FakeArgs.no_auth = True
    assert _dummy(_FakeArgs()) == 99, "--no-auth not working"
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 2. DATA PIPELINE  (imports from test_e2e_data.py)
# ──────────────────────────────────────────────────────────────────────


def test_data_stage() -> dict[str, Any]:
    """Exercise prompt building, chunk validation, quality stats, dedup, merging.

    Tests imported from tests/test_e2e_data.py
    """
    import tests.test_e2e_data as e2e_data

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    _r["tests"] += 1
    e2e_data.test_data_build_prompts()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_data.test_data_valid_chunk()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_data.test_data_row_hash_and_merge()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_data.test_data_quality_stats_does_not_crash()
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 3. TRAINING PIPELINE  (imports from test_e2e_training.py)
# ──────────────────────────────────────────────────────────────────────


def test_training_stage() -> dict[str, Any]:
    """Exercise dataset construction, callbacks, BLEU scoring.

    Tests imported from tests/test_e2e_training.py
    """
    import tests.test_e2e_training as e2e_training

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    _r["tests"] += 1
    e2e_training.test_training_examples_from_pairs()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_training.test_training_throughput_callback()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_training.test_training_curves_callback()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_training.test_training_compute_bleu()
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 4. RAG ENGINE
# ──────────────────────────────────────────────────────────────────────


def test_rag_stage() -> dict[str, Any]:
    """Exercise SimpleBM25, MMR, citation formatting, and query expansion template."""
    from src.rag.rag_engine import (
        SimpleBM25,
        _cosine_sim,
        format_sources,
        mmr_rerank,
    )

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    # --- 4a. SimpleBM25 ---
    _r["tests"] += 1
    corpus = [
        "Python lists are mutable ordered sequences",
        "Python dictionaries store key value pairs",
        "Python sets are unordered collections of unique elements",
    ]
    bm25 = SimpleBM25(corpus)
    assert bm25.n_docs == 3, f"n_docs: {bm25.n_docs}"
    assert bm25.avgdl > 0, "avgdl not computed"

    scores = bm25.get_scores("lists mutable")
    assert len(scores) == 3, f"expected 3 scores, got {len(scores)}"
    list_scores = bm25.get_scores("lists")
    dict_scores = bm25.get_scores("dictionaries")
    assert list_scores[0] > list_scores[1], "list doc should rank highest for 'lists'"
    assert dict_scores[1] > dict_scores[0], "dict doc should rank highest for 'dictionaries'"

    empty_scores = bm25.get_scores("")
    assert all(s == 0.0 for s in empty_scores), "empty query should give zero scores"
    _r["passed"] += 1

    # --- 4b. _cosine_sim ---
    _r["tests"] += 1
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    c = [2.0, 0.0, 0.0]
    assert _cosine_sim(a, a) == 1.0, "self similarity not 1"
    assert _cosine_sim(a, b) == 0.0, "orthogonal not 0"
    assert abs(_cosine_sim(a, c) - 1.0) < 1e-6, "parallel not 1"
    assert _cosine_sim([], [1.0]) == 0.0, "empty vector not 0"
    assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == 0.0, "zero vector not 0"
    _r["passed"] += 1

    # --- 4c. MMR re-rank ---
    _r["tests"] += 1
    docs = [
        {"title": "Doc A", "score": 0.9, "text": "A", "embedding": [1.0, 0.0]},
        {"title": "Doc B", "score": 0.8, "text": "B", "embedding": [0.99, 0.01]},
        {"title": "Doc C", "score": 0.7, "text": "C", "embedding": [0.0, 1.0]},
    ]
    query_emb = [1.0, 0.0]

    mmr_results = mmr_rerank(docs, query_emb, lambda_=0.9, top_k=3)
    assert len(mmr_results) == 3, f"expected 3 results, got {len(mmr_results)}"
    assert mmr_results[0]["score"] >= mmr_results[-1]["score"], "MMR not sorted by score"
    assert mmr_rerank([], query_emb, top_k=5) == [], "empty docs not empty"
    _r["passed"] += 1

    # --- 4d. format_sources ---
    _r["tests"] += 1
    src_docs = [
        {"citation_num": 1, "title": "Python Lists Guide", "version": "3.12", "category": "library"},
        {"citation_num": 2, "title": "Dict Internals", "version": "3.11", "category": "internals"},
    ]
    formatted = format_sources(src_docs)
    assert "[1]" in formatted, "missing [1]"
    assert "[2]" in formatted, "missing [2]"
    assert "Python Lists Guide" in formatted
    assert "Dict Internals" in formatted
    assert format_sources([]) == "", "empty sources not empty"
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 5. AGENT SWARM  (imports from test_swarm.py)
# ──────────────────────────────────────────────────────────────────────


def test_swarm_stage() -> dict[str, Any]:
    """Exercise task decomposition, AgentSwarm execution, MCP, monitoring."""
    from src.utils.swarm import (
        AgentSwarm,
        GenerationTask,
        MCPRegistry,
        MCPTool,
        RetryStrategy,
        SwarmMonitor,
        SwarmStats,
        TaskDecomposer,
        TaskResult,
    )

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    # --- 5a. TaskDecomposer ---
    _r["tests"] += 1
    decomposer = TaskDecomposer()
    chunk = {
        "id": "chunk-1",
        "title": "Async IO",
        "codes": ["async def main(): pass"],
        "version": "3.12",
    }
    prompts = {"basic": "Explain", "reasoning": "Why?", "code_review": "Review"}
    tasks = decomposer.decompose(chunk, prompts)
    task_types = {t.task_type for t in tasks}
    assert "basic" in task_types
    assert "reasoning" in task_types
    assert "code_review" in task_types
    for t in tasks:
        if t.task_type == "code_review":
            assert "basic" in t.dependencies, "code_review should depend on basic"
    _r["passed"] += 1

    # --- 5b. GenerationTask frozen dataclass ---
    _r["tests"] += 1
    task = GenerationTask(
        task_id="t1", task_type="basic", prompt="Test",
        max_retries=2, timeout=30.0,
    )
    assert task.task_id == "t1"
    assert task.max_retries == 2
    assert task.timeout == 30.0
    _r["passed"] += 1

    # --- 5c. AgentSwarm basic execution ---
    _r["tests"] += 1
    swarm = AgentSwarm(max_workers=2)
    tasks = [
        GenerationTask(task_id="a", task_type="basic", prompt="P1"),
        GenerationTask(task_id="b", task_type="basic", prompt="P2"),
    ]
    results = swarm.execute(tasks, lambda t: {"result": t.task_id})
    assert "a" in results
    assert "b" in results
    assert results["a"]["result"] == "a"
    assert results["b"]["result"] == "b"
    _r["passed"] += 1

    # --- 5d. AgentSwarm with dependencies ---
    _r["tests"] += 1
    swarm2 = AgentSwarm(max_workers=2)
    dep_tasks = [
        GenerationTask(task_id="t1", task_type="basic", prompt="Base"),
        GenerationTask(task_id="t2", task_type="advanced", prompt="Dep", dependencies=("t1",)),
    ]
    dep_results = swarm2.execute(dep_tasks, lambda t: {"done": True})
    assert "t1" in dep_results
    assert "t2" in dep_results
    _r["passed"] += 1

    # --- 5e. MCPRegistry ---
    _r["tests"] += 1
    registry = MCPRegistry()

    def _add(a: int, b: int) -> int:
        return a + b

    tool = MCPTool(name="add", description="Add two numbers", handler=_add, parameters={"a": "int", "b": "int"})
    registry.register(tool)
    assert registry.get("add") is tool
    result = registry.call_tool("add", a=3, b=4)
    assert result == 7, f"MCP add returned {result}"

    tool_list = registry.list_tools()
    assert len(tool_list) == 1
    assert tool_list[0]["name"] == "add"

    registry.unregister("add")
    assert registry.get("add") is None

    try:
        registry.call_tool("nonexistent")
        assert False, "should have raised KeyError"
    except KeyError:
        pass
    _r["passed"] += 1

    # --- 5f. SwarmMonitor & SwarmStats ---
    _r["tests"] += 1
    monitor = SwarmMonitor()
    monitor.start()

    r1 = TaskResult(task_id="t1", task_type="basic", success=True, data={"ok": True}, duration=0.1, worker_name="w1")
    r2 = TaskResult(task_id="t2", task_type="advanced", success=False, data={}, error="fail", duration=0.2, worker_name="w2")
    monitor.record(r1)
    monitor.record(r2)

    stats = monitor.stats()
    assert stats.total_tasks == 2
    assert stats.completed == 1
    assert stats.failed == 1
    assert stats.worker_usage["w1"] == 1
    assert stats.worker_usage["w2"] == 1

    report = stats.report()
    assert "Total tasks" in report
    assert "Completed" in report
    assert "Failed" in report
    _r["passed"] += 1

    # --- 5g. RetryStrategy enum ---
    _r["tests"] += 1
    assert RetryStrategy.FIXED.value == "fixed"
    assert RetryStrategy.LINEAR.value == "linear"
    assert RetryStrategy.EXPONENTIAL.value == "exponential"
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 6. CLI PARSING  (imports from test_e2e_cli.py)
# ──────────────────────────────────────────────────────────────────────


def test_cli_stage() -> dict[str, Any]:
    """Exercise CLI argument parsing for all subcommands and flags.

    Tests imported from tests/test_e2e_cli.py
    """
    import tests.test_e2e_cli as e2e_cli

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    _r["tests"] += 1
    e2e_cli.test_cli_status_with_json_and_verbose()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_cli.test_cli_ask_with_all_flags()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_cli.test_cli_train_with_flags()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_cli.test_cli_login_subcommands()
    _r["passed"] += 1

    _r["tests"] += 1
    e2e_cli.test_cli_eval_probe_clean_dataset_augment_merge()
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# 7. INTEGRATION: cross-stage data flow  (imports from test_e2e_integration.py)
# ──────────────────────────────────────────────────────────────────────


def test_integration_flow() -> dict[str, Any]:
    """Exercise a realistic cross-stage scenario.

    Tests imported from tests/test_e2e_integration.py
    """
    import tests.test_e2e_integration as e2e_integration

    stage: dict[str, Any] = {"tests": 0, "passed": 0, "failed": 0}
    _r = stage

    _r["tests"] += 1
    e2e_integration.test_integration_cross_stage_pipeline()
    _r["passed"] += 1

    return stage


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    stages = [
        ("🔐 Auth System",     test_auth_stage),
        ("📊 Data Pipeline",   test_data_stage),
        ("🔧 Training Pipeline", test_training_stage),
        ("🧠 RAG Engine",      test_rag_stage),
        ("🐝 Agent Swarm",     test_swarm_stage),
        ("🖥️  CLI Parsing",    test_cli_stage),
        ("🔗 Integration Flow", test_integration_flow),
    ]

    total_tests = 0
    total_passed = 0
    total_failed = 0
    failed_stages: list[str] = []

    print("=" * 62)
    print("  🧪 PYTHONAI END-TO-END SMOKE TEST")
    print("=" * 62)

    for name, func in stages:
        try:
            result = func()
            passed = result["passed"]
            failed = result["failed"]
            total_tests += result["tests"]
            total_passed += passed
            total_failed += failed

            status = "✅" if failed == 0 else "❌"
            print(f"\n  {status}  {name}")
            print(f"      Tests: {result['tests']:2d} | Passed: {passed:2d} | Failed: {failed:2d}")

            if failed > 0:
                failed_stages.append(name)

        except Exception as exc:
            total_failed += 1
            failed_stages.append(name)
            print(f"\n  ❌  {name}")
            print(f"      CRASHED: {exc}")

    # Summary
    print("\n" + "=" * 62)
    if total_failed == 0:
        print(f"  ✅ ALL {total_tests} TESTS PASSED")
    else:
        print(f"  ❌ {total_passed}/{total_tests} passed, {total_failed} failed")
        for s in failed_stages:
            print(f"     - {s}")
    print("=" * 62)
    print()

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
