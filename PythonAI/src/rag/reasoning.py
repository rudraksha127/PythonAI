from __future__ import annotations

import ollama

from src.rag.models import DEFAULT_MODEL


class ReasoningEngine:
    """
    Reasoning engine to perform Chain-of-Thought (CoT) and multi-step planning.
    It can decide if a query needs deep reasoning, generate a plan, and reflect on it.
    """
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def requires_reasoning(self, question: str) -> bool:
        """
        Determine if a question requires deep reasoning.
        Simple API lookups don't. Architecture, bugs, or multi-step algorithms do.
        """
        # A simple heuristic based router
        complex_keywords = [
            "why", "how to design", "architecture", "debug", "issue", "error",
            "optimize", "performance", "compare", "vs", "difference between",
            "best practice", "pattern", "implement a", "build a", "threading",
            "asyncio", "memory leak"
        ]
        q_lower = question.lower()
        if len(q_lower.split()) > 15: # Long questions usually need reasoning
            return True

        for kw in complex_keywords:
            if kw in q_lower:
                return True

        return False

    def generate_plan(self, question: str, context: str) -> str:
        """
        Generate a step-by-step reasoning plan to answer the complex question.
        """
        prompt = f"""You are an expert Python architect.
Before answering the user's question, you must create a brief, logical, step-by-step plan.
Do NOT write the final answer or code yet. Only output the numbered plan.

CONTEXT:
{context}

QUESTION:
{question}

PLAN:
"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2, "num_predict": 300},
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"[Reasoning] Plan generation failed: {e}")
            return "1. Analyze context.\n2. Write code.\n3. Explain."

    def reflect_and_correct(self, question: str, draft_answer: str) -> str:
        """
        Reflect on a drafted answer and suggest corrections if needed.
        """
        prompt = f"""You are a strict Python code reviewer.
Review the drafted answer to the user's question. Check for:
1. Accuracy and correctness
2. Edge cases missed
3. Security/Performance flaws
4. Readability and idiomatic Python

If it is perfect, reply with exactly: "LGTM"
Otherwise, provide specific, actionable corrections.

QUESTION:
{question}

DRAFT ANSWER:
{draft_answer}

REVIEW:
"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 400},
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"[Reasoning] Reflection failed: {e}")
            return "LGTM"

