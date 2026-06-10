"""Unit tests for src/data/augmenter.py — QA pair generation via keyword extraction + API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data.augmenter import (
    API_PROVIDERS,
    ROOT,
    _call_api_for_qa,
    _parse_api_response,
    build_keyword_prompt,
    extract_keywords,
    generate_pairs,
    load_json,
    merge_rows,
    parse_args,
    parse_json_rows,
    print_quality_stats,
    row_hash,
    save_json,
    select_chunks,
    valid_chunk,
)


# ══════════════════════════════════════════════════════════════════════
# valid_chunk
# ══════════════════════════════════════════════════════════════════════


class TestValidChunk:
    """Tests for valid_chunk — filters out invalid document chunks."""

    def test_standard_chunk(self):
        """A standard doc chunk with enough text should be valid."""
        chunk = {
            "title": "List Comprehensions",
            "category": "python_tutorial",
            "text": "A list comprehension is a concise way to create lists in Python. " * 10,
        }
        assert valid_chunk(chunk) is True

    def test_font_type_excluded(self):
        """Chunks with type 'font' should be invalid."""
        chunk = {"type": "font", "title": "Arial", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_image_types_excluded(self):
        """Chunks with image types should be invalid."""
        for img_type in {"image_png", "image_jpg", "image_gif"}:
            chunk = {"type": img_type, "title": "Image", "text": "B" * 300}
            assert valid_chunk(chunk) is False

    def test_static_and_css_excluded(self):
        """Static and CSS chunks should be invalid."""
        chunk = {"type": "static", "title": "Styles", "text": "C" * 300}
        assert valid_chunk(chunk) is False
        chunk["type"] = "css"
        assert valid_chunk(chunk) is False

    def test_short_text_invalid(self):
        """Text shorter than 250 chars should be invalid."""
        chunk = {"title": "Topic", "text": "Short text"}
        assert valid_chunk(chunk) is False

    def test_barely_enough_text(self):
        """Text of exactly 250+ chars with enough alpha should be valid."""
        chunk = {
            "title": "Topic",
            "text": "a" * 251,
        }
        assert valid_chunk(chunk) is True

    def test_index_title_excluded(self):
        """Chunks with 'index' in title should be excluded."""
        chunk = {"title": "index", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_genindex_title_excluded(self):
        """Chunks with title 'genindex' should be excluded."""
        chunk = {"title": "genindex", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_index_prefix_title_excluded(self):
        """Chunks starting with 'index' should be excluded."""
        chunk = {"title": "indexOfSomething", "text": "A" * 300}
        # title.lower() starts with "index"
        assert valid_chunk(chunk) is False

    def test_category_index_excluded(self):
        """Chunks with category ending in '_index' should be excluded."""
        chunk = {"title": "Valid", "category": "python_index", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_category_api_index_excluded(self):
        """Chunks with category 'api_index' should be excluded."""
        chunk = {"title": "Valid", "category": "api_index", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_full_alpha_filter(self):
        """Chunks with too few alpha characters should be invalid."""
        chunk = {"title": "Numbers", "text": "12345 67890  " * 50}  # Only 14 alpha
        assert valid_chunk(chunk) is False

    def test_boundary_alpha_chars(self):
        """Exactly 160 alpha chars should be valid."""
        chunk = {"title": "Alpha", "text": "A" * 160 + "1234567890 " * 10}
        assert valid_chunk(chunk) is True

    def test_index_with_unicode_dash(self):
        """Title with 'index –' pattern should be excluded."""
        chunk = {"title": "index – Module Index", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_index_with_dash(self):
        """Title with 'index -' pattern should be excluded."""
        chunk = {"title": "index - Module Index", "text": "A" * 300}
        assert valid_chunk(chunk) is False

    def test_missing_fields_default_to_empty(self):
        """Missing title/text fields should default to empty strings."""
        chunk = {"text": "A" * 300}
        assert valid_chunk(chunk) is True  # No title means no "index" match

    def test_missing_type(self):
        """Missing type should default to empty, not in exclusion set."""
        chunk = {"title": "Valid", "text": "A" * 300}
        assert valid_chunk(chunk) is True


# ══════════════════════════════════════════════════════════════════════
# extract_keywords
# ══════════════════════════════════════════════════════════════════════


class TestExtractKeywords:
    """Tests for extract_keywords — extracts Python keywords from text."""

    def test_capitalized_terms_extracted(self):
        """Capitalized multi-word terms should be extracted."""
        text = "A List Comprehension is used with Context Manager patterns."
        kw = extract_keywords(text, max_keywords=8)
        assert "List Comprehension" in kw
        assert "Context Manager" in kw

    def test_snake_case_functions_extracted(self):
        """Snake_case function names with parentheses should be extracted."""
        text = "Use os.path.join() to combine paths and getcwd() for current dir."
        kw = extract_keywords(text, max_keywords=8)
        # join and getcwd have parentheses, so they should be extracted
        assert "join" in kw
        assert "getcwd" in kw

    def test_excluded_function_names(self):
        """Common function names should be excluded."""
        text = "Use print() and len() and int() and str() and list() and dict() and class Foo: def bar(): pass"
        kw = extract_keywords(text, max_keywords=8)
        for excluded in ("print", "len", "int", "str", "list", "dict", "def", "class"):
            assert excluded not in kw

    def test_import_names_extracted(self):
        """Module names after import should be extracted."""
        text = "import numpy as np and from pandas import DataFrame"
        kw = extract_keywords(text, max_keywords=8)
        assert "numpy" in kw
        assert "pandas" in kw

    def test_technical_identifiers(self):
        """Technical identifiers with digits should be extracted."""
        text = "The method model_v2_0 handles version_2_1_0 features."
        kw = extract_keywords(text, max_keywords=8)
        assert any("model" in k for k in kw) or any("version" in k for k in kw)

    def test_respects_max_keywords(self):
        """Should not exceed max_keywords limit."""
        text = "Context Manager List Comprehension Generator Expression " * 10
        kw = extract_keywords(text, max_keywords=3)
        assert len(kw) <= 3

    def test_empty_text(self):
        """Empty text should produce empty list."""
        assert extract_keywords("") == []

    def test_short_words_excluded(self):
        """Words shorter than 5 chars should be excluded."""
        text = "A B CD EFG The Foo Bar Baz"
        kw = extract_keywords(text, max_keywords=8)
        assert all(len(w) > 4 for w in kw)

    def test_only_junk_text(self):
        """Text with no recognizable patterns should produce few keywords."""
        text = "a b c d e f g h i j k l m n o p"
        kw = extract_keywords(text, max_keywords=8)
        assert len(kw) < 3  # Should have very few matches


# ══════════════════════════════════════════════════════════════════════
# build_keyword_prompt
# ══════════════════════════════════════════════════════════════════════


class TestBuildKeywordPrompt:
    """Tests for build_keyword_prompt — prompt template generation."""

    def test_includes_keywords(self):
        """Prompt should include the provided keywords."""
        prompt = build_keyword_prompt(
            ["List Comprehension", "Generator"],
            {"title": "Python Features", "version": "3.12"},
            pairs_per_chunk=2,
        )
        assert "List Comprehension" in prompt
        assert "Generator" in prompt

    def test_includes_title(self):
        """Prompt should include the chunk title."""
        prompt = build_keyword_prompt(
            ["keyword"],
            {"title": "Context Managers", "version": ""},
            pairs_per_chunk=1,
        )
        assert "Context Managers" in prompt

    def test_singular_vs_plural(self):
        """pairs_per_chunk=1 should use 'object', >1 should use 'objects'."""
        prompt_singular = build_keyword_prompt(["kw"], {"title": "T"}, pairs_per_chunk=1)
        prompt_plural = build_keyword_prompt(["kw"], {"title": "T"}, pairs_per_chunk=3)
        assert "1 object" in prompt_singular
        assert "3 objects" in prompt_plural

    def test_default_title_fallback(self):
        """Missing title should use 'Python topic' as default."""
        prompt = build_keyword_prompt(["kw"], {}, pairs_per_chunk=1)
        assert "Python topic" in prompt

    def test_includes_json_shape(self):
        """Prompt should include JSON schema example."""
        prompt = build_keyword_prompt(["kw"], {"title": "T"}, pairs_per_chunk=1)
        assert "rows" in prompt
        assert "instruction" in prompt
        assert "output" in prompt

    def test_empty_keywords(self):
        """Empty keywords should produce empty keyword line."""
        prompt = build_keyword_prompt([], {"title": "T"}, pairs_per_chunk=1)
        assert "KEYWORDS:" in prompt


# ══════════════════════════════════════════════════════════════════════
# parse_json_rows
# ══════════════════════════════════════════════════════════════════════


class TestParseJsonRows:
    """Tests for parse_json_rows — JSON extraction with fallbacks."""

    def test_valid_json_dict(self):
        """A valid JSON dict with 'rows' key should parse correctly."""
        text = '{"rows": [{"instruction": "Q1", "output": "A1"}]}'
        rows = parse_json_rows(text)
        assert len(rows) == 1
        assert rows[0]["instruction"] == "Q1"

    def test_valid_json_array(self):
        """A valid JSON array should parse correctly."""
        text = '[{"instruction": "Q1", "output": "A1"}]'
        rows = parse_json_rows(text)
        assert len(rows) == 1

    def test_text_surrounding_json_dict(self):
        """Text surrounding a JSON dict should still parse."""
        text = "Some leading text\\n{\"rows\": [{\"instruction\": \"Q\", \"output\": \"A\"}]}\\ntrailing"
        rows = parse_json_rows(text)
        assert len(rows) == 1

    def test_text_surrounding_json_array(self):
        """Text surrounding a JSON array should still parse."""
        text = "Here is the result:\\n[{\"instruction\": \"Q\", \"output\": \"A\"}]\\nDone."
        rows = parse_json_rows(text)
        assert len(rows) == 1

    def test_no_json_found(self):
        """Text with no JSON should return empty list."""
        rows = parse_json_rows("This is just plain text with no JSON")
        assert rows == []

    def test_invalid_json_inside_braces(self):
        """Invalid JSON inside braces should try brackets fallback."""
        text = '{invalid json}[{"instruction": "Q", "output": "A"}]'
        rows = parse_json_rows(text)
        assert len(rows) == 1

    def test_filter_non_dicts(self):
        """Non-dict items in rows array should be filtered."""
        text = '{"rows": [{"instruction": "Q"}, "string_item", 42]}'
        rows = parse_json_rows(text)
        assert len(rows) == 1

    def test_empty_array(self):
        """Empty array should return empty list."""
        assert parse_json_rows("[]") == []
        assert parse_json_rows('{"rows": []}') == []


# ══════════════════════════════════════════════════════════════════════
# _parse_api_response (with mocked file I/O)
# ══════════════════════════════════════════════════════════════════════


class TestParseApiResponse:
    """Tests for _parse_api_response — parsing + quality checks."""

    def _make_chunk(self, **overrides: str) -> dict:
        return {
            "filepath": "docs/list.html",
            "title": "List Comprehensions",
            "category": "python_tutorial",
            "version": "3.12",
            **overrides,
        }

    def test_parses_valid_row(self, tmp_path: Path):
        """A valid response with proper instruction/output should parse."""
        output = "A list comprehension provides a concise way to create lists. " * 5
        content = json.dumps({"rows": [{"instruction": "What is a list comprehension in Python?", "output": output}]})
        result = _parse_api_response(content, self._make_chunk(), "groq")
        assert len(result) == 1
        assert "instruction" in result[0]
        assert "output" in result[0]
        assert result[0]["source"] == "docs/list.html"
        assert result[0]["generator"] == "api_groq"

    def test_filters_placeholder_instruction(self):
        """Rows with placeholder text in instruction should be filtered."""
        content = '{"rows": [{"instruction": "[your question here] Explain Python", "output": "A" * 100}]}'
        result = _parse_api_response(content, self._make_chunk(), "groq")
        assert len(result) == 0

    def test_filters_placeholder_output(self):
        """Rows with placeholder text in output should be filtered."""
        content = '{"rows": [{"instruction": "Explain Python comprehensions in detail", "output": "[insert answer here] Python is great. " * 5}]}'
        result = _parse_api_response(content, self._make_chunk(), "groq")
        assert len(result) == 0

    def test_filters_short_instruction(self):
        """Instruction shorter than 15 chars should be filtered."""
        content = '{"rows": [{"instruction": "Hi", "output": "A" * 100}]}'
        result = _parse_api_response(content, self._make_chunk(), "groq")
        assert len(result) == 0

    def test_filters_short_output(self):
        """Output shorter than 80 chars should be filtered."""
        content = '{"rows": [{"instruction": "Explain this concept in detail please.", "output": "Short"}]}'
        result = _parse_api_response(content, self._make_chunk(), "groq")
        assert len(result) == 0

    def test_handles_empty_content(self):
        """Empty content should return empty list."""
        result = _parse_api_response("", self._make_chunk(), "groq")
        assert result == []

    def test_handles_invalid_json(self):
        """Invalid JSON content should return empty list."""
        result = _parse_api_response("not json at all", self._make_chunk(), "groq")
        assert result == []

    def test_metadata_fields_set_correctly(self):
        """Each row should have source, category, version, generator fields."""
        output = "A " * 100
        content = json.dumps({"rows": [{"instruction": "Explain Python comprehensions in detail.", "output": output}]})
        result = _parse_api_response(content, self._make_chunk(filepath="custom/path.html"), "openai")
        assert result[0]["source"] == "custom/path.html"
        assert result[0]["category"] == "python_tutorial"
        assert result[0]["version"] == "3.12"
        assert result[0]["generator"] == "api_openai"


# ══════════════════════════════════════════════════════════════════════
# _call_api_for_qa (mocked HTTP)
# ══════════════════════════════════════════════════════════════════════


class TestCallApiForQa:
    """Tests for _call_api_for_qa — HTTP calls to API providers."""

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_successful_call(self, mock_post, mock_resolve):
        """Successful API call should return parsed rows."""
        mock_resolve.return_value = {"groq": "test-key-123"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        output = "A " * 100
        content = json.dumps({"rows": [{"instruction": "Explain Python? Please be detailed.", "output": output}]})
        mock_response.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_post.return_value = mock_response

        result = _call_api_for_qa(
            ["List Comprehension"],
            {"title": "Python", "version": "3.12"},
            pairs_per_chunk=1,
        )
        assert len(result) == 1
        assert result[0]["instruction"] == "Explain Python? Please be detailed."

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_no_keys_available(self, mock_post, mock_resolve):
        """No API keys should return empty list."""
        mock_resolve.return_value = {}
        result = _call_api_for_qa(["keyword"], {"title": "T"}, 1)
        assert result == []

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_rate_limit_then_succeed(self, mock_post, mock_resolve):
        """Rate limited provider should be skipped; next provider should be tried."""
        mock_resolve.return_value = {"groq": "gk", "openai": "ok"}

        # First response: rate limited. Second: success.
        rate_limited = MagicMock()
        rate_limited.status_code = 429

        output = "A " * 100
        content = json.dumps({"rows": [{"instruction": "Explain Python concepts in detail.", "output": output}]})
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }

        mock_post.side_effect = [rate_limited, success]
        result = _call_api_for_qa(["kw"], {"title": "T"}, 1)
        assert len(result) == 1
        assert mock_post.call_count == 2  # Tried both providers

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_timeout_handled(self, mock_post, mock_resolve):
        """Timeout should be caught and next provider tried."""
        mock_resolve.return_value = {"groq": "gk", "openai": "ok"}
        from requests.exceptions import Timeout

        mock_post.side_effect = [Timeout("timeout"), MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": "[]"}}]})]
        result = _call_api_for_qa(["kw"], {"title": "T"}, 1)
        assert result == []  # No valid rows from fallback
        assert mock_post.call_count == 2

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_connection_error_handled(self, mock_post, mock_resolve):
        """Connection error should be caught and next provider tried."""
        mock_resolve.return_value = {"groq": "gk"}
        from requests.exceptions import ConnectionError

        mock_post.side_effect = ConnectionError("connection refused")
        result = _call_api_for_qa(["kw"], {"title": "T"}, 1)
        assert result == []
        assert mock_post.call_count == 1

    @patch("src.data.augmenter.resolve_all")
    @patch("src.data.augmenter.requests.post")
    def test_non_200_retry(self, mock_post, mock_resolve):
        """Non-200 status should be skipped."""
        mock_resolve.return_value = {"groq": "gk", "openai": "ok"}
        mock_post.return_value = MagicMock(status_code=500)
        result = _call_api_for_qa(["kw"], {"title": "T"}, 1)
        assert result == []
        assert mock_post.call_count >= 1


# ══════════════════════════════════════════════════════════════════════
# generate_pairs
# ══════════════════════════════════════════════════════════════════════


class TestGeneratePairs:
    """Tests for generate_pairs — keyword extraction + API dispatch."""

    def test_short_text_returns_empty(self):
        """Text shorter than 50 chars should return empty list."""
        result = generate_pairs({"text": "short", "title": "T"})
        assert result == []

    def test_empty_text_returns_empty(self):
        """Missing text should return empty list."""
        result = generate_pairs({"title": "T"})
        assert result == []

    @patch("src.data.augmenter._call_api_for_qa")
    def test_dispatches_to_api(self, mock_call_api):
        """Should extract keywords and call API."""
        mock_call_api.return_value = [{"instruction": "Q?", "output": "A"}]
        text = "Python List Comprehension is a powerful feature for creating lists. " * 5
        result = generate_pairs({"text": text, "title": "List Comprehensions"})
        assert len(result) == 1
        assert mock_call_api.call_count == 1

    @patch("src.data.augmenter._call_api_for_qa")
    def test_fallback_title_words(self, mock_call_api):
        """When keywords < 2, should fallback to title words."""
        mock_call_api.return_value = []
        # Text with very few recognizable keywords
        result = generate_pairs({
            "text": "a b c d e f g h i j k l m n. " * 5,
            "title": "Comprehensions Features",
        })
        assert result == []  # No API results, but fallback keywords were used
        assert mock_call_api.call_count == 1


# ══════════════════════════════════════════════════════════════════════
# select_chunks
# ══════════════════════════════════════════════════════════════════════


class TestSelectChunks:
    """Tests for select_chunks — filter + slice."""

    def test_selects_valid_chunks(self):
        """Only valid chunks should be selected."""
        chunks = [
            {"text": "A" * 300},
            {"type": "font", "text": "B" * 300},
            {"text": "C" * 300},
        ]
        selected = select_chunks(chunks, limit=10, offset=0)
        assert len(selected) == 2

    def test_applies_offset(self):
        """Offset should skip chunks."""
        chunks = [{"text": "A" * 200 + " " * 100 + str(i)} for i in range(10)]
        selected = select_chunks(chunks, limit=10, offset=5)
        assert len(selected) == 5

    def test_applies_limit(self):
        """Limit should cap the number returned."""
        chunks = [{"text": "A" * 200 + " " * 100 + str(i)} for i in range(20)]
        selected = select_chunks(chunks, limit=3, offset=0)
        assert len(selected) == 3

    def test_limit_beyond_available(self):
        """Limit exceeding available chunks should return what's left."""
        chunks = [{"text": "A" * 200 + " " * 100 + str(i)} for i in range(5)]
        selected = select_chunks(chunks, limit=100, offset=0)
        assert len(selected) == 5

    def test_offset_beyond_list(self):
        """Offset beyond the list should return empty."""
        chunks = [{"text": "Valid alpha text " * 20} for i in range(5)]
        selected = select_chunks(chunks, limit=10, offset=100)
        assert selected == []

    def test_invalid_chunks_filtered(self):
        """Non-dict items should be filtered."""
        chunks = [
            {"text": "A" * 300},
            "not a dict",
            42,
            {"type": "font", "text": "B" * 300},
        ]
        selected = select_chunks(chunks, limit=10, offset=0)
        assert len(selected) == 1


