"""Tests for the SEAL Phase 3 type system.

Covers SelfEditAction, CurriculumState, RewardRecord, and SealConfig.
"""

from __future__ import annotations

from src.training.seal_types import (
    CurriculumState,
    RewardRecord,
    SealActionType,
    SealConfig,
    SelfEditAction,
)


class TestSelfEditAction:
    def test_create_default(self):
        action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES)
        assert action.action_type == SealActionType.GENERATE_EXAMPLES
        assert action.domain == "general"
        assert action.count == 20
        assert action.difficulty == "medium"
        assert action.language == "python"

    def test_to_dict_roundtrip(self):
        action = SelfEditAction(
            action_type=SealActionType.FOCUS_DOMAIN,
            domain="error_handling",
            count=15,
            difficulty="hard",
            language="typescript",
            focus_areas=["type_hints", "edge_cases"],
            rationale="Need more error handling examples",
        )
        d = action.to_dict()
        assert d["action"] == "focus_domain"
        assert d["domain"] == "error_handling"
        assert d["count"] == 15
        assert d["difficulty"] == "hard"
        assert d["language"] == "typescript"
        assert "type_hints" in d["focus_areas"]

    def test_to_json_roundtrip(self):
        action = SelfEditAction(
            action_type=SealActionType.INCREASE_DIFFICULTY,
            domain="async",
            count=30,
        )
        json_str = action.to_json()
        parsed = SelfEditAction.from_json(json_str)
        assert parsed is not None
        assert parsed.action_type == SealActionType.INCREASE_DIFFICULTY
        assert parsed.domain == "async"
        assert parsed.count == 30

    def test_from_json_code_block(self):
        json_str = '''```json\n{"action": "reduce_hallucination", "domain": "reasoning", "count": 25}\n```'''
        action = SelfEditAction.from_json(json_str)
        assert action is not None
        assert action.action_type == SealActionType.REDUCE_HALLUCINATION
        assert action.domain == "reasoning"
        assert action.count == 25

    def test_from_json_invalid_returns_none(self):
        action = SelfEditAction.from_json("not json at all")
        assert action is None

    def test_from_json_invalid_action_falls_back(self):
        json_str = '{"action": "unknown_action", "domain": "test"}'
        action = SelfEditAction.from_json(json_str)
        assert action is not None
        assert action.action_type == SealActionType.GENERATE_EXAMPLES  # fallback

    def test_all_action_types_present(self):
        types = list(SealActionType)
        expected = [
            "generate_examples",
            "focus_domain",
            "increase_difficulty",
            "reinforce_weakness",
            "balance_languages",
            "reduce_hallucination",
        ]
        assert sorted(t.value for t in types) == sorted(expected)


class TestCurriculumState:
    def test_default_state(self):
        state = CurriculumState()
        assert state.cycle_number == 0
        assert state.total_actions_taken == 0
        assert state.domains_explored == {}
        assert state.difficulties_tried == {}
        assert state.weakness_scores == {}
        assert state.acceptance_rate_history == []
        assert state.action_effectiveness == {}
        assert state.best_action is None

    def test_record_action_tracks_domains_and_difficulties(self):
        state = CurriculumState()
        action = SelfEditAction(
            action_type=SealActionType.GENERATE_EXAMPLES,
            domain="error_handling",
            difficulty="hard",
        )
        state.record_action(action, reward_delta=0.1)
        assert state.total_actions_taken == 1
        assert "error_handling/hard" in state.domains_explored
        assert state.domains_explored["error_handling/hard"] == 1
        assert state.difficulties_tried["hard"] == 1

    def test_record_action_tracks_effectiveness(self):
        state = CurriculumState()
        a1 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="a")
        a2 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="b")
        a3 = SelfEditAction(action_type=SealActionType.FOCUS_DOMAIN, domain="c")

        state.record_action(a1, reward_delta=0.2)
        state.record_action(a2, reward_delta=0.3)
        state.record_action(a3, reward_delta=0.5)

        assert "generate_examples" in state.action_effectiveness
        assert "focus_domain" in state.action_effectiveness
        assert state.action_effectiveness["generate_examples"] == [0.2, 0.3]
        assert state.action_effectiveness["focus_domain"] == [0.5]

    def test_record_action_tracks_best(self):
        state = CurriculumState()
        a1 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="a")
        a2 = SelfEditAction(action_type=SealActionType.FOCUS_DOMAIN, domain="b")

        state.record_action(a1, reward_delta=0.1)
        assert state.best_action is not None
        assert state.best_action["reward_delta"] == 0.1

        state.record_action(a2, reward_delta=0.5)
        assert state.best_action["reward_delta"] == 0.5
        assert state.best_action["action"] == "focus_domain"

    def test_get_best_action_type(self):
        state = CurriculumState()
        a1 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="a")
        a2 = SelfEditAction(action_type=SealActionType.FOCUS_DOMAIN, domain="b")
        state.record_action(a1, reward_delta=0.1)
        state.record_action(a2, reward_delta=0.9)
        assert state.get_best_action_type() == "focus_domain"

    def test_get_best_action_type_empty(self):
        state = CurriculumState()
        assert state.get_best_action_type() is None

    def test_get_underrepresented_domains(self):
        state = CurriculumState()
        a1 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="a")
        a2 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="b")
        a3 = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="a")
        state.record_action(a1, 0.1)
        state.record_action(a2, 0.1)
        state.record_action(a3, 0.1)
        under = state.get_underrepresented_domains(threshold=2)
        assert "b/medium" in under
        assert "a/medium" not in under

    def test_to_dict_roundtrip(self):
        state = CurriculumState()
        action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES, domain="test")
        state.record_action(action, reward_delta=0.5)
        state.cycle_number = 3
        state.acceptance_rate_history.append({"cycle": 1, "rate": 0.5, "delta": 0.1})

        d = state.to_dict()
        assert d["cycle_number"] == 3
        assert d["total_actions_taken"] == 1
        assert len(d["acceptance_rate_history"]) == 1

        restored = CurriculumState.from_dict(d)
        assert restored.cycle_number == 3
        assert restored.total_actions_taken == 1
        assert len(restored.acceptance_rate_history) == 1


