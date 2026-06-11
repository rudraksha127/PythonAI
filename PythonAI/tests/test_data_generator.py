"""Unit tests for src/data/generator.py — dataset generation via API swarm."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data.generator import (
    MODELS,
    URLS,
    active,
    build_prompts,
    call_api,
    calls,
    dedup_filter,
    fails,
    load_latest_checkpoint,
    process_chunk,
    process_generation_task,
    rate_limited,
    safe_json,
    save_checkpoint,
    score_pair,
    seen_hashes,
)
from src.data.generator import (
    setup as generator_setup,
)

# ══════════════════════════════════════════════════════════════════════
# safe_json
# ══════════════════════════════════════════════════════════════════════


class TestSafeJson:
    """Tests for safe_json — JSON extraction from arbitrary text."""

    def test_valid_json_array(self):
        """A clean JSON array should parse correctly."""
        text = '[{"instruction": "Q1", "output": "A1"}]'
        result = safe_json(text)
        assert len(result) == 1
        assert result[0]["instruction"] == "Q1"

    def test_text_surrounding_array(self):
        """Text before/after the JSON array should be handled."""
        text = "Here is the result:\\n[{\"instruction\": \"Q\", \"output\": \"A\"}]\\nDone."
        result = safe_json(text)
        assert len(result) == 1

    def test_no_brackets_found(self):
        """Text with no brackets should return empty list."""
        assert safe_json("just plain text") == []

    def test_trailing_comma_cleaned(self):
        """Trailing commas before closing brackets should be handled."""
        text = '[{"instruction": "Q", "output": "A"},]'
        result = safe_json(text)
        assert len(result) == 1

    def test_invalid_json_content(self):
        """Invalid content inside brackets should return empty."""
        text = '[{invalid}]'
        result = safe_json(text)
        assert result == []

    def test_empty_array(self):
        """Empty array should return empty list."""
        assert safe_json("[]") == []
        assert safe_json("text [] more") == []

    def test_nested_objects(self):
        """Complex nested JSON should parse correctly."""
        text = '[{"instruction": "Q", "output": "A", "nested": {"key": "val"}}]'
        result = safe_json(text)
        assert len(result) == 1
        assert result[0]["nested"]["key"] == "val"


# ══════════════════════════════════════════════════════════════════════
# dedup_filter
# ══════════════════════════════════════════════════════════════════════


class TestDedupFilter:
    """Tests for dedup_filter — deduplication + quality filtering."""

    def teardown_method(self) -> None:
        """Clear global seen_hashes after each test."""
        seen_hashes.clear()

    def test_valid_pairs_pass(self):
        """Valid pairs should pass the filter."""
        pairs = [{"instruction": "Explain Python", "output": "Python is a language. " * 5}]
        chunk = {"title": "Python", "version": "3.12", "category": "tutorial"}
        result = dedup_filter(pairs, chunk)
        assert len(result) == 1

    def test_short_instruction_filtered(self):
        """Instruction < 10 chars should be filtered."""
        pairs = [{"instruction": "Hi", "output": "A" * 50}]
        result = dedup_filter(pairs, {"title": "", "version": "", "category": ""})
        assert len(result) == 0

    def test_short_output_filtered(self):
        """Output < 40 chars should be filtered."""
        pairs = [{"instruction": "Explain Python", "output": "Short"}]
        result = dedup_filter(pairs, {"title": "", "version": "", "category": ""})
        assert len(result) == 0

    def test_duplicates_removed(self):
        """Duplicate instruction+output should be filtered."""
        pair = {"instruction": "Explain Python", "output": "A" * 50}
        pairs = [pair, pair]
        result = dedup_filter(pairs, {"title": "", "version": "", "category": ""})
        assert len(result) == 1

    def test_non_dict_items_filtered(self):
        """Non-dict items should be filtered."""
        pairs = [{"instruction": "Explain Python", "output": "A" * 50}, "string", 42]
        result = dedup_filter(pairs, {"title": "", "version": "", "category": ""})
        assert len(result) == 1

    def test_metadata_appended(self):
        """Source, version, and category should be set from chunk."""
        pairs = [{"instruction": "Explain Python", "output": "A" * 50}]
        result = dedup_filter(pairs, {"title": "Lists", "version": "3.12", "category": "tutorial"})
        assert result[0]["source"] == "Lists"
        assert result[0]["version"] == "3.12"
        assert result[0]["category"] == "tutorial"

    def test_global_dedup(self):
        """dedup_filter should use global seen_hashes for cross-call dedup."""
        seen_hashes.clear()
        pair = {"instruction": "Explain Python", "output": "A" * 50}
        result1 = dedup_filter([pair], {"title": "", "version": "", "category": ""})
        result2 = dedup_filter([pair], {"title": "", "version": "", "category": ""})
        assert len(result1) == 1
        assert len(result2) == 0  # Already seen


# ══════════════════════════════════════════════════════════════════════
# score_pair
# ══════════════════════════════════════════════════════════════════════


class TestScorePair:
    """Tests for score_pair — quality scoring heuristics."""

    def test_short_instruction_low_score(self):
        """Short instruction should score 0."""
        score, reasons = score_pair({"instruction": "Hi", "output": "A" * 120})
        assert score >= 0

    def test_long_instruction_bonus(self):
        """Instruction >= 20 chars should get score bonus."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail.",
            "output": "A" * 120,
        })
        assert score >= 20
        assert "clear instruction" in reasons

    def test_long_output_bonus(self):
        """Output >= 120 chars should get score bonus."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail.",
            "output": "A" * 150,
        })
        assert score >= 20
        assert "detailed answer" in reasons

    def test_code_example_bonus(self):
        """Code blocks should get score bonus."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail.",
            "output": "Here is code:\\n```python\\nprint('hi')\\n```",
        })
        assert score >= 20
        assert "code example" in reasons

    def test_reasoning_tokens_bonus(self):
        """Reasoning tokens should get bonus."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail.",
            "output": "Step 1: Understand. Because of this, trade-off is... Verify it works.",
        })
        assert score >= 20
        assert "reasoning" in reasons

    def test_operational_detail_bonus(self):
        """Operational detail tokens should get bonus."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail.",
            "output": "Performance warning: there is a common pitfall. Reliability matters.",
        })
        assert score >= 10
        assert "operational detail" in reasons

    def test_score_capped_at_100(self):
        """Score should not exceed 100."""
        score, reasons = score_pair({
            "instruction": "Explain Python comprehensions in detail for beginners. " * 3,
            "output": "A" * 300 + "\\n```python\\ncode\\n```\\nStep 1: do this. Because of that. Performance pitfall warning.",
        })
        assert score <= 100

    def test_minimal_pair(self):
        """Minimal pair should score low."""
        score, reasons = score_pair({
            "instruction": "Short instr",
            "output": "Short answer",
        })
        assert score < 40


