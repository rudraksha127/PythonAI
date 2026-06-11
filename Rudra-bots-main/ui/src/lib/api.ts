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
