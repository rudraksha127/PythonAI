import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
notebook_path = ROOT / "colab_export" / "finetune_qwen14b_unsloth.ipynb"

print(f"Loading notebook: {notebook_path}")
with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

cells = nb.get("cells", [])

# 1. Dependency installation cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "pip install unsloth" in source_str:
        print("Found dependency installation cell. Patching...")
        cell["source"] = [
            "# Install dependencies based on environment\n",
            "import sys, os\n",
            'IS_COLAB = "google.colab" in sys.modules\n',
            'IS_KAGGLE = "KAGGLE_URL_BASE" in os.environ\n',
            "\n",
            "if IS_COLAB or IS_KAGGLE:\n",
            '    print("Installing GPU dependencies (Colab/Kaggle)...\\n")\n',
            "    import subprocess\n",
            '    subprocess.run("pip install unsloth", shell=True)\n',
            '    subprocess.run("pip install --upgrade --no-deps --force-reinstall unsloth", shell=True)\n',
            '    subprocess.run("pip install flash-attn --no-build-isolation", shell=True)\n',
            '    subprocess.run("pip install datasets", shell=True)\n',
            "else:\n",
            '    print("Local CPU environment detected. Skipping GPU-specific installations (Unsloth, Flash-Attn).\\n")\n',
            "    try:\n",
            "        import datasets\n",
            "    except ImportError:\n",
            "        import subprocess\n",
            '        subprocess.run("pip install datasets", shell=True)\n',
        ]

# 1.5 Environment detection cell (ensure ENV = env is set)
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if 'env = "vscode"' in source_str and "ENV =" not in source_str:
        print("Found environment detection cell. Patching to define ENV...")
        cell["source"].append("\nENV = env\n")

# 2. GPU verification cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if 'raise RuntimeError("No GPU detected! Go to Runtime > Change runtime type > T4 GPU")' in source_str:
        print("Found GPU verification cell. Patching...")
        cell["source"] = [
            "# Verify GPU\n",
            "import torch\n",
            'gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU"\n',
            "gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3 if torch.cuda.is_available() else 0\n",
            'print(f"GPU: {gpu_name}")\n',
            'print(f"VRAM: {gpu_mem:.1f} GB")\n',
            'print(f"PyTorch: {torch.__version__}")\n',
            "print(f\"CUDA: {torch.version.cuda if torch.cuda.is_available() else 'None'}\\n\")\n",
            "\n",
            "if not torch.cuda.is_available():\n",
            '    if ENV in ["colab", "kaggle"]:\n',
            '        raise RuntimeError("No GPU detected! Go to Runtime > Change runtime type > T4 GPU")\n',
            "    else:\n",
            '        print("WARNING: No GPU detected. Running in Local CPU Fallback mode.")\n',
            "elif gpu_mem < 14:\n",
            '    print("Warning: Less than 14GB VRAM - training may OOM. Try reducing max_seq_length.")\n',
        ]

# 3. Dataset Option A: HF Dataset loading cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if 'HF_DATASET = "YOUR_HF_USERNAME/pythonai-training-data"' in source_str and "load_dataset" in source_str:
        print("Found Option A (HF Dataset loading) cell. Patching...")
        cell["source"] = [
            "from datasets import load_dataset\n",
            "\n",
            "# ===== SET YOUR HF DATASET NAME HERE =====\n",
            'HF_DATASET = "YOUR_HF_USERNAME/pythonai-training-data"\n',
            "# ==========================================\n",
            "\n",
            'if "YOUR_HF_USERNAME" not in HF_DATASET:\n',
            "    try:\n",
            '        dataset = load_dataset(HF_DATASET, split="train")\n',
            '        print(f"Loaded {len(dataset):,} examples")\n',
            "        print(f\"Sample: {dataset[0]['instruction'][:80]}...\")\n",
            "    except Exception as e:\n",
            '        print(f"Failed to load from HF: {e}. Skipping Option A.")\n',
            "else:\n",
            '    print("Option A skipped (placeholder detected). Use Option B to load local dataset.")\n',
        ]

