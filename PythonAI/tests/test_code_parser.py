import pytest
from src.utils.code_parser import (
    CodeBlock,
    extract_code_blocks,
    parse_python_ast,
    extract_and_analyze,
)


def test_extract_code_blocks_fenced():
    text = "Here is some code:\n```python\nprint('hello')\n```\nAnd more:\n```javascript\nconsole.log(1);\n```"
    blocks = extract_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].language == "python"
    assert blocks[0].code == "print('hello')"
    assert not blocks[0].is_inline
    assert blocks[0].line_count == 1

    assert blocks[1].language == "javascript"
    assert blocks[1].code == "console.log(1);"


def test_extract_code_blocks_inline():
    text = "Use the `print()` function."
    blocks = extract_code_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].language == ""
    assert blocks[0].code == "print()"
    assert blocks[0].is_inline


def test_extract_code_blocks_mixed():
    text = "Use `print()`:\n```python\nprint(1)\n```"
    blocks = extract_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].is_inline
    assert blocks[0].code == "print()"
    assert not blocks[1].is_inline
    assert blocks[1].code == "print(1)"


def test_parse_python_ast_valid():
    code = """
import os
from pathlib import Path

def my_func():
    pass

class MyClass:
    def method(self):
        pass
"""
    result = parse_python_ast(code)
    assert result["is_valid"]
    assert "os" in result["imports"]
    assert "pathlib.Path" in result["imports"]
    assert "my_func" in result["functions"]
    assert "MyClass" in result["classes"]
    assert result["error"] is None


def test_parse_python_ast_invalid():
    code = "def my_func(:"
    result = parse_python_ast(code)
    assert not result["is_valid"]
    assert result["error"] is not None


def test_extract_and_analyze():
    text = "Python:\n```python\nimport sys\ndef test(): pass\n```\nInvalid:\n```python\ndef (\n```"
    result = extract_and_analyze(text)
    
    assert result["total_blocks"] == 2
    assert result["fenced_blocks"] == 2
    assert result["inline_blocks"] == 0
    
    b1 = result["blocks"][0]
    assert b1["language"] == "python"
    assert "ast" in b1
    assert "sys" in b1["ast"]["imports"]
    
    b2 = result["blocks"][1]
    assert b2["language"] == "python"  # Language declared
    assert "ast" in b2
    assert not b2["ast"]["is_valid"]
