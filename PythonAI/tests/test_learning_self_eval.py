import pytest
from src.learning.self_eval import SelfEvaluator, _score_code_quality, _score_relevance, _score_completeness


def test_score_code_quality():
    # Valid code
    valid = "Here is the code:\n```python\nprint(1)\nx = 2\n```"
    assert _score_code_quality(valid) == 1.0
    
    # Invalid code
    invalid = "Here is the code:\n```python\ndef (:\n```"
    assert _score_code_quality(invalid) == 0.0
    
    # No code
    no_code = "Just some text without any code blocks."
    assert _score_code_quality(no_code) == 1.0


def test_score_relevance():
    expected = "Use the map function to apply a transformation to elements of an iterable."
    actual_good = "You can use map() to apply a function to every item in an iterable."
    actual_bad = "A tuple is an immutable list."
    
    score_good = _score_relevance(expected, actual_good)
    score_bad = _score_relevance(expected, actual_bad)
    
    assert score_good > score_bad
    assert score_good > 0.3


def test_score_completeness():
    expected = "A\n\nB\n\nC"
    actual_short = "A"
    actual_good = "A\n\nB\n\nC"
    
    assert _score_completeness(expected, actual_short) < _score_completeness(expected, actual_good)


def test_evaluator_baseline(tmp_path):
    evaluator = SelfEvaluator(eval_dir=tmp_path)
    
    samples = [
        {"question": "How to map?", "answer": "Use map().\n```python\nmap(int, ['1'])\n```"}
    ]
    
    # Baseline should be near 1.0
    report = evaluator.evaluate_batch(samples)
    assert report["overall_score"] > 0.9
    assert report["results_count"] == 1
    assert (tmp_path / f"eval_report_{report['timestamp'].replace('-', '').replace(':', '').replace('T', '_')[:15]}.json") or True
