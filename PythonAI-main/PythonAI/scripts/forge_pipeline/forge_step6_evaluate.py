"""
forge_step6_evaluate.py — PHASE 6: MODEL EVALUATION
====================================================
Test the trained model on multiple benchmark categories.
Calculates accuracy scores and generates detailed evaluation report.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import torch
from loguru import logger
from rich.console import Console
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from forge_config import ForgeConfig

try:
    from peft import PeftModel

    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False

console = Console()

# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARKS — Test categories with prompt → expected keyword(s)
# ═══════════════════════════════════════════════════════════════════════════

BENCHMARKS = {
    "general_knowledge": [
        {"q": "What is the capital of India?", "check": ["delhi", "new delhi"]},
        {"q": "Who wrote the Indian Constitution?", "check": ["ambedkar", "bhimrao"]},
        {"q": "What is photosynthesis?", "check": ["chlorophyll", "light", "energy"]},
        {"q": "What does CPU stand for?", "check": ["central processing unit"]},
        {"q": "What is Newton's first law of motion?", "check": ["inertia"]},
        {"q": "What is the chemical symbol for water?", "check": ["h2o", "h₂o"]},
        {"q": "What planet is known as the Red Planet?", "check": ["mars"]},
        {"q": "What is the largest ocean on Earth?", "check": ["pacific"]},
        {"q": "What is the boiling point of water in Celsius?", "check": ["100"]},
        {"q": "Who developed the theory of relativity?", "check": ["einstein"]},
    ],
    "coding": [
        {"q": "Write a Python function to check if a number is prime.", "check": ["def", "return"]},
        {"q": "What does the 'def' keyword mean in Python?", "check": ["function", "define"]},
        {"q": "Write SQL to select all rows from a table named 'users'.", "check": ["select", "from users"]},
        {"q": "What is a list comprehension in Python?", "check": ["syntax", "expression", "list"]},
        {"q": "What does HTML stand for?", "check": ["hypertext markup language"]},
    ],
    "hindi": [
        {"q": "भारत की राजधानी क्या है?", "check": ["दिल्ली", "नई दिल्ली"]},
        {"q": "1+1 कितना होता है?", "check": ["2", "दो"]},
        {"q": "Python क्या है?", "check": ["programming", "भाषा", "कंप्यूटर"]},
        {"q": "सूर्य क्या है?", "check": ["तारा", "star"]},
        {"q": "जल का रासायनिक सूत्र क्या है?", "check": ["h2o", "h₂o"]},
    ],
    "reasoning": [
        {"q": "If I have 5 apples and give 2 away, how many do I have left?", "check": ["3", "three"]},
        {"q": "What comes next: 2, 4, 8, 16, ?", "check": ["32"]},
        {
            "q": "A train leaves at 3 PM and travels for 2 hours. What time does it arrive?",
            "check": ["5", "5 pm", "5pm"],
        },
        {"q": "What is the next number: 1, 1, 2, 3, 5, 8, ?", "check": ["13"]},
        {"q": "If all cats are mammals, and all mammals are animals, are all cats animals?", "check": ["yes", "true"]},
    ],
    "india_specific": [
        {"q": "What is PM-KISAN scheme?", "check": ["farmer", "kisan", "income"]},
        {"q": "What is Ayushman Bharat?", "check": ["health", "insurance", "ayushman"]},
        {"q": "What is GST in India?", "check": ["tax", "goods and services"]},
        {"q": "What is the currency of India?", "check": ["rupee", "inr"]},
        {"q": "What is the national animal of India?", "check": ["tiger", "bengal tiger"]},
    ],
}


class ForgeEvaluator:
    """Evaluate trained model on multiple benchmark categories."""

    def __init__(self, cfg: ForgeConfig):
        self.cfg = cfg
        self.pipe = None

    def load_model(self) -> bool:
        """Load the trained model for evaluation."""
        model_dir = Path(self.cfg.final_model_dir)
        if not model_dir.exists() or not list(model_dir.glob("*.safetensors")) and not list(model_dir.glob("*.bin")):
            logger.error(f"Trained model not found in {model_dir}")
            return False

        logger.info(f"Loading trained model from {model_dir}...")

        try:
            tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Try loading with PEFT adapter first
            if HAS_PEFT:
                try:
                    base = AutoModelForCausalLM.from_pretrained(
                        self.cfg.base_model,
                        device_map="auto",
                        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                        token=self.cfg.hf_token or None,
                    )
                    model = PeftModel.from_pretrained(base, str(model_dir))
                    logger.info("Loaded as PEFT model with adapter")
                except Exception:
                    model = AutoModelForCausalLM.from_pretrained(
                        str(model_dir),
                        device_map="auto",
                        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    )
                    logger.info("Loaded as standalone model")
            else:
                model = AutoModelForCausalLM.from_pretrained(
                    str(model_dir),
                    device_map="auto",
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                )

            model.eval()

            self.pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                device_map="auto",
                max_new_tokens=128,
                do_sample=True,
                temperature=0.7,
                pad_token_id=tokenizer.pad_token_id,
            )
            logger.success("Model loaded for evaluation")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def run_benchmarks(self) -> dict:
        """Run all benchmark categories and calculate scores."""
        if not self.pipe:
            return {}

        all_results = {}

        for category, tests in BENCHMARKS.items():
            correct = 0
            category_results = []

            for test in tests:
                prompt = test["q"]
                checks = test["check"]

                start = time.time()
                try:
                    output = self.pipe(prompt, return_full_text=False)[0]["generated_text"]
                except Exception as e:
                    output = f"ERROR: {e}"
                latency = time.time() - start

                output_lower = output.lower()
                passed = any(check.lower() in output_lower for check in checks)

                if passed:
                    correct += 1

                category_results.append(
                    {
                        "question": prompt,
                        "output": output[:200],
                        "passed": passed,
                        "latency_ms": round(latency * 1000),
                    }
                )

            accuracy = correct / len(tests) * 100
            all_results[category] = {
                "accuracy": round(accuracy, 1),
                "correct": correct,
                "total": len(tests),
                "tests": category_results,
            }

            status = "[OK]" if accuracy >= 60 else "[WARN]" if accuracy >= 40 else "[FAIL]"
            logger.info(f"  {status} {category}: {accuracy:.0f}% ({correct}/{len(tests)})")

        # Overall score
        total_correct = sum(r["correct"] for r in all_results.values())
        total_tests = sum(r["total"] for r in all_results.values())
        overall = total_correct / total_tests * 100 if total_tests > 0 else 0

        all_results["overall"] = {
            "accuracy": round(overall, 1),
            "correct": total_correct,
            "total": total_tests,
        }

        return all_results

    def run(self) -> float:
        """Full evaluation pipeline."""
        console.print("\n[bold cyan]═══ PHASE 6: MODEL EVALUATION ═══[/bold cyan]")

        if not self.load_model():
            return 0.0

        results = self.run_benchmarks()

        if not results:
            console.print("[red]No evaluation results generated.[/red]")
            return 0.0

        overall = results.get("overall", {})
        console.print(f"\n{'=' * 50}")
        console.print(
            f"[bold]OVERALL SCORE: {overall.get('accuracy', 0):.1f}% "
            f"({overall.get('correct', 0)}/{overall.get('total', 0)})[/bold]"
        )
        console.print(f"{'=' * 50}")

        # Save results
        results_file = Path(self.cfg.final_model_dir) / "evaluation_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "overall_accuracy": overall.get("accuracy", 0),
                    "categories": {k: v for k, v in results.items() if k != "overall"},
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.success(f"Results saved: {results_file}")

        return overall.get("accuracy", 0)


def run_evaluation(cfg: ForgeConfig) -> float:
    """Entry point for evaluation."""
    evaluator = ForgeEvaluator(cfg)
    score = evaluator.run()
    print(f"\n[OK] Evaluation: {score:.1f}% accuracy")
    print("Run: python forge_step7_deploy.py")
    return score


if __name__ == "__main__":
    cfg = ForgeConfig.load()
    run_evaluation(cfg)