# 4. Dataset Option B: Local loading/upload cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "files.upload()" in source_str and "rows = []" in source_str:
        print("Found dataset upload cell (Option B). Patching...")
        cell["source"] = [
            "# Load dataset\n",
            "import json\n",
            "from datasets import Dataset\n",
            "\n",
            'if ENV == "vscode":\n',
            "    # Local loading for VS Code\n",
            '    dataset_path = "colab_export/training_dataset.jsonl"\n',
            '    print(f"Loading local dataset from {dataset_path}...")\n',
            "    rows = []\n",
            '    with open(dataset_path, "r", encoding="utf-8") as f:\n',
            "        for line in f:\n",
            "            if line.strip():\n",
            "                rows.append(json.loads(line))\n",
            "    dataset = Dataset.from_list(rows)\n",
            '    print(f"Loaded {len(dataset):,} examples locally.")\n',
            "else:\n",
            "    # Upload the JSONL file from your computer (Colab only)\n",
            "    from google.colab import files\n",
            '    print("Upload training_dataset.jsonl from the colab_export folder...")\n',
            "    uploaded = files.upload()\n",
            "\n",
            "    filename = list(uploaded.keys())[0]\n",
            "    rows = []\n",
            "    for line in uploaded[filename].decode('utf-8').splitlines():\n",
            "        if line.strip():\n",
            "            rows.append(json.loads(line))\n",
            "\n",
            "    dataset = Dataset.from_list(rows)\n",
            '    print(f"Loaded {len(dataset):,} examples from {filename}")\n',
        ]

# 5. Dataset Option C: Google Drive cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "drive.mount('/content/drive')" in source_str:
        print("Found Option C (Google Drive) cell. Patching...")
        cell["source"] = [
            'if ENV == "colab":\n',
            "    from google.colab import drive\n",
            "    drive.mount('/content/drive')\n",
            "\n",
            "    import json\n",
            "    from datasets import Dataset\n",
            "\n",
            "    # ===== SET YOUR PATH =====\n",
            '    DRIVE_PATH = "/content/drive/MyDrive/pythonai_training/training_dataset.jsonl"\n',
            "    # =========================\n",
            "\n",
            "    if os.path.exists(DRIVE_PATH):\n",
            "        rows = []\n",
            "        with open(DRIVE_PATH, 'r', encoding='utf-8') as f:\n",
            "            for line in f:\n",
            "                if line.strip():\n",
            "                    rows.append(json.loads(line))\n",
            "\n",
            "        dataset = Dataset.from_list(rows)\n",
            '        print(f"Loaded {len(dataset):,} examples from Google Drive")\n',
            "    else:\n",
            '        print(f"Google Drive path not found: {DRIVE_PATH}")\n',
            "else:\n",
            '    print("Option C skipped (not in Colab).")\n',
        ]

# 6. Dataset Option D: Kaggle cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if 'KAGGLE_DATA_PATH = "/kaggle/input/' in source_str:
        print("Found Option D (Kaggle Dataset) cell. Patching...")
        cell["source"] = [
            "# This cell is for Kaggle environment - dataset added via Add Data button\n",
            "import os, json\n",
            "from datasets import Dataset\n",
            "\n",
            "# List available input datasets\n",
            'input_dir = "/kaggle/input/"\n',
            "if os.path.exists(input_dir):\n",
            '    print("Available Kaggle datasets:")\n',
            "    for d in os.listdir(input_dir):\n",
            '        print(f"  {d}")\n',
            "        for f in os.listdir(os.path.join(input_dir, d)):\n",
            '            print(f"    - {f}")\n',
            "\n",
            "# ===== SET YOUR KAGGLE DATASET PATH =====\n",
            'KAGGLE_DATA_PATH = "/kaggle/input/pythonai-training-data/training_dataset.jsonl"\n',
            "# =========================================\n",
            "\n",
            'if ENV == "kaggle" and os.path.exists(KAGGLE_DATA_PATH):\n',
            "    rows = []\n",
            "    with open(KAGGLE_DATA_PATH, 'r', encoding='utf-8') as f:\n",
            "        for line in f:\n",
            "            if line.strip():\n",
            "                rows.append(json.loads(line))\n",
            "    dataset = Dataset.from_list(rows)\n",
            '    print(f"Loaded {len(dataset):,} examples from Kaggle dataset")\n',
            "else:\n",
            '    print("Option D skipped (not on Kaggle or dataset not found).")\n',
        ]

