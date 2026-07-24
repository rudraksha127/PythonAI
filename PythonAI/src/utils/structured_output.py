"""
ForgeAI Structured Output Engine — Outlines Integration
========================================================
Enforces strict JSON schema / regex constraint compliance on LLM output.

Uses outlines when available for guided decoding, or falls back to system prompt
schema injection + Pydantic validation.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger("forgeai.structured")

T = TypeVar("T", bound=BaseModel)


def generate_structured_output(
    prompt: str,
    schema: type[T],
    model_name: str = "qwen2.5-coder",
    system_prompt: str | None = None,
) -> T:
    """Generate structured output adhering to a Pydantic schema.

    Attempts Outlines guided decoding first; falls back to standard LLM call
    with JSON schema instruction + Pydantic parsing.
    """
    # 1. Try Outlines
    try:
        import outlines

        model = outlines.models.ollama(model_name)
        generator = outlines.generate.json(model, schema)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        result = generator(full_prompt)
        logger.info(f"Generated structured output via Outlines for {schema.__name__}")
        return result
    except ImportError:
        logger.debug("outlines package not available. Using Pydantic fallback schema enforcement.")
    except Exception as e:
        logger.warning(f"Outlines generation failed ({e}). Falling back to standard LLM parsing.")

    # 2. Fallback via Ollama / standard LLM
    try:
        import ollama
        from ollama import chat as ollama_chat

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        fallback_system = (
            (system_prompt or "You are a helpful AI coding assistant.")
            + "\n\nCRITICAL REQUIREMENT: You MUST respond ONLY with valid JSON matching the following JSON Schema:\n"
            + f"```json\n{schema_json}\n```\nDo NOT include markdown formatting outside the JSON block."
        )

        response = ollama.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": fallback_system},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        response_text = response["message"]["content"]
        cleaned_json = _extract_json(response_text)
        parsed = schema.model_validate_json(cleaned_json)
        logger.info(f"Generated structured output via fallback parser for {schema.__name__}")
        return parsed

    except Exception as e:
        logger.error(f"Structured output fallback generation failed: {e}")
        raise ValueError(f"Failed to generate structured output for {schema.__name__}: {e}") from e


def _extract_json(text: str) -> str:
    """Extract JSON object or array string from LLM output text."""
    text = text.strip()
    # Match markdown json block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()

    # Match first { ... } or [ ... ]
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        return match.group(1).strip()

    return text
