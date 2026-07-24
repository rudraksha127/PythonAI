"""Tests for the ForgeAI Researcher Agent (researcher.py).

Covers:
  - CLI entry point routing
  - Output helper functions (banner, phase, ok, etc.)
  - EnhancementAnalyzer knowledge gap detection
  - EnhancementAnalyzer suggestion generation
  - EnhancementAnalyzer report building
  - run_harvest error handling and structure
  - show_report and query_knowledge edge cases
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for test outputs."""
    d = tmp_path / "research_knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def sample_harvest_data() -> dict[str, Any]:
    """Sample harvest result with low paper count (triggers gap detection)."""
    return {
        "timestamp": "2026-07-23T12:00:00+00:00",
        "papers_collected": 0,
        "books_indexed": 18,
        "total_sources": 18,
        "total_chunks": 125,
        "by_type": {"book": 18},
        "duration_seconds": 5.2,
        "github_repos_scanned": 10,
        "errors": [],
    }


@pytest.fixture
def harvest_data_with_errors() -> dict[str, Any]:
    """Sample harvest result with errors."""
    return {
        "timestamp": "2026-07-23T12:00:00+00:00",
        "papers_collected": 5,
        "books_indexed": 3,
        "total_sources": 8,
        "total_chunks": 40,
        "by_type": {"book": 3, "paper": 5},
        "duration_seconds": 10.0,
        "github_repos_scanned": 0,
        "errors": ["Semantic Scholar API timeout", "GitHub rate limited"],
    }


@pytest.fixture
def sample_kb_stats() -> dict[str, Any]:
    """Sample knowledge base statistics."""
    return {
        "total_sources": 18,
        "by_type": {"book": 18},
        "papers": {"total_papers": 0},
        "cross_references": 8,
        "total_citations": 0,
    }


# ═══════════════════════════════════════════════════════════════════
# Test CLI Entry Point
# ═══════════════════════════════════════════════════════════════════


class TestMainCLI:
    """Test the main() CLI entry point routing."""

    def test_main_routes_harvest(self) -> None:
        """'harvest' command should call run_harvest."""
        with (
            patch("sys.argv", ["researcher.py", "harvest"]),
            patch("researcher.run_harvest", return_value={}) as mock,
        ):
            import researcher

            researcher.main()
            mock.assert_called_once()

    def test_main_routes_analyze(self) -> None:
        """'analyze' command should call run_analysis."""
        with (
            patch("sys.argv", ["researcher.py", "analyze"]),
            patch("researcher.run_analysis", return_value={}) as mock,
        ):
            import researcher

            researcher.main()
            mock.assert_called_once()

    def test_main_routes_full(self) -> None:
        """'full' command should call run_full_pipeline."""
        with (
            patch("sys.argv", ["researcher.py", "full"]),
            patch("researcher.run_full_pipeline", return_value={}) as mock,
        ):
            import researcher

            researcher.main()
            mock.assert_called_once()

    def test_main_routes_report(self) -> None:
        """'report' command should call show_report."""
        with (
            patch("sys.argv", ["researcher.py", "report"]),
            patch("researcher.show_report") as mock,
        ):
            import researcher

            researcher.main()
            mock.assert_called_once()

    def test_main_routes_query(self) -> None:
        """'query' command should call query_knowledge."""
        with (
            patch("sys.argv", ["researcher.py", "query", "attention mechanism"]),
            patch("researcher.query_knowledge", return_value=[]) as mock,
        ):
            import researcher

            researcher.main()
            mock.assert_called_once_with("attention mechanism")

    def test_main_no_args(self) -> None:
        """No arguments should print usage (not crash)."""
        with patch("sys.argv", ["researcher.py"]):
            import researcher

            researcher.main()

    def test_main_help(self) -> None:
        """--help should print usage."""
        with patch("sys.argv", ["researcher.py", "--help"]):
            import researcher

            researcher.main()

    def test_main_unknown_command(self) -> None:
        """Unknown command should not crash."""
        with patch("sys.argv", ["researcher.py", "invalid_cmd"]):
            import researcher

            researcher.main()

    def test_main_query_no_args(self) -> None:
        """query without args should warn (not crash)."""
        with patch("sys.argv", ["researcher.py", "query"]):
            import researcher

            researcher.main()


# ═══════════════════════════════════════════════════════════════════
# Test Output Helpers
# ═══════════════════════════════════════════════════════════════════


