"""
PHASE 1 DATA COLLECTION — Foundation Data
Complete schedule from the MASTER_DATA_PLAN with all datasets across 4 weeks.

Phase 1 builds the foundation for the INDRA model with:
  Week 1 — Foundation Text (FineWeb, Wikipedia, Gutenberg, The Stack, arXiv, PubMed)
  Week 2 — Indian + Multilingual (Sangraha, IndicCorp, data.gov.in, FineWeb2 Hindi, Shrutilipi)
  Week 3 — Instruction + Scientific (Open-Orca, UltraChat, PubMed Central, S2ORC, MathPile, Synthetic)
  Week 4 — Multimodal (LAION-Aesthetics, Common Voice, GigaSpeech, GitHub)

Usage:
    from src.data.phase1 import generate_phase1_datasets
    records = generate_phase1_datasets()
    mgr.register_many(records)
"""

from __future__ import annotations

from src.data.metadata import (
    DatasetRecord,
    DataDomain,
    DownloadProtocol,
)


# ════════════════════════════════════════════
# Helper builders
# ════════════════════════════════════════════

def _hf(
    id_: str, name: str, path: str,
    phase: int, week: int, domain: DataDomain,
    hf_config: str | None = None,
    hf_split: str = "train",
    estimated_records: int = 0,
    estimated_bytes: int = 0,
    languages: list[str] | None = None,
    license: str = "unknown",
    tags: list[str] | None = None,
    training_weight: float = 1.0,
    training_phase: int = 1,
    max_records: int = 0,
    output_subdir: str = "",
) -> DatasetRecord:
    if not output_subdir:
        output_subdir = f"phase{phase}/week{week}"
    return DatasetRecord(
        id=id_, name=name, source_url=path,
        protocol=DownloadProtocol.HUGGINGFACE,
        phase=phase, week=week, domain=domain,
        hf_config=hf_config, hf_split=hf_split,
        estimated_record_count=estimated_records,
        estimated_size_bytes=estimated_bytes,
        languages=languages or ["en"],
        license=license, tags=tags or [],
        training_weight=training_weight,
        training_phase=training_phase,
        download_params={"max_records": max_records},
        output_subdir=output_subdir,
    )


def _http(
    id_: str, name: str, url: str,
    phase: int, week: int, domain: DataDomain,
    estimated_bytes: int = 0,
    languages: list[str] | None = None,
    license: str = "unknown",
    tags: list[str] | None = None,
    training_weight: float = 1.0,
    output_subdir: str = "",
) -> DatasetRecord:
    if not output_subdir:
        output_subdir = f"phase{phase}/week{week}"
    return DatasetRecord(
        id=id_, name=name, source_url=url,
        protocol=DownloadProtocol.HTTP,
        phase=phase, week=week, domain=domain,
        estimated_size_bytes=estimated_bytes,
        languages=languages or ["en"],
        license=license, tags=tags or [],
        training_weight=training_weight,
        output_subdir=output_subdir,
    )


def _git_lfs(
    id_: str, name: str, url: str,
    phase: int, week: int, domain: DataDomain,
    languages: list[str] | None = None,
    license: str = "unknown",
    tags: list[str] | None = None,
    training_weight: float = 1.0,
    output_subdir: str = "",
) -> DatasetRecord:
    if not output_subdir:
        output_subdir = f"phase{phase}/week{week}"
    return DatasetRecord(
        id=id_, name=name, source_url=url,
        protocol=DownloadProtocol.GIT_LFS,
        phase=phase, week=week, domain=domain,
        languages=languages or ["en"],
        license=license, tags=tags or [],
        training_weight=training_weight,
        output_subdir=output_subdir,
    )


# ════════════════════════════════════════════
# WEEK 1 — Foundation Text (~1-3 TB)
# ════════════════════════════════════════════

