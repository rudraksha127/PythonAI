"use client";

import { useEffect, useState } from "react";
import { getImprovementHeatmap } from "@/lib/api";
import type {
  ImprovementHeatmapData,
  HeatmapLanguage,
  HeatmapPattern,
} from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Zap,
  Layers,
  Activity,
  RefreshCw,
  Flame,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

// ─── Color utilities ────────────────────────────────────────────

function textHeatColor(delta: number): string {
  if (delta > 10) return "text-success";
  if (delta > 5) return "text-forge-primary";
  if (delta > 0) return "text-text-secondary";
  if (delta < -5) return "text-error";
  if (delta < 0) return "text-warning";
  return "text-text-muted";
}

// ─── Heat Index Gauge ──────────────────────────────────────────

function HeatIndexGauge({ value }: { value: number }) {
  const clamped = Math.min(100, Math.max(0, value));
  const color =
    clamped > 70
      ? "bg-success"
      : clamped > 40
      ? "bg-forge-primary"
      : clamped > 20
      ? "bg-warning"
      : "bg-text-muted";

  return (
    <div className="card p-5 text-center">
      <div className="flex items-center justify-center gap-2 mb-3">
        <Flame size={18} className="text-forge-primary" />
        <span className="text-sm font-semibold text-text-primary">
          Improvement Heat Index
        </span>
      </div>
      <div className="relative inline-flex items-center justify-center">
        <svg width="120" height="120" viewBox="0 0 120 120">
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke="#27272C"
            strokeWidth="8"
          />
          <circle
            cx="60"
            cy="60"
            r="52"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${(clamped / 100) * 326.7} 326.7`}
            transform="rotate(-90 60 60)"
            className={color.replace("bg-", "text-")}
          />
        </svg>
        <span className="absolute text-2xl font-bold font-mono text-text-primary">
          {Math.round(clamped)}
        </span>
      </div>
      <p className="text-[10px] text-text-muted mt-2 uppercase tracking-wider">
        {clamped > 70
          ? "Strong Improvement"
          : clamped > 40
          ? "Moderate Improvement"
          : clamped > 20
          ? "Early Stage"
          : "Just Started"}
      </p>
    </div>
  );
}

// ─── Language Heatmap Grid ──────────────────────────────────────

function LanguageHeatmapGrid({
  languages,
}: {
  languages: HeatmapLanguage[];
}) {
  if (languages.length === 0) {
    return (
      <div className="card p-6 text-center">
        <BarChart3 size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted">
          No language data available yet
        </p>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <BarChart3 size={14} className="text-forge-primary" />
          Language Improvement Grid
        </h3>
        <span className="text-[10px] text-text-muted">
          Before → After (Delta)
        </span>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[1fr_repeat(3,64px)] gap-1 mb-2 text-[10px] text-text-muted uppercase tracking-wider font-medium">
        <div className="pl-1">Language</div>
        <div className="text-center">Before</div>
        <div className="text-center">After</div>
        <div className="text-center">Delta</div>
      </div>

      {/* Language rows */}
      <div className="space-y-1">
        {languages.map((lang) => {
          const delta = lang.delta;
          const maxDelta = Math.max(...languages.map((l) => l.delta), 1);
          const bgWidth = Math.max(4, (delta / maxDelta) * 100);

          return (
            <div
              key={lang.name}
              className="grid grid-cols-[1fr_repeat(3,64px)] gap-1 items-center py-2 px-1 rounded-lg hover:bg-forge-elevated/50 transition-colors group"
            >
              {/* Name + signal count */}
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-medium text-text-primary capitalize truncate">
                  {lang.name}
                </span>
                <span className="text-[10px] text-text-muted whitespace-nowrap">
                  ({lang.signal_count} sig)
                </span>
                {/* Mini heat bar */}
                <div className="hidden sm:block flex-1 h-1.5 bg-forge-elevated rounded-full overflow-hidden max-w-[80px]">
                  <div
                    className="h-full rounded-full bg-forge-primary/60 transition-all duration-500"
                    style={{ width: `${bgWidth}%` }}
                  />
                </div>
              </div>

              {/* Before rate */}
              <div className="text-center font-mono text-xs text-text-muted">
                {lang.rate_before.toFixed(1)}%
              </div>

              {/* After rate */}
              <div className="text-center">
                <div className="font-mono text-xs text-forge-primary font-medium">
                  {lang.rate_after.toFixed(1)}%
                </div>
                <span className="text-[8px] text-text-muted/60">est.</span>
              </div>

              {/* Delta */}
              <div className="flex items-center justify-center gap-0.5">
                {delta > 0 ? (
                  <TrendingUp size={10} className="text-success" />
                ) : delta < 0 ? (
                  <TrendingDown size={10} className="text-error" />
                ) : null}
                <span
                  className={cn(
                    "font-mono text-xs font-semibold",
                    textHeatColor(delta)
                  )}
                >
                  {delta >= 0 ? "+" : ""}
                  {delta.toFixed(1)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Pattern Improvement Cards ──────────────────────────────────

function PatternImprovement({
  patterns,
}: {
  patterns: HeatmapPattern[];
}) {
  if (patterns.length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Layers size={14} className="text-forge-primary" />
        Signal Pattern Trends
      </h3>
      <div className="space-y-4">
        {patterns.map((p) => {
          const delta = p.delta;
          return (
            <div key={p.key}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary">
                    {p.name}
                  </span>
                  <span className="text-[10px] font-mono text-text-muted">
                    {p.count}
                  </span>
                </div>
                <span
                  className={cn(
                    "text-xs font-mono font-semibold",
                    textHeatColor(delta)
                  )}
                >
                  {delta >= 0 ? "+" : ""}
                  {delta.toFixed(1)}pp
                </span>
              </div>

              {/* Before/after bar comparison */}
              <div className="flex items-center gap-2 h-5">
                <div className="flex-1 h-2 bg-forge-elevated rounded-full overflow-hidden relative">
                  {/* Before */}
                  <div
                    className="absolute inset-y-0 left-0 bg-text-muted/30 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, p.rate_before)}%` }}
                  />
                  {/* After */}
                  <div
                    className="absolute inset-y-0 left-0 bg-forge-primary/70 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, p.rate_after)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-text-muted w-8 text-right">
                  {p.percentage.toFixed(0)}%
                </span>
              </div>

              {/* Before → After labels */}
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-[9px] text-text-muted">
                  Before: {p.rate_before.toFixed(1)}%
                </span>
                <span className="text-[9px] text-forge-primary">
                  After: {p.rate_after.toFixed(1)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Training Run Timeline ──────────────────────────────────────

function TrainingRunTimeline({
  runs,
}: {
  runs: ImprovementHeatmapData["training_runs"];
}) {
  if (runs.length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Activity size={14} className="text-forge-primary" />
        Training Run Impact
      </h3>
      <div className="space-y-3">
        {[...runs].reverse().map((run, idx) => (
          <div
            key={run.run_id}
            className="flex items-start gap-3 group hover:bg-forge-elevated/30 rounded-lg p-2 -mx-2 transition-colors"
          >
            {/* Timeline dot */}
            <div className="relative flex flex-col items-center">
              <div
                className={cn(
                  "w-2.5 h-2.5 rounded-full ring-2 ring-forge-elevated",
                  run.delta >= 0 ? "bg-success" : "bg-error"
                )}
              />
              {idx < runs.length - 1 && (
                <div className="w-px flex-1 bg-forge-border mt-1" />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-primary">
                  Run #{runs.length - idx}
                </span>
                <span
                  className={cn(
                    "text-xs font-mono font-semibold",
                    run.delta >= 0 ? "text-success" : "text-error"
                  )}
                >
                  {run.delta >= 0 ? "+" : ""}
                  {run.delta.toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-text-muted mt-0.5">
                <span>{run.model || "—"}</span>
                <span>·</span>
                <span>{formatNumber(run.signals_used)} signals</span>
                <span>·</span>
                <span>
                  {new Date(run.timestamp * 1000).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Slots Overview ─────────────────────────────────────────────

function SlotsOverview({
  slots,
}: {
  slots: ImprovementHeatmapData["slots"];
}) {
  const items = [
    {
      label: "Overall Delta",
      value: `${slots.overall_delta >= 0 ? "+" : ""}${slots.overall_delta.toFixed(1)}%`,
      icon: TrendingUp,
      color: textHeatColor(slots.overall_delta),
      subtext: "From first to latest",
    },
    {
      label: "Current Rate",
      value: `${slots.current_rate.toFixed(1)}%`,
      icon: Zap,
      color: "text-forge-primary",
      subtext: "Current acceptance rate",
    },
    {
      label: "Target Rate",
      value: `${slots.target_rate.toFixed(1)}%`,
      icon: TrendingUp,
      color: "text-success",
      subtext: "Projected after next training",
    },
    {
      label: "Training Runs",
      value: formatNumber(slots.training_run_count),
      icon: Activity,
      color: "text-warning",
      subtext: `${formatNumber(slots.total_signals_used)} total signals`,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div
            key={item.label}
            className="card p-4 hover:bg-forge-elevated/50 transition-colors"
          >
            <div className="flex items-center gap-2 mb-2">
              <Icon size={14} className={item.color} />
              <span className="text-[10px] text-text-muted uppercase tracking-wider">
                {item.label}
              </span>
            </div>
            <div className={cn("text-lg font-bold font-mono", item.color)}>
              {item.value}
            </div>
            <p className="text-[10px] text-text-muted mt-0.5">
              {item.subtext}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// ─── Weekly Rate Trend (Compact Line Chart) ─────────────────────

function WeeklyTrendChart({
  data,
}: {
  data: ImprovementHeatmapData["weekly_data"];
}) {
  if (data.length === 0) return null;

  // Inline SVG chart — no recharts dependency needed here
  const maxRate = Math.max(...data.map((d) => d.acceptance_rate), 1);
  const minRate = Math.min(...data.map((d) => d.acceptance_rate), 0);
  const range = maxRate - minRate || 1;
  const w = 280;
  const h = 60;
  const points = data
    .map((d, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * w;
      const y = h - ((d.acceptance_rate - minRate) / range) * (h - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Activity size={14} className="text-forge-primary" />
          Weekly Rate Trajectory
        </h3>
        <span className="text-[10px] text-text-muted">
          {data.length} weeks
        </span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-16 overflow-visible"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Gradient fill area */}
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5B5BFF" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#5B5BFF" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        {/* Area fill */}
        <polyline
          points={`0,${h} ${points} ${w},${h}`}
          fill="url(#trendGrad)"
        />
        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="#5B5BFF"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Points */}
        {data.map((d, i) => {
          const x = (i / Math.max(data.length - 1, 1)) * w;
          const y = h - ((d.acceptance_rate - minRate) / range) * (h - 8) - 4;
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="2.5"
              fill="#5B5BFF"
              className="hover:r-4 transition-all"
            >
              <title>{`${d.period}: ${d.acceptance_rate.toFixed(1)}%`}</title>
            </circle>
          );
        })}
      </svg>
      <div className="flex items-center justify-between text-[9px] text-text-muted mt-1">
        <span>Baseline: {data[0]?.acceptance_rate.toFixed(1) ?? "—"}%</span>
        <span>Current: {data[data.length - 1]?.acceptance_rate.toFixed(1) ?? "—"}%</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════

export default function ImprovementHeatmap() {
  const [data, setData] = useState<ImprovementHeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await getImprovementHeatmap();
        if (result.success && result.data) {
          setData(result.data);
        } else {
          setError(result.error || "No data");
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="card p-5 animate-pulse space-y-3">
        <div className="h-5 w-48 bg-forge-elevated rounded" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-forge-elevated rounded-lg" />
          ))}
        </div>
        <div className="h-48 bg-forge-elevated rounded-lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card p-5 text-center">
        <BarChart3 size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted mb-3">
          {error || "Improvement heatmap data not available"}
        </p>
        <button
          className="btn-ghost text-xs gap-1.5"
          onClick={() => {
            setLoading(true);
            setError(null);
            getImprovementHeatmap().then((result) => {
              if (result.success && result.data) {
                setData(result.data);
              } else {
                setError(result.error || "No data");
              }
              setLoading(false);
            });
          }}
        >
          <RefreshCw size={12} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between group"
      >
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Layers size={16} className="text-forge-primary" />
          Model Improvement Heatmap
          <span className="text-[10px] font-normal text-text-muted ml-1">
            REQ-DASH-003
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {!expanded && data.slots && (
            <span
              className={cn(
                "text-xs font-mono font-semibold",
                textHeatColor(data.slots.overall_delta)
              )}
            >
              Δ {data.slots.overall_delta >= 0 ? "+" : ""}
              {data.slots.overall_delta.toFixed(1)}%
            </span>
          )}
          {expanded ? (
            <ChevronUp size={16} className="text-text-muted" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <>
          {/* Slots overview */}
          {data.slots && <SlotsOverview slots={data.slots} />}

          {/* Heat index + Weekly trend + Language grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <HeatIndexGauge value={data.slots?.heat_index ?? 0} />
            {data.weekly_data.length > 0 && (
              <div className="sm:col-span-2">
                <WeeklyTrendChart data={data.weekly_data} />
              </div>
            )}
          </div>

          {/* Language heatmap grid */}
          {data.languages.length > 0 && (
            <LanguageHeatmapGrid languages={data.languages} />
          )}

          {/* Patterns + Training timeline */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.patterns.length > 0 && (
              <PatternImprovement patterns={data.patterns} />
            )}
            {data.training_runs.length > 0 && (
              <TrainingRunTimeline runs={data.training_runs} />
            )}
          </div>

          {/* Language weekly trend grid */}
          {data.language_weekly_trend.length > 0 && (
            <div className="card p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
                <Activity size={14} className="text-forge-primary" />
                Per-Language Weekly Trend
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.language_weekly_trend.map((lt) => (
                  <div
                    key={lt.language}
                    className="bg-forge-elevated rounded-lg p-3"
                  >
                    <span className="text-xs font-medium text-text-primary capitalize block mb-2">
                      {lt.language}
                    </span>
                    <div className="flex items-end gap-1 h-12">
                      {lt.trend.map((t, i) => {
                        const rates = lt.trend.map((x) => x.rate);
                        const maxR = Math.max(...rates, 1);
                        const barH = (t.rate / maxR) * 40;
                        return (
                          <div
                            key={i}
                            className="flex-1 bg-forge-primary/50 rounded-t transition-all duration-300 hover:bg-forge-primary/80"
                            style={{ height: `${Math.max(4, barH)}px` }}
                            title={`Week ${t.week}: ${t.rate.toFixed(1)}%`}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timestamp */}
          <p className="text-[10px] text-text-muted text-center">
            Last updated{" "}
            {new Date(data.timestamp * 1000).toLocaleTimeString()}
            {" · "}v{data.version}
          </p>
        </>
      )}
    </div>
  );
}
