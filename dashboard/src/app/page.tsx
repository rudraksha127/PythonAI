"use client";

import { useEffect, useState } from "react";
import {
  getHealth,
  getAcceptanceRate,
  getTrainingStatus,
  getCaptureStats,
  getRagStats,
  getSealStats,
  triggerSealCycle,
} from "@/lib/api";
import type {
  HealthCheck,
  AcceptanceRatePoint,
  TrainingRun,
  CaptureStats,
  RagStats,
  SealStats,
} from "@/lib/types";
import { formatNumber, formatTimeAgo } from "@/lib/utils";
import {
  TrendingUp,
  Brain,
  Zap,
  BarChart3,
  CheckCircle2,
  XCircle,
  Edit3,
  GitMerge,
  Database,
  Search,
  Network,
  RefreshCw,
  Target,
  Layers,
  Activity,
  Play,
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
} from "recharts";
import Link from "next/link";

// ─── Stats Card ─────────────────────────────────────────────────

function StatsCard({
  title,
  value,
  icon: Icon,
  subtext,
  trend,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
  subtext?: string;
  trend?: { direction: "up" | "down"; value: string };
}) {
  return (
    <div className="card-hover p-5 group">
      <div className="flex items-start justify-between mb-3">
        <span className="metric-label">{title}</span>
        <div className="p-2 rounded-lg bg-forge-primary/10 group-hover:bg-forge-primary/20 transition-colors">
          <Icon size={16} className="text-forge-primary" />
        </div>
      </div>
      <div className="metric-value text-2xl font-bold">{value}</div>
      <div className="flex items-center gap-2 mt-1">
        {trend && (
          <span
            className={`text-xs font-medium ${
              trend.direction === "up" ? "text-success" : "text-error"
            }`}
          >
            {trend.direction === "up" ? "↑" : "↓"} {trend.value}
          </span>
        )}
        {subtext && <span className="text-xs text-text-muted">{subtext}</span>}
      </div>
    </div>
  );
}

// ─── Acceptance Rate Chart ──────────────────────────────────────

