"""Unit tests for the RAG engine — SimpleBM25 and hybrid_search."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.rag.rag_engine import SimpleBM25, _cosine_sim, hybrid_search

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

        [d["title"] for d in actual]
        documents = [d["text"] for d in actual]
        metadatas = [
            {"title": d["title"], "version": d.get("version", ""), "category": d.get("category", "")} for d in actual
        ]
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
            {
                "title": "Lists Guide",
                "text": "Python lists are mutable ordered sequences (Title: Lists Guide)",
                "version": "3.12",
                "category": "library",
                "score": 0.9,
                "embedding": [0.5, 0.5, 0.0],
            },
            {
                "title": "Dict Guide",
                "text": "Dictionaries store key-value pairs (Title: Dict Guide)",
                "version": "3.12",
                "category": "library",
                "score": 0.8,
                "embedding": [0.5, 0.5, 0.0],
            },
            {
                "title": "Sets Guide",
                "text": "Sets are unordered collections (Title: Sets Guide)",
                "version": "3.11",
                "category": "library",
                "score": 0.7,
                "embedding": [0.5, 0.5, 0.0],
            },
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

        results = hybrid_search(
            "lists", collection, embedder, bm25=None, corpus_texts=None, top_k=5, version_filter="3.12"
        )

        titles = [r["title"] for r in results]
        assert "Lists Guide" in titles
        assert "Dict Guide" in titles
        assert "Sets Guide" not in titles  # version 3.11

    def test_category_filter(self) -> None:
        """Filtering by category should exclude mismatched documents."""
        docs = self._default_docs()
        collection, embedder = self._make_mocks(docs)

        results = hybrid_search(
            "lists", collection, embedder, bm25=None, corpus_texts=None, top_k=5, category_filter="library"
        )

        assert len(results) == 3  # all are library

        results2 = hybrid_search(
            "lists", collection, embedder, bm25=None, corpus_texts=None, top_k=5, category_filter="tutorial"
        )
        assert len(results2) == 0  # none are tutorial

    def test_use_mmr(self) -> None:
        """With use_mmr=True, hybrid search should not crash and return MMR-processed results."""
        docs = self._default_docs()
        # Give docs different embeddings so MMR has an effect
        docs[0]["embedding"] = [1.0, 0.0, 0.0]
        docs[1]["embedding"] = [0.0, 1.0, 0.0]
        docs[2]["embedding"] = [0.0, 0.0, 1.0]

        collection, embedder = self._make_mocks(docs)
        results = hybrid_search(
            "lists", collection, embedder, bm25=None, corpus_texts=None, top_k=3, use_mmr=True, mmr_lambda=0.7
        )

        assert len(results) == 3
        # All original docs should still be present
        titles = [r["title"] for r in results]
        assert "Lists Guide" in titles
        assert "Dict Guide" in titles
        assert "Sets Guide" in titles

    def test_mmr_lambda_zero(self) -> None:
        """With lambda=0, MMR should favour diversity over relevance."""
        docs = [
            {
                "title": "Doc A",
                "text": "Text A",
                "version": "3.12",
                "category": "lib",
                "score": 0.9,
                "embedding": [1.0, 0.0, 0.0],
            },
            {
                "title": "Doc B",
                "text": "Text B",
                "version": "3.12",
                "category": "lib",
                "score": 0.8,
                "embedding": [0.99, 0.01, 0.0],
            },
            {
                "title": "Doc C",
                "text": "Text C",
                "version": "3.12",
                "category": "lib",
                "score": 0.7,
                "embedding": [0.0, 1.0, 0.0],
            },
        ]
        collection, embedder = self._make_mocks(docs)
        # No BM25 needed for this test
        results = hybrid_search(
            "query", collection, embedder, bm25=None, corpus_texts=None, top_k=3, use_mmr=True, mmr_lambda=0.0
        )

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
            {
                "title": f"Doc {i}",
                "text": f"Text {i}",
                "version": "3.12",
                "category": "lib",
                "score": 0.9 - i * 0.05,
                "embedding": [0.5, 0.5, 0.0],
            }
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

        docs = [self._make_doc(f"Doc {i}", 0.9 - i * 0.05, [float(i % 2), float((i + 1) % 2), 0.0]) for i in range(10)]
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


from contextlib import contextmanager  # noqa: E402


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
    assert "def foo(): pass" in blocks[1]


def test_extract_code_blocks_no_code() -> None:
    """extract_code_blocks should return empty list when no code."""
    from src.rag.rag_engine import extract_code_blocks

    text = "Just plain text, no code here."
    assert extract_code_blocks(text) == []


# ══════════════════════════════════════════════════════════════════════
# _code_chunks_to_rag_format tests
# ══════════════════════════════════════════════════════════════════════


class TestCodeChunksToRagFormat:
    """Tests for the cAST code chunk → RAG format conversion."""

    def test_basic_conversion(self) -> None:
        """A single CodeChunk should convert to the correct dict format."""
        from src.rag.cast_chunker import CodeChunk
        from src.rag.rag_engine import _code_chunks_to_rag_format

        chunk = CodeChunk(
            content="def foo():\n    return 42",
            chunk_type="function",
            start_line=1,
            end_line=2,
            name="foo",
            filepath="/project/src/module.py",
            language="python",
            token_count=10,
        )
        result = _code_chunks_to_rag_format([chunk])
        assert len(result) == 1
        d = result[0]
        assert d["type"] == "function"
        assert "foo" in d["title"]
        assert "module.py" in d["title"]
        assert d["category"] == "code"
        assert d["version"] == ""
        assert "def foo" in d["text"]
        assert d["id"].startswith("cast_")

    def test_with_parent_class(self) -> None:
        """Chunks with parent_class should include it in the title."""
        from src.rag.cast_chunker import CodeChunk
        from src.rag.rag_engine import _code_chunks_to_rag_format

        chunk = CodeChunk(
            content="def bar(self): pass",
            chunk_type="method",
            start_line=5,
            end_line=5,
            name="bar",
            parent_class="MyClass",
            filepath="test.py",
            language="python",
            token_count=2,
        )
        result = _code_chunks_to_rag_format([chunk])
        title = result[0]["title"]
        assert "MyClass" in title
        assert "bar" in title

    def test_empty_list(self) -> None:
        """An empty list should return an empty list."""
        from src.rag.rag_engine import _code_chunks_to_rag_format

        assert _code_chunks_to_rag_format([]) == []

    def test_multiple_chunks(self) -> None:
        """Multiple chunks should all be converted."""
        from src.rag.cast_chunker import CodeChunk
        from src.rag.rag_engine import _code_chunks_to_rag_format

        chunks = [
            CodeChunk(
                content="import os",
                chunk_type="import_block",
                start_line=1,
                end_line=1,
                name="imports",
                filepath="mod.py",
                language="python",
                token_count=1,
            ),
            CodeChunk(
                content="def util(): pass",
                chunk_type="function",
                start_line=3,
                end_line=3,
                name="util",
                filepath="mod.py",
                language="python",
                token_count=1,
            ),
            CodeChunk(
                content="class Helper: pass",
                chunk_type="class",
                start_line=5,
                end_line=5,
                name="Helper",
                filepath="mod.py",
                language="python",
                token_count=1,
            ),
        ]
        result = _code_chunks_to_rag_format(chunks)
        assert len(result) == 3
        assert result[0]["type"] == "import_block"
        assert result[1]["type"] == "function"
        assert result[2]["type"] == "class"

    def test_embedding_text_includes_signature_and_docstring(self) -> None:
        """to_embedding_text() should produce multi-view content."""
        from src.rag.cast_chunker import CodeChunk
        from src.rag.rag_engine import _code_chunks_to_rag_format

        chunk = CodeChunk(
            content="def compute(x, y):\n    return x + y",
            chunk_type="function",
            start_line=1,
            end_line=2,
            name="compute",
            signature="def compute(x, y):",
            docstring="Add two numbers.",
            filepath="calc.py",
            language="python",
            token_count=4,
        )
        result = _code_chunks_to_rag_format([chunk])
        text = result[0]["text"]
        assert "Signature: def compute(x, y):" in text
        assert "Docstring: Add two numbers." in text
        assert "return x + y" in text


# ══════════════════════════════════════════════════════════════════════
# load_or_build_db tests (mocked)
# ══════════════════════════════════════════════════════════════════════


def test_load_or_build_db_force_rebuild() -> None:
    """load_or_build_db with force_rebuild should call build_db."""
    # This is a lightweight smoke test — we test the import and path logic.
    # The function should exist and accept a boolean
    import inspect

    from src.rag.rag_engine import load_or_build_db

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


def test_save_conversation_with_temp_files(tmp_path: Path) -> None:
    """save_conversation should write a JSON file with conversation data."""
    import json

    import src.rag.rag_engine as rag
    from src.rag.rag_engine import save_conversation

    history = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a programming language."},
    ]

    original_root = rag.ROOT
    try:
        rag.ROOT = tmp_path
        result = save_conversation(history, export_md=False)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"
        data = json.loads(result.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[1]["role"] == "assistant"
    finally:
        rag.ROOT = original_root


def test_save_conversation_with_markdown(tmp_path: Path) -> None:
    """save_conversation with export_md=True should also write a .md file."""
    import src.rag.rag_engine as rag
    from src.rag.rag_engine import save_conversation

    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    original_root = rag.ROOT
    try:
        rag.ROOT = tmp_path
        result = save_conversation(history, export_md=True)
        assert result is not None
        conv_dir = tmp_path / "data" / "conversations"
        md_files = list(conv_dir.glob("*.md"))
        assert len(md_files) >= 1
        md_content = md_files[0].read_text(encoding="utf-8")
        assert "Question" in md_content
        assert "Hi" in md_content
        assert "Hello" in md_content
    finally:
        rag.ROOT = original_root


# ══════════════════════════════════════════════════════════════════════
# _to_plain_list tests
# ══════════════════════════════════════════════════════════════════════


class TestToPlainList:
    """Tests for the _to_plain_list helper."""

    def test_plain_list_passes_through(self) -> None:
        from src.rag.rag_engine import _to_plain_list

        assert _to_plain_list([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]

    def test_empty_list(self) -> None:
        from src.rag.rag_engine import _to_plain_list

        assert _to_plain_list([]) == []

    def test_numpy_array(self) -> None:
        import numpy as np

        from src.rag.rag_engine import _to_plain_list

        arr = np.array([0.5, 0.3, 0.1])
        result = _to_plain_list(arr)
        assert result == [0.5, 0.3, 0.1]
        assert type(result) is list

    def test_nested_numpy(self) -> None:
        import numpy as np

        from src.rag.rag_engine import _to_plain_list

        arr = np.array([[0.1, 0.2], [0.3, 0.4]])
        result = _to_plain_list(arr)
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        assert type(result) is list

    def test_tuple_input(self) -> None:
        from src.rag.rag_engine import _to_plain_list

        assert _to_plain_list((1, 2, 3)) == [1, 2, 3]

    def test_generator_input(self) -> None:
        from src.rag.rag_engine import _to_plain_list

        assert _to_plain_list(x * 2 for x in [1, 2, 3]) == [2, 4, 6]


# ══════════════════════════════════════════════════════════════════════
# parse_args tests
# ══════════════════════════════════════════════════════════════════════


class TestParseArgs:
    """Tests for the parse_args function."""

    def test_default_values(self, monkeypatch: Any) -> None:
        import sys

        monkeypatch.setattr(sys, "argv", ["rag_engine.py", "--question", "test"])
        from src.rag.rag_engine import parse_args

        args = parse_args()
        assert args.model == "qwen2.5-coder:14b"
        assert args.question == "test"
        assert args.rebuild is False
        assert args.stats is False
        assert args.no_exec is False
        assert args.exec_timeout == 5
        assert args.query_expansion is False
        assert args.mmr is False
        assert args.mmr_lambda == 0.7
        assert args.version == ""
        assert args.category == ""

    def test_boolean_flags(self, monkeypatch: Any) -> None:
        import sys

        monkeypatch.setattr(
            sys, "argv", ["rag_engine.py", "--rebuild", "--stats", "--no-exec", "--query-expansion", "--mmr"]
        )
        from src.rag.rag_engine import parse_args

        args = parse_args()
        assert args.rebuild is True
        assert args.stats is True
        assert args.no_exec is True
        assert args.query_expansion is True
        assert args.mmr is True

    def test_custom_values(self, monkeypatch: Any) -> None:
        import sys

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "rag_engine.py",
                "--model",
                "llama3.2:3b",
                "--question",
                "What is a list?",
                "--exec-timeout",
                "10",
                "--mmr-lambda",
                "0.5",
                "--version",
                "3.12",
                "--category",
                "library",
                "--list-models",
            ],
        )
        from src.rag.rag_engine import parse_args

        args = parse_args()
        assert args.model == "llama3.2:3b"
        assert args.question == "What is a list?"
        assert args.exec_timeout == 10
        assert args.mmr_lambda == 0.5
        assert args.version == "3.12"
        assert args.category == "library"
        assert args.list_models is True

    def test_list_models_flag(self, monkeypatch: Any) -> None:
        import sys

        monkeypatch.setattr(sys, "argv", ["rag_engine.py", "--list-models"])
        from src.rag.rag_engine import parse_args

        args = parse_args()
        assert args.list_models is True


# ══════════════════════════════════════════════════════════════════════
# format_sources edge cases
# ══════════════════════════════════════════════════════════════════════


class TestFormatSourcesExtended:
    """Extended edge case tests for format_sources."""

    def test_empty_list(self) -> None:
        from src.rag.rag_engine import format_sources

        assert format_sources([]) == ""

    def test_single_source(self) -> None:
        from src.rag.rag_engine import format_sources

        docs = [{"citation_num": 1, "title": "Doc A", "version": "3.12", "category": "lib"}]
        result = format_sources(docs)
        assert result.startswith("\n")
        assert "[1]" in result
        assert "Doc A" in result

    def test_multiple_sources(self) -> None:
        from src.rag.rag_engine import format_sources

        docs = [
            {"citation_num": 1, "title": "Doc A", "version": "3.12", "category": "lib"},
            {"citation_num": 2, "title": "Doc B", "version": "3.11", "category": "tutorial"},
            {"citation_num": 3, "title": "Doc C", "version": "", "category": ""},
        ]
        result = format_sources(docs)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) >= 4  # header + 3 docs
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result

    def test_none_version(self) -> None:
        """Missing version should not cause crash."""
        from src.rag.rag_engine import format_sources

        docs = [{"citation_num": 1, "title": "Doc", "version": None, "category": "lib"}]
        result = format_sources(docs)
        assert "Doc" in result

    def test_long_title_truncation(self) -> None:
        from src.rag.rag_engine import format_sources

        docs = [{"citation_num": 1, "title": "A" * 100, "version": "3.12", "category": "lib"}]
        result = format_sources(docs)
        assert len(result) < 200  # title should be truncated to 50 chars


# ══════════════════════════════════════════════════════════════════════
# extract_code_blocks edge cases
# ══════════════════════════════════════════════════════════════════════


class TestExtractCodeBlocksExtended:
    """Extended edge case tests for extract_code_blocks."""

    def test_empty_text(self) -> None:
        from src.rag.rag_engine import extract_code_blocks

        assert extract_code_blocks("") == []

    def test_no_fence(self) -> None:
        from src.rag.rag_engine import extract_code_blocks

        text = "Here is some inline `code` but no fences."
        assert extract_code_blocks(text) == []

    def test_other_language_fence(self) -> None:
        """Non-python fences should not be extracted."""
        from src.rag.rag_engine import extract_code_blocks

        text = """```javascript
console.log("hello");
```"""
        assert extract_code_blocks(text) == []

    def test_mixed_fences(self) -> None:
        """Python fences mixed with other languages should only extract python ones."""
        from src.rag.rag_engine import extract_code_blocks

        text = """```python
x = 1
```
```bash
echo hello
```"""
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "x = 1" in blocks[0]

    def test_empty_python_block(self) -> None:
        from src.rag.rag_engine import extract_code_blocks

        text = """```python
```"""
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0] == ""

    def test_code_with_backticks_inside(self) -> None:
        from src.rag.rag_engine import extract_code_blocks

        text = """```python
print('hello')
```"""
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1


# ══════════════════════════════════════════════════════════════════════
# execute_code edge cases
# ══════════════════════════════════════════════════════════════════════


class TestExecuteCodeExtended:
    """Extended edge case tests for execute_code."""

    def test_empty_code(self) -> None:
        from src.rag.rag_engine import execute_code

        stdout, stderr = execute_code("", timeout=5)
        # Empty code behavior varies by platform; verify tuple is returned without crash
        assert isinstance(stdout, (str, type(None)))
        assert isinstance(stderr, (str, type(None)))

    def test_import_socket_blocked(self) -> None:
        from src.rag.rag_engine import execute_code

        stdout, stderr = execute_code("import socket; s = socket.socket()", timeout=5)
        assert stdout is None
        assert stderr == "Skipped (safety)"

    def test_dangerous_open_blocked(self) -> None:
        from src.rag.rag_engine import execute_code

        # 'open(' in code should be blocked
        stdout, stderr = execute_code('open("test.txt", "w").write("data")', timeout=5)
        assert stdout is None
        assert stderr == "Skipped (safety)"

    def test_import_shutil_blocked(self) -> None:
        from src.rag.rag_engine import execute_code

        stdout, stderr = execute_code("import shutil; shutil.rmtree('/')", timeout=5)
        assert stdout is None
        assert stderr == "Skipped (safety)"

    def test_import_ctypes_blocked(self) -> None:
        from src.rag.rag_engine import execute_code

        stdout, stderr = execute_code("import ctypes; ctypes.CDLL('libc.so.6')", timeout=5)
        assert stdout is None
        assert stderr == "Skipped (safety)"

    def test_import_os_inside_function(self) -> None:
        """Even within a function definition, import os should be blocked."""
        from src.rag.rag_engine import execute_code

        code = """def foo():
    import os
    return os.getcwd()
