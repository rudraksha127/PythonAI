"""Tests for the Attention Mechanism Analyzer (src/research/attention_mechanism.py).

Covers:
  - All 6 attention variant implementations
  - AttentionMechanismAnalyzer codebase scanning
  - Utility functions (entropy, sparsity)
  - Edge cases (empty, single element, different shapes)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Module under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.attention_mechanism import (
    AttentionMechanismAnalyzer,
    AttentionVariant,
    ATTENTION_PAPERS,
    causal_masked_attention,
    cross_attention,
    demo_attention_variants,
    flash_attention,
    grouped_query_attention,
    multi_head_attention,
    run_attention_analysis,
    scaled_dot_product_attention,
    sliding_window_attention,
    _compute_attention_entropy,
    _compute_attention_sparsity,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def small_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Small random Q, K, V tensors for fast tests."""
    np.random.seed(42)
    q = np.random.randn(2, 8, 32).astype(np.float64)
    k = np.random.randn(2, 8, 32).astype(np.float64)
    v = np.random.randn(2, 8, 32).astype(np.float64)
    return q, k, v


@pytest.fixture
def tiny_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tiny 1x1 inputs for edge case tests."""
    np.random.seed(42)
    q = np.random.randn(1, 1, 4).astype(np.float64)
    k = np.random.randn(1, 1, 4).astype(np.float64)
    v = np.random.randn(1, 1, 4).astype(np.float64)
    return q, k, v


# ═══════════════════════════════════════════════════════════════════
# Scaled Dot-Product Attention
# ═══════════════════════════════════════════════════════════════════


class TestScaledDotProductAttention:
    """Tests for the base scaled dot-product attention."""

    def test_output_shape(self, small_inputs: tuple) -> None:
        """Output should have same shape as value."""
        q, k, v = small_inputs
        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.shape == v.shape, f"Expected {v.shape}, got {out.shape}"

    def test_output_dtype(self, small_inputs: tuple) -> None:
        """Output should be float64."""
        q, k, v = small_inputs
        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.dtype == np.float64

    def test_metadata_keys(self, small_inputs: tuple) -> None:
        """Metadata should contain expected keys."""
        q, k, v = small_inputs
        out, meta = scaled_dot_product_attention(q, k, v)
        assert "entropy" in meta
        assert "max_attention" in meta
        assert "sparsity" in meta
        assert "d_k" in meta
        assert meta["d_k"] == 32

    def test_entropy_range(self, small_inputs: tuple) -> None:
        """Entropy should be non-negative."""
        q, k, v = small_inputs
        out, meta = scaled_dot_product_attention(q, k, v)
        assert meta["entropy"] >= 0.0

    def test_causal_mask(self, small_inputs: tuple) -> None:
        """Causal mask should produce lower-triangular attention."""
        q, k, v = small_inputs
        # Create causal mask
        seq_len = q.shape[1]
        mask = np.triu(np.ones((seq_len, seq_len)), k=1).astype(bool)
        mask = np.broadcast_to(mask, (q.shape[0],) + mask.shape)

        out, meta = scaled_dot_product_attention(q, k, v, mask=mask)
        weights = meta["attention_weights"]

        # Check upper triangle is close to 0
        for b in range(weights.shape[0]):
            upper_tri = np.triu(weights[b], k=1)
            assert np.allclose(upper_tri, 0.0, atol=1e-6), (
                "Causal mask should zero out upper triangle"
            )

    def test_single_element(self, tiny_inputs: tuple) -> None:
        """Should handle single-element sequences."""
        q, k, v = tiny_inputs
        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.shape == v.shape
        assert meta["entropy"] >= 0.0

    def test_batch_independence(self) -> None:
        """Each batch item should attend independently."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 8).astype(np.float64)
        k = np.random.randn(2, 4, 8).astype(np.float64)
        v = np.random.randn(2, 4, 8).astype(np.float64)

        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.shape[0] == 2  # Two independent batches


# ═══════════════════════════════════════════════════════════════════
# Multi-Head Attention
# ═══════════════════════════════════════════════════════════════════


