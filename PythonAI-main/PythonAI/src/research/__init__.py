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
"""

from src.research.qaar import QAARMetric, compute_qaar
from src.research.zipf_inverse import ZipfInverseWeighting
from src.research.time_decay import TimeDecaySignal
from src.research.complexity_score import ConventionComplexityScore
from src.research.grokking import GrokkingDetector
from src.research.hormetic import HormeticTrainer

__all__ = [
    "QAARMetric",
    "compute_qaar",
    "ZipfInverseWeighting",
    "TimeDecaySignal",
    "ConventionComplexityScore",
    "GrokkingDetector",
    "HormeticTrainer",
]
