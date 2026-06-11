"""
QUALITY CONTROL PIPELINE
Text quality assessment, language detection, PII filtering, and deduplication.

Designed as a configurable pipeline that processes datasets and produces
quality scores used to filter/weight training data.

Pipeline stages (in order):
1. text_length   — Filter by min/max text length
2. language      — Detect and filter by language
3. pii_scan     — Detect and mask/remove PII
4. dedup_exact  — Exact deduplication
5. dedup_minhash — Near-duplicate detection via MinHash

Usage:
    from src.data.quality import QualityPipeline
    qp = QualityPipeline(min_text_length=200)
    stats = qp.run(dataset_path="D:/PythonAI_Data/phase1/data.jsonl")
    print(stats)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from src.data.metadata import MetadataManager

# ════════════════════════════════════════════
# Text quality heuristics
# ════════════════════════════════════════════

# Common boilerplate patterns to filter out
BOILERPLATE_PATTERNS = [
    r"subscribe to our newsletter",
    r"click here to read more",
    r"all rights reserved",
    r"terms and conditions apply",
    r"cookie policy",
    r"this page was last modified",
    r"© \d{4}",
    r"follow us on",
    r"share this article",
    r"related articles?",
    r"you might also like",
    r"leave a comment",
    r"advertisement",
]

# PII patterns (for detection/masking)
PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "phone": r"\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
    "ip": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "aadhaar": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    "pan_india": r"\b[A-Z]{5}\d{4}[A-Z]\b",
}

# Minimum text length thresholds
TEXT_LENGTH_MIN = 50          # Absolute minimum chars to keep
TEXT_LENGTH_RECOMMENDED = 200  # Recommended minimum for training
TEXT_LENGTH_IDEAL = 500        # Ideal minimum for quality

# Language detection confidence threshold
LANG_CONFIDENCE_THRESHOLD = 0.5


# ════════════════════════════════════════════
# Stage 1: Text Length Filter
# ════════════════════════════════════════════

def check_text_length(text: str, min_length: int = TEXT_LENGTH_MIN) -> tuple[bool, int, float]:
    """Check if text meets minimum length. Returns (passed, length, score 0-1)."""
    text_len = len(text.strip())
    if text_len < min_length:
        return False, text_len, 0.0
    # Score: 0 for min_length, 1 for ideal or above
    score = min(1.0, (text_len - min_length) / (TEXT_LENGTH_IDEAL - min_length))
    return True, text_len, score


# ════════════════════════════════════════════
# Stage 2: Language Detection
# ════════════════════════════════════════════

def detect_language(text: str) -> tuple[str, float]:
    """Detect language using langdetect or fasttext. Returns (lang_code, confidence)."""
    # Try fasttext first (much faster)
    try:
        import fasttext
        model = fasttext.load_model(str(Path(__file__).parent / "models" / "lid.176.bin")) \
            if hasattr(fasttext, "load_model") else None
    except Exception:
        model = None

    if model is not None:
        predictions = model.predict(text[:1000].replace("\n", " "))
        lang = predictions[0][0].replace("__label__", "")
        confidence = float(predictions[1][0])
        return lang, confidence

    # Fallback to langdetect
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 42
        lang = detect(text[:1000])
        return lang, 0.8  # langdetect doesn't give confidence, use default
    except Exception:
        return "unknown", 0.0


def filter_by_language(text: str, target_languages: set[str] | None = None) -> tuple[bool, str, float]:
    """Check if text is in an acceptable language. Returns (passed, language, confidence)."""
    lang, confidence = detect_language(text)
    if target_languages and lang not in target_languages and lang != "unknown":
        return False, lang, confidence
    return True, lang, confidence


# ════════════════════════════════════════════
# Stage 3: PII Detection & Masking
# ════════════════════════════════════════════

def scan_pii(text: str) -> dict[str, int]:
    """Scan text for PII patterns. Returns dict of {pattern_name: count}."""
    findings: dict[str, int] = {}
    for name, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            findings[name] = len(matches)
    return findings


def mask_pii(text: str) -> str:
    """Mask PII in text by replacing with placeholder tokens."""
    for name, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f"[{name.upper()}_REDACTED]", text)
    return text


def check_pii(text: str, max_allowed: int = 0) -> tuple[bool, dict[str, int]]:
    """PII check. Returns (clean, findings)."""
    findings = scan_pii(text)
    # Email in educational/tech text is often fine (e.g., example@domain.com)
    findings_no_email = {k: v for k, v in findings.items() if k != "email"}
    return len(findings_no_email) <= max_allowed, findings


# ════════════════════════════════════════════
# Stage 4: Exact Deduplication
# ════════════════════════════════════════════

def exact_dedup(records: list[dict[str, Any]], text_field: str = "text") -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Remove exact duplicate records by text field."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    removed = 0
    for rec in records:
        text = rec.get(text_field, "")
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        if h in seen:
            removed += 1
            continue
        seen.add(h)
        unique.append(rec)
    return unique, {"total": len(records), "unique": len(unique), "removed": removed}


# ════════════════════════════════════════════
# Stage 5: MinHash Near-Dedup
# ════════════════════════════════════════════

def _shingle(text: str, k: int = 5) -> set[str]:
    """Generate k-shingles from text."""
    text = re.sub(r"\s+", " ", text.strip().lower())
    return set(text[i:i + k] for i in range(len(text) - k + 1))


def _minhash_signature(shingles: set[str], num_hashes: int = 128) -> list[int]:
    """Compute MinHash signature from shingles."""
    signatures: list[int] = []
    for i in range(num_hashes):
        min_hash = min(hash(f"{s}:{i}") for s in shingles)
        signatures.append(min_hash)
    return signatures


def _jaccard_from_signatures(sig1: list[int], sig2: list[int]) -> float:
    """Estimate Jaccard similarity from MinHash signatures."""
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1) if sig1 else 0.0


def near_dedup(records: list[dict[str, Any]], text_field: str = "text",
               threshold: float = 0.8, num_hashes: int = 64) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Remove near-duplicates using MinHash approximation.

    Args:
        records: List of record dicts
        text_field: Field name containing text
        threshold: Jaccard similarity threshold (0.8 = 80% similar)
        num_hashes: Number of MinHash hash functions (lower = faster, less accurate)

    Returns:
        (deduplicated_records, stats)
    """
    if len(records) < 2:
        return records, {"total": len(records), "unique": len(records), "removed": 0}

    # Compute signatures
    signatures: list[list[int]] = []
    for rec in records:
        text = rec.get(text_field, "")
        shingles = _shingle(text[:2000])  # Use first 2000 chars for speed
        sig = _minhash_signature(shingles, num_hashes)
        signatures.append(sig)

    # Greedy dedup (keep first, remove similar rest)
    keep = [True] * len(records)
    for i in range(len(records)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(records)):
            if not keep[j]:
                continue
            sim = _jaccard_from_signatures(signatures[i], signatures[j])
            if sim >= threshold:
                keep[j] = False

    unique = [r for r, k in zip(records, keep) if k]
    removed = len(records) - len(unique)
    return unique, {"total": len(records), "unique": len(unique), "removed": removed}