def generate_week1() -> list[DatasetRecord]:
    """Foundation text datasets: FineWeb, Wikipedia, Gutenberg, The Stack, arXiv, PubMed."""

    return [
        # ── FineWeb-Edu (English educational web text) ──
        _hf(
            "fineweb_edu_en", "FineWeb-Edu (English HuggingFace)",
            "HuggingFaceFW/fineweb-edu",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            hf_config="sample-10BT",
            estimated_records=10_000_000_000,  # 10B tokens
            estimated_bytes=50_000_000_000,    # ~50 GB
            license="cc-by-nc-4.0",
            tags=["web_text", "educational"],
            training_weight=0.25,
            max_records=5_000_000,  # Sample 5M for local
        ),

        # ── FineWeb (general English web text) ──
        _hf(
            "fineweb_en", "FineWeb (English Web Text)",
            "HuggingFaceFW/fineweb",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            hf_config="sample-10BT",
            estimated_records=10_000_000_000,
            estimated_bytes=50_000_000_000,
            license="cc-by-nc-4.0",
            tags=["web_text", "general"],
            training_weight=0.15,
            max_records=5_000_000,
        ),

        # ── DCLM-Baseline (Datacomp LM) ──
        _hf(
            "dclm_baseline", "DCLM Baseline (High Quality Web)",
            "mlfoundations/dclm-baseline-1.0",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            hf_config="default",
            estimated_records=2_000_000_000,
            estimated_bytes=10_000_000_000,
            license="cc-by-4.0",
            tags=["web_text", "high_quality"],
            training_weight=0.20,
            max_records=2_000_000,
        ),

        # ── Wikipedia (English + all languages) ──
        _hf(
            "wikipedia_en", "Wikipedia (English)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            hf_config="20231101.en",
            estimated_records=6_000_000,
            estimated_bytes=12_000_000_000,
            license="cc-by-sa-3.0",
            tags=["encyclopedic", "reference"],
            training_weight=0.10,
            max_records=1_000_000,
        ),
        _hf(
            "wikipedia_hi", "Wikipedia (Hindi)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.hi",
            estimated_records=160_000,
            estimated_bytes=300_000_000,
            license="cc-by-sa-3.0",
            languages=["hi"],
            tags=["encyclopedic", "hindi"],
            training_weight=0.03,
            max_records=160_000,
        ),
        _hf(
            "wikipedia_ta", "Wikipedia (Tamil)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.ta",
            estimated_records=170_000,
            estimated_bytes=300_000_000,
            license="cc-by-sa-3.0",
            languages=["ta"],
            tags=["encyclopedic", "tamil"],
            training_weight=0.02,
            max_records=170_000,
        ),
        _hf(
            "wikipedia_te", "Wikipedia (Telugu)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.te",
            estimated_records=100_000,
            estimated_bytes=200_000_000,
            license="cc-by-sa-3.0",
            languages=["te"],
            tags=["encyclopedic", "telugu"],
            training_weight=0.02,
            max_records=100_000,
        ),
        _hf(
            "wikipedia_bn", "Wikipedia (Bengali)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.bn",
            estimated_records=160_000,
            estimated_bytes=300_000_000,
            license="cc-by-sa-3.0",
            languages=["bn"],
            tags=["encyclopedic", "bengali"],
            training_weight=0.02,
            max_records=160_000,
        ),
        _hf(
            "wikipedia_mr", "Wikipedia (Marathi)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.mr",
            estimated_records=100_000,
            estimated_bytes=200_000_000,
            license="cc-by-sa-3.0",
            languages=["mr"],
            tags=["encyclopedic", "marathi"],
            training_weight=0.02,
            max_records=100_000,
        ),
        _hf(
            "wikipedia_gu", "Wikipedia (Gujarati)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.gu",
            estimated_records=30_000,
            estimated_bytes=60_000_000,
            license="cc-by-sa-3.0",
            languages=["gu"],
            tags=["encyclopedic", "gujarati"],
            training_weight=0.01,
            max_records=30_000,
        ),
        _hf(
            "wikipedia_ml", "Wikipedia (Malayalam)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.ml",
            estimated_records=140_000,
            estimated_bytes=280_000_000,
            license="cc-by-sa-3.0",
            languages=["ml"],
            tags=["encyclopedic", "malayalam"],
            training_weight=0.02,
            max_records=140_000,
        ),
        _hf(
            "wikipedia_pa", "Wikipedia (Punjabi)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.pa",
            estimated_records=60_000,
            estimated_bytes=120_000_000,
            license="cc-by-sa-3.0",
            languages=["pa"],
            tags=["encyclopedic", "punjabi"],
            training_weight=0.01,
            max_records=60_000,
        ),
        _hf(
            "wikipedia_or", "Wikipedia (Odia)",
            "wikimedia/wikipedia",
            phase=1, week=1, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config="20231101.or",
            estimated_records=30_000,
            estimated_bytes=60_000_000,
            license="cc-by-sa-3.0",
            languages=["or"],
            tags=["encyclopedic", "odia"],
            training_weight=0.01,
            max_records=30_000,
        ),

        # ── The Stack (source code - Python focused) ──
        _hf(
            "the_stack_python", "The Stack (Python)",
            "bigcode/the-stack-v2",
            phase=1, week=1, domain=DataDomain.CODE,
            hf_config="data/python",
            estimated_records=30_000_000,
            estimated_bytes=150_000_000_000,
            license="multiple",
            tags=["code", "python"],
            training_weight=0.25,
            max_records=2_000_000,
        ),

        # ── Project Gutenberg (books via HuggingFace) ──
        _hf(
            "gutenberg_books", "Project Gutenberg (Books)",
            "bookcorpus/bookcorpus",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            estimated_records=10_000_000,
            estimated_bytes=15_000_000_000,
            license="public_domain",
            tags=["books", "literature"],
            training_weight=0.05,
            max_records=500_000,
        ),

        # ── arXiv papers (via HuggingFace) ──
        _hf(
            "arxiv_papers", "arXiv Papers (All Categories)",
            "arxiv-community/arxiv-dataset",
            phase=1, week=1, domain=DataDomain.SCIENCE,
            hf_config="default",
            estimated_records=2_000_000,
            estimated_bytes=50_000_000_000,
            license="cc-by-4.0",
            tags=["science", "papers"],
            training_weight=0.10,
            max_records=500_000,
        ),

        # ── PubMed abstracts ──
        _hf(
            "pubmed_abstracts", "PubMed Abstracts",
            "pubmed/pubmed",
            phase=1, week=1, domain=DataDomain.MEDICINE,
            hf_config="default",
            estimated_records=35_000_000,
            estimated_bytes=40_000_000_000,
            license="public_domain",
            tags=["medicine", "abstracts"],
            training_weight=0.08,
            max_records=1_000_000,
        ),

        # ── C4 (Colossal Clean Crawled Corpus) ──
        _hf(
            "c4_en", "C4 (Colossal Clean Crawled Corpus - English)",
            "allenai/c4",
            phase=1, week=1, domain=DataDomain.FOUNDATION_TEXT,
            hf_config="en",
            estimated_records=364_000_000,
            estimated_bytes=750_000_000_000,
            license="odc-by",
            tags=["web_text", "clean"],
            training_weight=0.15,
            max_records=3_000_000,
        ),
    ]


