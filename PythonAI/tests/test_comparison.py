"""Tests for the Model Comparison Dashboard module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from unittest.mock import MagicMock

from src.training.comparison import (
    AdapterResult,
    ComparisonReport,
    compute_bleu,
    discover_adapters,
    generate_html_report,
    load_adapter_config,
    run_comparison,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_results() -> list[AdapterResult]:
    return [
        AdapterResult(
            adapter_name="model_a",
            prompt="Explain context managers",
            output="Context managers manage resources via `with` blocks.",
            generation_time_s=1.2,
            output_length_chars=52,
            output_length_tokens=12,
            has_code=True,
            bleu_score=0.5,
        ),
        AdapterResult(
            adapter_name="model_b",
            prompt="Explain context managers",
            output="A context manager is used for resource management.",
            generation_time_s=2.5,
            output_length_chars=62,
            output_length_tokens=15,
            has_code=False,
            bleu_score=0.3,
        ),
    ]


@pytest.fixture
def sample_report(sample_results) -> ComparisonReport:
    return ComparisonReport(
        adapters=["model_a", "model_b"],
        prompts=["Explain context managers"],
        results=sample_results,
        timestamp="2025-01-01 12:00:00",
        total_adapters=2,
        total_prompts=1,
    )


# ── AdapterResult & ComparisonReport ──────────────────────────────────

class TestAdapterResult:
    def test_defaults(self) -> None:
        r = AdapterResult(
            adapter_name="test",
            prompt="Hello",
            output="World",
            generation_time_s=0.5,
            output_length_chars=5,
            output_length_tokens=2,
            has_code=False,
        )
        assert r.bleu_score == 0.0
        assert r.error is None

    def test_with_error(self) -> None:
        r = AdapterResult(
            adapter_name="err_model",
            prompt="Test",
            output="",
            generation_time_s=0,
            output_length_chars=0,
            output_length_tokens=0,
            has_code=False,
            error="CUDA out of memory",
        )
        assert r.error == "CUDA out of memory"


class TestComparisonReport:
    def test_to_dict_structure(self, sample_report: ComparisonReport) -> None:
        d = sample_report.to_dict()
        assert d["total_adapters"] == 2
        assert d["total_prompts"] == 1
        assert len(d["results"]) == 2
        assert d["results"][0]["adapter_name"] == "model_a"

    def test_to_dict_serializable(self, sample_report: ComparisonReport) -> None:
        d = sample_report.to_dict()
        json_str = json.dumps(d, ensure_ascii=False, indent=2)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["total_adapters"] == 2


# ── compute_bleu ──────────────────────────────────────────────────────

class TestComputeBleu:
    def test_exact_match(self) -> None:
        score = compute_bleu("hello world", "hello world")
        assert score == 1.0

    def test_partial_match(self) -> None:
        score = compute_bleu("the quick brown fox", "the quick blue fox")
        assert 0.5 < score < 1.0

    def test_no_match(self) -> None:
        score = compute_bleu("abc def", "xyz pqr")
        assert score == 0.0

    def test_empty_candidate(self) -> None:
        score = compute_bleu("some reference", "")
        assert score == 0.0


# ── load_adapter_config ───────────────────────────────────────────────

class TestLoadAdapterConfig:
    def test_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nonexistent"
            with pytest.raises(FileNotFoundError):
                load_adapter_config(p)

    def test_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "adapter_config.json"
            cfg_path.write_text(
                json.dumps({"base_model_name_or_path": "test-model", "r": 8}),
                encoding="utf-8",
            )
            cfg = load_adapter_config(Path(tmp))
            assert cfg["base_model_name_or_path"] == "test-model"
            assert cfg["r"] == 8


# ── discover_adapters ─────────────────────────────────────────────────

class TestDiscoverAdapters:
    def test_no_checkpoints_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When checkpoints dir doesn't exist, should return empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            monkeypatch.setattr("src.training.comparison.ROOT", fake_root)
            adapters = discover_adapters()
            assert adapters == []

    def test_finds_valid_adapters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            # Create a valid adapter directory
            adapter_dir = fake_root / "checkpoints" / "my_adapter"
            adapter_dir.mkdir(parents=True)
            (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
            (adapter_dir / "adapter_model.safetensors").write_text("fake", encoding="utf-8")

            # Create an invalid directory (missing safetensors)
            invalid_dir = fake_root / "checkpoints" / "incomplete"
            invalid_dir.mkdir(parents=True)
            (invalid_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

            monkeypatch.setattr("src.training.comparison.ROOT", fake_root)
            adapters = discover_adapters()
            assert len(adapters) == 1
            assert adapters[0].name == "my_adapter"


# ── generate_html_report ──────────────────────────────────────────────

class TestGenerateHtmlReport:
    def test_creates_html_file(self, sample_report: ComparisonReport) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            result = generate_html_report(sample_report, out_path)
            assert out_path.exists()
            assert result == str(out_path)

    def test_html_contains_adapter_names(self, sample_report: ComparisonReport) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            generate_html_report(sample_report, out_path)
            html = out_path.read_text(encoding="utf-8")
            assert "model_a" in html
            assert "model_b" in html

    def test_html_contains_prompts(self, sample_report: ComparisonReport) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            generate_html_report(sample_report, out_path)
            html = out_path.read_text(encoding="utf-8")
            assert "Explain context managers" in html

    def test_html_no_emoji_issues(self, sample_report: ComparisonReport) -> None:
        """Ensure no emoji characters that break Windows cp1252."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            generate_html_report(sample_report, out_path)
            html = out_path.read_text(encoding="utf-8")
            # Try encoding to cp1252 to verify Windows compatibility
            try:
                html.encode("cp1252")
            except UnicodeEncodeError as exc:
                pytest.fail(f"HTML contains characters not encodable in cp1252: {exc}")

    def test_stats_grid_present(self, sample_report: ComparisonReport) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            generate_html_report(sample_report, out_path)
            html = out_path.read_text(encoding="utf-8")
            assert "stats-grid" in html
            assert "Total Evaluations" in html or "total" in html.lower()


