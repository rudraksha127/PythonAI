# Colab Training Dataset Export

Exported on: 2026-05-27T06:53:29.966130

## Files

| File | Description |
|------|-------------|
| `training_dataset.jsonl` | Full dataset (11,962 examples) — for Unsloth |
| `training_sample_500.jsonl` | 500-example subset for quick testing |
| `dataset_stats.json` | Statistical breakdown of the dataset |

## Upload to Google Colab

1. Zip this folder: `tar -czf colab_export.tar.gz colab_export/`
2. Upload to your Google Drive or directly to Colab runtime
3. Or use the HuggingFace Datasets method (see notebook)

## Dataset Stats

- Total rows: 11,962
- Valid rows: 11,962
- Avg instruction length: 71.1 chars
- Avg output length: 332.2 chars
- Code examples: 1.8%
- Recommended max_seq_length: 1889
