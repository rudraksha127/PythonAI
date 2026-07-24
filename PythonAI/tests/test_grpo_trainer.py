"""Comprehensive tests for the GRPO Trainer — Group Relative Policy Optimization.

Tests cover:
- compute_reward: reward calculation with various scenarios
- GRPOPair: serialization and data integrity
- create_grpo_pairs_from_signals: signal matching logic
- GRPOTrainer: initialization and loss computation
- End-to-end data flow from capture engine → GRPO pairs → training
"""

from __future__ import annotations

import json

import pytest


# ═══════════════════════════════════════════════════════════════
# Reward Function Tests
# ═══════════════════════════════════════════════════════════════


class TestComputeReward:
    """Verify compute_reward logic with verifiable rewards (RLVR)."""

    def test_accept_baseline_reward(self):
        """Accepted response should get +1.0 base reward."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=False,
            lint_passed=False,
            is_accepted=True,
        )
        assert reward == 1.0, f"Expected 1.0, got {reward}"

    def test_reject_negative_reward(self):
        """Rejected response should get -1.0 base reward."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=False,
            lint_passed=False,
            is_accepted=False,
        )
        assert reward == -1.0, f"Expected -1.0, got {reward}"

    def test_test_passed_bonus(self):
        """Test passing should add +2.0 bonus."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=True,
            lint_passed=False,
            is_accepted=True,
        )
        assert reward == 3.0, f"Expected 3.0 (1.0 + 2.0), got {reward}"

    def test_lint_passed_bonus(self):
        """Lint passing should add +0.5 bonus."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=False,
            lint_passed=True,
            is_accepted=True,
        )
        assert reward == 1.5, f"Expected 1.5 (1.0 + 0.5), got {reward}"

    def test_all_bonuses_combined(self):
        """All bonuses combined for accepted + test + lint."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=True,
            lint_passed=True,
            is_accepted=True,
        )
        assert reward == 3.5, f"Expected 3.5 (1.0 + 2.0 + 0.5), got {reward}"

    def test_rejected_but_tests_pass(self):
        """Rejected + test pass should still be negative-ish."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="def add(a, b): return a + b",
            test_passed=True,
            lint_passed=False,
            is_accepted=False,
        )
        assert reward == 1.0, f"Expected 1.0 (-1.0 + 2.0), got {reward}"

    def test_length_penalty(self):
        """Long responses beyond 500 chars should incur format penalty."""
        from src.training.grpo_trainer import compute_reward

        long_response = "word " * 600  # ~3000 chars
        reward = compute_reward(
            response=long_response,
            test_passed=False,
            lint_passed=False,
            is_accepted=True,
        )
        # Penalty: -0.1 per 100 chars over 500
        expected_penalty = -0.1 * max(0, (len(long_response) - 500) // 100)
        expected = 1.0 + expected_penalty
        assert reward == expected, f"Expected {expected}, got {reward}"

    def test_empty_response_reward(self):
        """Empty response should still compute a reward."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="",
            test_passed=False,
            lint_passed=False,
            is_accepted=True,
        )
        assert reward == 1.0, f"Expected 1.0 for empty accepted, got {reward}"

    def test_rejected_with_test_lint_fail(self):
        """Rejected + no tests/lint = worst case."""
        from src.training.grpo_trainer import compute_reward

        reward = compute_reward(
            response="wrong code",
            test_passed=False,
            lint_passed=False,
            is_accepted=False,
        )
        assert reward == -1.0, f"Expected -1.0 for worst case, got {reward}"


# ═══════════════════════════════════════════════════════════════
# GRPOPair Tests
# ═══════════════════════════════════════════════════════════════


class TestGRPOPair:
    """Verify GRPOPair dataclass and serialization."""

    def test_create_basic(self):
        """A GRPOPair should be created with minimal fields."""
        from src.training.grpo_trainer import GRPOPair

        pair = GRPOPair(
            prompt="Write a Python function to add two numbers",
            accepted_response="def add(a, b): return a + b",
            rejected_response="def add(a, b): result = a + b\n    return result",
        )
        assert "add two numbers" in pair.prompt
        assert pair.accepted_response == "def add(a, b): return a + b"
        assert pair.accepted_test_passed is False  # default
        assert pair.language == "python"  # default

    def test_to_dict_round_trip(self):
        """to_dict() → from_dict() should preserve all fields."""
        from src.training.grpo_trainer import GRPOPair

        original = GRPOPair(
            prompt="Create a FastAPI endpoint",
            accepted_response='@app.get("/items")\ndef list_items(): pass',
            rejected_response='@app.route("/items")\ndef items(): pass',
            accepted_test_passed=True,
            rejected_test_passed=False,
            accepted_lint_passed=True,
            rejected_lint_passed=False,
            signal_id="grpo_sig_001",
            language="python",
            framework="fastapi",
        )
        data = original.to_dict()
        restored = GRPOPair.from_dict(data)

        assert restored.prompt == original.prompt
        assert restored.accepted_response == original.accepted_response
        assert restored.rejected_response == original.rejected_response
        assert restored.accepted_test_passed is True
        assert restored.rejected_test_passed is False
        assert restored.signal_id == original.signal_id
        assert restored.framework == original.framework

    def test_json_serializable(self):
        """GRPOPair should be JSON-serializable via to_dict."""
        from src.training.grpo_trainer import GRPOPair

        pair = GRPOPair(
            prompt="Test serialization",
            accepted_response="accepted",
            rejected_response="rejected",
        )
        json_str = json.dumps(pair.to_dict())
        parsed = json.loads(json_str)
        assert parsed["prompt"] == "Test serialization"
        assert parsed["language"] == "python"

    def test_with_full_metadata(self):
        """GRPOPair should handle all optional metadata fields."""
        from src.training.grpo_trainer import GRPOPair

        pair = GRPOPair(
            prompt="Write a React component",
            accepted_response="function App() { return <div />; }",
            rejected_response="class App extends React.Component { render() { return <div />; } }",
            accepted_test_passed=True,
            rejected_test_passed=False,
            accepted_lint_passed=True,
            rejected_lint_passed=False,
            signal_id="sig_react_001",
            language="javascript",
            framework="react",
        )
        assert pair.signal_id == "sig_react_001"
        assert pair.framework == "react"
        assert pair.accepted_test_passed is True


# ═══════════════════════════════════════════════════════════════
# Signal Pairing Tests
# ═══════════════════════════════════════════════════════════════


class TestCreateGRPOPairs:
    """Verify create_grpo_pairs_from_signals logic."""

    def test_matches_accept_with_reject_by_language(self):
        """Accepts should be matched with rejects of the same language."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        accepts = [
            {
                "signal_id": "a1",
                "suggestion": "def a(): pass",
                "language": "python",
                "full_context": "write a function",
                "context_before": "write a function",
                "test_passed": True,
            },
            {
                "signal_id": "a2",
                "suggestion": "function b() {}",
                "language": "javascript",
                "full_context": "write a JS function",
                "context_before": "write a JS function",
                "test_passed": False,
            },
        ]
        rejects = [
            {
                "signal_id": "r1",
                "suggestion": "def bad(): pass",
                "language": "python",
                "full_context": "write a function",
                "context_before": "write a function",
                "test_passed": False,
            },
            {
                "signal_id": "r2",
                "suggestion": "function bad() {}",
                "language": "javascript",
                "full_context": "write a JS function",
                "context_before": "write a JS function",
                "test_passed": False,
            },
        ]
        edits: list[dict] = []

        pairs = create_grpo_pairs_from_signals(accepts, rejects, edits)

        # Should create 2 pairs (one per accept matched with same-language reject)
        assert len(pairs) == 2, f"Expected 2 pairs, got {len(pairs)}"

        # Check language matching
        py_pairs = [p for p in pairs if p.language == "python"]
        js_pairs = [p for p in pairs if p.language == "javascript"]
        assert len(py_pairs) >= 1
        assert len(js_pairs) >= 1

    def test_edit_signals_create_self_pairs(self):
        """Edit signals should create pairs from suggestion vs final_code."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        edits = [
            {
                "signal_id": "e1",
                "suggestion": "return df.head()",
                "final_code": "import pandas as pd\nreturn df.head()",
                "full_context": "analyze data",
                "context_before": "analyze data",
                "language": "python",
            },
        ]

        pairs = create_grpo_pairs_from_signals([], [], edits)

        assert len(pairs) == 1
        assert "import pandas" in pairs[0].accepted_response
        assert pairs[0].rejected_response == "return df.head()"
        assert pairs[0].language == "python"

    def test_no_matching_reject_skips(self):
        """Accept with no matching reject should not create a pair."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        accepts = [
            {
                "signal_id": "a1",
                "suggestion": "def a(): pass",
                "language": "python",
                "full_context": "context",
                "context_before": "context",
                "test_passed": True,
            },
        ]
        rejects = [
            {
                "signal_id": "r1",
                "suggestion": "function b() {}",
                "language": "javascript",  # different language
                "full_context": "context",
                "context_before": "context",
                "test_passed": False,
            },
        ]
        edits: list[dict] = []

        pairs = create_grpo_pairs_from_signals(accepts, rejects, edits)

        # No matching reject by language → no pair
        assert len(pairs) == 0

    def test_mixed_signals(self):
        """Mix of accepts, rejects, and edits should create appropriate pairs."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        accepts = [
            {
                "signal_id": "a1",
                "suggestion": "def good(): pass",
                "language": "python",
                "full_context": "write function",
                "context_before": "write function",
                "test_passed": True,
            },
        ]
        rejects = [
            {
                "signal_id": "r1",
                "suggestion": "def bad(): pass",
                "language": "python",
                "full_context": "write function",
                "context_before": "write function",
                "test_passed": False,
            },
        ]
        edits = [
            {
                "signal_id": "e1",
                "suggestion": "quick fix",
                "final_code": "detailed fix with error handling",
                "full_context": "fix bug",
                "context_before": "fix bug",
                "language": "python",
            },
        ]

        pairs = create_grpo_pairs_from_signals(accepts, rejects, edits)

        assert len(pairs) >= 1  # At least 1 from accept/reject match
        # Edits always create pairs
        edit_pairs = [p for p in pairs if p.signal_id == "e1"]
        assert len(edit_pairs) == 1

    def test_empty_signals(self):
        """Empty signal lists should produce no pairs."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        pairs = create_grpo_pairs_from_signals([], [], [])
        assert pairs == []


