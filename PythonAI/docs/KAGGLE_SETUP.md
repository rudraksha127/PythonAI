# Kaggle CLI Setup Guide

## Overview

Kaggle provides **free P100 GPU** (16GB VRAM, 30 hours/week) for training models.
We use it to fine-tune Qwen2.5-Coder-14B and other models via QLoRA.

## Quick Start

```bash
# Run the setup helper
python scripts/kaggle_setup.py
```

## Manual Setup Steps

### 1. Install Kaggle CLI

Already installed at:
```
C:\Users\lucky_vv7fub\AppData\Roaming\Python\Python314\Scripts\kaggle.exe
```

Repo cloned at:
```
tools/kaggle-cli/
```

### 2. Get API Key

1. Go to **[kaggle.com/settings](https://kaggle.com/settings)**
2. Login/Signup (free account)
3. Scroll to **API** section
4. Click **Create New API Token**
5. Save `kaggle.json` to:

```
C:\Users\lucky_vv7fub\.kaggle\kaggle.json
```

### 3. Verify

```bash
# Run setup check
python scripts/kaggle_setup.py

# Or manually:
kaggle competitions list
kaggle kernels list --mine
```

## Training Notebooks

| Notebook | Description | File |
|----------|-------------|------|
| **Qwen2.5-Coder-14B** | QLoRA fine-tuning on Python dataset | `colab_export/finetune_qwen14b_unsloth.ipynb` |
| **Qwen2.5-Coder-7B** | Smaller model, faster training | (same notebook, change model name) |

### Upload to Kaggle

```bash
# Upload notebook
kaggle kernels push -p colab_export/

# Or manually on website:
# 1. kaggle.com/notebooks -> New Notebook
# 2. File -> Import Notebook -> select .ipynb
```

## PATH Setup

Add to PATH (Powershell):
```powershell
$env:Path += ";C:\Users\lucky_vv7fub\AppData\Roaming\Python\Python314\Scripts"
```

Or add permanently via System Settings > Environment Variables.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `kaggle: command not found` | Add Kaggle to PATH (see above) |
| `401 Unauthorized` | `kaggle.json` is invalid. Re-download from kaggle.com/settings |
| `403 Forbidden` | You accepted competition rules? Check kaggle.com/competitions |
| No GPU | Settings > Accelerator > GPU P100 |
| OOM during training | Reduce `MAX_SEQ_LENGTH` or `per_device_train_batch_size` |

## Resources

- [Kaggle CLI GitHub](https://github.com/Kaggle/kaggle-cli)
- [Kaggle Notebooks](https://www.kaggle.com/notebooks)
- [Kaggle API Docs](https://www.kaggle.com/docs/api)