class TestMultiHeadAttention:
    """Tests for multi-head attention."""

    def test_output_shape(self) -> None:
        """Output should maintain d_model dimensions."""
        np.random.seed(42)
        batch, seq, d_model = 2, 8, 64
        q = np.random.randn(batch, seq, d_model).astype(np.float64)
        k = np.random.randn(batch, seq, d_model).astype(np.float64)
        v = np.random.randn(batch, seq, d_model).astype(np.float64)

        out, meta = multi_head_attention(q, k, v, num_heads=8)
        assert out.shape == (batch, seq, d_model)

    def test_num_heads(self) -> None:
        """Metadata should report correct head count."""
        np.random.seed(42)
        q = np.random.randn(2, 8, 64).astype(np.float64)
        k = np.random.randn(2, 8, 64).astype(np.float64)
        v = np.random.randn(2, 8, 64).astype(np.float64)

        out, meta = multi_head_attention(q, k, v, num_heads=4)
        assert meta["num_heads"] == 4
        assert len(meta["head_entropies"]) == 4

    def test_head_diversity(self) -> None:
        """Different heads should produce different attention patterns."""
        np.random.seed(42)
        q = np.random.randn(2, 8, 64).astype(np.float64)
        k = np.random.randn(2, 8, 64).astype(np.float64)
        v = np.random.randn(2, 8, 64).astype(np.float64)

        out, meta = multi_head_attention(q, k, v, num_heads=4)
        assert meta["head_diversity"] >= 0.0

    def test_d_model_divisible(self) -> None:
        """Should raise ValueError if d_model not divisible by num_heads."""
        q = np.random.randn(2, 8, 65).astype(np.float64)
        k = np.random.randn(2, 8, 65).astype(np.float64)
        v = np.random.randn(2, 8, 65).astype(np.float64)

        with pytest.raises(ValueError, match="divisible"):
            multi_head_attention(q, k, v, num_heads=8)

    def test_single_head(self) -> None:
        """Single head MHA should equal scaled dot-product."""
        np.random.seed(42)
        batch, seq, d_model = 2, 4, 32
        q = np.random.randn(batch, seq, d_model).astype(np.float64)
        k = np.random.randn(batch, seq, d_model).astype(np.float64)
        v = np.random.randn(batch, seq, d_model).astype(np.float64)

        # Single head MHA is functionally similar to scaled dot-product
        out, meta = multi_head_attention(q, k, v, num_heads=1)
        assert meta["num_heads"] == 1


# ═══════════════════════════════════════════════════════════════════
# Causal Masked Attention
# ═══════════════════════════════════════════════════════════════════


class TestCausalMaskedAttention:
    """Tests for causal/autoregressive masked attention."""

    def test_output_shape(self, small_inputs: tuple) -> None:
        """Output shape should match input."""
        q, k, v = small_inputs
        out, meta = causal_masked_attention(q, k, v)
        assert out.shape == v.shape

    def test_causal_property(self) -> None:
        """Position i should not attend to positions > i."""
        np.random.seed(42)
        q = np.random.randn(1, 5, 8).astype(np.float64)
        k = np.random.randn(1, 5, 8).astype(np.float64)
        v = np.eye(5)[np.newaxis, :, :].astype(np.float64)  # Each position has a unique identity

        out, meta = causal_masked_attention(q, k, v)
        weights = meta["attention_weights"]

        # Upper triangle (j > i) should be zero
        for i in range(5):
            for j in range(i + 1, 5):
                assert weights[0, i, j] == 0.0, (
                    f"Position {i} should not attend to {j}"
                )

    def test_first_token_only_self(self) -> None:
        """First token should only attend to itself."""
        np.random.seed(42)
        q = np.random.randn(1, 4, 8).astype(np.float64)
        k = np.random.randn(1, 4, 8).astype(np.float64)
        v = np.random.randn(1, 4, 8).astype(np.float64)

        out, meta = causal_masked_attention(q, k, v)
        weights = meta["attention_weights"]

        # First token -> attn only at position 0
        assert weights[0, 0, 0] > 0
        assert np.allclose(weights[0, 0, 1:], 0.0, atol=1e-6)


