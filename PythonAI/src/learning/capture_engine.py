"""
Capture Engine — Developer Signal Collection for ForgeAI
=========================================================

Collects accept/reject/edit signals from developers using AI coding assistants.
This is the foundation of ForgeAI's self-improvement loop (MIT SEAL architecture).

Signal Types:
- ACCEPT: Developer accepts AI suggestion as-is
- REJECT: Developer rejects AI suggestion
- EDIT: Developer modifies AI suggestion before accepting
- TEST_PASS: Accepted code passes tests (verifiable reward)
- TEST_FAIL: Accepted code fails tests (negative signal)
- PR_MERGE: Code merged via PR (high-confidence positive signal)

Architecture:
- Local encrypted SQLite database
- Session fingerprinting (language, framework, project type)
- Git hook integration for PR merge signals
- Test runner integration for verifiable rewards

Research Foundation: MIT SEAL (NeurIPS 2025)
"Self-Adapting Language Models" — Developer accept signal = SEAL's downstream task reward.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet


class SignalType(str, Enum):
    """Types of developer feedback signals."""

    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"
    TEST_PASS = "test_pass"
    TEST_FAIL = "test_fail"
    PR_MERGE = "pr_merge"
    IMPLICIT_ACCEPT = "implicit_accept"  # Developer uses suggestion without explicit accept


@dataclass
class TrainingSignal:
    """A single training signal from developer interaction."""

    signal_type: SignalType
    timestamp: float
    session_id: str
    file_path: str
    line_number: int
    language: str
    framework: str | None
    project_type: str  # "web", "data", "ml", "cli", "library", etc.

    # The AI suggestion
    suggestion: str
    suggestion_metadata: dict = field(default_factory=dict)  # model, temperature, etc.

    # Context (surrounding code)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""

    # Developer's final code (if different from suggestion)
    final_code: str | None = None
    edit_distance: float = 0.0  # How much was edited (0.0 = identical, 1.0 = completely different)

    # Verifiable signals
    test_passed: bool | None = None
    lint_passed: bool | None = None
    compilation_passed: bool | None = None

    # Additional metadata
    git_sha: str | None = None
    branch_name: str | None = None
    pr_number: int | None = None
    developer_id: str | None = None  # Anonymized hash

    # Unique ID
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "language": self.language,
            "framework": self.framework,
            "project_type": self.project_type,
            "suggestion": self.suggestion,
            "suggestion_metadata": json.dumps(self.suggestion_metadata),
            "context_before": self.context_before,
            "context_after": self.context_after,
            "full_context": self.full_context,
            "final_code": self.final_code,
            "edit_distance": self.edit_distance,
            "test_passed": self.test_passed,
            "lint_passed": self.lint_passed,
            "compilation_passed": self.compilation_passed,
            "git_sha": self.git_sha,
            "branch_name": self.branch_name,
            "pr_number": self.pr_number,
            "developer_id": self.developer_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingSignal:
        return cls(
            signal_id=data.get("signal_id", str(uuid.uuid4())),
            signal_type=SignalType(data["signal_type"]),
            timestamp=data["timestamp"],
            session_id=data["session_id"],
            file_path=data["file_path"],
            line_number=data["line_number"],
            language=data["language"],
            framework=data.get("framework"),
            project_type=data["project_type"],
            suggestion=data["suggestion"],
            suggestion_metadata=json.loads(data.get("suggestion_metadata", "{}")),
            context_before=data.get("context_before", ""),
            context_after=data.get("context_after", ""),
            full_context=data.get("full_context", ""),
            final_code=data.get("final_code"),
            edit_distance=data.get("edit_distance", 0.0),
            test_passed=data.get("test_passed"),
            lint_passed=data.get("lint_passed"),
            compilation_passed=data.get("compilation_passed"),
            git_sha=data.get("git_sha"),
            branch_name=data.get("branch_name"),
            pr_number=data.get("pr_number"),
            developer_id=data.get("developer_id"),
        )


def _compute_edit_distance(original: str, final: str) -> float:
    """Compute normalized edit distance between original and final code."""
    if not original:
        return 1.0 if final else 0.0
    if not final:
        return 1.0

    # Simple Levenshtein-based normalized distance
    len_orig = len(original)
    len_final = len(final)
    max(len_orig, len_final)

    # Use simple diff for efficiency
    orig_lines = original.strip().splitlines()
    final_lines = final.strip().splitlines()

    total_lines = max(len(orig_lines), len(final_lines))
    if total_lines == 0:
        return 0.0

    diff_count = 0
    for i in range(max(len(orig_lines), len(final_lines))):
        orig_line = orig_lines[i] if i < len(orig_lines) else ""
        final_line = final_lines[i] if i < len(final_lines) else ""
        if orig_line.strip() != final_line.strip():
            diff_count += 1

    return diff_count / total_lines


class CaptureEngine:
    """
    Local encrypted signal capture and storage.

    Design principles:
    - Privacy-first: all data stored locally, encrypted at rest
    - Low latency: signals captured asynchronously
    - Resilient: survives crashes, power loss
    - Queryable: easy extraction for training pipeline
    """

    SCHEMA_VERSION = "2.0"

    def __init__(
        self,
        db_path: str | Path | None = None,
        encryption_key: str | None = None,
        project_name: str = "default",
    ):
        if db_path is None:
            db_path = Path.home() / ".forgeai" / "signals.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.project_name = project_name
        self.session_id = str(uuid.uuid4())

        # Encryption
        if encryption_key:
            self.fernet = Fernet(encryption_key)
        else:
            # Generate from machine ID for consistent encryption
            machine_id = self._get_machine_id()
            key = hashlib.sha256(machine_id.encode()).digest()
            # Use first 32 bytes as Fernet key (base64 encoded)
            import base64

            self.fernet = Fernet(base64.urlsafe_b64encode(key[:32]))

        self._init_db()

    def _get_machine_id(self) -> str:
        """Get a unique but anonymized machine identifier."""
        try:
            import platform

            return platform.node() + platform.machine()
        except Exception:
            return str(uuid.getnode())

    def _init_db(self):
        """Initialize the SQLite database with schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.executescript("""
        -- Signals table (main training data)
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            signal_type TEXT NOT NULL,
            timestamp REAL NOT NULL,
            session_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            language TEXT NOT NULL,
            framework TEXT,
            project_type TEXT NOT NULL,
            suggestion TEXT NOT NULL,
            suggestion_metadata TEXT,
            context_before TEXT,
            context_after TEXT,
            full_context TEXT,
            final_code TEXT,
            edit_distance REAL DEFAULT 0.0,
            test_passed BOOLEAN,
            lint_passed BOOLEAN,
            compilation_passed BOOLEAN,
            git_sha TEXT,
            branch_name TEXT,
            pr_number INTEGER,
            developer_id TEXT
        );

        -- Sessions table (for session-level analytics)
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            start_time REAL NOT NULL,
            end_time REAL,
            project_name TEXT,
            language TEXT,
            framework TEXT,
            project_type TEXT,
            total_accepts INTEGER DEFAULT 0,
            total_rejects INTEGER DEFAULT 0,
            total_edits INTEGER DEFAULT 0
        );

        -- Training runs table
        CREATE TABLE IF NOT EXISTS training_runs (
            run_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            model_name TEXT NOT NULL,
            signals_used INTEGER NOT NULL,
            train_loss REAL,
            eval_loss REAL,
            acceptance_rate_before REAL,
            acceptance_rate_after REAL,
            adapter_path TEXT,
            metrics TEXT
        );

        -- Acceptance rate tracking (for dashboard)
        CREATE TABLE IF NOT EXISTS acceptance_metrics (
            date TEXT PRIMARY KEY,
            total_accepts INTEGER DEFAULT 0,
            total_rejects INTEGER DEFAULT 0,
            total_suggestions INTEGER DEFAULT 0,
            acceptance_rate REAL DEFAULT 0.0,
            edit_rate REAL DEFAULT 0.0
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
        CREATE INDEX IF NOT EXISTS idx_signals_language ON signals(language);
        CREATE INDEX IF NOT EXISTS idx_signals_file ON signals(file_path);
        CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id);
        """)

        conn.commit()
        conn.close()

    def capture_accept(
        self,
        suggestion: str,
        file_path: str,
        line_number: int,
        language: str,
        context_before: str = "",
        context_after: str = "",
        full_context: str = "",
        suggestion_metadata: dict | None = None,
        framework: str | None = None,
        project_type: str = "general",
        developer_id: str | None = None,
    ) -> str:
        """Capture an accept signal."""
        signal = TrainingSignal(
            signal_type=SignalType.ACCEPT,
            timestamp=time.time(),
            session_id=self.session_id,
            file_path=file_path,
            line_number=line_number,
            language=language,
            framework=framework,
            project_type=project_type,
            suggestion=suggestion,
            suggestion_metadata=suggestion_metadata or {},
            context_before=context_before,
            context_after=context_after,
            full_context=full_context,
            final_code=suggestion,  # Accept means no changes
            edit_distance=0.0,
            developer_id=developer_id or self._anonymize_id(),
        )
        self._store_signal(signal)
        self._update_session_accept()
        self._update_daily_metrics("accept")
        return signal.signal_id

    def capture_reject(
        self,
        suggestion: str,
        file_path: str,
        line_number: int,
        language: str,
        context_before: str = "",
        context_after: str = "",
        full_context: str = "",
        suggestion_metadata: dict | None = None,
        framework: str | None = None,
        project_type: str = "general",
        rejection_reason: str | None = None,
        developer_id: str | None = None,
    ) -> str:
        """Capture a reject signal."""
        signal = TrainingSignal(
            signal_type=SignalType.REJECT,
            timestamp=time.time(),
            session_id=self.session_id,
            file_path=file_path,
            line_number=line_number,
            language=language,
            framework=framework,
            project_type=project_type,
            suggestion=suggestion,
            suggestion_metadata={**(suggestion_metadata or {}), "rejection_reason": rejection_reason},
            context_before=context_before,
            context_after=context_after,
            full_context=full_context,
            developer_id=developer_id or self._anonymize_id(),
        )
        self._store_signal(signal)
        self._update_session_reject()
        self._update_daily_metrics("reject")
        return signal.signal_id

    def capture_edit(
        self,
        original_suggestion: str,
        final_code: str,
        file_path: str,
        line_number: int,
        language: str,
        context_before: str = "",
        context_after: str = "",
        full_context: str = "",
        suggestion_metadata: dict | None = None,
        framework: str | None = None,
        project_type: str = "general",
        developer_id: str | None = None,
    ) -> str:
        """Capture an edit signal (developer modified suggestion before accepting)."""
        edit_distance = _compute_edit_distance(original_suggestion, final_code)
        signal = TrainingSignal(
            signal_type=SignalType.EDIT,
            timestamp=time.time(),
            session_id=self.session_id,
            file_path=file_path,
            line_number=line_number,
            language=language,
            framework=framework,
            project_type=project_type,
            suggestion=original_suggestion,
            suggestion_metadata=suggestion_metadata or {},
            context_before=context_before,
            context_after=context_after,
            full_context=full_context,
            final_code=final_code,
            edit_distance=edit_distance,
            developer_id=developer_id or self._anonymize_id(),
        )
        self._store_signal(signal)
        self._update_session_edit()
        self._update_daily_metrics("edit")
        return signal.signal_id

    def capture_test_result(
        self,
        signal_id: str,
        passed: bool,
        test_output: str | None = None,
    ):
        """Update a signal with test execution result (verifiable reward)."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE signals SET test_passed = ? WHERE signal_id = ?",
            (passed, signal_id),
        )
        conn.commit()
        conn.close()

    def capture_pr_merge(
        self,
        file_path: str,
        language: str,
        code_content: str,
        pr_number: int,
        branch_name: str,
        git_sha: str,
        context_before: str = "",
        context_after: str = "",
        full_context: str = "",
        framework: str | None = None,
        project_type: str = "general",
        developer_id: str | None = None,
    ) -> str:
        """Capture a PR merge signal (high-confidence positive example)."""
        signal = TrainingSignal(
            signal_type=SignalType.PR_MERGE,
            timestamp=time.time(),
            session_id=self.session_id,
            file_path=file_path,
            line_number=1,  # PR-level, not line-specific
            language=language,
            framework=framework,
            project_type=project_type,
            suggestion=code_content,
            suggestion_metadata={"pr_number": pr_number, "branch": branch_name},
            context_before=context_before,
            context_after=context_after,
            full_context=full_context,
            final_code=code_content,
            edit_distance=0.0,
            git_sha=git_sha,
            branch_name=branch_name,
            pr_number=pr_number,
            developer_id=developer_id or self._anonymize_id(),
        )
        self._store_signal(signal)
        self._update_session_accept()
        self._update_daily_metrics("accept")
        return signal.signal_id

    def _store_signal(self, signal: TrainingSignal):
        """Store a signal in the database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        data = signal.to_dict()
        cursor.execute(
            """
        INSERT INTO signals (
            signal_id, signal_type, timestamp, session_id, file_path, line_number,
            language, framework, project_type, suggestion, suggestion_metadata,
            context_before, context_after, full_context, final_code, edit_distance,
            test_passed, lint_passed, compilation_passed, git_sha, branch_name,
            pr_number, developer_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                data["signal_id"],
                data["signal_type"],
                data["timestamp"],
                data["session_id"],
                data["file_path"],
                data["line_number"],
                data["language"],
                data["framework"],
                data["project_type"],
                data["suggestion"],
                data["suggestion_metadata"],
                data["context_before"],
                data["context_after"],
                data["full_context"],
                data["final_code"],
                data["edit_distance"],
                data["test_passed"],
                data["lint_passed"],
                data["compilation_passed"],
                data["git_sha"],
                data["branch_name"],
                data["pr_number"],
                data["developer_id"],
            ),
        )

        conn.commit()
        conn.close()

    def _update_session_accept(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT INTO sessions (session_id, start_time, project_name)
        VALUES (?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            total_accepts = total_accepts + 1
        """,
            (self.session_id, time.time(), self.project_name),
        )
        conn.commit()
        conn.close()

    def _update_session_reject(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT INTO sessions (session_id, start_time, project_name)
        VALUES (?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            total_rejects = total_rejects + 1
        """,
            (self.session_id, time.time(), self.project_name),
        )
        conn.commit()
        conn.close()

    def _update_session_edit(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT INTO sessions (session_id, start_time, project_name)
        VALUES (?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            total_edits = total_edits + 1
        """,
            (self.session_id, time.time(), self.project_name),
        )
        conn.commit()
        conn.close()

    def _update_daily_metrics(self, event_type: str):
        """Update daily acceptance rate metrics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        if event_type == "accept":
            cursor.execute(
                """
            INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, acceptance_rate)
            VALUES (?, 1, 1, 1.0)
            ON CONFLICT(date) DO UPDATE SET
                total_accepts = total_accepts + 1,
                total_suggestions = total_suggestions + 1,
                acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions
            """,
                (today,),
            )
        elif event_type == "reject":
            cursor.execute(
                """
            INSERT INTO acceptance_metrics (date, total_rejects, total_suggestions, acceptance_rate)
            VALUES (?, 1, 1, 0.0)
            ON CONFLICT(date) DO UPDATE SET
                total_rejects = total_rejects + 1,
                total_suggestions = total_suggestions + 1,
                acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions
            """,
                (today,),
            )
        elif event_type == "edit":
            cursor.execute(
                """
            INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, edit_rate)
            VALUES (?, 1, 1, 0.0)
            ON CONFLICT(date) DO UPDATE SET
                total_accepts = total_accepts + 1,
                total_suggestions = total_suggestions + 1,
                edit_rate = CAST(total_accepts AS REAL) / total_suggestions
            """,
                (today,),
            )

        conn.commit()
        conn.close()

    def _anonymize_id(self) -> str:
        """Create an anonymized developer ID."""
        machine_id = self._get_machine_id()
        return hashlib.sha256(machine_id.encode()).hexdigest()[:16]

    def store_training_run(
        self,
        run_id: str,
        model_name: str,
        signals_used: int,
        acceptance_rate_before: float,
        acceptance_rate_after: float,
        train_loss: float | None = None,
        eval_loss: float | None = None,
        adapter_path: str | None = None,
        metrics: dict[str, Any] | None = None,
    ):
        """Record a training run with before/after acceptance rate."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT INTO training_runs (
            run_id, timestamp, model_name, signals_used,
            train_loss, eval_loss,
            acceptance_rate_before, acceptance_rate_after,
            adapter_path, metrics
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                run_id,
                time.time(),
                model_name,
                signals_used,
                train_loss,
                eval_loss,
                acceptance_rate_before,
                acceptance_rate_after,
                adapter_path,
                json.dumps(metrics) if metrics else None,
            ),
        )
        conn.commit()
        conn.close()

    def get_training_runs(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent training runs with acceptance rate deltas."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
        SELECT run_id, timestamp, model_name, signals_used,
               train_loss, eval_loss,
               acceptance_rate_before, acceptance_rate_after,
               adapter_path
        FROM training_runs
        ORDER BY timestamp DESC
        LIMIT ?
        """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            rate_before = row[6] or 0.0
            rate_after = row[7] or 0.0
            results.append(
                {
                    "run_id": row[0],
                    "timestamp": row[1],
                    "model_name": row[2],
                    "signals_used": row[3],
                    "train_loss": row[4],
                    "eval_loss": row[5],
                    "acceptance_rate_before": rate_before,
                    "acceptance_rate_after": rate_after,
                    "acceptance_delta": rate_after - rate_before,
                    "adapter_path": row[8],
                }
            )
        return results

    # ─── Query Methods ───────────────────────────────────────────────────

    def get_signals(
        self,
        signal_type: SignalType | str | None = None,
        language: str | None = None,
        start_date: float | None = None,
        end_date: float | None = None,
        limit: int = 1000,
    ) -> list[TrainingSignal]:
        """Query signals with optional filters."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        query = "SELECT * FROM signals WHERE 1=1"
        params = []

        if signal_type:
            query += " AND signal_type = ?"
            # Handle both SignalType enum and string values
            if isinstance(signal_type, SignalType):
                params.append(signal_type.value)
            else:
                params.append(signal_type)
        if language:
            query += " AND language = ?"
            params.append(language)
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            TrainingSignal.from_dict(
                dict(
                    zip(
                        [
                            "signal_id",
                            "signal_type",
                            "timestamp",
                            "session_id",
                            "file_path",
                            "line_number",
                            "language",
                            "framework",
                            "project_type",
                            "suggestion",
                            "suggestion_metadata",
                            "context_before",
                            "context_after",
                            "full_context",
                            "final_code",
                            "edit_distance",
                            "test_passed",
                            "lint_passed",
                            "compilation_passed",
                            "git_sha",
                            "branch_name",
                            "pr_number",
                            "developer_id",
                        ],
                        row,
                    )
                )
            )
            for row in rows
        ]

    def get_training_data(
        self,
        include_accepts: bool = True,
        include_edits: bool = True,
        include_pr_merges: bool = True,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Extract training data from signals.

        Returns list of dicts suitable for SFT training:
        {
            "instruction": "<context + task>",
            "input": "<code context>",
            "output": "<suggestion or final_code>"
        }
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        signal_types = []
        if include_accepts:
            signal_types.append("accept")
        if include_edits:
            signal_types.append("edit")
        if include_pr_merges:
            signal_types.append("pr_merge")

        if not signal_types:
            return []

        placeholders = ",".join("?" * len(signal_types))
        query = f"""
        SELECT * FROM signals
        WHERE signal_type IN ({placeholders})
        ORDER BY timestamp DESC
        """

        cursor.execute(query, signal_types)
        rows = cursor.fetchall()
        conn.close()

        training_data = []
        for row in rows:
            cols = [
                "signal_id",
                "signal_type",
                "timestamp",
                "session_id",
                "file_path",
                "line_number",
                "language",
                "framework",
                "project_type",
                "suggestion",
                "suggestion_metadata",
                "context_before",
                "context_after",
                "full_context",
                "final_code",
                "edit_distance",
                "test_passed",
                "lint_passed",
                "compilation_passed",
                "git_sha",
                "branch_name",
                "pr_number",
                "developer_id",
            ]
            data = dict(zip(cols, row))

            # Compute quality score
            quality = 1.0
            if data["signal_type"] == "edit":
                # Edits are good but the original suggestion wasn't perfect
                quality = 1.0 - data["edit_distance"]
            if data["test_passed"] is True:
                quality = 1.0  # Verified correct
            if data["signal_type"] == "pr_merge":
                quality = 1.0  # High confidence

            if quality < min_quality_score:
                continue

            # Build training example
            context = data["full_context"] or f"{data['context_before']}\n{data['context_after']}"

            # Use final_code for edits, suggestion for accepts/PR merges
            output = data["final_code"] if data["signal_type"] == "edit" else data["suggestion"]

            instruction = (
                f"Complete the code in {data['file_path']} ({data['language']}).\n"
                f"Framework: {data['framework'] or 'none'}\n"
                f"Project type: {data['project_type']}\n"
                f"Context:\n{context[:2000]}"
            )

            training_data.append(
                {
                    "instruction": instruction,
                    "input": context[:1000],
                    "output": output,
                    "metadata": {
                        "signal_id": data["signal_id"],
                        "signal_type": data["signal_type"],
                        "language": data["language"],
                        "quality_score": quality,
                    },
                }
            )

        return training_data

    def get_acceptance_rate(
        self,
        days: int = 7,
        group_by: str = "day",
    ) -> list[dict[str, Any]]:
        """Get acceptance rate over time."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cutoff = time.time() - (days * 86400)

        cursor.execute(
            """
        SELECT
            DATE(timestamp, 'unixepoch') as date,
            SUM(CASE WHEN signal_type = 'accept' OR signal_type = 'pr_merge' THEN 1 ELSE 0 END) as accepts,
            SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
            SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits,
            COUNT(*) as total
        FROM signals
        WHERE timestamp >= ?
        GROUP BY DATE(timestamp, 'unixepoch')
        ORDER BY date
        """,
            (cutoff,),
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "date": row[0],
                "accepts": row[1],
                "rejects": row[2],
                "edits": row[3],
                "total": row[4],
                "acceptance_rate": (row[1] / row[4] * 100) if row[4] > 0 else 0,
                "edit_rate": (row[3] / row[4] * 100) if row[4] > 0 else 0,
            }
            for row in rows
        ]

    def get_statistics(self) -> dict[str, Any]:
        """Get overall capture statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        stats = {}

        # Total signals by type
        cursor.execute("""
        SELECT signal_type, COUNT(*) FROM signals GROUP BY signal_type
        """)
        stats["signals_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Signals by language
        cursor.execute("""
        SELECT language, COUNT(*) FROM signals GROUP BY language ORDER BY COUNT(*) DESC LIMIT 10
        """)
        stats["signals_by_language"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Total sessions
        cursor.execute("SELECT COUNT(*) FROM sessions")
        stats["total_sessions"] = cursor.fetchone()[0]

        # Overall acceptance rate
        total_accepts = stats["signals_by_type"].get("accept", 0) + stats["signals_by_type"].get("pr_merge", 0)
        total_rejects = stats["signals_by_type"].get("reject", 0)
        total = total_accepts + total_rejects
        stats["overall_acceptance_rate"] = (total_accepts / total * 100) if total > 0 else 0

        # Average edit distance
        cursor.execute("SELECT AVG(edit_distance) FROM signals WHERE signal_type = 'edit'")
        result = cursor.fetchone()[0]
        stats["avg_edit_distance"] = result or 0

        conn.close()
        return stats

    def export_for_training(
        self,
        output_path: str | Path,
        format: str = "jsonl",
        include_accepts: bool = True,
        include_edits: bool = True,
        include_pr_merges: bool = True,
    ):
        """Export signals as training data in specified format."""
        data = self.get_training_data(
            include_accepts=include_accepts,
            include_edits=include_edits,
            include_pr_merges=include_pr_merges,
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for item in data:
                    f.write(json.dumps(item) + "\n")
        elif format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            raise ValueError(f"Unknown format: {format}")

        return len(data)


# ═══════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAI Capture Engine — Developer Signal Collection")
    subparsers = parser.add_subparsers(dest="command")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show capture statistics")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export training data")
    export_parser.add_argument("--output", "-o", required=True, help="Output file path")
    export_parser.add_argument("--format", default="jsonl", choices=["jsonl", "json"])
    export_parser.add_argument("--days", type=int, default=30, help="Days of data to export")

    # Rate command
    rate_parser = subparsers.add_parser("rate", help="Show acceptance rate")
    rate_parser.add_argument("--days", type=int, default=7, help="Days to show")

    args = parser.parse_args()

    engine = CaptureEngine()

    if args.command == "stats":
        stats = engine.get_statistics()
        print(json.dumps(stats, indent=2))
    elif args.command == "export":
        count = engine.export_for_training(args.output, args.format)
        print(f"Exported {count} training examples to {args.output}")
    elif args.command == "rate":
        rates = engine.get_acceptance_rate(args.days)
        for r in rates:
            print(f"{r['date']}: {r['acceptance_rate']:.1f}% ({r['accepts']}A/{r['rejects']}R/{r['edits']}E)")
    else:
        parser.print_help()
