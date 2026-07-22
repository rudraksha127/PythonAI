# Connect VS Code to Kaggle GPU Runtime

Aap VS Code ko **directly Kaggle ke free GPU (P100 16GB)** se connect kar sakte ho
aur phir apne local `.ipynb` notebook ko remote GPU pe execute kar sakte ho.

---

## Prerequisites

1. **Kaggle account** ho (free — kaggle.com)
2. **Kaggle API key** setup ho (`~/.kaggle/kaggle.json`)
3. **VS Code Jupyter extension** installed ho

---

## Method 1: Connect via Kaggle Notebook Proxy URL (Recommended)

### Step 1: Kaggle Notebook kholo

1. **[kaggle.com](https://www.kaggle.com/notebooks)** → **New Notebook** create karo
2. **Settings** (right panel) → **Accelerator** → **GPU P100** select karo
3. Notebook load hone do — runtime start ho jayega (1-2 minutes)

### Step 2: Jupyter Proxy URL copy karo

Kaggle notebook ke top-right corner mein **"Copy URL"** button hota hai — yeh ek **session-authenticated proxy URL** copy karta hai, aisa kuch:

```
https://kkb-production.jupyter-proxy.kaggle.net/k/{KERNEL_ID}/proxy/
```

> ⚠️ **Important:** Browser ke address bar ka URL (`kaggle.com/code/USER/NOTEBOOK`) kaam nahi karega. Sirf **"Copy URL" button** se milne wala proxy URL chalega.

### Step 3: VS Code me connect karo

1. VS Code me `Ctrl+Shift+P` dabao
2. **"Jupyter: Specify Jupyter Server for Connections"** select karo
3. **"Existing"** select karo
4. Kaggle ka proxy URL paste karo (jo Step 2 mein copy kiya)
5. VS Code prompt karega ki "Allow" ya "Trust" — **Allow** karo

### Step 4: Notebook open karo

1. VS Code me `colab_export/finetune_qwen14b_unsloth.ipynb` open karo
2. Top-right mein **Kernel** dikhega — click karo
3. **"Jupyter Server"** select karo → Kaggle server select ho jayega
4. Ab VS Code ka notebook **Kaggle ke GPU** par chalega!

### Step 5 (Optional): Auto-connect for future sessions

Proxy URL ko settings mein save kar sakte ho taaki har baar na poochhe:

`.vscode/settings.json` mein yeh add karo:
```json
"jupyter.serverUrl": "https://kkb-production.jupyter-proxy.kaggle.net/k/{KERNEL_ID}/"
```

> Note: Kaggle ka proxy URL har naye session ke saath badalta hai. Har baar naya URL copy karna hoga.

---

## Method 2: Kaggle CLI se Notebook Push

### Step 1: Kaggle API Setup

```bash
python scripts/kaggle_setup.py
```

### Step 2: Notebook initialize karo

```bash
# Create a new folder with kernel metadata
kaggle kernels init -p kaggle_temp
```

Isse `kernel-metadata.json` create hoga. Usme edit karo:
```json
{
  "id": "YOUR_USERNAME/finetune-qwen14b-pythonai",
  "title": "Finetune Qwen14B PythonAI",
  "code_file": "finetune_qwen14b_unsloth.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_internet": true
}
```

### Step 3: Local files copy karo

```bash
# Copy notebook + dataset into the kernel folder
copy colab_export\finetune_qwen14b_unsloth.ipynb kaggle_temp\
copy colab_export\training_dataset.jsonl kaggle_temp\
```

### Step 4: Push to Kaggle

```bash
kaggle kernels push -p kaggle_temp/
```

### Step 5: Status check

```bash
kaggle kernels status YOUR_USERNAME/finetune-qwen14b-pythonai
kaggle kernels output YOUR_USERNAME/finetune-qwen14b-pythonai
```

---

## Method 3: Kaggle Dataset Upload + Notebook

Dataset ko Kaggle Dataset ke roop mein upload karo, phir notebook mein directly access karo:

### Step 1: Kaggle Dataset create karo

```bash
# Create dataset metadata
kaggle datasets init -p kaggle_dataset

# Edit dataset-metadata.json
# "id": "YOUR_USERNAME/pythonai-training-data"
# "title": "PythonAI Training Data"

# Upload
kaggle datasets create -p kaggle_dataset/
```

### Step 2: Notebook mein dataset use karo

Option D wala cell use karo (already notebook mein hai):
```python
KAGGLE_DATA_PATH = "/kaggle/input/pythonai-training-data/training_dataset.jsonl"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| **"404 Not Found"** on proxy URL | Kaggle session expire ho gaya. Nayi notebook kholo aur naya URL copy karo. |
| **"Connection refused"** | Kaggle notebook running hai ya nahi check karo. Runtime → Restart karo. |
| **"Kernel not found"** in VS Code | VS Code me kernel select karte waqt Kaggle server choose karo, local nahi. |
| **Slow connection** | Kaggle free tier P100 hai — Colab T4 se thoda slow ho sakta hai. |
| **OOM error** | Reduce `MAX_SEQ_LENGTH=512` ya `per_device_train_batch_size=1` |
| **Kaggle CLI: "401 Unauthorized"** | API key galat hai. `python scripts/kaggle_setup.py` run karo. |
| **Kaggle CLI: "kaggle not found"** | PATH set nahi hai. `kaggle.cmd` use karo ya script run karo. |

### Notebook Session Expiry

- Kaggle session **expire ho jata hai ~9 hours** inactivity ke baad
- VS Code connection bhi toot jayega
- Naya notebook kholo, naya URL copy karo, VS Code me re-connect karo

---

## VS Code Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+P` → "Jupyter: Select Kernel" | Kernel select karo |
| `Ctrl+Shift+P` → "Jupyter: Specify Server" | Jupyter server connect karo |
| `Ctrl+Enter` | Current cell run karo |
| `Shift+Enter` | Cell run karo + next cell pe jao |

---

## VS Code Tasks (Ctrl+Shift+B)

| Task | Description |
|------|-------------|
| **Dataset: Export for Colab/Kaggle** | Exports training dataset to JSONL format |
| **GPU: Check Availability** | Checks if GPU is available for training |
| **Upload: HuggingFace Dataset** | Pushes dataset to HuggingFace Hub |
| **Smoke: Quick Test** | Runs 50-step smoke test on Qwen-0.5B |
| **Train: Qwen-0.5B** | Runs full training on local Qwen-0.5B model |
| **Open: Colab Notebook** | Opens the Colab notebook in browser |

---

## Important Notes

- Kaggle free tier gives **30 hours/week** of GPU (P100 16GB)
- Session **expires after ~9 hours** of inactivity
- Always **save your adapter to Google Drive** or download it immediately
- Notebook me `training_sample_500.jsonl` use karo for testing, full dataset for final training