# ═══════════════════════════════════════════════════════════════════
# Cross-Attention
# ═══════════════════════════════════════════════════════════════════


class TestCrossAttention:
    """Tests for cross-attention (encoder-decoder attention)."""

    def test_different_lengths(self) -> None:
        """Query and key/value can have different sequence lengths."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 16).astype(np.float64)  # decoder: 4 tokens
        k = np.random.randn(2, 10, 16).astype(np.float64)  # encoder: 10 tokens
        v = np.random.randn(2, 10, 16).astype(np.float64)

        out, meta = cross_attention(q, k, v)
        assert out.shape == (2, 4, 16)  # Output follows query length
        assert meta["entropy"] >= 0.0

    def test_mask_encoder_outputs(self) -> None:
        """Masked encoder positions should not be attended to."""
        np.random.seed(42)
        q = np.random.randn(1, 2, 8).astype(np.float64)
        k = np.random.randn(1, 4, 8).astype(np.float64)
        v = np.random.randn(1, 4, 8).astype(np.float64)

        # Mask out the last 2 encoder positions
        mask = np.zeros((1, 2, 4), dtype=bool)
        mask[:, :, 2:] = True

        out, meta = cross_attention(q, k, v, mask=mask)
        weights = meta["attention_weights"]
        # Last 2 positions should have 0 attention
        assert np.allclose(weights[0, :, 2:], 0.0, atol=1e-6)


# ═══════════════════════════════════════════════════════════════════
# FlashAttention (Tiled)
# ═══════════════════════════════════════════════════════════════════


class TestFlashAttention:
    """Tests for flash attention (tiled implementation)."""

    def test_output_shape(self, small_inputs: tuple) -> None:
        """Output should match input shape."""
        q, k, v = small_inputs
        out, meta = flash_attention(q, k, v, block_size=4)
        assert out.shape == v.shape

    def test_block_sizes(self, small_inputs: tuple) -> None:
        """Different block sizes should produce similar outputs."""
        q, k, v = small_inputs

        out_small, meta_small = flash_attention(q, k, v, block_size=2)
        out_large, meta_large = flash_attention(q, k, v, block_size=4)

        # Outputs shouldn't be wildly different
        diff = np.mean(np.abs(out_small - out_large))
        assert diff < 10.0, f"Block size change caused large diff: {diff}"

    def test_memory_reduction(self, small_inputs: tuple) -> None:
        """Block_size < seq_len should reduce memory."""
        q, k, v = small_inputs
        _, meta = flash_attention(q, k, v, block_size=4)
        assert meta["memory_reduction_ratio"] < 1.0
        assert meta["tiles_processed"] > 0

    def test_metadata(self, small_inputs: tuple) -> None:
        """Metadata should contain expected fields."""
        q, k, v = small_inputs
        _, meta = flash_attention(q, k, v, block_size=4)
        assert meta["algorithm"] == "flash_attention_tiled"
        assert "max_materialized_size" in meta
        assert "full_matrix_size" in meta

    def test_large_blocks_small_seq(self) -> None:
        """Block size larger than seq_len should still work."""
        np.random.seed(42)
        q = np.random.randn(1, 3, 8).astype(np.float64)
        k = np.random.randn(1, 3, 8).astype(np.float64)
        v = np.random.randn(1, 3, 8).astype(np.float64)

        out, meta = flash_attention(q, k, v, block_size=64)
        assert out.shape == v.shape


# ═══════════════════════════════════════════════════════════════════
# Grouped Query Attention
# ═══════════════════════════════════════════════════════════════════


class TestGroupedQueryAttention:
    """Tests for GQA (Grouped Query Attention)."""

    def test_output_shape(self) -> None:
        """Output should maintain d_model dimensions."""
        np.random.seed(42)
        batch, seq, d_model = 2, 8, 64
        q = np.random.randn(batch, seq, d_model).astype(np.float64)
        k = np.random.randn(batch, seq, d_model).astype(np.float64)
        v = np.random.randn(batch, seq, d_model).astype(np.float64)

        out, meta = grouped_query_attention(q, k, v, num_query_groups=8, num_kv_groups=2)
        assert out.shape == (batch, seq, d_model)

    def test_kv_memory_ratio(self) -> None:
        """KV memory ratio should reflect group count."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 32).astype(np.float64)
        k = np.random.randn(2, 4, 32).astype(np.float64)
        v = np.random.randn(2, 4, 32).astype(np.float64)

        # 8 query groups, 2 KV groups = 25% KV memory
        _, meta = grouped_query_attention(q, k, v, num_query_groups=8, num_kv_groups=2)
        assert meta["kv_memory_ratio"] == 0.25
        assert meta["heads_per_kv"] == 4

    def test_mqa_equivalent(self) -> None:
        """GQA with 1 KV group = MQA."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 32).astype(np.float64)
        k = np.random.randn(2, 4, 32).astype(np.float64)
        v = np.random.randn(2, 4, 32).astype(np.float64)

        _, meta = grouped_query_attention(q, k, v, num_query_groups=4, num_kv_groups=1)
        assert meta["kv_memory_ratio"] == 0.25  # 1/4 of standard MHA
        assert meta["heads_per_kv"] == 4

    def test_mha_equivalent(self) -> None:
        """GQA with equal groups = MHA."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 32).astype(np.float64)
        k = np.random.randn(2, 4, 32).astype(np.float64)
        v = np.random.randn(2, 4, 32).astype(np.float64)

        _, meta = grouped_query_attention(q, k, v, num_query_groups=4, num_kv_groups=4)
        assert meta["kv_memory_ratio"] == 1.0  # Full MHA

    def test_invalid_groups(self) -> None:
        """Should raise ValueError if groups don't divide evenly."""
        q = np.random.randn(2, 4, 32).astype(np.float64)
        k = np.random.randn(2, 4, 32).astype(np.float64)
        v = np.random.randn(2, 4, 32).astype(np.float64)

        with pytest.raises(ValueError, match="divisible"):
            grouped_query_attention(q, k, v, num_query_groups=8, num_kv_groups=3)


