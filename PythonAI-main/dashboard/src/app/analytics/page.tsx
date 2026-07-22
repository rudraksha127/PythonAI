"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getSignalPatterns,
} from "@/lib/api";
import type { SignalPatternData, WeeklySignalTrendPoint } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
  XCircle,
  CheckCircle2,
  Edit3,
  GitMerge,
  Users,
  Code2,
  AlertTriangle,
  Shield,
  UserCheck,
  Brain,
  Zap,
  Layers,
  Clock,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  BarChart,
  Bar,
  Cell,
} from "recharts";

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

interface RejectionPattern {
  language: string;
  signal_count: number;
  rejection_rate: number;
  acceptance_rate: number;
  severity: "high" | "medium" | "low";
}

// ═══════════════════════════════════════════════════════════════════
// Color helpers
// ═══════════════════════════════════════════════════════════════════

function rateColor(rate: number): string {
  if (rate >= 70) return "text-success";
  if (rate >= 50) return "text-forge-primary";
  if (rate >= 30) return "text-warning";
  return "text-error";
}

// ═══════════════════════════════════════════════════════════════════
// Overall Metrics Bar
// ═══════════════════════════════════════════════════════════════════

function OverallMetricsBar({ overall }: { overall: SignalPatternData["overall"] }) {
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
          <div key={item.label} className="card-hover p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon size={14} className={item.color} />
              <span className="text-[10px] text-text-muted uppercase tracking-wider">{item.label}</span>
            </div>
            <div className={cn("text-lg font-bold font-mono", item.color)}>{item.value}</div>
            <p className="text-[10px] text-text-muted mt-0.5">{item.subtext}</p>
          </div>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Weekly Acceptance Rate Trend Chart (Full-width AreaChart)
// ═══════════════════════════════════════════════════════════════════

function WeeklyTrendChart({ data }: { data: WeeklySignalTrendPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="card p-6 flex items-center justify-center h-48">
        <p className="text-xs text-text-muted">No weekly trend data available</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Activity size={14} className="text-forge-primary" />
          Weekly Acceptance Rate Trend
        </h3>
        <div className="flex items-center gap-3 text-[10px] text-text-muted">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-forge-primary" /> Rate</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-success" /> Accepts</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-error" /> Rejects</span>
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="analyticsRateGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#5B5BFF" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#5B5BFF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272C" />
            <XAxis
              dataKey="period"
              tick={{ fill: "#71717A", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#27272C" }}
            />
            <YAxis
              tick={{ fill: "#71717A", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{ background: "#18181C", border: "1px solid #27272C", borderRadius: "8px", fontSize: 12 }}
              formatter={(value: number) => [`${value.toFixed(1)}%`]}
            />
            <Area
              type="monotone"
              dataKey="acceptance_rate"
              stroke="#5B5BFF"
              strokeWidth={2}
              fill="url(#analyticsRateGrad)"
              dot={false}
              activeDot={{ r: 4, fill: "#5B5BFF" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Signal Type Distribution Bar Chart
// ═══════════════════════════════════════════════════════════════════

function SignalTypeChart({ types }: { types: SignalPatternData["signal_types"] }) {
  if (types.length === 0) return null;

  const COLORS: Record<string, string> = {
    accept: "#22C55E",
    reject: "#EF4444",
    edit: "#F59E0B",
    pr_merge: "#06B6D4",
  };

  const chartData = types.map((t) => ({
    name: t.label,
    value: t.count,
    fill: COLORS[t.key] || "#5B5BFF",
  }));

  return (
    <div className="card p-6">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <BarChart3 size={14} className="text-forge-primary" />
        Signal Type Distribution
      </h3>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272C" />
            <XAxis dataKey="name" tick={{ fill: "#71717A", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#27272C" }} />
            <YAxis tick={{ fill: "#71717A", fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: "#18181C", border: "1px solid #27272C", borderRadius: "8px", fontSize: 12 }}
              formatter={(value: number) => [formatNumber(value), "Signals"]}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={48}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Language Acceptance Rates Table
// ═══════════════════════════════════════════════════════════════════

function LanguageRatesTable({ languages }: { languages: SignalPatternData["language_rates"] }) {
  if (languages.length === 0) {
    return (
      <div className="card p-6 text-center">
        <Code2 size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted">No language data available yet</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-forge-border">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Code2 size={14} className="text-forge-primary" />
          Per-Language Acceptance Rates
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border">
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Language</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Signals</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">% of Total</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Accepts</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Rejects</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Rate</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Trend</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-forge-border">
            {languages.map((lang) => (
              <tr key={lang.language} className="hover:bg-forge-elevated/30 transition-colors">
                <td className="px-6 py-3">
                  <span className="text-xs font-medium text-text-primary capitalize">{lang.language}</span>
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs text-text-primary">{formatNumber(lang.signal_count)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">{lang.signal_pct.toFixed(1)}%</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-success">{formatNumber(lang.accepts)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-error">{formatNumber(lang.rejects)}</td>
                <td className="px-4 py-3 text-right">
                  <span className={cn("font-mono text-xs font-semibold", rateColor(lang.acceptance_rate))}>
                    {lang.acceptance_rate}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="h-1.5 bg-forge-elevated rounded-full overflow-hidden w-16 ml-auto">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${lang.acceptance_rate}%`,
                        backgroundColor:
                          lang.acceptance_rate >= 70 ? "#22C55E" :
                          lang.acceptance_rate >= 50 ? "#5B5BFF" :
                          lang.acceptance_rate >= 30 ? "#F59E0B" : "#EF4444",
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Rejection Pattern Analysis
// ═══════════════════════════════════════════════════════════════════

function RejectionPatterns({ patterns }: { patterns: SignalPatternData["rejection_patterns"] }) {
  if (patterns.length === 0) return null;

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
    <div className="card p-6">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <XCircle size={14} className="text-error" />
        Rejection Pattern Analysis
        <span className="text-[10px] font-normal text-text-muted ml-1">Highest rejection rate first</span>
      </h3>

      <div className="space-y-4">
        {patterns.slice(0, 10).map((p) => (
          <div key={p.language}>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-primary capitalize">{p.language}</span>
                <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border", severityColors[p.severity])}>
                  <span className={`w-1 h-1 rounded-full ${severityDots[p.severity]}`} />
                  {p.severity}
                </span>
                <span className="text-[10px] font-mono text-text-muted">{formatNumber(p.signal_count)} signals</span>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-error">Rej: {p.rejection_rate.toFixed(1)}%</span>
                <span className="text-success">Acc: {p.acceptance_rate.toFixed(1)}%</span>
              </div>
            </div>
            <div className="h-2.5 bg-forge-elevated rounded-full overflow-hidden flex">
              <div
                className="h-full bg-error/60 transition-all duration-500 rounded-l-full"
                style={{ width: `${p.rejection_rate}%` }}
              />
              <div
                className="h-full bg-success/60 transition-all duration-500 rounded-r-full"
                style={{ width: `${100 - p.rejection_rate}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Developer Stats Table
// ═══════════════════════════════════════════════════════════════════

function DeveloperStatsTable({ developers }: { developers: SignalPatternData["developer_stats"] }) {
  if (developers.length === 0) {
    return (
      <div className="card p-6 text-center">
        <Users size={24} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted">No developer data available yet. Signals need a developer_id to appear here.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-forge-border">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Users size={14} className="text-forge-primary" />
          Per-Developer Metrics
          <span className="text-[10px] font-normal text-text-muted ml-1">{developers.length} developer{developers.length !== 1 ? "s" : ""}</span>
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border">
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Developer</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Signals</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Accepts</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Rejects</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Edits</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Rate</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Role</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-forge-border">
            {developers.slice(0, 20).map((dev) => (
              <tr key={dev.developer_id} className="hover:bg-forge-elevated/30 transition-colors">
                <td className="px-6 py-3">
                  <div className="flex items-center gap-2">
                    <UserCheck size={12} className="text-text-muted shrink-0" />
                    <span className="text-xs font-mono text-text-primary">{dev.developer_id}</span>
                    {dev.is_anonymous && <span className="text-[8px] text-text-muted uppercase tracking-wider bg-forge-elevated px-1 py-0.5 rounded">anon</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs text-text-primary">{formatNumber(dev.total_signals)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-success">{formatNumber(dev.accepts)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-error">{formatNumber(dev.rejects)}</td>
                <td className="px-4 py-3 text-right font-mono text-xs text-warning">{formatNumber(dev.edits)}</td>
                <td className="px-4 py-3 text-right">
                  <span className={cn("font-mono text-xs font-semibold", rateColor(dev.acceptance_rate))}>
                    {dev.acceptance_rate}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <span className={cn(
                    "inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider",
                    dev.acceptance_rate >= 60 ? "bg-success/10 text-success" :
                    dev.acceptance_rate >= 40 ? "bg-forge-primary/10 text-forge-primary" :
                    "bg-error/10 text-error"
                  )}>
                    {dev.acceptance_rate >= 60 ? "Lead" : dev.acceptance_rate >= 40 ? "Dev" : "Learn"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════════════

export default function AnalyticsPage() {
  const [data, setData] = useState<SignalPatternData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSignalPatterns();
      if (result.success && result.data) {
        setData(result.data);
        setError(null);
      } else {
        setData(null);
        setError(result.error || "No data available");
      }
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── Loading ──
  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-56 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-72 bg-forge-elevated rounded" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-4 space-y-3">
              <div className="h-4 w-20 bg-forge-elevated rounded" />
              <div className="h-8 w-16 bg-forge-elevated rounded" />
            </div>
          ))}
        </div>
        <div className="card p-6">
          <div className="h-64 bg-forge-elevated rounded-lg" />
        </div>
      </div>
    );
  }

  // ── Error ──
  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <BarChart3 size={48} className="text-text-muted/40 mb-4" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">Analytics Data Unavailable</h2>
        <p className="text-sm text-text-muted max-w-md mb-6">{error || "No signal pattern data available yet. Use the agent to collect signals first."}</p>
        <button onClick={load} className="btn-primary">
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  const hasWeeklyTrend = data.weekly_trend.length > 0;
  const hasLanguages = data.language_rates.length > 0;
  const hasPatterns = data.rejection_patterns.length > 0;
  const hasDevelopers = data.developer_stats.length > 0;
  const hasSignalTypes = data.signal_types.length > 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <BarChart3 size={22} className="text-forge-primary" />
            Team Analytics
          </h1>
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-forge-primary/10 text-forge-primary border border-forge-primary/20 uppercase tracking-wider">
            REQ-DASH-005
          </span>
        </div>
        <p className="text-sm text-text-muted">
          Per-developer acceptance rates, language breakdowns, and rejection pattern analysis
        </p>
      </div>

      {/* Overall metrics */}
      {data.overall && <OverallMetricsBar overall={data.overall} />}

      {/* Weekly trend chart */}
      {hasWeeklyTrend && <WeeklyTrendChart data={data.weekly_trend} />}

      {/* Signal types + Rejection patterns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {hasSignalTypes && <SignalTypeChart types={data.signal_types} />}
        {hasPatterns && <RejectionPatterns patterns={data.rejection_patterns} />}
      </div>

      {/* Language rates table */}
      {hasLanguages && <LanguageRatesTable languages={data.language_rates} />}

      {/* Developer stats table */}
      {hasDevelopers && <DeveloperStatsTable developers={data.developer_stats} />}

      {/* Summary insights */}
      {data.overall && (
        <div className="card p-4">
          <h3 className="text-xs font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Brain size={14} className="text-forge-primary" />
            Key Insights
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-[11px]">
            <div className="p-3 rounded-lg bg-forge-elevated">
              <span className="text-text-muted block mb-1">Best Language</span>
              <p className="font-semibold text-text-primary capitalize">
                {data.language_rates.length > 0
                  ? `${data.language_rates.sort((a, b) => b.acceptance_rate - a.acceptance_rate)[0]?.language || "—"} — ${data.language_rates.sort((a, b) => b.acceptance_rate - a.acceptance_rate)[0]?.acceptance_rate || 0}%`
                  : "—"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-forge-elevated">
              <span className="text-text-muted block mb-1">Top Contributor</span>
              <p className="font-semibold text-text-primary font-mono text-[10px]">
                {data.developer_stats.length > 0
                  ? data.developer_stats.sort((a, b) => b.total_signals - a.total_signals)[0]?.developer_id || "—"
                  : "—"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-forge-elevated">
              <span className="text-text-muted block mb-1">Trend Direction</span>
              <p className={cn("font-semibold capitalize",
                data.overall.trend_direction === "up" ? "text-success" :
                data.overall.trend_direction === "down" ? "text-error" : "text-text-muted"
              )}>
                {data.overall.trend_direction === "up" ? `↑ ${data.overall.trend_value.toFixed(1)}pp` :
                 data.overall.trend_direction === "down" ? `↓ ${Math.abs(data.overall.trend_value).toFixed(1)}pp` :
                 "Stable"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-forge-elevated">
              <span className="text-text-muted block mb-1">Avg Edit Distance</span>
              <p className="font-semibold text-text-primary">{data.overall.avg_edit_distance.toFixed(3)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Timestamp */}
      <p className="text-[10px] text-text-muted text-center">
        Last updated {new Date(data.timestamp * 1000).toLocaleTimeString()}
        {" · "}v{data.version}
      </p>
    </div>
  );
}
