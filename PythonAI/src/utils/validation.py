"""
PythonAI — Validation Utilities
================================
Centralized validation and sanitization for inputs, API keys, configs, and data.

Use these functions instead of ad-hoc checks throughout the codebase.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════
#  Validation Result
# ═══════════════════════════════════════════════


@dataclass
class ValidationResult:
    """Standard result for all validation functions."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_value: Any = None

    def __bool__(self) -> bool:
        return self.valid

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another validation result into this one."""
        self.valid = self.valid and other.valid
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self

    @classmethod
    def ok(cls, value: Any = None) -> ValidationResult:
        return cls(valid=True, sanitized_value=value)

    @classmethod
    def fail(cls, error: str, value: Any = None) -> ValidationResult:
        return cls(valid=False, errors=[error], sanitized_value=value)

    @classmethod
    def warn(cls, warning: str, value: Any = None) -> ValidationResult:
        return cls(valid=True, warnings=[warning], sanitized_value=value)


# ═══════════════════════════════════════════════
#  Text / Input Sanitization
# ═══════════════════════════════════════════════

# Control characters to strip (keep newlines, tabs)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Dangerous patterns to flag in code execution
DANGEROUS_CODE_PATTERNS: list[tuple[str, str]] = [
    (r"import\s+os", "OS module import — file system access"),
    (r"import\s+subprocess", "Subprocess module import — shell execution"),
    (r"import\s+shutil", "Shutil module import — file system operations"),
    (r"import\s+socket", "Socket module import — network access"),
    (r"import\s+ctypes", "Ctypes module import — native code execution"),
    (r"eval\s*\(", "eval() — arbitrary code execution"),
    (r"exec\s*\(", "exec() — arbitrary code execution"),
    (r"__import__\s*\(", "__import__() — dynamic module loading"),
    (r"open\s*\([^)]*['\"]w", "open() in write mode — file modification"),
]


def sanitize_text(text: str, max_length: int = 10000, strip_control: bool = True) -> str:
    """Sanitize user-provided text: strip control chars and enforce length.

    Args:
        text: Input text to sanitize.
        max_length: Maximum allowed length (default: 10,000).
        strip_control: Whether to remove control characters.

    Returns:
        Sanitized text string.
    """
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    if strip_control:
        text = _CONTROL_CHARS.sub("", text)
    return text[:max_length]


def validate_question(question: str, max_length: int = 2000) -> ValidationResult:
    """Validate and sanitize a user question for the RAG engine.

    Args:
        question: The user's question string.
        max_length: Maximum allowed question length.

    Returns:
        ValidationResult with sanitized question in sanitized_value.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not question or not question.strip():
        errors.append("Question cannot be empty")
        return ValidationResult(valid=False, errors=errors)

    if len(question) > max_length:
        warnings.append(f"Question truncated to {max_length} characters")
        question = question[:max_length]

    sanitized = sanitize_text(question, max_length=max_length)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        sanitized_value=sanitized,
    )


def validate_code_block(code: str, max_length: int = 5000) -> ValidationResult:
    """Validate a Python code block for safety concerns.

    Args:
        code: Python code to validate.
        max_length: Maximum code length.

    Returns:
        ValidationResult with warnings for dangerous patterns.
    """
    warnings: list[str] = []

    if not code or not code.strip():
        return ValidationResult.fail("Code block is empty", value=code)

    if len(code) > max_length:
        warnings.append(f"Code truncated to {max_length} characters")
        code = code[:max_length]

    # Check for dangerous patterns
    for pattern, description in DANGEROUS_CODE_PATTERNS:
        if re.search(pattern, code):
            warnings.append(f"Dangerous pattern detected: {description}")

    return ValidationResult(valid=True, warnings=warnings, sanitized_value=code)


# ═══════════════════════════════════════════════
#  API Key Validation
# ═══════════════════════════════════════════════

