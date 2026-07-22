"""Comprehensive unit tests for all ForgeAI modules."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest


# ═══════════════════════════════════════
# Monitoring Tests
# ═══════════════════════════════════════


class TestMonitoring:
    """Tests for the monitoring module."""

    def setup_method(self) -> None:
        # Reset singleton for clean test
        import src.monitoring
        src.monitoring._metrics = None

    def test_record_api_request(self) -> None:
        from src.monitoring import get_metrics
        metrics = get_metrics()
        metrics.record_api_request("/api/test", "GET", 200, 50.0)
        metrics.record_api_request("/api/test", "GET", 200, 30.0)
        summary = metrics.get_summary()
        assert summary["api"]["total_requests"] == 2
        assert summary["api"]["overall_error_rate"] == 0.0

    def test_record_provider_call(self) -> None:
        from src.monitoring import get_metrics
        metrics = get_metrics()
        metrics.record_provider_call("openai", True, 100.0, prompt_tokens=50, completion_tokens=30, cost=0.002)
        summary = metrics.get_summary()
        assert summary["providers"]["total_calls"] >= 1

    def test_prometheus_format(self) -> None:
        from src.monitoring import get_metrics
        metrics = get_metrics()
        metrics.record_api_request("/api/test", "GET", 200, 10.0)
        text = metrics.get_prometheus_text()
        assert "forgeai_uptime_seconds" in text
        assert "forgeai_api_requests_total" in text

    def test_health_report(self) -> None:
        from src.monitoring import create_health_report
        report = create_health_report(version="test", db_ok=True, inference_connected=True)
        assert report["status"] == "healthy"
        assert report["version"] == "test"
        assert "components" in report
        assert report["components"]["database"]["status"] == "ok"


# ═══════════════════════════════════════
# Cache Tests
# ═══════════════════════════════════════


class TestSmartCache:
    """Tests for the cache module."""

    def setup_method(self) -> None:
        from src.cache import get_cache, CacheConfig
        self.cache = get_cache(CacheConfig(
            enabled=True,
            max_size=10,
            ttl_seconds=60,
            enable_semantic=False,
        ))

    def test_set_and_get_exact(self) -> None:
        self.cache.set("hello", "world", provider="test")
        result = self.cache.get("hello", provider="test")
        assert result == "world"

    def test_cache_miss(self) -> None:
        result = self.cache.get("nonexistent", provider="test")
        assert result is None

    def test_ttl_expiry(self) -> None:
        import time
        self.cache.set("quick", "data", provider="test", ttl=0.001)
        time.sleep(0.01)
        result = self.cache.get("quick", provider="test")
        assert result is None

    def test_invalidate(self) -> None:
        self.cache.set("temp", "value", provider="test")
        assert self.cache.invalidate("temp", provider="test") is True
        assert self.cache.get("temp", provider="test") is None

    def test_clear(self) -> None:
        self.cache.set("a", "1", provider="test")
        self.cache.set("b", "2", provider="test")
        cleared = self.cache.clear()
        assert cleared >= 2

    def test_get_stats(self) -> None:
        stats = self.cache.get_stats()
        assert "enabled" in stats
        assert "entries" in stats
        assert stats["enabled"] is True


# ═══════════════════════════════════════
# Retry Tests
# ═══════════════════════════════════════


class TestRetry:
    """Tests for the retry module."""

    def setup_method(self) -> None:
        from src.retry import get_retry_handler, RetryConfig
        self.handler = get_retry_handler(RetryConfig(
            max_retries=2,
            base_delay=0.01,
            circuit_breaker_threshold=3,
            circuit_breaker_reset_seconds=1,
        ))

    def test_is_retryable_rate_limit(self) -> None:
        from src.retry import is_retryable
        assert is_retryable(status_code=429) is True
        assert is_retryable(status_code=200) is False
        assert is_retryable(status_code=503) is True

    def test_classify_error(self) -> None:
        from src.retry import classify_error, RetryableErrorType
        assert classify_error(429) == RetryableErrorType.RATE_LIMIT
        assert classify_error(503) == RetryableErrorType.SERVICE_UNAVAILABLE
        assert classify_error(None, "timeout") == RetryableErrorType.TIMEOUT

    def test_circuit_breaker_initial_state(self) -> None:
        from src.retry import CircuitBreaker
        cb = CircuitBreaker(threshold=2, reset_seconds=1)
        assert cb.allow_request() is True
        assert cb.state.value == "closed"
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False
        assert cb.state.value == "open"

    def test_execute_success(self) -> None:
        def success_fn():
            return "ok"
        result = self.handler.execute(success_fn, provider="test")
        assert result == "ok"

    def test_get_stats(self) -> None:
        stats = self.handler.get_stats()
        assert "config" in stats
        assert "circuit_breakers" in stats


# ═══════════════════════════════════════
# Templates Tests
# ═══════════════════════════════════════


class TestTemplates:
    """Tests for the templates module."""

    def setup_method(self) -> None:
        import src.templates
        src.templates._manager = None
        self.manager = src.templates.get_template_manager(
            data_dir=Path(tempfile.mkdtemp())
        )

    def test_create_and_get(self) -> None:
        tmpl = self.manager.create(
            name="test-template",
            content="Hello {{name}}!",
            description="A test template",
            category="testing",
        )
        assert tmpl.name == "test-template"
        assert tmpl.version == 1
        assert "name" in tmpl.variables

    def test_render(self) -> None:
        self.manager.create(name="greet", content="Hello {{name}}!")
        result = self.manager.render("greet", name="World")
        assert result == "Hello World!"

    def test_render_missing_variable(self) -> None:
        self.manager.create(name="needs-var", content="{{missing}}")
        with pytest.raises(ValueError, match="Missing required variable"):
            self.manager.render("needs-var")

    def test_list_templates(self) -> None:
        templates = self.manager.list()
        assert len(templates) > 0

    def test_get_stats(self) -> None:
        stats = self.manager.get_stats()
        assert "total_templates" in stats
        assert stats["total_templates"] > 0

    def test_get_by_name(self) -> None:
        self.manager.create(name="unique-name", content="test")
        tmpl = self.manager.get_by_name("unique-name")
        assert tmpl is not None
        assert tmpl.name == "unique-name"


# ═══════════════════════════════════════
# Analytics Tests
# ═══════════════════════════════════════


class TestAnalytics:
    """Tests for the analytics module."""

    def setup_method(self) -> None:
        import src.analytics
        self.db_path = Path(tempfile.mkdtemp()) / "test_usage.db"
        self.tracker = src.analytics.UsageTracker(db_path=self.db_path)

    def test_log_call(self) -> None:
        rec_id = self.tracker.log_call(
            provider="openai",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            cost=0.003,
            user_id="test_user",
            project_id="test_project",
        )
        assert rec_id is not None
        assert len(rec_id) > 0

    def test_estimate_cost(self) -> None:
        from src.analytics import estimate_cost
        cost = estimate_cost("openai", "gpt-4o", 1000, 500)
        assert cost > 0

    def test_get_report(self) -> None:
        self.tracker.log_call(provider="openai", model="gpt-4", prompt_tokens=10, completion_tokens=5)
        report = self.tracker.get_report(days=7)
        assert report["totals"]["total_calls"] >= 1

    def test_cost_summary(self) -> None:
        self.tracker.log_call(provider="openai", model="gpt-4", prompt_tokens=10, completion_tokens=5)
        summary = self.tracker.get_cost_summary(days=30)
        assert "total_cost" in summary
        assert "provider_costs" in summary


# ═══════════════════════════════════════
# Git Hooks Tests
# ═══════════════════════════════════════


class TestGitHooks:
    """Tests for git_hooks module."""

    def test_compute_signal_weight_accept(self) -> None:
        from src.learning.git_hooks import compute_signal_weight
        weight = compute_signal_weight("accept")
        assert weight == 1.0

    def test_compute_signal_weight_reject(self) -> None:
        from src.learning.git_hooks import compute_signal_weight
        weight = compute_signal_weight("reject")
        # Base weight -0.5 clamped to 0.0 by max(0.0, weight)
        assert weight == 0.0

    def test_compute_signal_weight_pr_merge(self) -> None:
        from src.learning.git_hooks import compute_signal_weight
        weight = compute_signal_weight("pr_merge")
        # Base weight 1.5
        assert weight == 1.5

    def test_compute_signal_weight_test_pass(self) -> None:
        from src.learning.git_hooks import compute_signal_weight
        weight = compute_signal_weight("test_pass")
        assert weight == 2.0

    def test_signal_weight_with_edit_distance(self) -> None:
        from src.learning.git_hooks import compute_signal_weight
        weight = compute_signal_weight("edit", edit_distance=0.3)
        assert weight > 0.7
        assert weight < 1.0


# ═══════════════════════════════════════
# Battle Module Tests
# ═══════════════════════════════════════


class TestBattle:
    """Tests for the battle module."""

    def test_battle_config(self) -> None:
        from src.battle import BattleConfig
        config = BattleConfig(provider="openai", model="gpt-4")
        assert config.provider == "openai"

    def test_battle_request(self) -> None:
        from src.battle import BattleRequest, BattleConfig
        req = BattleRequest(
            prompt="test prompt",
            providers=[BattleConfig(provider="test", model="test-model")],
        )
        assert req.prompt == "test prompt"
        assert len(req.providers) == 1


# ═══════════════════════════════════════
# Completion Module Tests
# ═══════════════════════════════════════


class TestCompletion:
    """Tests for the completion module."""

    def test_find_possible_completions(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--test-flag", action="store_true")
        from src.completion import find_possible_completions
        comps = find_possible_completions(parser, ["--"])
        assert "--test-flag" in comps


# ═══════════════════════════════════════
# RBAC Tests
# ═══════════════════════════════════════


class TestRBAC:
    """Tests for RBAC module."""

    def setup_method(self) -> None:
        import tempfile
        import src.auth.rbac as rbac_module
        test_dir = tempfile.mkdtemp()
        self.rbac = rbac_module.RBACManager(data_dir=test_dir)
        # Reset global singleton for clean test
        rbac_module._rbac_manager = None

    def test_assign_role(self) -> None:
        result = self.rbac.assign_role("alice", "admin")
        assert result is True

    def test_has_permission_admin(self) -> None:
        self.rbac.assign_role("alice", "admin")
        assert self.rbac.has_permission("alice", "projects:create") is True
        assert self.rbac.has_permission("alice", "users:manage") is True

    def test_has_permission_developer(self) -> None:
        self.rbac.assign_role("bob", "developer")
        assert self.rbac.has_permission("bob", "projects:read") is True
        assert self.rbac.has_permission("bob", "projects:create") is False

    def test_project_access(self) -> None:
        self.rbac.assign_role("charlie", "manager")
        self.rbac.grant_project_access("charlie", "project-1")
        assert self.rbac.has_project_access("charlie", "project-1") is True
        assert self.rbac.has_project_access("charlie", "project-2") is False

    def test_revoke_project_access(self) -> None:
        self.rbac.assign_role("dave", "developer")
        self.rbac.grant_project_access("dave", "project-1")
        self.rbac.revoke_project_access("dave", "project-1")
        assert self.rbac.has_project_access("dave", "project-1") is False

    def test_list_users(self) -> None:
        self.rbac.assign_role("eve", "admin")
        users = self.rbac.list_users()
        assert len(users) >= 1
        assert any(u["username"] == "eve" for u in users)

    def test_get_role_permissions(self) -> None:
        from src.auth.rbac import ROLES
        assert "projects:create" in ROLES["admin"]["permissions"]
        assert "projects:read" in ROLES["developer"]["permissions"]


# ═══════════════════════════════════════
# RAG v2 Tests
# ═══════════════════════════════════════


class TestMultiViewEmbedder:
    """Tests for the multi-view embedder."""

    def setup_method(self) -> None:
        from src.rag.multi_view_embedder import MultiViewEmbedder
        self.embedder = MultiViewEmbedder()

    def test_extract_python_views(self) -> None:
        code = '''
def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello {name}"

class Greeter:
    """A greeter class."""
    def greet(self, name: str) -> str:
        return f"Hi {name}"
'''
        views = self.embedder.embed_chunk(code, language="python")
        assert "code_text" in views
        assert "docstring" in views or "signature" in views

    def test_multi_view_similarity(self) -> None:
        from src.rag.multi_view_embedder import multi_view_similarity
        query_emb = {"code_text": [0.1, 0.2, 0.3]}
        chunk_emb = {"code_text": [0.1, 0.2, 0.3]}
        score = multi_view_similarity(query_emb, chunk_emb)
        assert 0.0 <= score <= 1.0


class TestIncrementalIndexer:
    """Tests for the incremental indexer."""

    def test_has_basic_structure(self) -> None:
        from src.rag.incremental_indexer import IncrementalIndexer
        indexer = IncrementalIndexer()
        assert hasattr(indexer, "index_directory")
        assert hasattr(indexer, "index_file")
        assert hasattr(indexer, "get_stats")
        assert hasattr(indexer, "clear")