class TestOutputHelpers:
    """Test the banner, phase, ok, warn, info, err functions."""

    def test_banner(self, capsys: pytest.CaptureFixture[str]) -> None:
        """banner should print a formatted banner."""
        import researcher

        researcher.banner("Test Title")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
        assert "=" in captured.out

    def test_banner_custom_char(self, capsys: pytest.CaptureFixture[str]) -> None:
        """banner should use custom character."""
        import researcher

        researcher.banner("Custom", char="#")
        captured = capsys.readouterr()
        assert "#" in captured.out

    def test_phase(self, capsys: pytest.CaptureFixture[str]) -> None:
        """phase should print a phase header."""
        import researcher

        researcher.phase("Test Phase")
        captured = capsys.readouterr()
        assert "[PHASE]" in captured.out
        assert "Test Phase" in captured.out

    def test_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ok should print success message."""
        import researcher

        researcher.ok("All good")
        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "All good" in captured.out

    def test_warn(self, capsys: pytest.CaptureFixture[str]) -> None:
        """warn should print warning message."""
        import researcher

        researcher.warn("Something odd")
        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "Something odd" in captured.out

    def test_info(self, capsys: pytest.CaptureFixture[str]) -> None:
        """info should print info message."""
        import researcher

        researcher.info("Just so you know")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out
        assert "Just so you know" in captured.out

    def test_err(self, capsys: pytest.CaptureFixture[str]) -> None:
        """err should print error message."""
        import researcher

        researcher.err("Something broke")
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out
        assert "Something broke" in captured.out


# ═══════════════════════════════════════════════════════════════════
# Test EnhancementAnalyzer — Knowledge Gap Detection
# ═══════════════════════════════════════════════════════════════════


class TestEnhancementAnalyzerKnowledgeGaps:
    """Test knowledge gap detection in EnhancementAnalyzer."""

    def test_detects_low_paper_count(self) -> None:
        """Should flag low paper count as high-priority gap."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 0, "books_indexed": 18, "errors": []}
        analyzer._detect_knowledge_gaps(harvest_data, {})

        gaps = [s for s in analyzer.suggestions if s["area"] == "Research Paper Coverage"]
        assert len(gaps) == 1
        assert gaps[0]["priority"] == "high"
        assert "0 papers" in gaps[0]["finding"]

    def test_no_gap_with_sufficient_papers(self) -> None:
        """Should NOT flag paper gap if >= 10 papers."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 10, "books_indexed": 18, "errors": []}
        analyzer._detect_knowledge_gaps(harvest_data, {})

        gaps = [s for s in analyzer.suggestions if s["area"] == "Research Paper Coverage"]
        assert len(gaps) == 0

    def test_detects_low_book_count(self) -> None:
        """Should flag low book count as medium-priority gap."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 10, "books_indexed": 3, "errors": []}
        analyzer._detect_knowledge_gaps(harvest_data, {})

        gaps = [s for s in analyzer.suggestions if s["area"] == "Educational Resource Coverage"]
        assert len(gaps) == 1
        assert gaps[0]["priority"] == "medium"
        assert "3 books" in gaps[0]["finding"]

    def test_detects_errors(self) -> None:
        """Should flag harvest errors as high-priority."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 5, "books_indexed": 10, "errors": ["API timeout", "Rate limit"]}
        analyzer._detect_knowledge_gaps(harvest_data, {})

        gaps = [s for s in analyzer.suggestions if s["area"] == "Harvest Errors"]
        assert len(gaps) == 1
        assert gaps[0]["priority"] == "high"
        assert "2 errors" in gaps[0]["finding"]

    def test_no_errors(self) -> None:
        """Should NOT flag errors if none present."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 10, "books_indexed": 18, "errors": []}
        analyzer._detect_knowledge_gaps(harvest_data, {})

        gaps = [s for s in analyzer.suggestions if s["area"] == "Harvest Errors"]
        assert len(gaps) == 0

    def test_detects_sparse_kb_from_stats(self) -> None:
        """Should flag sparse paper KB from kb_stats."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 5, "books_indexed": 10, "errors": []}
        kb_stats = {"by_type": {"book": 10, "paper": 2}}
        analyzer._detect_knowledge_gaps(harvest_data, kb_stats)

        gaps = [s for s in analyzer.suggestions if s["area"] == "Paper Knowledge Base"]
        assert len(gaps) == 1
        assert gaps[0]["priority"] == "medium"

    def test_handles_empty_harvest_data(self) -> None:
        """Should not crash with empty harvest data."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._detect_knowledge_gaps({}, {})


# ═══════════════════════════════════════════════════════════════════
# Test EnhancementAnalyzer — Suggestion Generation
# ═══════════════════════════════════════════════════════════════════


