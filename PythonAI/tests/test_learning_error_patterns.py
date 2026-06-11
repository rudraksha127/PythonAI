from src.learning.error_patterns import ErrorPatternDB, _extract_error_info


def test_extract_error_info():
    traceback = """
Traceback (most recent call last):
  File "src/main.py", line 10, in <module>
    1 / 0
ZeroDivisionError: division by zero
"""
    info = _extract_error_info(traceback)
    assert info["error_type"] == "ZeroDivisionError"
    assert info["error_message"] == "division by zero"
    assert info["error_module"] == "main"


def test_error_pattern_db_basic(tmp_path):
    db_path = tmp_path / "errors.json"
    db = ErrorPatternDB(db_path=db_path)

    # Log new error
    res1 = db.log("TypeError: unsupported operand type(s) for +: 'int' and 'str'", "Convert the int to a str using str()")
    assert res1["is_new"] is True
    assert res1["times_seen"] == 1

    # Log same error again
    res2 = db.log("TypeError: unsupported operand type(s) for +: 'int' and 'str'", "Use str() on the int")
    assert res2["is_new"] is False
    assert res2["times_seen"] == 2
    assert res2["confidence"] > 0.5

    # Find exact
    matches = db.find("TypeError: unsupported operand type(s) for +: 'int' and 'str'")
    assert len(matches) == 1
    assert matches[0]["match_type"] == "exact"


def test_error_pattern_db_fuzzy(tmp_path):
    db_path = tmp_path / "errors.json"
    db = ErrorPatternDB(db_path=db_path)

    db.log("KeyError: 'user_id'", "Check if 'user_id' exists in the dictionary before accessing it.")

    # Find fuzzy
    matches = db.find("KeyError: 'account_id'")
    assert len(matches) == 1
    assert matches[0]["match_type"] == "fuzzy"
    assert matches[0]["error_type"] == "KeyError"