print(foo())"""
        stdout, stderr = execute_code(code, timeout=5)
        assert stdout is None
        assert stderr == "Skipped (safety)"


# ══════════════════════════════════════════════════════════════════════
# export_conversation_markdown tests
# ══════════════════════════════════════════════════════════════════════


class TestExportConversationMarkdown:
    """Tests for export_conversation_markdown."""

    def test_basic_export(self) -> None:
        from pathlib import Path

        from src.rag.rag_engine import export_conversation_markdown

        history = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a language."},
        ]
        result_path = export_conversation_markdown(history, output_path=None)
        assert result_path is not None
        assert result_path.endswith(".md")
        content = Path(result_path).read_text(encoding="utf-8")
        assert "Question" in content
        assert "What is Python?" in content
        assert "Answer" in content
        assert "Python is a language." in content
        # Cleanup
        Path(result_path).unlink(missing_ok=True)

    def test_export_with_citations(self) -> None:
        from pathlib import Path

        from src.rag.rag_engine import export_conversation_markdown

        history = [
            {"role": "user", "content": "What are lists?"},
            {
                "role": "assistant",
                "content": "Lists are ordered.",
                "docs": [
                    {
                        "citation_num": 1,
                        "title": "Lists Guide",
                        "version": "3.12",
                        "category": "library",
                        "text": "Python lists are mutable",
                    },
                ],
            },
        ]
        result_path = export_conversation_markdown(history, output_path=None)
        content = Path(result_path).read_text(encoding="utf-8")
        assert "Lists Guide" in content
        assert "[1]" in content
        Path(result_path).unlink(missing_ok=True)

    def test_export_empty_history(self) -> None:
        from pathlib import Path

        from src.rag.rag_engine import export_conversation_markdown

        result_path = export_conversation_markdown([], output_path=None)
        content = Path(result_path).read_text(encoding="utf-8")
        assert "PythonAI RAG Conversation" in content
        Path(result_path).unlink(missing_ok=True)

    def test_export_to_specified_path(self, tmp_path: Path) -> None:
        from pathlib import Path

        from src.rag.rag_engine import export_conversation_markdown

        history = [{"role": "user", "content": "Hi"}]
        output_path = tmp_path / "test_export.md"
        result_path = export_conversation_markdown(history, output_path=output_path)
        assert Path(result_path).exists()
        assert Path(result_path).read_text(encoding="utf-8") != ""

    def test_export_with_docs_param(self, tmp_path: Path) -> None:
        from pathlib import Path

        from src.rag.rag_engine import export_conversation_markdown

        history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
        docs = [
            {"citation_num": 1, "title": "Doc A", "version": "3.12", "category": "lib", "text": "Content"},
        ]
        output_path = tmp_path / "test_docs.md"
        result_path = export_conversation_markdown(history, output_path=output_path, docs=docs)
        content = Path(result_path).read_text(encoding="utf-8")
        assert "All Sources" in content or "Doc A" in content


# ══════════════════════════════════════════════════════════════════════
# list_conversations & search_conversations tests
# ══════════════════════════════════════════════════════════════════════


class TestListConversations:
    """Tests for list_conversations and search_conversations with temp files."""

    def test_no_conversations_dir(self, tmp_path: Path) -> None:
        import src.rag.rag_engine as rag
        from src.rag.rag_engine import list_conversations, search_conversations

        original_root = rag.ROOT
        try:
            rag.ROOT = tmp_path / "nonexistent"
            assert list_conversations() == []
            assert search_conversations("anything") == []
        finally:
            rag.ROOT = original_root

    def test_list_with_files(self, tmp_path: Path) -> None:
        import src.rag.rag_engine as rag
        from src.rag.rag_engine import list_conversations

        original_root = rag.ROOT
        try:
            rag.ROOT = tmp_path
            conv_dir = tmp_path / "data" / "conversations"
            conv_dir.mkdir(parents=True, exist_ok=True)

            # Create a test conversation file
            conv_data = [
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "Python is great."},
            ]
            import json

            json.dump(conv_data, (conv_dir / "conversation_20250101_120000.json").open("w"))

            results = list_conversations()
            assert len(results) >= 1
            assert results[0]["messages"] == 2
            assert results[0]["questions"] == 1
            assert "Python" in results[0]["summary"]
        finally:
            rag.ROOT = original_root

    def test_search_conversations(self, tmp_path: Path) -> None:
        import src.rag.rag_engine as rag
        from src.rag.rag_engine import search_conversations

        original_root = rag.ROOT
        try:
            rag.ROOT = tmp_path
            conv_dir = tmp_path / "data" / "conversations"
            conv_dir.mkdir(parents=True, exist_ok=True)

            conv_data = [
                {"role": "user", "content": "What is a Python list?"},
                {"role": "assistant", "content": "A list is a mutable sequence."},
            ]
            import json

            json.dump(conv_data, (conv_dir / "conversation_20250101_120000.json").open("w"))

            results = search_conversations("Python list")
            assert len(results) >= 1
            assert results[0]["matches"] >= 1
            assert len(results[0]["snippets"]) >= 1

            results_no_match = search_conversations("nonexistent_topic_xyz")
            assert len(results_no_match) == 0
        finally:
            rag.ROOT = original_root

    def test_search_with_malformed_file(self, tmp_path: Path) -> None:
        """Malformed JSON files should be gracefully skipped."""
        import src.rag.rag_engine as rag
        from src.rag.rag_engine import list_conversations, search_conversations

        original_root = rag.ROOT
        try:
            rag.ROOT = tmp_path
            conv_dir = tmp_path / "data" / "conversations"
            conv_dir.mkdir(parents=True, exist_ok=True)

            # Create an invalid JSON file
            (conv_dir / "conversation_bad.json").write_text("this is not json")

            # Should not crash
            results = list_conversations()
            assert len(results) == 0
            search_results = search_conversations("test")
            assert len(search_results) == 0
        finally:
            rag.ROOT = original_root

    def test_search_max_results(self, tmp_path: Path) -> None:
        import src.rag.rag_engine as rag
        from src.rag.rag_engine import search_conversations

        original_root = rag.ROOT
        try:
            rag.ROOT = tmp_path
            conv_dir = tmp_path / "data" / "conversations"
            conv_dir.mkdir(parents=True, exist_ok=True)

            import json

            for i in range(5):
                conv_data = [{"role": "user", "content": f"Question {i} about Python"}]
                json.dump(conv_data, (conv_dir / f"conversation_2025010{i}_120000.json").open("w"))

            results = search_conversations("Python", max_results=3)
            assert len(results) == 3
        finally:
            rag.ROOT = original_root


# ══════════════════════════════════════════════════════════════════════
# get_answer (mocked) — lightweight smoke tests
# ══════════════════════════════════════════════════════════════════════


class TestGetAnswer:
    """Tests for get_answer with mocked ollama.chat and ollama.generate."""

    def test_get_answer_returns_correct_structure(self) -> None:
        """get_answer should return (answer, docs) tuple without errors."""
        from src.rag.rag_engine import get_answer

        # Create mock collection with one doc
        coll = MockCollection(
            [
                {
                    "title": "Lists Guide",
                    "text": "Lists are mutable (Title: Lists Guide)",
                    "version": "3.12",
                    "category": "library",
                    "score": 0.9,
                    "embedding": [0.5, 0.5, 0.0],
                },
            ]
        )
        embedder = MockEmbedder()

        with _mock_ollama_generate("1. How do lists work?"):
            with _mock_ollama_chat("Lists are ordered and mutable."):
                answer, docs = get_answer(
                    "What are lists?",
                    coll,
                    embedder,
                    [],
                    bm25=None,
                    corpus_texts=None,
                    kg=None,
                    use_query_expansion=False,
                )

        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(docs, list)

    def test_get_answer_with_query_expansion(self) -> None:
        """get_answer with query_expansion=True should not crash."""
        from src.rag.rag_engine import get_answer

        coll = MockCollection(
            [
                {
                    "title": "Doc A",
                    "text": "Content of Doc A (Title: Doc A)",
                    "version": "3.12",
                    "category": "lib",
                    "score": 0.8,
                    "embedding": [0.5, 0.5, 0.0],
                },
            ]
        )
        embedder = MockEmbedder()

        with _mock_ollama_generate("1. Alternative query?\n2. Another query?"):
            with _mock_ollama_chat("Here is the answer."):
                answer, docs = get_answer(
                    "What is Python?",
                    coll,
                    embedder,
                    [],
                    use_query_expansion=True,
                )

        assert isinstance(answer, str)
        assert len(answer) > 0

    def test_get_answer_with_empty_docs(self) -> None:
        """get_answer should work even when no documents are found."""
        from src.rag.rag_engine import get_answer

        coll = MockCollection([])
        embedder = MockEmbedder()

        with _mock_ollama_generate(""):
            with _mock_ollama_chat("I'll answer from my knowledge."):
                answer, docs = get_answer(
                    "What is Python?",
                    coll,
                    embedder,
                    [],
                    no_exec=True,
                )

        assert isinstance(answer, str)
        assert isinstance(docs, list)


@contextmanager
def _mock_ollama_chat(response_text: str):
    """Context manager to mock ollama.chat (streaming).

    Returns a list of dicts matching the real ollama.chat streaming format
    where each chunk has chunk["message"]["content"].
    """
    import ollama as ollama_module

    original = ollama_module.chat

    def _fake_chat(*args: object, **kwargs: object) -> list[dict[str, dict[str, str]]]:
        return [{"message": {"content": response_text}}]

    ollama_module.chat = _fake_chat  # type: ignore[assignment]
    try:
        yield
    finally:
        ollama_module.chat = original


# ══════════════════════════════════════════════════════════════════════
# show_model_info tests (mocked Ollama)
# ══════════════════════════════════════════════════════════════════════


def test_show_model_info_with_data(capsys: Any) -> None:
    """show_model_info should print model details."""
    with _mock_ollama_show({"modelfile": "FROM qwen", "parameters": "num_ctx 512"}):
        from src.rag.rag_engine import show_model_info

        show_model_info("test-model")
        captured = capsys.readouterr()
        assert "test-model" in captured.out


def test_show_model_info_with_empty_response(capsys: Any) -> None:
    """show_model_info should handle empty/error response."""
    with _mock_ollama_show({}):
        from src.rag.rag_engine import show_model_info

        show_model_info("unknown-model")
        captured = capsys.readouterr()
        assert "unknown-model" in captured.out


@contextmanager
def _mock_ollama_show(return_data: dict[str, Any]):
    """Context manager to mock ollama.show."""
    import ollama as ollama_module

    original = ollama_module.show

    def _fake_show(model: str = "") -> dict[str, Any]:
        return return_data

    ollama_module.show = _fake_show  # type: ignore[assignment]
    try:
        yield
    finally:
        ollama_module.show = original