class TestEnhancementAnalyzerSuggestions:
    """Test static suggestion generation."""

    def test_generates_all_suggestions(self) -> None:
        """Should generate all 8 static suggestions."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        assert len(analyzer.suggestions) == 8

    def test_all_suggestions_have_required_fields(self) -> None:
        """Each suggestion should have category, priority, area, finding, action, impact."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        required = {"category", "priority", "area", "finding", "action", "impact"}
        for s in analyzer.suggestions:
            assert required.issubset(s.keys()), f"Missing fields in: {s['area']}"

    def test_high_medium_low_priorities_present(self) -> None:
        """Suggestions should cover high, medium, and low priorities."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        priorities = {s["priority"] for s in analyzer.suggestions}
        assert "high" in priorities
        assert "medium" in priorities
        assert "low" in priorities

    def test_high_priority_areas(self) -> None:
        """High priority areas should include self-query, auto-tune, and benchmarks."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        high = [s for s in analyzer.suggestions if s["priority"] == "high"]
        high_areas = {s["area"] for s in high}
        assert "Self-Query Knowledge Retrieval" in high_areas
        assert "Auto-Tune Paper Topics" in high_areas
        assert "Benchmark & Dataset Tracking" in high_areas

    def test_medium_priority_areas(self) -> None:
        """Medium priority should include arXiv categories, code links, and codebase alignment."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        medium = [s for s in analyzer.suggestions if s["priority"] == "medium"]
        medium_areas = {s["area"] for s in medium}
        assert "arXiv Category Coverage" in medium_areas
        assert "Code Implementation Links" in medium_areas
        assert "Codebase-Knowledge Alignment" in medium_areas

    def test_low_priority_areas(self) -> None:
        """Low priority should include books and citation graph."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        low = [s for s in analyzer.suggestions if s["priority"] == "low"]
        low_areas = {s["area"] for s in low}
        assert "Free Book Sources" in low_areas
        assert "Paper Citation Graph" in low_areas

    def test_suggestions_have_effort_field(self) -> None:
        """Suggestions should have effort estimates."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})

        efforts = {s.get("effort") for s in analyzer.suggestions if s.get("effort")}
        assert len(efforts) >= 2  # At least Low and Medium


# ═══════════════════════════════════════════════════════════════════
# Test EnhancementAnalyzer — Report Building
# ═══════════════════════════════════════════════════════════════════


class TestEnhancementAnalyzerReport:
    """Test report building from suggestions."""

    def test_report_has_correct_structure(self) -> None:
        """Report should contain all expected top-level keys."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 5, "books_indexed": 10, "total_sources": 15, "total_chunks": 80, "errors": [], "github_repos_scanned": 5},
            {},
        )

        assert "report_timestamp" in report
        assert "report_version" in report
        assert "system" in report
        assert "knowledge_snapshot" in report
        assert "enhancement_suggestions" in report
        assert "quick_wins" in report
        assert "harvest_metadata" in report

    def test_knowledge_snapshot_values(self) -> None:
        """Knowledge snapshot should reflect input data."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 10, "books_indexed": 20, "total_sources": 30, "total_chunks": 150, "duration_seconds": 8.5, "errors": [], "github_repos_scanned": 3},
            {},
        )

        ks = report["knowledge_snapshot"]
        assert ks["papers_collected"] == 10
        assert ks["books_indexed"] == 20
        assert ks["total_sources"] == 30
        assert ks["total_rag_chunks"] == 150
        assert ks["harvest_duration_seconds"] == 8.5

    def test_suggestion_counts_in_report(self) -> None:
        """Report should count suggestions by priority correctly."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 5, "books_indexed": 10, "total_sources": 15, "total_chunks": 80, "errors": [], "github_repos_scanned": 5},
            {},
        )

        es = report["enhancement_suggestions"]
        assert es["total"] == 8
        assert es["high_priority"] == 3
        assert es["medium_priority"] == 3
        assert es["low_priority"] == 2
        assert len(es["items"]) == 8

    def test_suggestion_counts_with_gaps(self) -> None:
        """Knowledge gaps should add to suggestion count."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        harvest_data = {"papers_collected": 0, "books_indexed": 3, "errors": ["API error"]}
        analyzer._detect_knowledge_gaps(harvest_data, {})
        analyzer._generate_suggestions(harvest_data, {})

        report = analyzer._build_report(harvest_data, {})
        es = report["enhancement_suggestions"]
        # 3 gaps + 8 suggestions = 11 total
        assert es["total"] == 11
        assert es["high_priority"] >= 2   # 2 gaps (papers + errors) + 3 suggestions
        assert es["medium_priority"] >= 1  # 1 gap (books)

    def test_quick_wins_filter(self) -> None:
        """Quick wins should be high priority with low effort."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 5, "books_indexed": 10, "total_sources": 15, "total_chunks": 80, "errors": [], "github_repos_scanned": 5},
            {},
        )

        qw = report["quick_wins"]
        # Self-Query Knowledge Retrieval is high priority + low effort
        assert len(qw) >= 1
        for win in qw:
            assert win["priority"] == "high"
            assert isinstance(win.get("effort", ""), str)

    def test_harvest_metadata_in_report(self) -> None:
        """Harvest metadata should include errors and github count."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 5, "books_indexed": 10, "total_sources": 15, "total_chunks": 80, "errors": ["timeout"], "github_repos_scanned": 3},
            {},
        )

        hm = report["harvest_metadata"]
        assert hm["errors"] == ["timeout"]
        assert hm["github_repos_scanned"] == 3

    def test_report_is_json_serializable(self) -> None:
        """Report should be serializable to JSON."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        analyzer._generate_suggestions({}, {})
        report = analyzer._build_report(
            {"papers_collected": 5, "books_indexed": 10, "total_sources": 15, "total_chunks": 80, "errors": [], "github_repos_scanned": 5},
            {},
        )

        json_str = json.dumps(report, indent=2)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["knowledge_snapshot"]["papers_collected"] == 5