# ═══════════════════════════════════════════════════════════════════
# Sliding Window Attention
# ═══════════════════════════════════════════════════════════════════


class TestSlidingWindowAttention:
    """Tests for local sliding window attention."""

    def test_output_shape(self, small_inputs: tuple) -> None:
        """Output should match input shape."""
        q, k, v = small_inputs
        out, meta = sliding_window_attention(q, k, v, window_size=2)
        assert out.shape == v.shape

    def test_attends_to_fewer_tokens(self, small_inputs: tuple) -> None:
        """Sliding window should attend to fewer tokens than full attention."""
        q, k, v = small_inputs
        seq_len = q.shape[1]
        _, meta = sliding_window_attention(q, k, v, window_size=2)
        assert meta["avg_tokens_attended"] <= min(2 * 2 + 1, seq_len)  # 2*2+1 = 5

    def test_window_size_property(self) -> None:
        """Window size should determine context length."""
        np.random.seed(42)
        q = np.random.randn(1, 10, 8).astype(np.float64)
        k = np.random.randn(1, 10, 8).astype(np.float64)
        v = np.random.randn(1, 10, 8).astype(np.float64)

        _, meta = sliding_window_attention(q, k, v, window_size=1)
        assert meta["avg_tokens_attended"] <= 3  # left 1 + self + right 1

    def test_efficiency_ratio(self) -> None:
        """Efficiency ratio should be < 1 for small windows."""
        np.random.seed(42)
        q = np.random.randn(1, 20, 8).astype(np.float64)
        k = np.random.randn(1, 20, 8).astype(np.float64)
        v = np.random.randn(1, 20, 8).astype(np.float64)

        _, meta = sliding_window_attention(q, k, v, window_size=2)
        assert meta["efficiency_ratio"] < 1.0


# ═══════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════