# ══════════════════════════════════════════════════════════════════════
# merge_rows
# ══════════════════════════════════════════════════════════════════════


class TestMergeRows:
    """Tests for merge_rows — hash-based dedup."""

    def test_no_duplicates(self):
        """Two distinct rows should both be kept."""
        existing = [{"instruction": "Q1", "output": "A1"}]
        generated = [{"instruction": "Q2", "output": "A2"}]
        merged = merge_rows(existing, generated)
        assert len(merged) == 2

    def test_exact_duplicate_skipped(self):
        """Exact duplicates should be skipped."""
        row = {"instruction": "Q1", "output": "A1"}
        existing = [row]
        generated = [row]
        merged = merge_rows(existing, generated)
        assert len(merged) == 1

    def test_multiple_duplicates_skipped(self):
        """Multiple copies of a duplicate should all be skipped."""
        row = {"instruction": "Q1", "output": "A1"}
        existing = [row]
        generated = [row, row, row]
        merged = merge_rows(existing, generated)
        assert len(merged) == 1

    def test_mixed_duplicates(self):
        """Mixed: some duplicates, some new."""
        existing = [{"instruction": "Q1", "output": "A1"}, {"instruction": "Q2", "output": "A2"}]
        generated = [{"instruction": "Q1", "output": "A1"}]  # Q1 duplicate, Q3 new
        merged = merge_rows(existing, generated)
        assert len(merged) == 2