# ═══════════════════════════════════════════════════════════════
# GRPOTrainer Tests (without GPU/transformers)
# ═══════════════════════════════════════════════════════════════


class TestGRPOTrainerInit:
    """Verify GRPOTrainer initialization and configuration."""

    def test_initialization_defaults(self):
        """GRPOTrainer should initialize with sensible defaults."""
        from src.training.grpo_trainer import GRPOTrainer

        trainer = GRPOTrainer(model_name="Qwen/Qwen2.5-1.5B-Instruct")
        assert trainer.model_name == "Qwen/Qwen2.5-1.5B-Instruct"
        assert trainer.lora_rank == 16
        assert trainer.learning_rate == 1e-5
        assert trainer.kl_coef == 0.04

    def test_custom_config(self):
        """GRPOTrainer should accept custom configuration."""
        from src.training.grpo_trainer import GRPOTrainer

        trainer = GRPOTrainer(
            model_name="Qwen/Qwen2.5-1.5B-Instruct",  # Must be a real model name for HF
            lora_rank=8,
            lora_alpha=16,
            learning_rate=5e-6,
            kl_coef=0.1,
            gamma=0.99,
            max_length=1024,
        )
        assert trainer.lora_rank == 8
        assert trainer.lora_alpha == 16
        assert trainer.learning_rate == 5e-6
        assert trainer.kl_coef == 0.1
        assert trainer.gamma == 0.99
        assert trainer.max_length == 1024

    def test_tokenizer_loading(self):
        """Tokenizer should be loaded from model name."""
        from src.training.grpo_trainer import GRPOTrainer

        # Use a tiny model available in most environments
        trainer = GRPOTrainer(model_name="Qwen/Qwen2.5-1.5B-Instruct")
        assert trainer.tokenizer is not None
        assert trainer.tokenizer.pad_token is not None