# ════════════════════════════════════════════
# WEEK 2 — Indian + Multilingual (~200-500 GB)
# ════════════════════════════════════════════

def generate_week2() -> list[DatasetRecord]:
    """Indian languages and multilingual datasets."""
    records = []

    # ── Sangraha (Indic languages corpus) ──
    for lang_code, lang_name, est_records in [
        ("hi", "Hindi", 5_000_000),
        ("bn", "Bengali", 3_000_000),
        ("ta", "Tamil", 2_000_000),
        ("te", "Telugu", 1_500_000),
        ("mr", "Marathi", 1_000_000),
        ("gu", "Gujarati", 800_000),
        ("ml", "Malayalam", 700_000),
        ("kn", "Kannada", 600_000),
        ("pa", "Punjabi", 400_000),
        ("or", "Odia", 300_000),
        ("as", "Assamese", 200_000),
        ("mai", "Maithili", 100_000),
    ]:
        records.append(_hf(
            f"sangraha_{lang_code}", f"Sangraha ({lang_name})",
            "ai4bharat/sangraha",
            phase=1, week=2, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config=lang_code,
            estimated_records=est_records,
            estimated_bytes=est_records * 500,  # ~500 bytes/record
            languages=[lang_code],
            license="cc-by-nc-4.0",
            tags=["indic", lang_code],
            training_weight=0.03,
            max_records=min(est_records, 200_000),
        ))

    # ── IndicCorp (AI4Bharat) ──
    for lang_code, lang_name, est_records in [
        ("hi", "Hindi", 8_000_000),
        ("bn", "Bengali", 4_000_000),
        ("ta", "Tamil", 3_000_000),
        ("te", "Telugu", 2_000_000),
        ("mr", "Marathi", 1_500_000),
        ("gu", "Gujarati", 1_000_000),
    ]:
        records.append(_hf(
            f"indiccorp_{lang_code}", f"IndicCorp ({lang_name})",
            "ai4bharat/indiccorp",
            phase=1, week=2, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config=lang_code,
            estimated_records=est_records,
            estimated_bytes=est_records * 500,
            languages=[lang_code],
            license="cc-by-nc-4.0",
            tags=["indic", "web_text", lang_code],
            training_weight=0.03,
            max_records=min(est_records, 300_000),
        ))

    # ── Shrutilipi (Indic TTS + text) ──
    for lang_code, lang_name in [
        ("hi", "Hindi"), ("bn", "Bengali"), ("ta", "Tamil"),
        ("te", "Telugu"), ("mr", "Marathi"), ("gu", "Gujarati"),
        ("kn", "Kannada"), ("ml", "Malayalam"),
    ]:
        records.append(_hf(
            f"shrutilipi_{lang_code}", f"Shrutilipi ({lang_name})",
            "ai4bharat/shrutilipi",
            phase=1, week=2, domain=DataDomain.INDIAN_LANGUAGES,
            hf_config=lang_code,
            estimated_records=500_000,
            estimated_bytes=1_000_000_000,
            languages=[lang_code],
            license="cc-by-4.0",
            tags=["indic", "audio_text", lang_code],
            training_weight=0.01,
            max_records=100_000,
        ))

    # ── FLORES-200 (NMT benchmark — good for multilingual alignment) ──
    for split_name in ["dev", "devtest"]:
        records.append(_hf(
            f"flores200_{split_name}", f"FLORES-200 ({split_name})",
            "facebook/flores",
            phase=1, week=2, domain=DataDomain.MULTILINGUAL,
            hf_config="default",
            estimated_records=2000,
            estimated_bytes=20_000_000,
            languages=["en", "hi", "ta", "te", "bn", "mr", "gu", "ml", "kn", "pa"],
            license="cc-by-sa-4.0",
            tags=["translation", "multilingual", "benchmark"],
            training_weight=0.01,
            max_records=2000,
        ))

    # ── IN22 (Indic-to-English translation) ──
    records.append(_hf(
        "in22_corpus", "IN22 (Indic-to-English Translation)",
        "ai4bharat/in22",
        phase=1, week=2, domain=DataDomain.INDIAN_LANGUAGES,
        hf_config="default",
        estimated_records=20_000,
        estimated_bytes=50_000_000,
        languages=["en", "hi", "bn", "ta", "te", "mr", "gu", "ml", "kn", "pa", "or", "as"],
        license="cc-by-nc-4.0",
        tags=["translation", "indic-english"],
        training_weight=0.01,
        max_records=20_000,
    ))

    # ── FineWeb2 Hindi (from HuggingFaceFW multlingual release) ──
    records.append(_hf(
        "fineweb2_hi", "FineWeb2 (Hindi)",
        "HuggingFaceFW/fineweb-2",
        phase=1, week=2, domain=DataDomain.INDIAN_LANGUAGES,
        hf_config="hi",
        estimated_records=500_000_000,
        estimated_bytes=2_500_000_000_000,
        languages=["hi"],
        license="cc-by-nc-4.0",
        tags=["web_text", "hindi"],
        training_weight=0.05,
        max_records=1_000_000,
    ))

    # ── India Data (data.gov.in curated datasets) ──
    records.append(_http(
        "indiagov_agri", "India Government Agriculture Data",
        "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
        phase=1, week=2, domain=DataDomain.OTHER,
        estimated_bytes=500_000_000,
        languages=["hi", "en"],
        license="government_open",
        tags=["india", "government", "agriculture"],
    ))

    # ── Oscar (massive multilingual corpus) ──
    for lang_code in ["hi", "bn", "ta", "te", "mr", "gu", "ml", "kn", "pa", "or", "as", "ur"]:
        records.append(_hf(
            f"oscar_{lang_code}", f"OSCAR (Multilingual - {lang_code})",
            "oscar-corpus/OSCAR-2301",
            phase=1, week=2, domain=DataDomain.MULTILINGUAL,
            hf_config=lang_code,
            estimated_records=10_000_000,
            estimated_bytes=20_000_000_000,
            languages=[lang_code],
            license="cc-by-nc-4.0",
            tags=["web_text", "multilingual", lang_code],
            training_weight=0.02,
            max_records=300_000,
        ))

    # ── CulturaX (multilingual with Indic focus) ──
    for lang_code in ["hi", "bn", "ta", "te", "mr", "gu", "ml", "kn", "pa"]:
        records.append(_hf(
            f"culturax_{lang_code}", f"CulturaX ({lang_code})",
            "uonlp/CulturaX",
            phase=1, week=2, domain=DataDomain.MULTILINGUAL,
            hf_config=lang_code,
            estimated_records=5_000_000,
            estimated_bytes=10_000_000_000,
            languages=[lang_code],
            license="cc-by-nc-sa-4.0",
            tags=["web_text", "multilingual", lang_code],
            training_weight=0.02,
            max_records=200_000,
        ))

    return records


