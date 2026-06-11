"""\
SEAL Curriculum Generator — Self-Edit Instruction Producer (Phase 3)
======================================================================

The model generates its own curriculum by producing structured JSON
instructions (self-edit actions) that describe what to train on next.

This module is the "brain" of SEAL — it decides what the model should
learn next based on its current state and performance history.

Architecture:
  1. Run state analysis → identify weaknesses, gaps, opportunities
  2. Generate self-edit action via Ollama with curriculum prompt
  3. Parse the response into a SelfEditAction
  4. Optionally explore random actions for better coverage
"""

from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any, Optional

from src.training.seal_types import (
    CurriculumState,
    SealActionType,
    SealConfig,
    SelfEditAction,
)

logger = logging.getLogger("forgeai.seal.curriculum")


# ═══════════════════════════════════════════════════════════════
# Curriculum Prompt Templates
# ═══════════════════════════════════════════════════════════════

SELF_EDIT_SYSTEM_PROMPT = """\
You are the **Self-Improvement Controller** for ForgeAI, an autonomous \
coding assistant that continuously improves by fine-tuning on developer feedback.

Your job is to decide what the model should learn next. You generate a \
structured JSON "self-edit instruction" that tells the training pipeline \
what kind of synthetic training data to generate.

**Available actions:**
| Action | Purpose |
|--------|---------|
| `generate_examples` | Generate N synthetic examples in a specific domain |
| `focus_domain` | Train specifically on an underrepresented domain |
| `increase_difficulty` | Generate harder examples (more edge cases, complex logic) |
| `reinforce_weakness` | Target areas where the model performs worst |
| `balance_languages` | Generate examples in underrepresented coding languages |
| `reduce_hallucination` | Generate examples testing factual grounding |

**Rules:**
1. Vary your actions — avoid repeating the same type every time
2. Explore new domains before exploiting known good ones
3. If acceptance rate is improving, continue the current strategy
4. If acceptance rate is flat/decreasing, try something different
5. Balance difficulty: include some easy wins with harder challenges

**Output format:** Return ONLY a valid JSON object in a code block:
```json
{
  "action": "generate_examples",
  "domain": "error_handling",
  "count": 25,
  "difficulty": "medium",
  "language": "python",
  "focus_areas": ["type_hints", "edge_cases"],
  "rationale": "Error handling is a common weakness — more examples will improve robustness",
  "temperature": 0.7
}
```"""


