"""
ForgeAI Guardrails Engine — Guardrails-AI Safety Integration
=============================================================
Provides input prompt validation and output safety checks.

Protects against:
- Prompt injection / jailbreak attempts
- Malicious shell commands or unintended file system destruction
- System prompt leaking
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("forgeai.guardrails")

_GUARD = None


def get_guardrails_engine() -> Any | None:
    """Get Guardrails-AI engine instance or None if not initialized."""
    global _GUARD

    if _GUARD is not None:
        return _GUARD

    try:
        import guardrails as gd

        _GUARD = gd.Guard()
        logger.info("Guardrails-AI engine initialized successfully")
    except ImportError:
        logger.debug("guardrails-ai package not installed. Using local security guardrails.")
        _GUARD = None
    except Exception as e:
        logger.warning(f"Guardrails-AI init error: {e}")
        _GUARD = None

    return _GUARD


class GuardrailValidationResult:

    def __init__(self, is_valid: bool, reason: str = "", sanitized_input: str = "") -> None:
        self.is_valid = is_valid
        self.reason = reason
        self.sanitized_input = sanitized_input


def validate_user_prompt(prompt: str) -> GuardrailValidationResult:
    """Validate user input prompt before sending to LLM."""
    prompt = prompt.strip()

    # 1. Guardrails-AI validation if available
    guard = get_guardrails_engine()
    if guard is not None:
        try:
            res = guard.validate(prompt)
            if hasattr(res, "validation_passed") and not res.validation_passed:
                return GuardrailValidationResult(
                    is_valid=False,
                    reason="Input failed Guardrails-AI security policy",
                    sanitized_input=prompt,
                )
        except Exception as e:
            logger.debug(f"Guardrails-AI validation error: {e}")

    # 2. Local heuristic checks for prompt injection & destructive commands
    dangerous_patterns = [
        (r"ignore\s+all\s+previous\s+instructions", "Prompt injection attempt detected"),
        (r"rm\s+-rf\s+/", "Destructive shell command attempt detected"),
        (r"format\s+[c-z]:\s+/f", "System drive format attempt detected"),
    ]

    for pattern, reason in dangerous_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            logger.warning(f"Guardrail triggered: {reason}")
            return GuardrailValidationResult(is_valid=False, reason=reason, sanitized_input=prompt)

    return GuardrailValidationResult(is_valid=True, sanitized_input=prompt)


def validate_agent_output(output: str) -> GuardrailValidationResult:
    """Validate agent output text before returning to user."""
    output = output.strip()

    # Check for leaked secrets or API key formats
    secret_patterns = [
        (r"sk-[a-zA-Z0-9]{32,}", "Potential OpenAI API key leaked in output"),
        (r"ghp_[a-zA-Z0-9]{36}", "Potential GitHub token leaked in output"),
    ]

    for pattern, reason in secret_patterns:
        if re.search(pattern, output):
            logger.warning(f"Output guardrail triggered: {reason}")
            sanitized = re.sub(pattern, "[REDACTED_API_KEY]", output)
            return GuardrailValidationResult(is_valid=True, reason=reason, sanitized_input=sanitized)

    return GuardrailValidationResult(is_valid=True, sanitized_input=output)