# ═══════════════════════════════════════════════════════════════════
# Test EnhancementAnalyzer — Full Flow
# ═══════════════════════════════════════════════════════════════════


class TestEnhancementAnalyzerFullFlow:
    """Test the full analyze() flow end-to-end."""

    def test_analyze_with_no_data_returns_error(self, tmp_path: Path) -> None:
        """analyze() without harvest data should return error dict."""
        import researcher

        with patch.object(researcher, "DATA_DIR", tmp_path / "empty"):
            analyzer = researcher.EnhancementAnalyzer()
            result = analyzer.analyze()

        assert "error" in result
        assert result["error"] == "No harvest data"

    def test_analyze_with_data_generates_report(self, temp_data_dir: Path, sample_harvest_data: dict[str, Any]) -> None:
        """analyze() with harvest data should generate a full report."""
        import researcher

        # Write harvest data to temp dir
        summary_file = temp_data_dir / "harvest_summary.json"
        summary_file.write_text(json.dumps(sample_harvest_data), encoding="utf-8")

        with patch.object(researcher, "DATA_DIR", temp_data_dir):
            analyzer = researcher.EnhancementAnalyzer()
            result = analyzer.analyze()

        assert "error" not in result
        assert result["knowledge_snapshot"]["papers_collected"] == 0
        assert result["knowledge_snapshot"]["books_indexed"] == 18
        assert result["enhancement_suggestions"]["total"] >= 8

    def test_report_saved_to_disk(self, temp_data_dir: Path, sample_harvest_data: dict[str, Any]) -> None:
        """analyze() should save report JSON to disk."""
        import researcher

        # Write harvest data to temp dir
        summary_file = temp_data_dir / "harvest_summary.json"
        summary_file.write_text(json.dumps(sample_harvest_data), encoding="utf-8")

        with patch.object(researcher, "DATA_DIR", temp_data_dir):
            analyzer = researcher.EnhancementAnalyzer()
            analyzer.analyze()

        report_file = temp_data_dir / "enhancement_report.json"
        assert report_file.exists()
        report_data = json.loads(report_file.read_text(encoding="utf-8"))
        assert "enhancement_suggestions" in report_data


# ═══════════════════════════════════════════════════════════════════
# Test Harvest (mocked to avoid real API calls)
# ═══════════════════════════════════════════════════════════════════