# ════════════════════════════════════════════
# WEEK 3 — Instruction + Scientific (~300 GB - 1 TB)
# ════════════════════════════════════════════

def generate_week3() -> list[DatasetRecord]:
    """Instruction tuning and scientific datasets."""

    return [
        # ── Open-Orca (GPT-4 generated instructions) ──
        _hf(
            "open_orca", "Open-Orca (Instruction Tuning)",
            "Open-Orca/OpenOrca",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            estimated_records=4_000_000,
            estimated_bytes=8_000_000_000,
            license="cc-by-nc-4.0",
            tags=["instruction", "gpt4"],
            training_weight=0.10,
            max_records=500_000,
        ),

        # ── UltraChat (diverse multi-turn conversations) ──
        _hf(
            "ultrachat", "UltraChat (Multi-turn Conversations)",
            "HuggingFaceH4/ultrachat_200k",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            estimated_records=200_000,
            estimated_bytes=1_000_000_000,
            license="cc-by-nc-4.0",
            tags=["instruction", "multi_turn"],
            training_weight=0.08,
            max_records=200_000,
        ),

        # ── PubMed Central (full-text biomedical articles) ──
        _hf(
            "pubmed_central_full", "PubMed Central (Full Text)",
            "pubmed_central",
            phase=1, week=3, domain=DataDomain.MEDICINE,
            hf_config="default",
            estimated_records=3_000_000,
            estimated_bytes=100_000_000_000,
            license="cc-by",
            tags=["medicine", "full_text"],
            training_weight=0.06,
            max_records=300_000,
        ),

        # ── S2ORC (Semantic Scholar Open Research Corpus) ──
        _hf(
            "s2orc_papers", "S2ORC (Semantic Scholar Papers)",
            "allenai/s2orc",
            phase=1, week=3, domain=DataDomain.SCIENCE,
            hf_config="default",
            estimated_records=8_000_000,
            estimated_bytes=100_000_000_000,
            license="cc-by",
            tags=["science", "papers", "full_text"],
            training_weight=0.06,
            max_records=500_000,
        ),

        # ── MathPile (mathematical reasoning) ──
        _hf(
            "mathpile", "MathPile (Mathematical Reasoning)",
            "GAIR/MathPile",
            phase=1, week=3, domain=DataDomain.MATH,
            hf_config="default",
            estimated_records=8_000_000,
            estimated_bytes=35_000_000_000,
            license="cc-by-nc-4.0",
            tags=["math", "reasoning"],
            training_weight=0.05,
            max_records=500_000,
        ),

        # ── NuminaMath (math instruction data) ──
        _hf(
            "numinamath", "NuminaMath (Math Problem Solving)",
            "AI-MO/NuminaMath-CoT",
            phase=1, week=3, domain=DataDomain.MATH,
            hf_config="default",
            estimated_records=860_000,
            estimated_bytes=2_000_000_000,
            license="mit",
            tags=["math", "cot"],
            training_weight=0.04,
            max_records=860_000,
        ),

        # ── OpenMathInstruct (math instruction + code) ──
        _hf(
            "openmath_instruct", "OpenMathInstruct (Math + Code)",
            "nvidia/OpenMathInstruct-1",
            phase=1, week=3, domain=DataDomain.MATH,
            hf_config="default",
            estimated_records=1_800_000,
            estimated_bytes=5_000_000_000,
            license="cc-by-4.0",
            tags=["math", "code"],
            training_weight=0.04,
            max_records=500_000,
        ),

        # ── OpenAssistant (human instructions) ──
        _hf(
            "openassistant", "OpenAssistant Conversations",
            "OpenAssistant/oasst1",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            estimated_records=160_000,
            estimated_bytes=500_000_000,
            license="cc-by-4.0",
            tags=["instruction", "human"],
            training_weight=0.05,
            max_records=160_000,
        ),

        # ── Natural Instructions v3 (diverse NLP tasks) ──
        _hf(
            "natural_instructions", "Natural Instructions (NLP Tasks)",
            "microsoft/natural-instructions",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            hf_config="default",
            estimated_records=5_000_000,
            estimated_bytes=10_000_000_000,
            license="mit",
            tags=["instruction", "nlp"],
            training_weight=0.05,
            max_records=500_000,
        ),

        # ── Tulu3 (Diverse instruction mix) ──
        _hf(
            "tulu3_dpo", "Tulu3 DPO Mix (Instruction)",
            "allenai/tulu-3-sft-mixture",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            hf_config="default",
            estimated_records=500_000,
            estimated_bytes=2_000_000_000,
            license="cc-by-nc-4.0",
            tags=["instruction", "diverse"],
            training_weight=0.06,
            max_records=500_000,
        ),

        # ── Capybara (long-form instruction) ──
        _hf(
            "capybara", "Capybara (Long-Form Instructions)",
            "LDJnr/Capybara",
            phase=1, week=3, domain=DataDomain.INSTRUCTION,
            hf_config="default",
            estimated_records=200_000,
            estimated_bytes=1_000_000_000,
            license="cc-by-nc-4.0",
            tags=["instruction", "long_form"],
            training_weight=0.03,
            max_records=200_000,
        ),

        # ── Python Code Instructions (magpie) ──
        _hf(
            "magpie_python", "Magpie Python Instructions",
            "Magpie-Align/Magpie-Pro-MT-300K-v0.1",
            phase=1, week=3, domain=DataDomain.CODE,
            hf_config="default",
            estimated_records=300_000,
            estimated_bytes=1_500_000_000,
            license="mit",
            tags=["code", "instruction", "python"],
            training_weight=0.06,
            max_records=300_000,
        ),

        # ── Synthetic generation config (for local generation) ──
        DatasetRecord(
            id="synthetic_indic_instructions",
            name="Synthetic Indic Instructions (Generated)",
            source_url="local",
            protocol=DownloadProtocol.LOCAL,
            phase=1, week=3, domain=DataDomain.INDIAN_LANGUAGES,
            estimated_record_count=100_000,
            estimated_size_bytes=500_000_000,
            languages=["hi", "bn", "ta", "te", "mr", "gu"],
            license="synthetic",
            tags=["synthetic", "indic", "instruction"],
            training_weight=0.03,
            output_subdir="phase1/week3/synthetic",
        ),
    ]


