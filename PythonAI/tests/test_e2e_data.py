"""End-to-end tests for the Data Pipeline stage.

Covers prompt building, chunk validation, quality stats, dedup/merge.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout


def test_data_build_prompts() -> None:
    """build_prompts should generate all expected prompt types."""
    from src.data.generator import build_prompts

    chunk = {
        "title": "Python Lists",
        "text": "Lists are mutable sequences. They support indexing, slicing, and methods.",
        "codes": ["my_list = [1, 2, 3]"],
        "version": "3.12",
    }
    prompts = build_prompts(chunk)
    assert "basic" in prompts, "missing basic prompt"
    assert "reasoning" in prompts, "missing reasoning prompt"
    assert "expert" in prompts, "missing expert prompt"
    assert "security" in prompts, "missing security prompt"
    assert "performance" in prompts, "missing performance prompt"
    assert "error_fix" in prompts, "missing error_fix prompt (has code)"
    for key, prompt in prompts.items():
        assert "Python" in prompt, f"prompt {key} missing 'Python'"


def test_data_valid_chunk() -> None:
    """valid_chunk should accept good chunks and reject bad ones."""
    from src.data.augmenter import valid_chunk

    good = {
        "title": "List Comprehensions",
        "text": "A" * 300,
        "type": "howto",
    }
    assert valid_chunk(good), "good chunk rejected"

    bad_type = {**good, "type": "font"}
    assert not valid_chunk(bad_type), "bad type accepted"

    short = {**good, "text": "short"}
    assert not valid_chunk(short), "short text accepted"


def test_data_row_hash_and_merge() -> None:
    """row_hash dedup and merge should work correctly."""
    from src.data.merger import merge, row_hash

    rows_a = [
        {"instruction": "What is a list?", "output": "A sequence."},
        {"instruction": "What is a dict?", "output": "A mapping."},
    ]
    rows_b = [
        {"instruction": "What is a list?", "output": "A sequence."},
        {"instruction": "What is a set?", "output": "Unordered unique."},
    ]

    # Check row_hash consistency
    assert row_hash(rows_a[0]) == row_hash(rows_b[0]), "hash mismatch for same content"

    merged = merge(rows_a, rows_b, min_output_chars=5, keep_old=True)
    assert len(merged) == 3, f"expected 3 merged rows, got {len(merged)}"
    texts = [r["instruction"] for r in merged]
    assert "What is a list?" in texts
    assert "What is a dict?" in texts
    assert "What is a set?" in texts


def test_data_quality_stats_does_not_crash() -> None:
    """print_quality_stats should run without crashing."""
    from src.data.augmenter import print_quality_stats

    sample_rows = [
        {"instruction": "Explain decorators.", "output": "```python\n@decorator\ndef f(): pass\n```"},
        {"instruction": "What is a generator?", "output": "A lazy iterator."},
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_quality_stats(sample_rows)
    output = buf.getvalue()
    assert "Total rows" in output
    assert "With code examples" in output
