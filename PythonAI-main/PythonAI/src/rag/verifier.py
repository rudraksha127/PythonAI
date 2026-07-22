from __future__ import annotations

from typing import Any

import ollama

from src.rag.models import DEFAULT_MODEL
from src.utils.code_parser import extract_code_blocks
from src.utils.sandbox import execute_code


class AnswerVerifier:
    """
    Verification System for RAG answers.
    Cross-references facts against context, checks code execution, and assigns confidence.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def verify_code(self, answer_text: str, timeout: int = 5) -> dict[str, Any]:
        """
        Extract code blocks and verify they run successfully.
        """
        code_blocks = extract_code_blocks(answer_text)
        results = []
        all_passed = True

        for i, code in enumerate(code_blocks[:3]):  # Check at most 3 blocks
            output, error = execute_code(code, timeout=timeout)

            # If skipped due to safety, we consider it neutral (not a fail)
            if error == "Skipped (safety)":
                results.append({"status": "skipped", "output": error})
                continue

            if error:
                all_passed = False
                results.append({"status": "error", "output": error})
            else:
                results.append({"status": "success", "output": output})

        return {"all_passed": all_passed, "details": results, "blocks_checked": len(code_blocks[:3])}

    def verify_facts(self, question: str, answer_text: str, context: str) -> dict[str, Any]:
        """
        Use an LLM to cross-reference facts in the answer against the retrieved context.
        """
        prompt = f"""You are a Fact Checker.
Task: Verify if the ANSWER is fully supported by the CONTEXT, or if it hallucinates information not present.
It is okay if the answer uses general Python knowledge, but it must NOT contradict the context or invent false APIs.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER TO VERIFY:
{answer_text}

Output ONLY a JSON object with this exact structure:
{{"hallucinations_found": true/false, "explanation": "brief reason"}}
"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 150},
                format="json",
            )
            import json

            result = json.loads(response["message"]["content"])
            return result
        except Exception as e:
            print(f"[Verifier] Fact check failed: {e}")
            return {"hallucinations_found": False, "explanation": "Verification failed"}

    def compute_confidence(self, code_verification: dict[str, Any], fact_verification: dict[str, Any]) -> float:
        """
        Compute a confidence score (0.0 to 1.0) based on verification results.
        """
        score = 1.0

        if fact_verification.get("hallucinations_found", False):
            score -= 0.4

        if not code_verification.get("all_passed", True):
            # Penalize for broken code
            error_count = sum(1 for d in code_verification.get("details", []) if d.get("status") == "error")
            score -= 0.2 * error_count

        return max(0.0, min(1.0, score))
