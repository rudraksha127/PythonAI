"use client";

import { useEffect, useState, useCallback } from "react";
import { getSealStats } from "@/lib/api";
import type { SealStats } from "@/lib/types";
import { formatNumber } from "@/lib/utils";
import {
  RefreshCw,
  Target,
  Layers,
  Activity,
  TrendingUp,
  TrendingDown,
  Play,
  CheckCircle2,
  AlertCircle,
  Brain,
  FileCode,
  Clock,
  ChevronRight,
  BarChart3,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// ─── Summary Stats Row ──────────────────────────────────────────

function SummaryStats({ seal }: { seal: SealStats | null }) {
  const items = [
    {
      label: "Cycle",
      value: seal ? `#${seal.cycle}` : "—",
      icon: RefreshCw,
      color: "text-forge-primary",
      gradient: "from-forge-primary/20 to-forge-primary/5",
    },
    {
      label: "Actions Taken",
      value: seal ? formatNumber(seal.curriculum_state.total_actions_taken) : "—",
      icon: Activity,
      color: "text-success",
      gradient: "from-success/20 to-success/5",
    },
    {
      label: "Domains Explored",
      value: seal ? formatNumber(seal.curriculum_state.domains_explored) : "—",
      icon: Layers,
      color: "text-warning",
      gradient: "from-warning/20 to-warning/5",
    },
    {
      label: "Rewards Collected",
      value: seal ? formatNumber(seal.meta_learning.reward_count) : "—",
      icon: Target,
      color: "text-cyan-400",
      gradient: "from-cyan-500/20 to-cyan-500/5",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.label} className="card p-4 relative overflow-hidden group">
            <div
              className={`absolute inset-0 bg-gradient-to-br ${item.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`}
            />
            <div className="relative">
              <div className="flex items-center justify-between mb-2">
                <span className="metric-label">{item.label}</span>
                <Icon size={16} className={item.color} />
              </div>
              <div className={`metric-value text-2xl font-bold ${item.color}`}>
                {item.value}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Best Action Card ──────────────────────────────────────────

function BestActionCard({ seal }: { seal: SealStats | null }) {
  const action = seal?.best_action;
  if (!action) {
    return (
      <div className="card p-6 flex items-center justify-center h-48">
        <div className="text-center">
          <Target size={32} className="mx-auto mb-3 text-text-muted" />
          <p className="text-sm text-text-muted">
            No actions recorded yet. Run a SEAL cycle to see the best action here.
          </p>
        </div>
      </div>
    );
  }

  const isPositive = action.reward_delta >= 0;

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={16} className="text-forge-primary" />
        <h3 className="text-sm font-semibold text-text-primary">
          Best Curriculum Action
        </h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Action info */}
        <div className="space-y-3">
          <div>
            <span className="metric-label text-[10px]">Action Type</span>
            <div className="flex items-center gap-2 mt-1">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-forge-primary/10 text-forge-primary capitalize">
                {action.action.replace(/_/g, " ")}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div>
              <span className="metric-label text-[10px]">Domain</span>
              <p className="text-sm font-mono text-text-primary mt-0.5 capitalize">
                {action.domain.replace(/_/g, " ")}
              </p>
            </div>
            <div>
              <span className="metric-label text-[10px]">Difficulty</span>
              <p className="text-sm font-mono text-text-primary mt-0.5 capitalize">
                {action.difficulty}
              </p>
            </div>
            <div>
              <span className="metric-label text-[10px]">Cycle</span>
              <p className="text-sm font-mono text-text-primary mt-0.5">
                #{action.cycle}
              </p>
            </div>
          </div>
        </div>

        {/* Reward delta */}
        <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-forge-elevated">
          <span className="metric-label text-[10px] mb-1">Reward Delta</span>
          <div className={`flex items-center gap-2 ${isPositive ? "text-success" : "text-error"}`}>
            {isPositive ? (
              <TrendingUp size={24} />
            ) : (
              <TrendingDown size={24} />
            )}
            <span className="text-3xl font-bold font-mono">
              {isPositive ? "+" : ""}
              {(action.reward_delta * 100).toFixed(2)}%
            </span>
          </div>
          <p className="text-xs text-text-muted mt-1">
            {isPositive ? "Acceptance rate improved" : "Acceptance rate declined"}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Curriculum Chart ─────────────────────────────────────────

function CurriculumChart({ seal }: { seal: SealStats | null }) {
  const difficulties = seal?.curriculum_state?.difficulties_tried;
  if (!difficulties || Object.keys(difficulties).length === 0) {
    return (
      <div className="card p-6 flex items-center justify-center h-48">
        <div className="text-center">            <BarChart3 size={32} className="mx-auto mb-3 text-text-muted" />
          <p className="text-sm text-text-muted">
            No curriculum data yet. Run a SEAL cycle to populate.
          </p>
        </div>
      </div>
    );
  }

  const chartData = Object.entries(difficulties).map(([difficulty, count]) => ({
    name: difficulty.charAt(0).toUpperCase() + difficulty.slice(1),
    count,
  }));

  const COLORS = ["#22C55E", "#FBBF24", "#EF4444", "#5B5BFF", "#22D3EE"];

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 size={16} className="text-forge-primary" />
        <h3 className="text-sm font-semibold text-text-primary">
          Difficulties Tried
        </h3>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
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
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "#18181C",
                border: "1px solid #27272C",
                borderRadius: "8px",
                fontSize: 12,
              }}
              formatter={(value: number) => [formatNumber(value), "Actions"]}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} barSize={48}>
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                  className="hover:opacity-80 transition-opacity"
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Meta-Learning Panel ──────────────────────────────────────

function MetaLearningPanel({ seal }: { seal: SealStats | null }) {
  if (!seal) {
    return (
      <div className="card p-6 flex items-center justify-center h-48">
        <p className="text-sm text-text-muted">Loading...</p>
      </div>
    );
  }

  const meta = seal.meta_learning;
  const ready = meta.ready_to_train;

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={16} className="text-forge-primary" />
        <h3 className="text-sm font-semibold text-text-primary">
          Meta-Learning Status
        </h3>
      </div>

      <div className="space-y-4">
        {/* Readiness indicator */}
        <div
          className={`p-4 rounded-lg ${
            ready ? "bg-success/10 border border-success/20" : "bg-forge-elevated"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center ${
                  ready ? "bg-success/20" : "bg-zinc-800"
                }`}
              >
                {ready ? (
                  <CheckCircle2 size={20} className="text-success" />
                ) : (
                  <Clock size={20} className="text-text-muted" />
                )}
              </div>
              <div>
                <p className="text-sm font-semibold text-text-primary">
                  {ready
                    ? "Ready to Train"
                    : "Collecting Rewards"}
                </p>
                <p className="text-xs text-text-muted mt-0.5">
                  {ready
                    ? "Enough rewards collected. The curriculum generator will now be fine-tuned on successful actions."
                    : `${meta.reward_count} reward${
                        meta.reward_count !== 1 ? "s" : ""
                      } collected so far. Need at least 3 rewards with at least 1 positive result.`}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-text-muted">
              Training Readiness
            </span>
            <span className="text-xs font-mono text-text-primary">
              {Math.min(100, Math.round((meta.reward_count / 3) * 100))}%
            </span>
          </div>
          <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                ready ? "bg-success" : "bg-forge-primary/60"
              }`}
              style={{
                width: `${Math.min(100, Math.round((meta.reward_count / 3) * 100))}%`,
              }}
            />
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg bg-forge-elevated">
            <span className="metric-label text-[10px]">Reward Records</span>
            <p className="text-lg font-bold font-mono text-text-primary mt-1">
              {formatNumber(meta.reward_count)}
            </p>
          </div>
          <div className="p-3 rounded-lg bg-forge-elevated">
            <span className="metric-label text-[10px]">
              Min Required
            </span>
            <p className="text-lg font-bold font-mono text-text-muted mt-1">
              3
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Config Panel ─────────────────────────────────────────────

function ConfigPanel({ seal }: { seal: SealStats | null }) {
  if (!seal) return null;

  const config = seal.config;
  const keySettings = [
    { label: "Curriculum Model", key: "curriculum_model" },
    { label: "Inner Model", key: "inner_model" },
    { label: "Inner LoRA Rank", key: "inner_lora_rank" },
    { label: "Learning Rate", key: "inner_learning_rate" },
    { label: "Max Steps", key: "inner_max_steps" },
    { label: "Examples Per Action", key: "synthetic_examples_per_action" },
    { label: "Meta-Learning", key: "meta_enabled" },
    { label: "Exploration Rate", key: "exploration_rate" },
    { label: "State Dir", key: "state_dir" },
    { label: "Adapter Dir", key: "adapter_dir" },
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <FileCode size={16} className="text-forge-primary" />
        <h3 className="text-sm font-semibold text-text-primary">
          Configuration
        </h3>
      </div>
      <div className="space-y-2">
        {keySettings.map(({ label, key }) => {
          const value = config[key];
          if (value === undefined || value === null) return null;
          return (
            <div
              key={key}
              className="flex items-center justify-between py-1.5"
            >
              <span className="text-xs text-text-secondary">{label}</span>
              <span className="text-xs font-mono text-text-primary truncate ml-4 max-w-[200px]">
                {typeof value === "boolean"
                  ? value
                    ? "Enabled"
                    : "Disabled"
                  : String(value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function SealPage() {
  const [seal, setSeal] = useState<SealStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await getSealStats();
      setSeal(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load SEAL status"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRunCycle = async () => {
    setRunning(true);
    setRunResult(null);
    try {
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";
      const res = await fetch(`${baseUrl}/api/seal/cycle?dry_run=true`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || res.statusText);
      }
      const result = await res.json();
      const action = result.seal?.action;
      setRunResult(
        action
          ? `Generated action: ${action.action} in ${action.domain} (${action.difficulty})`
          : "Cycle completed"
      );
      // Reload data after a short delay for state to persist
      setTimeout(() => loadData(), 500);
    } catch (err) {
      setRunResult(
        `Error: ${err instanceof Error ? err.message : "Run failed"}`
      );
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-80 bg-forge-elevated rounded" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-4 space-y-2">
              <div className="h-4 w-16 bg-forge-elevated rounded" />
              <div className="h-8 w-12 bg-forge-elevated rounded" />
            </div>
          ))}
        </div>
        <div className="card p-6">
          <div className="h-48 bg-forge-elevated rounded-lg" />
        </div>
      </div>
    );
  }

  if (error && !seal) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <AlertCircle size={48} className="text-error/40 mb-4" />
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Cannot load SEAL data
        </h2>
        <p className="text-sm text-text-muted max-w-md mb-6">{error}</p>
        <button onClick={loadData} className="btn-primary">
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  const isActive = seal?.status === "active";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-text-primary">
              SEAL Self-Improvement
            </h1>
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
          <p className="text-sm text-text-muted">
            {seal?.system || "SEAL Phase 3"} ·{" "}
            {isActive
              ? `Cycle #${seal?.cycle} running`
              : "Waiting for next cycle"}
            {seal && ` · ${seal.curriculum_state.domains_explored} domains explored`}
          </p>
        </div>
        <button
          onClick={handleRunCycle}
          disabled={running}
          className="btn-primary"
        >
          {running ? (
            <>
              <RefreshCw size={16} className="animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Play size={16} />
              Run Dry-Run Cycle
            </>
          )}
        </button>
      </div>

      {/* Run result toast */}
      {runResult && (
        <div
          className={`card p-3 flex items-center gap-2 text-sm ${
            runResult.startsWith("Error")
              ? "border-error/30 bg-error/5"
              : "border-success/30 bg-success/5"
          }`}
        >
          {runResult.startsWith("Error") ? (
            <AlertCircle size={14} className="text-error shrink-0" />
          ) : (
            <CheckCircle2 size={14} className="text-success shrink-0" />
          )}
          <span
            className={
              runResult.startsWith("Error") ? "text-error" : "text-success"
            }
          >
            {runResult}
          </span>
        </div>
      )}

      {/* Summary stats */}
      <SummaryStats seal={seal} />

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left column: Best Action + Curriculum Chart */}
        <div className="lg:col-span-2 space-y-4">
          <BestActionCard seal={seal} />
          <CurriculumChart seal={seal} />

          {/* Cycle History Placeholder */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <Clock size={16} className="text-forge-primary" />
              <h3 className="text-sm font-semibold text-text-primary">
                Cycle History
              </h3>
            </div>
            {seal && seal.cycle > 0 ? (
              <div className="space-y-2">
                {Array.from({ length: seal.cycle }, (_, i) => {
                  const cycleNum = i + 1;
                  const isBest =
                    seal.best_action?.cycle === cycleNum;
                  return (
                    <div
                      key={cycleNum}
                      className={`flex items-center justify-between p-3 rounded-lg ${
                        isBest
                          ? "bg-forge-primary/5 border border-forge-primary/20"
                          : "bg-forge-elevated"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-xs font-mono text-text-secondary">
                          {cycleNum}
                        </span>
                        <div>
                          <p className="text-xs font-medium text-text-primary">
                            Cycle #{cycleNum}
                            {isBest && (
                              <span className="ml-2 text-[10px] text-forge-primary font-semibold">
                                Best
                              </span>
                            )}
                          </p>
                          <p className="text-[10px] text-text-muted mt-0.5">
                            {cycleNum === seal.cycle
                              ? "Latest cycle"
                              : "Previous cycle"}
                          </p>
                        </div>
                      </div>
                      <ChevronRight size={14} className="text-text-muted" />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8">
                <Clock size={28} className="mx-auto mb-2 text-text-muted" />
                <p className="text-sm text-text-muted">
                  No cycles completed yet. Run a SEAL cycle to get started.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right column: Meta-Learning + Config */}
        <div className="space-y-4">
          <MetaLearningPanel seal={seal} />
          <ConfigPanel seal={seal} />
        </div>
      </div>
    </div>
  );
}
