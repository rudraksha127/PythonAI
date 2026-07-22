"use client";

import { useEffect, useState } from "react";
import { getSignalPatterns } from "@/lib/api";
import type { SignalPatternData } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  XCircle,
  CheckCircle2,
  Edit3,
  GitMerge,
  Users,
  Code2,
  AlertTriangle,
  Shield,
  UserCheck,
} from "lucide-react";

// ─── Color helpers ──────────────────────────────────────────────

function rateColor(rate: number): string {
  if (rate >= 70) return "text-success";
  if (rate >= 50) return "text-forge-primary";
  if (rate >= 30) return "text-warning";
  return "text-error";
}

function rateBg(rate: number): string {
  if (rate >= 70) return "bg-success/10";
  if (rate >= 50) return "bg-forge-primary/10";
  if (rate >= 30) return "bg-warning/10";
  return "bg-error/10";
}

// ─── Signal Type Icon ───────────────────────────────────────────

function SignalTypeIcon({ type, size = 14 }: { type: string; size?: number }) {
  const icons: Record<string, { icon: React.ElementType; color: string }> = {
    accept: { icon: CheckCircle2, color: "text-success" },
    reject: { icon: XCircle, color: "text-error" },
    edit: { icon: Edit3, color: "text-warning" },
    pr_merge: { icon: GitMerge, color: "text-cyan-400" },
    test_pass: { icon: Shield, color: "text-success" },
    test_fail: { icon: AlertTriangle, color: "text-error" },
  };
  const meta = icons[type] || { icon: Activity, color: "text-text-muted" };
  const Icon = meta.icon;
  return <Icon size={size} className={meta.color} />;
}

// ─── Signal Type Distribution ───────────────────────────────────