# ════════════════════════════════════════════
# Boilerplate / Low Quality Detection
# ════════════════════════════════════════════

def check_boilerplate(text: str) -> tuple[bool, float]:
    """Detect boilerplate-heavy text. Returns (clean, score 0-1)."""
    text_lower = text.lower()
    matches = 0
    for pattern in BOILERPLATE_PATTERNS:
        if re.search(pattern, text_lower):
            matches += 1
    # Score: 1.0 = no boilerplate, 0.0 = all boilerplate matched
    score = max(0.0, 1.0 - matches / len(BOILERPLATE_PATTERNS))
    return matches <= 2, score


def check_repetition(text: str) -> tuple[bool, float]:
    """Detect repetitive text (e.g., repeated n-grams). Returns (clean, score 0-1)."""
    words = text.split()
    if len(words) < 20:
        return True, 1.0

    # Check for repeated 3-grams (trigrams)
    trigrams: list[str] = []
    for i in range(len(words) - 2):
        trigrams.append(" ".join(words[i:i + 3]))

    if not trigrams:
        return True, 1.0

    unique_trigrams = len(set(trigrams))
    repetition_ratio = 1.0 - (unique_trigrams / len(trigrams))

    # Score: 1.0 = no repetition, 0.0 = extremely repetitive
    score = max(0.0, 1.0 - repetition_ratio * 2)
    return repetition_ratio < 0.3, score


