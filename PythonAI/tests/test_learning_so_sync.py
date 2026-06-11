import pytest
from src.learning.so_sync import StackOverflowSyncer, _strip_html, _format_answer


def test_strip_html():
    html = "<p>Here is <b>bold</b> text &amp; more.</p>"
    text = _strip_html(html)
    assert text == "Here is bold text & more."


def test_format_answer():
    html = "<p>Use this code:</p><pre><code>print(1)\nprint(2)</code></pre><p>Done.</p>"
    md = _format_answer(html)
    assert "Use this code:" in md
    assert "```python\nprint(1)\nprint(2)\n```" in md
    assert "Done." in md


def test_syncer_dedup(tmp_path):
    syncer = StackOverflowSyncer(output_dir=tmp_path, cache_dir=tmp_path)
    
    # Inject a known hash
    syncer._known_hashes.add("test_hash_123")
    
    # It should correctly load known hashes next time
    syncer._save_known_hashes()
    
    syncer2 = StackOverflowSyncer(output_dir=tmp_path, cache_dir=tmp_path)
    assert "test_hash_123" in syncer2._known_hashes
