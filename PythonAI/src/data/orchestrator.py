"""
AntiGravityOrchestrator — Master Controller
=============================================
Phased execution of data collection, processing, and training.
Inspired by Dario Amodei's "Machines of Loving Grace" vision.
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ═══════════════════════════════════════════════════
# Config & Status Types (imported by src.data.__init__)
# ═══════════════════════════════════════════════════

class TaskStatus(Enum):
    """Status of an individual collection task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PhaseStatus(Enum):
    """Status of a collection phase"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class Phase(Enum):
    """Collection phases"""
    PHASE1 = "phase1"
    PHASE2 = "phase2"
    PHASE3 = "phase3"
    PHASE4 = "phase4"
    PHASE5 = "phase5"
    HF = "hf"
    ARXIV = "arxiv"
    OPENALEX = "openalex"
    AUDIO = "audio"
    SYNTHETIC = "synthetic"


@dataclass
class CollectionTask:
    """A single data collection task with its configuration and status"""
    name: str
    source_type: str
    params: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    records_collected: int = 0
    error_message: str = ""
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class OrchestratorConfig:
    """Configuration for the AntiGravity orchestrator"""
    base_output_dir: str = "D:/PythonAI_Data/anti_gravity_data"
    max_concurrent: int = 30
    synthetic_per_task: int = 1000
    priorities: dict = field(default_factory=dict)
    phase1_sources: dict = field(default_factory=lambda: {
        "huggingface_datasets": True,
        "arxiv_papers": True,
        "openalex_snapshot": True,
        "openimages": True,
    })


@dataclass
class PhaseResult:
    """Result of a single phase execution"""
    name: str
    status: str  # "✅ SUCCESS", "❌ FAILED", "⏭️ SKIPPED"
    duration_seconds: float = 0.0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceStatus:
    """Track the status of a data source"""
    name: str
    source_type: str  # "hf", "arxiv", "openalex", "image", "video", "audio", "synthetic"
    status: str = "pending"  # pending, downloading, complete, failed
    size_bytes: int = 0
    num_items: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class AntiGravityOrchestrator:
    """
    Master controller for the AntiGravity data collection system.

    Coordinates phased execution of:
    - Phase 1: Text & Code (HuggingFace, arXiv, OpenAlex)
    - Phase 2: Multimodal (Images, Video, Audio)
    - Phase 3: Synthetic Data Generation
    - Phase 4: Quality Processing (dedup, filter, clean)
    - Phase 5: Training Pipeline Integration

    Usage:
        orchestrator = AntiGravityOrchestrator("ag_config.json")
        await orchestrator.run_phase("phase1")
        await orchestrator.run_all()
    """

    def __init__(self, config_path: str = "ag_config.json"):
        self.config = self._load_config(config_path)
        self.base_dir = Path(self.config.get("base_output_dir", "./anti_gravity_data"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.status_dir = self.base_dir / ".status"
        self.status_dir.mkdir(exist_ok=True)

        self.phase_results: list[PhaseResult] = []
        self.source_statuses: dict[str, DataSourceStatus] = {}

        # Track whether individual sources should be run
        self.priorities = self.config.get("priorities", {})
        self.phase1_sources = self.config.get("phase1_sources", {})

    def _load_config(self, path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config {path} not found, using defaults")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Config {path} is invalid JSON: {e}")
            return {}

    def _get_key(self, env_key: str, default: str | None = None) -> str | None:
        """Get API key from environment or config"""
        import os
        return os.environ.get(env_key) or self.config.get(env_key.lower(), default)

    def _update_source_status(self, name: str, source_type: str, status: str,
                              size_bytes: int = 0, num_items: int = 0,
                              error: str | None = None):
        """Update tracking status for a data source"""
        now = datetime.now(timezone.utc).isoformat()
        if name not in self.source_statuses:
            self.source_statuses[name] = DataSourceStatus(
                name=name, source_type=source_type,
                started_at=now if status in ("downloading", "complete") else None
            )
        entry = self.source_statuses[name]
        entry.status = status
        entry.completed_at = now if status in ("complete", "failed") else entry.completed_at
        if size_bytes:
            entry.size_bytes = size_bytes
        if num_items:
            entry.num_items = num_items
        if error:
            entry.error = error
        self._save_status()

    def _save_status(self):
        """Persist source statuses to disk"""
        try:
            status_file = self.status_dir / "sources.json"
            data = {k: asdict(v) for k, v in self.source_statuses.items()}
            status_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug(f"Failed to save status: {e}")

    def _load_status(self) -> dict[str, DataSourceStatus]:
        """Load persisted source statuses"""
        try:
            status_file = self.status_dir / "sources.json"
            if status_file.exists():
                data = json.loads(status_file.read_text())
                for k, v in data.items():
                    self.source_statuses[k] = DataSourceStatus(**v)
        except Exception as e:
            logger.debug(f"Failed to load status: {e}")
        return self.source_statuses

    async def run_phase(self, phase_name: str, force: bool = False) -> PhaseResult:
        """
        Execute a specific phase by name.

        Returns:
            PhaseResult with status, duration, and details
        """
        phase_map = {
            "phase1": self._run_phase1_text,
            "phase2": self._run_phase2_multimodal,
            "phase3": self._run_phase3_synthetic,
            "phase4": self._run_phase4_quality,
            "phase5": self._run_phase5_training,
            "hf": self._run_hf_download,
            "arxiv": self._run_arxiv_collect,
            "openalex": self._run_openalex_collect,
            "images": self._run_image_collect,
            "audio": self._run_audio_collect,
            "synthetic": self._run_synthetic,
        }

        runner = phase_map.get(phase_name)
        if not runner:
            return PhaseResult(
                name=phase_name,
                status="❌ FAILED",
                error=f"Unknown phase: {phase_name}. Available: {', '.join(phase_map.keys())}"
            )

        logger.info(f"[Phase] Starting {phase_name}")
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(runner):
                result = await runner(force)
            else:
                result = runner(force)
            duration = time.time() - start
            pr = PhaseResult(
                name=phase_name,
                status="✅ SUCCESS" if result else "⚠️ PARTIAL",
                duration_seconds=duration,
                details={"force": force}
            )
            logger.success(f"[Phase] {phase_name} completed in {duration:.1f}s")
            return pr
        except Exception as e:
            duration = time.time() - start
            pr = PhaseResult(
                name=phase_name,
                status="❌ FAILED",
                duration_seconds=duration,
                error=str(e),
                details={"force": force}
            )
            logger.error(f"[Phase] {phase_name} failed after {duration:.1f}s: {e}")
            return pr

    async def run_all(self, force: bool = False):
        """Execute all phases in sequence"""
        console.print(Panel.fit(
            "[bold green]╔══════════════════════════════════════════════════════╗\n"
            "║     ⚡ ANTI-GRAVITY ORCHESTRATOR ⚡                      ║\n"
            "║     \"A country of geniuses in a data center\"             ║\n"
            "║     — Dario Amodei, Machines of Loving Grace             ║\n"
            "╚══════════════════════════════════════════════════════╝[/bold green]",
            title="🚀 Initializing"
        ))

        phases = ["phase1", "phase2", "phase3", "phase4", "phase5"]
        self.phase_results = []

        for phase in phases:
            result = await self.run_phase(phase, force=force)
            self.phase_results.append(result)
            self._print_phase_summary()

        self._print_final_report()

    # ── Phase Implementations ──────────────────────────────────

    async def _run_phase1_text(self, force: bool = False) -> bool:
        """Phase 1: Text & Code collection"""
        console.print("[bold cyan]▶ Phase 1: Text & Code Collection[/bold cyan]")

        tasks = []
        if self.phase1_sources.get("huggingface_datasets", True):
            tasks.append(self._run_hf_download(force))
        if self.phase1_sources.get("arxiv_papers", True):
            tasks.append(self._run_arxiv_collect(force))
        if self.phase1_sources.get("openalex_snapshot", True):
            tasks.append(self._run_openalex_collect(force))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if r is True or r is None)
        return successes >= len(tasks) * 0.5  # 50% success threshold

    async def _run_phase2_multimodal(self, force: bool = False) -> bool:
        """Phase 2: Image, Video, Audio collection"""
        console.print("[bold cyan]▶ Phase 2: Multimodal Collection[/bold cyan]")

        tasks = []
        if self.phase1_sources.get("openimages", True):
            tasks.append(self._run_image_collect(force))
        tasks.append(self._run_audio_collect(force))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if r is True or r is None)
        return successes >= len(tasks) * 0.5

    async def _run_phase3_synthetic(self, force: bool = False) -> bool:
        """Phase 3: Synthetic data generation"""
        console.print("[bold cyan]▶ Phase 3: Synthetic Data Generation[/bold cyan]")
        return await self._run_synthetic(force)

    async def _run_phase4_quality(self, force: bool = False) -> bool:
        """Phase 4: Quality processing pipeline"""
        console.print("[bold cyan]▶ Phase 4: Quality Processing[/bold cyan]")
        # TODO: Implement full quality pipeline
        logger.info("Quality processing phase placeholder")
        return True

    async def _run_phase5_training(self, force: bool = False) -> bool:
        """Phase 5: Training pipeline integration"""
        console.print("[bold cyan]▶ Phase 5: Training Pipeline[/bold cyan]")
        # TODO: Implement training launch
        logger.info("Training pipeline phase placeholder")
        return True

    # ── Individual Source Runners ──────────────────────────────

    async def _run_hf_download(self, force: bool = False) -> bool:
        """Run HuggingFace mass downloader"""
        logger.info("Starting HuggingFace dataset downloads...")
        self._update_source_status("huggingface_datasets", "hf", "downloading")

        try:
            from collect_everything import HuggingFaceMassDownloader
            downloader = HuggingFaceMassDownloader(
                str(self.base_dir / "huggingface"),
                self._get_key("HF_TOKEN")
            )
            # Run the synchronous download_all in a thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, downloader.download_all)
            self._update_source_status("huggingface_datasets", "hf", "complete")
            return True
        except Exception as e:
            self._update_source_status("huggingface_datasets", "hf", "failed", error=str(e))
            logger.error(f"HF download failed: {e}")
            return False

    async def _run_arxiv_collect(self, force: bool = False) -> bool:
        """Run arXiv collector"""
        logger.info("Starting arXiv paper collection...")
        self._update_source_status("arxiv_papers", "arxiv", "downloading")

        try:
            from collect_everything import ArXivMassCollector
            collector = ArXivMassCollector(str(self.base_dir / "arxiv"))
            await collector.collect_all()
            self._update_source_status("arxiv_papers", "arxiv", "complete")
            return True
        except Exception as e:
            self._update_source_status("arxiv_papers", "arxiv", "failed", error=str(e))
            logger.error(f"arXiv collection failed: {e}")
            return False

    async def _run_openalex_collect(self, force: bool = False) -> bool:
        """Run OpenAlex collector"""
        logger.info("Starting OpenAlex collection...")
        self._update_source_status("openalex", "openalex", "downloading")
        try:
            from collect_everything import OpenAlexCollector
            collector = OpenAlexCollector(
                self._get_key("OPENALEX_EMAIL", "user@example.com"),
                str(self.base_dir / "openalex")
            )
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, collector.download_snapshot)
            self._update_source_status("openalex", "openalex", "complete")
            return True
        except Exception as e:
            self._update_source_status("openalex", "openalex", "failed", error=str(e))
            return False

    async def _run_image_collect(self, force: bool = False) -> bool:
        """Run OpenImages download"""
        logger.info("Starting image dataset collection...")
        self._update_source_status("openimages", "image", "downloading")
        try:
            from collect_everything import LAIONImageCollector
            collector = LAIONImageCollector()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: collector.download_openimages(str(self.base_dir / "images/openimages"))
            )
            self._update_source_status("openimages", "image", "complete")
            return True
        except Exception as e:
            self._update_source_status("openimages", "image", "failed", error=str(e))
            return False

    async def _run_audio_collect(self, force: bool = False) -> bool:
        """Run Common Voice and Indic audio collection"""
        logger.info("Starting audio dataset collection...")
        from collect_everything import AudioDataCollector

        loop = asyncio.get_event_loop()

        try:
            collector = AudioDataCollector()
            await loop.run_in_executor(
                None, lambda: collector.download_common_voice(
                    output_dir=str(self.base_dir / "audio/common_voice")
                )
            )
            self._update_source_status("common_voice", "audio", "complete")
        except Exception as e:
            self._update_source_status("common_voice", "audio", "failed", error=str(e))

        try:
            collector = AudioDataCollector()
            await loop.run_in_executor(
                None, lambda: collector.download_indic_speech(str(self.base_dir / "audio/indic"))
            )
            self._update_source_status("indic_speech", "audio", "complete")
        except Exception as e:
            self._update_source_status("indic_speech", "audio", "failed", error=str(e))

        return True

    async def _run_synthetic(self, force: bool = False) -> bool:
        """Run synthetic data generation"""
        logger.info("Starting synthetic data generation...")
        self._update_source_status("synthetic_data", "synthetic", "downloading")

        try:
            from collect_everything import MultiModelSyntheticFactory

            from src.data.apikeys import resolve_all

            factory = MultiModelSyntheticFactory(api_keys=resolve_all())
            await factory.run_full_synthetic_pipeline(
                str(self.base_dir / "synthetic"),
                total_per_task=self.config.get("synthetic_per_task", 1000)
            )
            self._update_source_status("synthetic_data", "synthetic", "complete")
            return True
        except Exception as e:
            self._update_source_status("synthetic_data", "synthetic", "failed", error=str(e))
            logger.error(f"Synthetic generation failed: {e}")
            return False

    # ── Reporting ─────────────────────────────────────────────

    def get_collection_summary(self) -> dict[str, Any]:
        """Get summary of all collected data"""
        summary = {
            "total_size_bytes": 0,
            "sources": {},
            "by_type": {},
            "phases_completed": len(self.phase_results),
        }
        for name, status in self.source_statuses.items():
            summary["sources"][name] = asdict(status)
            summary["total_size_bytes"] += status.size_bytes
            if status.source_type not in summary["by_type"]:
                summary["by_type"][status.source_type] = {"count": 0, "size_bytes": 0}
            summary["by_type"][status.source_type]["count"] += 1
            summary["by_type"][status.source_type]["size_bytes"] += status.size_bytes
        return summary

    def _print_phase_summary(self):
        """Print intermediate phase results"""
        table = Table(title="Phase Progress", title_style="bold cyan")
        table.add_column("Phase", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Duration", style="yellow")
        table.add_column("Error", style="red")

        for pr in self.phase_results:
            dur = f"{pr.duration_seconds:.1f}s" if pr.duration_seconds else "-"
            err = pr.error[:60] if pr.error else ""
            table.add_row(pr.name, pr.status, dur, err)

        console.print(table)

    def _print_final_report(self):
        """Print comprehensive final report"""
        summary = self.get_collection_summary()

        console.print(Panel.fit(
            f"[bold green]🏆 COLLECTION COMPLETE[/bold green]\n\n"
            f"Phases Completed: {summary['phases_completed']}\n"
            f"Sources Tracked: {len(summary['sources'])}\n"
            f"Total Size: {summary['total_size_bytes'] / 1e9:.2f} GB\n\n"
            f"[bold]By Type:[/bold]\n" +
            "\n".join(f"  {k}: {v['count']} sources, {v['size_bytes']/1e9:.2f} GB"
                     for k, v in summary['by_type'].items()),
            title="📊 Final Summary"
        ))

    def get_dashboard_data(self) -> dict:
        """Return data formatted for web dashboard"""
        summary = self.get_collection_summary()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_size_gb": round(summary["total_size_bytes"] / 1e9, 2),
            "sources_count": len(summary["sources"]),
            "phases_completed": summary["phases_completed"],
            "by_type": {k: {"count": v["count"], "size_gb": round(v["size_bytes"] / 1e9, 2)}
                       for k, v in summary["by_type"].items()},
            "sources": {k: asdict(v) for k, v in self.source_statuses.items()},
            "phase_results": [asdict(pr) for pr in self.phase_results],
        }
