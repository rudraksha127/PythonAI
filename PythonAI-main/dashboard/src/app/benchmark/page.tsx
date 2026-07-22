"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getBenchmarkReports,
  getBenchmarkReport,
  type BenchmarkReportListItem,
  type BenchmarkReportResponse,
} from "@/lib/api";
import type { BenchmarkReport } from "@/lib/types";
import { cn, formatNumber, formatTimeAgo } from "@/lib/utils";
import {
  BarChart3,
  TrendingUp,
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Trash2,
  Clock,
  Zap,
  Cpu,
  Database,
  FileText,
  Download,
  Search,
  Gauge,
  XCircle,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// Color helpers
// ═══════════════════════════════════════════════════════════════════

function latencyColor(ms: number): string {
  if (ms < 1000) return "text-success";
  if (ms < 3000) return "text-forge-primary";
  if (ms < 8000) return "text-warning";
  return "text-error";
}

function latencyBg(ms: number): string {
  if (ms < 1000) return "bg-success/10";
  if (ms < 3000) return "bg-forge-primary/10";
  if (ms < 8000) return "bg-warning/10";
  return "bg-error/10";
}

function ratioColor(ratio: number): string {
  if (ratio >= 2) return "text-success";
  if (ratio >= 1.3) return "text-forge-primary";
  if (ratio >= 1) return "text-warning";
  return "text-error";
}

// ═══════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════

function StatCard({
  title,
  value,
  icon: Icon,
  color = "text-text-muted",
  subtitle,
}: {
  title: string;
  value: string;
  icon: React.ElementType;
  color?: string;
  subtitle?: string;
}) {
  return (
    <div className="card p-4 hover:bg-forge-elevated/50 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={color} />
        <span className="text-[10px] text-text-muted uppercase tracking-wider">{title}</span>
      </div>
      <div className={cn("text-lg font-bold font-mono", color)}>{value}</div>
      {subtitle && <p className="text-[10px] text-text-muted/70 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function BackendComparisonTable({ stats }: { stats: BenchmarkReport["stats"] }) {
  const entries = Object.entries(stats).sort(([, a], [, b]) => a.avg_total_ms - b.avg_total_ms);
  if (entries.length === 0) return null;

  const bestLatency = entries[0][1].avg_total_ms;

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-forge-border">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <BarChart3 size={14} className="text-forge-primary" />
          Backend Latency Comparison
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border">
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Backend</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Avg (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">P50 (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">P95 (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Min (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Max (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Chars</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Speedup</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-forge-border">
            {entries.map(([name, s]) => {
              const speedup = bestLatency > 0 && s.avg_total_ms > 0
                ? (s.avg_total_ms / bestLatency).toFixed(1)
                : "—";
              return (
                <tr key={name} className="hover:bg-forge-elevated/30 transition-colors">
                  <td className="px-6 py-3">
                    <span className={cn("font-medium text-xs font-mono",
                      name.toLowerCase().includes("chroma") ? "text-forge-primary" : "text-cyan-400"
                    )}>
                      {name.split("(")[0].trim()}
                    </span>
                    <span className="text-[10px] text-text-muted ml-2">
                      {name.includes("(") ? name.split("(")[1].replace(")", "") : ""}
                    </span>
                  </td>
                  <td className={cn("px-4 py-3 text-right font-mono text-xs font-semibold", latencyColor(s.avg_total_ms))}>
                    {s.avg_total_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-primary">
                    {s.p50_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-secondary">
                    {s.p95_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {s.min_total_ms.toFixed(0) || "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {s.max_total_ms.toFixed(0) || "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {s.avg_answer_len.toFixed(0)}
                  </td>
                  <td className={cn("px-4 py-3 text-right font-mono text-xs font-semibold", ratioColor(parseFloat(speedup)))}>
                    {speedup !== "—" ? `${speedup}x` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn(
                      "text-xs font-mono",
                      s.errors > 0 ? "text-error" : "text-text-muted"
                    )}>
                      {s.errors}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LatencyBarChart({ details }: { details: BenchmarkReport["details"] }) {
  if (details.length === 0) return null;

  // Group by backend
  const grouped: Record<string, { avg: number; count: number; color: string }> = {};
  for (const d of details) {
    if (d.error) continue;
    const key = d.mode === "cache" ? `${d.backend} (cached)` : d.backend;
    if (!grouped[key]) {
      grouped[key] = { avg: 0, count: 0, color: key.includes("chroma") ? "#5B5BFF" : "#22C55E" };
    }
    grouped[key].avg += d.total_ms;
    grouped[key].count += 1;
  }
  for (const key of Object.keys(grouped)) {
    grouped[key].avg = grouped[key].count > 0 ? grouped[key].avg / grouped[key].count : 0;
  }

  const maxAvg = Math.max(...Object.values(grouped).map((g) => g.avg), 1);

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Activity size={14} className="text-forge-primary" />
        Avg Latency by Backend
      </h3>
      <div className="space-y-3">
        {Object.entries(grouped)
          .sort(([, a], [, b]) => a.avg - b.avg)
          .map(([name, g]) => (
            <div key={name}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-text-secondary font-mono">{name}</span>
                <span className={cn("text-xs font-mono font-semibold", latencyColor(g.avg))}>
                  {g.avg.toFixed(0)} ms
                </span>
              </div>
              <div className="h-3 bg-forge-elevated rounded-full overflow-hidden flex">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${(g.avg / maxAvg) * 100}%`,
                    backgroundColor: g.color,
                    opacity: g.avg / maxAvg > 0.15 ? 0.8 : 0.6,
                  }}
                />
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

function ComparisonRatios({ comparisons }: { comparisons: Record<string, number> }) {
  const entries = Object.entries(comparisons).filter(([, v]) => v > 0);
  if (entries.length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Gauge size={14} className="text-forge-primary" />
        Key Speedup Ratios
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {entries.map(([key, val]) => {
          const labels: Record<string, string> = {
            lightrag_vs_chromadb: "LightRAG hybrid vs ChromaDB",
            naive_vs_chromadb: "LightRAG naive vs ChromaDB",
            cache_vs_cold: "Cache hit vs cold query",
            hybrid_vs_naive: "Hybrid vs naive mode",
          };
          const label = labels[key] || key.replace(/_/g, " ");
          const isFaster = val > 1;
          return (
            <div
              key={key}
              className={cn(
                "p-3 rounded-lg border transition-colors",
                isFaster ? "bg-success/5 border-success/20" : "bg-forge-elevated border-forge-border"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-text-muted uppercase tracking-wider">{label}</span>
                <span className={cn("text-lg font-bold font-mono", ratioColor(val))}>
                  {val.toFixed(1)}x
                </span>
              </div>
              <p className="text-[10px] text-text-muted/70 mt-1">
                {isFaster
                  ? `${label.split(" vs ")[0] || "First"} is ${val.toFixed(1)}x faster`
                  : `${label.split(" vs ")[1] || "Second"} is ${(1 / val).toFixed(1)}x faster`}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DetailRow({ detail }: { detail: BenchmarkReport["details"][0] }) {
  const [expanded, setExpanded] = useState(false);
  const isCache = detail.mode === "cache";
  return (
    <div className="border-b border-forge-border last:border-b-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-forge-elevated/30 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn(
              "text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded",
              detail.backend.includes("lightrag") ? "bg-success/10 text-success" : "bg-forge-primary/10 text-forge-primary"
            )}>
              {detail.backend.replace("lightrag-", "LR-")}
            </span>
            {isCache && (
              <span className="text-[9px] text-warning bg-warning/10 px-1 py-0.5 rounded font-semibold">CACHED</span>
            )}
            <span className="text-xs text-text-secondary truncate">{detail.query.slice(0, 50)}...</span>
          </div>
        </div>
        <span className={cn("text-xs font-mono font-semibold", latencyColor(detail.total_ms))}>
          {detail.total_ms.toFixed(0)}ms
        </span>
        {expanded ? <ChevronUp size={14} className="text-text-muted shrink-0" /> : <ChevronDown size={14} className="text-text-muted shrink-0" />}
      </button>
      {expanded && (
        <div className="px-4 pb-3 space-y-1.5">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <span className="text-[9px] text-text-muted block">Query</span>
              <span className="text-[10px] text-text-primary font-mono">{detail.query}</span>
            </div>
            <div>
              <span className="text-[9px] text-text-muted block">Retrieval</span>
              <span className="text-[10px] font-mono text-text-primary">{detail.retrieval_ms.toFixed(0)}ms</span>
            </div>
            <div>
              <span className="text-[9px] text-text-muted block">Answer length</span>
              <span className="text-[10px] font-mono text-text-primary">{detail.answer_len} chars</span>
            </div>
          </div>
          {detail.error && (
            <div className="flex items-center gap-1.5 text-error">
              <XCircle size={11} />
              <span className="text-[10px]">{detail.error}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailList({ details }: { details: BenchmarkReport["details"] }) {
  if (details.length === 0) {
    return (
      <div className="card p-6 text-center">
        <p className="text-xs text-text-muted">No query details recorded.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-forge-border">
        <h3 className="text-xs font-semibold text-text-primary flex items-center gap-2">
          <Search size={12} className="text-forge-primary" />
          Per-Query Details
          <span className="text-[10px] font-normal text-text-muted">({details.length} queries)</span>
        </h3>
      </div>
      <div className="divide-y divide-forge-border">
        {details.map((d, i) => (
          <DetailRow key={i} detail={d} />
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Concurrent Throughput Components
// ═══════════════════════════════════════════════════════════════════

function QpsColor(qps: number, maxQps: number): string {
  const ratio = maxQps > 0 ? qps / maxQps : 0;
  if (ratio >= 0.8) return "text-success";
  if (ratio >= 0.5) return "text-forge-primary";
  if (ratio >= 0.3) return "text-warning";
  return "text-text-muted";
}

function QpsBarChart({ throughput }: { throughput: BenchmarkReport["throughput"] }) {
  if (!throughput || throughput.results.length === 0) return null;

  const maxQps = Math.max(...throughput.results.map((r) => r.qps), 0.1);
  const backendColors: Record<string, string> = {
    chroma: "#5B5BFF",
    "lightrag-hybrid": "#22C55E",
    "lightrag-naive": "#EAB308",
  };

  // Group by concurrency level
  const byConcurrency: Record<number, typeof throughput.results> = {};
  for (const r of throughput.results) {
    if (!byConcurrency[r.concurrency]) byConcurrency[r.concurrency] = [];
    byConcurrency[r.concurrency].push(r);
  }

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Activity size={14} className="text-forge-primary" />
        Throughput by Concurrency (QPS)
      </h3>
      <div className="space-y-5">
        {Object.entries(byConcurrency)
          .sort(([a], [b]) => Number(a) - Number(b))
          .map(([concurrency, results]) => (
            <div key={concurrency}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">
                  Concurrency = {concurrency}
                </span>
                <span className="text-[9px] text-text-muted/60">({results.length} backends)</span>
              </div>
              <div className="space-y-2">
                {results
                  .sort((a, b) => a.qps - b.qps)
                  .map((r) => (
                    <div key={`${r.backend}-${r.concurrency}`}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: backendColors[r.backend] || "#888" }}
                          />
                          <span className="text-xs font-mono text-text-secondary">
                            {r.backend === "lightrag-hybrid" ? "LightRAG" :
                             r.backend === "lightrag-naive" ? "L-Naive" :
                             r.backend.charAt(0).toUpperCase() + r.backend.slice(1)}
                          </span>
                        </div>
                        <span className={cn("text-xs font-mono font-semibold", QpsColor(r.qps, maxQps))}>
                          {r.qps.toFixed(1)} QPS
                        </span>
                      </div>
                      <div className="h-4 bg-forge-elevated rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${(r.qps / maxQps) * 100}%`,
                            backgroundColor: backendColors[r.backend] || "#888",
                            opacity: 0.75,
                          }}
                        />
                      </div>
                      <div className="flex justify-between text-[9px] text-text-muted/60 mt-0.5">
                        <span>{r.total_queries} queries</span>
                        <span>{r.wall_time_seconds.toFixed(1)}s wall</span>
                        <span>{r.avg_latency_ms.toFixed(0)}ms avg latency</span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

function ThroughputComparisonTable({ throughput }: { throughput: BenchmarkReport["throughput"] }) {
  if (!throughput || throughput.results.length === 0) return null;

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-forge-border">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Cpu size={14} className="text-forge-primary" />
          Concurrent Throughput Details
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-forge-border">
              <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Backend</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Conc</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">QPS</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Wall (s)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Avg Lat (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">P50 (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">P95 (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Min (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Max (ms)</th>
              <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-forge-border">
            {throughput.results
              .sort((a, b) => {
                if (a.backend !== b.backend) return a.backend.localeCompare(b.backend);
                return a.concurrency - b.concurrency;
              })
              .map((r, i) => (
                <tr key={i} className="hover:bg-forge-elevated/30 transition-colors">
                  <td className="px-6 py-3">
                    <span className={cn("text-xs font-mono font-medium",
                      r.backend.includes("lightrag") ? "text-cyan-400" : "text-forge-primary"
                    )}>
                      {r.backend === "lightrag-hybrid"
                        ? "LightRAG"
                        : r.backend === "lightrag-naive"
                        ? "L-Naive"
                        : r.backend.charAt(0).toUpperCase() + r.backend.slice(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-primary">
                    <span className="bg-forge-elevated px-1.5 py-0.5 rounded text-[10px]">
                      x{r.concurrency}
                    </span>
                  </td>
                  <td className={cn("px-4 py-3 text-right font-mono text-xs font-semibold", QpsColor(r.qps, throughput.best_qps))}>
                    {r.qps.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {r.wall_time_seconds.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs" style={{ color: r.avg_latency_ms < 3000 ? "var(--color-success)" : r.avg_latency_ms < 8000 ? "var(--color-warning)" : "var(--color-error)" }}>
                    {r.avg_latency_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-primary">
                    {r.p50_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-secondary">
                    {r.p95_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {r.min_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-muted">
                    {r.max_ms.toFixed(0)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn("text-xs font-mono", r.errors > 0 ? "text-error" : "text-text-muted")}>
                      {r.errors}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {throughput.best_qps > 0 && (
        <div className="px-6 py-3 border-t border-forge-border bg-success/5">
          <p className="text-[10px] text-text-muted">
            Best throughput: <span className="font-mono text-success font-semibold">{throughput.best_qps.toFixed(1)} QPS</span> —
            <span className="font-mono text-text-primary"> {throughput.best_backend === "lightrag-hybrid" ? "LightRAG" : throughput.best_backend.charAt(0).toUpperCase() + throughput.best_backend.slice(1)}</span>
            @ concurrency <span className="font-mono">x{throughput.best_concurrency}</span>
          </p>
        </div>
      )}
    </div>
  );
}

function ThroughputScalingSummary({ throughput }: { throughput: BenchmarkReport["throughput"] }) {
  if (!throughput || Object.keys(throughput.scaling).length === 0) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <TrendingUp size={14} className="text-forge-primary" />
        Throughput Scaling (QPS Ratio vs Sequential)
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {Object.entries(throughput.scaling).map(([backend, levels]) => {
          const label = backend === "lightrag-hybrid"
            ? "LightRAG"
            : backend === "lightrag-naive"
            ? "L-Naive"
            : "ChromaDB";
          const color = backend.includes("lightrag") ? "text-cyan-400" : "text-forge-primary";
          return (
            <div key={backend} className="p-3 rounded-lg bg-forge-elevated/50 border border-forge-border">
              <div className="flex items-center gap-1.5 mb-2">
                <span className={cn("text-xs font-semibold", color)}>{label}</span>
              </div>
              <div className="space-y-2">
                {Object.entries(levels).map(([cl, ratio]) => (
                  <div key={cl} className="flex items-center justify-between">
                    <span className="text-[10px] text-text-muted">Concurrency x{cl}</span>
                    <span className={cn("text-xs font-mono font-semibold", ratioColor(ratio))}>
                      {ratio.toFixed(2)}x
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[9px] text-text-muted/60 mt-3">
        Ratio &gt; 1 means queries scale sub-linearly (each additional worker adds &lt;100% throughput).
        Ratio = 2.0 means perfect linear scaling. Ratio &lt; 1 indicates contention.
      </p>
    </div>
  );
}

function CacheSummary({ report }: { report: BenchmarkReport }) {
  const cacheStats = report.cache_stats_from_adapter;
  const perMode = report.per_mode_queries;
  if (!cacheStats && !perMode) return null;

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <Zap size={14} className="text-warning" />
        LightRAG Cache & Mode Distribution
      </h3>
      {cacheStats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <StatCard title="Cache Hit Rate" value={`${cacheStats.hit_rate.toFixed(1)}%`} icon={Zap} color="text-warning" subtitle={`${cacheStats.hits} hits / ${cacheStats.misses} misses`} />
          <StatCard title="Cache Size" value={`${cacheStats.size} / ${cacheStats.maxsize}`} icon={Database} color="text-forge-primary" subtitle={`TTL: ${cacheStats.ttl}s`} />
          <StatCard title="Cache Hits" value={formatNumber(cacheStats.hits)} icon={TrendingUp} color="text-success" subtitle="Total cache hits" />
          <StatCard title="Cache Misses" value={formatNumber(cacheStats.misses)} icon={Activity} color="text-text-muted" subtitle="Total cache misses" />
        </div>
      )}
      {perMode && (
        <div>
          <h4 className="text-[10px] text-text-muted uppercase tracking-wider mb-2">Per-Mode Query Distribution</h4>
          <div className="grid grid-cols-4 gap-2">
            {Object.entries(perMode).map(([mode, count]) => {
              const total = Object.values(perMode).reduce((a, b) => a + b, 0);
              const pct = total > 0 ? (count as number / total) * 100 : 0;
              return (
                <div key={mode} className="text-center p-2 rounded-lg bg-forge-elevated/50">
                  <div className="text-xs font-mono font-semibold text-text-primary">{(count as number)}</div>
                  <div className="text-[9px] text-text-muted capitalize">{mode}</div>
                  <div className="h-1 mt-1 bg-forge-elevated rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-forge-primary/60" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════════════

export default function BenchmarkPage() {
  const [reports, setReports] = useState<BenchmarkReportListItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const [reportData, setReportData] = useState<BenchmarkReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getBenchmarkReports();
      if (result.success) {
        setReports(result.reports);
        // Auto-select first report
        if (result.reports.length > 0 && !selectedReport) {
          setSelectedReport(result.reports[0].filename);
        }
      } else {
        setError(result.error || "Failed to load reports");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, [selectedReport]);

  const loadReport = useCallback(async (filename: string) => {
    setLoadingReport(true);
    setError(null);
    try {
      const result = await getBenchmarkReport(filename);
      if (result.success && result.report) {
        setReportData(result.report);
      } else {
        setError(result.error || "Failed to load report");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to load report: ${e}`);
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  useEffect(() => {
    if (selectedReport) {
      loadReport(selectedReport);
    }
  }, [selectedReport, loadReport]);

  // ── Loading skeleton ──
  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-64 bg-forge-elevated rounded-lg" />
        <div className="h-4 w-96 bg-forge-elevated rounded" />
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card p-5 space-y-3"><div className="h-4 w-24 bg-forge-elevated rounded" /><div className="h-8 w-16 bg-forge-elevated rounded" /></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <BarChart3 size={22} className="text-forge-primary" />
            RAG Benchmark
          </h1>
          <p className="text-sm text-text-muted mt-1">
            LightRAG vs ChromaDB performance comparison from saved benchmark reports
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadReports} disabled={loading} className="btn-secondary text-xs gap-1.5">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="card p-3 border border-error/20 bg-error/5">
          <p className="text-xs text-error flex items-center gap-2"><XCircle size={14} />{error}</p>
        </div>
      )}

      {/* Reports list */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-text-muted mr-1">Reports:</span>
        {reports.length === 0 && !loading && (
          <span className="text-xs text-text-muted">No benchmark reports found. Run <code className="text-forge-primary">python benchmark_rag.py</code> to generate one.</span>
        )}
        {reports.map((r) => (
          <button
            key={r.filename}
            onClick={() => setSelectedReport(r.filename)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-mono transition-all",
              selectedReport === r.filename
                ? "bg-forge-primary/20 text-forge-primary border border-forge-primary/30"
                : "bg-forge-elevated text-text-muted hover:text-text-primary border border-transparent"
            )}
          >
            {r.filename.replace("rag_benchmark_", "").replace(".json", "")}
          </button>
        ))}
      </div>

      {/* Report content */}
      {loadingReport && (
        <div className="card p-8 text-center animate-pulse">
          <div className="h-6 w-48 bg-forge-elevated rounded mx-auto mb-3" />
          <div className="h-4 w-64 bg-forge-elevated rounded mx-auto" />
        </div>
      )}

      {reportData && !loadingReport && (
        <>
          {/* Timing summary */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
            <StatCard
              title="Seed Time"
              value={`${reportData.timing.seed_seconds.toFixed(1)}s`}
              icon={Database}
              color="text-forge-primary"
            />
            <StatCard
              title="Cold Queries"
              value={`${reportData.timing.cold_queries_seconds.toFixed(1)}s`}
              icon={Clock}
              color="text-cyan-400"
              subtitle={`${reportData.config.test_queries.length} queries`}
            />
            <StatCard
              title="Throughput"
              value={`${reportData.timing.concurrent_seconds?.toFixed(1) || "0.0"}s`}
              icon={Cpu}
              color="text-forge-primary"
              subtitle={`${reportData.throughput?.results?.length || 0} runs`}
            />
            <StatCard
              title="Cache Tests"
              value={`${reportData.timing.cache_queries_seconds.toFixed(1)}s`}
              icon={Zap}
              color="text-warning"
              subtitle={`${reportData.config.cache_test_queries.length} queries`}
            />
            <StatCard
              title="Total Duration"
              value={`${reportData.timing.total_seconds.toFixed(1)}s`}
              icon={Activity}
              color="text-text-primary"
            />
          </div>

          {/* Model info */}
          <div className="card p-3">
            <div className="flex items-center gap-4 text-xs text-text-muted">
              <span>Model: <span className="font-mono text-text-primary">{reportData.config.model}</span></span>
              <span>Embed: <span className="font-mono text-text-primary">{reportData.config.embed_model}</span></span>
              <span>Queries: <span className="font-mono text-text-primary">{reportData.config.num_queries}</span></span>
            </div>
          </div>

          {/* Key ratios */}
          {Object.keys(reportData.comparisons).length > 0 && (
            <ComparisonRatios comparisons={reportData.comparisons} />
          )}

          {/* Latency comparison table */}
          <BackendComparisonTable stats={reportData.stats} />

          {/* Latency bar chart */}
          <LatencyBarChart details={reportData.details} />

          {/* Cache & Mode stats */}
          <CacheSummary report={reportData} />

          {/* Concurrent Throughput sections */}
          {reportData.throughput && reportData.throughput.results.length > 0 && (
            <>
              <div className="border-t border-forge-border pt-4 mt-2">
                <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-4">
                  <Cpu size={14} className="text-forge-primary" />
                  Concurrent Throughput
                </h2>
              </div>

              {/* Scaling summary */}
              <ThroughputScalingSummary throughput={reportData.throughput} />

              {/* QPS bar chart */}
              <QpsBarChart throughput={reportData.throughput} />

              {/* Throughput detail table */}
              <ThroughputComparisonTable throughput={reportData.throughput} />
            </>
          )}

          {/* Per-query details */}
          <DetailList details={reportData.details} />

          {/* Timestamp */}
          <p className="text-[10px] text-text-muted text-center">
            Report generated {new Date(reportData.timestamp * 1000).toLocaleString()}
          </p>
        </>
      )}

      {!reportData && !loadingReport && !loading && reports.length === 0 && (
        <div className="card p-12 text-center">
          <BarChart3 size={40} className="mx-auto text-text-muted mb-4" />
          <h3 className="text-base font-medium text-text-primary mb-2">No Benchmark Data</h3>
          <p className="text-sm text-text-muted mb-6 max-w-md mx-auto">
            Run the benchmark suite from the PythonAI directory to generate comparison results.
          </p>
          <code className="text-xs bg-forge-elevated px-3 py-2 rounded-lg text-forge-primary">
            cd PythonAI && python benchmark_rag.py
          </code>
        </div>
      )}
    </div>
  );
}
