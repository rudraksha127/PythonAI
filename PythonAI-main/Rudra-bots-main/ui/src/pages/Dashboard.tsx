import { useEffect, useState } from "react";
import { getStats, getHealth } from "@/lib/api";
import type { StatsResponse, HealthCheck } from "@/lib/types";
import { Activity, TrendingUp, Zap, Users, RefreshCw } from "lucide-react";

export default function Dashboard() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([
          getStats().catch(() => null),
          getHealth().catch(() => null),
        ]);
        setStats(s);
        setHealth(h);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw size={24} className="animate-spin text-zinc-500" />
      </div>
    );
  }

  const totalSignals = stats
    ? Object.values(stats.signals_by_type).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold">Dashboard</h1>
        <p className="text-sm text-zinc-400 mt-1">
          ForgeAI system overview and acceptance rate tracking
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={14} className="text-purple-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
              Acceptance Rate
            </span>
          </div>
          <div className="text-2xl font-bold text-purple-400">
            {stats ? `${stats.overall_acceptance_rate.toFixed(1)}%` : "—"}
          </div>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity size={14} className="text-cyan-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
              Total Signals
            </span>
          </div>
          <div className="text-2xl font-bold text-cyan-400">
            {totalSignals.toLocaleString()}
          </div>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap size={14} className="text-green-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
              Sessions
            </span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {stats?.total_sessions ?? "—"}
          </div>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Users size={14} className="text-yellow-400" />
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
              Version
            </span>
          </div>
          <div className="text-2xl font-bold text-yellow-400">
            {health?.version ?? "—"}
          </div>
        </div>
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-semibold mb-3">Signal Distribution</h2>
        {stats ? (
          <div className="space-y-2">
            {Object.entries(stats.signals_by_type).map(([type, count]) => {
              const pct = totalSignals > 0 ? (count / totalSignals) * 100 : 0;
              return (
                <div key={type}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="capitalize text-zinc-300">{type}</span>
                    <span className="font-mono text-zinc-500">{count}</span>
                  </div>
                  <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-purple-500/60"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-zinc-500">Connect to ForgeAI server to see stats.</p>
        )}
      </div>

      {health && (
        <div className="text-center text-[10px] text-zinc-600">
          Server uptime: {Math.floor(health.uptime_seconds / 60)}m · Status: {health.status}
        </div>
      )}
    </div>
  );
}
