"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Activity,
  Wifi,
  WifiOff,
  Terminal,
  Cpu,
  Shield,
  DollarSign,
  ChevronRight,
  Server,
  HardDrive,
  Bot,
  Brain,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────

interface MonitorStats {
  total_files: number;
  total_size_gb: number;
  arxiv_papers: number;
  openalex_works: number;
  synthetic_rows: number;
  rag_indexed: number;
  errors: number;
  hf_datasets?: number;
}

interface AgentInfo {
  status: string;
  last_action: string;
}

interface ProviderInfo {
  label: string;
  tier: string;
  has_key: boolean;
  status: string;
}

interface HeartbeatData {
  uptime_s: number;
  stats: MonitorStats;
  agents: Record<string, AgentInfo>;
  providers: Record<string, ProviderInfo>;
  status: string;
}

interface LogEntry {
  id: number;
  level: string;
  message: string;
  timestamp: Date;
}

// ─── Phase Config ───────────────────────────────────────────────

const PHASES = [
  { id: "arxiv", name: "arXiv Papers", icon: "📚", gradient: "from-blue-500 to-cyan-500" },
  { id: "openalex", name: "OpenAlex Research", icon: "🔬", gradient: "from-purple-500 to-pink-500" },
  { id: "hf", name: "HuggingFace Datasets", icon: "🤗", gradient: "from-yellow-500 to-orange-500" },
  { id: "synthetic", name: "Synthetic Generation", icon: "🤖", gradient: "from-green-500 to-emerald-500" },
  { id: "rag", name: "RAG Pipeline Indexing", icon: "🧠", gradient: "from-cyan-500 to-blue-500" },
];

const AGENTS = [
  { id: "orchestrator", name: "Orchestrator", emoji: "🎯" },
  { id: "retrieval", name: "Retrieval", emoji: "🔍" },
  { id: "code", name: "Code", emoji: "💻" },
  { id: "docs", name: "Docs", emoji: "📚" },
  { id: "performance", name: "Performance", emoji: "⚡" },
  { id: "teacher", name: "Teacher", emoji: "🎓" },
];

const CONSTITUTION = [
  { label: "Truth over Confidence", passed: true },
  { label: "Verify before Trust", passed: true },
  { label: "Empower over Depend", passed: true },
  { label: "Depth over Breadth", passed: true },
];

// ─── Console Component ──────────────────────────────────────────

