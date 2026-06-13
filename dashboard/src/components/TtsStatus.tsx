"use client";

import { useEffect, useState } from "react";
import { getTtsStatus, updateTtsConfig, resetTtsStats } from "@/lib/api";
import type {
  TtsStatusResponse,
  TtsConfig,
  TtsStats,
} from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";

// ─── Color helpers ──────────────────────────────────────────

const BG_ICON_MAP: Record<string, string> = {
  "text-forge-primary": "bg-forge-primary/10",
  "text-success": "bg-success/10",
  "text-warning": "bg-warning/10",
  "text-error": "bg-error/10",
  "text-cyan-400": "bg-cyan-500/10",
  "text-text-muted": "bg-forge-elevated",
};

const BAR_BG_MAP: Record<string, string> = {
  "bg-success": "bg-success",
  "bg-warning": "bg-warning/80",
  "bg-forge-primary": "bg-forge-primary/80",
};
import {
  Cpu,
  Zap,
  Layers,
  Activity,
  RefreshCw,
  Gauge,
  TrendingUp,
  Bot,
  GitCompare,
  Workflow,
  Settings2,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  BarChart3,
  FlaskConical,
} from "lucide-react";

// ─── Color constants ──────────────────────────────────────────

const ROUTE_COLORS: Record<string, { text: string; bg: string; label: string }> = {
  fast: { text: "text-success", bg: "bg-success", label: "Fast" },
  medium: { text: "text-warning", bg: "bg-warning", label: "Balanced" },
  hard: { text: "text-forge-primary", bg: "bg-forge-primary", label: "Hard (PDR+RTV)" },
};

// ─── Donut Chart ─────────────────────────────────────────────