# 7. Model loading cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if (
        'MODEL_NAME = "unsloth/Qwen2.5-Coder-14B-bnb-4bit"' in source_str
        and "FastLanguageModel.from_pretrained" in source_str
    ):
        print("Found model loading cell. Patching...")
        cell["source"] = [
            "import torch\n",
            "\n",
            'MODEL_NAME = "unsloth/Qwen2.5-Coder-14B-bnb-4bit"\n',
            "MAX_SEQ_LENGTH = 1024\n",
            "\n",
            "# Check if we can use Unsloth (needs CUDA and unsloth package)\n",
            "use_unsloth = False\n",
            "try:\n",
            "    from unsloth import FastLanguageModel\n",
            "    if torch.cuda.is_available():\n",
            "        use_unsloth = True\n",
            "except ImportError:\n",
            "    pass\n",
            "\n",
            "if use_unsloth:\n",
            '    print("Loading 4-bit model with Unsloth optimizations...")\n',
            "    model, tokenizer = FastLanguageModel.from_pretrained(\n",
            "        model_name=MODEL_NAME,\n",
            "        max_seq_length=MAX_SEQ_LENGTH,\n",
            "        dtype=None,  # Auto-detect\n",
            "        load_in_4bit=True,\n",
            "    )\n",
            "else:\n",
            '    print("Unsloth or CUDA not available. Falling back to standard HF transformers on CPU.")\n',
            "    # For CPU training, use a very small model (sshleifer/tiny-gpt2)\n",
            "    # to avoid downloading 14B model and running out of CPU RAM\n",
            '    FALLBACK_MODEL = "sshleifer/tiny-gpt2"\n',
            '    print(f"Using fallback model: {FALLBACK_MODEL}")\n',
            "    from transformers import AutoModelForCausalLM, AutoTokenizer\n",
            "    tokenizer = AutoTokenizer.from_pretrained(FALLBACK_MODEL)\n",
            "    if tokenizer.pad_token is None:\n",
            "        tokenizer.pad_token = tokenizer.eos_token\n",
            "    model = AutoModelForCausalLM.from_pretrained(FALLBACK_MODEL)\n",
            "\n",
            'print(f"Model loaded! Parameters: {model.num_parameters():,}")\n',
            'print(f"Trainable: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")\n',
        ]

# 8. Add LoRA cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "model = FastLanguageModel.get_peft_model(" in source_str and "r=16" in source_str:
        print("Found PEFT/LoRA cell. Patching...")
        cell["source"] = [
            "if use_unsloth:\n",
            "    model = FastLanguageModel.get_peft_model(\n",
            "        model,\n",
            "        r=16,\n",
            "        target_modules=[\n",
            '            "q_proj", "k_proj", "v_proj", "o_proj",\n',
            '            "gate_proj", "up_proj", "down_proj",\n',
            "        ],\n",
            "        lora_alpha=16,\n",
            "        lora_dropout=0.05,\n",
            '        bias="none",\n',
            '        use_gradient_checkpointing="unsloth",\n',
            "        random_state=42,\n",
            "    )\n",
            "else:\n",
            '    print("Using standard PEFT/LoraConfig for fallback model...")\n',
            "    from peft import LoraConfig, get_peft_model\n",
            "    # Find proper linear layers for fallback model\n",
            '    model_type = getattr(getattr(model, "config", None), "model_type", "").lower()\n',
            '    if "gpt2" in model_type:\n',
            '        target_modules = ["c_attn", "c_proj"]\n',
            "    else:\n",
            '        target_modules = ["q_proj", "v_proj"]\n',
            "        \n",
            "    lora_config = LoraConfig(\n",
            "        r=16,\n",
            "        lora_alpha=16,\n",
            "        lora_dropout=0.05,\n",
            '        bias="none",\n',
            '        task_type="CAUSAL_LM",\n',
            "        target_modules=target_modules,\n",
            "    )\n",
            "    model = get_peft_model(model, lora_config)\n",
            "\n",
            "trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)\n",
            "total = model.num_parameters()\n",
            'print(f"Trainable: {trainable:,} / {total:,} ({trainable/total*100:.2f}%)")\n',
        ]