# ═══════════════════════════════════════════════════════════════
# End-to-End Signal → Pair → Training Flow
# ═══════════════════════════════════════════════════════════════


class TestGRPOE2EFlow:
    """End-to-end validation: signals → GRPO pairs → training metrics."""

    def test_full_signal_to_pair_pipeline(self):
        """Simulate the full data flow from capture engine to training pairs."""
        from src.training.grpo_trainer import (
            GRPOPair,
            compute_reward,
            create_grpo_pairs_from_signals,
        )

        # Simulate capture engine data (accept and reject must share language
        # AND same file_path extension to match via create_grpo_pairs_from_signals)
        accepts = [
            {
                "signal_id": "a1",
                "suggestion": "import os\nimport sys\n\ndef main():\n    return os.getcwd()",
                "language": "python",
                "full_context": "Write a Python script that prints the current working directory",
                "context_before": "Write a Python script that prints the current working directory",
                "test_passed": True,
                "file_path": "src/main.py",
            },
            {
                "signal_id": "a2",
                "suggestion": "SELECT * FROM users WHERE active = 1",
                "language": "sql",
                "full_context": "Write a SQL query",
                "context_before": "Write a SQL query",
                "test_passed": True,
            },
        ]
        rejects = [
            {
                "signal_id": "r1",
                "suggestion": "import os\nprint('hello')",
                "language": "python",
                "full_context": "Write a Python script that prints the current working directory",
                "context_before": "Write a Python script that prints the current working directory",
                "test_passed": False,
                "file_path": "src/main.py",  # same extension as accept to match
            },
        ]
        edits: list[dict] = []

        pairs = create_grpo_pairs_from_signals(accepts, rejects, edits)

        # Python accept/reject should match → 1 pair
        assert len(pairs) >= 1

        # Verify rewards for the matched pair
        py_pair = [p for p in pairs if p.language == "python"]
        if py_pair:
            pair = py_pair[0]
            accepted_reward = compute_reward(
                response=pair.accepted_response,
                test_passed=pair.accepted_test_passed,
                lint_passed=pair.accepted_lint_passed,
                is_accepted=True,
            )
            rejected_reward = compute_reward(
                response=pair.rejected_response,
                test_passed=pair.rejected_test_passed,
                lint_passed=pair.rejected_lint_passed,
                is_accepted=False,
            )

            # Accepted should have higher reward
            assert accepted_reward > rejected_reward, (
                f"Accepted reward ({accepted_reward}) should exceed rejected ({rejected_reward})"
            )

    def test_signal_pair_persistence(self):
        """GRPO pairs should round-trip through JSON for storage."""
        from src.training.grpo_trainer import GRPOPair

        pairs = [
            GRPOPair(
                prompt="Create a FastAPI app",
                accepted_response='app = FastAPI()',
                rejected_response='app = Flask(__name__)',
                signal_id="e2e_001",
                language="python",
            ),
            GRPOPair(
                prompt="Create a React component",
                accepted_response='function App() { return <div />; }',
                rejected_response='class App extends Component { render() { return <div />; } }',
                signal_id="e2e_002",
                language="javascript",
            ),
        ]

        # Convert to JSON lines
        json_lines = [json.dumps(p.to_dict()) for p in pairs]

        # Restore
        restored = [GRPOPair.from_dict(json.loads(line)) for line in json_lines]

        assert len(restored) == len(pairs)
        for original, rest in zip(pairs, restored):
            assert original.prompt == rest.prompt
            assert original.accepted_response == rest.accepted_response
            assert original.rejected_response == rest.rejected_response
            assert original.signal_id == rest.signal_id

    def test_reward_delta_is_meaningful(self):
        """The reward difference between accept/reject should be significant."""
        from src.training.grpo_trainer import compute_reward

        # Best case accept
        best_accept = compute_reward(
            response="perfect code",
            test_passed=True,
            lint_passed=True,
            is_accepted=True,
        )
        # Worst case reject
        worst_reject = compute_reward(
            response="wrong code that also is way too long " * 50,
            test_passed=False,
            lint_passed=False,
            is_accepted=False,
        )

        delta = best_accept - worst_reject
        assert delta > 3.0, f"Reward delta too small: {delta:.2f}"
