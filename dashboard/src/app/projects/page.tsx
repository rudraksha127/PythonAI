"use client";

import { useEffect, useState, useCallback } from "react";
import { getProjects, indexProject, searchRag } from "@/lib/api";
import type { Project } from "@/lib/types";
import { formatDate, truncate } from "@/lib/utils";
import {
  GitBranch,
  Plus,
  RefreshCw,
  Database,
  BookOpen,
  Code,
  Search,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Layers,
  Clock,
  ExternalLink,
  ChevronRight,
} from "lucide-react";

// ─── Project Card ───────────────────────────────────────────────

function ProjectCard({
  project,
  onReindex,
  onSearch,
  reindexing,
}: {
  project: Project;
  onReindex: (id: string) => void;
  onSearch: (id: string) => void;
  reindexing: boolean;
}) {
  const phaseLabels: Record<number, { label: string; color: string }> = {
    0: { label: "RAG Only", color: "bg-zinc-700 text-text-secondary" },
    1: { label: "QLoRA", color: "bg-forge-primary/20 text-forge-primary" },
    2: { label: "GRPO", color: "bg-purple-500/20 text-purple-400" },
    3: { label: "SEAL", color: "bg-cyan-500/20 text-cyan-400" },
  };

  const phaseInfo = phaseLabels[project.training_phase] ?? phaseLabels[0];

  return (
    <div className="card-hover p-5 group">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-forge-primary/10 flex items-center justify-center shrink-0">
            <FileCode size={18} className="text-forge-primary" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {project.name}
            </h3>
            <p className="text-xs text-text-muted truncate mt-0.5 font-mono">
              {truncate(project.repo_path, 50)}
            </p>
          </div>
        </div>
        <span
          className={`badge text-[10px] ${phaseInfo.color}`}
        >
          {phaseInfo.label}
        </span>
      </div>

      {/* Languages */}
      {project.languages.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {project.languages.map((lang) => (
            <span
              key={lang}
              className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-forge-elevated text-text-muted"
            >
              {lang}
            </span>
          ))}
        </div>
      )}

      {/* Metadata */}
      <div className="space-y-1.5 mb-4">
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-muted">Adapter</span>
          <span className="font-mono text-text-primary">
            v{project.current_adapter_version}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-muted">Base Model</span>
          <span className="font-mono text-text-secondary truncate ml-2 max-w-[180px]">
            {project.base_model || "Default"}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-muted">Schedule</span>
          <span className="font-mono text-text-primary capitalize">
            {project.training_schedule}
          </span>
        </div>
        {project.rag_indexed_at && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-muted">RAG Indexed</span>
            <span className="font-mono text-text-secondary">
              {formatDate(project.rag_indexed_at)}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-3 border-t border-forge-border">
        <button
          onClick={() => onReindex(project.id)}
          disabled={reindexing}
          className="btn-ghost text-xs gap-1.5 flex-1"
        >
          <RefreshCw
            size={12}
            className={reindexing ? "animate-spin" : ""}
          />
          Reindex
        </button>
        <button
          onClick={() => onSearch(project.id)}
          className="btn-ghost text-xs gap-1.5 flex-1"
        >
          <Search size={12} />
          Search
        </button>
      </div>
    </div>
  );
}

// ─── Add Project Modal ──────────────────────────────────────────

function AddProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const { createProject } = await import("@/lib/api");
      await createProject(name.trim(), repoPath.trim());
      setName("");
      setRepoPath("");
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="fixed inset-0 bg-black/60"
        onClick={onClose}
      />
      <div className="relative bg-forge-surface border border-forge-border rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h2 className="text-lg font-semibold text-text-primary mb-1">
          Add Project
        </h2>
        <p className="text-sm text-text-muted mb-5">
          Connect a local project to ForgeAI for signal capture and training.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Project Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., my-web-app"
              className="input"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Repository Path
            </label>
            <input
              type="text"
              value={repoPath}
              onChange={(e) => setRepoPath(e.target.value)}
              placeholder="e.g., /home/user/projects/my-app"
              className="input"
            />
          </div>

          {error && (
            <p className="text-xs text-error flex items-center gap-1">
              <AlertCircle size={12} />
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!name.trim() || submitting}
              className="btn-primary"
            >
              {submitting ? (
                <>
                  <RefreshCw size={14} className="animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Plus size={14} />
                  Add Project
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Search Panel ───────────────────────────────────────────────

function SearchPanel({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{
    answer: string;
    chunks: unknown[];
  } | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const result = await searchRag(query.trim(), projectId);
      setResults(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Search failed"
      );
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-forge-surface border border-forge-border rounded-xl p-6 w-full max-w-2xl mx-4 shadow-2xl max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary">
            Code Search
          </h2>
          <button onClick={onClose} className="btn-ghost p-1">
            <AlertCircle size={16} className="rotate-45" />
          </button>
        </div>

        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search your codebase..."
            className="input flex-1"
            autoFocus
          />
          <button
            onClick={handleSearch}
            disabled={!query.trim() || searching}
            className="btn-primary"
          >
            {searching ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : (
              <Search size={14} />
            )}
            Search
          </button>
        </div>

        {error && (
          <p className="text-xs text-error flex items-center gap-1 mb-3">
            <AlertCircle size={12} />
            {error}
          </p>
        )}

        {results && (
          <div className="space-y-4">
            <div className="card p-4">
              <span className="metric-label text-[10px] mb-2 block">
                Answer
              </span>
              <p className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
                {results.answer}
              </p>
            </div>
            {results.chunks.length > 0 && (
              <div>
                <span className="metric-label text-[10px] mb-2 block">
                  Retrieved Chunks ({results.chunks.length})
                </span>
                <div className="space-y-2">
                  {results.chunks.map((chunk: any, i: number) => (
                    <div
                      key={i}
                      className="card p-3 text-xs text-text-secondary font-mono"
                    >
                      {chunk.content?.slice(0, 300)}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Empty State ────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="card p-12 text-center">
      <GitBranch size={40} className="mx-auto mb-4 text-text-muted" />
      <h3 className="text-base font-semibold text-text-primary mb-2">
        No Projects Yet
      </h3>
      <p className="text-sm text-text-muted max-w-md mx-auto mb-6">
        Add your first project to start capturing developer signals and
        tracking acceptance rate improvements through training.
      </p>
      <button onClick={onAdd} className="btn-primary">
        <Plus size={16} />
        Add Project
      </button>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [reindexingProject, setReindexingProject] = useState<string | null>(
    null
  );
  const [searchProjectId, setSearchProjectId] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const data = await getProjects();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load projects"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleReindex = async (projectId: string) => {
    setReindexingProject(projectId);
    try {
      const project = projects.find((p) => p.id === projectId);
      if (project) {
        await indexProject(projectId, project.repo_path, true);
        // Brief delay then reload
        setTimeout(() => {
          setReindexingProject(null);
          loadProjects();
        }, 2000);
      }
    } catch {
      setReindexingProject(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-72 bg-forge-elevated rounded" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-5 space-y-4">
              <div className="flex gap-3">
                <div className="w-9 h-9 rounded-lg bg-forge-elevated" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-32 bg-forge-elevated rounded" />
                  <div className="h-3 w-48 bg-forge-elevated rounded" />
                </div>
              </div>
              <div className="h-8 bg-forge-elevated rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error && projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <AlertCircle size={48} className="text-error/40 mb-4" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Cannot load projects
        </h2>
        <p className="text-sm text-text-muted max-w-md mb-6">{error}</p>
        <button onClick={loadProjects} className="btn-primary">
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Projects</h1>
          <p className="text-sm text-text-muted mt-1">
            Manage your code projects, RAG indices, and trained adapters.
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary"
        >
          <Plus size={16} />
          Add Project
        </button>
      </div>

      {/* Summary stats */}
      {projects.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="card p-4">
            <span className="metric-label">Total</span>
            <div className="metric-value text-xl font-bold mt-1">
              {projects.length}
            </div>
          </div>
          <div className="card p-4">
            <span className="metric-label">Phase 3 (SEAL)</span>
            <div className="metric-value text-xl font-bold mt-1 text-cyan-400">
              {projects.filter((p) => p.training_phase >= 3).length}
            </div>
          </div>
          <div className="card p-4">
            <span className="metric-label">RAG Indexed</span>
            <div className="metric-value text-xl font-bold mt-1 text-success">
              {projects.filter((p) => p.rag_indexed_at).length}
            </div>
          </div>
          <div className="card p-4">
            <span className="metric-label">Latest Adapter</span>
            <div className="metric-value text-xl font-bold mt-1 text-forge-primary">
              v
              {Math.max(
                ...projects.map((p) => p.current_adapter_version),
                0
              )}
            </div>
          </div>
        </div>
      )}

      {/* Project grid or empty state */}
      {projects.length === 0 ? (
        <EmptyState onAdd={() => setShowAddModal(true)} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onReindex={handleReindex}
              onSearch={(id) => setSearchProjectId(id)}
              reindexing={reindexingProject === project.id}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      <AddProjectModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCreated={loadProjects}
      />
      {searchProjectId && (
        <SearchPanel
          projectId={searchProjectId}
          onClose={() => setSearchProjectId(null)}
        />
      )}
    </div>
  );
}