# 9. SFTTrainer cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if (
        "trainer = SFTTrainer(" in source_str
        and "per_device_train_batch_size=2" in source_str
        and "qwen14b_pythonai_adapter" in source_str
    ):
        print("Found trainer configuration cell. Patching...")
        cell["source"] = [
            "from trl import SFTTrainer\n",
            "from transformers import TrainingArguments\n",
            "\n",
            "if use_unsloth:\n",
            "    from unsloth import is_bfloat16_supported\n",
            "    bf16_val = is_bfloat16_supported()\n",
            "    fp16_val = not bf16_val\n",
            '    optim_val = "adamw_8bit"\n',
            "else:\n",
            "    bf16_val = False\n",
            "    fp16_val = False\n",
            '    optim_val = "adamw_torch"\n',
            "\n",
            "# Define local CPU smoke test overrides\n",
            "max_steps_val = 2 if not use_unsloth else -1\n",
            "epochs_val = 1.0 if use_unsloth else 1.0\n",
            "dataset_num_proc_val = 2 if use_unsloth else 1\n",
            "\n",
            "trainer = SFTTrainer(\n",
            "    model=model,\n",
            "    tokenizer=tokenizer,\n",
            "    train_dataset=train_dataset,\n",
            "    eval_dataset=eval_dataset,\n",
            '    dataset_text_field="text",\n',
            "    max_seq_length=MAX_SEQ_LENGTH,\n",
            "    dataset_num_proc=dataset_num_proc_val,\n",
            "    packing=False,\n",
            "    args=TrainingArguments(\n",
            '        output_dir="./qwen14b_pythonai_adapter",\n',
            "        per_device_train_batch_size=2,\n",
            "        per_device_eval_batch_size=2,\n",
            "        gradient_accumulation_steps=4,\n",
            "        warmup_steps=2 if not use_unsloth else 20,\n",
            "        max_steps=max_steps_val,\n",
            "        num_train_epochs=epochs_val,\n",
            "        learning_rate=2e-4,\n",
            "        fp16=fp16_val,\n",
            "        bf16=bf16_val,\n",
            "        logging_steps=1,\n",
            "        optim=optim_val,\n",
            "        weight_decay=0.01,\n",
            '        lr_scheduler_type="cosine",\n',
            "        seed=42,\n",
            '        report_to="none",\n',
            '        evaluation_strategy="steps" if use_unsloth else "no",\n',
            "        eval_steps=50,\n",
            '        save_strategy="steps" if use_unsloth else "no",\n',
            "        save_steps=100,\n",
            "        save_total_limit=2,\n",
            "    ),\n",
            ")\n",
            "\n",
            'print("Trainer configured!")\n',
            "if use_unsloth:\n",
            '    print(f"Batch size: 2, Grad accum: 4, Effective batch: 8")\n',
            "else:\n",
            '    print("Running in Local CPU Fallback (Smoke Test Mode: max_steps=2)")\n',
        ]

# 10. Inference testing cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "test_model, test_tokenizer = FastLanguageModel.from_pretrained(" in source_str:
        print("Found inference testing cell. Patching...")
        cell["source"] = [
            "# Test inference with the trained adapter\n",
            "if use_unsloth:\n",
            "    from unsloth import FastLanguageModel\n",
            "\n",
            "    # Load base model + trained adapter\n",
            "    test_model, test_tokenizer = FastLanguageModel.from_pretrained(\n",
            "        model_name=MODEL_NAME,\n",
            "        max_seq_length=MAX_SEQ_LENGTH,\n",
            "        dtype=None,\n",
            "        load_in_4bit=True,\n",
            "    )\n",
            "    test_model.load_adapter(ADAPTER_DIR)\n",
            "    FastLanguageModel.for_inference(test_model)\n",
            '    device = "cuda"\n',
            "else:\n",
            '    print("Using standard transformers + PEFT for inference on CPU...")\n',
            "    from transformers import AutoModelForCausalLM, AutoTokenizer\n",
            "    from peft import PeftModel\n",
            "    test_tokenizer = AutoTokenizer.from_pretrained(FALLBACK_MODEL)\n",
            "    base_model = AutoModelForCausalLM.from_pretrained(FALLBACK_MODEL)\n",
            "    test_model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)\n",
            '    device = "cpu"\n',
            "\n",
            "def generate_response(prompt):\n",
            '    formatted = alpaca_prompt.format(prompt, "")\n',
            '    inputs = test_tokenizer([formatted], return_tensors="pt").to(device)\n',
            "    outputs = test_model.generate(\n",
            "        **inputs,\n",
            '        max_new_tokens=64 if device == "cpu" else 256,\n',
            "        temperature=0.7,\n",
            "        top_p=0.95,\n",
            "        repetition_penalty=1.1,\n",
            "    )\n",
            "    response = test_tokenizer.decode(outputs[0], skip_special_tokens=True)\n",
            '    response = response.split("### Response:")[-1].strip()\n',
            "    return response\n",
            "\n",
            "# Test prompts\n",
            "test_prompts = [\n",
            '    "Explain Python context managers and the `with` statement.",\n',
            '    "Write a Python function to merge two sorted lists.",\n',
            '    "What is the difference between a list and a tuple in Python?",\n',
            "]\n",
            "\n",
            "for prompt in test_prompts:\n",
            "    print(f\"\\n{'='*60}\")\n",
            '    print(f"Q: {prompt}")\n',
            '    print(f"\\nA: {generate_response(prompt)}")\n',
        ]

