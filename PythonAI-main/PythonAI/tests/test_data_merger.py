"""Unit tests for src/data/merger.py — merge, dedup, and distribution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.data.merger import (
    load_rows,
    merge,
    output_len,
    parse_args,
    print_distribution,
    row_hash,
    save_rows,
    valid_row,
)

# ══════════════════════════════════════════════════════════════════════
# row_hash
# ══════════════════════════════════════════════════════════════════════


class TestRowHash:
    """Tests for row_hash — deterministic SHA-256 of instruction+output."""

    def test_consistent_hash(self):
        """Same row should produce the same hash."""
        row = {"instruction": "What is Python?", "output": "Python is a language."}
        assert row_hash(row) == row_hash(row)

    def test_different_rows_different_hashes(self):
        """Different rows should produce different hashes."""
        row1 = {"instruction": "What is Python?", "output": "Python is a language."}
        row2 = {"instruction": "What is Java?", "output": "Java is a language."}
        assert row_hash(row1) != row_hash(row2)

    def test_hash_is_sha256(self):
        """Hash should be a 64-character hex SHA-256."""
        row = {"instruction": "Hi", "output": "Hello"}
        h = row_hash(row)
        assert len(h) == 64
        int(h, 16)  # Should not raise

    def test_extra_fields_ignored(self):
        """Extra fields should not affect the hash (only instruction+output)."""
        row1 = {"instruction": "A", "output": "B"}
        row2 = {"instruction": "A", "output": "B", "category": "test", "version": "3.12"}
        assert row_hash(row1) == row_hash(row2)

    def test_whitespace_stripped(self):
        """Trailing whitespace should be stripped before hashing."""
        row1 = {"instruction": "A", "output": "B"}
        row2 = {"instruction": "  A  ", "output": "  B  "}
        assert row_hash(row1) == row_hash(row2)

    def test_missing_keys(self):
        """Missing keys should hash to empty strings."""
        h = row_hash({})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_none_values(self):
        """None values should be treated as empty strings."""
        h = row_hash({"instruction": None, "output": None})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_empty_instruction(self):
        """Empty instruction should still produce a hash."""
        h = row_hash({"instruction": "", "output": "Some output"})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_long_content(self):
        """Long content should still produce a valid hash."""
        row = {"instruction": "A" * 10000, "output": "B" * 10000}
        h = row_hash(row)
        assert len(h) == 64


# ══════════════════════════════════════════════════════════════════════
# output_len
# ══════════════════════════════════════════════════════════════════════


class TestOutputLen:
    """Tests for output_len — returns length of stripped output."""

    def test_normal_output(self):
        """Normal output should return its length."""
        assert output_len({"output": "Hello world"}) == 11

    def test_whitespace_stripped(self):
        """Trailing whitespace should be stripped before counting."""
        assert output_len({"output": "  Hello  "}) == 5

    def test_empty_output(self):
        """Empty output should return 0."""
        assert output_len({"output": ""}) == 0

    def test_missing_output(self):
        """Missing output should return 0."""
        assert output_len({}) == 0

    def test_none_output(self):
        """None output casts to 'None' string, length 4."""
        assert output_len({"output": None}) == 4

    def test_multiline_output(self):
        """Multi-line output should count all characters."""
        text = "Line 1\nLine 2\nLine 3"
        assert output_len({"output": text}) == len(text)


# ══════════════════════════════════════════════════════════════════════
# valid_row
# ══════════════════════════════════════════════════════════════════════


class TestValidRow:
    """Tests for valid_row — checks minimum lengths."""

    def test_valid_row_default(self):
        """Row with instruction >= 10 and output >= 80 should be valid."""
        row = {
            "instruction": "Explain Python recursion comprehensively",
            "output": "Recursion is a programming technique where a function calls itself. " * 5,
        }
        assert valid_row(row, min_output_chars=80) is True

    def test_short_instruction(self):
        """Instruction shorter than 10 should be invalid."""
        row = {"instruction": "Hi", "output": "A" * 100}
        assert valid_row(row, min_output_chars=80) is False

    def test_short_output(self):
        """Output shorter than min_output_chars should be invalid."""
        row = {"instruction": "Explain something", "output": "Short"}
        assert valid_row(row, min_output_chars=80) is False

    def test_custom_min_output(self):
        """Custom min_output_chars should be respected."""
        row = {"instruction": "Explain something", "output": "A" * 50}
        assert valid_row(row, min_output_chars=30) is True
        assert valid_row(row, min_output_chars=100) is False

    def test_missing_keys(self):
        """Missing keys should be treated as empty strings (invalid)."""
        assert valid_row({}, min_output_chars=80) is False

    def test_whitespace_instruction(self):
        """Whitespace-only instruction should be invalid."""
        row = {"instruction": "   ", "output": "A" * 100}
        assert valid_row(row, min_output_chars=80) is False

    def test_exact_minimum(self):
        """Exactly min_output_chars should be valid."""
        row = {"instruction": "Exactly 10 chars", "output": "A" * 80}
        assert valid_row(row, min_output_chars=80) is True

    def test_just_below_minimum(self):
        """Just below min_output_chars should be invalid."""
        row = {"instruction": "Exactly 10 chars", "output": "A" * 79}
        assert valid_row(row, min_output_chars=80) is False


# ══════════════════════════════════════════════════════════════════════
# load_rows / save_rows
# ══════════════════════════════════════════════════════════════════════


class TestLoadSaveRows:
    """Tests for load_rows and save_rows — JSON file I/O."""

    def test_load_rows_simple(self, tmp_path: Path):
        """load_rows should parse a JSON list of dicts."""
        f = tmp_path / "data.json"
        f.write_text('[{"instruction": "A", "output": "B"}]')
        rows = load_rows(f)
        assert len(rows) == 1
        assert rows[0]["instruction"] == "A"

    def test_load_rows_filters_non_dicts(self, tmp_path: Path):
        """load_rows should filter out non-dict items."""
        f = tmp_path / "data.json"
        f.write_text('[{"instruction": "A"}, "string_item", 42, null]')
        rows = load_rows(f)
        assert len(rows) == 1
        assert rows[0]["instruction"] == "A"

    def test_load_rows_empty(self, tmp_path: Path):
        """load_rows should return empty list for empty array."""
        f = tmp_path / "data.json"
        f.write_text("[]")
        assert load_rows(f) == []

    def test_load_rows_not_a_list(self, tmp_path: Path):
        """load_rows should raise ValueError for non-list JSON."""
        f = tmp_path / "data.json"
        f.write_text('{"not": "a list"}')
        with pytest.raises(ValueError, match="must contain a JSON list"):
            load_rows(f)

    def test_save_rows_writes_json(self, tmp_path: Path):
        """save_rows should write a pretty-printed JSON list."""
        f = tmp_path / "output.json"
        rows = [{"instruction": "A", "output": "B"}]
        save_rows(f, rows)
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data == rows

    def test_save_rows_ensure_ascii(self, tmp_path: Path):
        """save_rows should handle Unicode characters."""
        f = tmp_path / "output.json"
        rows = [{"instruction": "कृपया", "output": "हिंदी"}]
        save_rows(f, rows)
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data[0]["instruction"] == "कृपया"

    def test_save_rows_empty(self, tmp_path: Path):
        """save_rows should write empty array."""
        f = tmp_path / "output.json"
        save_rows(f, [])
        assert json.loads(f.read_text(encoding="utf-8")) == []


# ══════════════════════════════════════════════════════════════════════
# merge
# ══════════════════════════════════════════════════════════════════════


class TestMerge:
    """Tests for merge — core dedup and conflict resolution."""

    def test_empty_addition(self):
        """Merging empty addition should return valid base rows only."""
        base = [{"instruction": "Explain Python", "output": "Python is great. " * 20}]
        result = merge(base, [], min_output_chars=80)
        assert len(result) == 1

    def test_empty_base(self):
        """Merging into empty base should return valid addition rows."""
        addition = [{"instruction": "Explain Python", "output": "Python is great. " * 20}]
        result = merge([], addition, min_output_chars=80)
        assert len(result) == 1

    def test_deduplication(self):
        """Duplicate instruction+output should be merged into one."""
        row = {"instruction": "What is Python?", "output": "Python is a language. " * 20}
        base = [row]
        addition = [row]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 1

    def test_unique_rows_combined(self):
        """Two different rows should both appear in merged result."""
        base = [{"instruction": "What is Python?", "output": "Python is great. " * 20}]
        addition = [{"instruction": "What is Java?", "output": "Java is versatile. " * 20}]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 2

    def test_dedup_identical_rows(self):
        """Exactly duplicate rows (same instruction+output) should dedup to one."""
        output_text = "Identical output for testing purposes only. " * 15
        base = [{"instruction": "Explain this concept in detail please.", "output": output_text}]
        addition = [{"instruction": "Explain this concept in detail please.", "output": output_text}]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 1

    def test_dedup_multiple_copies(self):
        """Multiple copies of same row should dedup to one."""
        row = {"instruction": "Explain Python recursion comprehensively.", "output": "A. " * 80}
        base = [row]
        addition = [row, row, row]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 1

    def test_different_rows_both_kept(self):
        """Rows with different instruction+output should both appear."""
        base = [{"instruction": "Explain Python list comprehensions.", "output": "List comprehensions. " * 20}]
        addition = [{"instruction": "Explain Python dictionary operations.", "output": "Dict operations. " * 20}]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 2

    def test_filters_invalid_rows(self):
        """Rows below minimum output length should be filtered out."""
        addition = [{"instruction": "Short instruction.", "output": "Way too short"}]
        result = merge([], addition, min_output_chars=80)
        assert len(result) == 0

    def test_filters_short_instruction(self):
        """Rows with short instructions should be filtered."""
        addition = [{"instruction": "Hi", "output": "A" * 100}]
        result = merge([], addition, min_output_chars=80)
        assert len(result) == 0

    def test_dedup_many_pairs(self):
        """Many rows with exact duplicates should all dedup."""
        output_text = "Same answer text for testing purposes. " * 15
        base = [
            {"instruction": f"Explain Python concept number {i} in detail.", "output": output_text} for i in range(5)
        ]
        addition = [
            {"instruction": f"Explain Python concept number {i} in detail.", "output": output_text} for i in range(5)
        ]
        result = merge(base, addition, min_output_chars=80)
        assert len(result) == 5

    def test_large_dataset(self):
        """merge should handle a moderately large dataset."""
        base = [
            {
                "instruction": f"Explain Python question number {i} in detail.",
                "output": f"Answer to question {i}. " * 20,
            }
            for i in range(100)
        ]
        addition = []
        for i in range(50):
            addition.append(
                {
                    "instruction": f"Explain Python question number {i} in detail.",
                    "output": f"Answer to question {i}. " * 20,
                }
            )
        for i in range(50, 100):
            addition.append(
                {"instruction": f"Explain new question number {i} in detail.", "output": f"New answer {i}. " * 20}
            )
        result = merge(base, addition, min_output_chars=80)
        # 100 base + 50 new unique = 150
        assert len(result) == 150

    def test_different_metadata_same_content(self):
        """Same content with different metadata should dedup, keeping base metadata."""
        output_text = "Same content for testing purposes right here. " * 15
        base = [
            {"instruction": "Explain this Python concept in detail please.", "output": output_text, "category": "old"}
        ]
        addition = [
            {"instruction": "Explain this Python concept in detail please.", "output": output_text, "category": "new"}
        ]
        result = merge(base, addition, min_output_chars=80, keep_old=True)
        assert len(result) == 1
        assert result[0]["category"] == "old"


# ══════════════════════════════════════════════════════════════════════
# print_distribution
# ══════════════════════════════════════════════════════════════════════


class TestPrintDistribution:
    """Tests for print_distribution — output formatting."""

    def test_empty_rows(self, capsys):
        """Empty rows should print a message."""
        print_distribution([], label="Test")
        captured = capsys.readouterr()
        assert "No rows" in captured.out

    def test_single_category(self, capsys):
        """Rows with one category should show 100%."""
        rows = [
            {"instruction": "A", "output": "A" * 100, "category": "python"},
            {"instruction": "B", "output": "B" * 100, "category": "python"},
        ]
        print_distribution(rows)
        captured = capsys.readouterr()
        assert "Total rows: 2" in captured.out
        assert "python: 2" in captured.out

    def test_label_included(self, capsys):
        """Label should be printed if provided."""
        rows = [{"instruction": "A", "output": "A" * 100}]
        print_distribution(rows, label="Custom Label")
        captured = capsys.readouterr()
        assert "Custom Label" in captured.out

    def test_version_and_type_counts(self, capsys):
        """Versions and types should be counted."""
        rows = [
            {"instruction": "A", "output": "A" * 100, "version": "3.12", "type": "tutorial"},
            {"instruction": "B", "output": "B" * 100, "version": "3.12", "type": "tutorial"},
            {"instruction": "C", "output": "C" * 100, "version": "3.11", "type": "howto"},
        ]
        print_distribution(rows)
        captured = capsys.readouterr()
        assert "3.12: 2" in captured.out
        assert "tutorial: 2" in captured.out

    def test_missing_fields(self, capsys):
        """Rows with missing fields should use 'unknown'."""
        rows = [{"instruction": "A", "output": "A" * 100}]
        print_distribution(rows)
        captured = capsys.readouterr()
        assert "unknown" in captured.out

    def test_percentage_formatting(self, capsys):
        """Percentages should be integers."""
        rows = [{"instruction": f"A{i}", "output": "A" * 100, "category": "python"} for i in range(3)]
        rows.append({"instruction": "B", "output": "B" * 100, "category": "other"})
        print_distribution(rows)
        captured = capsys.readouterr()
        assert "python: 3 (75%)" in captured.out or "python: 3" in captured.out
        assert "other: 1 (25%)" in captured.out or "other: 1" in captured.out


# ══════════════════════════════════════════════════════════════════════
# parse_args (CLI)
# ══════════════════════════════════════════════════════════════════════


class TestParseArgs:
    """Tests for CLI argument parsing."""

    def test_default_values(self, monkeypatch):
        """Default values should be set correctly."""
        monkeypatch.setattr(sys, "argv", ["merger.py", "--add", "extra.json"])
        args = parse_args()
        assert args.base == "training_dataset.json"
        assert args.add == "extra.json"
        assert args.output == "training_dataset_augmented.json"
        assert args.min_output_chars == 80
        assert args.keep_old is False
        assert args.stats_only is False

    def test_custom_values(self, monkeypatch):
        """Custom values should override defaults."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "merger.py",
                "--base",
                "custom_base.json",
                "--add",
                "new.json",
                "--output",
                "merged.json",
                "--min-output-chars",
                "50",
                "--keep-old",
                "--stats-only",
            ],
        )
        args = parse_args()
        assert args.base == "custom_base.json"
        assert args.add == "new.json"
        assert args.output == "merged.json"
        assert args.min_output_chars == 50
        assert args.keep_old is True
        assert args.stats_only is True

    def test_keep_old_default(self, monkeypatch):
        """keep_old should default to False."""
        monkeypatch.setattr(sys, "argv", ["merger.py", "--add", "extra.json"])
        args = parse_args()
        assert args.keep_old is False

    def test_min_output_chars_type(self, monkeypatch):
        """min_output_chars should be parsed as int."""
        monkeypatch.setattr(sys, "argv", ["merger.py", "--add", "x.json", "--min-output-chars", "120"])
        args = parse_args()
        assert isinstance(args.min_output_chars, int)
        assert args.min_output_chars == 120


