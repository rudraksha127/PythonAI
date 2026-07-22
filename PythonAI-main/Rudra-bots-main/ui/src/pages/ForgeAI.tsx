import { useEffect, useState } from "react";
import {
  Activity,
  TrendingUp,
  Brain,
  Server,
  Zap,
  RefreshCw,
  BarChart3,
  Cpu,
  Clock,
  Database,
  Layers,
} from "lucide-react";
import { getForgeAIMetrics, type ForgeAIMetricsResponse } from "@/lib/api";

const STAT_COLORS: Record<string, string> = {
  purple: "text-purple-400",
  cyan: "text-cyan-400",
  green: "text-green-400",
  yellow: "text-yellow-400",
};

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  subtitle,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  subtitle?: string;
}) {
  const textColor = STAT_COLORS[color] || "text-zinc-400";
  return (
    <div className="card p-4 hover:bg-[var(--panel)]/50 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={textColor} />
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className={`text-2xl font-bold ${textColor}`}>{value}</div>
      {subtitle && (
        <div className="text-[10px] text-zinc-600 mt-1">{subtitle}</div>
      )}
    </div>
  );
}

const SIGNAL_COLORS: Record<string, string> = {
  Accept: "bg-green-500/60",
  Reject: "bg-red-500/60",
  Edit: "bg-yellow-500/60",
  Pr_merge: "bg-blue-500/60",
  Test_pass: "bg-emerald-500/60",
  Test_fail: "bg-orange-500/60",
};

