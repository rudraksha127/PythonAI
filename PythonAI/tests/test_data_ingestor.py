"""Unit tests for src/data/ingestor.py — parse_so_data and parse_github_data."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.data.ingestor import (
    GITHUB_DIR,
    SO_DIR,
    parse_github_data,
    parse_so_data,
)

# ══════════════════════════════════════════════════════════════════════
# parse_so_data
# ══════════════════════════════════════════════════════════════════════


class TestParseSOData:
    """Tests for parse_so_data — parses Stack Overflow JSON files."""

    def test_no_so_dir_returns_empty(self):
        """When SO_DIR doesn't exist, should return empty list."""
        with patch("src.data.ingestor.SO_DIR", Path("/nonexistent/path")):
            assert parse_so_data() == []

    def test_parses_question_files(self, tmp_path: Path):
        """Should parse so_top_*.json files as questions."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        q_file = so_dir / "so_top_python.json"
        q_file.write_text(
            json.dumps(
                [
                    {
                        "question_id": 12345,
                        "title": "How to use Python lists?",
                        "body": "<p>I want to use <b>lists</b> in Python.</p>",
                        "tags": ["python", "list"],
                    },
                    {
                        "question_id": 12346,
                        "title": "What is a dict?",
                        "body": "Explain dictionaries in Python.",
                        "tags": ["python", "dictionary"],
                    },
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        assert len(chunks) == 2
        assert chunks[0]["id"] == "so_q_12345"
        assert chunks[0]["title"] == "How to use Python lists?"
        assert "lists" in chunks[0]["text"]
        assert chunks[0]["type"] == "so_question"
        assert chunks[0]["category"] == "qa"
        assert "python" in chunks[0]["tags"]

    def test_strips_html_tags(self, tmp_path: Path):
        """HTML tags should be stripped from question body."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        q_file = so_dir / "so_top_test.json"
        q_file.write_text(
            json.dumps(
                [
                    {
                        "question_id": 1,
                        "title": "Test",
                        "body": "<p>Hello <b>World</b> <a href='x'>link</a></p>",
                    },
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        assert "<p>" not in chunks[0]["text"]
        assert "<b>" not in chunks[0]["text"]
        assert "Hello" in chunks[0]["text"]
        assert "World" in chunks[0]["text"]

    def test_parses_answer_files(self, tmp_path: Path):
        """Should parse so_answers_*.json files as answers."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        a_file = so_dir / "so_answers_python.json"
        a_file.write_text(
            json.dumps(
                [
                    {
                        "answer_id": 999,
                        "question_id": 12345,
                        "body": "You can use the <code>list.append()</code> method.",
                    },
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        assert len(chunks) == 1
        assert chunks[0]["id"] == "so_a_999"
        assert "list.append" in chunks[0]["text"]
        assert chunks[0]["type"] == "so_answer"
        assert chunks[0]["category"] == "qa"

    def test_parses_both_questions_and_answers(self, tmp_path: Path):
        """Should parse both question and answer files."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)

        (so_dir / "so_top_test.json").write_text(
            json.dumps(
                [
                    {"question_id": 1, "title": "Q1", "body": "Body1"},
                ]
            )
        )
        (so_dir / "so_answers_test.json").write_text(
            json.dumps(
                [
                    {"answer_id": 2, "question_id": 1, "body": "Answer1"},
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        assert len(chunks) == 2

    def test_handles_file_read_error(self, tmp_path: Path):
        """Should handle JSON decode errors gracefully."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        bad_file = so_dir / "so_top_bad.json"
        bad_file.write_text("this is not json")

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        # Should not crash, should return empty
        assert isinstance(chunks, list)

    def test_handles_missing_fields(self, tmp_path: Path):
        """Should handle items with missing optional fields."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        q_file = so_dir / "so_top_test.json"
        q_file.write_text(
            json.dumps(
                [
                    {"question_id": 1, "title": "Test", "body": "Body"},
                    {"question_id": 2},  # Missing title and body
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        # Both items should be processed (missing fields just become empty strings)
        assert len(chunks) == 2

    def test_empty_tags(self, tmp_path: Path):
        """Questions without tags should have empty tags list."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        q_file = so_dir / "so_top_test.json"
        q_file.write_text(
            json.dumps(
                [
                    {"question_id": 1, "title": "Test", "body": "Body"},
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        assert "tags" not in chunks[0] or chunks[0].get("tags") == []


# ══════════════════════════════════════════════════════════════════════
# parse_github_data
# ══════════════════════════════════════════════════════════════════════


class TestParseGitHubData:
    """Tests for parse_github_data — parses GitHub repo JSON files."""

    def test_no_github_dir_returns_empty(self):
        """When GITHUB_DIR doesn't exist, should return empty list."""
        with patch("src.data.ingestor.GITHUB_DIR", Path("/nonexistent/path")):
            assert parse_github_data() == []

    def test_parses_repo_files(self, tmp_path: Path):
        """Should parse *.json files as repo data."""
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)
        repo_file = gh_dir / "repos.json"
        repo_file.write_text(
            json.dumps(
                [
                    {
                        "name": "requests",
                        "description": "HTTP library for Python",
                        "topics": ["http", "python", "library"],
                    },
                    {
                        "name": "flask",
                        "description": "Web framework",
                        "topics": ["web", "python"],
                    },
                ]
            )
        )

        with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
            chunks = parse_github_data()

        assert len(chunks) == 2
        assert chunks[0]["id"] == "gh_requests"
        assert chunks[0]["title"] == "requests"
        assert "HTTP library" in chunks[0]["text"]
        assert chunks[0]["type"] == "github_repo"
        assert chunks[0]["category"] == "repository"
        assert chunks[0]["topics"] == ["http", "python", "library"]

    def test_handles_missing_description(self, tmp_path: Path):
        """Should handle repos without a description."""
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)
        repo_file = gh_dir / "repos.json"
        repo_file.write_text(
            json.dumps(
                [
                    {"name": "empty-repo"},
                ]
            )
        )

        with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
            chunks = parse_github_data()

        assert len(chunks) == 1
        assert chunks[0]["title"] == "empty-repo"
        # Text should just be the name
        assert "empty-repo:" in chunks[0]["text"]

    def test_handles_file_read_error(self, tmp_path: Path):
        """Should handle JSON decode errors gracefully."""
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)
        bad_file = gh_dir / "bad.json"
        bad_file.write_text("not json")

        with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
            chunks = parse_github_data()

        assert isinstance(chunks, list)

    def test_empty_topics(self, tmp_path: Path):
        """Repos without topics should have empty topics list."""
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)
        repo_file = gh_dir / "repos.json"
        repo_file.write_text(
            json.dumps(
                [
                    {"name": "tool", "description": "A tool"},
                ]
            )
        )

        with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
            chunks = parse_github_data()

        assert chunks[0].get("topics", []) == []

    def test_multiple_files(self, tmp_path: Path):
        """Should parse multiple JSON files in the directory."""
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)
        (gh_dir / "python_repos.json").write_text(
            json.dumps(
                [
                    {"name": "requests", "description": "HTTP"},
                ]
            )
        )
        (gh_dir / "web_repos.json").write_text(
            json.dumps(
                [
                    {"name": "flask", "description": "Web"},
                ]
            )
        )

        with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
            chunks = parse_github_data()

        assert len(chunks) == 2


# ══════════════════════════════════════════════════════════════════════
# Edge cases for both parsers
# ══════════════════════════════════════════════════════════════════════


class TestIngestorEdgeCases:
    """Edge cases for data ingestor parsers."""

    def test_empty_file(self, tmp_path: Path):
        """Empty JSON array should return empty list."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        (so_dir / "so_top_test.json").write_text("[]")
        (so_dir / "so_answers_test.json").write_text("[]")

        with patch("src.data.ingestor.SO_DIR", so_dir):
            assert parse_so_data() == []

    def test_file_with_only_non_dict_items(self, tmp_path: Path):
        """Files with only non-dict items should not crash."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        (so_dir / "so_top_test.json").write_text('[null, 42, "string"]')

        with patch("src.data.ingestor.SO_DIR", so_dir):
            chunks = parse_so_data()

        # Non-dict items are skipped by .get() calls
        assert isinstance(chunks, list)

    def test_empty_directory_returns_empty(self, tmp_path: Path):
        """Empty directory should return empty list."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)

        with patch("src.data.ingestor.SO_DIR", so_dir):
            with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
                assert parse_so_data() == []
                assert parse_github_data() == []

    def test_combined_parse_output(self, tmp_path: Path):
        """Both parsers should produce compatible chunk formats."""
        so_dir = tmp_path / "stackoverflow"
        so_dir.mkdir(parents=True)
        gh_dir = tmp_path / "github_code"
        gh_dir.mkdir(parents=True)

        (so_dir / "so_top_test.json").write_text(
            json.dumps(
                [
                    {"question_id": 1, "title": "Q", "body": "Body"},
                ]
            )
        )
        (gh_dir / "repos.json").write_text(
            json.dumps(
                [
                    {"name": "repo", "description": "Desc"},
                ]
            )
        )

        with patch("src.data.ingestor.SO_DIR", so_dir):
            with patch("src.data.ingestor.GITHUB_DIR", gh_dir):
                so_chunks = parse_so_data()
                gh_chunks = parse_github_data()

        all_chunks = so_chunks + gh_chunks
        assert len(all_chunks) == 2

        # Both should have id, title, text, type, category
        for chunk in all_chunks:
            assert "id" in chunk
            assert "title" in chunk
            assert "text" in chunk
            assert "type" in chunk
            assert "category" in chunk


# ══════════════════════════════════════════════════════════════════════
# Path constants verification
# ══════════════════════════════════════════════════════════════════════


class TestIngestorPaths:
    """Tests for path constants."""

    def test_so_dir_is_named_stackoverflow(self):
        """SO_DIR should end with 'stackoverflow'."""
        assert SO_DIR.name == "stackoverflow"

    def test_github_dir_is_named_github_code(self):
        """GITHUB_DIR should end with 'github_code'."""
        assert GITHUB_DIR.name == "github_code"