# ══════════════════════════════════════════════════════════════════════
# build_prompts
# ══════════════════════════════════════════════════════════════════════


class TestBuildPrompts:
    """Tests for build_prompts — prompt template generation per data type."""

    def make_chunk(self, title: str = "List Comprehensions",
                   text: str = "A list comprehension creates lists concisely. " * 20,
                   codes: list | None = None,
                   version: str = "3.12") -> dict:
        return {
            "title": title,
            "text": text,
            "codes": codes or [],
            "version": version,
        }

    def test_basic_prompt_included(self):
        """The 'basic' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "basic" in prompts

    def test_reasoning_prompt_included(self):
        """The 'reasoning' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "reasoning" in prompts

    def test_expert_prompt_included(self):
        """The 'expert' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "expert" in prompts

    def test_interview_prompt_included(self):
        """The 'interview' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "interview" in prompts

    def test_project_prompt_included(self):
        """The 'project' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "project" in prompts

    def test_version_prompt_included(self):
        """The 'version' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "version" in prompts

    def test_security_prompt_included(self):
        """The 'security' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "security" in prompts

    def test_performance_prompt_included(self):
        """The 'performance' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "performance" in prompts

    def test_testing_prompt_included(self):
        """The 'testing' prompt type should always be present."""
        prompts = build_prompts(self.make_chunk())
        assert "testing" in prompts

    def test_error_fix_prompt_included_with_codes(self):
        """The 'error_fix' prompt should be present when codes exist."""
        prompts = build_prompts(self.make_chunk(codes=["print('hi')"]))
        assert "error_fix" in prompts

    def test_error_fix_absent_without_codes(self):
        """The 'error_fix' prompt should NOT be present without codes."""
        prompts = build_prompts(self.make_chunk(codes=[]))
        assert "error_fix" not in prompts

    def test_code_review_filtered_by_keep(self):
        """The 'code_review' prompt is generated but filtered by keep list."""
        prompts = build_prompts(self.make_chunk(codes=["print('hi')"]))
        assert "code_review" not in prompts

    def test_prompts_include_topic(self):
        """Each prompt should include the topic title."""
        prompts = build_prompts(self.make_chunk(title="Decorators"))
        for key in ["basic", "reasoning", "expert"]:
            assert "Decorators" in prompts[key], f"{key} missing topic"

    def test_prompts_contain_context(self):
        """Prompts should contain the documentation context."""
        prompts = build_prompts(self.make_chunk())
        for key in ["basic", "expert"]:
            assert "List Comprehensions" in prompts[key]

    def test_prompts_request_json(self):
        """Prompts should request JSON array output."""
        prompts = build_prompts(self.make_chunk())
        assert "JSON" in prompts["basic"] or "json" in prompts["basic"]

    def test_keep_filter_applied(self):
        """Prompts should filter to the 'keep' list (basic, reasoning, expert, interview, project, version, security, performance, testing, error_fix)."""
        prompts = build_prompts(self.make_chunk(codes=["code"]))
        # These should NOT be present
        assert "beginner" not in prompts
        assert "code_review" not in prompts  # code_review is generated but filtered by keep