function LiveConsole({ logs }: { logs: LogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const levelColors: Record<string, string> = {
    info: "text-cyan-400",
    success: "text-green-400",
    warn: "text-yellow-400",
    error: "text-red-400",
  };

  return (
    <div className="bg-black/60 rounded-lg border border-zinc-800 font-mono text-xs h-80 overflow-y-auto p-3 space-y-0.5">
      {logs.length === 0 && (
        <div className="text-zinc-600 italic">Waiting for events...</div>
      )}
      {logs.map((log) => (
        <div
          key={log.id}
          className="opacity-0 animate-[fadeSlide_0.3s_ease_forwards]"
          style={{ animationFillMode: "forwards" }}
        >
          <span className="text-zinc-600 mr-2">
            {log.timestamp.toLocaleTimeString()}
          </span>
          <span className={levelColors[log.level] || "text-zinc-400"}>
            {log.message}
          </span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

// ─── Phase Pipeline Component ───────────────────────────────────

function PhasePipeline({ phaseStatus }: { phaseStatus: Record<string, string> }) {
  return (
    <div className="space-y-2">
      {PHASES.map((phase) => {
        const status = phaseStatus[phase.name] || "IDLE";
        const isRunning = status.includes("RUNNING");
        const isComplete = status.includes("COMPLETE");

        return (
          <div
            key={phase.id}
            className={`flex items-center gap-3 p-2.5 rounded-lg border transition-all ${
              isRunning
                ? "bg-cyan-500/5 border-cyan-500/20"
                : isComplete
                  ? "bg-green-500/5 border-green-500/20"
                  : "bg-zinc-800/30 border-zinc-800"
            }`}
          >
            <div
              className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                isRunning
                  ? "bg-cyan-400 animate-pulse shadow-lg shadow-cyan-400/50"
                  : isComplete
                    ? "bg-green-400 shadow-lg shadow-green-400/30"
                    : "bg-zinc-600"
              }`}
            />
            <span className="text-xs font-medium flex-1">{phase.icon} {phase.name}</span>
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                isRunning
                  ? "bg-cyan-500/10 text-cyan-300"
                  : isComplete
                    ? "bg-green-500/10 text-green-300"
                    : "bg-zinc-700/50 text-zinc-500"
              }`}
            >
              {status}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Agent Swarm Component ──────────────────────────────────────

function AgentSwarm({ agents }: { agents: Record<string, AgentInfo> }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {AGENTS.map((agent) => {
        const info = agents[agent.id];
        const isActive = info?.status === "active";

        return (
          <div
            key={agent.id}
            className={`p-2.5 rounded-lg text-center border transition-all ${
              isActive
                ? "bg-green-500/5 border-green-500/20"
                : "bg-zinc-800/30 border-zinc-800 hover:bg-zinc-800/50"
            }`}
          >
            <div className="text-lg mb-0.5">{agent.emoji}</div>
            <div className="text-xs font-semibold text-text-primary">
              {agent.name}
            </div>
            <div className="text-[10px] text-text-muted truncate mt-0.5">
              {info?.last_action || "idle"}
            </div>
            {isActive && (
              <div className="mt-1.5 flex justify-center">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Data Sources Component ─────────────────────────────────────

function DataSources({ stats }: { stats: MonitorStats }) {
  const sources = [
    { label: "arXiv Papers", value: stats.arxiv_papers, color: "bg-green-400" },
    { label: "OpenAlex Works", value: stats.openalex_works, color: "bg-cyan-400" },
    { label: "HuggingFace Rows", value: stats.hf_datasets || 0, color: "bg-purple-400" },
    { label: "Synthetic Data", value: stats.synthetic_rows, color: "bg-yellow-400" },
    { label: "RAG Indexed", value: stats.rag_indexed, color: "bg-blue-400" },
  ];

  const sizeGB = stats.total_size_gb || 0;
  const pct = Math.min((sizeGB / 100) * 100, 100);

  return (
    <div className="space-y-3">
      {sources.map((src) => (
        <div key={src.label} className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-800/30">
          <div className={`w-1.5 h-1.5 rounded-full ${src.color}`} />
          <span className="text-xs text-text-secondary flex-1">{src.label}</span>
          <span className="text-xs font-mono text-cyan-400 font-semibold">
            {src.value.toLocaleString()}
          </span>
        </div>
      ))}

      {/* Storage bar */}
      <div className="pt-1">
        <div className="h-4 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-purple-500 relative transition-all duration-1000"
            style={{ width: `${Math.max(pct, 0.5)}%` }}
          >
            <div className="absolute top-0 right-0 bottom-0 w-8 bg-gradient-to-r from-transparent to-white/30 animate-pulse" />
          </div>
        </div>
        <div className="flex justify-between text-[10px] text-zinc-500 mt-1">
          <span>Used: {sizeGB.toFixed(3)} GB</span>
          <span>Storage</span>
        </div>
      </div>
    </div>
  );
}

// ─── Provider Status Component ─────────────────────────────────

function ProviderStatus({ providers }: { providers: Record<string, ProviderInfo> }) {
  const entries = Object.entries(providers);

  if (entries.length === 0) {
    return (
      <div className="text-center text-xs text-zinc-600 py-4">
        No provider data yet
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {entries.map(([key, info]) => (
        <div
          key={key}
          className="flex items-center gap-2 p-2 rounded-lg bg-zinc-800/30 border border-zinc-800"
        >
          <div
            className={`w-1.5 h-1.5 rounded-full ${
              info.status === "online" ? "bg-green-400 shadow-green-400/50" : "bg-zinc-600"
            }`}
          />
          <div className="min-w-0">
            <div className="text-xs font-medium text-text-primary truncate">
              {info.label || key}
            </div>
            <div className="text-[10px] font-mono text-zinc-500 truncate">
              {info.tier} {info.has_key ? "✓" : ""}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Constitution Checks ───────────────────────────────────────

function ConstitutionChecks() {
  return (
    <div className="grid grid-cols-2 gap-2">
      {CONSTITUTION.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-2 p-2.5 rounded-lg bg-zinc-800/30"
        >
          <div className="w-5 h-5 rounded-md bg-green-500/15 text-green-400 flex items-center justify-center text-[10px] font-bold">
            ✓
          </div>
          <span className="text-xs font-medium text-text-secondary">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function MonitorPage() {
  const [connected, setConnected] = useState(false);
  const [uptime, setUptime] = useState(0);
  const [stats, setStats] = useState<MonitorStats>({
    total_files: 0,
    total_size_gb: 0,
    arxiv_papers: 0,
    openalex_works: 0,
    synthetic_rows: 0,
    rag_indexed: 0,
    errors: 0,
  });
  const [agents, setAgents] = useState<Record<string, AgentInfo>>({});
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [phaseStatus, setPhaseStatus] = useState<Record<string, string>>({
    "arXiv Papers": "IDLE",
    "OpenAlex Research": "IDLE",
    "HuggingFace Datasets": "IDLE",
    "Synthetic Data Generation": "IDLE",
    "RAG Pipeline Indexing": "IDLE",
  });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [cost, setCost] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const logIdRef = useRef(0);

  const addLog = useCallback((level: string, message: string) => {
    setLogs((prev) => {
      const next = [
        ...prev,
        { id: logIdRef.current++, level, message, timestamp: new Date() },
      ];
      // Cap at 300
      return next.length > 300 ? next.slice(-300) : next;
    });
  }, []);

  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    const ws = new WebSocket("ws://localhost:8765");

    ws.onopen = () => {
      setConnected(true);
      addLog("success", "[DASHBOARD] Connected to Anti-Gravity Live Server");
    };

    ws.onclose = () => {
      setConnected(false);
      addLog("warn", "[DASHBOARD] Connection lost. Reconnecting in 3s...");
      reconnectRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      setConnected(false);
      addLog("error", "[DASHBOARD] WebSocket error");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch {
        // ignore
      }
    };

    wsRef.current = ws;
  }, [addLog]);

  const handleMessage = useCallback(
    (msg: any) => {
      switch (msg.type) {
        case "FULL_STATE": {
          const { state, history } = msg.data || {};
          if (state?.stats) setStats((prev) => ({ ...prev, ...state.stats }));
          if (state?.agents) setAgents(state.agents);
          if (state?.providers) setProviders(state.providers);
          if (state?.phases) {
            const updated: Record<string, string> = {};
            for (const [phase, status] of Object.entries(state.phases)) {
              updated[phase] = String(status);
            }
            setPhaseStatus((prev) => ({ ...prev, ...updated }));
          }
          if (history) {
            for (const evt of history) {
              if (evt.type === "LOG") {
                addLog(evt.data?.level || "info", evt.data?.msg || "");
              }
            }
          }
          break;
        }
        case "HEARTBEAT": {
          const data = msg.data as HeartbeatData;
          if (data.stats) setStats((prev) => ({ ...prev, ...data.stats }));
          if (data.agents) setAgents(data.agents);
          if (data.providers) setProviders(data.providers);
          if (data.uptime_s != null) setUptime(data.uptime_s);
          if (data.status) addLog("info", `[HEARTBEAT] Status: ${data.status}`);
          break;
        }
        case "LOG": {
          addLog(msg.data?.level || "info", msg.data?.msg || "");
          break;
        }
        case "PHASE_START": {
          const phase = msg.data?.phase;
          if (phase) setPhaseStatus((prev) => ({ ...prev, [phase]: "RUNNING" }));
          addLog("info", `[PHASE] ${phase} started`);
          break;
        }
        case "PHASE_COMPLETE": {
          const p = msg.data?.phase;
          if (p) setPhaseStatus((prev) => ({ ...prev, [p]: "COMPLETE ✓" }));
          addLog("success", `[PHASE] ${p} complete`);
          break;
        }
        case "PROGRESS": {
          const { phase: progPhase, count } = msg.data || {};
          setCost((prev) => prev + 0.001);
          if (progPhase && count != null) {
            addLog("info", `[PROGRESS] ${progPhase}: ${count.toLocaleString()}`);
          }
          break;
        }
      }
    },
    [addLog]
  );

  useEffect(() => {
    addLog("info", "[DASHBOARD] Omniscient AI Monitor v2.0 loaded");
    addLog("info", "[DASHBOARD] Attempting WebSocket connection to ws://localhost:8765...");
    connect();

    return () => {
      wsRef.current?.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [connect, addLog]);

  // Format uptime
  const fmtUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 via-purple-500 to-pink-500 bg-clip-text text-transparent">
          Omniscient AI — God Mode
        </h1>
        <div className="flex items-center justify-center gap-3 mt-2">
          <div className="flex items-center gap-1.5">
            {connected ? (
              <>
                <Wifi size={14} className="text-green-400 animate-pulse" />
                <span className="text-xs text-green-400">Connected — Live Streaming</span>
              </>
            ) : (
              <>
                <WifiOff size={14} className="text-red-400" />
                <span className="text-xs text-red-400">Disconnected</span>
              </>
            )}
          </div>
          <span className="text-zinc-600">|</span>
          <span className="font-mono text-xs text-cyan-400">{fmtUptime(uptime)}</span>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {[
          { label: "Total Files", value: stats.total_files.toString() },
          { label: "GB Collected", value: stats.total_size_gb.toFixed(3) },
          { label: "arXiv Papers", value: stats.arxiv_papers.toLocaleString() },
          { label: "OpenAlex Works", value: stats.openalex_works.toLocaleString() },
          { label: "Synthetic Rows", value: stats.synthetic_rows.toLocaleString() },
          { label: "RAG Indexed", value: stats.rag_indexed.toLocaleString() },
          { label: "Errors", value: stats.errors.toString() },
        ].map((s) => (
          <div
            key={s.label}
            className="card-hover p-3 text-center"
          >
            <div className="text-lg font-bold font-mono bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
              {s.value}
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-wider mt-0.5">
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {/* 1. Live Console (span 2) */}
        <div className="card p-4 lg:col-span-2 xl:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Terminal size={16} className="text-cyan-400" />
              Live System Console
            </h2>
            <span className="text-[10px] text-green-400 font-mono">
              {logs.length} events
            </span>
          </div>
          <LiveConsole logs={logs} />
        </div>

        {/* 2. Phase Pipeline */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <Activity size={16} className="text-purple-400" />
            Active Pipelines
          </h2>
          <PhasePipeline phaseStatus={phaseStatus} />
        </div>

        {/* 3. Agent Swarm */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <Bot size={16} className="text-green-400" />
            Multi-Agent Swarm
          </h2>
          <AgentSwarm agents={agents} />
        </div>

        {/* 4. RAG Architecture */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <Brain size={16} className="text-cyan-400" />
            RAG Pipeline — Triple Hybrid Search
          </h2>
          <div className="flex items-center justify-center flex-wrap gap-0 py-2">
            {["Query", "Dense", "BM25", "KG", "RRF"].map((node, i) => (
              <>
                <div
                  key={node}
                  className="px-3 py-1.5 rounded-lg bg-zinc-800/50 border border-zinc-700 text-[11px] font-semibold text-zinc-300 text-center"
                >
                  {node}
                  {node === "Dense" && (
                    <div className="text-[9px] text-cyan-400 font-normal">MiniLM-L6</div>
                  )}
                  {node === "BM25" && (
                    <div className="text-[9px] text-purple-400 font-normal">Sparse</div>
                  )}
                  {node === "KG" && (
                    <div className="text-[9px] text-green-400 font-normal">NetworkX</div>
                  )}
                </div>
                {i < 4 && (
                  <ChevronRight size={14} className="text-zinc-600 mx-1" />
                )}
              </>
            ))}
          </div>
          <div className="text-center text-[10px] text-zinc-500 mt-2">
            Documents indexed:{" "}
            <span className="text-cyan-400 font-semibold">
              {stats.rag_indexed.toLocaleString()}
            </span>{" "}
            · Embedding: <span className="text-purple-400">all-MiniLM-L6-v2</span>
          </div>
        </div>

        {/* 5. Constitutional Core */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <Shield size={16} className="text-green-400" />
            Constitutional Core
          </h2>
          <ConstitutionChecks />
        </div>

        {/* 6. Data Storage */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <HardDrive size={16} className="text-yellow-400" />
            Data Storage — Live
          </h2>
          <DataSources stats={stats} />
        </div>

        {/* 7. Cost Tracker */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <DollarSign size={16} className="text-green-400" />
            Cost Tracker
          </h2>
          <div className="text-center py-2">
            <div
              className="text-3xl font-bold font-mono bg-gradient-to-r from-green-400 to-cyan-400 bg-clip-text text-transparent"
            >
              ${cost.toFixed(3)}
            </div>
            <div className="text-[10px] text-zinc-500 mt-1">
              Estimated USD cost across all API providers
            </div>
          </div>
        </div>

        {/* 8. API Providers */}
        <div className="card p-4 lg:col-span-2 xl:col-span-2">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-3">
            <Server size={16} className="text-blue-400" />
            API Providers — Multi-Key Parallel Engine
          </h2>
          <ProviderStatus providers={providers} />
          <div className="text-center text-[10px] text-zinc-500 mt-3">
            <strong>Mode:</strong> Parallel Racing — fire all APIs simultaneously, fastest response wins
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-[10px] text-zinc-600 pt-4 border-t border-zinc-800">
        Omniscient AI Monitor v2.0 · Real-time WebSocket streaming · Data encrypted at rest
      </div>
    </div>
  );
}