# ── run_comparison ────────────────────────────────────────────────────

class TestRunComparison:
    def test_no_adapters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            monkeypatch.setattr("src.training.comparison.ROOT", fake_root)
            adapters = discover_adapters()
            assert adapters == []

    def test_generates_report_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)

            # Create a mock adapter
            adapter_dir = fake_root / "checkpoints" / "test_adapter"
            adapter_dir.mkdir(parents=True)
            (adapter_dir / "adapter_config.json").write_text(
                json.dumps({"base_model_name_or_path": "sshleifer/tiny-gpt2"}),
                encoding="utf-8",
            )
            (adapter_dir / "adapter_model.safetensors").write_text("fake", encoding="utf-8")

            monkeypatch.setattr("src.training.comparison.ROOT", fake_root)

            # Mock evaluate_adapter to avoid loading real model/tokenizer
            mock_results = [
                AdapterResult(
                    adapter_name="test_adapter",
                    prompt="Test prompt",
                    output="Mock output",
                    generation_time_s=0.5,
                    output_length_chars=11,
                    output_length_tokens=3,
                    has_code=False,
                )
            ]
            monkeypatch.setattr(
                "src.training.comparison.evaluate_adapter",
                MagicMock(return_value=mock_results),
            )

            # Run comparison
            out_dir = "checkpoints/test_compare"
            report = run_comparison(
                [adapter_dir],
                prompts=["Test prompt"],
                max_new_tokens=8,
                output_dir=out_dir,
            )

            # Check report structure
            assert report.total_adapters == 1
            assert report.total_prompts == 1

            # Check output files created
            json_path = fake_root / out_dir / "comparison_report.json"
            html_path = fake_root / out_dir / "comparison_dashboard.html"
            assert json_path.exists()
            assert html_path.exists()


# ── main CLI ──────────────────────────────────────────────────────────

class TestMain:
    def test_importable(self) -> None:
        """Just verify the module can be imported cleanly."""
        import src.training.comparison  # noqa: F811
        assert hasattr(src.training.comparison, "main")