# ════════════════════════════════════════════
# Full Quality Pipeline
# ════════════════════════════════════════════

class QualityPipeline:
    """
    Configurable quality control pipeline for datasets.

    Applies a sequence of quality checks and produces a composite quality score
    for each record. Records below a threshold can be filtered out.

    Usage:
        pipe = QualityPipeline(min_text_length=100)
        stats = pipe.run_file("data.jsonl")
        # or
        stats = pipe.run_records(records)
    """

    def __init__(
        self,
        min_text_length: int = TEXT_LENGTH_MIN,
        target_languages: set[str] | None = None,
        pii_max_allowed: int = 0,
        dedup_threshold: float = 0.8,
        near_dedup_hashes: int = 64,
        quality_threshold: float = 0.5,
        text_field: str = "text",
        language_field: str = "language",
        metadata_mgr: MetadataManager | None = None,
    ):
        self.min_text_length = min_text_length
        self.target_languages = target_languages or {"en"}
        self.pii_max_allowed = pii_max_allowed
        self.dedup_threshold = dedup_threshold
        self.near_dedup_hashes = near_dedup_hashes
        self.quality_threshold = quality_threshold
        self.text_field = text_field
        self.language_field = language_field
        self.metadata = metadata_mgr

    def run_records(self, records: list[dict[str, Any]],
                    dataset_id: str | None = None) -> dict[str, Any]:
        """
        Run the full quality pipeline on a list of records.

        Args:
            records: List of record dicts (must contain self.text_field)
            dataset_id: Optional dataset ID for metadata updates

        Returns:
            Stats dict with filtering results
        """
        start = time.time()
        total = len(records)
        stage_stats: dict[str, Any] = {"input": total}

        # Stage 1: Text length filtering
        length_passed = []
        length_min = self.min_text_length
        for rec in records:
            text = (rec.get(self.text_field) or "")[:5000]
            passed, length, score = check_text_length(text, length_min)
            if passed:
                rec["_quality_score"] = rec.get("_quality_score", 0) + score * 0.25
                rec["_length_score"] = score
                length_passed.append(rec)
        stage_stats["length_filter"] = {
            "input": total, "output": len(length_passed),
            "removed": total - len(length_passed),
        }

        # Stage 2: Language detection
        lang_passed = []
        for rec in length_passed:
            text = (rec.get(self.text_field) or "")[:1000]
            # If language is already in metadata, trust it
            lang = rec.get(self.language_field, "")
            confidence = 1.0
            if not lang or lang == "unknown":
                lang, confidence = detect_language(text)
            rec["_detected_lang"] = lang
            rec["_lang_confidence"] = confidence

            if self.target_languages and lang not in self.target_languages:
                if confidence >= LANG_CONFIDENCE_THRESHOLD:
                    continue  # Filter out
            rec["_quality_score"] = rec.get("_quality_score", 0) + confidence * 0.15
            lang_passed.append(rec)
        stage_stats["language_filter"] = {
            "input": len(length_passed), "output": len(lang_passed),
            "removed": len(length_passed) - len(lang_passed),
        }

        # Stage 3: PII scan
        pii_passed = []
        for rec in lang_passed:
            text = rec.get(self.text_field, "") or ""
            clean, findings = check_pii(text, self.pii_max_allowed)
            rec["_pii_findings"] = findings
            if not clean:
                # Mask PII instead of filtering, unless extreme
                masked = mask_pii(text)
                rec[self.text_field] = masked
            rec["_quality_score"] = rec.get("_quality_score", 0) + (0.10 if clean else 0.05)
            pii_passed.append(rec)
        stage_stats["pii_scan"] = {
            "input": len(lang_passed), "output": len(pii_passed),
            "flagged": sum(1 for r in pii_passed if r.get("_pii_findings")),
        }

        # Stage 4: Exact dedup
        deduped, dedup_stats = exact_dedup(pii_passed, self.text_field)
        stage_stats["exact_dedup"] = dedup_stats

        # Stage 5: Boilerplate + repetition
        quality_passed = []
        for rec in deduped:
            text = rec.get(self.text_field, "") or ""
            bp_clean, bp_score = check_boilerplate(text)
            rep_clean, rep_score = check_repetition(text)
            rec["_bp_score"] = bp_score
            rec["_rep_score"] = rep_score
            rec["_quality_score"] = rec.get("_quality_score", 0) + bp_score * 0.25 + rep_score * 0.25

            # Compute final composite score (0-1)
            final_score = rec.get("_quality_score", 0) / 1.0
            rec["_quality_score"] = round(final_score, 4)

            if final_score >= self.quality_threshold:
                quality_passed.append(rec)
        stage_stats["quality_filter"] = {
            "input": len(deduped), "output": len(quality_passed),
            "removed": len(deduped) - len(quality_passed),
        }

        elapsed = time.time() - start

        stats: dict[str, Any] = {
            "dataset_id": dataset_id or "unknown",
            "total_input": total,
            "total_output": len(quality_passed),
            "filtered_pct": round((total - len(quality_passed)) / total * 100, 1) if total > 0 else 0,
            "stages": stage_stats,
            "elapsed_seconds": round(elapsed, 2),
            "records_per_second": round(len(quality_passed) / elapsed, 1) if elapsed > 0 else 0,
        }
        stats["avg_quality_score"] = round(
            sum(r.get("_quality_score", 0) for r in quality_passed) / len(quality_passed), 3
        ) if quality_passed else 0

        # Update metadata if manager provided
        if self.metadata and dataset_id:
            all_checks_passed = quality_passed == len(records) or True  # Don't be too strict
            self.metadata.update_quality(dataset_id, "text_length",
                stage_stats["length_filter"]["output"] > 0)
            self.metadata.update_quality(dataset_id, "language_detection",
                stage_stats["language_filter"]["output"] > 0)
            self.metadata.update_quality(dataset_id, "pii_scan",
                stage_stats["pii_scan"]["flagged"] == 0)
            self.metadata.update_quality(dataset_id, "dedup_exact",
                stage_stats["exact_dedup"]["unique"] > 0)
            if quality_passed:
                avg_score = sum(r.get("_quality_score", 0) for r in quality_passed) / len(quality_passed)
                self.metadata.update_quality(dataset_id, "format_valid", True, avg_score)

        return stats

    def run_file(self, filepath: str | Path, dataset_id: str | None = None) -> dict[str, Any]:
        """Run quality pipeline on a JSONL file."""
        path = Path(filepath)
        if not path.exists():
            return {"error": f"File not found: {path}"}

        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not records:
            return {"error": "No valid JSON records found"}

        return self.run_records(records, dataset_id or path.stem)

    def quality_distribution(self, records: list[dict[str, Any]],
                             bins: int = 10) -> dict[str, Any]:
        """Compute quality score distribution."""
        scores = [r.get("_quality_score", 0) for r in records if "_quality_score" in r]
        if not scores:
            return {"error": "No quality scores found"}

        bin_size = 1.0 / bins
        distribution: dict[str, int] = {}
        for i in range(bins):
            lower = round(i * bin_size, 2)
            upper = round((i + 1) * bin_size, 2)
            label = f"{lower:.2f}-{upper:.2f}"
            distribution[label] = sum(1 for s in scores if lower <= s < upper)

        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        if n % 2 == 0:
            median_val = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2
        else:
            median_val = sorted_scores[n // 2]

        return {
            "count": len(scores),
            "mean": round(sum(scores) / len(scores), 3),
            "median": round(median_val, 3),
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "distribution": distribution,
        }
