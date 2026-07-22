"""
ForgeAI Project Management API Routes
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.projects")
router = APIRouter(prefix="/api/projects", tags=["Projects"])

_PROJECTS_DB_PATH = Path.home() / ".forgeai" / "projects.db"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    repo_path: str = Field(..., min_length=1, max_length=1000)
    languages: list[str] = Field(default_factory=list)
    base_model: str = Field(default="Qwen/Qwen2.5-Coder-7B-Instruct")
    training_schedule: str = Field(default="0 2 * * 0")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    repo_path: str | None = Field(default=None, max_length=1000)
    languages: list[str] | None = None
    rag_indexed_at: float | None = None
    current_adapter_version: int | None = None
    training_phase: int | None = None
    base_model: str | None = None
    training_schedule: str | None = None


def _row_to_project(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "repo_path": row[2],
        "languages": json.loads(row[3]) if row[3] else [],
        "rag_indexed_at": row[4],
        "current_adapter_version": row[5],
        "training_phase": row[6],
        "base_model": row[7],
        "training_schedule": row[8],
    }


def _init_projects_db() -> None:
    _PROJECTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo_path TEXT NOT NULL,
            languages TEXT NOT NULL DEFAULT '[]',
            rag_indexed_at REAL,
            current_adapter_version INTEGER NOT NULL DEFAULT 1,
            training_phase INTEGER NOT NULL DEFAULT 1,
            base_model TEXT NOT NULL DEFAULT 'Qwen/Qwen2.5-Coder-7B-Instruct',
            training_schedule TEXT NOT NULL DEFAULT '0 2 * * 0',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


_init_projects_db()


@router.get("")
async def get_projects() -> list[dict[str, Any]]:
    """Return all tracked projects."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_project(r) for r in rows]
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail="Failed to list projects")


@router.post("", status_code=201)
async def create_project(body: ProjectCreate) -> dict[str, Any]:
    """Register a new project for monitoring and RAG indexing."""
    project_id = str(uuid.uuid4())
    now = time.time()
    languages = body.languages

    if not languages:
        try:
            repo = Path(body.repo_path)
            if repo.is_dir():
                detected: set[str] = set()
                file_count = 0
                for f in repo.rglob("*"):
                    file_count += 1
                    if file_count > 2000:
                        break
                    if f.is_file() and f.suffix:
                        ext_map = {
                            ".py": "python",
                            ".js": "javascript",
                            ".ts": "typescript",
                            ".jsx": "javascript",
                            ".tsx": "typescript",
                            ".go": "go",
                            ".rs": "rust",
                            ".java": "java",
                            ".cpp": "cpp",
                            ".c": "c",
                        }
                        lang = ext_map.get(f.suffix.lower())
                        if lang:
                            detected.add(lang)
                            if len(detected) >= 10:
                                break
                languages = sorted(detected)
        except Exception:
            pass

    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        conn.execute(
            """INSERT INTO projects
               (id, name, repo_path, languages, rag_indexed_at,
                current_adapter_version, training_phase, base_model,
                training_schedule, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                body.name,
                body.repo_path,
                json.dumps(languages),
                None,
                1,
                1,
                body.base_model,
                body.training_schedule,
                now,
                now,
            ),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            raise RuntimeError("Failed to read back created project")

        logger.info(f"Project created: {body.name} (id={project_id})")
        return _row_to_project(row)
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail="Failed to create project")


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    """Get a single project by ID."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _row_to_project(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate) -> dict[str, Any]:
    """Update an existing project. Only provided fields are changed."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))

        cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if cursor.fetchone() is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Project not found")

        updates: list[str] = []
        params: list[Any] = []

        field_map = {
            "name": "name",
            "repo_path": "repo_path",
            "rag_indexed_at": "rag_indexed_at",
            "current_adapter_version": "current_adapter_version",
            "training_phase": "training_phase",
            "base_model": "base_model",
            "training_schedule": "training_schedule",
        }

        if body.languages is not None:
            updates.append("languages = ?")
            params.append(json.dumps(body.languages))

        for attr, col in field_map.items():
            val = getattr(body, attr, None)
            if val is not None:
                updates.append(f"{col} = ?")
                params.append(val)

        if not updates:
            cursor = conn.execute(
                "SELECT id, name, repo_path, languages, rag_indexed_at, "
                "current_adapter_version, training_phase, base_model, training_schedule "
                "FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            conn.close()
            return _row_to_project(row)  # type: ignore[arg-type]

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(project_id)

        conn.execute(
            f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT id, name, repo_path, languages, rag_indexed_at, "
            "current_adapter_version, training_phase, base_model, training_schedule "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        conn.close()

        logger.info(f"Project updated: {project_id}")
        return _row_to_project(row)  # type: ignore[arg-type]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update project")


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    """Delete a project and its associated data."""
    try:
        conn = sqlite3.connect(str(_PROJECTS_DB_PATH))
        cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if cursor.fetchone() is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Project not found")

        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        conn.close()
        logger.info(f"Project deleted: {project_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete project")
