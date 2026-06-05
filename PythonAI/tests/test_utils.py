import pytest
from src.utils.cost_tracker import CostTracker
from src.utils.dedup import Deduplicator
import tempfile
import os

def test_cost_tracker():
    with tempfile.TemporaryDirectory() as tmpdirname:
        log_path = os.path.join(tmpdirname, "test_log.json")
        tracker = CostTracker(log_path=log_path)
        
        # Test estimating tokens
        tracker.log_call("openai", "Hello", "World")
        
        assert os.path.exists(log_path)
        with open(log_path, "r") as f:
            data = f.read()
            assert "openai" in data
            assert "cost_usd" in data

def test_deduplicator():
    dedup = Deduplicator(threshold=0.5, num_perm=64)
    
    # Test identical long documents
    doc1 = "The quick brown fox jumps over the lazy dog. " * 10
    doc2 = "The quick brown fox jumps over the lazy dog. " * 10
    
    # First time shouldn't be duplicate
    assert dedup.is_duplicate(doc1, doc_id="1") is False
    
    # Second time should be duplicate
    assert dedup.is_duplicate(doc2, doc_id="2") is True
    
    # Completely different document
    doc3 = "This is a completely different document about quantum physics and relativity theory. " * 10
    assert dedup.is_duplicate(doc3, doc_id="3") is False
