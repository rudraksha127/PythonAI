"""
Comprehensive Tests for src/utils/validation.py
══════════════════════════════════════════════════

Covers every public function and dataclass in the validation module:
- ValidationResult  (dataclass + bool/merge/ok/fail/warn)
- sanitize_text
- validate_question
- validate_code_block
- validate_api_key
- validate_config
- validate_path
- validate_json_string
- validate_training_record
- get_env_bool / get_env_int / get_env_list
- validate_dataset_file
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.utils.validation import (
    DANGEROUS_CODE_PATTERNS,
    ValidationResult,
    get_env_bool,
    get_env_int,
    get_env_list,
    sanitize_text,
    validate_api_key,
    validate_code_block,
    validate_config,
    validate_dataset_file,
    validate_json_string,
    validate_path,
    validate_question,
    validate_training_record,
)

# ═══════════════════════════════════════════════
#  ValidationResult
# ═══════════════════════════════════════════════

class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_defaults(self) -> None:
        r = ValidationResult()
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []
        assert r.sanitized_value is None
        assert bool(r) is True

    def test_valid_false(self) -> None:
        r = ValidationResult(valid=False)
        assert bool(r) is False

    def test_with_errors(self) -> None:
        r = ValidationResult(valid=False, errors=["err1", "err2"])
        assert bool(r) is False
        assert r.errors == ["err1", "err2"]

    def test_with_warnings(self) -> None:
        r = ValidationResult(warnings=["warn1"])
        assert bool(r) is True  # warnings don't make it invalid
        assert r.warnings == ["warn1"]

    def test_with_sanitized_value(self) -> None:
        r = ValidationResult(sanitized_value="cleaned")
        assert r.sanitized_value == "cleaned"

    def test_merge_both_valid(self) -> None:
        a = ValidationResult(valid=True)
        b = ValidationResult(valid=True)
        a.merge(b)
        assert a.valid is True

    def test_merge_one_invalid(self) -> None:
        a = ValidationResult(valid=True)
        b = ValidationResult(valid=False, errors=["b_error"])
        a.merge(b)
        assert a.valid is False
        assert "b_error" in a.errors

    def test_merge_combines_errors_and_warnings(self) -> None:
        a = ValidationResult(errors=["a_err"], warnings=["a_warn"])
        b = ValidationResult(errors=["b_err"], warnings=["b_warn"])
        a.merge(b)
        assert a.errors == ["a_err", "b_err"]
        assert a.warnings == ["a_warn", "b_warn"]

    def test_merge_returns_self(self) -> None:
        a = ValidationResult()
        b = ValidationResult()
        result = a.merge(b)
        assert result is a  # Returns self for chaining

    def test_ok_classmethod(self) -> None:
        r = ValidationResult.ok()
        assert r.valid is True
        assert r.errors == []

    def test_ok_with_value(self) -> None:
        r = ValidationResult.ok(42)
        assert r.sanitized_value == 42

    def test_fail_classmethod(self) -> None:
        r = ValidationResult.fail("something went wrong")
        assert r.valid is False
        assert r.errors == ["something went wrong"]

    def test_fail_with_value(self) -> None:
        r = ValidationResult.fail("err", "raw_input")
        assert r.sanitized_value == "raw_input"

    def test_warn_classmethod(self) -> None:
        r = ValidationResult.warn("just a warning")
        assert r.valid is True
        assert r.warnings == ["just a warning"]

    def test_warn_with_value(self) -> None:
        r = ValidationResult.warn("warn", "value")
        assert r.sanitized_value == "value"


# ═══════════════════════════════════════════════
#  sanitize_text
# ═══════════════════════════════════════════════

class TestSanitizeText:
    """Tests for sanitize_text()."""

    def test_normal_text_preserved(self) -> None:
        assert sanitize_text("Hello, world!") == "Hello, world!"

    def test_strips_whitespace(self) -> None:
        assert sanitize_text("  hello  ") == "hello"

    def test_removes_control_chars(self) -> None:
        # \x00 (null), \x07 (bell), \x1b (escape)
        text = "hello\x00world\x07test\x1bend"
        result = sanitize_text(text)
        assert "\x00" not in result
        assert "\x07" not in result
        assert "\x1b" not in result
        assert result == "helloworldtestend"

    def test_preserves_newlines_and_tabs(self) -> None:
        text = "line1\nline2\tindented"
        result = sanitize_text(text)
        assert "\n" in result
        assert "\t" in result

    def test_truncates_over_max_length(self) -> None:
        text = "a" * 100
        result = sanitize_text(text, max_length=10)
        assert len(result) == 10
        assert result == "a" * 10

    def test_exact_max_length_ok(self) -> None:
        text = "a" * 50
        result = sanitize_text(text, max_length=50)
        assert len(result) == 50

    def test_with_strip_control_false(self) -> None:
        text = "hello\x00world"
        result = sanitize_text(text, strip_control=False)
        assert "\x00" in result  # control chars preserved

    def test_non_string_input(self) -> None:
        assert sanitize_text(123) == "123"
        assert sanitize_text(None) == "None"

    def test_empty_string(self) -> None:
        assert sanitize_text("") == ""

    def test_only_whitespace(self) -> None:
        assert sanitize_text("   ") == ""


# ═══════════════════════════════════════════════
#  validate_question
# ═══════════════════════════════════════════════

class TestValidateQuestion:
    """Tests for validate_question()."""

    def test_valid_question(self) -> None:
        result = validate_question("What is async/await?")
        assert result.valid is True
        assert result.sanitized_value == "What is async/await?"

    def test_empty_question(self) -> None:
        result = validate_question("")
        assert result.valid is False
        assert "cannot be empty" in result.errors[0].lower()

    def test_whitespace_only(self) -> None:
        result = validate_question("   ")
        assert result.valid is False

    def test_truncation_warning(self) -> None:
        long_q = "x" * 2001
        result = validate_question(long_q, max_length=2000)
        assert result.valid is True
        assert result.warnings  # Truncation warning present
        assert len(result.sanitized_value) == 2000

    def test_exactly_at_limit(self) -> None:
        q = "x" * 100
        result = validate_question(q, max_length=100)
        assert result.valid is True
        assert len(result.sanitized_value) == 100
        assert result.warnings == []  # No truncation warning

    def test_sanitizes_control_chars(self) -> None:
        result = validate_question("hello\x00world")
        assert result.valid is True
        assert "\x00" not in result.sanitized_value

    def test_custom_max_length(self) -> None:
        result = validate_question("short", max_length=500)
        assert result.valid is True
        assert result.sanitized_value == "short"


# ═══════════════════════════════════════════════
#  validate_code_block
# ═══════════════════════════════════════════════

class TestValidateCodeBlock:
    """Tests for validate_code_block()."""

    def test_safe_code(self) -> None:
        code = "print('hello world')"
        result = validate_code_block(code)
        assert result.valid is True
        assert result.warnings == []

    def test_empty_code(self) -> None:
        result = validate_code_block("")
        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_whitespace_only(self) -> None:
        result = validate_code_block("   ")
        assert result.valid is False

    def test_detects_import_os(self) -> None:
        code = "import os\nos.listdir('.')"
        result = validate_code_block(code)
        assert result.valid is True
        assert any("OS module" in w for w in result.warnings)

    def test_detects_import_subprocess(self) -> None:
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = validate_code_block(code)
        assert any("Subprocess" in w for w in result.warnings)

    def test_detects_eval(self) -> None:
        code = "eval('print(1)')"
        result = validate_code_block(code)
        assert any("eval()" in w for w in result.warnings)

    def test_detects_exec(self) -> None:
        code = "exec('x = 1')"
        result = validate_code_block(code)
        assert any("exec()" in w for w in result.warnings)

    def test_detects_open_write_mode(self) -> None:
        code = 'with open("file.txt", "w") as f: f.write("data")'
        result = validate_code_block(code)
        assert any("write mode" in w for w in result.warnings)

    def test_detects_multiple_patterns(self) -> None:
        code = "import os\nimport socket\neval('x')"
        result = validate_code_block(code)
        # Should have at least 3 warnings
        assert len(result.warnings) >= 3

    def test_truncation_warning(self) -> None:
        code = "x = 1\n" * 200  # Exceeds 100-char limit
        result = validate_code_block(code, max_length=100)
        assert result.valid is True
        assert any("truncated" in w.lower() for w in result.warnings)
        assert len(result.sanitized_value) <= 100

    def test_safe_code_with_complex_python(self) -> None:
        code = """
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