class TestRunHarvest:
    """Test the run_harvest function with mocks."""

    def test_harvest_returns_dict(self, tmp_path: Path) -> None:
        """run_harvest should always return a dict."""
        import researcher

        with patch.object(researcher, "DATA_DIR", tmp_path):
            result = researcher.run_harvest(paper_limit=5)

        assert isinstance(result, dict)

    def test_harvest_contains_expected_keys(self, tmp_path: Path) -> None:
        """run_harvest result should have expected structure."""
        import researcher

        with patch.object(researcher, "DATA_DIR", tmp_path):
            result = researcher.run_harvest(paper_limit=5)

        expected_keys = {"timestamp", "papers_collected", "books_indexed", "total_sources", "total_chunks", "duration_seconds", "github_repos_scanned", "errors"}
        assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"
        assert isinstance(result["papers_collected"], int)
        assert isinstance(result["duration_seconds"], (int, float))
        assert isinstance(result["errors"], list)

    def test_harvest_saves_summary(self, tmp_path: Path) -> None:
        """run_harvest should save summary to DATA_DIR."""
        import researcher

        with patch.object(researcher, "DATA_DIR", tmp_path):
            result = researcher.run_harvest(paper_limit=5)

        summary_file = tmp_path / "harvest_summary.json"
        assert summary_file.exists()
        saved = json.loads(summary_file.read_text(encoding="utf-8"))
        assert saved["timestamp"] == result["timestamp"]

    def test_harvest_counts_are_non_negative(self, tmp_path: Path) -> None:
        """All count fields should be >= 0."""
        import researcher

        with patch.object(researcher, "DATA_DIR", tmp_path):
            result = researcher.run_harvest(paper_limit=5)

        count_keys = ["papers_collected", "books_indexed", "total_sources", "total_chunks", "github_repos_scanned"]
        for key in count_keys:
            assert result[key] >= 0, f"{key} is negative: {result[key]}"


# ═══════════════════════════════════════════════════════════════════
# Test Query and Report Display
# ═══════════════════════════════════════════════════════════════════


class TestQueryKnowledge:
    """Test the query_knowledge function."""

    def test_query_does_not_crash_with_empty_query(self) -> None:
        """query_knowledge should handle empty string gracefully."""
        import researcher

        result = researcher.query_knowledge("")
        assert isinstance(result, list)


class TestShowReport:
    """Test the show_report function."""

    def test_show_report_no_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        """show_report with no report file should warn (not crash)."""
        import researcher

        with patch.object(researcher, "DATA_DIR", Path(tempfile.mkdtemp()) / "empty"):
            researcher.show_report()

        captured = capsys.readouterr()
        assert "No report found" in captured.out

    def test_show_report_with_corrupt_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        """show_report with corrupt JSON should warn (not crash)."""
        import researcher

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            report_file = data_dir / "enhancement_report.json"
            report_file.write_text("not valid json", encoding="utf-8")

            with patch.object(researcher, "DATA_DIR", data_dir):
                researcher.show_report()

        captured = capsys.readouterr()
        assert "Failed to read report" in captured.out

    def test_show_report_with_valid_report(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """show_report should display valid report."""
        import researcher

        report_data = {
            "report_timestamp": "2026-07-23T12:00:00+00:00",
            "knowledge_snapshot": {
                "papers_collected": 10,
                "books_indexed": 18,
                "total_sources": 28,
                "total_rag_chunks": 135,
                "harvest_duration_seconds": 5.0,
            },
            "enhancement_suggestions": {
                "total": 1,
                "high_priority": 1,
                "medium_priority": 0,
                "low_priority": 0,
                "items": [{"priority": "high", "area": "Test Area", "finding": "Test finding", "action": "Test action", "impact": "Test impact", "effort": "Low"}],
            },
        }
        report_file = tmp_path / "enhancement_report.json"
        report_file.write_text(json.dumps(report_data), encoding="utf-8")

        with patch.object(researcher, "DATA_DIR", tmp_path):
            researcher.show_report()

        captured = capsys.readouterr()
        assert "Papers collected" in captured.out
        assert "Test Area" in captured.out


# ═══════════════════════════════════════════════════════════════════
# Test Module Import
# ═══════════════════════════════════════════════════════════════════


class TestResearcherModule:
    """Test the researcher module can be imported and has expected exports."""

    def test_module_imports(self) -> None:
        """researcher module should import without errors."""
        import researcher

        assert researcher is not None

    def test_expected_functions_exist(self) -> None:
        """researcher module should expose expected public functions."""
        import researcher

        assert callable(researcher.run_harvest)
        assert callable(researcher.run_analysis)
        assert callable(researcher.run_full_pipeline)
        assert callable(researcher.run_continuous)
        assert callable(researcher.query_knowledge)
        assert callable(researcher.show_report)
        assert callable(researcher.main)

    def test_enhancement_analyzer_importable(self) -> None:
        """EnhancementAnalyzer class should be available."""
        import researcher

        analyzer = researcher.EnhancementAnalyzer()
        assert hasattr(analyzer, "suggestions")
        assert hasattr(analyzer, "analyze")
        assert hasattr(analyzer, "_detect_knowledge_gaps")
        assert hasattr(analyzer, "_generate_suggestions")
        assert hasattr(analyzer, "_build_report")