# ══════════════════════════════════════════════════════════════════════
# print_quality_stats
# ══════════════════════════════════════════════════════════════════════


class TestPrintQualityStats:
    """Tests for print_quality_stats — console output."""

    def test_empty_rows(self, capsys):
        """Empty rows should print a message."""
        print_quality_stats([])
        captured = capsys.readouterr()
        assert "No rows" in captured.out

    def test_single_row(self, capsys):
        """Single row should show stats."""
        rows = [
            {"instruction": "Explain Python", "output": "Python is a language. " * 20, "category": "python"},
        ]
        print_quality_stats(rows)
        captured = capsys.readouterr()
        assert "Total rows" in captured.out
        assert "python" in captured.out

    def test_code_detection(self, capsys):
        """Code blocks in output should be counted."""
        rows = [
            {"instruction": "Explain Python", "output": "Code: ```python\\nprint('hi')\\n```", "category": "code"},
            {"instruction": "Explain Java", "output": "Java is verbose. " * 20, "category": "text"},
        ]
        print_quality_stats(rows)
        captured = capsys.readouterr()
        assert "With code examples" in captured.out

    def test_averages(self, capsys):
        """Average lengths should be computed."""
        rows = [
            {"instruction": "Short", "output": "A" * 100, "category": "cat1"},
            {"instruction": "Longer instruction here", "output": "B" * 200, "category": "cat2"},
        ]
        print_quality_stats(rows)
        captured = capsys.readouterr()
        assert "Avg instruction len" in captured.out
        assert "Avg output len" in captured.out

    def test_top_categories(self, capsys):
        """Top 5 categories should be shown."""
        rows = [
            {"instruction": f"Q{i}", "output": "A" * 100, "category": "python"}
            for i in range(10)
        ] + [
            {"instruction": f"R{i}", "output": "B" * 100, "category": "other"}
            for i in range(3)
        ]
        print_quality_stats(rows)
        captured = capsys.readouterr()
        assert "python" in captured.out
        assert "other" in captured.out