# ══════════════════════════════════════════════════════════════════════
# Integration: merge + load_rows + save_rows
# ══════════════════════════════════════════════════════════════════════


class TestMergeIntegration:
    """End-to-end merge workflow with temp files."""

    def test_full_merge_workflow(self, tmp_path: Path):
        """Full workflow: load -> merge -> save -> verify."""
        base_file = tmp_path / "base.json"
        add_file = tmp_path / "add.json"
        output_file = tmp_path / "output.json"

        base = [
            {"instruction": "What is Python?", "output": "Python is great. " * 20},
            {"instruction": "What is Java?", "output": "Java is versatile. " * 20},
        ]
        addition = [
            {"instruction": "What is Python?", "output": "Python is great. " * 20},
            {"instruction": "What is Rust?", "output": "Rust is fast. " * 20},
        ]

        base_file.write_text(json.dumps(base))
        add_file.write_text(json.dumps(addition))

        base_rows = load_rows(base_file)
        add_rows = load_rows(add_file)
        merged = merge(base_rows, add_rows, min_output_chars=80)
        save_rows(output_file, merged)

        result = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(result) == 3  # 2 base + 1 new
        assert any("Python" in r["output"] for r in result)
        assert any("Rust" in r["output"] for r in result)

    def test_merge_with_all_invalid(self, tmp_path: Path):
        """All rows below minimum should produce empty output."""
        base_file = tmp_path / "base.json"
        output_file = tmp_path / "output.json"

        base = [{"instruction": "Hi", "output": "Short"}]
        base_file.write_text(json.dumps(base))

        base_rows = load_rows(base_file)
        merged = merge(base_rows, [], min_output_chars=80)
        save_rows(output_file, merged)

        assert json.loads(output_file.read_text(encoding="utf-8")) == []

    def test_merge_with_all_valid(self, tmp_path: Path):
        """All valid rows should appear in output."""
        add_file = tmp_path / "add.json"
        output_file = tmp_path / "output.json"

        addition = [{"instruction": f"Question {i}", "output": f"Answer {i}. " * 20} for i in range(10)]
        add_file.write_text(json.dumps(addition))

        add_rows = load_rows(add_file)
        merged = merge([], add_rows, min_output_chars=80)
        save_rows(output_file, merged)

        result = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(result) == 10
