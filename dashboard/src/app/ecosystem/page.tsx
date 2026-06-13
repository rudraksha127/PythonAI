"use client";

import { useEffect, useState, useCallback } from "react";
import { getEcosystemMetrics, type EcosystemFetchResponse } from "@/lib/api";
import {
  Server,
  Activity,
  TrendingUp,
  Brain,
  Zap,
  RefreshCw,
  BarChart3,
  Cpu,
  Clock,
  Database as DbIcon,
  XCircle,
  Wifi,
  WifiOff,
  Gauge,
  ChevronDown,
  ChevronUp,
  Layers,
  Bot,
  Monitor,
  Globe,
  Terminal,
} from "lucide-react";
import { cn, formatNumber, formatTimeAgo } from "@/lib/utils";
import LiveEventFeed from "@/components/LiveEventFeed";
import ArchitectureFlow from "@/components/ArchitectureFlow";

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

interface ServiceInfo {
  name: string;
  description: string;
  port: number;
  url: string;
  icon: React.ElementType;
  healthEndpoint?: string;
}

interface ServiceStatus {
  online: boolean;
  latency: number | null;
  lastChecked: number | null;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════
// Service Registry — all ecosystem services with their endpoints
// ═══════════════════════════════════════════════════════════════════

const SERVICES: ServiceInfo[] = [
  {
    name: "PythonAI",
    description: "Core engine — capture, RAG, training, inference",
    port: 7337,
    url: "http://localhost:7337",
    icon: Cpu,
    healthEndpoint: "http://localhost:7337/health",
  },
  {
    name: "ForgeAI Gateway",
    description: "Unified entry point for all ecosystem services",
    port: 8000,
    url: "http://localhost:8000",
    icon: Globe,
    healthEndpoint: "http://localhost:8000/health",
  },
  {
    name: "Rudra-bots",
    description: "Chat dashboard with ForgeAI metrics integration",
    port: 7000,
    url: "http://localhost:7000",
    icon: Bot,
    healthEndpoint: "http://localhost:7000/api/health",
  },
  {
    name: "Next.js Dashboard",
    description: "Training pipeline, SEAL, acceptance charts (this page)",
    port: 3000,
    url: "http://localhost:3000",
    icon: Monitor,
    healthEndpoint: undefined, // self — always online
  },
  {
    name: "Hermes Agent",
    description: "Multi-agent orchestrator (Python 3.12 venv)",
    port: -1,
    url: "",
    icon: Brain,
    healthEndpoint: "http://localhost:8642/health",
  },
  {
    name: "Open-Claude CLI",
    description: "Terminal AI assistant — Claude Code fork",
    port: -1,
    url: "",
    icon: Terminal,
    healthEndpoint: undefined, // CLI tool, no HTTP
  },
  {
    name: "Hermes Studio",
    description: "Hermes web UI — React/TanStack Router",
    port: 3002,
    url: "http://localhost:3002",
    icon: Layers,
    healthEndpoint: "http://localhost:3002/health",
  },
  {
    name: "Claude Code npm",
    description: "CLI tool — Claude Code via npm package",
    port: -1,
    url: "",
    icon: Terminal,
    healthEndpoint: undefined,
  },
  {
    name: "Superview-sh",
    description: "Competitor intelligence — Claude Code skills & templates",
    port: -1,
    url: "",
    icon: Activity,
    healthEndpoint: undefined, // git repo, no HTTP
  },
];

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

/** Ping a service endpoint with a short timeout. Returns null on failure. */
async function pingService(url: string): Promise<{ ok: boolean; ms: number } | null> {
  const start = performance.now();
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    const ms = Math.round(performance.now() - start);
    return { ok: res.ok, ms };
  } catch {
    return null;
  }
}

const STATUS_COLORS: Record<string, string> = {
  "forge-primary": "text-forge-primary",
  cyan: "text-cyan-400",
  yellow: "text-yellow-400",
  green: "text-green-400",
  error: "text-error",
};

// ═══════════════════════════════════════════════════════════════════
// Components
// ═══════════════════════════════════════════════════════════════════