# ════════════════════════════════════════════
# WEEK 4 — Multimodal + Audio (~500 GB - 2 TB)
# ════════════════════════════════════════════

def generate_week4() -> list[DatasetRecord]:
    """Multimodal and audio datasets."""

    return [
        # ── Common Voice (multilingual speech) ──
        _hf(
            "common_voice_en", "Common Voice (English Speech)",
            "mozilla-foundation/common_voice_19_0",
            phase=1, week=4, domain=DataDomain.AUDIO,
            hf_config="en",
            estimated_records=2_000_000,
            estimated_bytes=200_000_000_000,
            languages=["en"],
            license="cc0-1.0",
            tags=["audio", "speech"],
            training_weight=0.02,
            max_records=200_000,
        ),
        _hf(
            "common_voice_hi", "Common Voice (Hindi Speech)",
            "mozilla-foundation/common_voice_19_0",
            phase=1, week=4, domain=DataDomain.AUDIO,
            hf_config="hi",
            estimated_records=500_000,
            estimated_bytes=50_000_000_000,
            languages=["hi"],
            license="cc0-1.0",
            tags=["audio", "speech", "hindi"],
            training_weight=0.01,
            max_records=100_000,
        ),

        # ── GitHub repositories (via Git LFS large repos) ──
        _git_lfs(
            "github_awesome_ml", "GitHub Awesome ML Repos (Mirror)",
            "https://github.com/EthicalML/awesome-production-machine-learning.git",
            phase=1, week=4, domain=DataDomain.CODE,
            languages=["en"],
            license="multiple",
            tags=["code", "github", "ml"],
            training_weight=0.02,
        ),

        # ── GitHub Python repos from The Stack (code subset) ──
        _hf(
            "the_stack_python_extra", "The Stack Python (Extra subset)",
            "bigcode/the-stack-smol",
            phase=1, week=4, domain=DataDomain.CODE,
            hf_config="python",
            estimated_records=2_000_000,
            estimated_bytes=10_000_000_000,
            license="multiple",
            tags=["code", "python"],
            training_weight=0.05,
            max_records=500_000,
        ),

        # ── CodeSearchNet (code + docs for multiple languages) ──
        _hf(
            "codesearchnet_all", "CodeSearchNet (All Languages)",
            "code_search_net",
            phase=1, week=4, domain=DataDomain.CODE,
            hf_config="all",
            estimated_records=2_000_000,
            estimated_bytes=5_000_000_000,
            license="mit",
            tags=["code", "documentation"],
            training_weight=0.04,
            max_records=500_000,
        ),

        # ── LAION-Aesthetics (image-text) — sampled ──
        _hf(
            "laion_aesthetics", "LAION-Aesthetics (Image-Text)",
            "laion/laion2B-en-aesthetic",
            phase=1, week=4, domain=DataDomain.MULTIMODAL,
            hf_config="default",
            estimated_records=1_200_000_000,
            estimated_bytes=500_000_000_000,
            license="cc-by-4.0",
            tags=["image_text", "vision"],
            training_weight=0.02,
            max_records=100_000,
        ),

        # ── WikiHow (instructional text + images) ──
        _hf(
            "wikihow_instructions", "WikiHow (Instructional Text)",
            "wikihow/wikihow",
            phase=1, week=4, domain=DataDomain.INSTRUCTION,
            hf_config="default",
            estimated_records=250_000,
            estimated_bytes=500_000_000,
            license="cc-by-nc-sa-3.0",
            tags=["instructions", "howto"],
            training_weight=0.03,
            max_records=250_000,
        ),

        # ── GigaSpeech (large-scale speech) ──
        _hf(
            "gigaspeech", "GigaSpeech (Large Speech Corpus)",
            "speechcolab/gigaspeech",
            phase=1, week=4, domain=DataDomain.AUDIO,
            hf_config="xs",  # Use XS subset for local
            estimated_records=10_000,
            estimated_bytes=50_000_000_000,
            languages=["en"],
            license="cc-by-4.0",
            tags=["audio", "speech", "large"],
            training_weight=0.01,
            max_records=10_000,
        ),

        # ── VoxPopuli (multilingual speech) ──
        _hf(
            "voxpopuli_en", "VoxPopuli (English Speech)",
            "facebook/voxpopuli",
            phase=1, week=4, domain=DataDomain.AUDIO,
            hf_config="en",
            estimated_records=100_000,
            estimated_bytes=20_000_000_000,
            languages=["en"],
            license="cc0-1.0",
            tags=["audio", "speech"],
            training_weight=0.01,
            max_records=50_000,
        ),

        # ── ConceptNet (knowledge graph) ──
        _hf(
            "conceptnet_knowledge", "ConceptNet (Knowledge Graph)",
            "conceptnet/conceptnet",
            phase=1, week=4, domain=DataDomain.KNOWLEDGE_GRAPH,
            hf_config="default",
            estimated_records=30_000_000,
            estimated_bytes=1_000_000_000,
            license="cc-by-sa-4.0",
            tags=["knowledge", "graph"],
            training_weight=0.02,
            max_records=500_000,
        ),
    ]


