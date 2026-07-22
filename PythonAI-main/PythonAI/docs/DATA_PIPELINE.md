# 📊 Data Pipeline — Collection, Generation, Augmentation & Merging

## Overview

The data pipeline collects Python documentation, generates SFT (Supervised Fine-Tuning) training pairs via multiple APIs, augments them with local Ollama models, and merges datasets with deduplication.

```
raw_chunks.json → generator.py → training_dataset.json
                                    ↓
raw_chunks_godmode.json → augmenter.py → augmented dataset
                                           ↓
                                    merger.py → deduped dataset
```

---

## 📝 Prompt to Continue (Data Pipeline Enhancements)

```
Copy-paste into Codebuff to continue:

Improve the data pipeline. Here's what I need:

### 1. Better Data Collection (src/data/collector.py)
- Add more library sources (Django, SQLAlchemy, Matplotlib, Scikit-learn)
- Add Python 3.13+ release notes scraping
- Store scraped data with timestamps to avoid re-downloading unchanged PEPs
- Add progress bars and better error handling

### 2. Smarter Dataset Generation (src/data/generator.py)
- Add more prompt templates (security, performance, testing patterns)
- Implement quality scoring based on output length, code presence, reasoning depth
- Add configurable quality thresholds via CLI args
- Support resumable generation from checkpoint files

### 3. Augmentation Improvements (src/data/augmenter.py)
- Support multiple Ollama models (not just qwen2.5-coder)
- Add validation that generated rows don't contain placeholder text
- Add --shuffle flag to randomize output order
- Print quality statistics after generation

### 4. Merge with Conflict Resolution (src/data/merger.py)
- When duplicate rows conflict, keep the one with longer output
- Add --keep-old flag to prefer original rows
- Add --stats-only flag to just print merge statistics without saving
- Show category/version distribution after merge
```

---

## 🧩 Pipeline Components

| Module | File | Purpose |
|--------|------|---------|
| Collector | `src/data/collector.py` | Scrape PEPs + library docs + error patterns |
| Generator | `src/data/generator.py` | Parallel multi-API SFT dataset generation |
| Augmenter | `src/data/augmenter.py` | Generate extra rows via local Ollama |
| Merger | `src/data/merger.py` | Dedupe merge two datasets |

## 🚀 Commands

```powershell
# Collect Python docs
python -m src.data.collector

# Generate dataset via multi-API
python -m src.data.generator

# Augment with local Ollama (dry run)
python -m src.cli augment --dry-run

# Augment with local Ollama (generate + merge)
python -m src.cli augment --limit 5 --pairs-per-chunk 1 --merge

# Merge two datasets
python -m src.cli merge --add data/training/training_dataset_augmented.json

# Show dataset profile
python -m src.cli dataset
```

## 📍 Data Files

| File | Description |
|------|-------------|
| `data/raw/raw_chunks.json` | Initial scraped chunks |
| `data/raw/raw_chunks_godmode.json` | Augmented chunks (PEPs + libraries) |
| `data/processed/cleaned_chunks.json` | Cleaned/filtered chunks |
| `data/training/training_dataset.json` | Final SFT dataset (~1K rows) |
| `data/training/training_dataset_augmented.json` | Ollama-augmented dataset |

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