function SummaryBar({
  healthy,
  total,
}: {
  healthy: number;
  total: number;
}) {
  const pct = total > 0 ? Math.round((healthy / total) * 100) : 0;
  const isAll = healthy === total;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary">Service Health</span>
        </div>
        <span className="text-xs font-mono text-text-muted">
          {healthy}/{total} online
        </span>
      </div>
      <div className="h-2 bg-forge-elevated rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-700 ease-out",
            isAll ? "bg-success" : pct > 50 ? "bg-forge-primary" : "bg-error"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[11px] text-text-muted mt-2">
        {isAll
          ? "All services are online and healthy."
          : `${total - healthy} service${total - healthy > 1 ? "s" : ""} unreachable.`}
      </p>
    </div>
  );
}

function ServiceCard({
  service,
  status,
  onPing,
  pinging,
}: {
  service: ServiceInfo;
  status: ServiceStatus | null;
  onPing: () => void;
  pinging: boolean;
}) {
  const Icon = service.icon;
  const isOnline = status?.online ?? false;
  const ms = status?.latency;
  const error = status?.error;
  const lastChecked = status?.lastChecked;

  return (
    <div
      className={cn(
        "card p-5 transition-all duration-300",
        isOnline && "ring-1 ring-success/20",
        status && !isOnline && "ring-1 ring-error/10"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "p-2 rounded-lg transition-colors duration-300",
              isOnline ? "bg-success/10" : "bg-forge-elevated"
            )}
          >
            <Icon
              size={16}
              className={cn(
                "transition-colors duration-300",
                isOnline ? "text-success" : "text-text-muted"
              )}
            />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{service.name}</h3>
            <p className="text-[11px] text-text-muted leading-tight mt-0.5">
              {service.description}
            </p>
          </div>
        </div>

        {/* Status dot */}
        <div className="flex items-center gap-1.5">
          {status === null && !pinging ? (
            <button
              onClick={onPing}
              className="btn-ghost p-1.5 rounded-md text-text-muted hover:text-text-primary"
              title="Ping service"
            >
              <RefreshCw size={12} />
            </button>
          ) : pinging ? (
            <RefreshCw size={14} className="animate-spin text-text-muted" />
          ) : isOnline ? (
            <Wifi size={14} className="text-success" />
          ) : (
            <WifiOff size={14} className="text-error" />
          )}
        </div>
      </div>

      {/* Status details */}
      <div className="flex items-center gap-4 text-[11px]">
        {status && (
          <>
            {/* Online/Offline */}
            <span className="flex items-center gap-1">
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  isOnline ? "bg-success animate-pulse" : "bg-error"
                )}
              />
              <span className="font-medium text-text-secondary">
                {isOnline ? "Online" : error ?? "Offline"}
              </span>
            </span>

            {/* Latency */}
            {ms !== null && (
              <span className="flex items-center gap-1 text-text-muted">
                <Gauge size={10} />
                <span>
                  {ms}
                  <span className="text-[10px]">ms</span>
                </span>
              </span>
            )}
          </>
        )}

        {/* Port */}
        {service.port > 0 && (
          <span className="font-mono text-text-muted">: {service.port}</span>
        )}

        {/* Empty state — click to ping */}
        {!status && !pinging && (
          <span className="text-text-muted">Click refresh to check</span>
        )}
      </div>

      {/* Last checked */}
      {lastChecked && (
        <p className="text-[10px] text-text-muted mt-2">
          Last checked {formatTimeAgo(lastChecked)}
        </p>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  icon: Icon,
  color,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
  subtitle?: string;
}) {
  const textColor = STATUS_COLORS[color] || "text-text-muted";
  return (
    <div className="card p-4 text-center hover:bg-forge-elevated/50 transition-colors">
      <Icon size={20} className={cn("mx-auto mb-2", textColor)} />
      <div className="text-xl font-bold font-mono text-text-primary">{value}</div>
      <div className="text-[10px] text-text-muted uppercase tracking-wider mt-1">{label}</div>
      {subtitle && (
        <div className="text-[10px] text-text-muted/60 mt-0.5">{subtitle}</div>
      )}
    </div>
  );
}