function RoutingDonut({ stats }: { stats: TtsStats }) {
  const total = stats.total_pipelines || 1;
  const fastPct = (stats.fast_tasks / total) * 100;
  const mediumPct = (stats.medium_tasks / total) * 100;
  const hardPct = (stats.hard_tasks / total) * 100;

  const segments = [
    { value: fastPct, color: "#22C55E", label: "Fast" },
    { value: mediumPct, color: "#F59E0B", label: "Balanced" },
    { value: hardPct, color: "#5B5BFF", label: "Hard" },
  ].filter((s) => s.value > 0);

  if (total <= 1) {
    return (
      <div className="flex items-center justify-center h-32 text-text-muted">
        <span className="text-xs">Insufficient data</span>
      </div>
    );
  }

  // SVG donut with stroke-dasharray
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="flex items-center gap-4">
      <svg width="100" height="100" viewBox="0 0 100 100" className="shrink-0">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#27272C" strokeWidth="16" />
        {segments.map((seg) => {
          const length = (seg.value / 100) * circumference;
          const dashOffset = -offset;
          offset += length;
          return (
            <circle
              key={seg.label}
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth="16"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={dashOffset}
              transform="rotate(-90 50 50)"
              strokeLinecap="round"
              className="transition-all duration-700"
            />
          );
        })}
      </svg>
      <div className="space-y-1.5">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full" style={{ background: seg.color }} />
            <span className="text-text-muted">{seg.label}</span>
            <span className="font-mono text-text-primary font-medium">
              {seg.value.toFixed(0)}%
            </span>
          </div>
        ))}
        <div className="pt-1 border-t border-forge-border mt-1">
          <div className="flex items-center justify-between text-[10px] text-text-muted">
            <span>Total</span>
            <span className="font-mono">{formatNumber(stats.total_pipelines)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Stat Pill ──────────────────────────────────────────────

function StatPill({
  label,
  value,
  icon: Icon,
  color = "text-text-primary",
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color?: string;
}) {
  return (
    <div className="bg-forge-elevated rounded-lg p-3 flex items-center gap-3">
      <div className={cn("p-1.5 rounded-md", BG_ICON_MAP[color] || "bg-forge-elevated")}>
        <Icon size={14} className={color} />
      </div>
      <div className="min-w-0">
        <div className={cn("text-sm font-bold font-mono truncate", color)}>{value}</div>
        <div className="text-[10px] text-text-muted">{label}</div>
      </div>
    </div>
  );
}

// ─── Config Editor ──────────────────────────────────────────

function ConfigEditor({
  config,
  onUpdate,
  saving,
}: {
  config: TtsConfig;
  onUpdate: (updates: Partial<TtsConfig>) => void;
  saving: boolean;
}) {
  const [local, setLocal] = useState({ ...config });

  useEffect(() => {
    setLocal({ ...config });
  }, [config]);

  const hasChanges =
    local.complexity_threshold !== config.complexity_threshold ||
    local.num_initial_rollouts !== config.num_initial_rollouts ||
    local.num_pdr_rollouts !== config.num_pdr_rollouts;

  return (
    <div className="space-y-3">
      {/* Complexity threshold slider */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] text-text-muted">Complexity Threshold</span>
          <span className="text-xs font-mono text-forge-primary font-medium">
            {local.complexity_threshold.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={local.complexity_threshold}
          onChange={(e) =>
            setLocal({ ...local, complexity_threshold: parseFloat(e.target.value) })
          }
          className="w-full h-1.5 bg-forge-elevated rounded-full appearance-none cursor-pointer accent-forge-primary"
        />
        <div className="flex justify-between text-[9px] text-text-muted mt-0.5">
          <span>Easy</span>
          <span>Hard</span>
        </div>
      </div>

      {/* Rollout counts */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[11px] text-text-muted block mb-1">
            Initial Rollouts
          </label>
          <div className="flex items-center gap-1">
            <button
              onClick={() =>
                setLocal({
                  ...local,
                  num_initial_rollouts: Math.max(1, local.num_initial_rollouts - 1),
                })
              }
              className="btn-ghost p-1 rounded text-text-muted hover:text-text-primary text-xs"
            >
              −
            </button>
            <span className="flex-1 text-center text-sm font-mono text-text-primary font-bold">
              {local.num_initial_rollouts}
            </span>
            <button
              onClick={() =>
                setLocal({
                  ...local,
                  num_initial_rollouts: Math.min(20, local.num_initial_rollouts + 1),
                })
              }
              className="btn-ghost p-1 rounded text-text-muted hover:text-text-primary text-xs"
            >
              +
            </button>
          </div>
        </div>
        <div>
          <label className="text-[11px] text-text-muted block mb-1">PDR Rollouts</label>
          <div className="flex items-center gap-1">
            <button
              onClick={() =>
                setLocal({
                  ...local,
                  num_pdr_rollouts: Math.max(1, local.num_pdr_rollouts - 1),
                })
              }
              className="btn-ghost p-1 rounded text-text-muted hover:text-text-primary text-xs"
            >
              −
            </button>
            <span className="flex-1 text-center text-sm font-mono text-text-primary font-bold">
              {local.num_pdr_rollouts}
            </span>
            <button
              onClick={() =>
                setLocal({
                  ...local,
                  num_pdr_rollouts: Math.min(10, local.num_pdr_rollouts + 1),
                })
              }
              className="btn-ghost p-1 rounded text-text-muted hover:text-text-primary text-xs"
            >
              +
            </button>
          </div>
        </div>
      </div>

      {/* Save button */}
      <button
        onClick={() => onUpdate(local)}
        disabled={!hasChanges || saving}
        className={cn(
          "w-full text-xs py-2 rounded-lg font-medium transition-all",
          hasChanges && !saving
            ? "btn-primary"
            : "bg-forge-elevated text-text-muted cursor-not-allowed"
        )}
      >
        {saving ? (
          <span className="flex items-center justify-center gap-1.5">
            <RefreshCw size={12} className="animate-spin" />
            Saving...
          </span>
        ) : hasChanges ? (
          "Apply Changes"
        ) : (
          "No changes"
        )}
      </button>
    </div>
  );
}

// ─── Sub-Statistics Panel ──────────────────────────────────

function SubStatsPanel({
  label,
  icon: Icon,
  color,
  stats,
}: {
  label: string;
  icon: React.ElementType;
  color: string;
  stats: Record<string, number>;
}) {
  const entries = Object.entries(stats).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return null;

  return (
    <div className="bg-forge-elevated/50 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2.5">
        <Icon size={13} className={color} />
        <span className="text-[11px] font-semibold text-text-primary uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className="space-y-1.5">
        {entries.map(([key, value]) => (
          <div
            key={key}
            className="flex items-center justify-between text-[11px]"
          >
            <span className="text-text-muted capitalize">
              {key.replace(/_/g, " ")}
            </span>
            <span className="font-mono text-text-primary font-medium">
              {typeof value === "number" && value > 100
                ? formatNumber(Math.round(value))
                : typeof value === "number"
                ? value.toFixed(1)
                : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

export default function TtsStatus() {
  const [status, setStatus] = useState<TtsStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [configExpanded, setConfigExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const result = await getTtsStatus();
      setStatus(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load TTS status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleConfigUpdate = async (updates: Partial<TtsConfig>) => {
    setSaving(true);
    try {
      const result = await updateTtsConfig(updates);
      // Refresh full status to get updated stats
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update config");
    } finally {
      setSaving(false);
    }
  };

  const handleResetStats = async () => {
    try {
      await resetTtsStats();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset stats");
    }
  };

  // ── Loading ─────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="card p-5 animate-pulse space-y-3">
        <div className="h-5 w-48 bg-forge-elevated rounded" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-14 bg-forge-elevated rounded-lg" />
          ))}
        </div>
        <div className="h-32 bg-forge-elevated rounded-lg" />
      </div>
    );
  }

  // ── Error / Unavailable ───────────────────────────────────
  if (error || !status) {
    return (
      <div className="card p-5 text-center">
        <FlaskConical size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted mb-3">
          {error || "Test-Time Scaling status not available"}
        </p>
        <button className="btn-ghost text-xs gap-1.5" onClick={load}>
          <RefreshCw size={12} />
          Retry
        </button>
      </div>
    );
  }

  const stats = status.stats as TtsStats | Record<string, never>;
  const hasStats = "total_pipelines" in stats && stats.total_pipelines > 0;
  const isActive = status.enabled && status.pipeline_initialized;

  // ── Render ─────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between group"
      >
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Cpu size={16} className="text-forge-primary" />
          Test-Time Scaling (PDR+RTV)
          <span className="text-[10px] font-normal text-text-muted ml-1">
            arXiv 2604.16529
          </span>
        </h2>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider",
              isActive
                ? "bg-success/10 text-success"
                : "bg-forge-elevated text-text-muted"
            )}
          >
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                isActive ? "bg-success animate-pulse" : "bg-text-muted"
              )}
            />
            {isActive ? "Active" : status.pipeline_initialized ? "Paused" : "Offline"}
          </span>
          {expanded ? (
            <ChevronUp size={16} className="text-text-muted" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <>
          {/* ═══ Status Badges ═══ */}
          <div className="flex items-center gap-3 text-[11px]">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full",
                status.pipeline_initialized
                  ? "bg-forge-primary/10 text-forge-primary"
                  : "bg-forge-elevated text-text-muted"
              )}
            >
              <Cpu size={11} />
              Pipeline {status.pipeline_initialized ? "Initialized" : "Not Initialized"}
            </span>
            {status.config && (
              <span className="text-text-muted font-mono">
                threshold={status.config.complexity_threshold}
              </span>
            )}
          </div>

          {/* ═══ Quick Stats Grid ═══ */}
          {hasStats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatPill
                label="Total Pipelines"
                value={formatNumber((stats as TtsStats).total_pipelines)}
                icon={Activity}
                color="text-forge-primary"
              />
              <StatPill
                label="Avg Complexity"
                value={(stats as TtsStats).avg_complexity_score.toFixed(3)}
                icon={Gauge}
                color="text-warning"
              />
              <StatPill
                label="Total Tokens"
                value={formatNumber(Math.round((stats as TtsStats).total_tokens_used))}
                icon={Zap}
                color="text-success"
              />
              <StatPill
                label="Avg Elapsed"
                value={
                  (stats as TtsStats).total_pipelines > 0
                    ? `${((stats as TtsStats).total_elapsed_ms / (stats as TtsStats).total_pipelines).toFixed(0)}ms`
                    : "—"
                }
                icon={TrendingUp}
                color="text-cyan-400"
              />
            </div>
          )}

          {/* ═══ Routing Distribution + Config ═══ */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Routing Donut */}
            <div className="card p-4">
              <h3 className="text-xs font-semibold text-text-primary mb-3 flex items-center gap-2">
                <BarChart3 size={13} className="text-forge-primary" />
                Routing Distribution
              </h3>
              {hasStats ? (
                <RoutingDonut stats={stats as TtsStats} />
              ) : (
                <p className="text-xs text-text-muted text-center py-6">
                  No pipeline data yet. Route a task through the agent chat to collect stats.
                </p>
              )}
            </div>

            {/* Config + Actions */}
            <div className="card p-4">
              <button
                onClick={() => setConfigExpanded(!configExpanded)}
                className="w-full flex items-center justify-between mb-2"
              >
                <h3 className="text-xs font-semibold text-text-primary flex items-center gap-2">
                  <Settings2 size={13} className="text-forge-primary" />
                  Configuration
                </h3>
                {configExpanded ? (
                  <ChevronUp size={14} className="text-text-muted" />
                ) : (
                  <ChevronDown size={14} className="text-text-muted" />
                )}
              </button>

              {configExpanded ? (
                <ConfigEditor
                  config={status.config}
                  onUpdate={handleConfigUpdate}
                  saving={saving}
                />
              ) : (
                <div className="space-y-1.5">
                  {[
                    { label: "Threshold", value: status.config.complexity_threshold.toFixed(2) },
                    { label: "Rollouts", value: `${status.config.num_initial_rollouts} init + ${status.config.num_pdr_rollouts} pdr` },
                  ].map(({ label, value }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-text-muted">{label}</span>
                      <span className="font-mono text-text-primary">{value}</span>
                    </div>
                  ))}

                  {/* Reset stats button */}
                  <div className="pt-2 border-t border-forge-border mt-2">
                    <button
                      onClick={handleResetStats}
                      className="w-full btn-ghost text-xs gap-1.5 py-1.5 text-text-muted hover:text-error"
                    >
                      <RotateCcw size={11} />
                      Reset Statistics
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ═══ Sub-component Stats ═══ */}
          {hasStats && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <SubStatsPanel
                label="Rollout Generator"
                icon={Bot}
                color="text-forge-primary"
                stats={(stats as TtsStats).generator as unknown as Record<string, number>}
              />
              <SubStatsPanel
                label="RTV Tournament"
                icon={GitCompare}
                color="text-success"
                stats={(stats as TtsStats).tournament as unknown as Record<string, number>}
              />
              <SubStatsPanel
                label="PDR Refinement"
                icon={Workflow}
                color="text-cyan-400"
                stats={(stats as TtsStats).pdr as unknown as Record<string, number>}
              />
            </div>
          )}

          {/* ═══ Route breakdown bar ═══ */}
          {hasStats && (
            <div className="card p-4">
              <h3 className="text-xs font-semibold text-text-primary mb-3 flex items-center gap-2">
                <Layers size={13} className="text-forge-primary" />
                Task Routing Breakdown
              </h3>
              {((stats as TtsStats).total_pipelines || 0) > 0 ? (
                <div className="space-y-3">
                  {(["fast", "medium", "hard"] as const).map((route) => {
                    const count = (stats as TtsStats)[`${route}_tasks` as keyof TtsStats] as number;
                    const pct =
                      (stats as TtsStats).total_pipelines > 0
                        ? (count / (stats as TtsStats).total_pipelines) * 100
                        : 0;
                    const colors = ROUTE_COLORS[route];
                    return (
                      <div key={route}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span className={cn("w-2 h-2 rounded-full", colors.bg)} />
                            <span className="text-xs text-text-secondary">
                              {colors.label}
                            </span>
                            <span className="text-[10px] font-mono text-text-muted">
                              {formatNumber(count)} tasks
                            </span>
                          </div>
                          <span className={cn("text-xs font-mono font-semibold", colors.text)}>
                            {pct.toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full transition-all duration-500", BAR_BG_MAP[colors.bg] || colors.bg)}
                            style={{ width: `${Math.max(1, pct)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-text-muted text-center py-2">
                  No tasks routed yet
                </p>
              )}
            </div>
          )}

          {/* ═══ Timestamp ═══ */}
          <p className="text-[10px] text-text-muted text-center">
            Live polling · Auto-refreshes every 30s
          </p>
        </>
      )}
    </div>
  );
}