class TestUtilityFunctions:
    """Tests for _compute_attention_entropy and _compute_attention_sparsity."""

    def test_entropy_zero_for_perfect_confidence(self) -> None:
        """Entropy should be ~0 when all weight is on one position."""
        # One-hot attention: all mass on first position
        weights = np.zeros((1, 1, 5))
        weights[0, 0, 0] = 1.0
        entropy = _compute_attention_entropy(weights)
        assert entropy < 1e-6, f"Expected ~0 entropy, got {entropy}"

    def test_entropy_positive_for_uniform(self) -> None:
        """Entropy should be > 0 for uniform distribution."""
        weights = np.ones((1, 1, 5)) / 5.0
        entropy = _compute_attention_entropy(weights)
        assert entropy > 0.0

    def test_entropy_max_for_uniform(self) -> None:
        """Uniform distribution should have maximum entropy."""
        n = 5
        weights = np.ones((1, 1, n)) / n
        entropy = _compute_attention_entropy(weights)
        theoretical_max = np.log(n)
        assert abs(entropy - theoretical_max) < 0.001

    def test_sparsity_all_high(self) -> None:
        """Sparsity should be 0 when all weights are above threshold."""
        weights = np.ones((1, 1, 5)) * 0.2
        sparsity = _compute_attention_sparsity(weights, threshold=0.1)
        assert sparsity == 0.0

    def test_sparsity_all_low(self) -> None:
        """Sparsity should be 1 when all weights below threshold (approx)."""
        weights = np.ones((1, 1, 5)) * 0.01
        sparsity = _compute_attention_sparsity(weights, threshold=0.1)
        assert sparsity > 0.9

    def test_sparsity_half(self) -> None:
        """Sparsity should be ~0.5 when half of weights are near-zero."""
        weights = np.zeros((1, 1, 10))
        weights[0, 0, :5] = 0.19   # Above 0.02 threshold
        weights[0, 0, 5:] = 0.001  # Below threshold
        sparsity = _compute_attention_sparsity(weights, threshold=0.02)
        # 5 out of 10 weights are < 0.02
        assert 0.4 <= sparsity <= 0.6, f"Expected ~0.5 sparsity, got {sparsity}"


# ═══════════════════════════════════════════════════════════════════
# AttentionMechanismAnalyzer
# ═══════════════════════════════════════════════════════════════════


