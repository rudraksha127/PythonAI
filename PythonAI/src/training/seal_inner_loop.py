"""\
SEAL Inner Loop — Synthetic Data Generation + SFT Training (Phase 3)
======================================================================

The inner loop takes a self-edit curriculum action and:
1. Generates synthetic training examples matching the curriculum
2. Augments real signal data from the capture engine
3. Runs SFT (QLoRA via Unsloth or standard Trainer) on the combined data
4. Saves the new adapter for evaluation by the outer loop

The synthetic data generation uses Ollama to create realistic coding
examples that follow the curriculum's domain, difficulty, and focus areas.
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

from src.training.sdft_trainer import (
    ReplayBuffer,
    ReplayBufferConfig,
)
from src.training.sdft_trainer import (
    SDFTTrainer as SDFTBaseTrainer,
)
from src.training.sdft_trainer import (
    TrainingExample as SDFTExample,
)
from src.training.seal_types import (
    SealConfig,
    SelfEditAction,
)

logger = logging.getLogger("forgeai.seal.inner")


# ═══════════════════════════════════════════════════════════════
# Synthetic Data Generation
# ═══════════════════════════════════════════════════════════════

EXAMPLE_GENERATION_PROMPT = """\
Generate a {difficulty} {language} coding example for the domain: {domain}.

Focus areas: {focus_areas}

Format the output as a JSON object with these fields:
- "instruction": Clear instruction for what to code
- "input": Code context or scaffolding (empty string if none needed)
- "output": The complete code solution with type hints and docstrings

Requirements:
{requirements}