function SignalTypeDistribution({ types }: { types: SignalPatternData["signal_types"] }) {
  if (types.length === 0) return null;

  const total = types.reduce((a, b) => a + b.count, 0);
  const maxCount = Math.max(...types.map((t) => t.count), 1);

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <BarChart3 size={14} className="text-forge-primary" />
        Signal Type Distribution
      </h3>
      <div className="space-y-3">
        {types.map((t) => (
          <div key={t.key}>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <SignalTypeIcon type={t.key} />
                <span className="text-xs text-text-secondary">{t.label}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-text-primary">{formatNumber(t.count)}</span>
                <span className="text-[10px] font-mono text-text-muted w-10 text-right">
                  {t.percentage}%
                </span>
              </div>
            </div>
            <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(t.count / maxCount) * 100}%`,
                  backgroundColor:
                    t.key === "accept"
                      ? "rgba(34,197,94,0.6)"
                      : t.key === "reject"
                      ? "rgba(239,68,68,0.6)"
                      : t.key === "edit"
                      ? "rgba(245,158,11,0.6)"
                      : t.key === "pr_merge"
                      ? "rgba(6,182,212,0.6)"
                      : "rgba(91,91,255,0.6)",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Language Acceptance Rates ─────────────────────────────────

function LanguageAcceptanceRates({
  languages,
}: {
  languages: SignalPatternData["language_rates"];
}) {
  if (languages.length === 0) {
    return (
      <div className="card p-6 text-center">
        <Code2 size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted">No language data available yet</p>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Code2 size={14} className="text-forge-primary" />
          Language Acceptance Rates
        </h3>
        <span className="text-[10px] text-text-muted">
          Rate ÷ signals
        </span>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[1fr_60px_60px] gap-1 mb-2 text-[10px] text-text-muted uppercase tracking-wider font-medium">
        <div className="pl-1">Language</div>
        <div className="text-center">Rate</div>
        <div className="text-center">Signals</div>
      </div>

      <div className="space-y-1">
        {languages.map((lang) => (
          <div
            key={lang.language}
            className="grid grid-cols-[1fr_60px_60px] gap-1 items-center py-2 px-1 rounded-lg hover:bg-forge-elevated/50 transition-colors group"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-medium text-text-primary capitalize truncate">
                {lang.language}
              </span>
              {/* Mini rate bar */}
              <div className="hidden sm:block flex-1 h-1.5 bg-forge-elevated rounded-full overflow-hidden max-w-[80px]">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${lang.acceptance_rate}%`,
                    backgroundColor:
                      lang.acceptance_rate >= 70
                        ? "rgba(34,197,94,0.6)"
                        : lang.acceptance_rate >= 50
                        ? "rgba(91,91,255,0.6)"
                        : lang.acceptance_rate >= 30
                        ? "rgba(245,158,11,0.6)"
                        : "rgba(239,68,68,0.6)",
                  }}
                />
              </div>
            </div>

            {/* Rate */}
            <div className="text-center">
              <span className={cn("font-mono text-xs font-semibold", rateColor(lang.acceptance_rate))}>
                {lang.acceptance_rate}%
              </span>
            </div>

            {/* Signal count */}
            <div className="text-center">
              <span className="font-mono text-xs text-text-muted">
                {formatNumber(lang.signal_count)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Rejection Pattern Analysis ─────────────────────────────────

function RejectionPatterns({
  patterns,
}: {
  patterns: SignalPatternData["rejection_patterns"];
}) {
  if (patterns.length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <XCircle size={14} className="text-error" />
        Rejection Patterns
        <span className="text-[10px] font-normal text-text-muted ml-1">Highest rejection rate first</span>
      </h3>

      <div className="space-y-3">
        {patterns.slice(0, 8).map((p) => {
          const severityColors: Record<string, string> = {
            high: "bg-error/10 text-error border-error/20",
            medium: "bg-warning/10 text-warning border-warning/20",
            low: "bg-success/10 text-success border-success/20",
          };
          const severityDots: Record<string, string> = {
            high: "bg-error",
            medium: "bg-warning",
            low: "bg-success",
          };

          return (
            <div
              key={p.language}
              className="flex items-center gap-3 group hover:bg-forge-elevated/30 rounded-lg p-2 -mx-2 transition-colors"
            >
              {/* Language */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-text-primary capitalize truncate">
                    {p.language}
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                      severityColors[p.severity]
                    )}
                  >
                    <span className={`w-1 h-1 rounded-full ${severityDots[p.severity]}`} />
                    {p.severity}
                  </span>
                </div>

                {/* Dual progress bar: rejection rate (red) + acceptance rate (green) */}
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="flex-1 h-2 bg-forge-elevated rounded-full overflow-hidden flex">
                    {/* Rejection portion */}
                    <div
                      className="h-full bg-error/60 transition-all duration-500"
                      style={{ width: `${p.rejection_rate}%` }}
                    />
                    {/* Acceptance portion */}
                    <div
                      className="h-full bg-success/60 transition-all duration-500"
                      style={{ width: `${100 - p.rejection_rate}%` }}
                    />
                  </div>
                  <span className="text-[10px] font-mono text-text-muted w-8 text-right">
                    {formatNumber(p.signal_count)}
                  </span>
                </div>

                {/* Labels */}
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[9px] text-error">
                    Reject: {p.rejection_rate.toFixed(1)}%
                  </span>
                  <span className="text-[9px] text-success">
                    Accept: {p.acceptance_rate.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Weekly Signal Type Trend (Compact Inline Chart) ────────────

function WeeklyTrendChart({ data }: { data: SignalPatternData["weekly_trend"] }) {
  if (data.length === 0) return null;

  const maxTotal = Math.max(...data.map((d) => d.total), 1);
  const w = 300;
  const h = 64;

  // Accepts line
  const acceptPoints = data
    .map((d, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * w;
      const y = h - ((d.accepts / maxTotal) * (h - 10)) - 5;
      return `${x},${y}`;
    })
    .join(" ");

  // Rejects line
  const rejectPoints = data
    .map((d, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * w;
      const y = h - ((d.rejects / maxTotal) * (h - 10)) - 5;
      return `${x},${y}`;
    })
    .join(" ");

  // Edits line
  const editPoints = data
    .map((d, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * w;
      const y = h - ((d.edits / maxTotal) * (h - 10)) - 5;
      return `${x},${y}`;
    })
    .join(" ");

  const latest = data[data.length - 1];
  const earliest = data[0];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Activity size={14} className="text-forge-primary" />
          Weekly Signal Trend
        </h3>
        <div className="flex items-center gap-3 text-[9px] text-text-muted">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-success" />
            Accepts
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-error" />
            Rejects
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-warning" />
            Edits
          </span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-16 overflow-visible"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Accepts area fill */}
        <defs>
          <linearGradient id="acceptGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22C55E" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#22C55E" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="rejectGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#EF4444" stopOpacity={0.15} />
            <stop offset="100%" stopColor="#EF4444" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Accepts area */}
        <polyline points={`0,${h} ${acceptPoints} ${w},${h}`} fill="url(#acceptGrad)" />
        <polyline points={acceptPoints} fill="none" stroke="#22C55E" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />

        {/* Rejects area */}
        <polyline points={`0,${h} ${rejectPoints} ${w},${h}`} fill="url(#rejectGrad)" />
        <polyline points={rejectPoints} fill="none" stroke="#EF4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />

        {/* Edits line */}
        <polyline points={editPoints} fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3 2" />
      </svg>

      <div className="flex items-center justify-between text-[9px] text-text-muted mt-1">
        <span>
          {earliest ? `${earliest.period}: ${formatNumber(earliest.accepts)}A / ${formatNumber(earliest.rejects)}R` : ""}
        </span>
        <span>
          {latest ? `${latest.period}: ${formatNumber(latest.accepts)}A / ${formatNumber(latest.rejects)}R` : ""}
        </span>
      </div>
    </div>
  );
}

// ─── Developer Stats ────────────────────────────────────────────

function DeveloperStats({
  developers,
}: {
  developers: SignalPatternData["developer_stats"];
}) {
  if (developers.length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Users size={14} className="text-forge-primary" />
        Developer Acceptance Rates
        {developers.length > 0 && (
          <span className="text-[10px] font-normal text-text-muted ml-1">
            {developers.length} developer{developers.length !== 1 ? "s" : ""}
          </span>
        )}
      </h3>

      {/* Header row */}
      <div className="grid grid-cols-[1fr_48px_48px_48px] gap-1 mb-2 text-[10px] text-text-muted uppercase tracking-wider font-medium">
        <div className="pl-1">Developer</div>
        <div className="text-center">Rate</div>
        <div className="text-center">Sig</div>
        <div className="text-center">Role</div>
      </div>

      <div className="space-y-1">
        {developers.slice(0, 10).map((dev) => (
          <div
            key={dev.developer_id}
            className="grid grid-cols-[1fr_48px_48px_48px] gap-1 items-center py-2 px-1 rounded-lg hover:bg-forge-elevated/50 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <UserCheck size={12} className="text-text-muted shrink-0" />
              <span className="text-xs font-mono text-text-primary truncate">
                {dev.developer_id}
              </span>
              {dev.is_anonymous && (
                <span className="text-[8px] text-text-muted uppercase tracking-wider">anon</span>
              )}
            </div>

            {/* Rate */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-0.5">
                {dev.acceptance_rate >= 60 ? (
                  <TrendingUp size={10} className="text-success" />
                ) : dev.acceptance_rate < 40 ? (
                  <TrendingDown size={10} className="text-error" />
                ) : null}
                <span className={cn("font-mono text-xs font-semibold", rateColor(dev.acceptance_rate))}>
                  {dev.acceptance_rate}%
                </span>
              </div>
            </div>

            {/* Signal count */}
            <div className="text-center font-mono text-xs text-text-muted">
              {dev.total_signals}
            </div>

            {/* Role badge */}
            <div className="text-center">
              <span
                className={cn(
                  "inline-block px-1 py-0.5 rounded text-[8px] font-semibold uppercase tracking-wider",
                  dev.acceptance_rate >= 60
                    ? "bg-success/10 text-success"
                    : dev.acceptance_rate >= 40
                    ? "bg-forge-primary/10 text-forge-primary"
                    : "bg-error/10 text-error"
                )}
              >
                {dev.acceptance_rate >= 60 ? "Lead" : dev.acceptance_rate >= 40 ? "Dev" : "Learn"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Overall Metrics Bar ────────────────────────────────────────

function OverallMetricsBar({
  overall,
}: {
  overall: SignalPatternData["overall"];
}) {
  const items = [
    {
      label: "Acceptance Rate",
      value: `${overall.overall_acceptance_rate.toFixed(1)}%`,
      icon: TrendingUp,
      color: rateColor(overall.overall_acceptance_rate),
      subtext:
        overall.trend_direction === "up"
          ? `↑ ${overall.trend_value.toFixed(1)}pp`
          : overall.trend_direction === "down"
          ? `↓ ${Math.abs(overall.trend_value).toFixed(1)}pp`
          : "Stable",
    },
    {
      label: "Total Signals",
      value: formatNumber(overall.total_signals),
      icon: BarChart3,
      color: "text-forge-primary",
      subtext: `${formatNumber(overall.total_sessions)} sessions`,
    },
    {
      label: "Languages",
      value: formatNumber(overall.languages_count),
      icon: Code2,
      color: "text-cyan-400",
      subtext: "Active languages",
    },
    {
      label: "Developers",
      value: formatNumber(overall.developers_count),
      icon: Users,
      color: "text-warning",
      subtext: `Avg edit: ${overall.avg_edit_distance.toFixed(2)}`,
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
            <p className="text-[10px] text-text-muted mt-0.5">{item.subtext}</p>
          </div>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

export default function SignalPatternAnalysis() {
  const [data, setData] = useState<SignalPatternData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await getSignalPatterns();
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
          {error || "Signal pattern data not available"}
        </p>
        <button
          className="btn-ghost text-xs gap-1.5"
          onClick={() => {
            setLoading(true);
            setError(null);
            getSignalPatterns().then((result) => {
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

  const hasDevelopers = data.developer_stats.length > 0;
  const hasLanguages = data.language_rates.length > 0;
  const hasTrend = data.weekly_trend.length > 0;
  const hasPatterns = data.rejection_patterns.length > 0;

  return (
    <div className="space-y-4">
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between group"
      >
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Users size={16} className="text-forge-primary" />
          Signal Pattern Analysis
          <span className="text-[10px] font-normal text-text-muted ml-1">
            REQ-DASH-005
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {!expanded && data.overall && (
            <span
              className={cn(
                "text-xs font-mono font-semibold",
                rateColor(data.overall.overall_acceptance_rate)
              )}
            >
              {data.overall.overall_acceptance_rate.toFixed(1)}%
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
          {/* Overall metrics bar */}
          {data.overall && <OverallMetricsBar overall={data.overall} />}

          {/* Signal types + Weekly trend */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.signal_types.length > 0 && (
              <SignalTypeDistribution types={data.signal_types} />
            )}
            {hasTrend && <WeeklyTrendChart data={data.weekly_trend} />}
          </div>

          {/* Language rates + Rejection patterns */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {hasLanguages && <LanguageAcceptanceRates languages={data.language_rates} />}
            {hasPatterns && <RejectionPatterns patterns={data.rejection_patterns} />}
          </div>

          {/* Developer stats */}
          {hasDevelopers && <DeveloperStats developers={data.developer_stats} />}

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