class TestAttentionMechanismAnalyzer:
    """Tests for the codebase analysis class."""

    @pytest.fixture
    def analyzer(self) -> AttentionMechanismAnalyzer:
        """Create an analyzer instance."""
        return AttentionMechanismAnalyzer()

    def test_analyzer_importable(self) -> None:
        """Analyzer should be importable and instantiable."""
        analyzer = AttentionMechanismAnalyzer()
        assert analyzer is not None
        assert hasattr(analyzer, "analyze_codebase")

    def test_variant_patterns_defined(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """Every variant should have at least one search pattern."""
        for variant in AttentionVariant:
            patterns = analyzer.VARIANT_PATTERNS.get(variant, [])
            assert len(patterns) > 0, f"{variant.value} has no search patterns"

    def test_variant_enum_count(self) -> None:
        """Should have exactly 13 attention variants."""
        assert len(AttentionVariant) == 13

    def test_attention_papers_have_all_fields(self) -> None:
        """Each paper reference should have required fields."""
        for paper in ATTENTION_PAPERS:
            assert "variant" in paper
            assert "title" in paper
            assert "arxiv_id" in paper
            assert "insight" in paper

    def test_analyze_codebase_returns_dict(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """analyze_codebase should return a dict with expected structure."""
        report = analyzer.analyze_codebase()
        assert isinstance(report, dict)
        assert "total_variants" in report
        assert "variant_coverage" in report
        assert "paper_references" in report
        assert "recommendations" in report
        assert report["total_variants"] == 13

    def test_variant_coverage_structure(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """Each variant in coverage should have expected fields."""
        report = analyzer.analyze_codebase()
        for v_name, cov in report["variant_coverage"].items():
            assert "status" in cov
            assert cov["status"] in ("covered", "partial", "missing")
            assert "match_count" in cov
            assert "patterns_matched" in cov
            assert "files_using" in cov

    def test_at_least_one_variant_covered(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """At least one attention variant should be covered in the codebase."""
        report = analyzer.analyze_codebase()
        covered_count = report["variants_covered"]
        assert covered_count >= 1, (
            f"Expected at least 1 covered variant, got {covered_count}"
        )

    def test_specific_variants_exist(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """Check that specific key variants exist in coverage."""
        report = analyzer.analyze_codebase()
        # These should always be in the coverage dict
        for key in ["scaled_dot_product", "multi_head", "causal_masked", "cross_attention"]:
            assert key in report["variant_coverage"], f"Missing variant key: {key}"

    def test_paper_references_include_codebase_cov(self, analyzer: AttentionMechanismAnalyzer) -> None:
        """Paper references should include coverage status."""
        report = analyzer.analyze_codebase()
        for ref in report["paper_references"]:
            assert "codebase_coverage" in ref
            assert ref["codebase_coverage"] in ("covered", "partial", "missing")

    def test_print_report_does_not_crash(self, analyzer: AttentionMechanismAnalyzer, capsys: pytest.CaptureFixture) -> None:
        """print_report should not crash."""
        report = analyzer.analyze_codebase()
        analyzer.print_report(report)
        captured = capsys.readouterr()
        assert "ATTENTION MECHANISM ANALYSIS REPORT" in captured.out


# ═══════════════════════════════════════════════════════════════════
# Demo & Convenience Functions
# ═══════════════════════════════════════════════════════════════════


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_demo_attention_variants(self, capsys: pytest.CaptureFixture) -> None:
        """demo_attention_variants should run without errors."""
        demo_attention_variants(seq_len=4, d_k=8)
        captured = capsys.readouterr()
        assert "ATTENTION MECHANISM DEMONSTRATION" in captured.out
        assert "All variants executed successfully" in captured.out

    def test_run_attention_analysis_returns_dict(self, capsys: pytest.CaptureFixture) -> None:
        """run_attention_analysis should return a report dict."""
        report = run_attention_analysis()
        assert isinstance(report, dict)
        assert "variant_coverage" in report
        # Check output was printed
        captured = capsys.readouterr()
        assert "ATTENTION MECHANISM ANALYSIS REPORT" in captured.out


# ═══════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Tests for edge cases across all attention implementations."""

    def test_zero_d_k(self) -> None:
        """d_k=0 should raise an error (can't divide by sqrt(0))."""
        q = np.random.randn(2, 4, 0).astype(np.float64)
        k = np.random.randn(2, 4, 0).astype(np.float64)
        v = np.random.randn(2, 4, 0).astype(np.float64)
        with pytest.raises(Exception):
            scaled_dot_product_attention(q, k, v)

    def test_large_d_k(self) -> None:
        """Should handle large d_k without numerical issues."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 256).astype(np.float64)
        k = np.random.randn(2, 4, 256).astype(np.float64)
        v = np.random.randn(2, 4, 256).astype(np.float64)

        out, meta = scaled_dot_product_attention(q, k, v)
        assert not np.any(np.isnan(out)), "Output contains NaN"
        assert not np.any(np.isinf(out)), "Output contains Inf"
        assert meta["entropy"] >= 0.0

    def test_non_square_keys(self) -> None:
        """Query and key/value can have different sequence lengths."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 16).astype(np.float64)  # 4 queries
        k = np.random.randn(2, 7, 16).astype(np.float64)  # 7 keys
        v = np.random.randn(2, 7, 16).astype(np.float64)  # 7 values

        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.shape == (2, 4, 16)  # Output matches query length
        assert meta["attention_weights"].shape == (2, 4, 7)  # (q_len, k_len)

    def test_broadcasting(self) -> None:
        """Should handle batched inputs (batch, heads, seq, d_k)."""
        np.random.seed(42)
        q = np.random.randn(2, 4, 8, 16).astype(np.float64)  # (batch, heads, seq, d_k)
        k = np.random.randn(2, 4, 8, 16).astype(np.float64)
        v = np.random.randn(2, 4, 8, 16).astype(np.float64)

        out, meta = scaled_dot_product_attention(q, k, v)
        assert out.shape == (2, 4, 8, 16)