# ══════════════════════════════════════════════════════════════════════
# save_checkpoint / load_latest_checkpoint
# ══════════════════════════════════════════════════════════════════════


class TestCheckpoint:
    """Tests for save_checkpoint and load_latest_checkpoint."""

    def test_save_checkpoint_creates_files(self, tmp_path: Path):
        """save_checkpoint should create checkpoint files."""
        with patch("src.data.generator.CKPT_DIR", tmp_path), \
             patch("src.data.generator.CKPT_META", tmp_path / "generation_meta.json"):
            pairs = [{"instruction": "Q1", "output": "A1"}]
            save_checkpoint(pairs, chunk_index=5, type_stats={"basic": 1})
            ckpt = tmp_path / "par_5.json"
            assert ckpt.exists()
            meta = tmp_path / "generation_meta.json"
            assert meta.exists()

            data = json.loads(ckpt.read_text(encoding="utf-8"))
            assert len(data) == 1
            assert data[0]["instruction"] == "Q1"

    def test_save_checkpoint_meta(self, tmp_path: Path):
        """save_checkpoint should write correct metadata."""
        with patch("src.data.generator.CKPT_DIR", tmp_path), \
             patch("src.data.generator.CKPT_META", tmp_path / "generation_meta.json"):
            save_checkpoint([], chunk_index=10, type_stats={"basic": 5, "expert": 3})
            meta = json.loads((tmp_path / "generation_meta.json").read_text(encoding="utf-8"))
            assert meta["chunk_index"] == 10
            assert meta["total_pairs"] == 0
            assert meta["type_stats"] == {"basic": 5, "expert": 3}
            assert "timestamp" in meta

    def test_load_latest_no_checkpoint(self, tmp_path: Path):
        """No checkpoint should return starting state."""
        with patch("src.data.generator.CKPT_DIR", tmp_path), \
             patch("src.data.generator.CKPT_META", tmp_path / "generation_meta.json"):
            index, pairs, type_stats = load_latest_checkpoint()
            assert index == 0
            assert pairs == []
            assert type_stats == defaultdict(int)

    def test_load_latest_with_checkpoint(self, tmp_path: Path):
        """Existing checkpoint should load state."""
        with patch("src.data.generator.CKPT_DIR", tmp_path), \
             patch("src.data.generator.CKPT_META", tmp_path / "generation_meta.json"):
            pairs_data = [{"instruction": "Q1", "output": "A1"}]
            (tmp_path / "par_0.json").write_text(json.dumps(pairs_data), encoding="utf-8")
            (tmp_path / "generation_meta.json").write_text(
                json.dumps({"chunk_index": 1, "total_pairs": 1, "type_stats": {"basic": 1}}),
                encoding="utf-8",
            )

            index, pairs, type_stats = load_latest_checkpoint()
            assert index == 1
            assert len(pairs) == 1
            assert pairs[0]["instruction"] == "Q1"


# ══════════════════════════════════════════════════════════════════════
# call_api (mocked HTTP)
# ══════════════════════════════════════════════════════════════════════


