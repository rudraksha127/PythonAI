# Qwen2.5-Coder-14B Training Guide 🚀

> **Dataset:** 11,962 Python Q&A examples | **Model:** Qwen2.5-Coder-14B (QLoRA 4-bit)
> **Adapter size:** ~34 MB | **VRAM needed:** ~14-16 GB

---

## 📋 Quick Comparison

| Feature | Google Colab ⭐ | Kaggle |
|---------|:---------------:|:------:|
| **GPU** | T4 (16 GB) | P100 (16 GB) |
| **Cost** | Free | Free |
| **Setup time** | 2 minutes | 15 minutes |
| **Training time** | ~2-4 hours | ~1.5-3 hours |
| **Account needed** | Google account | Kaggle account |
| **Difficulty** | Easy ⭐ | Medium |

---

## 🅰️ Option A: Google Colab (Recommended) ⭐

### Prerequisites
- ✅ Google account (gmail)
- ✅ Internet connection
- ✅ ~2-4 hours free time

### Step-by-Step

#### Step 1: Open Colab & Upload Notebook
```
1. Go to https://colab.research.google.com/
2. Click: File → Upload Notebook
3. Upload: colab_export/finetune_qwen14b_unsloth.ipynb
```

#### Step 2: Enable GPU
```
1. Click: Runtime → Change runtime type
2. Set: Hardware accelerator → T4 GPU
3. Click: Save
```

#### Step 3: Upload Dataset (Option B in notebook)
```
1. In the notebook, scroll to Step 2 → Option B
2. Run the "Upload JSONL directly to Colab" cell
3. When prompted, upload: colab_export/training_dataset.jsonl
```

#### Step 4: Train!
```
Option A: Quick test (~5 minutes)
  - Use the "Quick Test Mode" cell at the bottom
  - 50 steps on 200 examples
  - Good for smoke testing

Option B: Full training (~2-4 hours)
  - Run Step 6 with 1 epoch on all 11,962 examples
  - Runtime → Run all
  - Colab may disconnect → save to Google Drive (Step 7)
```

#### Step 5: Download Trained Adapter
```
1. After training, run Step 7 cells
2. Adapter downloads as: pythonai_qwen14b_lora_adapter.zip
3. Save to your project: checkpoints/qwen14b_pythonai/
```

---

## 🅱️ Option B: Kaggle

### Prerequisites
- ✅ Kaggle account (free at kaggle.com)
- ✅ Kaggle API key
- ✅ Internet connection

### Step 1: Get Kaggle API Key

```
1. Go to https://www.kaggle.com/settings
2. Scroll to: API section
3. Click: "Create New API Token"
4. Save the downloaded file to: C:\Users\lucky_vv7fub\.kaggle\kaggle.json
```

### Step 2: Verify Setup

```bash
# Check if everything is ready
python colab_export/upload_to_kaggle.py --setup
```

### Step 3: Upload Dataset to Kaggle

```bash
# Manual way (recommended):
# 1. Go to https://www.kaggle.com/
# 2. Click: Create → New Dataset
# 3. Upload: colab_export/training_dataset.jsonl
# 4. Name it: pythonai-training-data
# 5. License: MIT

# OR via CLI (if API key is set up):
python colab_export/upload_to_kaggle.py --dataset-only --username YOUR_USERNAME
```

### Step 4: Push Notebook to Kaggle

```bash
# Manual way (recommended):
# 1. Go to https://www.kaggle.com/notebooks
# 2. Click: Create → New Notebook
# 3. File → Import Notebook → Select finetune_qwen14b_unsloth.ipynb
# 4. Settings → Accelerator → GPU P100
# 5. Settings → Internet → On
# 6. Add Data → Search "pythonai-training-data"

# OR via CLI (after API key setup):
python colab_export/upload_to_kaggle.py --all --username YOUR_USERNAME
```

### Step 5: Train on Kaggle

```
1. Open: https://www.kaggle.com/notebooks
2. Find: finetune-qwen14b-pythonai
3. Verify: Settings → Accelerator → GPU P100
4. Click: Run All (top-right)
5. Monitor: Output logs in real-time
```

### Step 6: Download Results

```
1. After training, go to: /kaggle/working/ directory
2. Find: pythonai_qwen14b_lora_adapter/
3. Download via Kaggle file browser
4. Extract to your project: checkpoints/qwen14b_pythonai/
```

---

## 📥 After Training — Use Locally

Once you have the adapter downloaded, use it locally:

```bash
# 1. Extract the adapter
# Place in: checkpoints/qwen14b_pythonai/

# 2. Evaluate it
python -m src.training.evaluator --adapter-path checkpoints/qwen14b_pythonai

# 3. Compare with other adapters
python -m src.training.comparison --compare-all

# 4. Use with RAG
python -m src.rag.rag_engine --use-adapter checkpoints/qwen14b_pythonai

# 5. (Optional) Convert to GGUF for Ollama
# See notebook Step 9 for details
```

---

## 📊 Dataset Summary

| Metric | Value |
|--------|-------|
| **Total examples** | **11,962** |
| **Categories** | 20 (library, c_api, whatsnew, howto, tutorial, etc.) |
| **Python versions** | 2.7 → 3.16 |
| **Code examples** | ~5,000+ |
| **Avg instruction** | 71 chars |
| **Avg output** | 332 chars |
| **File size** | 6.5 MB |

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Colab OOM** | Reduce `MAX_SEQ_LENGTH` to 512 or batch size to 1 |
| **Colab disconnects** | Save checkpoints to Google Drive periodically (Step 7) |
| **Kaggle GPU not available** | Check Settings → Accelerator → GPU P100 |
| **Kaggle dataset not found** | Add `pythonai-training-data` via Add Data button |
| **HF auth error** | Get token from huggingface.co/settings/tokens |
| **Slow training** | Normal for 14B on T4. Full training: ~2-4 hrs |
| **Adapter download fails** | Re-run save cell and try again |
| **PyTorch version mismatch** | The notebook auto-installs the right version |

---

## 🚀 Quick Commands

```bash
# Colab — Open package
python colab_export/open_in_colab.py

# Kaggle — Check setup
python colab_export/upload_to_kaggle.py --setup

# Kaggle — Manual instructions
python colab_export/upload_to_kaggle.py --manual

# Local smoke test (Qwen-0.5B, ~2 min)
python -m src.training.run --mode qwen --max-steps 8 --max-examples 64
```

---

## 📝 Notes

- **Full training time:** ~2-4 hours on T4 (Colab), ~1.5-3 hours on P100 (Kaggle)
- **Adapter size:** ~34 MB (LoRA rank 16, only trainable weights)
- **Merged model:** ~28 GB (full weights) — only needed for GGUF conversion
- **Colab free tier limit:** Resets after ~12 hours, but you can use multiple sessions
