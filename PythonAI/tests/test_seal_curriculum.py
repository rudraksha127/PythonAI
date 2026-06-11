"""Tests for the SEAL curriculum generator.

Covers CurriculumGenerator action generation, state management,
and random action exploration.
"""

from __future__ import annotations

from src.training.seal_types import (
    CurriculumState,
    SealActionType,
    SealConfig,
    SelfEditAction,
)
from src.training.seal_curriculum import CurriculumGenerator


class TestCurriculumGenerator:
    def test_init(self):
        gen = CurriculumGenerator()
        assert gen.config is not None
        assert gen.state is not None
        assert gen.state.cycle_number == 0

    def test_init_with_state(self):
        state = CurriculumState(cycle_number=5)
        gen = CurriculumGenerator(state=state)
        assert gen.state.cycle_number == 5

    def test_generate_random_action(self):
        gen = CurriculumGenerator()
        # Override exploration rate to 1.0 to force random
        gen.config.exploration_rate = 1.0
        action = gen.generate_action()
        assert isinstance(action, SelfEditAction)
        assert action.action_type in list(SealActionType)
        assert action.domain in [
            "general", "error_handling", "async_programming",
            "type_safety", "performance", "security",
            "testing", "api_design", "data_structures",
            "concurrency", "debugging", "refactoring",
        ]
        assert action.difficulty in ["easy", "medium", "hard"]
        assert action.count >= 10
        assert action.language in ["python", "typescript"]

    def test_generate_random_action_explores_underrepresented(self):
        state = CurriculumState()
        state.domains_explored = {"general/easy": 0, "unknown_domain/medium": 0}
        gen = CurriculumGenerator(state=state)
        gen.config.exploration_rate = 1.0
        action = gen.generate_action()
        assert isinstance(action, SelfEditAction)

    def test_random_action_has_focus_areas(self):
        gen = CurriculumGenerator()
        gen.config.exploration_rate = 1.0
        action = gen.generate_action()
        assert len(action.focus_areas) >= 1
        assert action.rationale != ""

    def test_update_state(self):
        gen = CurriculumGenerator()
        mock_action = SelfEditAction(
            action_type=SealActionType.GENERATE_EXAMPLES,
            domain="test_domain",
        )

        class MockReward:
            cycle = 1
            action = mock_action
            reward_delta = 0.15
            acceptance_rate_after = 0.65
            timestamp = 1000.0
            def to_dict(self):
                return {}

        gen.update_state(MockReward())

        assert gen.state.cycle_number == 1
        assert gen.state.total_actions_taken == 1
        assert "test_domain/medium" in gen.state.domains_explored

    def test_update_state_with_degradation_increases_weakness(self):
        gen = CurriculumGenerator()

        class MockBadReward:
            cycle = 1
            action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="weak_area")
            reward_delta = -0.05
            acceptance_rate_after = 0.3
            timestamp = 1000.0
            def to_dict(self):
                return {}

        gen.update_state(MockBadReward())
        # Weakness score should increase for "weak_area"
        score = gen.state.weakness_scores.get("weak_area", 0)
        assert score > 0.5, f"Expected > 0.5, got {score}"

    def test_save_and_load_state(self, tmp_path):
        gen = CurriculumGenerator()
        gen.state.cycle_number = 7
        gen.state.total_actions_taken = 10

        # Save to temp dir
        saved_path = gen.save_state(str(tmp_path))

        # Create new generator and load
        gen2 = CurriculumGenerator()
        loaded = gen2.load_state(str(tmp_path))
        assert loaded is True
        assert gen2.state.cycle_number == 7
        assert gen2.state.total_actions_taken == 10

    def test_save_and_load_empty_state(self, tmp_path):
        gen = CurriculumGenerator()
        loaded = gen.load_state(str(tmp_path))
        assert loaded is False  # No state file exists

    def test_build_state_summary_first_cycle(self):
        from src.training.seal_curriculum import _build_state_summary
        state = CurriculumState()
        summary = _build_state_summary(state)
        assert "FIRST cycle" in summary

    def test_build_state_summary_with_history(self):
        from src.training.seal_curriculum import _build_state_summary
        state = CurriculumState()
        state.cycle_number = 3
        state.total_actions_taken = 5
        state.acceptance_rate_history = [
            {"cycle": 1, "rate": 0.3, "delta": 0.0},
            {"cycle": 2, "rate": 0.5, "delta": 0.2},
            {"cycle": 3, "rate": 0.55, "delta": 0.05},
        ]
        state.action_effectiveness = {
            "generate_examples": [0.2, 0.1],
            "focus_domain": [0.5],
        }
        summary = _build_state_summary(state)
        assert "Cycle: 3" in summary
        assert "generate_examples" in summary
        assert "focus_domain" in summary

    def test_self_edit_system_prompt_available(self):
        assert CurriculumGenerator.SELF_EDIT_SYSTEM_PROMPT is not None
        assert "Self-Improvement Controller" in CurriculumGenerator.SELF_EDIT_SYSTEM_PROMPT
        assert "generate_examples" in CurriculumGenerator.SELF_EDIT_SYSTEM_PROMPT