# ════════════════════════════════════════════
# Complete Phase 1 Generator
# ════════════════════════════════════════════

def generate_phase1_datasets() -> list[DatasetRecord]:
    """Generate ALL Phase 1 dataset records across all 4 weeks."""
    all_datasets = []
    all_datasets.extend(generate_week1())
    all_datasets.extend(generate_week2())
    all_datasets.extend(generate_week3())
    all_datasets.extend(generate_week4())
    return all_datasets


def phase1_stats() -> dict[str, int | dict]:
    """Print a summary of Phase 1 dataset counts."""
    records = generate_phase1_datasets()
    by_week: dict[int, int] = {}
    by_domain: dict[str, int] = {}
    total_records = 0
    total_bytes = 0

    for r in records:
        by_week[r.week] = by_week.get(r.week, 0) + 1
        domain_str = r.domain.value
        by_domain[domain_str] = by_domain.get(domain_str, 0) + 1
        total_records += r.estimated_record_count
        total_bytes += r.estimated_size_bytes

    return {
        "total_datasets": len(records),
        "estimated_total_records": total_records,
        "estimated_total_gb": round(total_bytes / (1024**3), 1),
        "by_week": by_week,
        "by_domain": by_domain,
    }


if __name__ == "__main__":
    import json
    stats = phase1_stats()
    print("Phase 1 — Foundation Data Collection")
    print(f"  Total datasets     : {stats['total_datasets']}")
    print(f"  Estimated records  : {stats['estimated_total_records']:,}")
    print(f"  Estimated size     : {stats['estimated_total_gb']} GB")
    print()
    print("  By Week:")
    for w, c in sorted(stats['by_week'].items()):
        print(f"    Week {w}: {c} datasets")
    print()
    print("  By Domain:")
    for d, c in sorted(stats['by_domain'].items()):
        print(f"    {d}: {c} datasets")

    # Show all datasets
    print(f"\n  {'ID':45s} {'Source':50s} {'Language':10s} {'Records':>12s}")
    print(f"  {'-'*45} {'-'*50} {'-'*10} {'-'*12}")
    for r in generate_phase1_datasets():
        lang_str = ",".join(r.languages)[:10]
        records_str = f"{r.estimated_record_count:,}" if r.estimated_record_count else "?"
        url_str = r.source_url[:50] if r.source_url else "(local)"
        print(f"  {r.id:45s} {url_str:50s} {lang_str:10s} {records_str:>12s}")