class TestRewardRecord:
    def test_default_reward(self):
        action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES)
        record = RewardRecord(
            cycle=1,
            action=action,
            acceptance_rate_before=0.5,
            acceptance_rate_after=0.7,
        )
        assert record.cycle == 1
        assert record.acceptance_rate_before == 0.5
        assert record.acceptance_rate_after == 0.7
        assert abs(record.reward_delta - 0.2) < 1e-10
        assert record.is_improvement()
        assert record.examples_generated == 0

    def test_no_improvement(self):
        action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES)
        record = RewardRecord(
            cycle=1,
            action=action,
            acceptance_rate_before=0.7,
            acceptance_rate_after=0.5,
        )
        assert abs(record.reward_delta - (-0.2)) < 1e-10
        assert not record.is_improvement()

    def test_improvement_direction(self):
        action = SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES)
        r1 = RewardRecord(cycle=1, action=action, acceptance_rate_before=0.3, acceptance_rate_after=0.9)
        assert "strong_improvement" in r1.improvement_direction

        r2 = RewardRecord(cycle=2, action=action, acceptance_rate_before=0.5, acceptance_rate_after=0.52)
        assert "improvement" in r2.improvement_direction
        assert "strong" not in r2.improvement_direction

        r3 = RewardRecord(cycle=3, action=action, acceptance_rate_before=0.7, acceptance_rate_after=0.68)
        assert "slight_degradation" in r3.improvement_direction

        r4 = RewardRecord(cycle=4, action=action, acceptance_rate_before=0.8, acceptance_rate_after=0.3)
        assert "strong_degradation" in r4.improvement_direction

    def test_to_dict(self):
        action = SelfEditAction(action_type=SealActionType.FOCUS_DOMAIN, domain="error_handling")
        record = RewardRecord(
            cycle=3,
            action=action,
            acceptance_rate_before=0.4,
            acceptance_rate_after=0.65,
            examples_generated=50,
            inner_train_loss=0.12,
            inner_eval_loss=0.15,
        )
        d = record.to_dict()
        assert d["cycle"] == 3
        assert d["reward_delta"] == 0.25
        assert d["examples_generated"] == 50
        assert d["inner_train_loss"] == 0.12
        assert d["acceptance_rate_before"] == 0.4


class TestSealConfig:
    def test_default_config(self):
        config = SealConfig()
        assert config.curriculum_model == "qwen2.5-coder:7b-instruct-q4_K_M"
        assert config.inner_lora_rank == 16
        assert config.inner_max_steps == 100
        assert config.meta_enabled is True
        assert config.exploration_rate == 0.3
        assert config.state_dir == ".forgeai/seal"

    def test_from_dict(self):
        config = SealConfig.from_dict({
            "inner_lora_rank": 32,
            "inner_max_steps": 200,
            "meta_enabled": False,
            "exploration_rate": 0.5,
            "state_dir": "/tmp/seal_test",
        })
        assert config.inner_lora_rank == 32
        assert config.inner_max_steps == 200
        assert config.meta_enabled is False
        assert config.exploration_rate == 0.5
        assert config.state_dir == "/tmp/seal_test"

    def test_from_dict_ignores_invalid_keys(self):
        config = SealConfig.from_dict({"unknown_key": 42, "inner_lora_rank": 8})
        assert config.inner_lora_rank == 8
        # Should not raise an error for unknown keys

    def test_to_dict(self):
        config = SealConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert "inner_lora_rank" in d
        assert "curriculum_model" in d
        assert "meta_enabled" in d
        assert len(d) > 10  # Many fields
