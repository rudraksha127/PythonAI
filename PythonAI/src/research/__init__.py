"""
ForgeAI Research — Original Contributions
==========================================
Unpublished research from the ForgeAI Antigravity System Prompt.

This package implements 10 original research contributions:
1. QAAR — Quality-Adjusted Acceptance Rate
2. Zipf-Inverse Training Weights
3. Time-Decay Learning Signal
4. Convention Complexity Score (K_team)
5. Grokking Detection
6. Vulnerability Vaccination
7. Hormetic Training
8. Somatic Hypermutation for Adapters
9. ForgeAI Training Theorem utilities
10. Lindy-Weighted Training

Research-backed implementations from harvested papers:
11. Attention Mechanism Analyzer — 13 attention variants & codebase analysis
"""

from src.research.qaar import QAARMetric, compute_qaar
from src.research.zipf_inverse import ZipfInverseWeighting
from src.research.time_decay import TimeDecaySignal
from src.research.complexity_score import ConventionComplexityScore
from src.research.grokking import GrokkingDetector
from src.research.hormetic import HormeticTrainer
from src.research.attention_mechanism import (
    AttentionMechanismAnalyzer,
    AttentionVariant,
    scaled_dot_product_attention,
    multi_head_attention,
    causal_masked_attention,
    cross_attention,
    flash_attention,
    grouped_query_attention,
    sliding_window_attention,
    run_attention_analysis,
    demo_attention_variants,
)

__all__ = [
    "QAARMetric",
    "compute_qaar",
    "ZipfInverseWeighting",
    "TimeDecaySignal",
    "ConventionComplexityScore",
    "GrokkingDetector",
    "HormeticTrainer",
    # Attention Mechanism Analyzer
    "AttentionMechanismAnalyzer",
    "AttentionVariant",
    "scaled_dot_product_attention",
    "multi_head_attention",
    "causal_masked_attention",
    "cross_attention",
    "flash_attention",
    "grouped_query_attention",
    "sliding_window_attention",
    "run_attention_analysis",
    "demo_attention_variants",
]
