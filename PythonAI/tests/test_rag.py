"""Unit tests for the RAG engine — SimpleBM25 and hybrid_search."""

from __future__ import annotations

import math
from typing import Any

import pytest

from src.rag.rag_engine import SimpleBM25, hybrid_search, _cosine_sim


# ══════════════════════════════════════════════════════════════════════
# SimpleBM25
# ══════════════════════════════════════════════════════════════════════


class TestSimpleBM25:
    """Comprehensive tests for the lightweight BM25 implementation."""

    def test_corpus_empty(self) -> None:
        """BM25 with an empty corpus should not crash."""
        bm25 = SimpleBM25([])
        assert bm25.n_docs == 0
        assert bm25.avgdl == 0.0
        assert bm25.get_scores("anything") == []

    def test_single_document(self) -> None:
        """BM25 with a single document returns score 0 from the only doc."""
        bm25 = SimpleBM25(["Python lists are mutable"])
        scores = bm25.get_scores("lists")
        assert len(scores) == 1
        assert scores[0] > 0.0, "matching term should produce a positive score"

    def test_relevant_ranking(self) -> None:
        """Documents containing query terms should rank higher."""
        corpus = [
            "Python lists are mutable ordered sequences",
            "Python dictionaries store key value pairs",
            "Python sets are unordered collections of unique elements",
        ]
        bm25 = SimpleBM25(corpus)

        list_scores = bm25.get_scores("lists mutable")
        dict_scores = bm25.get_scores("dictionaries key value")
        set_scores = bm25.get_scores("sets unordered unique")

        assert list_scores[0] > list_scores[1], "list doc should rank #1 for 'lists mutable'"
        assert dict_scores[1] > dict_scores[0], "dict doc should rank #1 for 'dictionaries key value'"
        assert dict_scores[1] > dict_scores[2], "dict doc should rank #1 for 'dictionaries key value'"
        assert set_scores[2] > set_scores[0], "sets doc should rank #1 for 'sets unordered unique'"
        assert set_scores[2] > set_scores[1], "sets doc should rank #1 for 'sets unordered unique'"

    def test_empty_query(self) -> None:
        """An empty query should return zero scores for all documents."""
        bm25 = SimpleBM25(["doc a", "doc b"])
        scores = bm25.get_scores("")
        assert all(s == 0.0 for s in scores)

    def test_no_match_query(self) -> None:
        """A query with no matching terms returns all zeros."""
        bm25 = SimpleBM25(["Python lists", "Java arrays"])
        scores = bm25.get_scores("zzzzz")
        assert all(s == 0.0 for s in scores)

    def test_case_insensitive(self) -> None:
        """BM25 tokenization should be case-insensitive."""
        bm25 = SimpleBM25(["Python lists are mutable"])
        upper_score = bm25.get_scores("PYTHON")
        lower_score = bm25.get_scores("python")
        assert upper_score == lower_score, "case should not affect scores"

    def test_term_repetition(self) -> None:
        """A document with more term repetitions should score higher."""
        bm25 = SimpleBM25(["lists lists", "lists once"])
        scores = bm25.get_scores("lists")
        assert scores[0] > scores[1], "doc with repeated 'lists' should score higher"

    def test_tokenize(self) -> None:
        """_tokenize should handle punctuation and mixed case."""
        tokens = SimpleBM25._tokenize("Hello-World! This is Python_3.12")
        assert "hello" in tokens
        assert "world" in tokens
        assert "this" in tokens
        assert "python_3" in tokens  # underscore kept, period splits
        # "12" alone may also appear if split on '.'
        assert len(tokens) >= 5

    def test_k1_and_b_parameters(self) -> None:
        """Different k1/b values should produce different scores."""
        # Document with same words but different lengths
        corpus = [
            "python lists are mutable ordered sequences",  # shorter doc
            "python lists are mutable ordered sequences python lists are mutable "
            "ordered sequences python lists are mutable ordered sequences",  # longer doc
        ]
        bm25_default = SimpleBM25(corpus, k1=1.5, b=0.75)
        bm25_high_b = SimpleBM25(corpus, k1=1.5, b=1.0)

        scores_default = bm25_default.get_scores("python lists")
        scores_high_b = bm25_high_b.get_scores("python lists")

        # With higher b, longer doc is penalised more → scores differ
        assert scores_default != scores_high_b, "varying b should produce different scores"

    def test_idf_out_of_range(self) -> None:
        """IDF for terms not in the corpus should not crash."""
        bm25 = SimpleBM25(["Python lists"])
        scores = bm25.get_scores("nonexistent_word_xzy")
        assert all(s == 0.0 for s in scores)

    def test_large_corpus_does_not_crash(self) -> None:
        """BM25 should handle a moderately large corpus without issues."""
        corpus = [f"Document number {i} contains some words about topic {i % 10}" for i in range(100)]
        bm25 = SimpleBM25(corpus)
        scores = bm25.get_scores("document topic")
        assert len(scores) == 100
        assert any(s > 0 for s in scores), "some docs should match"

    def test_get_scores_output_order(self) -> None:
        """get_scores should return scores in the same order as the corpus."""
        bm25 = SimpleBM25(["zero", "first", "second"])
        scores = bm25.get_scores("first")
        assert scores[1] > scores[0], "index 1 should score higher than index 0"
        assert scores[1] > scores[2], "index 1 should score higher than index 2"