# 11. Model merging cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "merged_model, merged_tokenizer = FastLanguageModel.from_pretrained(" in source_str:
        print("Found model merging cell. Patching...")
        cell["source"] = [
            "# Merge LoRA weights into base model\n",
            "if use_unsloth:\n",
            "    merged_model, merged_tokenizer = FastLanguageModel.from_pretrained(\n",
            "        model_name=MODEL_NAME,\n",
            "        max_seq_length=MAX_SEQ_LENGTH,\n",
            "        dtype=None,\n",
            "        load_in_4bit=True,\n",
            "    )\n",
            "    merged_model.load_adapter(ADAPTER_DIR)\n",
            "    merged_model = merged_model.merge_and_unload()\n",
            "else:\n",
            '    print("Merging model weights on CPU using standard PEFT...")\n',
            "    from transformers import AutoModelForCausalLM, AutoTokenizer\n",
            "    from peft import PeftModel\n",
            "    merged_tokenizer = AutoTokenizer.from_pretrained(FALLBACK_MODEL)\n",
            "    base_model = AutoModelForCausalLM.from_pretrained(FALLBACK_MODEL)\n",
            "    peft_model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)\n",
            "    merged_model = peft_model.merge_and_unload()\n",
            "\n",
            'print("LoRA weights merged into base model!")\n',
        ]

# 12. Quick test cell
for cell in cells:
    source_str = "".join(cell.get("source", []))
    if "quick_trainer = SFTTrainer(" in source_str:
        print("Found quick test cell. Patching...")
        cell["source"] = [
            "# Quick test: 50 steps on a 200-example subset (~5 min)\n",
            "if use_unsloth:\n",
            "    from unsloth import is_bfloat16_supported\n",
            "    bf16_val = is_bfloat16_supported()\n",
            "    fp16_val = not bf16_val\n",
            '    optim_val = "adamw_8bit"\n',
            "    max_steps_val = 50\n",
            "else:\n",
            "    bf16_val = False\n",
            "    fp16_val = False\n",
            '    optim_val = "adamw_torch"\n',
            "    max_steps_val = 2\n",
            "\n",
            "quick_trainer = SFTTrainer(\n",
            "    model=model,\n",
            "    tokenizer=tokenizer,\n",
            "    train_dataset=train_dataset.select(range(min(200, len(train_dataset)))),\n",
            "    eval_dataset=eval_dataset.select(range(min(40, len(eval_dataset)))),\n",
            '    dataset_text_field="text",\n',
            "    max_seq_length=MAX_SEQ_LENGTH,\n",
            "    packing=False,\n",
            "    args=TrainingArguments(\n",
            '        output_dir="./qwen14b_quicktest",\n',
            "        per_device_train_batch_size=2,\n",
            "        gradient_accumulation_steps=4,\n",
            "        warmup_steps=2 if not use_unsloth else 5,\n",
            "        max_steps=max_steps_val,\n",
            "        learning_rate=2e-4,\n",
            "        fp16=fp16_val,\n",
            "        bf16=bf16_val,\n",
            "        logging_steps=1,\n",
            "        optim=optim_val,\n",
            "        seed=42,\n",
            '        report_to="none",\n',
            "    ),\n",
            ")\n",
            "\n",
            'print(f"Running quick test ({max_steps_val} steps)...")\n',
            "quick_trainer.train()\n",
            'print("Quick test complete!")\n',
        ]

print("Saving modified notebook...")
with open(notebook_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print("Notebook patched successfully!")
