"use client";

import { useState, useEffect, useRef } from "react";
import {
  Swords,
  Send,
  Loader2,
  Clock,
  DollarSign,
  FileText,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  RefreshCw,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  TrendingUp,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────

interface ProviderResult {
  provider: string;
  model: string;
  label: string;
  content: string;
  latency_ms: number;
  token_count_input: number;
  token_count_output: number;
  token_count_total: number;
  cost_usd: number;
  error: string | null;
}

interface BattleData {
  prompt: string;
  system_prompt: string | null;
  results: ProviderResult[];
  winner: string | null;
  total_latency_ms: number;
}

interface ProviderOption {
  id: string;
  label: string;
  default_model: string;
  is_local: boolean;
}

// ─── API ─────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";

async function runBattle(
  prompt: string,
  providers: { provider: string; model: string }[],
  systemPrompt?: string
) {
  const res = await fetch(`${API_BASE}/api/battle/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      system_prompt: systemPrompt || null,
      providers: providers.map((p) => ({
        provider: p.provider,
        model: p.model,
        temperature: 0.7,
        max_tokens: 2048,
      })),
      auto_select: providers.length === 0,
      auto_count: 3,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json();
}

async function getProviders() {
  const res = await fetch(`${API_BASE}/api/battle/providers`);
  if (!res.ok) return { providers: [] };
  const data = await res.json();
  return data;
}

// ─── Components ─────────────────────────────────────────────────

function LatencyBar({ ms }: { ms: number }) {
  const maxBar = 10000;
  const pct = Math.min((ms / maxBar) * 100, 100);
  const color = ms < 1000 ? "bg-success" : ms < 5000 ? "bg-warning" : "bg-error";
  return (
    <div className="h-1.5 bg-forge-elevated rounded-full overflow-hidden flex-1">
      <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ProviderCard({ result, isWinner }: { result: ProviderResult; isWinner: boolean }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`card p-4 ${isWinner ? "ring-1 ring-success/40" : ""}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isWinner ? "bg-success/20" : "bg-forge-elevated"}`}>
            {isWinner ? (
              <CheckCircle2 size={16} className="text-success" />
            ) : result.error ? (
              <XCircle size={16} className="text-error" />
            ) : (
              <Zap size={16} className="text-forge-primary" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-text-primary">{result.label}</span>
              {isWinner && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-success/20 text-success uppercase">
                  Winner
                </span>
              )}
            </div>
            <span className="text-[10px] font-mono text-text-muted">{result.provider}/{result.model}</span>
          </div>
        </div>
        {isWinner && <TrendingUp size={16} className="text-success" />}
      </div>

      {result.error ? (
        <div className="flex items-start gap-2 p-2 rounded-lg bg-error/10">
          <AlertTriangle size={14} className="text-error mt-0.5 shrink-0" />
          <p className="text-xs text-error">{result.error}</p>
        </div>
      ) : (
        <>
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div>
              <div className="flex items-center gap-1 text-[10px] text-text-muted mb-1">
                <Clock size={10} />
                Latency
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-text-primary font-semibold">
                  {result.latency_ms.toFixed(0)}ms
                </span>
                <LatencyBar ms={result.latency_ms} />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-1 text-[10px] text-text-muted mb-1">
                <FileText size={10} />
                Tokens
              </div>
              <span className="text-xs font-mono text-text-primary">
                {result.token_count_input}→{result.token_count_output}
              </span>
            </div>
            <div>
              <div className="flex items-center gap-1 text-[10px] text-text-muted mb-1">
                <DollarSign size={10} />
                Cost
              </div>
              <span className="text-xs font-mono text-text-primary">
                ${result.cost_usd.toFixed(6)}
              </span>
            </div>
          </div>

          {/* Content toggle */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-forge-primary hover:text-forge-primary/80 transition-colors"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {expanded ? "Hide response" : `Show response (${result.content.length} chars)`}
          </button>

          {expanded && (
            <div className="mt-2 p-3 rounded-lg bg-forge-elevated">
              <pre className="text-xs whitespace-pre-wrap text-text-secondary font-mono leading-relaxed max-h-60 overflow-y-auto">
                {result.content}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function BattlePage() {
  const [prompt, setPrompt] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showSystem, setShowSystem] = useState(false);
  const [entries, setEntries] = useState<{ provider: string; model: string; key: number }[]>([
    { provider: "openai", model: "gpt-4o", key: Date.now() },
    { provider: "anthropic", model: "claude-sonnet-4", key: Date.now() + 1 },
    { provider: "ollama", model: "qwen2.5-coder:14b", key: Date.now() + 2 },
  ]);
  const [availableProviders, setAvailableProviders] = useState<ProviderOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [battle, setBattle] = useState<BattleData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoMode, setAutoMode] = useState(false);
  const nextKey = useRef(Date.now() + 100);

  useEffect(() => {
    getProviders().then((data) => {
      if (data.providers) setAvailableProviders(data.providers);
    }).catch(() => {});
  }, []);

  const handleAddEntry = () => {
    nextKey.current += 1;
    setEntries([...entries, { provider: "", model: "", key: nextKey.current }]);
  };

  const handleRemoveEntry = (key: number) => {
    if (entries.length <= 1) return;
    setEntries(entries.filter((e) => e.key !== key));
  };

  const handleUpdateEntry = (key: number, field: "provider" | "model", value: string) => {
    setEntries(entries.map((e) => (e.key === key ? { ...e, [field]: value } : e)));
  };

  const handleRunBattle = async () => {
    if (!prompt.trim()) {
      setError("Please enter a prompt first.");
      return;
    }
    setError(null);
    setBattle(null);
    setLoading(true);

    try {
      if (autoMode) {
        const data = await runBattle(prompt, []);
        if (data.success) setBattle(data.battle);
        else setError(data.error || "Battle failed");
      } else {
        const validEntries = entries.filter((e) => e.provider && e.model);
        if (validEntries.length === 0) {
          setError("Please add at least one provider entry.");
          setLoading(false);
          return;
        }
        const data = await runBattle(
          prompt,
          validEntries.map((e) => ({ provider: e.provider, model: e.model })),
          systemPrompt || undefined
        );
        if (data.success) setBattle(data.battle);
        else setError(data.error || "Battle failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run battle");
    } finally {
      setLoading(false);
    }
  };

  const commonModels: Record<string, string[]> = {
    openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3"],
    anthropic: ["claude-sonnet-4", "claude-opus-4", "claude-3-5-sonnet-20241022"],
    deepseek: ["deepseek-chat", "deepseek-reasoner"],
    gemini: ["gemini-2.5-pro", "gemini-2.5-flash"],
    mistral: ["mistral-large", "mistral-small"],
    groq: ["llama-3.3-70b", "mixtral-8x7b"],
    ollama: ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "llama3.2:3b"],
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-3">
          <Swords size={24} className="text-forge-primary" />
          Model Battle Arena
        </h1>
        <p className="text-sm text-text-muted mt-1">
          Send the same prompt to multiple models and compare responses, latency, and cost.
        </p>
      </div>

      {/* Input area */}
      <div className="card p-5 space-y-4">
        {/* Prompt */}
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter your prompt here..."
          rows={4}
          className="input resize-none font-mono text-sm w-full"
        />

        {/* System prompt toggle */}
        <button
          onClick={() => setShowSystem(!showSystem)}
          className="text-xs text-forge-primary hover:text-forge-primary/80 transition-colors"
        >
          {showSystem ? "− Hide system prompt" : "+ Add system prompt"}
        </button>

        {showSystem && (
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Optional system prompt..."
            rows={2}
            className="input resize-none text-sm w-full"
          />
        )}

        {/* Auto mode toggle */}
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoMode}
              onChange={(e) => setAutoMode(e.target.checked)}
              className="rounded border-forge-border bg-forge-elevated text-forge-primary focus:ring-forge-primary"
            />
            <span className="text-sm text-text-secondary">Auto-select top providers</span>
          </label>
          {!autoMode && (
            <button onClick={handleAddEntry} className="btn-ghost text-xs gap-1">
              <Plus size={14} />
              Add Provider
            </button>
          )}
        </div>

        {/* Provider entries */}
        {!autoMode && (
          <div className="space-y-2">
            {entries.map((entry) => (
              <div key={entry.key} className="flex items-center gap-2">
                <select
                  value={entry.provider}
                  onChange={(e) => handleUpdateEntry(entry.key, "provider", e.target.value)}
                  className="input text-xs py-2 w-40"
                >
                  <option value="">Select provider...</option>
                  {availableProviders.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={entry.model}
                  onChange={(e) => handleUpdateEntry(entry.key, "model", e.target.value)}
                  placeholder="Model ID"
                  list={`models-${entry.key}`}
                  className="input text-xs py-2 w-56 font-mono"
                />
                <datalist id={`models-${entry.key}`}>
                  {entry.provider && (commonModels[entry.provider] || []).map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <button
                  onClick={() => handleRemoveEntry(entry.key)}
                  disabled={entries.length <= 1}
                  className="btn-ghost p-2 disabled:opacity-30"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-error/10 border border-error/20 text-sm text-error flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {/* Run button */}
        <button
          onClick={handleRunBattle}
          disabled={loading}
          className="btn-primary gap-2"
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Battling...
            </>
          ) : (
            <>
              <Swords size={16} />
              Start Battle
            </>
          )}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="card p-12 flex flex-col items-center justify-center">
          <Loader2 size={32} className="text-forge-primary animate-spin mb-4" />
          <p className="text-sm text-text-muted">Sending prompt to all providers...</p>
          <div className="flex gap-4 mt-4 text-xs text-text-muted">
            {entries.filter(e => e.provider).map((e, i) => (
              <span key={i} className="flex items-center gap-1">
                <RefreshCw size={10} className="animate-spin" />
                {e.provider}/{e.model}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {battle && !loading && (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
          {/* Summary */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Swords size={16} className="text-forge-primary" />
                Battle Results
              </h3>
              <span className="text-[10px] font-mono text-text-muted">
                Total: {battle.total_latency_ms.toFixed(0)}ms
              </span>
            </div>
            <p className="text-xs text-text-muted mb-4 line-clamp-2">{battle.prompt}</p>

            {/* Winner highlight */}
            {battle.winner && (
              <div className="p-3 rounded-lg bg-success/10 border border-success/20 flex items-center gap-3 mb-4">
                <CheckCircle2 size={20} className="text-success shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-success">Winner: {battle.winner}</p>
                  <p className="text-[10px] text-text-muted">
                    Fastest quality response based on content analysis
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Provider cards */}
          {battle.results.map((result, i) => (
            <ProviderCard
              key={i}
              result={result}
              isWinner={result.label === battle.winner}
            />
          ))}
        </div>
      )}
    </div>
  );
}