function DistributionBar({
  label,
  value,
  total,
  color = "forge-primary",
}: {
  label: string;
  value: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-text-secondary capitalize">
          {label.replace(/_/g, " ")}
        </span>
        <span className="text-xs font-mono text-text-muted">
          {formatNumber(value)} ({pct.toFixed(0)}%)
        </span>
      </div>
      <div className="h-1.5 bg-forge-elevated rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            color === "success" ? "bg-success/60" : "bg-forge-primary/60"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════════════

export default function EcosystemPage() {
  // PythonAI metrics
  const [metrics, setMetrics] = useState<EcosystemFetchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Service pinging
  const [serviceStatuses, setServiceStatuses] = useState<Record<string, ServiceStatus>>({});
  const [pinging, setPinging] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Expandable sections
  const [showMetrics, setShowMetrics] = useState(true);
  const [showDistribution, setShowDistribution] = useState(true);

  // ── Load PythonAI metrics ──────────────────────────────────────

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getEcosystemMetrics();
      setMetrics(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch ecosystem data");
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Ping all services ──────────────────────────────────────────

  const pingAll = useCallback(async () => {
    setPinging(true);
    const results: Record<string, ServiceStatus> = {};

    // Ping services in parallel (up to 6 at a time)
    const chunks: ServiceInfo[][] = [];
    for (let i = 0; i < SERVICES.length; i += 6) {
      chunks.push(SERVICES.slice(i, i + 6));
    }

    for (const chunk of chunks) {
      const pings = chunk.map(async (svc) => {
        if (!svc.healthEndpoint) {
          // CLI tools with no HTTP — mark as "N/A"
          results[svc.name] = {
            online: true,
            latency: null,
            lastChecked: Date.now() / 1000,
          };
          return;
        }
        const ping = await pingService(svc.healthEndpoint);
        if (ping) {
          results[svc.name] = {
            online: ping.ok,
            latency: ping.ms,
            lastChecked: Date.now() / 1000,
          };
        } else {
          results[svc.name] = {
            online: false,
            latency: null,
            lastChecked: Date.now() / 1000,
            error: "Unreachable",
          };
        }
      });
      await Promise.all(pings);
    }

    // Dashboard is always online (it's this page)
    results["Next.js Dashboard"] = {
      online: true,
      latency: 0,
      lastChecked: Date.now() / 1000,
    };

    setServiceStatuses(results);
    setPinging(false);
  }, []);

  // ── Initial load ───────────────────────────────────────────────

  useEffect(() => {
    load();
    pingAll();
  }, [load, pingAll]);

  // ── Auto-refresh ───────────────────────────────────────────────

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      load();
      pingAll();
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, load, pingAll]);

  // ── Derived state ──────────────────────────────────────────────

  const data = metrics?.data;
  const pythonaiOk = data?.server?.status === "ok";

  const healthyCount = Object.values(serviceStatuses).filter((s) => s.online).length;
  const totalServices = SERVICES.length;

  const totalSignals = data?.statistics?.signals_by_type
    ? Object.values(data.statistics.signals_by_type).reduce((a, b) => a + b, 0)
    : 0;

  const signalsByLang = data?.statistics?.signals_by_language ?? {};
  const signalDistribution = data?.signal_distribution ?? [];

  // ── Loading skeleton ───────────────────────────────────────────

  if (loading && !metrics) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-64 bg-forge-elevated rounded-lg" />
          <div className="h-4 w-80 bg-forge-elevated rounded" />
        </div>
        <div className="h-20 bg-forge-elevated rounded-lg" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="card p-5 space-y-3">
              <div className="h-4 w-24 bg-forge-elevated rounded" />
              <div className="h-3 w-32 bg-forge-elevated rounded" />
              <div className="h-3 w-20 bg-forge-elevated rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="space-y-8">
      {/* ═══ Header ═══ */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <Server size={22} className="text-forge-primary" />
            Ecosystem Status
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Live health monitoring for all ForgeAI services — auto-refreshes every 30s
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={cn(
              "btn-ghost text-xs gap-1.5 px-3 py-2 rounded-lg transition-all",
              autoRefresh ? "text-forge-primary" : "text-text-muted"
            )}
          >
            <Activity size={14} />
            {autoRefresh ? "Auto On" : "Auto Off"}
          </button>
          <button
            onClick={() => {
              load();
              pingAll();
            }}
            disabled={loading || pinging}
            className="btn-secondary text-xs gap-1.5"
          >
            <RefreshCw size={14} className={loading || pinging ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ═══ Error banner ═══ */}
      {error && (
        <div className="card p-4 border border-error/20 bg-error/5">
          <p className="text-sm text-error flex items-center gap-2">
            <XCircle size={16} />
            {error}
          </p>
        </div>
      )}

      {/* ═══ Cached indicator ═══ */}
      {metrics?.cached && (
        <div className="card p-3 border border-warning/20 bg-warning/5">
          <p className="text-xs text-warning flex items-center gap-2">
            <DbIcon size={14} />
            Showing cached data — PythonAI server is not reachable on port 7337
          </p>
        </div>
      )}

      {/* ═══ Architecture Overview ═══ */}
      <ArchitectureFlow serviceStatuses={serviceStatuses} />

      {/* ═══ Summary Bar ═══ */}
      <SummaryBar healthy={healthyCount} total={totalServices} />

      {/* ═══ Services Grid ═══ */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
          <Server size={16} className="text-forge-primary" />
          Services
          <span className="text-[11px] font-normal text-text-muted ml-1">
            ({healthyCount}/{totalServices} online)
          </span>
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {SERVICES.map((svc) => (
            <ServiceCard
              key={svc.name}
              service={svc}
              status={serviceStatuses[svc.name] ?? null}
              onPing={() => {
                // Single-service ping
                if (!svc.healthEndpoint) return;
                pingService(svc.healthEndpoint).then((ping) => {
                  setServiceStatuses((prev) => ({
                    ...prev,
                    [svc.name]: ping
                      ? { online: ping.ok, latency: ping.ms, lastChecked: Date.now() / 1000 }
                      : { online: false, latency: null, lastChecked: Date.now() / 1000, error: "Unreachable" },
                  }));
                });
              }}
              pinging={false}
            />
          ))}
        </div>
      </div>

      {/* ═══ PythonAI Live Metrics ═══ */}
      {data && (
        <>
          {/* ── Quick Stats ── */}
          <div>
            <button
              onClick={() => setShowMetrics(!showMetrics)}
              className="w-full flex items-center justify-between text-sm font-semibold text-text-primary mb-3"
            >
              <span className="flex items-center gap-2">
                <Activity size={16} className="text-forge-primary" />
                PythonAI Live Metrics
              </span>
              {showMetrics ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showMetrics && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatTile
                  label="Acceptance Rate"
                  value={`${data.statistics.overall_acceptance_rate.toFixed(1)}%`}
                  icon={TrendingUp}
                  color="forge-primary"
                  subtitle="Last 7 days"
                />
                <StatTile
                  label="Total Signals"
                  value={formatNumber(totalSignals)}
                  icon={BarChart3}
                  color="cyan"
                  subtitle="All time"
                />
                <StatTile
                  label="Training Runs"
                  value={formatNumber(data.training.history.length)}
                  icon={Brain}
                  color="yellow"
                  subtitle="Completed"
                />
                <StatTile
                  label="Sessions"
                  value={formatNumber(data.statistics.total_sessions)}
                  icon={Zap}
                  color="green"
                  subtitle="Recorded"
                />
              </div>
            )}
          </div>

          {/* ── Signal & Language Distribution ── */}
          <div>
            <button
              onClick={() => setShowDistribution(!showDistribution)}
              className="w-full flex items-center justify-between text-sm font-semibold text-text-primary mb-3"
            >
              <span className="flex items-center gap-2">
                <BarChart3 size={16} className="text-forge-primary" />
                Signal & Language Distribution
              </span>
              {showDistribution ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showDistribution && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Signal types */}
                <div className="card p-5">
                  <h4 className="text-xs font-semibold text-text-primary mb-4 uppercase tracking-wider">
                    By Signal Type
                  </h4>
                  {signalDistribution.length > 0 ? (
                    <div className="space-y-3">
                      {signalDistribution.map((s) => (
                        <DistributionBar
                          key={s.name}
                          label={s.name}
                          value={s.value}
                          total={totalSignals}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted text-center py-4">
                      No signals captured yet
                    </p>
                  )}
                </div>

                {/* Language distribution */}
                <div className="card p-5">
                  <h4 className="text-xs font-semibold text-text-primary mb-4 uppercase tracking-wider">
                    By Language
                  </h4>
                  {Object.keys(signalsByLang).length > 0 ? (
                    <div className="space-y-3">
                      {Object.entries(signalsByLang)
                        .sort(([, a], [, b]) => (b as number) - (a as number))
                        .map(([lang, count]) => (
                          <DistributionBar
                            key={lang}
                            label={lang}
                            value={count as number}
                            total={totalSignals}
                            color="success"
                          />
                        ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted text-center py-4">
                      No language data yet
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── Training Schedule ── */}
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              <Clock size={16} className="text-forge-primary" />
              Training Schedule
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">
                  Enabled
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full",
                      data.training.schedule.enabled ? "bg-success" : "bg-text-muted"
                    )}
                  />
                  <span className="text-sm font-mono text-text-primary">
                    {data.training.schedule.enabled ? "Yes" : "No"}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">
                  Schedule
                </div>
                <div className="text-sm font-mono text-text-primary">
                  {data.training.schedule.description}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">
                  Total Runs
                </div>
                <div className="text-sm font-mono text-text-primary">
                  {data.training.schedule.total_runs}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">
                  Next Run
                </div>
                <div className="text-sm font-mono text-text-primary">
                  {data.training.schedule.next_run
                    ? new Date(data.training.schedule.next_run).toLocaleDateString()
                    : "N/A"}
                </div>
              </div>
            </div>
          </div>

          {/* ═══ Real-Time Events: Sync Daemon + Live Feed ═══ */}
          {data.sync_daemon && (
            <LiveEventFeed
              syncInfo={{
                running: data.sync_daemon.running,
                lastSyncTime: data.sync_daemon.last_sync_time,
                totalSyncs: data.sync_daemon.total_syncs,
                failCount: data.sync_daemon.fail_count,
                consecutiveFails: data.sync_daemon.consecutive_fails,
                lastSyncResult: data.sync_daemon.last_sync_result,
                startedAt: data.sync_daemon.started_at,
                interval: data.sync_daemon.interval,
              }}
            />
          )}

          {/* ── System Status ── */}
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server size={14} className="text-text-muted" />
                <span className="text-xs font-medium text-text-muted">System Health</span>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      data.server.inference_connected ? "bg-success" : "bg-error"
                    )}
                  />
                  Inference
                </span>
                <span className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      data.server.db_ok ? "bg-success" : "bg-error"
                    )}
                  />
                  Database
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-forge-primary animate-pulse" />
                  v{data.version}
                </span>
              </div>
            </div>
          </div>

          {/* ── Last refreshed ── */}
          <p className="text-[10px] text-text-muted text-center">
            Last updated {new Date(data.timestamp * 1000).toLocaleTimeString()}
            {metrics?.cached ? " (cached)" : ""}
          </p>
        </>
      )}

      {/* ═══ Not connected ═══ */}
      {!data && !loading && (
        <div className="card p-12 text-center">
          <Server size={40} className="mx-auto text-text-muted mb-4" />
          <h3 className="text-base font-medium text-text-primary mb-2">
            PythonAI Server Not Reachable
          </h3>
          <p className="text-sm text-text-muted mb-6 max-w-md mx-auto">
            Start the PythonAI API server on port 7337 to see live ecosystem metrics.
            Services are still being pinged for connectivity status.
          </p>
          <div className="flex items-center justify-center gap-3">
            <button onClick={() => { load(); pingAll(); }} className="btn-primary text-sm">
              <RefreshCw size={14} className="mr-1.5 inline" />
              Retry Connection
            </button>
            <span className="text-xs text-text-muted">
              {healthyCount}/{totalServices} services online
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