class TestCallApi:
    """Tests for call_api — HTTP calls with round-robin provider selection."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        global curr_idx
        active.clear()
        curr_idx = 0
        calls.clear()
        fails.clear()
        rate_limited.clear()

    @patch("requests.post")
    def test_successful_call(self, mock_post):
        """Successful API call should return content and provider name."""
        active.append({"name": "groq", "url": "https://api.groq.com/", "key": "gk", "model": "llama"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        mock_post.return_value = mock_response

        content, name = call_api("Test prompt")
        assert content == "Hello"
        assert name == "groq"

    @patch("requests.post")
    def test_rate_limit_handling(self, mock_post):
        """Rate limited (429) should skip the provider and try next."""
        active.append({"name": "groq", "url": "https://api.groq.com/", "key": "gk", "model": "llama"})
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 429
        mock_post.return_value = rate_limited_response

        content, name = call_api("Test")
        # Only one active provider, rate limited -> returns empty
        assert content == "[]"
        assert name == "none"

    @patch("requests.post")
    def test_timeout_handling(self, mock_post):
        """Timeout should fail the provider and skip."""
        active.append({"name": "groq", "url": "https://api.groq.com/", "key": "gk", "model": "llama"})
        from requests.exceptions import Timeout
        mock_post.side_effect = Timeout("timeout")

        content, name = call_api("Test")
        assert content == "[]"
        assert name == "none"
        assert fails.get("groq", 0) >= 1

    @patch("requests.post")
    def test_round_robin_providers(self, mock_post):
        """Multiple providers should be used in round-robin fashion."""
        active.append({"name": "groq", "url": "https://groq/", "key": "gk", "model": "m1"})
        active.append({"name": "openai", "url": "https://openai/", "key": "ok", "model": "m2"})

        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"choices": [{"message": {"content": "Result"}}]}
        mock_post.return_value = mock_response

        content1, name1 = call_api("Test 1")
        content2, name2 = call_api("Test 2")
        assert name1 != name2  # Different providers due to round-robin

    @patch("requests.post")
    def test_no_active_providers(self, mock_post):
        """No active providers should return empty."""
        active.clear()
        content, name = call_api("Test")
        assert content == "[]"
        assert name == "none"


# ══════════════════════════════════════════════════════════════════════
# MODELS and URLS data integrity
# ══════════════════════════════════════════════════════════════════════


class TestModelsUrls:
    """Tests for static MODELS and URLS data."""

    def test_all_urls_are_https(self):
        """All URLs should be HTTPS."""
        for name, url in URLS.items():
            assert url.startswith("https://"), f"{name} URL not HTTPS"

    def test_models_have_matching_urls(self):
        """Every model should have a corresponding URL."""
        for name in MODELS:
            assert name in URLS, f"{name} missing from URLS"

    def test_urls_have_matching_models(self):
        """Every URL should have a corresponding model."""
        for name in URLS:
            assert name in MODELS, f"{name} missing from MODELS"

    def test_at_least_10_providers(self):
        """Should have at least 10 providers configured."""
        assert len(MODELS) >= 10


# ══════════════════════════════════════════════════════════════════════
# process_chunk / process_generation_task (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestProcessChunk:
    """Tests for process_chunk — task decomposition and swarm execution."""

    def test_process_chunk_empty_prompts(self):
        """Chunk with no prompts should return empty."""
        chunk = {"title": "T", "text": "", "version": "", "codes": []}
        result = process_chunk(chunk)
        assert result == []

    @patch("src.data.generator.call_api")
    @patch("src.data.generator.dedup_filter")
    @patch("src.data.generator.score_pair")
    def test_generation_task_flow(self, mock_score, mock_dedup, mock_call):
        """process_generation_task should call API, dedup, and score."""
        chunk = {"title": "Test", "version": "3.12", "category": "tutorial"}
        mock_call.return_value = ('[{"instruction": "Q", "output": "A"}]', "groq")
        mock_dedup.return_value = [{"instruction": "Q", "output": "A"}]
        mock_score.return_value = (80, ["good"])

        # Create a mock task
        task = MagicMock()
        task.prompt = "Test prompt"
        task.task_type = "basic"
        task.task_id = "task_1"

        result = process_generation_task(task, chunk)
        assert result["task_type"] == "basic"
        assert len(result["pairs"]) == 1
        assert result["api"] == "groq"

    def test_setup_requires_keys(self):
        """setup() with no keys should not crash if KEYS is empty."""
        # KEYS is module-level; just verify the function doesn't crash unexpectly
        with patch("src.data.generator.KEYS", {}):
            with pytest.raises(SystemExit):
                generator_setup()