def _build_state_summary(state: CurriculumState) -> str:
    """Build a concise summary of the current curriculum state for the prompt."""
    lines = ["=== Current Curriculum State ==="]

    if state.cycle_number > 0:
        lines.append(f"Cycle: {state.cycle_number} | Total actions: {state.total_actions_taken}")

        # Recent acceptance rate history
        if state.acceptance_rate_history:
            recent = state.acceptance_rate_history[-3:]
            lines.append("Recent acceptance rates:")
            for r in recent:
                delta = r.get("delta", 0)
                direction = "↑" if delta >= 0 else "↓"
                lines.append(f"  Cycle {r.get('cycle', '?')}: {r.get('rate', 0)*100:.1f}% ({direction}{delta*100:+.1f}%)")

        # Domains explored
        if state.domains_explored:
            explored = sorted(state.domains_explored.items(), key=lambda x: -x[1])
            lines.append("Domains explored:")
            for domain, count in explored[:5]:
                lines.append(f"  {domain}: {count}x")

        # Action effectiveness
        if state.action_effectiveness:
            lines.append("Action effectiveness (avg reward delta):")
            for action_type, deltas in sorted(
                state.action_effectiveness.items(),
                key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0,
                reverse=True,
            ):
                if deltas:
                    avg = sum(deltas) / len(deltas)
                    lines.append(f"  {action_type}: {avg:+.3f} (from {len(deltas)} uses)")

        # Best action
        if state.best_action:
            lines.append(f"Best action so far: {state.best_action.get('action', '?')} "
                         f"(reward: {state.best_action.get('reward_delta', 0):+.3f})")

        # Weakness scores
        if state.weakness_scores:
            weaknesses = sorted(state.weakness_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            lines.append("Top weaknesses:")
            for area, score in weaknesses:
                lines.append(f"  {area}: {score:.2f}")

    else:
        lines.append("This is the FIRST cycle. Start by generating a diverse set of examples "
                     "across common coding patterns to establish a baseline.")

    # Underrepresented domains
    underrepresented = state.get_underrepresented_domains(threshold=2)
    if underrepresented:
        lines.append(f"Under-explored domains: {', '.join(underrepresented)}")

    return "\n".join(lines)


def _build_curriculum_prompt(state: CurriculumState) -> str:
    """Build the full prompt for the curriculum generator."""
    state_summary = _build_state_summary(state)

    return f"""\
You are deciding what the model should learn next in its autonomous training cycle.

Current state of the model's training curriculum:
{state_summary}

Based on this state, generate a self-edit instruction that will produce \
the most value for the next training cycle. Consider:
- What domains need more coverage?
- Is the current difficulty appropriate?
- Which action types have been most effective?
- What would create the best improvement in acceptance rate?

Return ONLY a valid JSON object in a code block."""


# ═══════════════════════════════════════════════════════════════
# Curriculum Generator
# ═══════════════════════════════════════════════════════════════

class CurriculumGenerator:
    """Generates self-edit instructions for the SEAL inner loop.

    This is a meta-cognitive layer: the model reflects on its own
    performance and decides what to study next.
    """

    # Module-level constant made available as a class attribute
    # so `self.SELF_EDIT_SYSTEM_PROMPT` resolves correctly
    SELF_EDIT_SYSTEM_PROMPT = SELF_EDIT_SYSTEM_PROMPT

    def __init__(
        self,
        config: Optional[SealConfig] = None,
        state: Optional[CurriculumState] = None,
    ):
        self.config = config or SealConfig()
        self.state = state or CurriculumState()

    def generate_action(self) -> SelfEditAction:
        """Generate the next curriculum action.

        With probability exploration_rate, picks a random action
        to explore. Otherwise, generates an informed action via
        the LLM curriculum generator.
        """

        # Exploration: try something random
        if random.random() < self.config.exploration_rate:
            action = self._generate_random_action()
            logger.info(f"[SEAL] Exploring random action: {action.action_type.value} "
                        f"(domain={action.domain}, count={action.count})")
            return action

        # Exploitation: use LLM-informed decision
        action = self._generate_llm_action()
        if action is None:
            # Fallback to random on failure
            action = self._generate_random_action()
            logger.info(f"[SEAL] LLM generation failed, using random fallback: "
                        f"{action.action_type.value}")

        logger.info(f"[SEAL] Curriculum action: {action.action_type.value} "
                    f"(domain={action.domain}, count={action.count}, "
                    f"difficulty={action.difficulty})")
        return action

    def _generate_llm_action(self) -> Optional[SelfEditAction]:
        """Generate a curriculum action using an LLM via Ollama."""
        try:
            import ollama

            prompt = _build_curriculum_prompt(self.state)
            response = ollama.generate(
                model=self.config.curriculum_model,
                prompt=prompt,
                system=self.SELF_EDIT_SYSTEM_PROMPT,
                options={
                    "temperature": self.config.curriculum_temperature,
                    "num_predict": 512,
                },
            )

            raw = response.get("response", "")
            logger.debug(f"[SEAL] Raw curriculum response: {raw[:200]}...")

            return SelfEditAction.from_json(raw)

        except ImportError:
            logger.warning("[SEAL] Ollama not installed. Using random action.")
            return None
        except Exception as e:
            logger.error(f"[SEAL] LLM curriculum generation error: {e}")
            return None

    def _generate_random_action(self) -> SelfEditAction:
        """Generate a random curriculum action for exploration."""
        action_types = list(SealActionType)
        difficulties = ["easy", "medium", "hard"]
        domains = [
            "general", "error_handling", "async_programming",
            "type_safety", "performance", "security",
            "testing", "api_design", "data_structures",
            "concurrency", "debugging", "refactoring",
        ]

        # Weight towards underrepresented domains
        if self.state.domains_explored:
            underrepresented = self.state.get_underrepresented_domains(threshold=1)
            if underrepresented:
                # Prefer a domain from underrepresented
                domain = random.choice(underrepresented).split("/")[0]
            else:
                domain = random.choice(domains)
        else:
            domain = random.choice(domains)

        # Effective count based on config
        count = max(10, self.config.synthetic_examples_per_action +
                    random.randint(-10, 20))

        return SelfEditAction(
            action_type=random.choice(action_types),
            domain=domain,
            count=count,
            difficulty=random.choice(difficulties),
            language=random.choice(["python", "typescript", "python"]),
            focus_areas=random.sample(
                ["type_hints", "edge_cases", "error_handling",
                 "documentation", "testing", "performance"],
                k=random.randint(1, 3),
            ),
            rationale="Random exploration to discover effective training strategies",
            temperature=random.uniform(0.5, 0.9),
        )

    def update_state(self, reward: Any) -> None:
        """Update the curriculum state with a reward record."""
        from src.training.seal_types import RewardRecord

        if hasattr(reward, "to_dict"):
            record = reward
        else:
            return

        self.state.cycle_number = record.cycle
        self.state.record_action(record.action, record.reward_delta)

        # Update acceptance rate history
        self.state.acceptance_rate_history.append({
            "cycle": record.cycle,
            "rate": record.acceptance_rate_after,
            "delta": record.reward_delta,
            "timestamp": record.timestamp,
        })

        # Update weakness scores based on degradation
        if record.reward_delta < -0.02:
            domain = record.action.domain
            current = self.state.weakness_scores.get(domain, 0.5)
            self.state.weakness_scores[domain] = min(1.0, current + abs(record.reward_delta))

        # Reduce weakness scores for improvements
        if record.reward_delta > 0.02:
            domain = record.action.domain
            current = self.state.weakness_scores.get(domain, 0.5)
            self.state.weakness_scores[domain] = max(0.0, current - record.reward_delta)

        logger.info(f"[SEAL] State updated: cycle={self.state.cycle_number}, "
                    f"actions={self.state.total_actions_taken}, "
                    f"domains explored={len(self.state.domains_explored)}")

    def save_state(self, state_dir: Optional[str] = None) -> str:
        """Persist the curriculum state to disk."""
        path = Path(state_dir or self.config.state_dir)
        path.mkdir(parents=True, exist_ok=True)

        state_file = path / "curriculum_state.json"
        state_file.write_text(
            json.dumps(self.state.to_dict(), indent=2),
            encoding="utf-8",
        )
        logger.info(f"[SEAL] Curriculum state saved: {state_file}")
        return str(state_file)

    def load_state(self, state_dir: Optional[str] = None) -> bool:
        """Load curriculum state from disk. Returns True on success."""
        path = Path(state_dir or self.config.state_dir)
        state_file = path / "curriculum_state.json"

        if not state_file.exists():
            return False

        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            self.state = CurriculumState.from_dict(data)
            logger.info(f"[SEAL] Curriculum state loaded: cycle={self.state.cycle_number}")
            return True
        except Exception as e:
            logger.warning(f"[SEAL] Failed to load curriculum state: {e}")
            return False
