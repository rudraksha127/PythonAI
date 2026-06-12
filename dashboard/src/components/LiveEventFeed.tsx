"use client";

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Wifi,
  WifiOff,
  CheckCircle2,
  XCircle,
  Edit3,
  GitMerge,
  Clock,
  RefreshCw,
} from "lucide-react";
import { cn, formatTimeAgo } from "@/lib/utils";
import type { WsEventCaptured, WsSyncStatus } from "@/lib/types";

// ─── Types ──────────────────────────────────────────────────────

interface LiveEvent {
  id: string;
  type: "event_captured" | "sync_status";
  eventType?: string;
  status?: string;
  timestamp: number;
  signalId?: string;
  totalSyncs?: number;
}

interface SyncDaemonInfo {
  running: boolean;
  lastSyncTime: number | null;
  totalSyncs: number;
  failCount: number;
  consecutiveFails: number;
  lastSyncResult: string | null;
  startedAt: number | null;
  interval: number;
}

// ─── Helpers ────────────────────────────────────────────────────

const EVENT_ICONS: Record<string, React.ElementType> = {
  accept: CheckCircle2,
  reject: XCircle,
  edit: Edit3,
  pr_merge: GitMerge,
  test_pass: CheckCircle2,
  test_fail: XCircle,
};

const EVENT_COLORS: Record<string, string> = {
  accept: "text-success",
  reject: "text-error",
  edit: "text-warning",
  pr_merge: "text-cyan-400",
  test_pass: "text-success",
  test_fail: "text-error",
};

const EVENT_LABELS: Record<string, string> = {
  accept: "Accepted",
  reject: "Rejected",
  edit: "Edited",
  pr_merge: "PR Merged",
  test_pass: "Test Passed",
  test_fail: "Test Failed",
};

// ─── Sync Daemon Status Card ────────────────────────────────────

