import pytest
from src.learning.doc_watcher import DocWatcher, _parse_version


def test_parse_version():
    assert _parse_version("3.12.0") == (3, 12, 0)
    assert _parse_version("3.13.0b1") == (3, 13, 0, 1)


def test_doc_watcher_state(tmp_path):
    watcher = DocWatcher(state_dir=tmp_path)
    
    watcher._state["last_known_version"] = "3.12.0"
    watcher._state["known_versions"] = ["3.11.0", "3.12.0"]
    watcher._save_state()
    
    watcher2 = DocWatcher(state_dir=tmp_path)
    assert watcher2._state["last_known_version"] == "3.12.0"
    assert "3.11.0" in watcher2._state["known_versions"]