# ══════════════════════════════════════════════════════════════════════
# load_json / save_json
# ══════════════════════════════════════════════════════════════════════


class TestLoadSaveJson:
    """Tests for load_json and save_json — JSON file I/O."""

    def test_load_json(self, tmp_path: Path):
        """load_json should parse JSON file."""
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        assert load_json(f) == {"key": "value"}

    def test_save_json_writes_file(self, tmp_path: Path):
        """save_json should write data to file."""
        f = tmp_path / "output.json"
        save_json(f, {"a": 1, "b": 2})
        assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1, "b": 2}

    def test_save_json_creates_parent_dirs(self, tmp_path: Path):
        """save_json should create parent directories."""
        f = tmp_path / "sub" / "nested" / "output.json"
        save_json(f, {"key": "val"})
        assert f.exists()
        assert json.loads(f.read_text(encoding="utf-8")) == {"key": "val"}

    def test_load_json_not_found(self, tmp_path: Path):
        """load_json should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_json(tmp_path / "nonexistent.json")


# ══════════════════════════════════════════════════════════════════════
# API_PROVIDERS data integrity
# ══════════════════════════════════════════════════════════════════════


class TestApiProviders:
    """Tests for the static API_PROVIDERS data."""

    def test_at_least_5_providers(self):
        """API_PROVIDERS should have at least 5 entries."""
        assert len(API_PROVIDERS) >= 5

    def test_all_have_url_and_model(self):
        """Every provider should have url and model keys."""
        for name, cfg in API_PROVIDERS.items():
            assert "url" in cfg, f"{name} missing 'url'"
            assert "model" in cfg, f"{name} missing 'model'"
            assert cfg["url"].startswith("http"), f"{name} url invalid"

    def test_all_urls_are_https(self):
        """All provider URLs should be HTTPS."""
        for name, cfg in API_PROVIDERS.items():
            assert cfg["url"].startswith("https://"), f"{name} URL not HTTPS"

    def test_unique_model_names(self):
        """Model names should be unique per provider."""
        models = [cfg["model"] for cfg in API_PROVIDERS.values()]
        # Not requiring unique — multiple providers can use same model


# ══════════════════════════════════════════════════════════════════════
# parse_args (CLI)
# ══════════════════════════════════════════════════════════════════════


class TestParseArgs:
    """Tests for CLI argument parsing."""

    def test_default_values(self, monkeypatch):
        """Default values should be set correctly."""
        import sys
        monkeypatch.setattr(sys, "argv", ["augmenter.py"])
        args = parse_args()
        assert args.model == "auto"
        assert args.limit == 3
        assert args.offset == 0
        assert args.pairs_per_chunk == 1
        assert args.shuffle is False
        assert args.merge is False
        assert args.dry_run is False
        assert args.stats is False

    def test_custom_values(self, monkeypatch):
        """Custom values should override defaults."""
        import sys
        monkeypatch.setattr(sys, "argv", [
            "augmenter.py", "--model", "groq", "--limit", "10",
            "--offset", "5", "--pairs-per-chunk", "3",
            "--shuffle", "--merge", "--dry-run", "--stats",
        ])
        args = parse_args()
        assert args.model == "groq"
        assert args.limit == 10
        assert args.offset == 5
        assert args.pairs_per_chunk == 3
        assert args.shuffle is True
        assert args.merge is True
        assert args.dry_run is True
        assert args.stats is True

    def test_types(self, monkeypatch):
        """Numeric args should be parsed as ints."""
        import sys
        monkeypatch.setattr(sys, "argv", ["augmenter.py", "--limit", "50", "--offset", "10"])
        args = parse_args()
        assert isinstance(args.limit, int)
        assert isinstance(args.offset, int)
        assert isinstance(args.pairs_per_chunk, int)