Generate exactly 1 example. Make it realistic — this will be used as \
training data for an AI coding assistant."""

DIFFICULTY_REQUIREMENTS = {
    "easy": [
        "- Use standard library only",
        "- Keep the solution under 15 lines",
        "- Focus on one concept",
        "- Include clear variable names",
    ],
    "medium": [
        "- May use common third-party libraries",
        "- Solution should be 15-40 lines",
        "- Combine 2-3 concepts",
        "- Include error handling",
        "- Add type hints where applicable",
    ],
    "hard": [
        "- May use advanced library features",
        "- Solution can be 40-100 lines",
        "- Combine multiple concepts with complex logic",
        "- Include comprehensive error handling",
        "- Consider edge cases and performance",
        "- Add full type hints and docstrings",
        "- Follow production best practices",
    ],
}


class SyntheticExampleGenerator:
    """Generates synthetic training examples using Ollama.

    Each generated example mimics the format from the capture engine
    so it can be used interchangeably with real developer signals.
    """

    def __init__(self, config: SealConfig | None = None):
        self.config = config or SealConfig()
        self._ollama_available = None  # Lazy check

    def check_ollama(self) -> bool:
        """Check if Ollama is available for generation."""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            import ollama
            ollama.list()
            self._ollama_available = True
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    def generate_examples(
        self,
        action: SelfEditAction,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate synthetic training examples matching a curriculum action.

        Args:
            action: The curriculum action describing what to generate.
            count: Number of examples to generate (default: from action).

        Returns:
            List of training examples in SDFT format.
        """
        target_count = count or action.count
        if not self.check_ollama():
            logger.warning("[SEAL] Ollama not available. Using template-based generation.")
            return self._generate_template_examples(action, target_count)

        return self._generate_llm_examples(action, target_count)

    def _generate_llm_examples(
        self,
        action: SelfEditAction,
        count: int,
    ) -> list[dict[str, Any]]:
        """Generate examples via Ollama with the given curriculum."""
        import ollama

        requirements_lines = DIFFICULTY_REQUIREMENTS.get(
            action.difficulty,
            DIFFICULTY_REQUIREMENTS["medium"],
        )
        focus_str = ", ".join(action.focus_areas) if action.focus_areas else "general best practices"

        prompt = EXAMPLE_GENERATION_PROMPT.format(
            difficulty=action.difficulty,
            language=action.language,
            domain=action.domain,
            focus_areas=focus_str,
            requirements="\n".join(requirements_lines),
        )

        examples = []
        batch_size = min(5, count)  # Generate in batches to avoid timeouts

        while len(examples) < count:
            batch_target = min(batch_size, count - len(examples))
            batch_results = []

            for _ in range(batch_target):
                try:
                    response = ollama.generate(
                        model=self.config.inner_synthetic_model,
                        prompt=prompt,
                        options={
                            "temperature": action.temperature,
                            "num_predict": 1024,
                        },
                    )
                    raw = response.get("response", "")
                    parsed = self._parse_generation(raw)
                    if parsed:
                        batch_results.append(parsed)
                except Exception as e:
                    logger.debug(f"[SEAL] Generation error: {e}")
                    continue

            examples.extend(batch_results)

            if len(batch_results) < batch_target:
                # Generation rate is low; wait briefly then continue
                logger.info(f"[SEAL] Generated {len(batch_results)}/{batch_target} in batch"
                            f" ({len(examples)}/{count} total)")
                time.sleep(0.5)

            # Vary the prompt slightly for diversity
            prompt = _vary_prompt(prompt)
            batch_size = min(batch_size + 1, 8)

        logger.info(f"[SEAL] Generated {len(examples)} synthetic examples "
                    f"({action.domain}/{action.difficulty})")
        return examples[:count]

    def _generate_template_examples(
        self,
        action: SelfEditAction,
        count: int,
    ) -> list[dict[str, Any]]:
        """Generate template-based examples when Ollama is unavailable."""
        examples = []
        templates = _get_domain_templates(action.domain, action.language)

        for i in range(min(count, len(templates) * 3)):
            template = random.choice(templates)
            difficulty_tag = f"[{action.difficulty.upper()}]"
            focus_tag = f"[{random.choice(action.focus_areas or ['general']).replace('_', ' ').title()}]"

            example = {
                "instruction": f"{difficulty_tag} {focus_tag} {template['instruction']}",
                "input": template.get("input", ""),
                "output": template.get("output", f"# {template['instruction']}\n# TODO: implement\npass"),
                "source": "seal_synthetic",
                "language": action.language,
                "domain": action.domain,
                "difficulty": action.difficulty,
                "quality_score": 0.7,
            }
            examples.append(example)

        return examples

    def _parse_generation(self, text: str) -> dict[str, Any] | None:
        """Parse a generated example from LLM output.

        Accepts JSON in code blocks or raw JSON.
        """
        import re

        # Try to extract JSON from code blocks
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError:
            return None

        instruction = data.get("instruction", "").strip()
        output = data.get("output", "").strip()
        input_text = data.get("input", "").strip()

        if not instruction or not output:
            return None

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output,
            "source": "seal_synthetic",
            "language": data.get("language", "python"),
            "domain": data.get("domain", "general"),
            "difficulty": data.get("difficulty", "medium"),
            "quality_score": 0.85,  # Synthetic data starts at 0.85
            "timestamp": time.time(),
        }

    def augment_real_signals(
        self,
        real_examples: list[dict[str, Any]],
        augmentation_factor: int = 3,
    ) -> list[dict[str, Any]]:
        """Augment real training signals with synthetic variations.

        Each real example generates N variations using the LLM.
        Falls back to rule-based variations if Ollama is unavailable.
        """
        if not real_examples:
            return []

        augmented = list(real_examples)

        if self.check_ollama():
            logger.info(f"[SEAL] Augmenting {len(real_examples)} real examples "
                        f"(factor={augmentation_factor})...")
            for ex in real_examples[:20]:  # Cap to avoid excessive generation
                variations = self._generate_variations(ex, augmentation_factor)
                augmented.extend(variations)
        else:
            # Rule-based augmentation
            for ex in real_examples:
                for _ in range(min(augmentation_factor, 5)):
                    variation = _rule_based_variation(ex)
                    if variation:
                        augmented.append(variation)

        logger.info(f"[SEAL] Augmented {len(real_examples)} examples → "
                    f"{len(augmented)} total (factor={augmentation_factor})")
        return augmented

    def _generate_variations(
        self,
        example: dict[str, Any],
        count: int,
    ) -> list[dict[str, Any]]:
        """Generate LLM-based variations of a real example."""
        import ollama

        instruction = example.get("instruction", "")
        output = example.get("output", "")

        prompt = f"""\
Generate {count} variations of the following coding example.
Keep the same concept but change the implementation approach, naming, or structure.

Original instruction: {instruction}
Original output: {output}

For each variation, output a JSON object with "instruction", "input", and "output" fields.
Return them as a JSON array."""

        variations = []
        try:
            response = ollama.generate(
                model=self.config.inner_synthetic_model,
                prompt=prompt,
                options={"temperature": 0.8, "num_predict": 2048},
            )
            raw = response.get("response", "")
            parsed = self._parse_variations(raw)
            if parsed:
                for v in parsed:
                    v["source"] = "seal_augmented"
                    v["quality_score"] = 0.75
                    variations.append(v)
        except Exception as e:
            logger.debug(f"[SEAL] Variation generation error: {e}")

        return variations[:count]

    def _parse_variations(self, text: str) -> list[dict[str, Any]]:
        """Parse a JSON array of variations from LLM output."""
        import re  # noqa: F401 — re is used below

        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        try:
            data = json.loads(text.strip())
            if isinstance(data, list):
                return [
                    d for d in data
                    if d.get("instruction") and d.get("output")
                ]
            elif isinstance(data, dict):
                return [data] if data.get("instruction") else []
        except json.JSONDecodeError:
            pass
        return []


