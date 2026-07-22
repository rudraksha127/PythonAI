"""End-to-end tests for the Training Pipeline stage.

Covers dataset construction, callbacks, BLEU scoring.
"""

from __future__ import annotations


def test_training_examples_from_pairs() -> None:
    """build_examples_from_pairs should create Example objects correctly."""
    from src.training.trainer import Example, build_examples_from_pairs

    pairs = [
        {"instruction": "Explain Python lists", "output": "Lists are mutable ordered sequences."},
        {"instruction": "Explain dicts", "output": "A" * 50},
    ]
    examples = build_examples_from_pairs(pairs, limit=10)
    assert len(examples) == 2, f"expected 2 examples, got {len(examples)}"
    assert all(isinstance(e, Example) for e in examples)
    assert all(len(e.prompt) > 10 for e in examples)
    assert all(len(e.response) > 0 for e in examples)


def test_training_throughput_callback() -> None:
    """ThroughputCallback should compute tokens without crashing."""
    from src.training.trainer import ThroughputCallback

    cb = ThroughputCallback(max_length=512)
    cb.on_log(None, None, None)

    class _FakeTrainingArgs:
        per_device_train_batch_size = 1
        gradient_accumulation_steps = 4

    class _FakeState:
        global_step = 10

    cb.on_log(_FakeTrainingArgs(), _FakeState(), None)
    assert cb.total_tokens > 0 or cb.start_time is not None


def test_training_curves_callback() -> None:
    """TrainingCurvesCallback should collect loss values."""
    from src.training.trainer import TrainingCurvesCallback

    curves_cb = TrainingCurvesCallback(output_dir=".")

    class _FakeLogState:
        global_step = 0

    for step, loss in [(0, 2.5), (1, 1.8), (2, 1.2)]:
        _FakeLogState.global_step = step
        curves_cb.on_log(None, _FakeLogState(), None, logs={"loss": loss})

    assert len(curves_cb.losses) == 3, f"expected 3 losses, got {len(curves_cb.losses)}"
    assert curves_cb.losses == [2.5, 1.8, 1.2]


def test_training_compute_bleu() -> None:
    """compute_bleu should return valid BLEU scores."""
    from src.training.evaluator import compute_bleu

    ref = "Python lists are mutable ordered sequences"
    cand = "Lists are mutable sequences in Python"
    bleu = compute_bleu(ref, cand)
    assert 0.0 < bleu <= 1.0, f"BLEU out of range: {bleu}"

    # Empty candidate
    assert compute_bleu(ref, "") == 0.0, "empty candidate BLEU should be 0"

    # Exact match
    exact_bleu = compute_bleu(ref, ref)
    assert exact_bleu >= 0.5, f"exact match BLEU too low: {exact_bleu}"
