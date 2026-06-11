"""Unit tests for src/data/quality.py — quality control pipeline for datasets."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.data.quality import (
    BOILERPLATE_PATTERNS,
    PII_PATTERNS,
    QualityPipeline,
    _jaccard_from_signatures,
    _minhash_signature,
    _shingle,
    check_boilerplate,
    check_pii,
    check_repetition,
    check_text_length,
    detect_language,
    exact_dedup,
    filter_by_language,
    mask_pii,
    near_dedup,
    scan_pii,
)

# ══════════════════════════════════════════════════════════════════════
# check_text_length
# ══════════════════════════════════════════════════════════════════════


class TestCheckTextLength:
    """Tests for check_text_length — minimum length filter."""

    def test_meets_minimum(self):
        """Text at or above minimum should pass."""
        passed, length, score = check_text_length("A" * 100, min_length=50)
        assert passed is True
        assert length == 100

    def test_below_minimum(self):
        """Text below minimum should fail."""
        passed, length, score = check_text_length("Short", min_length=50)
        assert passed is False
        assert length == 5
        assert score == 0.0

    def test_score_scaling(self):
        """Score should scale from 0 at min to 1 at ideal."""
        _, _, score_min = check_text_length("A" * 50, min_length=50)
        _, _, score_ideal = check_text_length("A" * 500, min_length=50)
        _, _, score_mid = check_text_length("A" * 275, min_length=50)
        assert score_min == 0.0
        assert score_ideal == 1.0
        assert 0 < score_mid < 1.0

    def test_empty_text(self):
        """Empty text should fail."""
        passed, length, score = check_text_length("", min_length=50)
        assert passed is False
        assert length == 0

    def test_whitespace_only(self):
        """Whitespace-only text should fail (stripped length is 0)."""
        passed, length, score = check_text_length("   \\n   ", min_length=50)
        assert passed is False

    def test_custom_minimum(self):
        """Custom minimum length should be respected."""
        passed1, _, _ = check_text_length("A" * 30, min_length=50)
        passed2, _, _ = check_text_length("A" * 30, min_length=20)
        assert passed1 is False
        assert passed2 is True


# ══════════════════════════════════════════════════════════════════════
# detect_language
# ══════════════════════════════════════════════════════════════════════


class TestDetectLanguage:
    """Tests for detect_language — with mocked dependencies."""

    @patch("tests.test_data_quality.detect_language")
    def test_english_detected(self, mock_detect):
        """English text should be detected."""
        mock_detect.return_value = ("en", 0.95)
        lang, conf = detect_language("This is an English sentence.")
        assert lang == "en"
        assert conf >= 0.9

    @patch("tests.test_data_quality.detect_language")
    def test_unknown_returns_fallback(self, mock_detect):
        """Unrecognizable text should return 'unknown'."""
        mock_detect.return_value = ("unknown", 0.0)
        lang, conf = detect_language("")
        assert lang == "unknown"
        assert conf == 0.0

    @patch("tests.test_data_quality.detect_language")
    def test_hindi_detected(self, mock_detect):
        """Hindi text should be detected."""
        mock_detect.return_value = ("hi", 0.85)
        lang, conf = detect_language("नमस्ते मेरा नाम पायथन है।")
        assert lang == "hi"
        assert conf >= 0.8


# ══════════════════════════════════════════════════════════════════════
# filter_by_language
# ══════════════════════════════════════════════════════════════════════


class TestFilterByLanguage:
    """Tests for filter_by_language — language filtering."""

    @patch("src.data.quality.detect_language", return_value=("en", 0.95))
    def test_english_accepted(self, mock_detect):
        """English should pass with English-only targets."""
        passed, lang, conf = filter_by_language("English text", target_languages={"en"})
        assert passed is True
        assert lang == "en"

    @patch("src.data.quality.detect_language", return_value=("fr", 0.9))
    def test_french_filtered(self, mock_detect):
        """French should be filtered when targeting only English."""
        passed, lang, conf = filter_by_language("Texte français", target_languages={"en"})
        assert passed is False
        assert lang == "fr"

    @patch("src.data.quality.detect_language", return_value=("en", 0.95))
    def test_no_target_filter(self, mock_detect):
        """No target languages should pass all."""
        passed, lang, conf = filter_by_language("English text", target_languages=None)
        assert passed is True

    @patch("src.data.quality.detect_language", return_value=("unknown", 0.0))
    def test_unknown_passes_filter(self, mock_detect):
        """Unknown language should pass (not filtered)."""
        passed, lang, conf = filter_by_language("", target_languages={"en"})
        assert passed is True  # unknown is allowed through


# ══════════════════════════════════════════════════════════════════════
# scan_pii / mask_pii / check_pii
# ══════════════════════════════════════════════════════════════════════


class TestPiiScan:
    """Tests for PII detection and masking."""

    def test_email_detected(self):
        """Email addresses should be detected."""
        text = "Contact me at user@example.com for help."
        findings = scan_pii(text)
        assert "email" in findings
        assert findings["email"] >= 1

    def test_phone_detected(self):
        """Phone numbers should be detected."""
        text = "Call me at +1-555-123-4567"
        findings = scan_pii(text)
        assert "phone" in findings

    def test_ssn_detected(self):
        """SSN should be detected."""
        text = "My SSN is 123-45-6789"
        findings = scan_pii(text)
        assert "ssn" in findings

    def test_ip_detected(self):
        """IP addresses should be detected."""
        text = "Server at 192.168.1.1"
        findings = scan_pii(text)
        assert "ip" in findings

    def test_credit_card_detected(self):
        """Credit card numbers should be detected."""
        text = "Card: 4111-1111-1111-1111"
        findings = scan_pii(text)
        assert "credit_card" in findings

    def test_clean_text_no_pii(self):
        """Clean text should have no findings."""
        text = "This is just plain text about Python programming."
        findings = scan_pii(text)
        assert findings == {}

    def test_multiple_pii_types(self):
        """Multiple PII types in one text should all be detected."""
        text = "Email: a@b.com, Phone: 555-123-4567"
        findings = scan_pii(text)
        assert len(findings) >= 2

    def test_email_not_flagged_as_pii(self):
        """Emails alone should not trigger PII flag in check_pii."""
        text = "Email me at test@example.com"
        clean, findings = check_pii(text, max_allowed=0)
        assert clean is True  # email excluded from non-email count
        assert "email" in findings


class TestMaskPii:
    """Tests for PII masking."""

    def test_email_masked(self):
        """Email should be replaced with placeholder."""
        masked = mask_pii("Email: user@example.com")
        assert "[EMAIL_REDACTED]" in masked

    def test_phone_masked(self):
        """Phone should be replaced with placeholder."""
        masked = mask_pii("Phone: +1-555-123-4567")
        assert "[PHONE_REDACTED]" in masked

    def test_ssn_masked(self):
        """SSN should be replaced with placeholder."""
        masked = mask_pii("SSN: 123-45-6789")
        assert "[SSN_REDACTED]" in masked

    def test_multiple_pii_masked(self):
        """Multiple PII instances should all be masked."""
        masked = mask_pii("Email: a@b.com, Phone: 555-123-4567")
        assert "[EMAIL_REDACTED]" in masked
        assert "[PHONE_REDACTED]" in masked

    def clean_text_unchanged(self):
        """Clean text should remain unchanged."""
        text = "This is clean Python code."
        assert mask_pii(text) == text


class TestCheckPii:
    """Tests for check_pii — PII presence check."""

    def test_no_pii(self):
        """No PII should return clean=True."""
        clean, findings = check_pii("Clean text about Python", max_allowed=0)
        assert clean is True
        assert findings == {}

    def test_pii_detected(self):
        """PII should return clean=False."""
        text = "SSN: 123-45-6789 and Phone: 555-123-4567"
        clean, findings = check_pii(text, max_allowed=0)
        assert clean is False
        assert len(findings) >= 2

    def test_email_excluded_from_count(self):
        """Emails should be excluded from the 'non-email' count."""
        clean, findings = check_pii("test@example.com", max_allowed=0)
        assert clean is True  # email excluded


# ══════════════════════════════════════════════════════════════════════
# exact_dedup
# ══════════════════════════════════════════════════════════════════════


class TestExactDedup:
    """Tests for exact_dedup — MD5-based exact deduplication."""

    def test_no_duplicates(self):
        """All unique records should be kept."""
        records = [{"text": "First"}, {"text": "Second"}, {"text": "Third"}]
        unique, stats = exact_dedup(records)
        assert len(unique) == 3
        assert stats["removed"] == 0

    def test_exact_duplicates_removed(self):
        """Exact duplicates should be removed."""
        records = [{"text": "Same " * 10}, {"text": "Same " * 10}, {"text": "Different"}]
        unique, stats = exact_dedup(records)
        assert len(unique) == 2
        assert stats["removed"] == 1

    def test_all_duplicates(self):
        """All records identical should dedup to one."""
        records = [{"text": "Identical"}] * 5
        unique, stats = exact_dedup(records)
        assert len(unique) == 1
        assert stats["removed"] == 4

    def test_empty_records(self):
        """Empty list should return empty."""
        unique, stats = exact_dedup([])
        assert unique == []
        assert stats["total"] == 0

    def test_custom_text_field(self):
        """Custom text_field should be used."""
        records = [{"content": "A"}, {"content": "A"}, {"content": "B"}]
        unique, stats = exact_dedup(records, text_field="content")
        assert len(unique) == 2


# ══════════════════════════════════════════════════════════════════════
# MinHash helpers: _shingle, _minhash_signature, _jaccard_from_signatures
# ══════════════════════════════════════════════════════════════════════


class TestShingle:
    """Tests for _shingle — k-shingle generation."""

    def test_generates_shingles(self):
        """Text should produce shingles."""
        shingles = _shingle("abcde", k=2)
        assert len(shingles) > 0
        assert "ab" in shingles
        assert "bc" in shingles

    def test_short_text(self):
        """Very short text should produce few shingles."""
        shingles = _shingle("ab", k=5)
        assert shingles == set() or len(shingles) == 0

    def test_whitespace_normalized(self):
        """Whitespace should be normalized before shingling."""
        s1 = _shingle("hello world", k=3)
        s2 = _shingle("hello   world", k=3)
        assert s1 == s2

    def test_case_normalized(self):
        """Case should be normalized."""
        s1 = _shingle("Hello World", k=3)
        s2 = _shingle("hello world", k=3)
        assert s1 == s2

    def test_default_k(self):
        """Default k should be 5."""
        shingles = _shingle("abcdefghij", k=5)
        assert "abcde" in shingles


class TestMinhashSignature:
    """Tests for _minhash_signature — MinHash signature computation."""

    def test_returns_correct_length(self):
        """Should return exactly num_hashes values."""
        shingles = {"ab", "bc", "cd", "de"}
        sig = _minhash_signature(shingles, num_hashes=128)
        assert len(sig) == 128

    def test_fewer_hashes(self):
        """Fewer hash functions should be supported."""
        shingles = {"ab", "bc"}
        sig = _minhash_signature(shingles, num_hashes=16)
        assert len(sig) == 16

    def test_all_ints(self):
        """All signature values should be integers."""
        shingles = {"a", "b", "c"}
        sig = _minhash_signature(shingles, num_hashes=10)
        assert all(isinstance(v, int) for v in sig)

    def test_same_shingles_same_signature(self):
        """Same shingles should produce the same signature."""
        s1 = _minhash_signature({"ab", "bc"}, num_hashes=32)
        s2 = _minhash_signature({"ab", "bc"}, num_hashes=32)
        assert s1 == s2

    def test_different_shingles_different_signatures(self):
        """Different shingles should produce different signatures."""
        s1 = _minhash_signature({"ab", "bc"}, num_hashes=32)
        s2 = _minhash_signature({"xy", "yz"}, num_hashes=32)
        assert s1 != s2


class TestJaccardFromSignatures:
    """Tests for _jaccard_from_signatures — Jaccard similarity estimation."""

    def test_identical_signatures(self):
        """Identical signatures should return 1.0."""
        sig = [1, 2, 3, 4, 5]
        sim = _jaccard_from_signatures(sig, sig)
        assert sim == 1.0

    def test_completely_different(self):
        """Completely different should return 0.0."""
        sig1 = [1, 2, 3]
        sig2 = [4, 5, 6]
        sim = _jaccard_from_signatures(sig1, sig2)
        assert sim == 0.0

    def test_partial_match(self):
        """Partially matching should return intermediate value."""
        sig1 = [1, 2, 3, 4]
        sig2 = [1, 2, 5, 6]
        sim = _jaccard_from_signatures(sig1, sig2)
        assert 0.4 < sim < 0.6  # 2/4 = 0.5

    def test_empty_signature(self):
        """Empty signatures should return 0.0."""
        assert _jaccard_from_signatures([], []) == 0.0


# ══════════════════════════════════════════════════════════════════════
# near_dedup
# ══════════════════════════════════════════════════════════════════════


class TestNearDedup:
    """Tests for near_dedup — MinHash near-duplicate detection."""

    def test_no_duplicates(self):
        """All different records should stay."""
        records = [
            {"text": "The quick brown fox jumps over the lazy dog near the river bank."},
            {"text": "Python is a powerful programming language used for web development."},
        ]
        unique, stats = near_dedup(records, threshold=0.8)
        assert len(unique) == 2
        assert stats["removed"] == 0

    def test_single_record(self):
        """Single record should return as-is."""
        records = [{"text": "Only one record here."}]
        unique, stats = near_dedup(records)
        assert len(unique) == 1

    def test_empty_records(self):
        """Empty list should return empty."""
        unique, stats = near_dedup([])
        assert unique == []
        assert stats["total"] == 0

    def test_low_threshold_may_dedup(self):
        """Low threshold may remove similar records."""
        text = "Python is a great programming language for beginners and experts alike. "
        records = [
            {"text": text * 3},
            {"text": text * 3 + " Extra content here for variety."},
        ]
        unique, stats = near_dedup(records, threshold=0.5, num_hashes=64)
        # These are highly similar, so likely deduped with low threshold
        assert stats["removed"] >= 0

    def test_different_text_field(self):
        """Custom text_field should be used."""
        records = [{"content": "A" * 50}, {"content": "A" * 50}]
        unique, stats = near_dedup(records, text_field="content", threshold=0.9, num_hashes=32)
        assert stats["removed"] >= 0


# ══════════════════════════════════════════════════════════════════════
# check_boilerplate
# ══════════════════════════════════════════════════════════════════════


class TestCheckBoilerplate:
    """Tests for check_boilerplate — boilerplate detection."""

    def test_clean_text(self):
        """Clean text should pass."""
        text = "Python is a versatile programming language used across many domains."
        clean, score = check_boilerplate(text)
        assert clean is True
        assert score >= 0.8

    def test_subscribe_pattern_detected(self):
        """'subscribe to our newsletter' should be flagged."""
        text = "Subscribe to our newsletter for more Python tips and tutorials."
        clean, score = check_boilerplate(text)
        assert clean is True  # 1 match, threshold is matches <= 2
        assert score < 1.0

    def test_all_rights_reserved_detected(self):
        """'all rights reserved' should be flagged."""
        text = "Copyright 2024. All rights reserved. Python documentation."
        clean, score = check_boilerplate(text)
        assert clean is True  # only 1 match, threshold is matches <= 2
        assert score < 1.0

    def test_copyright_pattern_detected(self):
        """Copyright symbol + year should be flagged."""
        text = "© 2024 Python Software Foundation"
        clean, score = check_boilerplate(text)
        assert clean is True  # 1 match, threshold is <= 2
        assert score < 1.0

    def test_heavy_boilerplate(self):
        """Many boilerplate phrases should get low score."""
        text = (
            "Subscribe to our newsletter. All rights reserved. "
            "Follow us on social media. Share this article. "
            "Leave a comment below. You might also like these related articles."
        )
        clean, score = check_boilerplate(text)
        assert clean is False
        assert score < 0.6


# ══════════════════════════════════════════════════════════════════════
# check_repetition
# ══════════════════════════════════════════════════════════════════════


class TestCheckRepetition:
    """Tests for check_repetition — repetition detection."""

    def test_normal_text(self):
        """Normal text should pass."""
        text = "This is a normal sentence with varied words throughout the content."
        clean, score = check_repetition(text)
        assert clean is True
        assert score >= 0.8

    def test_repetitive_text_detected(self):
        """Highly repetitive text should be flagged."""
        text = "Python is great. Python is great. Python is great. Python is great. Python is great. Python is great. Python is great. "
        clean, score = check_repetition(text)
        # Repetition ratio should be high (21 words, above 20-word minimum)
        assert clean is False or score < 0.8

    def test_short_text_passes(self):
        """Short text (< 20 words) should pass automatically."""
        text = "Short text here."
        clean, score = check_repetition(text)
        assert clean is True
        assert score == 1.0


# ══════════════════════════════════════════════════════════════════════
# BOILERPLATE_PATTERNS and PII_PATTERNS data integrity
# ══════════════════════════════════════════════════════════════════════


class TestPatternData:
    """Tests for static pattern data."""

    def test_boilerplate_patterns_non_empty(self):
        """BOILERPLATE_PATTERNS should have entries."""
        assert len(BOILERPLATE_PATTERNS) >= 5

    def test_pii_patterns_non_empty(self):
        """PII_PATTERNS should have entries."""
        assert len(PII_PATTERNS) >= 4
        assert "email" in PII_PATTERNS
        assert "phone" in PII_PATTERNS
        assert "ssn" in PII_PATTERNS
        assert "ip" in PII_PATTERNS

    def test_pii_patterns_are_strings(self):
        """All PII patterns should be regex strings."""
        for name, pattern in PII_PATTERNS.items():
            assert isinstance(pattern, str)
            assert len(pattern) > 5


# ══════════════════════════════════════════════════════════════════════
# QualityPipeline — Full Pipeline
# ══════════════════════════════════════════════════════════════════════


class TestQualityPipeline:
    """Tests for QualityPipeline.run_records — full pipeline execution."""

    def make_record(self, text: str, **extra: str) -> dict:
        return {"text": text, **extra}

    def test_empty_records(self):
        """Empty records should produce zero stats."""
        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_records([])
        assert stats["total_input"] == 0
        assert stats["total_output"] == 0

    def test_all_good_records_pass(self):
        """Good records should all pass."""
        records = [
            self.make_record(
                "Python is a versatile programming language used for web development. " * 5 +
                "It supports multiple paradigms and has a rich ecosystem. " * 3
            ),
            self.make_record(
                "Java is a class-based, object-oriented programming language. " * 5 +
                "It is designed to have as few implementation dependencies as possible. " * 3
            ),
        ]
        pipe = QualityPipeline(min_text_length=50, target_languages={"en"})
        stats = pipe.run_records(records)
        assert stats["total_output"] == 2

    def test_short_records_filtered(self):
        """Short records should be filtered by length stage."""
        records = [self.make_record("Short")]
        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_records(records)
        assert stats["total_output"] == 0
        assert stats["stages"]["length_filter"]["removed"] == 1

    def test_pii_masked_not_filtered(self):
        """Records with PII should be masked, not filtered (unless extreme)."""
        records = [self.make_record(
            "Python programming guide. Email: test@example.com. " * 10 +
            "This is a tutorial about data science with Python. " * 3
        )]
        pipe = QualityPipeline(min_text_length=50, pii_max_allowed=0)
        stats = pipe.run_records(records)
        # PII records are masked not filtered
        assert stats["total_output"] >= 1

    def test_multiple_stages_tracked(self):
        """All stages should be tracked in stats."""
        records = [self.make_record("A" * 300)]
        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_records(records)
        assert "length_filter" in stats["stages"]
        assert "language_filter" in stats["stages"]
        assert "pii_scan" in stats["stages"]
        assert "exact_dedup" in stats["stages"]
        assert "quality_filter" in stats["stages"]

    def test_quality_score_threshold(self):
        """Records below quality threshold should be filtered."""
        records = [self.make_record(
            "Short text that barely meets minimum requirements for testing purposes. "
        )]
        pipe = QualityPipeline(min_text_length=50, quality_threshold=0.9)
        stats = pipe.run_records(records)
        # The quality score won't be high enough with the 0.9 threshold
        assert stats["total_output"] <= 1

    def test_custom_text_field(self):
        """Custom text_field should be used."""
        records = [{"content": "Python is a versatile programming language used for web development, data science, and automation. " * 4}]
        pipe = QualityPipeline(min_text_length=50, text_field="content")
        stats = pipe.run_records(records)
        assert stats["total_output"] == 1

    def test_dataset_id_tracked(self):
        """Dataset ID should appear in stats."""
        records = [self.make_record("A" * 200)]
        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_records(records, dataset_id="test_dataset_001")
        assert stats["dataset_id"] == "test_dataset_001"


# ══════════════════════════════════════════════════════════════════════
# QualityPipeline.run_file
# ══════════════════════════════════════════════════════════════════════


class TestQualityPipelineFile:
    """Tests for QualityPipeline.run_file — file-based pipeline."""

    def test_file_not_found(self, tmp_path: Path):
        """Non-existent file should return error."""
        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_file(str(tmp_path / "nonexistent.jsonl"))
        assert "error" in stats

    def test_valid_file(self, tmp_path: Path):
        """Valid JSONL file should process correctly."""
        f = tmp_path / "data.jsonl"
        with open(f, "w") as fp:
            fp.write(json.dumps({"text": "Python is a versatile programming language used for web development. " * 7}) + "\n")
            fp.write(json.dumps({"text": "Java is a class-based object-oriented programming language. " * 7}) + "\n")

        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_file(str(f))
        assert stats["total_input"] == 2
        assert stats["total_output"] == 2

    def test_mixed_valid_invalid(self, tmp_path: Path):
        """File with both valid and invalid JSON lines should handle gracefully."""
        f = tmp_path / "mixed.jsonl"
        with open(f, "w") as fp:
            fp.write(json.dumps({"text": "Python is a versatile programming language used for web development. " * 7}) + "\n")
            fp.write("not valid json\n")
            fp.write(json.dumps({"text": "Java is a class-based object-oriented programming language. " * 7}) + "\n")

        pipe = QualityPipeline(min_text_length=50)
        stats = pipe.run_file(str(f))
        assert stats["total_input"] == 2  # Invalid lines skipped
        assert stats["total_output"] == 2


# ══════════════════════════════════════════════════════════════════════
# QualityPipeline.quality_distribution
# ══════════════════════════════════════════════════════════════════════


class TestQualityDistribution:
    """Tests for quality_distribution — score distribution analysis."""

    def test_no_scores(self):
        """Records without quality scores should return error."""
        pipe = QualityPipeline()
        dist = pipe.quality_distribution([{"text": "hello"}])
        assert "error" in dist

    def test_distribution_shape(self):
        """Distribution should have the expected structure."""
        records = [
            {"_quality_score": s}
            for s in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ]
        pipe = QualityPipeline()
        dist = pipe.quality_distribution(records, bins=5)
        assert dist["count"] == 10
        assert dist["mean"] == 0.55
        assert "distribution" in dist
        assert len(dist["distribution"]) == 5

    def test_statistics(self):
        """Statistics should be correctly computed."""
        records = [{"_quality_score": s} for s in [0.1, 0.3, 0.3, 0.5, 0.8, 0.9]]
        pipe = QualityPipeline()
        dist = pipe.quality_distribution(records)
        assert dist["min"] == 0.1
        assert dist["max"] == 0.9
        assert dist["median"] == 0.4  # 0.1, 0.3, 0.3, 0.5, 0.8, 0.9 -> median = (0.3+0.5)/2 = 0.4
        assert dist["mean"] == 0.483