function SignalBar({ name, value, percentage }: { name: string; value: number; percentage: number }) {
  const barColor = SIGNAL_COLORS[name] || "bg-purple-500/60";

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-zinc-300 capitalize">{name.replace(/_/g, " ")}</span>
        <span className="font-mono text-zinc-500">
          {value} ({percentage}%)
        </span>
      </div>
      <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function MiniChart({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return <div className="text-xs text-zinc-600 py-4 text-center">No data yet</div>;
  const max = Math.max(...data, 1);
  return (
    <div className="flex items-end gap-0.5 h-24">
      {data.map((val, i) => (
        <div
          key={i}
          className="flex-1 rounded-t transition-all duration-300 hover:opacity-80"
          style={{
            height: `${(val / max) * 100}%`,
            backgroundColor: `var(--${color === "purple" ? "accent" : color})`,
            opacity: 0.4 + (val / max) * 0.6,
          }}
          title={`${val.toFixed(1)}%`}
        />
      ))}
    </div>
  );
}

export default function ForgeAI() {
  const [metrics, setMetrics] = useState<ForgeAIMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await getForgeAIMetrics();
      setMetrics(result);
      setLastFetch(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch metrics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  const data = metrics?.data;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-6 space-y-6 max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <BarChart3 size={18} className="text-[var(--accent)]" />
              <h1 className="text-xl font-bold">ForgeAI Metrics</h1>
            </div>
            <p className="text-sm text-zinc-400 mt-1">
              Real-time self-improvement AI metrics from PythonAI
            </p>
          </div>
          <div className="flex items-center gap-2">
            {lastFetch && (
              <span className="text-[10px] text-zinc-600">
                Updated {Math.floor((Date.now() - lastFetch.getTime()) / 1000)}s ago
              </span>
            )}
            <button
              onClick={load}
              disabled={loading}
              className="btn-secondary text-xs flex items-center gap-1.5"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="card p-6 border border-red-500/20 bg-red-500/5">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center">
                <Zap size={14} className="text-red-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-medium text-red-400">Connection Error</h3>
                <p className="text-xs text-zinc-400 mt-0.5">{error}</p>
              </div>
              <button onClick={load} className="btn-primary text-xs">
                Retry
              </button>
            </div>
            {metrics?.hint && (
              <p className="text-xs text-zinc-500 mt-3 ml-11">{metrics.hint}</p>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && !data && !error && (
          <div className="flex items-center justify-center h-64">
            <RefreshCw size={24} className="animate-spin text-zinc-500" />
          </div>
        )}

        {/* Connected: Show Data */}
        {data && (
          <>
            {/* Status Bar */}
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]" />
                PythonAI Connected
              </span>
              <span>·</span>
              <span>v{data.version}</span>
              <span>·</span>
              <span className="flex items-center gap-1">
                <Clock size={10} />
                Uptime: {Math.floor(data.server.uptime_seconds / 60)}m
              </span>
              {metrics?.cached && (
                <>
                  <span>·</span>
                  <span className="text-yellow-500 flex items-center gap-1">
                    <Database size={10} />
                    Cached
                  </span>
                </>
              )}
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatCard
                label="Acceptance Rate"
                value={`${data.statistics.overall_acceptance_rate.toFixed(1)}%`}
                icon={TrendingUp}
                color="purple"
                subtitle={`${data.total_signals} total signals`}
              />
              <StatCard
                label="Total Sessions"
                value={data.statistics.total_sessions}
                icon={Activity}
                color="cyan"
              />
              <StatCard
                label="Edit Distance"
                value={data.statistics.avg_edit_distance.toFixed(2)}
                icon={Layers}
                color="green"
              />
              <StatCard
                label="Training Runs"
                value={data.training.history.length}
                icon={Brain}
                color="yellow"
                subtitle={
                  data.training.schedule.enabled
                    ? `Next: ${data.training.schedule.next_run ? new Date(data.training.schedule.next_run).toLocaleDateString() : "N/A"}`
                    : "Manual only"
                }
              />
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: Acceptance Rate Trend */}
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold flex items-center gap-2">
                    <TrendingUp size={14} className="text-purple-400" />
                    Acceptance Rate Trend
                  </h2>
                  <span className="text-[10px] text-zinc-600">
                    {data.acceptance_rates.length} data points
                  </span>
                </div>
                <MiniChart
                  data={data.acceptance_rates.map((r) => r.acceptance_rate)}
                  color="purple"
                />
                {data.acceptance_rates.length > 0 && (
                  <div className="flex justify-between text-[10px] text-zinc-600 mt-2">
                    <span>{data.acceptance_rates[0]?.date}</span>
                    <span>{data.acceptance_rates[data.acceptance_rates.length - 1]?.date}</span>
                  </div>
                )}
              </div>

              {/* Right: Signal Distribution */}
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold flex items-center gap-2">
                    <BarChart3 size={14} className="text-cyan-400" />
                    Signal Distribution
                  </h2>
                  <span className="text-[10px] text-zinc-600">
                    {data.signal_distribution.length} types
                  </span>
                </div>
                {data.signal_distribution.length > 0 ? (
                  <div className="space-y-3">
                    {data.signal_distribution.map((s) => (
                      <SignalBar
                        key={s.name}
                        name={s.name}
                        value={s.value}
                        percentage={s.percentage}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 py-4 text-center">
                    No signals captured yet
                  </p>
                )}
              </div>
            </div>

            {/* Bottom section: Languages + Training */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Languages */}
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold flex items-center gap-2">
                    <Cpu size={14} className="text-green-400" />
                    Languages Detected
                  </h2>
                </div>
                {Object.keys(data.statistics.signals_by_language).length > 0 ? (
                  <div className="space-y-2">
                    {Object.entries(data.statistics.signals_by_language)
                      .sort(([, a], [, b]) => b - a)
                      .map(([lang, count]) => {
                        const total = data.total_signals || 1;
                        const pct = (count / total) * 100;
                        return (
                          <div key={lang}>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span className="capitalize text-zinc-300">{lang}</span>
                              <span className="font-mono text-zinc-500">{count}</span>
                            </div>
                            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-emerald-500/60"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 py-4 text-center">No language data yet</p>
                )}
              </div>

              {/* Training History */}
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold flex items-center gap-2">
                    <Brain size={14} className="text-yellow-400" />
                    Training History
                  </h2>
                  {data.training.schedule.enabled && (
                    <span className="text-[10px] text-green-400 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                      Auto-schedule
                    </span>
                  )}
                </div>

                {data.training.history.length > 0 ? (
                  <div className="space-y-2">
                    {data.training.history.slice(0, 5).map((run: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between py-1.5 border-b border-zinc-800/50 last:border-0"
                      >
                        <div className="text-xs text-zinc-300">
                          Run #{run.run_id?.slice(0, 8) || i + 1}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-[10px] text-zinc-500">
                            Δ: {run.acceptance_delta != null ? `${(run.acceptance_delta * 100).toFixed(1)}%` : "—"}
                          </span>
                          <span className="text-[10px] text-zinc-600">
                            {run.signals_used || "?"} signals
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-6">
                    <Brain size={24} className="mx-auto text-zinc-700 mb-2" />
                    <p className="text-sm text-zinc-500">No training runs yet</p>
                    <p className="text-xs text-zinc-600 mt-1">
                      Training runs appear after signals are captured
                    </p>
                  </div>
                )}

                {/* Schedule info */}
                {data.training.schedule.enabled && data.training.schedule.next_run && (
                  <div className="mt-3 pt-3 border-t border-zinc-800/50">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-zinc-500">Next scheduled run</span>
                      <span className="text-zinc-300">
                        {new Date(data.training.schedule.next_run).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-[10px] text-zinc-600 mt-0.5">
                      {data.training.schedule.description}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* System Status */}
            <div className="card p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Server size={14} className="text-zinc-400" />
                  <span className="text-xs font-medium text-zinc-400">System Status</span>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <span className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${data.server.inference_connected ? "bg-green-400" : "bg-red-400"}`} />
                    Inference
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${data.server.db_ok ? "bg-green-400" : "bg-red-400"}`} />
                    Database
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                    Auto-sync (30s)
                  </span>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Not connected + no error (first load) */}
        {!loading && !data && !error && (
          <div className="card p-8 text-center">
            <Server size={32} className="mx-auto text-zinc-700 mb-3" />
            <h3 className="text-sm font-medium text-zinc-300 mb-1">PythonAI Server Not Reachable</h3>
            <p className="text-xs text-zinc-500 mb-4">
              Start the PythonAI API server on port 7337 to see ForgeAI metrics.
            </p>
            <button onClick={load} className="btn-primary text-xs">
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