# Provider-specific key pattern validation
_KEY_PATTERNS: dict[str, tuple[str, str]] = {
    "openai": (r"^sk-[A-Za-z0-9]{20,}$", "OpenAI key should start with 'sk-'"),
    "anthropic": (r"^sk-ant-[A-Za-z0-9]{40,}$", "Anthropic key should start with 'sk-ant-'"),
    "groq": (r"^gsk_[A-Za-z0-9]{20,}$", "Groq key should start with 'gsk_'"),
    "google": (r"^AIza[A-Za-z0-9_-]{20,}$", "Google key should start with 'AIza'"),
    "deepseek": (r"^sk-[A-Za-z0-9]{20,}$", "DeepSeek key should start with 'sk-'"),
    "huggingface": (r"^hf_[A-Za-z0-9]{20,}$", "HuggingFace token should start with 'hf_'"),
    "github": (r"^gh[pousr]_[A-Za-z0-9]{20,}$", "GitHub token has unexpected format"),
}


def validate_api_key(provider: str, key: str) -> ValidationResult:
    """Validate an API key for a specific provider.

    Args:
        provider: Provider name (e.g., 'openai', 'anthropic').
        key: The API key string.

    Returns:
        ValidationResult with warnings for unusual patterns.
    """
    warnings: list[str] = []

    if not key or not key.strip():
        return ValidationResult.fail(f"API key for '{provider}' is empty")

    if len(key) < 10:
        warnings.append(f"Key for '{provider}' seems too short ({len(key)} chars)")

    # Check provider-specific pattern
    pattern_info = _KEY_PATTERNS.get(provider.lower())
    if pattern_info:
        pattern, hint = pattern_info
        if not re.match(pattern, key.strip()):
            warnings.append(f"Key format may be invalid: {hint}")

    return ValidationResult(valid=True, warnings=warnings)


# ═══════════════════════════════════════════════
#  Configuration Validation
# ═══════════════════════════════════════════════


@dataclass
class ConfigValidation:
    """Result of validating a configuration dictionary."""

    valid: bool = True
    missing_required: list[str] = field(default_factory=list)
    invalid_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_config(
    config: dict[str, Any],
    required_fields: dict[str, type],
    optional_fields: dict[str, tuple[type, Any]] | None = None,
) -> ConfigValidation:
    """Validate a configuration dictionary against field requirements.

    Args:
        config: Configuration dictionary to validate.
        required_fields: Dict mapping field name to expected type.
        optional_fields: Dict mapping field name to (type, default_value).

    Returns:
        ConfigValidation with any issues found.
    """
    result = ConfigValidation()

    for field_name, expected_type in required_fields.items():
        if field_name not in config or config[field_name] is None:
            result.missing_required.append(field_name)
            result.valid = False
        elif not isinstance(config[field_name], expected_type):
            result.invalid_types.append(
                f"'{field_name}': expected {expected_type.__name__}, got {type(config[field_name]).__name__}"
            )
            result.valid = False

    if optional_fields:
        for field_name, (expected_type, default) in optional_fields.items():
            if field_name in config and config[field_name] is not None:
                if not isinstance(config[field_name], expected_type):
                    result.warnings.append(
                        f"'{field_name}': expected {expected_type.__name__}, got {type(config[field_name]).__name__}"
                    )

    return result


# ═══════════════════════════════════════════════
#  Path Validation
# ═══════════════════════════════════════════════


def validate_path(
    path: str | Path,
    must_exist: bool = False,
    must_be_file: bool = False,
    must_be_dir: bool = False,
    allowed_extensions: set[str] | None = None,
) -> ValidationResult:
    """Validate a file system path.

    Args:
        path: Path to validate.
        must_exist: Whether the path must already exist.
        must_be_file: Whether the path must be a file.
        must_be_dir: Whether the path must be a directory.
        allowed_extensions: Set of allowed file extensions (e.g., {'.json', '.csv'}).

    Returns:
        ValidationResult.
    """
    errors: list[str] = []
    path_obj = Path(path)

    if must_exist and not path_obj.exists():
        errors.append(f"Path does not exist: {path_obj}")

    if must_be_file and not path_obj.is_file():
        errors.append(f"Path is not a file: {path_obj}")

    if must_be_dir and not path_obj.is_dir():
        errors.append(f"Path is not a directory: {path_obj}")

    if allowed_extensions and path_obj.suffix.lower() not in allowed_extensions:
        errors.append(f"File extension '{path_obj.suffix}' not allowed. Allowed: {', '.join(allowed_extensions)}")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        sanitized_value=path_obj,
    )


