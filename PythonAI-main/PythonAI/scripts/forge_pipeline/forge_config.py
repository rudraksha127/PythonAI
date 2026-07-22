from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
import psutil
from dotenv import load_dotenv

try:
    import torch

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


ROOT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = ROOT_DIR / "forge_workspace"
DATA_DIR = WORKSPACE_DIR / "data"

# ── HARDWARE DETECTION ──────────────────────────────────────────────────────


def get_hardware_profile():
    cpu_cores = os.cpu_count() or 4
    total_ram_gb = psutil.virtual_memory().total / (1024**3)
    free_ram_gb = psutil.virtual_memory().available / (1024**3)
    disk_free_gb = psutil.disk_usage(str(ROOT_DIR)).free / (1024**3)

    has_cuda = False
    gpu_name = "None"
    vram_gb = 0.0

    if HAS_TORCH and torch.cuda.is_available():
        has_cuda = True
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)

    # Determine tier
    if vram_gb >= 40:
        tier = "ultra"
    elif vram_gb >= 24:
        tier = "high"
    elif vram_gb >= 12:
        tier = "medium"
    elif vram_gb >= 6:
        tier = "low"
    elif has_cuda:
        tier = "minimal_gpu"
    else:
        tier = "cpu"

    return {
        "cpu_cores": cpu_cores,
        "total_ram_gb": total_ram_gb,
        "free_ram_gb": free_ram_gb,
        "disk_free_gb": disk_free_gb,
        "has_cuda": has_cuda,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "tier": tier,
    }


def select_best_model(hw_profile: dict) -> dict:
    """Select the best model architecture and training params based on hardware."""
    tier = hw_profile.get("tier", "cpu")

    configs = {
        "ultra": {  # 40GB+ VRAM (A100, H100, etc.)
            "base_model": "meta-llama/Meta-Llama-3-70B",
            "load_in_4bit": True,
            "batch_size": 4,
            "grad_accum": 4,
            "lora_rank": 32,
            "max_length": 4096,
            "learning_rate": 1e-4,
        },
        "high": {  # 24GB+ VRAM (RTX 3090/4090, A10g)
            "base_model": "mistralai/Mistral-7B-Instruct-v0.2",
            "load_in_4bit": True,
            "batch_size": 4,
            "grad_accum": 4,
            "lora_rank": 16,
            "max_length": 2048,
            "learning_rate": 2e-4,
        },
        "medium": {  # 12-16GB VRAM (T4, RTX 3060/4070)
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "load_in_4bit": True,
            "batch_size": 2,
            "grad_accum": 8,
            "lora_rank": 8,
            "max_length": 1024,
            "learning_rate": 2e-4,
        },
        "low": {  # 6-12GB VRAM
            "base_model": "microsoft/phi-2",
            "load_in_4bit": True,
            "batch_size": 1,
            "grad_accum": 8,
            "lora_rank": 8,
            "max_length": 512,
            "learning_rate": 3e-4,
        },
        "minimal_gpu": {  # <6GB VRAM
            "base_model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "load_in_4bit": True,
            "batch_size": 1,
            "grad_accum": 16,
            "lora_rank": 4,
            "max_length": 256,
            "learning_rate": 3e-4,
        },
        "cpu": {  # CPU Only
            "base_model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "load_in_4bit": False,
            "batch_size": 1,
            "grad_accum": 8,
            "lora_rank": 4,
            "max_length": 512,
            "learning_rate": 3e-4,
        },
    }

    return configs.get(tier, configs["cpu"])


# ── CONFIGURATION ────────────────────────────────────────────────────────────