function AcceptanceRateChart({ data }: { data: AcceptanceRatePoint[] }) {
  if (data.length === 0) {
    return (
      <div className="card p-6 flex items-center justify-center h-64">
        <p className="text-text-muted text-sm">
          No acceptance rate data yet. Start using ForgeAI to collect signals.
        </p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">
          Acceptance Rate Over Time
        </h3>
        <div className="flex items-center gap-4 text-xs text-text-muted">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-forge-primary" />
            Rate
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-success" />
            Accepts
          </span>
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="rateGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#5B5BFF" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#5B5BFF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272C" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#71717A", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "#27272C" }}
            />
            <YAxis
              tick={{ fill: "#71717A", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{
                background: "#18181C",
                border: "1px solid #27272C",
                borderRadius: "8px",
                fontSize: 12,
              }}
              labelStyle={{ color: "#FAFAFA" }}
              formatter={(value: number) => [`${value.toFixed(1)}%`]}
            />
            <Area
              type="monotone"
              dataKey="acceptance_rate"
              stroke="#5B5BFF"
              strokeWidth={2}
              fill="url(#rateGrad)"
              dot={false}
              activeDot={{ r: 4, fill: "#5B5BFF" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Training History Table ─────────────────────────────────────

function TrainingHistory({ runs }: { runs: TrainingRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="card p-6 text-center">
        <Brain size={32} className="mx-auto mb-3 text-text-muted" />
        <p className="text-text-muted text-sm">
          No training runs yet. Collect enough signals and trigger your first
          training run.
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-forge-border">
        <h3 className="text-sm font-semibold text-text-primary">
          Recent Training Runs
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border">
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                Date
              </th>
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                Model
              </th>
              <th className="text-right px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                Signals
              </th>
              <th className="text-right px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                Before
              </th>
              <th className="text-right px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                After
              </th>
              <th className="text-right px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">
                Delta
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-forge-border">
            {runs.map((run) => (
              <tr
                key={run.run_id}
                className="hover:bg-forge-elevated transition-colors"
              >
                <td className="px-6 py-3 text-text-primary font-mono text-xs">
                  {formatTimeAgo(run.timestamp)}
                </td>
                <td className="px-6 py-3 text-text-secondary font-mono text-xs">
                  {run.model_name.split("/").pop()}
                </td>
                <td className="px-6 py-3 font-mono text-xs text-right text-text-primary">
                  {formatNumber(run.signals_used)}
                </td>
                <td className="px-6 py-3 font-mono text-xs text-right text-text-secondary">
                  {(run.acceptance_rate_before * 100).toFixed(1)}%
                </td>
                <td className="px-6 py-3 font-mono text-xs text-right text-success">
                  {(run.acceptance_rate_after * 100).toFixed(1)}%
                </td>
                <td className="px-6 py-3 font-mono text-xs text-right">
                  <span
                    className={
                      run.acceptance_delta >= 0 ? "text-success" : "text-error"
                    }
                  >
                    {run.acceptance_delta >= 0 ? "+" : ""}
                    {(run.acceptance_delta * 100).toFixed(1)}%
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

// ─── Signal Distribution ────────────────────────────────────────

function SignalDistribution({ stats }: { stats: CaptureStats | null }) {
  if (!stats) return null;

  const signals = stats.signals_by_type;
  const total = Object.values(signals).reduce((a, b) => a + b, 0);

  if (total === 0) return null;

  const items = [
    {
      label: "Accepts",
      value: signals.accept || 0,
      icon: CheckCircle2,
      color: "text-success",
      bg: "bg-success/10",
    },
    {
      label: "Rejects",
      value: signals.reject || 0,
      icon: XCircle,
      color: "text-error",
      bg: "bg-error/10",
    },
    {
      label: "Edits",
      value: signals.edit || 0,
      icon: Edit3,
      color: "text-warning",
      bg: "bg-warning/10",
    },
    {
      label: "PR Merges",
      value: signals.pr_merge || 0,
      icon: GitMerge,
      color: "text-forge-accent",
      bg: "bg-cyan-500/10",
    },
  ];

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4">
        Signal Distribution
      </h3>
      <div className="space-y-3">
        {items.map((item) => {
          const pct = total > 0 ? (item.value / total) * 100 : 0;
          const Icon = item.icon;
          return (
            <div key={item.label}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <Icon size={14} className={item.color} />
                  <span className="text-xs text-text-secondary">
                    {item.label}
                  </span>
                </div>
                <span className="text-xs font-mono text-text-primary">
                  {formatNumber(item.value)} ({pct.toFixed(0)}%)
                </span>
              </div>
              <div className="h-1.5 bg-forge-elevated rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${item.bg}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── RAG Status ─────────────────────────────────────────────────

function RagStatus({ rag }: { rag: RagStats | null }) {
  const isAvailable = rag?.status === "available" && rag.chunks > 0;

  const items = [
    {
      label: "Indexed Chunks",
      value: rag ? formatNumber(rag.chunks) : "—",
      icon: Database,
      color: "text-forge-primary",
      bg: "bg-forge-primary/10",
    },
    {
      label: "Embedding Model",
      value: rag?.embedding_model ? rag.embedding_model.split("/").pop() || rag.embedding_model : "—",
      icon: Brain,
      color: "text-success",
      bg: "bg-success/10",
    },
    {
      label: "BM25 Index",
      value: rag?.has_bm25 ? "Active" : "—",
      icon: Search,
      color: "text-warning",
      bg: "bg-warning/10",
    },
    {
      label: "Knowledge Graph",
      value: rag?.has_knowledge_graph ? "Connected" : "Not built",
      icon: Network,
      color: "text-cyan-400",
      bg: "bg-cyan-500/10",
    },
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">
          RAG System Status
        </h3>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
            isAvailable
              ? "bg-success/10 text-success"
              : "bg-forge-elevated text-text-muted"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isAvailable ? "bg-success" : "bg-text-muted"
            }`}
          />
          {isAvailable ? "Active" : "Offline"}
        </span>
      </div>
      <div className="space-y-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="flex items-center justify-between py-1.5"
            >
              <div className="flex items-center gap-2">
                <div
                  className={`p-1.5 rounded-lg ${item.bg} transition-colors`}
                >
                  <Icon size={13} className={item.color} />
                </div>
                <span className="text-xs text-text-secondary">
                  {item.label}
                </span>
              </div>
              <span className="text-xs font-mono text-text-primary font-medium">
                {item.value}
              </span>
            </div>
          );
        })}
        {rag?.db_path && isAvailable && (
          <div className="pt-1 border-t border-forge-border">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">DB Path</span>
              <span className="text-[10px] font-mono text-text-muted truncate max-w-[180px]" title={rag.db_path}>
                {rag.db_path}
              </span>
            </div>
          </div>
        )}
        {!rag && (
          <p className="text-xs text-text-muted text-center py-2">
            Loading RAG status...
          </p>
        )}
        {rag && !isAvailable && (
          <div className="pt-2">
            <p className="text-[11px] text-text-muted text-center leading-relaxed">
              Index a project on the{" "}
              <Link href="/projects" className="text-forge-primary hover:underline">
                Projects
              </Link>{" "}
              page to enable semantic code search.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── SEAL Status ────────────────────────────────────────────────

function SealStatus({ seal, onCycleComplete }: { seal: SealStats | null; onCycleComplete?: () => void }) {
  const isActive = seal?.status === "active";
  const metaReady = seal?.meta_learning?.ready_to_train ?? false;
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);

  const items = [
    {
      label: "Cycle",
      value: seal ? `#${seal.cycle}` : "—",
      icon: RefreshCw,
      color: "text-forge-primary",
      bg: "bg-forge-primary/10",
    },
    {
      label: "Actions Taken",
      value: seal ? String(seal.curriculum_state.total_actions_taken) : "—",
      icon: Activity,
      color: "text-success",
      bg: "bg-success/10",
    },
    {
      label: "Domains Explored",
      value: seal ? String(seal.curriculum_state.domains_explored) : "—",
      icon: Layers,
      color: "text-warning",
      bg: "bg-warning/10",
    },
    {
      label: "Rewards Collected",
      value: seal ? String(seal.meta_learning.reward_count) : "—",
      icon: Target,
      color: "text-cyan-400",
      bg: "bg-cyan-500/10",
    },
  ];

  const handleRunCycle = async () => {
    setRunning(true);
    setRunResult(null);
    try {
      const result = await triggerSealCycle(true);
      const action = result.seal?.action;
      const msg = action
        ? `Cycle: ${action.action as string} in ${action.domain as string}`
        : "Cycle completed";
      setRunResult(msg);
      setTimeout(() => {
        setRunResult(null);
        onCycleComplete?.();
      }, 3000);
    } catch (err) {
      setRunResult(`Error: ${err instanceof Error ? err.message : "Run failed"}`);
      setTimeout(() => setRunResult(null), 4000);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">
          SEAL Self-Improvement
        </h3>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
            isActive
              ? "bg-success/10 text-success"
              : "bg-forge-elevated text-text-muted"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isActive ? "bg-success animate-pulse" : "bg-text-muted"
            }`}
          />
          {isActive ? "Active" : "Idle"}
        </span>
      </div>
      <div className="space-y-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="flex items-center justify-between py-1.5"
            >
              <div className="flex items-center gap-2">
                <div
                  className={`p-1.5 rounded-lg ${item.bg} transition-colors`}
                >
                  <Icon size={13} className={item.color} />
                </div>
                <span className="text-xs text-text-secondary">
                  {item.label}
                </span>
              </div>
              <span className="text-xs font-mono text-text-primary font-medium">
                {item.value}
              </span>
            </div>
          );
        })}

        {/* Meta-learning readiness badge */}
        {seal && (
          <div className="pt-1 border-t border-forge-border">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-text-muted">
                Meta-Learning
              </span>
              <span
                className={`inline-flex items-center gap-1 text-[10px] font-semibold ${
                  metaReady ? "text-success" : "text-text-muted"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    metaReady ? "bg-success" : "bg-text-muted"
                  }`}
                />
                {metaReady ? "Ready to train" : `${seal.meta_learning.reward_count} reward${seal.meta_learning.reward_count !== 1 ? 's' : ''} collected`}
              </span>
            </div>
          </div>
        )}

        {/* Best action info */}
        {seal?.best_action && (
          <div className="pt-1 border-t border-forge-border">
            <div className="space-y-1">
              <span className="text-[10px] text-text-muted">Best Action</span>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-forge-primary font-medium">
                  {seal.best_action.action}
                </span>
                <span
                  className={`text-[10px] font-mono font-medium ${
                    seal.best_action.reward_delta >= 0
                      ? "text-success"
                      : "text-error"
                  }`}
                >
                  {seal.best_action.reward_delta >= 0 ? "+" : ""}
                  {(seal.best_action.reward_delta * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-text-muted">
                <span>{seal.best_action.domain}</span>
                <span>·</span>
                <span>{seal.best_action.difficulty}</span>
                <span>·</span>
                <span>Cycle #{seal.best_action.cycle}</span>
              </div>
            </div>
          </div>
        )}

        {!seal && (
          <p className="text-xs text-text-muted text-center py-2">
            Loading SEAL status...
          </p>
        )}

        {/* Trigger button */}
        {seal && (
          <div className="pt-3 border-t border-forge-border">
            {runResult && (
              <p
                className={`text-[10px] mb-2 text-center ${
                  runResult.startsWith("Error") ? "text-error" : "text-success"
                }`}
              >
                {runResult}
              </p>
            )}
            <button
              onClick={handleRunCycle}
              disabled={running}
              className="w-full btn-secondary text-xs gap-1.5 py-2"
            >
              {running ? (
                <>
                  <RefreshCw size={12} className="animate-spin" />
                  Running cycle...
                </>
              ) : (
                <>
                  <Play size={12} />
                  Run Dry-Run Cycle
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Languages Bar ──────────────────────────────────────────────

function LanguagesBar({ stats }: { stats: CaptureStats | null }) {
  if (!stats) return null;

  const langs = stats.signals_by_language;
  const entries = Object.entries(langs).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;

  const maxVal = entries[0][1];

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4">
        Languages
      </h3>
      <div className="space-y-2.5">
        {entries.slice(0, 6).map(([lang, count]) => (
          <div key={lang}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-mono text-text-secondary">
                {lang}
              </span>
              <span className="text-xs font-mono text-text-muted">
                {formatNumber(count)}
              </span>
            </div>
            <div className="h-1.5 bg-forge-elevated rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-forge-primary/60 transition-all duration-500"
                style={{ width: `${(count / maxVal) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [rateData, setRateData] = useState<AcceptanceRatePoint[]>([]);
  const [trainingRuns, setTrainingRuns] = useState<TrainingRun[]>([]);
  const [stats, setStats] = useState<CaptureStats | null>(null);
  const [ragStats, setRagStats] = useState<RagStats | null>(null);
  const [sealStats, setSealStats] = useState<SealStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [h, rate, train, s, rag, seal] = await Promise.all([
          getHealth().catch(() => null),
          getAcceptanceRate().catch(() => ({ data: [], training_markers: [] })),
          getTrainingStatus().catch(() => ({ active_run: null, history: [] })),
          getCaptureStats().catch(() => null),
          getRagStats().catch(() => null),
          getSealStats().catch(() => null),
        ]);
        setHealth(h);
        setRateData(rate.data);
        setTrainingRuns(train.history);
        setStats(s);
        setRagStats(rag);
        setSealStats(seal);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load dashboard data"
        );
      } finally {
        setLoading(false);
      }
    }
    load();

    // Auto-refresh every 30 seconds for real-time updates
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-8 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-96 bg-forge-elevated rounded" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-5 space-y-3">
              <div className="h-4 w-24 bg-forge-elevated rounded" />
              <div className="h-8 w-20 bg-forge-elevated rounded" />
            </div>
          ))}
        </div>
        <div className="card p-6">
          <div className="h-64 bg-forge-elevated rounded-lg" />
        </div>
      </div>
    );
  }

  if (error && !health) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <Zap size={48} className="text-forge-primary/40 mb-4" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Cannot connect to ForgeAI server
        </h2>
        <p className="text-sm text-text-muted max-w-md mb-6">
          Make sure the ForgeAI backend is running on port 7337.
          <br />
          Start it with: <code className="text-forge-primary">python src/api/server.py</code>
        </p>
        <button
          onClick={() => window.location.reload()}
          className="btn-primary"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  const totalSignals = stats
    ? Object.values(stats.signals_by_type).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-sm text-text-muted mt-1">
          Acceptance rate:{" "}
          <span className="text-forge-primary font-semibold">
            {stats
              ? `${stats.overall_acceptance_rate.toFixed(1)}%`
              : "—"}
          </span>
          {" · "}
          {totalSignals > 0 && (
            <>
              {formatNumber(totalSignals)} signals collected
              {" · "}
            </>
          )}
          {health?.uptime_seconds
            ? `Uptime: ${Math.floor(health.uptime_seconds / 60)}m`
            : ""}
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Acceptance Rate"
          value={stats ? `${stats.overall_acceptance_rate.toFixed(1)}%` : "—"}
          icon={TrendingUp}
          subtext={`${formatNumber(totalSignals)} total signals`}
        />
        <StatsCard
          title="Training Runs"
          value={formatNumber(trainingRuns.length)}
          icon={Brain}
          subtext={
            trainingRuns.length > 0
              ? `Last: ${formatTimeAgo(trainingRuns[0].timestamp)}`
              : "No runs yet"
          }
        />
        <StatsCard
          title="Languages"
          value={
            stats
              ? formatNumber(Object.keys(stats.signals_by_language).length)
              : "—"
          }
          icon={BarChart3}
          subtext="Active languages"
        />
        <StatsCard
          title="Sessions"
          value={stats ? formatNumber(stats.total_sessions) : "—"}
          icon={Zap}
          subtext="Developer sessions"
        />
      </div>

      {/* Chart + Signal Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <AcceptanceRateChart data={rateData} />
        </div>
        <SignalDistribution stats={stats} />
      </div>

      {/* Training History + SEAL Status + Languages + RAG Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <TrainingHistory runs={trainingRuns} />
        </div>
        <div className="space-y-4">
          <SealStatus seal={sealStats} onCycleComplete={() => getSealStats().then(setSealStats).catch(() => {})} />
          <RagStatus rag={ragStats} />
          <LanguagesBar stats={stats} />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="flex items-center gap-3 pt-2">
        <Link href="/training" className="btn-primary">
          <Brain size={16} />
          View Training
        </Link>
        <Link href="/projects" className="btn-secondary">
          <BarChart3 size={16} />
          Manage Projects
        </Link>
        <Link href="/agent" className="btn-secondary">
          <Zap size={16} />
          Open Agent
        </Link>
      </div>
    </div>
  );
}
