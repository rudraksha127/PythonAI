import type { HealthCheck, StatsResponse, ChatResponse } from "./types";

const API_BASE = "/api";

async function fetchApi<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API ${res.status}: ${error}`);
  }

  return res.json();
}

// ─── Health ─────────────────────────────────────────────────

export async function getHealth(): Promise<HealthCheck> {
  return fetchApi<HealthCheck>("/health");
}

// ─── Chat ───────────────────────────────────────────────────

export async function sendChatMessage(
  question: string,
  model?: string
): Promise<ChatResponse> {
  return fetchApi<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ question, model: model || "" }),
  });
}

// ─── Agent Chat (Streaming) ──────────────────────────────────

export function createAgentChatUrl(): string {
  return `${API_BASE}/agent/chat`;
}

// ─── Events ─────────────────────────────────────────────────

export async function captureEvent(payload: {
  event_type: string;
  session_id: string;
  file_path: string;
  language: string;
  suggestion: string;
}): Promise<{ event_id: string }> {
  return fetchApi("/api/events", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Stats ──────────────────────────────────────────────────

export async function getStats(): Promise<StatsResponse> {
  return fetchApi<StatsResponse>("/stats");
}

// ─── Models ─────────────────────────────────────────────────

export async function getOllamaModels(): Promise<string[]> {
  return fetchApi<string[]>("/api/models/ollama");
}

// ─── RAG ────────────────────────────────────────────────────

export async function searchRag(
  query: string,
  projectId?: string
): Promise<{ answer: string; chunks: unknown[] }> {
  return fetchApi("/api/rag/search", {
    method: "POST",
    body: JSON.stringify({ query, project_id: projectId || "default" }),
  });
}

// ─── ForgeAI Ecosystem Metrics ────────────────────────────────

export interface ForgeAIMetricsResponse {
  success: boolean;
  data?: {
    version: string;
    timestamp: number;
    statistics: {
      signals_by_type: Record<string, number>;
      signals_by_language: Record<string, number>;
      total_sessions: number;
      overall_acceptance_rate: number;
      avg_edit_distance: number;
    };
    acceptance_rates: Array<{
      date: string;
      acceptance_rate: number;
      accepts: number;
      rejects: number;
      edits: number;
    }>;
    training: {
      active_run: Record<string, unknown> | null;
      history: Array<Record<string, unknown>>;
      schedule: { enabled: boolean; cron: string; description: string; next_run: string | null; total_runs: number };
    };
    signal_distribution: Array<{ name: string; value: number; percentage: number }>;
    total_signals: number;
    server: { uptime_seconds: number; status: string; inference_connected: boolean; db_ok: boolean };
    health: { status: string; version: string; uptime_seconds: number };
  };
  cached: boolean;
  error?: string;
  hint?: string;
}

export async function getForgeAIMetrics(): Promise<ForgeAIMetricsResponse> {
  return fetchApi<ForgeAIMetricsResponse>("/forgeai/fetch");
}
