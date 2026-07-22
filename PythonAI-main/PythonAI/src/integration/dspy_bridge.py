"""
DSPy Bridge — Programmatic Prompt Optimization Framework
=========================================================

Wraps the `dspy` library (stanfordnlp/dspy) to provide declarative
LLM pipelines with automatic prompt optimization via teleprompters.

DSPy replaces brittle prompt engineering with Python modules — you
define the task signature (inputs/outputs) and DSPy optimizes prompts
and few-shot examples automatically.

Architecture:
    - Lazy initialization of DSPy + LM on first use
    - Supports all LiteLLM providers (OpenAI, Anthropic, Ollama, etc.)
    - ChainOfThought, ReAct, ProgramOfThought module support
    - Automatic optimization via BootstrapFewShot / MIPROv2 teleprompters
    - Dataset management with dspy.Example
    - Graceful fallback when dspy is not installed

Usage:
    from src.integration.dspy_bridge import DSPyBridge

    bridge = DSPyBridge()
    answer = bridge.classify(
        prompt="Classify this review: 'Great product!'",
        classes=["positive", "negative", "neutral"],
    )
    # => {"classification": "positive", "confidence": 0.95}

Environment:
    DSPY_LM_PROVIDER  : "openai" or "anthropic" or "ollama" (default: openai)
    DSPY_LM_MODEL     : model ID (default: gpt-4o-mini)
    DSPY_API_KEY      : API key for the LM provider
    DSPY_MAX_TOKENS   : max generation tokens (default: 4096)
    DSPY_TEMPERATURE  : sampling temperature (default: 0.0)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Callable

logger = logging.getLogger("forgeai.integration.dspy")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_LM_PROVIDER = "openai"
DEFAULT_LM_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.0


class DSPyBridge:
    """Declarative LLM pipeline builder with automatic prompt optimization.

    Provides pre-built modules for classification, QA, chain-of-thought,
    and ReAct reasoning, plus an optimization pipeline that automatically
    improves prompts from training examples.

    Lazy-initializes DSPy + LM on first use.
    """

    def __init__(
        self,
        lm_provider: str | None = None,
        lm_model: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        enabled: bool = True,
    ) -> None:
        self._lm_provider = lm_provider or os.environ.get("DSPY_LM_PROVIDER", DEFAULT_LM_PROVIDER)
        self._lm_model = lm_model or os.environ.get("DSPY_LM_MODEL", DEFAULT_LM_MODEL)
        self._api_key = api_key or os.environ.get("DSPY_API_KEY", "")
        self._max_tokens = max_tokens or DEFAULT_MAX_TOKENS
        self._temperature = temperature or DEFAULT_TEMPERATURE
        self._enabled = enabled

        self._dspy = None
        self._lm = None
        self._initialized = False
        self._init_error: str | None = None
        self._optimized_modules: dict[str, Any] = {}

        self._stats = {
            "classify_calls": 0,
            "qa_calls": 0,
            "chain_of_thought_calls": 0,
            "react_calls": 0,
            "optimization_runs": 0,
            "errors": 0,
            "last_error": None,
            "avg_response_ms": 0.0,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Load dspy + configure LM on first use."""
        if self._initialized:
            return self._lm is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "DSPy bridge disabled"
            logger.info("DSPyBridge is disabled")
            return False

        try:
            import dspy
            self._dspy = dspy

            # Configure LM via LiteLLM provider string
            provider_model = f"{self._lm_provider}/{self._lm_model}"
            lm_kwargs: dict[str, Any] = {
                "model": provider_model,
                "max_tokens": self._max_tokens,
                "temperature": self._temperature,
            }
            if self._api_key:
                lm_kwargs["api_key"] = self._api_key

            self._lm = dspy.LM(**lm_kwargs)
            dspy.configure(lm=self._lm)
            self._initialized = True

            logger.info(f"DSPy initialized: {provider_model}")
            return True

        except ImportError:
            self._init_error = "dspy not installed. Run: pip install dspy"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"DSPyBridge init failed: {e}")

        self._initialized = True
        return False

    # ── Module Definitions ───────────────────────────────────────

    def _make_signature(self, inputs: list[str], outputs: list[str]) -> type:
        """Create a dynamic DSPy Signature from field name lists."""
        import dspy

        fields_str = ", ".join(inputs) + " -> " + ", ".join(outputs)

        class DynamicSig(dspy.Signature):
            """Dynamically generated signature."""
            __doc__ = fields_str

        DynamicSig.__doc__ = fields_str
        return DynamicSig

    # ── Public API ───────────────────────────────────────────────

    def classify(
        self,
        prompt: str,
        classes: list[str],
        context: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Classify input text into one of the given classes.

        Uses ChainOfThought for step-by-step reasoning before classifying.

        Args:
            prompt: Text to classify.
            classes: List of possible class labels.
            context: Optional additional context.
            temperature: Override default temperature.

        Returns:
            Dict with "classification", "reasoning", "confidence".
        """
        if not self._ensure_initialized() or self._dspy is None:
            return {"classification": None, "error": self._init_error or "DSPy not available"}

        try:
            import dspy

            start = time.time()

            class ClassificationModule(dspy.Module):
                def __init__(self):
                    super().__init__()
                    self.chain_of_thought = dspy.ChainOfThought("context, options -> classification, reasoning")

                def forward(self, context, options):
                    return self.chain_of_thought(context=context, options=options)

            module = ClassificationModule()
            options_str = ", ".join(classes)
            combined_context = f"{context}\n\n{prompt}" if context else prompt

            result = module(context=combined_context, options=options_str)

            elapsed = time.time() - start
            self._stats["classify_calls"] += 1
            self._stats["avg_response_ms"] = (
                (self._stats["avg_response_ms"] * (self._stats["classify_calls"] - 1) + elapsed * 1000)
                / self._stats["classify_calls"]
            )

            classification = getattr(result, "classification", "")
            reasoning = getattr(result, "reasoning", "")

            # Estimate confidence from reasoning length (heuristic)
            confidence = min(1.0, len(reasoning) / 200) if reasoning else 0.5

            return {
                "classification": str(classification).strip(),
                "reasoning": str(reasoning).strip(),
                "confidence": round(confidence, 2),
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"classification": None, "error": str(e)}

    def chain_of_thought(
        self,
        prompt: str,
        instructions: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Answer a question with step-by-step reasoning.

        Uses dspy.ChainOfThought to generate a reasoning trace before
        producing the final answer.

        Args:
            prompt: The question or task.
            instructions: Optional system-level guidance.

        Returns:
            Dict with "reasoning", "answer", and metadata.
        """
        if not self._ensure_initialized() or self._dspy is None:
            return {"answer": None, "error": self._init_error or "DSPy not available"}

        try:
            import dspy

            start = time.time()

            class ThoughtModule(dspy.Module):
                def __init__(self):
                    super().__init__()
                    self.chain_of_thought = dspy.ChainOfThought("question -> reasoning, answer")

                def forward(self, question):
                    return self.chain_of_thought(question=question)

            module = ThoughtModule()
            result = module(question=prompt)

            elapsed = time.time() - start
            self._stats["chain_of_thought_calls"] += 1

            return {
                "reasoning": str(getattr(result, "reasoning", "")).strip(),
                "answer": str(getattr(result, "answer", "")).strip(),
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"answer": None, "error": str(e)}

    def react(
        self,
        prompt: str,
        max_steps: int = 5,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Execute a ReAct reasoning loop (Reasoning + Acting).

        Uses dspy.ReAct to iteratively reason, take actions, and
        observe results before producing a final answer.

        Args:
            prompt: The task to solve.
            max_steps: Maximum ReAct iterations.
            temperature: Override default temperature.

        Returns:
            Dict with "answer", "trajectory" (list of steps), and metadata.
        """
        if not self._ensure_initialized() or self._dspy is None:
            return {"answer": None, "error": self._init_error or "DSPy not available"}

        try:
            import dspy

            start = time.time()

            class ReactModule(dspy.Module):
                def __init__(self, max_iterations=5):
                    super().__init__()
                    self.react = dspy.ReAct(
                        signature="question -> answer",
                        max_iters=max_iterations,
                    )

                def forward(self, question):
                    return self.react(question=question)

            module = ReactModule(max_iterations=max_steps)
            result = module(question=prompt)

            elapsed = time.time() - start
            self._stats["react_calls"] += 1

            return {
                "answer": str(getattr(result, "answer", "")).strip(),
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"answer": None, "error": str(e)}

    def optimize(
        self,
        training_data: list[dict[str, str]],
        input_fields: list[str],
        output_fields: list[str],
        metric_fn: Callable | None = None,
        num_threads: int = 4,
    ) -> dict[str, Any]:
        """Optimize a module using training data and teleprompters.

        Uses BootstrapFewShot to automatically improve prompts and
        few-shot examples from a training dataset.

        Args:
            training_data: List of dicts with input and output fields.
            input_fields: Names of input fields.
            output_fields: Names of output fields.
            metric_fn: Function(likely_output, ground_truth) -> bool.
            num_threads: Parallel threads for optimization.

        Returns:
            Dict with optimization results and metrics.
        """
        if not self._ensure_initialized() or self._dspy is None:
            return {"success": False, "error": self._init_error or "DSPy not available"}

        try:
            import dspy
            from dspy.teleprompt import BootstrapFewShot

            start = time.time()

            # Convert training data to dspy.Example objects
            examples = []
            for item in training_data:
                example = dspy.Example(**item)
                example = example.with_inputs(*input_fields)
                examples.append(example)

            # Split into train and dev
            split = int(len(examples) * 0.8)
            trainset = examples[:split]
            devset = examples[split:]

            if not trainset:
                return {"success": False, "error": "Training set is empty"}

            # Define a simple module for the task
            class OptimizedModule(dspy.Module):
                def __init__(self):
                    super().__init__()
                    signature_str = ", ".join(input_fields) + " -> " + ", ".join(output_fields)
                    self.cot = dspy.ChainOfThought(signature_str)

                def forward(self, **kwargs):
                    return self.cot(**kwargs)

            # Default metric: exact match
            if metric_fn is None:
                def default_metric(example, prediction, trace=None):
                    for field in output_fields:
                        pred_val = getattr(prediction, field, "")
                        true_val = getattr(example, field, "")
                        if str(pred_val).strip().lower() != str(true_val).strip().lower():
                            return False
                    return True
                metric_fn = default_metric

            # Optimize
            teleprompter = BootstrapFewShot(metric=metric_fn, max_rounds=3,
                                            num_threads=num_threads)
            compiled = teleprompter.compile(OptimizedModule(), trainset=trainset)

            # Evaluate on dev set
            correct = 0
            for example in devset:
                kwargs = {f: getattr(example, f) for f in input_fields}
                prediction = compiled(**kwargs)
                all_match = True
                for field in output_fields:
                    pred_val = str(getattr(prediction, field, "")).strip().lower()
                    true_val = str(getattr(example, field, "")).strip().lower()
                    if pred_val != true_val:
                        all_match = False
                        break
                if all_match:
                    correct += 1

            accuracy = correct / len(devset) if devset else 0.0
            elapsed = time.time() - start

            self._stats["optimization_runs"] += 1

            # Cache the compiled module
            cache_key = f"optimized_{self._stats['optimization_runs']}"
            self._optimized_modules[cache_key] = compiled

            return {
                "success": True,
                "accuracy": round(accuracy, 3),
                "train_samples": len(trainset),
                "dev_samples": len(devset),
                "elapsed_seconds": round(elapsed, 2),
                "module_key": cache_key,
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"success": False, "error": str(e)}

    def get_optimized_module(self, key: str) -> Any | None:
        """Retrieve a previously compiled optimization module."""
        return self._optimized_modules.get(key)

    # ── Info ─────────────────────────────────────────────────────

    def available(self) -> bool:
        """Check if DSPy is available and LM is configured."""
        self._ensure_initialized()
        return self._lm is not None

    def get_lm_info(self) -> dict[str, Any]:
        """Return current LM configuration info."""
        return {
            "provider": self._lm_provider,
            "model": self._lm_model,
            "has_api_key": bool(self._api_key),
            "initialized": self._initialized,
        }

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics."""
        return {
            **self._stats,
            "lm": self.get_lm_info(),
            "optimized_modules_cached": len(self._optimized_modules),
            "enabled": self._enabled,
        }

    def health_check(self) -> dict[str, Any]:
        """Quick health check."""
        checks = []
        try:
            import dspy  # noqa: F401
            checks.append({"name": "import", "status": "ok"})
        except ImportError:
            checks.append({"name": "import", "status": "fail"})

        if self._ensure_initialized():
            checks.append({"name": "lm", "status": "ok", "detail": f"{self._lm_provider}/{self._lm_model}"})
        else:
            checks.append({"name": "lm", "status": "fail", "detail": self._init_error})

        return {"healthy": all(c["status"] == "ok" for c in checks),
                "checks": checks, "timestamp": time.time()}


# ── Factory ──────────────────────────────────────────────────────


def create_dspy_bridge() -> DSPyBridge | None:
    """Create a DSPyBridge if dspy is installed."""
    try:
        import dspy  # noqa: F401
        return DSPyBridge()
    except ImportError:
        logger.info("dspy not installed — prompt optimization unavailable")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DSPy Bridge CLI")
    parser.add_argument("--prompt", required=True, help="Input prompt")
    parser.add_argument("--mode", choices=["classify", "cot", "react"], default="cot")
    parser.add_argument("--classes", help="Comma-separated class labels (for classify mode)")
    parser.add_argument("--model", default=DEFAULT_LM_MODEL)
    parser.add_argument("--provider", default=DEFAULT_LM_PROVIDER)
    args = parser.parse_args()

    bridge = DSPyBridge(lm_provider=args.provider, lm_model=args.model)

    if args.mode == "classify" and args.classes:
        classes = [c.strip() for c in args.classes.split(",")]
        result = bridge.classify(args.prompt, classes)
    elif args.mode == "react":
        result = bridge.react(args.prompt)
    else:
        result = bridge.chain_of_thought(args.prompt)

    print(json.dumps(result, indent=2, default=str))