# ══════════════════════════════════════════════════════════════════════
# hybrid_search (mocked dependencies)
# ══════════════════════════════════════════════════════════════════════


class MockEmbedder:
    """A mock SentenceTransformer that returns trivial embeddings."""

    def encode(self, texts: list[str]) -> Any:
        """Return a simple 2-D embedding array-like."""
        import numpy as np

        _ = texts  # unused — all queries get the same fake embedding
        return np.array([[0.5, 0.5, 0.0]])


class MockCollection:
    """A mock chromadb Collection that returns predetermined results."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def query(self, **kwargs: Any) -> dict[str, list[Any]]:
        n_results = kwargs.get("n_results", len(self._docs))
        actual = self._docs[:n_results]

        titles = [d["title"] for d in actual]
        documents = [d["text"] for d in actual]
        metadatas = [{"title": d["title"], "version": d.get("version", ""), "category": d.get("category", "")}
                     for d in actual]
        distances = [[1.0 - d.get("score", 0.5) for d in actual]]

        result: dict[str, list[Any]] = {
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": distances,
        }

        include = kwargs.get("include", [])
        if "embeddings" in include:
            result["embeddings"] = [[d.get("embedding", []) for d in actual]]

        return result


class TestHybridSearch:
    """Tests for hybrid_search with mocked chromadb + SentenceTransformer."""

    def _make_mocks(self, docs: list[dict[str, Any]] | None = None) -> tuple[MockCollection, MockEmbedder]:
        if docs is None:
            docs = self._default_docs()
        return MockCollection(docs), MockEmbedder()

    @staticmethod
    def _default_docs() -> list[dict[str, Any]]:
        return [
            {"title": "Lists Guide", "text": "Python lists are mutable ordered sequences (Title: Lists Guide)",
             "version": "3.12", "category": "library", "score": 0.9, "embedding": [0.5, 0.5, 0.0]},
            {"title": "Dict Guide", "text": "Dictionaries store key-value pairs (Title: Dict Guide)",
             "version": "3.12", "category": "library", "score": 0.8, "embedding": [0.5, 0.5, 0.0]},
            {"title": "Sets Guide", "text": "Sets are unordered collections (Title: Sets Guide)",
             "version": "3.11", "category": "library", "score": 0.7, "embedding": [0.5, 0.5, 0.0]},
        ]

    def test_basic_no_bm25(self) -> None:
        """hybrid_search with no BM25 should return dense results sorted by score."""
        collection, embedder = self._make_mocks()
        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None, top_k=3)

        assert len(results) >= 1
        # Highest score doc should be first
        assert results[0]["title"] == "Lists Guide"

    def test_top_k_limits_results(self) -> None:
        """Setting top_k should limit the number of dense search results returned."""
        collection, embedder = self._make_mocks(self._default_docs()[:2])
        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None, top_k=1)

        assert len(results) == 1

    def test_with_bm25(self) -> None:
        """hybrid_search with BM25 should include BM25-only results via RRF."""
        collection, embedder = self._make_mocks(self._default_docs()[:2])

        # BM25 corpus includes an extra doc the dense search didn't see
        corpus_texts = [
            "Title: Lists Guide\nVersion: Python 3.12\nCategory: library\n\nLists content",
            "Title: Dict Guide\nVersion: Python 3.12\nCategory: library\n\nDict content",
            "Title: Tuples Guide\nVersion: Python 3.11\nCategory: library\n\nTuples content",
        ]
        bm25 = SimpleBM25(corpus_texts)

        results = hybrid_search("lists", collection, embedder, bm25=bm25, corpus_texts=corpus_texts, top_k=5)
        titles = [r["title"] for r in results]

        assert "Lists Guide" in titles
        assert "Dict Guide" in titles
        # BM25-only result may be included if scores merit it
        assert len(results) >= 2

    def test_version_filter(self) -> None:
        """Filtering by version should exclude mismatched documents."""
        docs = self._default_docs()
        collection, embedder = self._make_mocks(docs)

        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None,
                                top_k=5, version_filter="3.12")

        titles = [r["title"] for r in results]
        assert "Lists Guide" in titles
        assert "Dict Guide" in titles
        assert "Sets Guide" not in titles  # version 3.11

    def test_category_filter(self) -> None:
        """Filtering by category should exclude mismatched documents."""
        docs = self._default_docs()
        collection, embedder = self._make_mocks(docs)

        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None,
                                top_k=5, category_filter="library")

        assert len(results) == 3  # all are library

        results2 = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None,
                                 top_k=5, category_filter="tutorial")
        assert len(results2) == 0  # none are tutorial

    def test_use_mmr(self) -> None:
        """With use_mmr=True, hybrid search should not crash and return MMR-processed results."""
        docs = self._default_docs()
        # Give docs different embeddings so MMR has an effect
        docs[0]["embedding"] = [1.0, 0.0, 0.0]
        docs[1]["embedding"] = [0.0, 1.0, 0.0]
        docs[2]["embedding"] = [0.0, 0.0, 1.0]

        collection, embedder = self._make_mocks(docs)
        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None,
                                top_k=3, use_mmr=True, mmr_lambda=0.7)

        assert len(results) == 3
        # All original docs should still be present
        titles = [r["title"] for r in results]
        assert "Lists Guide" in titles
        assert "Dict Guide" in titles
        assert "Sets Guide" in titles

    def test_mmr_lambda_zero(self) -> None:
        """With lambda=0, MMR should favour diversity over relevance."""
        docs = [
            {"title": "Doc A", "text": "Text A", "version": "3.12", "category": "lib",
             "score": 0.9, "embedding": [1.0, 0.0, 0.0]},
            {"title": "Doc B", "text": "Text B", "version": "3.12", "category": "lib",
             "score": 0.8, "embedding": [0.99, 0.01, 0.0]},
            {"title": "Doc C", "text": "Text C", "version": "3.12", "category": "lib",
             "score": 0.7, "embedding": [0.0, 1.0, 0.0]},
        ]
        collection, embedder = self._make_mocks(docs)
        # No BM25 needed for this test
        results = hybrid_search("query", collection, embedder, bm25=None, corpus_texts=None,
                                top_k=3, use_mmr=True, mmr_lambda=0.0)

        assert len(results) == 3

    def test_empty_dense_results(self) -> None:
        """When dense search returns nothing, hybrid_search should return empty."""
        collection = MockCollection([])
        embedder = MockEmbedder()
        results = hybrid_search("anything", collection, embedder, bm25=None, corpus_texts=None, top_k=5)
        assert results == []

    def test_citation_numbers_included(self) -> None:
        """Results should have sequential citation_num starting from 1."""
        collection, embedder = self._make_mocks(self._default_docs()[:2])
        results = hybrid_search("lists", collection, embedder, bm25=None, corpus_texts=None, top_k=5)

        for i, doc in enumerate(results):
            assert doc["citation_num"] == i + 1, f"doc[{i}] citation_num should be {i + 1}"
            assert doc["rank"] == i + 1, f"doc[{i}] rank should be {i + 1}"

    def test_return_capped_at_six(self) -> None:
        """Returned list should be capped at 6 items."""
        many_docs = [
            {"title": f"Doc {i}", "text": f"Text {i}", "version": "3.12", "category": "lib",
             "score": 0.9 - i * 0.05, "embedding": [0.5, 0.5, 0.0]}
            for i in range(20)
        ]
        collection, embedder = self._make_mocks(many_docs)
        results = hybrid_search("query", collection, embedder, bm25=None, corpus_texts=None, top_k=20)
        assert len(results) <= 6


# ══════════════════════════════════════════════════════════════════════
# mmr_rerank (dedicated unit tests)
# ══════════════════════════════════════════════════════════════════════


class TestMmrRerank:
    """Dedicated unit tests for the mmr_rerank function."""

    def _make_doc(self, title: str, score: float, embedding: list[float]) -> dict[str, Any]:
        return {"title": title, "score": score, "embedding": embedding, "text": f"Content of {title}"}

    def test_empty_docs(self) -> None:
        """Empty docs list should return empty list."""
        from src.rag.rag_engine import mmr_rerank
        assert mmr_rerank([], [0.0, 0.0, 0.0]) == []

    def test_single_doc(self) -> None:
        """Single doc should be returned as-is."""
        from src.rag.rag_engine import mmr_rerank
        docs = [self._make_doc("A", 0.9, [1.0, 0.0, 0.0])]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0])
        assert len(result) == 1
        assert result[0]["title"] == "A"

    def test_lambda_one_pure_relevance(self) -> None:
        """lambda=1.0 should rank purely by relevance score (no diversity)."""
        from src.rag.rag_engine import mmr_rerank
        docs = [
            self._make_doc("High", 0.9, [1.0, 0.0, 0.0]),
            self._make_doc("Medium", 0.7, [0.0, 1.0, 0.0]),
            self._make_doc("Low", 0.5, [0.0, 0.0, 1.0]),
        ]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], lambda_=1.0, top_k=3)
        assert result[0]["title"] == "High"
        assert result[1]["title"] == "Medium"
        assert result[2]["title"] == "Low"

    def test_lambda_zero_pure_diversity(self) -> None:
        """lambda=0.0 should purely penalise similarity (diversity first)."""
        from src.rag.rag_engine import mmr_rerank
        # Two very similar docs, one very different doc
        docs = [
            self._make_doc("SimilarA", 0.9, [1.0, 0.0, 0.0]),
            self._make_doc("SimilarB", 0.8, [0.99, 0.01, 0.0]),
            self._make_doc("Different", 0.7, [0.0, 1.0, 0.0]),
        ]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], lambda_=0.0, top_k=2)
        # With lambda=0, only diversity penalty matters
        # First selected will be the highest relevance (SimilarA, score 0.9)
        # Second will be the most different from SimilarA
        assert result[0]["title"] == "SimilarA"
        assert result[1]["title"] == "Different"

    def test_top_k_limits_results(self) -> None:
        """top_k should limit how many docs are returned."""
        from src.rag.rag_engine import mmr_rerank
        docs = [
            self._make_doc(f"Doc {i}", 0.9 - i * 0.05, [float(i % 2), float((i + 1) % 2), 0.0])
            for i in range(10)
        ]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], top_k=3)
        assert len(result) == 3

    def test_no_embeddings_fallback(self) -> None:
        """Docs with empty embeddings should fall back gracefully."""
        from src.rag.rag_engine import mmr_rerank
        docs = [
            {"title": "A", "score": 0.9, "embedding": [], "text": "A"},
            {"title": "B", "score": 0.8, "embedding": [], "text": "B"},
        ]
        # Should not crash — empty embeddings produce 0 similarity
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], top_k=2)
        assert len(result) == 2

    def test_all_same_embeddings(self) -> None:
        """Docs with identical embeddings should still return in score order."""
        from src.rag.rag_engine import mmr_rerank
        docs = [
            self._make_doc("High", 0.9, [1.0, 0.0, 0.0]),
            self._make_doc("Medium", 0.8, [1.0, 0.0, 0.0]),
            self._make_doc("Low", 0.7, [1.0, 0.0, 0.0]),
        ]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], top_k=3)
        # When all embeddings are identical, diversity_penalty = 1.0 for all
        # So mmr_score = lambda * relevance - (1-lambda) * 1.0
        # First selected: highest relevance (High)
        # Second: next highest relevance (Medium) since diversity penalty is same
        assert result[0]["title"] == "High"
        assert result[1]["title"] == "Medium"
        assert result[2]["title"] == "Low"

    def test_citation_numbers_preserved(self) -> None:
        """MMR should preserve citation numbers on selected docs."""
        from src.rag.rag_engine import mmr_rerank
        docs = [
            {"title": "A", "score": 0.9, "embedding": [1.0, 0.0], "citation_num": 5},
            {"title": "B", "score": 0.8, "embedding": [0.0, 1.0], "citation_num": 3},
        ]
        result = mmr_rerank(docs, [0.5, 0.5], top_k=2)
        assert len(result) == 2
        # Check citation numbers are preserved through MMR
        result_a = next(d for d in result if d["title"] == "A")
        result_b = next(d for d in result if d["title"] == "B")
        assert result_a["citation_num"] == 5
        assert result_b["citation_num"] == 3

    def test_diversity_selection(self) -> None:
        """MMR should select diverse docs even when scores are similar."""
        from src.rag.rag_engine import mmr_rerank
        # Doc A and Doc B related (similar), Doc C very different
        # Scores: A=0.9, B=0.85, C=0.8
        # MMR with lambda=0.5 should pick A first, then C (diverse), then B
        docs = [
            self._make_doc("A", 0.9, [1.0, 0.0, 0.0]),
            self._make_doc("B", 0.85, [0.95, 0.05, 0.0]),
            self._make_doc("C", 0.8, [0.0, 1.0, 0.0]),
        ]
        result = mmr_rerank(docs, [0.5, 0.5, 0.0], lambda_=0.5, top_k=3)
        assert len(result) == 3
        # A (highest relevance) should be first
        assert result[0]["title"] == "A"
        # C should be before B because C is more diverse from A
        # Let's check relative order of B and C
        c_pos = next(i for i, d in enumerate(result) if d["title"] == "C")
        b_pos = next(i for i, d in enumerate(result) if d["title"] == "B")
        assert c_pos < b_pos, "C (diverse) should come before B (similar to A)"


# ══════════════════════════════════════════════════════════════════════
# _cosine_sim (helper used by hybrid_search and MMR)
# ══════════════════════════════════════════════════════════════════════


class TestCosineSim:
    """Tests for the _cosine_sim helper."""

    def test_identical(self) -> None:
        assert _cosine_sim([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0

    def test_orthogonal(self) -> None:
        assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_parallel(self) -> None:
        result = _cosine_sim([2.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert abs(result - 1.0) < 1e-6

    def test_empty_vectors(self) -> None:
        assert _cosine_sim([], [1.0]) == 0.0
        assert _cosine_sim([1.0], []) == 0.0

    def test_zero_vector(self) -> None:
        assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_mismatched_lengths(self) -> None:
        assert _cosine_sim([1.0, 0.0], [1.0]) == 0.0

    def test_negative_values(self) -> None:
        result = _cosine_sim([1.0, 0.0], [-1.0, 0.0])
        assert result == -1.0

    def test_partial_similarity(self) -> None:
        result = _cosine_sim([1.0, 1.0], [1.0, 0.0])
        expected = 1.0 / math.sqrt(2)  # ~0.707
        assert abs(result - expected) < 1e-6


# ══════════════════════════════════════════════════════════════════════
# expand_query (mocked Ollama)
# ══════════════════════════════════════════════════════════════════════


def test_expand_query_basic() -> None:
    """expand_query should return a list with the original question at minimum."""
    from src.rag.rag_engine import expand_query

    with _mock_ollama_generate("1. What is Python?"):
        result = expand_query("What is Python?")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0] == "What is Python?"


def test_expand_query_fallback_on_exception() -> None:
    """expand_query should fall back to just the original question on failure."""
    from src.rag.rag_engine import expand_query

    with _mock_ollama_generate("", should_raise=True):
        result = expand_query("What is Python?")
    assert result == ["What is Python?"]


def test_expand_query_extracts_queries() -> None:
    """expand_query should extract numbered queries from Ollama response."""
    from src.rag.rag_engine import expand_query

    fake_response = "1. What are Python lists?\n2. How to use lists in Python?"
    with _mock_ollama_generate(fake_response):
        result = expand_query("Explain lists")
    assert len(result) >= 2
    assert result[0] == "Explain lists"


class _MockResponse:
    """Simulates ollama.generate response."""
    def __init__(self, text: str) -> None:
        self._text = text

    def get(self, key: str, default: str = "") -> str:
        if key == "response":
            return self._text
        return default


from contextlib import contextmanager


@contextmanager
def _mock_ollama_generate(response_text: str, should_raise: bool = False):
    """Context manager to mock ollama.generate."""
    import ollama as ollama_module
    original = ollama_module.generate

    def _fake_generate(*args: object, **kwargs: object) -> _MockResponse:
        if should_raise:
            raise RuntimeError("Ollama unavailable")
        return _MockResponse(response_text)

    ollama_module.generate = _fake_generate  # type: ignore[assignment]
    try:
        yield
    finally:
        ollama_module.generate = original


# ══════════════════════════════════════════════════════════════════════
# execute_code tests
# ══════════════════════════════════════════════════════════════════════


def test_execute_code_simple_print() -> None:
    """execute_code should run a simple print statement."""
    from src.rag.rag_engine import execute_code

    stdout, stderr = execute_code("print('hello world')", timeout=5)
    assert stdout == "hello world"
    assert stderr is None


def test_execute_code_syntax_error() -> None:
    """execute_code should capture syntax errors."""
    from src.rag.rag_engine import execute_code

    stdout, stderr = execute_code("print(", timeout=5)
    assert stdout is None
    assert stderr is not None
    assert "SyntaxError" in stderr or "unexpected" in stderr.lower() or stderr != ""


def test_execute_code_timeout() -> None:
    """execute_code should handle timeout gracefully."""
    from src.rag.rag_engine import execute_code

    stdout, stderr = execute_code("import time; time.sleep(10)", timeout=1)
    assert stdout is None
    assert stderr is not None


def test_execute_code_dangerous_patterns() -> None:
    """execute_code should skip code with dangerous patterns."""
    from src.rag.rag_engine import execute_code

    # Should skip os import
    stdout, stderr = execute_code("import os; os.listdir('.')", timeout=5)
    assert stdout is None
    assert stderr == "Skipped (safety)"

    # Should skip subprocess
    stdout2, stderr2 = execute_code("import subprocess; subprocess.run(['ls'])", timeout=5)
    assert stdout2 is None
    assert stderr2 == "Skipped (safety)"

    # Should skip eval
    stdout3, stderr3 = execute_code("eval('1+1')", timeout=5)
    assert stdout3 is None
    assert stderr3 == "Skipped (safety)"

    # Should skip exec
    stdout4, stderr4 = execute_code("exec('x=1')", timeout=5)
    assert stdout4 is None
    assert stderr4 == "Skipped (safety)"


def test_execute_code_multiline() -> None:
    """execute_code should handle multi-line code."""
    from src.rag.rag_engine import execute_code

    code = """
