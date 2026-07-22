"""
ForgeAI Unified Configuration System
=====================================

Central configuration management for the entire ForgeAI ecosystem.
Loads from ~/.forgeai/config.json with environment variable overrides.

Design principles:
- Single source of truth for all configuration
- Environment variables override config file
- Sensible defaults for all settings
- Type-safe with validation
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CloudConfig:
    """Cloud services configuration (delegates to src.cloud.config for details).

    For actual cloud integration, use the 'cloud' module's get_cloud_config().
    This dataclass holds Forge AI's opinionated defaults for the config file.
    """

    enabled: bool = False
    app_url: str = "http://localhost:3000"
    allow_signups: bool = True
    require_subscription: bool = False


@dataclass
class InferenceConfig:
    """Inference engine configuration."""

    backend: str = "ollama"  # ollama, vllm, sglang, openai, anthropic
    url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    fallback_models: list[str] = field(default_factory=lambda: ["openai", "anthropic"])
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9

    # API keys (can be overridden by env vars)
    openai_key: str | None = None
    anthropic_key: str | None = None


@dataclass
class TrainingConfig:
    """Training pipeline configuration."""

    base_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 2e-4
    num_epochs: int = 1
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    max_length: int = 2048
    use_4bit: bool = True

    # SDFT ratios
    current_week_ratio: float = 0.70
    previous_week_ratio: float = 0.20
    foundational_ratio: float = 0.10

    # GRPO
    grpo_kl_coef: float = 0.04
    grpo_learning_rate: float = 1e-5


@dataclass
class RAGConfig:
    """RAG engine configuration."""

    chunk_size: int = 2000  # tokens
    chunk_overlap: int = 200  # tokens
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_store_path: str = "~/.forgeai/data/vector_store"
    knowledge_graph_path: str = "~/.forgeai/data/knowledge_graph"

    # Retrieval
    top_k: int = 5
    score_threshold: float = 0.5

    # cAST
    max_chunk_tokens: int = 2000
    min_chunk_tokens: int = 50
    merge_threshold: int = 300


@dataclass
class CaptureConfig:
    """Capture engine configuration."""

    db_path: str = "~/.forgeai/signals.db"
    encryption_key: str | None = None  # Auto-generated from machine ID if None
    project_name: str = "default"

    # Quality thresholds
    min_edit_distance_for_training: float = 0.1
    max_edit_distance_for_accept: float = 0.05


@dataclass
class AgentConfig:
    """Agent orchestration configuration."""

    orchestrator: str = "hermes-agent"
    skills_path: str = "~/.forgeai/skills"
    max_iterations: int = 10
    timeout_seconds: int = 300

    # Available agents
    agents: list[str] = field(default_factory=lambda: ["code", "debug", "docs", "teacher", "retrieval"])


@dataclass
class PathsConfig:
    """File system paths configuration."""

    models_dir: str = "~/.forgeai/models"
    adapters_dir: str = "~/.forgeai/adapters"
    data_dir: str = "~/.forgeai/data"
    logs_dir: str = "~/.forgeai/logs"
    checkpoints_dir: str = "~/.forgeai/checkpoints"
    replay_dir: str = "~/.forgeai/data/replay"
    foundational_dir: str = "~/.forgeai/data/foundational"


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_path: str | None = "~/.forgeai/logs/forgeai.log"
    max_size_mb: int = 100
    backup_count: int = 5


@dataclass
class ForgeAIConfig:
    """Master configuration for the entire ForgeAI ecosystem."""

    version: str = "2.0.0"

    # Sub-configs
    cloud: CloudConfig = field(default_factory=CloudConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Ecosystem
    ecosystem: dict[str, str] = field(
        default_factory=lambda: {
            "core_engine": "PythonAI",
            "agent_framework": "hermes-agent",
            "cli_interface": "open-claude",
            "dashboard": "Rudra-bots",
        }
    )

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> ForgeAIConfig:
        """Load configuration from JSON file."""
        if path is None:
            path = Path.home() / ".forgeai" / "config.json"

        path = Path(path)
        if not path.exists():
            return cls()  # Return defaults

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> ForgeAIConfig:
        """Create config from dictionary with nested structure."""
        config = cls()

        if "version" in data:
            config.version = data["version"]

        if "inference" in data:
            for key, value in data["inference"].items():
                if hasattr(config.inference, key):
                    setattr(config.inference, key, value)

        if "training" in data:
            for key, value in data["training"].items():
                if hasattr(config.training, key):
                    setattr(config.training, key, value)

        if "rag" in data:
            for key, value in data["rag"].items():
                if hasattr(config.rag, key):
                    setattr(config.rag, key, value)

        if "capture" in data:
            for key, value in data["capture"].items():
                if hasattr(config.capture, key):
                    setattr(config.capture, key, value)

        if "agent" in data:
            for key, value in data["agent"].items():
                if hasattr(config.agent, key):
                    setattr(config.agent, key, value)

        if "paths" in data:
            for key, value in data["paths"].items():
                if hasattr(config.paths, key):
                    setattr(config.paths, key, value)

        if "logging" in data:
            for key, value in data["logging"].items():
                if hasattr(config.logging, key):
                    setattr(config.logging, key, value)

        if "ecosystem" in data:
            config.ecosystem.update(data["ecosystem"])

        # Apply environment variable overrides
        config._apply_env_overrides()

        return config

    @classmethod
    def _from_env_only(cls) -> ForgeAIConfig:
        """Create config from environment variables only (no file)."""
        config = cls()
        config.cloud.enabled = os.getenv("FORGEAI_CLOUD_ENABLED", "").lower() in ("1", "true", "yes")
        config.cloud.app_url = os.getenv("FORGEAI_APP_URL", "http://localhost:3000")
        config.cloud.allow_signups = os.getenv("FORGEAI_ALLOW_SIGNUPS", "true").lower() in ("1", "true", "yes")
        config.cloud.require_subscription = os.getenv("FORGEAI_REQUIRE_SUBSCRIPTION", "").lower() in (
            "1",
            "true",
            "yes",
        )
        config._apply_env_overrides()
        return config

    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        # Cloud
        if os.getenv("FORGEAI_CLOUD_ENABLED"):
            self.cloud.enabled = os.getenv("FORGEAI_CLOUD_ENABLED").lower() in ("1", "true", "yes")
        if os.getenv("FORGEAI_ALLOW_SIGNUPS"):
            self.cloud.allow_signups = os.getenv("FORGEAI_ALLOW_SIGNUPS").lower() in ("1", "true", "yes")
        if os.getenv("FORGEAI_REQUIRE_SUBSCRIPTION"):
            self.cloud.require_subscription = os.getenv("FORGEAI_REQUIRE_SUBSCRIPTION").lower() in ("1", "true", "yes")
        if os.getenv("FORGEAI_APP_URL"):
            self.cloud.app_url = os.getenv("FORGEAI_APP_URL")

        # Inference
        if os.getenv("FORGEAI_MODEL"):
            self.inference.model = os.getenv("FORGEAI_MODEL")
        if os.getenv("FORGEAI_INFERENCE_BACKEND"):
            self.inference.backend = os.getenv("FORGEAI_INFERENCE_BACKEND")
        if os.getenv("FORGEAI_INFERENCE_URL"):
            self.inference.url = os.getenv("FORGEAI_INFERENCE_URL")
        if os.getenv("OPENAI_API_KEY"):
            self.inference.openai_key = os.getenv("OPENAI_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            self.inference.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        # Training
        if os.getenv("FORGEAI_BASE_MODEL"):
            self.training.base_model = os.getenv("FORGEAI_BASE_MODEL")
        if os.getenv("FORGEAI_LORA_RANK"):
            self.training.lora_rank = int(os.getenv("FORGEAI_LORA_RANK"))
        if os.getenv("FORGEAI_LEARNING_RATE"):
            self.training.learning_rate = float(os.getenv("FORGEAI_LEARNING_RATE"))
        if os.getenv("FORGEAI_BATCH_SIZE"):
            self.training.batch_size = int(os.getenv("FORGEAI_BATCH_SIZE"))

        # RAG
        if os.getenv("FORGEAI_TOP_K"):
            self.rag.top_k = int(os.getenv("FORGEAI_TOP_K"))

        # Logging
        if os.getenv("FORGEAI_LOG_LEVEL"):
            self.logging.level = os.getenv("FORGEAI_LOG_LEVEL")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "version": self.version,
            "inference": {
                "backend": self.inference.backend,
                "url": self.inference.url,
                "model": self.inference.model,
                "fallback_models": self.inference.fallback_models,
                "max_tokens": self.inference.max_tokens,
                "temperature": self.inference.temperature,
            },
            "training": {
                "base_model": self.training.base_model,
                "lora_rank": self.training.lora_rank,
                "learning_rate": self.training.learning_rate,
                "batch_size": self.training.batch_size,
                "sdft_ratios": {
                    "current": self.training.current_week_ratio,
                    "previous": self.training.previous_week_ratio,
                    "foundational": self.training.foundational_ratio,
                },
            },
            "rag": {
                "chunk_size": self.rag.chunk_size,
                "top_k": self.rag.top_k,
                "embedding_model": self.rag.embedding_model,
            },
            "agent": {
                "orchestrator": self.agent.orchestrator,
                "agents": self.agent.agents,
            },
            "ecosystem": self.ecosystem,
        }

    def save(self, path: str | Path | None = None):
        """Save configuration to JSON file."""
        if path is None:
            path = Path.home() / ".forgeai" / "config.json"

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def expand_path(self, path: str) -> Path:
        """Expand ~ in paths to absolute path."""
        return Path(path).expanduser()


# Global config instance (lazy loaded)
_config: ForgeAIConfig | None = None


def get_config() -> ForgeAIConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = ForgeAIConfig.from_file()
    return _config


def reload_config():
    """Reload configuration from file."""
    global _config
    _config = ForgeAIConfig.from_file()
    return _config


# Convenience functions
def get_model_path() -> Path:
    return get_config().expand_path(get_config().paths.models_dir)


def get_data_path() -> Path:
    return get_config().expand_path(get_config().paths.data_dir)


def get_signals_db_path() -> Path:
    return get_config().expand_path(get_config().capture.db_path)


if __name__ == "__main__":
    # Print current configuration
    config = get_config()
    print(json.dumps(config.to_dict(), indent=2))