@dataclass
class ForgeConfig:
    # ── PATHS ────────────────────────────────────────────────────────────────
    root_dir: str = str(ROOT_DIR)
    workspace_dir: str = str(WORKSPACE_DIR)
    raw_data_dir: str = str(DATA_DIR / "raw")
    clean_data_dir: str = str(DATA_DIR / "clean")
    train_data_dir: str = str(DATA_DIR / "train")
    checkpoint_dir: str = str(WORKSPACE_DIR / "checkpoints")
    final_model_dir: str = str(WORKSPACE_DIR / "final_model")
    logs_dir: str = str(WORKSPACE_DIR / "logs")

    # ── API KEYS (set as env vars or in .env file) ────────────────────────────
    hf_token: str = ""
    anthropic_key: str = ""
    openai_key: str = ""
    groq_key: str = ""
    cerebras_key: str = ""
    sambanova_key: str = ""
    openrouter_key: str = ""
    mistral_key: str = ""
    nvidia_llama_key: str = ""
    nvidia_nemotron_key: str = ""
    nvidia_mavarik_key: str = ""
    nvidia_qwen_key: str = ""
    nvidia_moonshot_key: str = ""
    all_api_keys: dict = field(default_factory=dict)

    # ── DATA COLLECTION ──────────────────────────────────────────────────────
    max_download_size_gb: float = 20.0
    max_rows_per_dataset: int = 50000
    synthetic_per_task: int = 100
    languages: list = field(default_factory=lambda: ["en", "hi", "bn", "te", "ta", "mr"])
    min_text_length: int = 100
    max_text_length: int = 8192
    dedup_threshold: float = 0.8  # MinHash similarity threshold

    # ── MODEL SETTINGS (auto-filled by hardware detection) ───────────────────
    base_model: str = ""
    load_in_4bit: bool = False
    batch_size: int = 1
    grad_accum: int = 8
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    max_length: int = 512
    epochs: float = 1.0
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    weight_decay: float = 0.001
    num_epochs: int = 3

    # ── STATE ─────────────────────────────────────────────────────────────────
    hardware_profile: dict = field(default_factory=dict)

    def __post_init__(self):
        # Ensure all directories exist
        for attr_name in [
            "workspace_dir",
            "raw_data_dir",
            "clean_data_dir",
            "train_data_dir",
            "checkpoint_dir",
            "final_model_dir",
            "logs_dir",
        ]:
            path_str = getattr(self, attr_name)
            Path(path_str).mkdir(parents=True, exist_ok=True)

        if not self.hardware_profile:
            self.hardware_profile = get_hardware_profile()
            model_params = select_best_model(self.hardware_profile)

            # Auto-fill from selected model params
            self.base_model = model_params["base_model"]
            self.load_in_4bit = model_params["load_in_4bit"]
            self.batch_size = model_params["batch_size"]
            self.grad_accum = model_params["grad_accum"]
            self.lora_rank = model_params["lora_rank"]
            self.max_length = model_params["max_length"]
            self.learning_rate = model_params.get("learning_rate", self.learning_rate)

        # Load .env file
        dotenv_path = ROOT_DIR / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path)

        # Read API keys from environment if not set
        if not self.hf_token:
            self.hf_token = os.getenv("HF_TOKEN", "")
        if not self.anthropic_key:
            self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not self.openai_key:
            self.openai_key = os.getenv("OPENAI_API_KEY", "")
        if not self.groq_key:
            self.groq_key = os.getenv("GROQ_API_KEY", "")

    def save(self):
        config_path = Path(self.workspace_dir) / "forge_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls):
        config_path = WORKSPACE_DIR / "forge_config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return cls(**data)
        return cls()

    @classmethod
    def setup_dirs(cls):
        """Convenience: create all required directories."""
        cfg = cls()
        for attr_name in [
            "workspace_dir",
            "raw_data_dir",
            "clean_data_dir",
            "train_data_dir",
            "checkpoint_dir",
            "final_model_dir",
            "logs_dir",
        ]:
            Path(getattr(cfg, attr_name)).mkdir(parents=True, exist_ok=True)
        print("[OK] Directory structure created")
        return cfg


if __name__ == "__main__":
    cfg = ForgeConfig()
    cfg.save()
    print("\n" + "=" * 50)
    print("FORGE-OMEGA Configuration Generated")
    print("=" * 50)
    print(f"Hardware Tier : {cfg.hardware_profile.get('tier', 'unknown')}")
    print(f"Selected Model: {cfg.base_model}")
    print(f"CUDA Available: {cfg.hardware_profile.get('has_cuda', False)}")
    print(f"Batch Size    : {cfg.batch_size}")
    print(f"Grad Accum    : {cfg.grad_accum}")
    print(f"Max Length    : {cfg.max_length}")
    print(f"LoRA Rank     : {cfg.lora_rank}")
    print(f"4-bit QLoRA   : {cfg.load_in_4bit}")
    print(f"Workspace     : {cfg.workspace_dir}")