function SyncDaemonStatus({ info }: { info: SyncDaemonInfo | null }) {
  if (!info) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="h-4 w-32 bg-forge-elevated rounded mb-3" />
        <div className="space-y-2">
          <div className="h-3 w-48 bg-forge-elevated rounded" />
          <div className="h-3 w-40 bg-forge-elevated rounded" />
        </div>
      </div>
    );
  }

  const isHealthy = info.running && info.consecutiveFails < 5;
  const secondsSinceSync = info.lastSyncTime
    ? Math.floor((Date.now() / 1000 - info.lastSyncTime))
    : null;
  const uptimeSeconds = info.startedAt
    ? Math.floor(Date.now() / 1000 - info.startedAt)
    : null;

  return (
    <div
      className={cn(
        "card p-4 transition-all duration-300",
        isHealthy
          ? "ring-1 ring-success/20"
          : "ring-1 ring-warning/20"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              "p-1.5 rounded-lg",
              isHealthy ? "bg-success/10" : "bg-warning/10"
            )}
          >
            <Activity
              size={14}
              className={isHealthy ? "text-success" : "text-warning"}
            />
          </div>
          <span className="text-sm font-semibold text-text-primary">
            Auto-Sync Daemon
          </span>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider",
            isHealthy
              ? "bg-success/10 text-success"
              : "bg-warning/10 text-warning"
          )}
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              isHealthy
                ? "bg-success animate-pulse"
                : "bg-warning"
            )}
          />
          {isHealthy ? "Running" : "Degraded"}
        </span>
      </div>

      {/* Counters grid */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mb-0.5">
            Total Syncs
          </div>
          <div className="text-sm font-mono font-bold text-text-primary">
            {info.totalSyncs}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mb-0.5">
            Failures
          </div>
          <div className="text-sm font-mono font-bold text-text-primary">
            {info.failCount}
            {info.consecutiveFails > 0 && (
              <span className="text-[10px] text-error ml-1">
                ({info.consecutiveFails} consecutive)
              </span>
            )}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mb-0.5">
            Last Sync
          </div>
          <div className="flex items-center gap-1">
            <Clock size={10} className="text-text-muted" />
            <span className="text-xs font-mono text-text-primary">
              {secondsSinceSync !== null
                ? secondsSinceSync < 60
                  ? `${secondsSinceSync}s ago`
                  : `${Math.floor(secondsSinceSync / 60)}m ago`
                : "—"}
            </span>
          </div>
        </div>
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-wider mb-0.5">
            Uptime
          </div>
          <div className="text-xs font-mono text-text-primary">
            {uptimeSeconds !== null
              ? uptimeSeconds < 3600
                ? `${Math.floor(uptimeSeconds / 60)}m`
                : `${Math.floor(uptimeSeconds / 3600)}h ${Math.floor((uptimeSeconds % 3600) / 60)}m`
              : "—"}
          </div>
        </div>
      </div>

      {/* Last result */}
      {info.lastSyncResult && (
        <div className="pt-2 border-t border-forge-border">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-text-muted">Last result</span>
            <span
              className={cn(
                "font-medium capitalize",
                info.lastSyncResult === "success"
                  ? "text-success"
                  : "text-error"
              )}
            >
              {info.lastSyncResult}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Live Event Feed ─────────────────────────────────────────────

function LiveEventList({ events }: { events: LiveEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="card p-5 text-center">
        <Activity size={20} className="mx-auto mb-2 text-text-muted" />
        <p className="text-xs text-text-muted">
          Waiting for events... Connect VS Code to see live signal captures.
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-forge-border flex items-center justify-between">
        <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2">
          <Activity size={12} className="text-forge-primary" />
          Live Event Stream
        </h3>
        <span className="text-[10px] text-text-muted">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="divide-y divide-forge-border max-h-[320px] overflow-y-auto">
        {events.map((event) => (
          <div
            key={event.id}
            className="flex items-start gap-3 px-4 py-2.5 hover:bg-forge-elevated/30 transition-colors"
          >
            {/* Timeline dot + icon */}
            <div className="relative flex flex-col items-center pt-0.5">
              {event.type === "event_captured" && event.eventType ? (
                (() => {
                  const Icon =
                    EVENT_ICONS[event.eventType] || Activity;
                  return (
                    <Icon
                      size={12}
                      className={
                        EVENT_COLORS[event.eventType] || "text-text-muted"
                      }
                    />
                  );
                })()
              ) : (
                <Activity
                  size={12}
                  className={
                    event.status === "success"
                      ? "text-success"
                      : "text-warning"
                  }
                />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-primary">
                  {event.type === "event_captured" && event.eventType
                    ? EVENT_LABELS[event.eventType] || event.eventType
                    : event.type === "sync_status"
                    ? `Sync #${event.totalSyncs ?? "?"}`
                    : "Event"}
                </span>
                <span className="text-[10px] font-mono text-text-muted">
                  {formatTimeAgo(event.timestamp)}
                </span>
              </div>
              {event.type === "sync_status" && (
                <p className="text-[10px] text-text-muted mt-0.5 capitalize">
                  {event.status === "success"
                    ? "Metrics pushed to Rudra-bots"
                    : "Sync failed"}
                </p>
              )}
              {event.type === "event_captured" && event.signalId && (
                <p className="text-[10px] text-text-muted mt-0.5 font-mono">
                  {event.signalId.slice(0, 12)}...
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Live Connection Badge ───────────────────────────────────────

function LiveBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-full transition-all",
        connected
          ? "bg-success/10 text-success"
          : "bg-forge-elevated text-text-muted"
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          connected ? "bg-success animate-pulse" : "bg-text-muted"
        )}
      />
      {connected ? "Live" : "Disconnected"}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

interface LiveEventFeedProps {
  syncInfo?: SyncDaemonInfo | null;
}

export default function LiveEventFeed({ syncInfo }: LiveEventFeedProps) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );

  // Connect to WebSocket for real-time events (same API_BASE as api.ts)
  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";
    const wsBase = apiBase.replace(/^http/, "ws");
    let isCancelled = false;

    function connect() {
      if (isCancelled) return;

      try {
        const ws = new WebSocket(`${wsBase}/ws/training-progress`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isCancelled) {
            ws.close();
            return;
          }
          setWsConnected(true);
          setWsError(null);
        };

        ws.onmessage = (msg) => {
          if (isCancelled) return;
          try {
            const data = JSON.parse(msg.data);
            const now = Date.now() / 1000;

            if (data.type === "event_captured") {
              const event: WsEventCaptured = data;
              setEvents((prev) => [
                {
                  id: `event-${event.signal_id || now}`,
                  type: "event_captured",
                  eventType: event.event_type,
                  timestamp: event.timestamp || now,
                  signalId: event.signal_id,
                },
                ...prev.slice(0, 49), // keep last 50
              ]);
            } else if (data.type === "sync_status") {
              const sync: WsSyncStatus = data;
              setEvents((prev) => [
                {
                  id: `sync-${sync.last_sync || now}`,
                  type: "sync_status",
                  status: sync.status,
                  timestamp: sync.last_sync || now,
                  totalSyncs: sync.total_syncs,
                },
                ...prev.slice(0, 49),
              ]);
            } else if (data.type === "pong") {
              // heartbeat — connection alive
            }
          } catch {
            // ignore parse errors
          }
        };

        ws.onerror = () => {
          if (!isCancelled) {
            setWsConnected(false);
            setWsError("Connection error");
          }
        };

        ws.onclose = () => {
          if (!isCancelled) {
            setWsConnected(false);
            // Auto-reconnect after 5 seconds
            reconnectTimeoutRef.current = setTimeout(() => {
              if (!isCancelled) connect();
            }, 5000);
          }
        };
      } catch (e) {
        if (!isCancelled) {
          setWsError(
            e instanceof Error ? e.message : "Failed to connect"
          );
          // Retry
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isCancelled) connect();
          }, 5000);
        }
      }
    }

    connect();

    return () => {
      isCancelled = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return (
    <div className="space-y-4">
      {/* Header with Live badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {wsConnected ? (
            <Wifi size={14} className="text-success" />
          ) : (
            <WifiOff size={14} className="text-text-muted" />
          )}
          <span className="text-sm font-semibold text-text-primary">
            Real-Time Events
          </span>
          <LiveBadge connected={wsConnected} />
        </div>
        {wsError && (
          <span className="text-[10px] text-error flex items-center gap-1">
            <RefreshCw size={10} />
            {wsError}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Sync Daemon status card */}
        <div className="lg:col-span-1">
          <SyncDaemonStatus info={syncInfo ?? null} />
        </div>

        {/* Live event list */}
        <div className="lg:col-span-2">
          <LiveEventList events={events} />
        </div>
      </div>
    </div>
  );
}