# ═══════════════════════════════════════════════════════════════
# Inner Loop Runner
# ═══════════════════════════════════════════════════════════════

class SealInnerLoop:
    """Runs the inner SFT loop: curriculum → data → training → adapter.

    Orchestrates synthetic data generation, real signal augmentation,
    replay buffer mixing, and QLoRA training.
    """

    def __init__(
        self,
        config: SealConfig | None = None,
        capture_engine: Any | None = None,
    ):
        self.config = config or SealConfig()
        self.generator = SyntheticExampleGenerator(config)
        self.capture_engine = capture_engine

        # Replay buffer for SDFT mixing
        replay_config = ReplayBufferConfig(
            current_week_ratio=0.60,
            previous_week_ratio=0.25,
            foundational_ratio=0.15,
            max_replay_size=2000,
            max_foundational_size=500,
        )
        self.replay_buffer = ReplayBuffer(replay_config)

    def execute(
        self,
        action: SelfEditAction,
        cycle: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Execute one inner loop cycle.

        Args:
            action: The curriculum action to execute.
            cycle: The current SEAL cycle number.

        Returns:
            (metrics_dict, generated_examples_list)
        """
        logger.info(f"[SEAL] Inner loop executing: {action.action_type.value} "
                    f"(domain={action.domain}, count={action.count})")

        # Phase 1: Generate synthetic data
        synthetic = self._generate_data(action)

        # Phase 2: Fetch and augment real signals
        real_signals = self._fetch_real_signals()
        if real_signals:
            synthetic = self.generator.augment_real_signals(
                real_signals,
                self.config.synthetic_augmentation_factor,
            )

        # Phase 3: Combine with replay buffer
        combined = self._combine_with_replay(synthetic, real_signals)

        if not combined:
            logger.warning("[SEAL] No training data available. Skipping inner loop.")
            return {"status": "skipped", "reason": "no_data"}, []

        # Phase 4: Run SFT training
        metrics = self._run_training(combined, cycle)

        # Phase 5: Save synthetic data for provenance
        self._save_synthetic_data(synthetic, cycle)

        return metrics, synthetic

    def _generate_data(self, action: SelfEditAction) -> list[dict[str, Any]]:
        """Generate synthetic training data from the curriculum action."""
        logger.info(f"[SEAL] Generating {action.count} examples "
                    f"({action.domain}/{action.difficulty})...")
        return self.generator.generate_examples(action)

    def _fetch_real_signals(self) -> list[dict[str, Any]]:
        """Fetch real training signals from the capture engine.

        Returns examples suitable for SDFT training.
        """
        if self.capture_engine is None:
            return []

        try:
            return self.capture_engine.get_training_data(
                include_accepts=True,
                include_edits=True,
                include_pr_merges=False,  # Too few PR merges typically
            )
        except Exception as e:
            logger.warning(f"[SEAL] Could not fetch real signals: {e}")
            return []

    def _combine_with_replay(
        self,
        synthetic: list[dict[str, Any]],
        real: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Combine synthetic + real data using SDFT replay buffer mixing.

        Composition:
          - 60% synthetic (current curriculum)
          - 25% real signals (from developer feedback)
          - 15% replay buffer (previous runs, foundational)
        """
        # Convert to SDFT TrainingExample objects
        current_examples = []

        # Mark synthetic as "current"
        for ex in synthetic:
            te = SDFTExample(
                instruction=ex.get("instruction", ""),
                input=ex.get("input", ""),
                output=ex.get("output", ""),
                source="current",
                quality_score=ex.get("quality_score", 0.85),
                timestamp=time.time(),
                language=ex.get("language", "python"),
            )
            current_examples.append(te)

        # Mark real signals as "current" too (they'll go into the mix)
        for ex in real:
            te = SDFTExample(
                instruction=ex.get("instruction", ""),
                input=ex.get("input", ""),
                output=ex.get("output", ""),
                source="current",
                quality_score=ex.get("quality_score", 0.95),  # Real data = higher quality
                timestamp=time.time(),
                language=ex.get("language", "python"),
            )
            current_examples.append(te)

        # Use SDFT's replay buffer for mixing
        mixed = self.replay_buffer.create_mixed_dataset(current_examples)

        logger.info(f"[SEAL] Combined dataset: {len(mixed)} examples "
                    f"({len(synthetic)} synthetic + {len(real)} real "
                    f"+ replay buffer)")
        return mixed

    def _run_training(
        self,
        examples: list[SDFTExample],
        cycle: int,
    ) -> dict[str, Any]:
        """Run SFT training using SDFT trainer.

        Uses the existing SDFTTrainer infrastructure with Unsloth
        acceleration when available.
        """
        output_dir = Path(self.config.adapter_dir) / f"cycle_{cycle:03d}"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            trainer = SDFTBaseTrainer(
                model_name=self.config.inner_model,
                lora_rank=self.config.inner_lora_rank,
                learning_rate=self.config.inner_learning_rate,
                max_length=self.config.inner_max_length,
            )

            metrics = trainer.train(
                current_examples=examples,
                output_dir=str(output_dir),
                num_epochs=1,
                batch_size=self.config.inner_batch_size,
                gradient_accumulation_steps=4,
                use_4bit=True,
            )

            # Save adapter path in metrics
            metrics["adapter_path"] = str(output_dir)
            metrics["cycle"] = cycle
            metrics["examples_trained"] = len(examples)

            logger.info(f"[SEAL] Inner loop training complete: "
                        f"train_loss={metrics.get('train_loss', 'N/A'):.4f}, "
                        f"eval_loss={metrics.get('eval_loss', 'N/A'):.4f}, "
                        f"steps={metrics.get('total_steps', 0)}")
            return metrics

        except ImportError as e:
            logger.error(f"[SEAL] Training dependencies not available: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "cycle": cycle,
                "adapter_path": None,
            }
        except Exception as e:
            logger.error(f"[SEAL] Training failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "cycle": cycle,
                "adapter_path": None,
            }

    def _save_synthetic_data(
        self,
        examples: list[dict[str, Any]],
        cycle: int,
    ) -> str:
        """Save generated synthetic data for inspection and audit."""
        data_dir = Path(self.config.synthetic_data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        output_path = data_dir / f"cycle_{cycle:03d}_synthetic.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

        logger.info(f"[SEAL] Synthetic data saved: {output_path} "
                    f"({len(examples)} examples)")
        return str(output_path)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _vary_prompt(prompt: str) -> str:
    """Slightly vary the generation prompt for diversity."""
    variations = [
        "\n\nMake the solution production-ready with proper error handling.",
        "\n\nAdd comments explaining the key decisions in the code.",
        "\n\nWrite a solution that prioritizes readability and maintainability.",
        "\n\nFocus on performance: make the solution efficient.",
        "\n\nInclude test cases at the end of the solution.",
    ]
    return prompt + random.choice(variations)


def _rule_based_variation(example: dict[str, Any]) -> dict[str, Any] | None:
    """Create a simple rule-based variation of an example.

    Used when Ollama is not available for LLM-based augmentation.
    """
    import re  # noqa: F401 — re is used below

    instruction = example.get("instruction", "")
    output = example.get("output", "")

    if not instruction or not output:
        return None

    # Simple substitutions for variety
    substitution_pairs = [
        ("function", "def"),
        ("calculate", "compute"),
        ("process", "handle"),
        ("validate", "check"),
        ("transform", "convert"),
        ("extract", "parse"),
    ]

    for old, new in random.sample(substitution_pairs, min(2, len(substitution_pairs))):
        if old in instruction.lower():
            instruction = re.sub(old, new, instruction, flags=re.I)
            break

    return {
        "instruction": instruction + " (alternative approach)",
        "input": example.get("input", ""),
        "output": output,
        "source": "seal_augmented",
        "language": example.get("language", "python"),
        "domain": example.get("domain", "general"),
        "quality_score": 0.7,
    }


def _get_domain_templates(domain: str, language: str) -> list[dict[str, str]]:
    """Get instruction templates for a given domain.

    Provides fallback content when Ollama is unavailable.
    """
    templates: dict[str, list[dict[str, str]]] = {
        "general": [
            {"instruction": f"Write a {language} function that processes a list of items and returns a summary", "input": ""},
            {"instruction": f"Create a {language} class for managing configuration settings", "input": ""},
            {"instruction": f"Implement a utility function in {language} for file reading with error handling", "input": ""},
        ],
        "error_handling": [
            {"instruction": f"Write a {language} function with comprehensive error handling for network requests", "input": ""},
            {"instruction": f"Create a custom exception hierarchy in {language} for a library", "input": ""},
            {"instruction": f"Implement retry logic with exponential backoff in {language}", "input": ""},
        ],
        "async_programming": [
            {"instruction": f"Write an async {language} function that fetches data from multiple sources", "input": ""},
            {"instruction": f"Create an async context manager in {language} for database connections", "input": ""},
            {"instruction": f"Implement async rate limiting in {language}", "input": ""},
        ],
        "type_safety": [
            {"instruction": f"Write a type-safe {language} function using generics", "input": ""},
            {"instruction": f"Create a type-annotated {language} class for a data model", "input": ""},
        ],
        "testing": [
            {"instruction": f"Write unit tests in {language} for a data processing function", "input": ""},
            {"instruction": f"Create integration tests in {language} for an API endpoint", "input": ""},
        ],
        "performance": [
            {"instruction": f"Optimize this {language} function for better performance", "input": "def slow_function(items):\n    result = []\n    for i in items:\n        for j in items:\n            result.append(i * j)\n    return result"},
            {"instruction": f"Write a memory-efficient {language} generator for large datasets", "input": ""},
        ],
    }

    return templates.get(domain, templates["general"])
