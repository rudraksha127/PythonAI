"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getTrainingStatus,
  triggerTraining,
} from "@/lib/api";
import { useTrainingWebSocket } from "@/hooks/useTrainingWebSocket";
import type {
  TrainingRun,
  ActiveTrainingRun,
} from "@/lib/types";
import { formatNumber, formatTimeAgo } from "@/lib/utils";
import {
  Brain,
  Play,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  AlertCircle,
  BarChart3,
  Activity,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";

// ─── Active Run Monitor ─────────────────────────────────────────

function ActiveRunMonitor({
  run,
  onComplete,
}: {
  run: ActiveTrainingRun | null;
  onComplete: () => void;
}) {
  // Use the reusable training WebSocket hook (seeds from run, updates via WS)
  const { progress, loss, step, status } = useTrainingWebSocket({
    enabled: run !== null,
    run,
    onComplete,
  });

  if (!run && status === "idle") return null;

  const isRunning = status === "running" || status === "queued";
  const progressPct = Math.round(progress * 100);

  return (
    <div className="card p-5 border-forge-primary/30">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              isRunning
                ? "bg-forge-primary/10 animate-pulse"
                : status === "completed"
                ? "bg-success/10"
                : "bg-error/10"
            }`}
          >
            {isRunning ? (
              <Activity size={18} className="text-forge-primary" />
            ) : status === "completed" ? (
              <CheckCircle2 size={18} className="text-success" />
            ) : (
              <XCircle size={18} className="text-error" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">
              {isRunning
                ? "Training in Progress"
                : status === "completed"
                ? "Training Complete"
                : "Training Failed"}
            </h3>
            <p className="text-xs text-text-muted mt-0.5">
              {isRunning
                ? `Run ID: ${run?.run_id.slice(0, 8)}...`
                : status === "completed"
                ? `Completed ${formatTimeAgo(Date.now() / 1000)} ago`
                : "An error occurred during training"}
            </p>
          </div>
        </div>
        {run && (
          <span className="text-xs font-mono text-text-muted">
            {formatTimeAgo(run.started_at)}
          </span>
        )}
      </div>

      {isRunning && (
        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-text-muted">Progress</span>
              <span className="text-xs font-mono text-text-primary">
                {progressPct}%
              </span>
            </div>
            <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-forge-primary transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            {step !== null && (
              <span>
                Step: <span className="font-mono text-text-primary">{step}</span>
              </span>
            )}
            {loss !== null && (
              <span>
                Loss:{" "}
                <span className="font-mono text-text-primary">
                  {loss.toFixed(4)}
                </span>
              </span>
            )}
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              Running
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Training History Table ─────────────────────────────────────

function TrainingHistoryTable({ runs }: { runs: TrainingRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="card p-12 text-center">
        <Brain size={40} className="mx-auto mb-4 text-text-muted" />
        <h3 className="text-base font-semibold text-text-primary mb-2">
          No Training Runs Yet
        </h3>
        <p className="text-sm text-text-muted max-w-md mx-auto mb-6">
          Collect at least 50 developer signals (accepts/rejects/edits) via the
          VS Code extension, then trigger your first training run.
        </p>
        <button className="btn-primary" disabled>
          <Play size={16} />
          Trigger Training
        </button>
      </div>
    );
  }

  const improved = runs.filter((r) => r.acceptance_delta > 0).length;
  const degraded = runs.filter((r) => r.acceptance_delta < 0).length;
  const avgDelta =
    runs.reduce((sum, r) => sum + r.acceptance_delta, 0) / runs.length;

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4">
          <span className="metric-label">Total Runs</span>
          <div className="metric-value text-xl font-bold mt-1">
            {formatNumber(runs.length)}
          </div>
        </div>
        <div className="card p-4">
          <span className="metric-label">Improved</span>
          <div className="metric-value text-xl font-bold mt-1 text-success">
            {formatNumber(improved)}
          </div>
        </div>
        <div className="card p-4">
          <span className="metric-label">Degraded</span>
          <div className="metric-value text-xl font-bold mt-1 text-error">
            {formatNumber(degraded)}
          </div>
        </div>
        <div className="card p-4">
          <span className="metric-label">Avg Delta</span>
          <div
            className={`metric-value text-xl font-bold mt-1 ${
              avgDelta >= 0 ? "text-success" : "text-error"
            }`}
          >
            {avgDelta >= 0 ? "+" : ""}
            {(avgDelta * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Charts row: Delta chart + Loss curve */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Delta chart */}
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-4">
            Acceptance Rate Delta per Run
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[...runs].reverse().map((r, i) => ({
                  name: `#${runs.length - i}`,
                  delta: r.acceptance_delta * 100,
                  fill: r.acceptance_delta >= 0 ? "#22C55E" : "#EF4444",
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#27272C" />
                <XAxis
                  dataKey="name"
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
                  contentStyle={{
                    background: "#18181C",
                    border: "1px solid #27272C",
                    borderRadius: "8px",
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${value.toFixed(2)}%`, "Delta"]}
                />
                <Bar dataKey="delta" radius={[3, 3, 0, 0]}>
                  {[...runs].reverse().map((r, i) => (
                    <Cell
                      key={`cell-${i}`}
                      fill={r.acceptance_delta >= 0 ? "#22C55E" : "#EF4444"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Loss curve (REQ-DASH-002) */}
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-4">
            Training Loss Progression
          </h3>
          <div className="h-48">
            {(() => {
              const lossData = [...runs]
                .reverse()
                .filter((r) => r.train_loss !== null)
                .map((r, i) => ({
                  name: `#${runs.length - i}`,
                  loss: r.train_loss as number,
                }));

              if (lossData.length < 2) {
                return (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-xs text-text-muted">
                      {lossData.length === 1
                        ? "Need at least 2 runs with loss data to plot a curve"
                        : "No training loss data available yet"}
                    </p>
                  </div>
                );
              }

              return (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={lossData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272C" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "#71717A", fontSize: 11 }}
                      tickLine={false}
                      axisLine={{ stroke: "#27272C" }}
                    />
                    <YAxis
                      tick={{ fill: "#71717A", fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      domain={["auto", "auto"]}
                      tickFormatter={(v) => v.toFixed(3)}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#18181C",
                        border: "1px solid #27272C",
                        borderRadius: "8px",
                        fontSize: 12,
                      }}
                      formatter={(value: number) => [value.toFixed(4), "Train Loss"]}
                    />
                    <Line
                      type="monotone"
                      dataKey="loss"
                      stroke="#F59E0B"
                      strokeWidth={2}
                      dot={{ r: 3, fill: "#F59E0B" }}
                      activeDot={{ r: 5, fill: "#F59E0B" }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              );
            })()}
          </div>
          <p className="text-[10px] text-text-muted text-center mt-2">
            Lower loss indicates better model fit. Yellow line shows training loss across runs.
          </p>
        </div>
      </div>

      {/* History table */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-forge-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            Run History
          </h3>
          <span className="text-xs text-text-muted">
            {formatNumber(runs.length)} total runs
          </span>
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
                  Train Loss
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
              {runs.slice(0, 50).map((run) => (
                <tr
                  key={run.run_id}
                  className="hover:bg-forge-elevated transition-colors"
                >
                  <td className="px-6 py-3 font-mono text-xs text-text-primary">
                    {formatTimeAgo(run.timestamp)}
                  </td>
                  <td className="px-6 py-3 text-text-secondary font-mono text-xs max-w-[160px] truncate">
                    {run.model_name.split("/").pop()}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-right text-text-primary">
                    {formatNumber(run.signals_used)}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-right text-text-secondary">
                    {run.train_loss !== null
                      ? run.train_loss.toFixed(4)
                      : "—"}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-right text-text-secondary">
                    {(run.acceptance_rate_before * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-right text-text-primary">
                    {(run.acceptance_rate_after * 100).toFixed(1)}%
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-right">
                    <div className="flex items-center justify-end gap-1">
                      {run.acceptance_delta >= 0 ? (
                        <TrendingUp size={12} className="text-success" />
                      ) : (
                        <TrendingDown size={12} className="text-error" />
                      )}
                      <span
                        className={
                          run.acceptance_delta >= 0
                            ? "text-success"
                            : "text-error"
                        }
                      >
                        {run.acceptance_delta >= 0 ? "+" : ""}
                        {(run.acceptance_delta * 100).toFixed(2)}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function TrainingPage() {
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [activeRun, setActiveRun] = useState<ActiveTrainingRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const status = await getTrainingStatus();
      setRuns(status.history);
      setActiveRun(status.active_run);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load training data"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      const result = await triggerTraining();
      // Poll for active run
      const interval = setInterval(async () => {
        try {
          const status = await getTrainingStatus();
          if (status.active_run) {
            setActiveRun(status.active_run);
            clearInterval(interval);
          }
        } catch {}
      }, 1000);

      // Timeout after 30s
      setTimeout(() => clearInterval(interval), 30000);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to trigger training"
      );
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-80 bg-forge-elevated rounded" />
        </div>
        <div className="card p-6">
          <div className="h-64 bg-forge-elevated rounded-lg" />
        </div>
      </div>
    );
  }

  if (error && runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <AlertCircle size={48} className="text-error/40 mb-4" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Cannot load training data
        </h2>
        <p className="text-sm text-text-muted max-w-md mb-6">{error}</p>
        <button onClick={loadData} className="btn-primary">
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
          <h1 className="text-2xl font-bold text-text-primary">Training</h1>
          <p className="text-sm text-text-muted mt-1">
            Monitor training runs, track acceptance rate improvements, and
            trigger manual training.
          </p>
        </div>
        <button
          onClick={handleTrigger}
          disabled={triggering || activeRun !== null}
          className="btn-primary"
        >
          {triggering ? (
            <>
              <RefreshCw size={16} className="animate-spin" />
              Starting...
            </>
          ) : (
            <>
              <Play size={16} />
              Trigger Training
            </>
          )}
        </button>
      </div>

      {/* Active run monitor */}
      <ActiveRunMonitor
        run={activeRun}
        onComplete={() => {
          setActiveRun(null);
          loadData();
        }}
      />

      {/* Training history */}
      <TrainingHistoryTable runs={runs} />
    </div>
  );
}