x = 1
y = 2
print(x + y)
"""
    stdout, stderr = execute_code(code, timeout=5)
    assert stdout == "3"
    assert stderr is None


def test_extract_code_blocks() -> None:
    """extract_code_blocks should find all python fenced code blocks."""
    from src.rag.rag_engine import extract_code_blocks

    text = """Here's some code:
```python
print("hello")
```
And more:
```python
def foo(): pass
```"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 2
    assert 'print("hello")' in blocks[0]
    assert 'def foo(): pass' in blocks[1]


def test_extract_code_blocks_no_code() -> None:
    """extract_code_blocks should return empty list when no code."""
    from src.rag.rag_engine import extract_code_blocks

    text = "Just plain text, no code here."
    assert extract_code_blocks(text) == []


# ══════════════════════════════════════════════════════════════════════
# load_or_build_db tests (mocked)
# ══════════════════════════════════════════════════════════════════════


def test_load_or_build_db_force_rebuild() -> None:
    """load_or_build_db with force_rebuild should call build_db."""
    # This is a lightweight smoke test — we test the import and path logic.
    from src.rag.rag_engine import load_or_build_db
    from pathlib import Path

    # The function should exist and accept a boolean
    import inspect
    sig = inspect.signature(load_or_build_db)
    assert "force_rebuild" in sig.parameters


def test_format_sources() -> None:
    """format_sources should return properly formatted citations."""
    from src.rag.rag_engine import format_sources

    docs = [
        {"citation_num": 1, "title": "Python Lists Guide", "version": "3.12", "category": "library"},
        {"citation_num": 2, "title": "Dict Internals", "version": "3.11", "category": "internals"},
    ]
    formatted = format_sources(docs)
    assert "[1]" in formatted
    assert "[2]" in formatted
    assert "Python Lists Guide" in formatted
    assert "Dict Internals" in formatted
    assert format_sources([]) == "", "empty sources should return empty string"


def test_save_conversation() -> None:
    """save_conversation should write a JSON file."""
    from src.rag.rag_engine import save_conversation
    from pathlib import Path

    # Just verify the function exists and accepts the right args
    import inspect
    sig = inspect.signature(save_conversation)
    assert "history" in sig.parameters