# ═══════════════════════════════════════════════
#  JSON Validation
# ═══════════════════════════════════════════════


def validate_json_string(json_str: str, schema_type: str | None = None) -> ValidationResult:
    """Validate a JSON string and optionally check its structure.

    Args:
        json_str: JSON string to parse and validate.
        schema_type: Optional type hint ('object', 'array', 'any').

    Returns:
        ValidationResult with parsed value in sanitized_value.
    """
    errors: list[str] = []

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult.fail(f"Invalid JSON: {e}")

    if schema_type == "object" and not isinstance(parsed, dict):
        errors.append("Expected JSON object (dict)")
    elif schema_type == "array" and not isinstance(parsed, list):
        errors.append("Expected JSON array (list)")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        sanitized_value=parsed,
    )


# ═══════════════════════════════════════════════
#  Data Record Validation
# ═══════════════════════════════════════════════


def validate_training_record(record: dict[str, Any]) -> ValidationResult:
    """Validate a single training data record.

    Args:
        record: Training record with 'instruction' and 'output' fields.

    Returns:
        ValidationResult.
    """
    errors: list[str] = []

    if not isinstance(record, dict):
        return ValidationResult.fail("Record must be a dictionary")

    if "instruction" not in record:
        errors.append("Missing required field: 'instruction'")
    elif not isinstance(record["instruction"], str) or len(record["instruction"].strip()) < 3:
        errors.append("'instruction' must be a non-empty string (min 3 chars)")

    if "output" not in record:
        errors.append("Missing required field: 'output'")
    elif not isinstance(record["output"], str) or len(record["output"].strip()) < 3:
        errors.append("'output' must be a non-empty string (min 3 chars)")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        sanitized_value=record,
    )


# ═══════════════════════════════════════════════
#  Environment Variable Helpers
# ═══════════════════════════════════════════════


def get_env_bool(name: str, default: bool = False) -> bool:
    """Get an environment variable as a boolean.

    Accepts: '1', 'true', 'yes', 'on' (case-insensitive) as True.
    All other values return default.

    Args:
        name: Environment variable name.
        default: Default value if not set.

    Returns:
        Boolean value.
    """
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def get_env_int(name: str, default: int = 0) -> int:
    """Get an environment variable as an integer.

    Args:
        name: Environment variable name.
        default: Default value if not set or invalid.

    Returns:
        Integer value.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_env_list(name: str, separator: str = ",", default: list[str] | None = None) -> list[str]:
    """Get an environment variable as a list.

    Args:
        name: Environment variable name.
        separator: Separator character (default: ',').
        default: Default value if not set.

    Returns:
        List of strings.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]


# ═══════════════════════════════════════════════
#  File Content Validation
# ═══════════════════════════════════════════════


def validate_dataset_file(filepath: str | Path) -> ValidationResult:
    """Validate a training dataset JSON file.

    Args:
        filepath: Path to the dataset JSON file.

    Returns:
        ValidationResult with dataset stats in sanitized_value.
    """
    errors: list[str] = []
    path_result = validate_path(filepath, must_exist=True, must_be_file=True, allowed_extensions={".json"})
    if not path_result:
        return path_result

    try:
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return ValidationResult.fail(f"Cannot read dataset file: {e}")

    if not isinstance(data, list):
        return ValidationResult.fail("Dataset must be a JSON array")

    if len(data) == 0:
        return ValidationResult.fail("Dataset is empty")

    valid_records = 0
    invalid_records = 0
    for i, record in enumerate(data):
        result = validate_training_record(record)
        if result:
            valid_records += 1
        else:
            invalid_records += 1
            if len(errors) < 5:  # Limit error reporting
                errors.append(f"Record {i}: {result.errors[0]}")

    return ValidationResult(
        valid=invalid_records == 0,
        errors=errors,
        sanitized_value={
            "total_records": len(data),
            "valid_records": valid_records,
            "invalid_records": invalid_records,
        },
    )
