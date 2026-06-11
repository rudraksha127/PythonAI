import json
from pathlib import Path
import pytest
from src.learning.conv_learner import ConversationLearner, learn_from_conversation, _normalize_text, _extract_concepts


def test_normalize_text():
    text = "  Hello \t World \r\n This is a test. \x00"
    normalized = _normalize_text(text)
    assert normalized == "Hello World \n This is a test."


def test_extract_concepts():
    text = "Here we use an async def function with a decorator. I import os.path."
    concepts = _extract_concepts(text)
    assert "async" in concepts
    assert "def" in concepts
    assert "import" in concepts
    assert "decorator" in concepts
    assert "os.path" in concepts


def test_conversation_learner_basic(tmp_path):
    learner = ConversationLearner(output_dir=tmp_path, min_answer_length=10)
    
    qa_pairs = [
        {"question": "How do I print?", "answer": "Use the print() function built into Python."},
    ]
    
    stats = learner.learn(qa_pairs)
    assert stats["learned"] == 1
    assert stats["duplicates_skipped"] == 0
    assert stats["invalid_skipped"] == 0
    
    # Check that a file was created
    files = list(tmp_path.glob("conversations_*.jsonl"))
    assert len(files) == 1
    
    with open(files[0]) as f:
        data = json.loads(f.readline())
        assert data["question"] == "How do I print?"
        assert data["answer"] == "Use the print() function built into Python."


def test_conversation_learner_dedup(tmp_path):
    learner = ConversationLearner(output_dir=tmp_path, min_answer_length=10)
    
    qa_pairs = [
        {"question": "How do I print?", "answer": "Use the print() function."},
    ]
    
    learner.learn(qa_pairs)
    stats2 = learner.learn(qa_pairs)
    
    assert stats2["learned"] == 0
    assert stats2["duplicates_skipped"] == 1


def test_conversation_learner_skip_invalid(tmp_path):
    learner = ConversationLearner(output_dir=tmp_path, min_answer_length=10)
    
    qa_pairs = [
        {"question": "", "answer": "Answer"},  # Missing question
        {"question": "Q", "answer": "Short"},  # Too short
    ]
    
    stats = learner.learn(qa_pairs)
    assert stats["learned"] == 0
    assert stats["invalid_skipped"] == 2
