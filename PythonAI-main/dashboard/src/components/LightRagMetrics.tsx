"use client";

import { useEffect, useState, useCallback } from "react";
import { getRagStats, getRagCacheStats, clearRagCache, getRagBackendInfo } from "@/lib/api";
import type { RagStats, RagCacheStats, RagBackendInfo } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import {
  Database,
  Zap,
  Clock,
  RefreshCw,
  Trash2,
  Layers,
  Search,
  AlertTriangle,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// Sub-Components
// ═══════════════════════════════════════════════════════════════════

/** A radial-style gauge showing a percentage (cache hit rate). */
function HitRateGauge({ rate, size = 72 }: { rate: number; size?: number }) {
  const strokeWidth = 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (rate / 100) * circumference;

  const color =
    rate >= 80 ? "#22C55E" : rate >= 50 ? "#5B5BFF" : rate >= 20 ? "#F59E0B" : "#EF4444";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(39,39,44,0.8)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-bold font-mono" style={{ color }}>
          {rate.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

/** A small stat tile used inside the widget. */
function StatItem({
  label,
  value,
  icon: Icon,
  color = "text-text-muted",
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color?: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-center gap-3 group">
      <div className="p-1.5 rounded-lg bg-forge-elevated/50 group-hover:bg-forge-elevated transition-colors">
        <Icon size={14} className={color} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
          <span className={cn("text-xs font-semibold font-mono", color)}>{value}</span>
        </div>
        {subtitle && <p className="text-[9px] text-text-muted/60 mt-0.5 truncate">{subtitle}</p>}
      </div>
    </div>
  );
}

/** Latency display with a mini bar. */
function LatencyBar({ avgMs }: { avgMs: number }) {
  const clamped = Math.min(avgMs, 5000);
  const pct = (clamped / 5000) * 100;
  const color =
    avgMs < 500 ? "bg-success" : avgMs < 1500 ? "bg-forge-primary" : avgMs < 3000 ? "bg-warning" : "bg-error";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-text-muted uppercase tracking-wider flex items-center gap-1">
          <Clock size={11} className="text-forge-primary" />
          Avg Query Latency
        </span>
        <span className="text-xs font-mono font-semibold text-text-primary">
          {avgMs < 1 ? "<1" : avgMs.toFixed(0)} ms
        </span>
      </div>
      <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-700", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-text-muted">
        <span>Fast</span>
        <span>5,000ms</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

interface LightRagMetricsProps {
  /** Optional — pass in existing RagStats to avoid redundant fetches */
  existingStats?: RagStats | null;
}

export default function LightRagMetrics({ existingStats }: LightRagMetricsProps) {
  const [stats, setStats] = useState<RagStats | null>(existingStats ?? null);
  const [cacheStats, setCacheStats] = useState<RagCacheStats | null>(null);
  const [backendInfo, setBackendInfo] = useState<RagBackendInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, c, b] = await Promise.all([
        existingStats ? Promise.resolve(existingStats) : getRagStats().catch(() => null),
        getRagCacheStats().catch(() => null),
        getRagBackendInfo().catch(() => null),
      ]);
      if (!existingStats) setStats(s);
      setCacheStats(c);
      setBackendInfo(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [existingStats]);

  useEffect(() => {
    // Only load if existingStats wasn't provided
    if (!existingStats) {
      load();
    } else {
      setStats(existingStats);
      // Still fetch cache stats separately
      getRagCacheStats()
        .then(setCacheStats)
        .catch(() => {})
        .finally(() => setLoading(false));
      getRagBackendInfo()
        .then(setBackendInfo)
        .catch(() => {});
    }
  }, [load, existingStats]);

  const handleClearCache = async () => {
    setClearing(true);
    try {
      await clearRagCache();
      // Re-fetch cache stats
      const c = await getRagCacheStats();
      setCacheStats(c);
    } catch (e) {
      console.error("Failed to clear cache:", e);
    } finally {
      setClearing(false);
    }
  };

  const isLightRag = stats?.backend === "lightrag" || backendInfo?.backend === "lightrag";
  const cacheActive = cacheStats?.cache_active ?? false;
  const hitRate = cacheStats?.hit_rate ?? 0;
  const latencyMs = stats?.avg_query_ms ?? 0;
  const queriesRun = stats?.queries_run ?? 0;
  const chunks = stats?.chunks ?? 0;
  const filesIndexed = stats?.files_indexed ?? 0;
  const totalErrors = (stats?.insert_errors ?? 0) + (stats?.query_errors ?? 0);

  // ── Loading skeleton ──
  if (loading && !stats && !cacheStats) {
    return (
      <div className="card p-5 animate-pulse space-y-4">
        <div className="flex items-center justify-between">
          <div className="h-5 w-36 bg-forge-elevated rounded" />
          <div className="h-4 w-16 bg-forge-elevated rounded" />
        </div>
        <div className="flex items-center justify-center py-4">
          <div className="w-[72px] h-[72px] bg-forge-elevated rounded-full" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-5 bg-forge-elevated rounded" />
          ))}
        </div>
      </div>
    );
  }

  // ── Empty / not available ──
  if (!loading && !isLightRag) {
    return (
      <div className="card p-5 text-center">
        <div className="flex items-center justify-center mb-3">
          <div className="p-2.5 rounded-xl bg-forge-elevated">
            <Database size={18} className="text-text-muted" />
          </div>
        </div>
        <h3 className="text-sm font-semibold text-text-primary mb-1">
          LightRAG Backend Inactive
        </h3>
        <p className="text-xs text-text-muted leading-relaxed mb-3">
          Set <code className="text-forge-primary text-[10px]">FORGEAI_RAG_BACKEND=lightrag</code>{" "}
          to enable graph + vector hybrid RAG with query caching.
        </p>
        <p className="text-[10px] text-text-muted/60">
          Current backend: <span className="font-mono text-text-muted">{backendInfo?.backend || "chroma"}</span>
        </p>
      </div>
    );
  }

  // ── Render ──
  return (
    <div className="card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-forge-primary/10">
            <Database size={15} className="text-forge-primary" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary">LightRAG Metrics</h3>
        </div>
        <div className="flex items-center gap-2">
          {/* Backend status badge */}
          <span
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider",
              isLightRag ? "bg-success/10 text-success" : "bg-forge-elevated text-text-muted"
            )}
          >
            <span className={cn("w-1.5 h-1.5 rounded-full", isLightRag ? "bg-success" : "bg-text-muted")} />
            {isLightRag ? "LightRAG" : "ChromaDB"}
          </span>
          <button
            onClick={load}
            disabled={loading}
            className="btn-ghost p-1.5 rounded-md text-text-muted hover:text-text-primary transition-colors"
            title="Refresh metrics"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2 rounded-lg bg-error/5 border border-error/10">
          <p className="text-[10px] text-error flex items-center gap-1">
            <AlertTriangle size={11} />
            {error}
          </p>
        </div>
      )}

      {/* ── Cache Hit Rate Gauge ── */}
      <div className="flex items-center justify-center py-2 mb-4">
        <div className="text-center">
          <HitRateGauge rate={cacheActive ? hitRate : 0} />
          <p className="text-[9px] text-text-muted mt-1 uppercase tracking-wider">
            Cache Hit Rate
          </p>
          {cacheActive && (
            <p className="text-[9px] text-text-muted/60 mt-0.5">
              {formatNumber(cacheStats?.size ?? 0)} / {formatNumber(cacheStats?.maxsize ?? 256)} entries
            </p>
          )}
        </div>
      </div>

      {/* ── Stat Items ── */}
      <div className="space-y-3 mb-3">
        {/* Latency */}
        <LatencyBar avgMs={latencyMs} />

        {/* Queries Run */}
        <StatItem
          label="Queries Run"
          value={formatNumber(queriesRun)}
          icon={Search}
          color="text-forge-primary"
        />

        {/* Chunks Inserted */}
        <StatItem
          label="Chunks Inserted"
          value={formatNumber(chunks)}
          icon={Layers}
          color="text-cyan-400"
          subtitle={filesIndexed > 0 ? `${formatNumber(filesIndexed)} files indexed` : undefined}
        />

        {/* Cache Hits/Misses */}
        {cacheActive && (
          <StatItem
            label="Cache Hits / Misses"
            value={`${formatNumber(cacheStats?.hits ?? 0)} / ${formatNumber(cacheStats?.misses ?? 0)}`}
            icon={Zap}
            color="text-success"
            subtitle={`Cache TTL: ${(cacheStats?.ttl ?? 300) / 60}m`}
          />
        )}

        {/* Error count */}
        {totalErrors > 0 && (
          <StatItem
            label="Total Errors"
            value={formatNumber(totalErrors)}
            icon={AlertTriangle}
            color="text-warning"
            subtitle={`${formatNumber(stats?.insert_errors ?? 0)} insert / ${formatNumber(stats?.query_errors ?? 0)} query`}
          />
        )}
      </div>

      {/* ── Action Buttons ── */}
      {cacheActive && (
        <div className="flex items-center gap-2 pt-3 border-t border-forge-border">
          <button
            onClick={handleClearCache}
            disabled={clearing}
            className="btn-ghost text-[10px] gap-1.5 py-1.5 px-3 rounded-lg hover:bg-error/10 hover:text-error transition-colors flex items-center"
          >
            <Trash2 size={11} className={clearing ? "animate-spin" : ""} />
            {clearing ? "Clearing..." : "Clear Cache"}
          </button>
          <span className="text-[9px] text-text-muted/60">
            {cacheStats?.ttl ? `Auto-evicts after ${cacheStats.ttl / 60}m` : ""}
          </span>
        </div>
      )}

      {/* ── Embedding model info ── */}
      {stats?.embedding_model && (
        <div className="flex items-center justify-between pt-2 mt-2 border-t border-forge-border/50">
          <span className="text-[9px] text-text-muted/60">Embedding Model</span>
          <span className="text-[9px] font-mono text-text-muted truncate max-w-[160px]" title={stats.embedding_model}>
            {stats.embedding_model.split("/").pop() || stats.embedding_model}
          </span>
        </div>
      )}

      {/* ── DB path ── */}
      {stats?.db_path && (
        <div className="flex items-center justify-between pt-1">
          <span className="text-[9px] text-text-muted/60">Working Dir</span>
          <span className="text-[9px] font-mono text-text-muted/60 truncate max-w-[180px]" title={stats.db_path}>
            {stats.db_path}
          </span>
        </div>
      )}
    </div>
  );
}