for num in fibonacci(10):
    print(num)
"""
        result = validate_code_block(code)
        assert result.valid is True
        assert result.warnings == []

    def test_import_shutil_detected(self) -> None:
        code = "import shutil\nshutil.rmtree('/tmp/test')"
        result = validate_code_block(code)
        assert any("Shutil" in w for w in result.warnings)

    def test_import_ctypes_detected(self) -> None:
        code = "import ctypes\nctypes.CDLL('libc.so.6')"
        result = validate_code_block(code)
        assert any("Ctypes" in w for w in result.warnings)

    def test_dunder_import_detected(self) -> None:
        code = "__import__('os').system('ls')"
        result = validate_code_block(code)
        assert any("__import__()" in w for w in result.warnings)


# ═══════════════════════════════════════════════
#  validate_api_key
# ═══════════════════════════════════════════════

class TestValidateApiKey:
    """Tests for validate_api_key()."""

    def test_valid_openai_key(self) -> None:
        result = validate_api_key("openai", "sk-" + "a" * 48)
        assert result.valid is True

    def test_valid_anthropic_key(self) -> None:
        result = validate_api_key("anthropic", "sk-ant-" + "a" * 40)
        assert result.valid is True

    def test_valid_groq_key(self) -> None:
        result = validate_api_key("groq", "gsk_" + "a" * 24)
        assert result.valid is True

    def test_valid_google_key(self) -> None:
        result = validate_api_key("google", "AIza" + "a" * 25)
        assert result.valid is True

    def test_valid_huggingface_key(self) -> None:
        result = validate_api_key("huggingface", "hf_" + "a" * 24)
        assert result.valid is True

    def test_valid_github_key(self) -> None:
        result = validate_api_key("github", "ghp_" + "a" * 24)
        assert result.valid is True

    def test_empty_key(self) -> None:
        result = validate_api_key("openai", "")
        assert result.valid is False
        assert "empty" in result.errors[0]

    def test_whitespace_key(self) -> None:
        result = validate_api_key("openai", "   ")
        assert result.valid is False

    def test_short_key_warning(self) -> None:
        result = validate_api_key("openai", "abc")
        assert result.valid is True  # Not invalid, just warning
        assert any("too short" in w for w in result.warnings)

    def test_wrong_format_openai(self) -> None:
        result = validate_api_key("openai", "not-an-openai-key")
        assert result.valid is True
        assert any("should start with 'sk-'" in w for w in result.warnings)

    def test_unknown_provider_no_pattern_check(self) -> None:
        """Unknown providers should get basic checks only."""
        result = validate_api_key("unknown_provider", "some_key_value_12345")
        assert result.valid is True
        # No format warnings since we don't have a pattern for this provider
        fmt_warnings = [w for w in result.warnings if "format" in w.lower()]
        assert len(fmt_warnings) == 0

    def test_case_insensitive_provider(self) -> None:
        result = validate_api_key("OpenAI", "sk-" + "a" * 48)
        assert result.valid is True

    def test_wrong_groq_format(self) -> None:
        result = validate_api_key("groq", "sk-wrong-format")
        assert any("should start with 'gsk_'" in w for w in result.warnings)


# ═══════════════════════════════════════════════
#  validate_config
# ═══════════════════════════════════════════════

class TestValidateConfig:
    """Tests for validate_config()."""

    def test_valid_required_fields(self) -> None:
        config = {"name": "test", "count": 42}
        result = validate_config(config, {"name": str, "count": int})
        assert result.valid is True
        assert result.missing_required == []
        assert result.invalid_types == []

    def test_missing_required_field(self) -> None:
        config = {"name": "test"}
        result = validate_config(config, {"name": str, "count": int})
        assert result.valid is False
        assert "count" in result.missing_required

    def test_wrong_type_required(self) -> None:
        config = {"name": 42, "count": "not_int"}
        result = validate_config(config, {"name": str, "count": int})
        assert result.valid is False
        assert len(result.invalid_types) == 2

    def test_none_field_treated_as_missing(self) -> None:
        config = {"name": None}
        result = validate_config(config, {"name": str})
        assert result.valid is False
        assert "name" in result.missing_required

    def test_optional_fields_valid(self) -> None:
        config = {"name": "test"}
        result = validate_config(
            config,
            required_fields={"name": str},
            optional_fields={"desc": (str, "default")},
        )
        assert result.valid is True

    def test_optional_field_wrong_type(self) -> None:
        config = {"name": "test", "desc": 123}
        result = validate_config(
            config,
            required_fields={"name": str},
            optional_fields={"desc": (str, "default")},
        )
        assert result.valid is True  # Optional fields don't make it invalid
        assert any("desc" in w for w in result.warnings)

    def test_optional_field_none_ignored(self) -> None:
        config = {"name": "test", "desc": None}
        result = validate_config(
            config,
            required_fields={"name": str},
            optional_fields={"desc": (str, "default")},
        )
        assert result.valid is True
        assert result.warnings == []

    def test_no_optional_fields(self) -> None:
        config = {"name": "test"}
        result = validate_config(config, {"name": str})
        assert result.valid is True

    def test_empty_config(self) -> None:
        result = validate_config({}, {"name": str})
        assert result.valid is False
        assert "name" in result.missing_required


# ═══════════════════════════════════════════════
#  validate_path
# ═══════════════════════════════════════════════

class TestValidatePath:
    """Tests for validate_path()."""

    def test_path_no_existence_check(self) -> None:
        result = validate_path("/nonexistent/path")
        assert result.valid is True  # Doesn't need to exist

    def test_must_exist_nonexistent(self) -> None:
        result = validate_path("/nonexistent/path", must_exist=True)
        assert result.valid is False
        assert "does not exist" in result.errors[0]

    def test_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            tmp_path = f.name
        try:
            result = validate_path(tmp_path, must_exist=True, must_be_file=True)
            assert result.valid is True
        finally:
            os.unlink(tmp_path)

    def test_existing_file_but_wants_dir(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = f.name
        try:
            result = validate_path(tmp_path, must_exist=True, must_be_dir=True)
            assert result.valid is False
            assert "not a directory" in result.errors[0]
        finally:
            os.unlink(tmp_path)

    def test_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = validate_path(tmp_dir, must_exist=True, must_be_dir=True)
            assert result.valid is True

    def test_allowed_extension(self) -> None:
        result = validate_path("test.json", allowed_extensions={".json"})
        assert result.valid is True

    def test_disallowed_extension(self) -> None:
        result = validate_path("test.py", allowed_extensions={".json", ".csv"})
        assert result.valid is False
        assert "extension" in result.errors[0].lower()

    def test_allowed_extension_case_insensitive(self) -> None:
        result = validate_path("test.JSON", allowed_extensions={".json"})
        assert result.valid is True

    def test_returns_path_object(self) -> None:
        result = validate_path("some/path")
        assert isinstance(result.sanitized_value, Path)

    def test_multiple_errors(self) -> None:
        result = validate_path(
            "/nonexistent/file.py",
            must_exist=True,
            must_be_dir=True,
            allowed_extensions={".json"},
        )
        assert result.valid is False
        assert len(result.errors) >= 2  # At least "does not exist" + "not a directory" or extension

    def test_string_input(self) -> None:
        result = validate_path("relative/path")
        assert result.valid is True

    def test_path_input(self) -> None:
        result = validate_path(Path("relative/path"))
        assert result.valid is True


# ═══════════════════════════════════════════════
#  validate_json_string
# ═══════════════════════════════════════════════

class TestValidateJsonString:
    """Tests for validate_json_string()."""

    def test_valid_object(self) -> None:
        result = validate_json_string('{"key": "value"}')
        assert result.valid is True
        assert result.sanitized_value == {"key": "value"}

    def test_valid_array(self) -> None:
        result = validate_json_string("[1, 2, 3]")
        assert result.valid is True
        assert result.sanitized_value == [1, 2, 3]

    def test_invalid_json(self) -> None:
        result = validate_json_string("{bad json}")
        assert result.valid is False
        assert "Invalid JSON" in result.errors[0]

    def test_empty_string(self) -> None:
        result = validate_json_string("")
        assert result.valid is False

    def test_expect_object_gets_object(self) -> None:
        result = validate_json_string('{"a": 1}', schema_type="object")
        assert result.valid is True

    def test_expect_object_gets_array(self) -> None:
        result = validate_json_string("[1, 2]", schema_type="object")
        assert result.valid is False
        assert "Expected JSON object" in result.errors[0]

    def test_expect_array_gets_array(self) -> None:
        result = validate_json_string("[1, 2]", schema_type="array")
        assert result.valid is True

    def test_expect_array_gets_object(self) -> None:
        result = validate_json_string('{"a": 1}', schema_type="array")
        assert result.valid is False
        assert "Expected JSON array" in result.errors[0]

    def test_nested_object(self) -> None:
        json_str = '{"users": [{"name": "Alice"}, {"name": "Bob"}]}'
        result = validate_json_string(json_str)
        assert result.valid is True
        assert len(result.sanitized_value["users"]) == 2

    def test_parsed_value_type(self) -> None:
        result = validate_json_string("42")
        assert result.valid is True
        assert result.sanitized_value == 42
        assert isinstance(result.sanitized_value, int)


# ═══════════════════════════════════════════════
#  validate_training_record
# ═══════════════════════════════════════════════

class TestValidateTrainingRecord:
    """Tests for validate_training_record()."""

    def test_valid_record(self) -> None:
        record = {"instruction": "Write a function", "output": "def foo(): pass"}
        result = validate_training_record(record)
        assert result.valid is True

    def test_missing_instruction(self) -> None:
        result = validate_training_record({"output": "some output"})
        assert result.valid is False
        assert "instruction" in result.errors[0]

    def test_missing_output(self) -> None:
        result = validate_training_record({"instruction": "do something"})
        assert result.valid is False
        assert "output" in result.errors[0]

    def test_instruction_too_short(self) -> None:
        result = validate_training_record({"instruction": "ab", "output": "valid output"})
        assert result.valid is False
        assert "min 3 chars" in result.errors[0]

    def test_instruction_whitespace_only(self) -> None:
        result = validate_training_record({"instruction": "   ", "output": "valid output"})
        assert result.valid is False

    def test_not_a_dict(self) -> None:
        result = validate_training_record("not a dict")  # type: ignore[arg-type]
        assert result.valid is False
        assert "must be a dictionary" in result.errors[0]

    def test_list_instead_of_dict(self) -> None:
        result = validate_training_record([1, 2, 3])  # type: ignore[arg-type]
        assert result.valid is False

    def test_extra_fields_ok(self) -> None:
        record = {
            "instruction": "Write code",
            "output": "print('hi')",
            "source": "github",
            "category": "coding",
            "version": "3.10",
        }
        result = validate_training_record(record)
        assert result.valid is True

    def test_instruction_non_string(self) -> None:
        result = validate_training_record({"instruction": 123, "output": "output"})
        assert result.valid is False

    def test_output_non_string(self) -> None:
        result = validate_training_record({"instruction": "do it", "output": 456})
        assert result.valid is False

    def test_empty_instruction_string(self) -> None:
        result = validate_training_record({"instruction": "", "output": "output"})
        assert result.valid is False

    def test_empty_output_string(self) -> None:
        result = validate_training_record({"instruction": "do it", "output": ""})
        assert result.valid is False


# ═══════════════════════════════════════════════
#  get_env_bool
# ═══════════════════════════════════════════════

class TestGetEnvBool:
    """Tests for get_env_bool()."""

    def test_default_false_when_not_set(self) -> None:
        assert get_env_bool("NONEXISTENT_VAR_THAT_WONT_EXIST") is False

    def test_default_true_when_not_set(self) -> None:
        assert get_env_bool("NONEXISTENT_AGAIN", default=True) is True

    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"])
    def test_truthy_values(self, val: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_BOOL", val)
        assert get_env_bool("TEST_BOOL") is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "maybe", "", "2"])
    def test_falsy_values(self, val: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_BOOL", val)
        assert get_env_bool("TEST_BOOL") is False


# ═══════════════════════════════════════════════
#  get_env_int
# ═══════════════════════════════════════════════

class TestGetEnvInt:
    """Tests for get_env_int()."""

    def test_default_when_not_set(self) -> None:
        assert get_env_int("NONEXISTENT_INT") == 0

    def test_custom_default(self) -> None:
        assert get_env_int("NONEXISTENT_INT", default=42) == 42

    def test_parses_integer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_INT", "123")
        assert get_env_int("TEST_INT") == 123

    def test_parses_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_INT", "-5")
        assert get_env_int("TEST_INT") == -5

    def test_invalid_value_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_INT", "not_a_number")
        assert get_env_int("TEST_INT") == 0

    def test_empty_value_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_INT", "")
        assert get_env_int("TEST_INT") == 0


# ═══════════════════════════════════════════════
#  get_env_list
# ═══════════════════════════════════════════════

class TestGetEnvList:
    """Tests for get_env_list()."""

    def test_default_when_not_set(self) -> None:
        assert get_env_list("NONEXISTENT_LIST") == []

    def test_custom_default(self) -> None:
        assert get_env_list("NONEXISTENT", default=["a"]) == ["a"]

    def test_single_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", "item1")
        assert get_env_list("TEST_LIST") == ["item1"]

    def test_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", "a,b,c")
        assert get_env_list("TEST_LIST") == ["a", "b", "c"]

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", " a , b , c ")
        assert get_env_list("TEST_LIST") == ["a", "b", "c"]

    def test_custom_separator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", "a|b|c")
        assert get_env_list("TEST_LIST", separator="|") == ["a", "b", "c"]

    def test_empty_items_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", "a,,b,,c")
        assert get_env_list("TEST_LIST") == ["a", "b", "c"]

    def test_empty_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_LIST", "")
        assert get_env_list("TEST_LIST") == []


# ═══════════════════════════════════════════════
#  validate_dataset_file
# ═══════════════════════════════════════════════

class TestValidateDatasetFile:
    """Tests for validate_dataset_file()."""

    def test_nonexistent_file(self) -> None:
        result = validate_dataset_file("/nonexistent/dataset.json")
        assert result.valid is False

    def test_non_json_extension(self) -> None:
        # Create an existing file with a non-JSON extension
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("[{\"instruction\": \"test\", \"output\": \"test\"}]")
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is False
            assert "extension" in result.errors[0].lower()
        finally:
            os.unlink(tmp_path)

    def test_valid_dataset_file(self) -> None:
        data = [
            {"instruction": "Write a function", "output": "def foo(): pass"},
            {"instruction": "Explain lists", "output": "Lists are ordered collections"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is True
            assert result.sanitized_value["total_records"] == 2
            assert result.sanitized_value["valid_records"] == 2
            assert result.sanitized_value["invalid_records"] == 0
        finally:
            os.unlink(tmp_path)

    def test_invalid_records_in_file(self) -> None:
        data = [
            {"instruction": "Write code", "output": "print('hi')"},
            {"instruction": "", "output": "bad record"},  # Invalid
            {"output": "missing instruction"},  # Invalid
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is False
            assert result.sanitized_value["total_records"] == 3
            assert result.sanitized_value["valid_records"] == 1
            assert result.sanitized_value["invalid_records"] == 2
            assert len(result.errors) >= 1
        finally:
            os.unlink(tmp_path)

    def test_empty_dataset_array(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump([], f)
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is False
            assert "empty" in result.errors[0].lower()
        finally:
            os.unlink(tmp_path)

    def test_not_a_list_in_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"not": "a list"}, f)
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is False
            assert "JSON array" in result.errors[0]
        finally:
            os.unlink(tmp_path)

    def test_corrupted_json_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{corrupted json")
            tmp_path = f.name

        try:
            result = validate_dataset_file(tmp_path)
            assert result.valid is False
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════════════
#  DANGEROUS_CODE_PATTERNS (module-level constant)
# ═══════════════════════════════════════════════

class TestDangerousCodePatterns:
    """Verify the DANGEROUS_CODE_PATTERNS constant is well-formed."""

    def test_is_list_of_tuples(self) -> None:
        assert isinstance(DANGEROUS_CODE_PATTERNS, list)
        for item in DANGEROUS_CODE_PATTERNS:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], str)  # regex pattern
            assert isinstance(item[1], str)  # description

    def test_has_expected_patterns(self) -> None:
        descriptions = [d for _, d in DANGEROUS_CODE_PATTERNS]
        assert any("OS module" in d for d in descriptions)
        assert any("Subprocess" in d for d in descriptions)
        assert any("eval()" in d for d in descriptions)
        assert any("exec()" in d for d in descriptions)

    def test_no_empty_patterns(self) -> None:
        for pattern, description in DANGEROUS_CODE_PATTERNS:
            assert pattern, f"Empty pattern for {description}"
            assert description, f"Empty description for {pattern}"
