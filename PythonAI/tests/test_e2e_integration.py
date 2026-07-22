"""End-to-end cross-stage integration tests.

Exercises a realistic cross-stage scenario with real helper functions
across auth, data, training, RAG, and swarm subsystems.
"""

from __future__ import annotations

from src.auth.auth import hash_password, verify_password
from src.data.merger import merge
from src.rag.rag_engine import SimpleBM25, format_sources
from src.training.evaluator import compute_bleu
from src.utils.swarm import AgentSwarm, TaskDecomposer


def test_integration_cross_stage_pipeline() -> None:
    """Exercise a realistic cross-stage scenario with real helper functions."""

    # 1) Auth generates credentials
    salt, hashed = hash_password("pipeline_pass")
    assert verify_password("pipeline_pass", salt, hashed), "auth verify failed"

    # 2) Data pipeline dedups and merges some training pairs
    base = [
        {"instruction": "What is a list?", "output": "A" * 100, "category": "basic"},
        {"instruction": "What is a dict?", "output": "B" * 100, "category": "basic"},
    ]
    addition = [
        {"instruction": "What is a list?", "output": "A" * 100, "category": "basic"},
        {"instruction": "What is a set?", "output": "C" * 100, "category": "advanced"},
    ]
    merged = merge(base, addition, min_output_chars=10)
    assert len(merged) == 3, f"integrated merge: expected 3, got {len(merged)}"

    # 3) Training pipeline computes BLEU on a sample
    bleu = compute_bleu(
        "Python lists are mutable ordered sequences",
        "Lists are mutable ordered sequences",
    )
    assert bleu > 0.3, f"integrated BLEU too low: {bleu}"

    # 4) RAG BM25 scores documents
    corpus = [r["output"] for r in merged]
    bm25 = SimpleBM25(corpus)
    scores = bm25.get_scores("list")
    assert len(scores) == 3

    # Citation formatting
    docs = [
        {"citation_num": i + 1, "title": r["instruction"], "version": "3.12", "category": r["category"]}
        for i, r in enumerate(merged)
    ]
    sources = format_sources(docs)
    assert "[1]" in sources
    assert "[2]" in sources

    # 5) Swarm executes tasks
    swarm = AgentSwarm(max_workers=2)
    decomposer = TaskDecomposer()
    chunk = {"id": "int", "title": "Integration", "codes": ["x = 1"], "version": "3.12"}
    prompts = {"basic": "Explain integration", "code_review": "Review this"}
    tasks = decomposer.decompose(chunk, prompts)
    swarm_results = swarm.execute(tasks, lambda t: {"type": t.task_type, "pairs": [t.task_type]})
    assert len(swarm_results) == len(tasks)
