"use client";

import { useState } from "react";
import {
  Monitor,
  Terminal,
  Globe,
  Brain,
  Cpu,
  Layers,
  Server,
  ChevronDown,
  ChevronUp,
  ArrowDown,
  Wifi,
  WifiOff,
  Bot,
  Zap,
  GitBranch,
  Library,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

interface ServiceStatusMap {
  [name: string]: { online: boolean; latency: number | null };
}

interface LayerItem {
  icon: React.ElementType;
  name: string;
  subItems: string[];
  statusKey?: string;
}

interface Layer {
  name: string;
  color: string;
  items: LayerItem[];
}

// ═══════════════════════════════════════════════════════════════════
// Layer definitions
// ═══════════════════════════════════════════════════════════════════

const LAYERS: Layer[] = [
  {
    name: "Layer 1: User Interfaces",
    color: "from-cyan-500/20 to-blue-500/10",
    items: [
      {
        icon: Terminal,
        name: "CLI (open-claude)",
        subItems: ["VS Code Extension", "Terminal Assistant"],
        statusKey: "Open-Claude CLI",
      },
      {
        icon: Monitor,
        name: "Web Dashboard",
        subItems: ["Next.js (this)", "Rudra-bots UI"],
        statusKey: "Next.js Dashboard",
      },
    ],
  },
  {
    name: "Layer 2: Agent Orchestration",
    color: "from-violet-500/20 to-purple-500/10",
    items: [
      {
        icon: Brain,
        name: "Hermes-Agent",
        subItems: ["Planner Agent", "Executor Agent", "Monitor Agent", "Skill Manager"],
        statusKey: "Hermes Agent",
      },
      {
        icon: Globe,
        name: "ForgeAI Gateway",
        subItems: ["Unified Entry Point", "Route Distribution"],
        statusKey: "ForgeAI Gateway",
      },
    ],
  },
  {
    name: "Layer 3: Core Engine (PythonAI)",
    color: "from-forge-primary/20 to-forge-primary/5",
    items: [
      {
        icon: Cpu,
        name: "PythonAI",
        subItems: ["RAG Engine (cAST)", "AI Agents", "Training Pipeline", "Capture Engine"],
        statusKey: "PythonAI",
      },
      {
        icon: Bot,
        name: "Rudra-bots",
        subItems: ["Odysseus UI", "Analytics Views"],
        statusKey: "Rudra-bots",
      },
    ],
  },
  {
    name: "Layer 4: Infrastructure",
    color: "from-emerald-500/20 to-teal-500/10",
    items: [
      {
        icon: Layers,
        name: "MCP Servers",
        subItems: ["File Ops", "Git Tools", "LSP Server", "Custom Tools"],
        statusKey: undefined,
      },
      {
        icon: Server,
        name: "API & Storage",
        subItems: ["REST API (7337)", "Projects DB", "Signal Store", "Adapter Files"],
        statusKey: "PythonAI",
      },
    ],
  },
];

// ═══════════════════════════════════════════════════════════════════
// Layer Card Component
// ═══════════════════════════════════════════════════════════════════

function LayerCard({
  layer,
  statuses,
}: {
  layer: Layer;
  statuses: ServiceStatusMap;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div
      className={cn(
        "card overflow-hidden border border-forge-border/50 transition-all duration-300",
        "hover:border-forge-border"
      )}
    >
      {/* Layer header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 bg-gradient-to-r from-forge-elevated/50 to-transparent"
      >
        <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">
          {layer.name}
        </h3>
        {expanded ? (
          <ChevronUp size={14} className="text-text-muted" />
        ) : (
          <ChevronDown size={14} className="text-text-muted" />
        )}
      </button>

      {/* Layer items */}
      {expanded && (
        <div className="p-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {layer.items.map((item) => {
            const Icon = item.icon;
            const status = item.statusKey ? statuses[item.statusKey] : undefined;
            const isOnline = status?.online ?? false;

            return (
              <div
                key={item.name}
                className={cn(
                  "p-3 rounded-lg border transition-all duration-300",
                  status
                    ? isOnline
                      ? "border-success/20 bg-success/[0.02]"
                      : "border-error/10 bg-forge-elevated/30"
                    : "border-forge-border/30 bg-forge-elevated/20"
                )}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        "p-1.5 rounded-md transition-colors",
                        status && isOnline
                          ? "bg-success/10"
                          : "bg-forge-elevated"
                      )}
                    >
                      <Icon
                        size={14}
                        className={
                          status && isOnline
                            ? "text-success"
                            : "text-text-muted"
                        }
                      />
                    </div>
                    <span className="text-xs font-semibold text-text-primary">
                      {item.name}
                    </span>
                  </div>
                  {status && (
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full",
                        isOnline ? "bg-success" : "bg-error"
                      )}
                    />
                  )}
                </div>

                {/* Sub-items */}
                <ul className="space-y-1">
                  {item.subItems.map((sub) => (
                    <li
                      key={sub}
                      className="text-[10px] text-text-muted flex items-center gap-1.5 pl-1"
                    >
                      <span className="w-0.5 h-0.5 rounded-full bg-text-muted/40" />
                      {sub}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Data Flow Arrows (between layers)
// ═══════════════════════════════════════════════════════════════════

const FLOW_LABELS = [
  { from: "User Interfaces", to: "Agent Orchestration", label: "CLI / WS Commands" },
  { from: "Agent Orchestration", to: "Core Engine (PythonAI)", label: "RAG Queries / Training" },
  { from: "Core Engine (PythonAI)", to: "Infrastructure", label: "MCP Tools / REST API" },
  { from: "Infrastructure", to: "User Interfaces", label: "Responses / Events" },
];

function DataFlowLegend({ statuses }: { statuses: ServiceStatusMap }) {
  const onlineCount = Object.values(statuses).filter((s) => s.online).length;
  const totalCount = Object.keys(statuses).length;

  return (
    <div className="card p-4">
      <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-3 flex items-center gap-2">
        <Zap size={14} className="text-forge-primary" />
        Data Flow
      </h3>
      <div className="space-y-2">
        {FLOW_LABELS.map((flow, idx) => (
          <div key={flow.label} className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-[11px] text-text-secondary min-w-0 flex-1">
              <span className="font-medium truncate">{flow.from}</span>
              <ArrowDown size={10} className="text-forge-primary shrink-0" />
              <span className="font-medium truncate">{flow.to}</span>
            </div>
            <span className="text-[10px] font-mono text-text-muted shrink-0">
              {flow.label}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 pt-3 border-t border-forge-border flex items-center justify-between text-[11px]">
        <span className="text-text-muted">Service status</span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-success">
            <Wifi size={10} />
            {onlineCount} online
          </span>
          {totalCount - onlineCount > 0 && (
            <span className="flex items-center gap-1 text-error">
              <WifiOff size={10} />
              {totalCount - onlineCount} offline
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

interface ArchitectureFlowProps {
  serviceStatuses: ServiceStatusMap;
  className?: string;
}

export default function ArchitectureFlow({
  serviceStatuses,
  className,
}: ArchitectureFlowProps) {
  return (
    <div className={cn("space-y-6", className)}>
      {/* Section header */}
      <div>
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Library size={16} className="text-forge-primary" />
          Architecture Overview
        </h2>
        <p className="text-[11px] text-text-muted mt-1">
          ForgeAI ecosystem layered architecture — UI → Orchestration → Core Engine → Infrastructure
        </p>
      </div>

      {/* Architecture layers */}
      <div className="space-y-3">
        {LAYERS.map((layer) => (
          <div key={layer.name}>
            <LayerCard layer={layer} statuses={serviceStatuses} />
            {/* Arrow between layers (not after last) */}
            {layer !== LAYERS[LAYERS.length - 1] && (
              <div className="flex justify-center py-1">
                <div className="flex items-center gap-2 text-[10px] text-text-muted">
                  <span className="w-16 h-px bg-forge-border" />
                  <ArrowDown size={12} className="text-forge-primary/60" />
                  <span className="w-16 h-px bg-forge-border" />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Data flow summary */}
      <DataFlowLegend statuses={serviceStatuses} />

      {/* Research references */}
      <details className="card p-3">
        <summary className="text-xs font-medium text-text-muted cursor-pointer hover:text-text-secondary transition-colors flex items-center gap-2">
          <BookOpen size={12} />
          Research Backing
        </summary>
        <div className="mt-2 space-y-1.5 text-[10px] text-text-muted">
          <p>• RAG Engine (cAST chunking) — EMNLP 2025</p>
          <p>• Multi-agent orchestration — AAAI 2025</p>
          <p>• QLoRA / GRPO fine-tuning — NeurIPS 2025, MIT 2026</p>
          <p>• Capture Engine (signal collection) — MIT SEAL architecture</p>
          <p>• SDFT mixing (70/20/10) — Self-Improvement via Direct Preference Optimization</p>
        </div>
      </details>
    </div>
  );
}
