import type {
  HealthCheck,
  AcceptanceRateResponse,
  TrainingStatusResponse,
  CaptureStats,
  MetricsSummary,
  Project,
  EventPayload,
  EventResponse,
  RagStats,
  SealStats,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";

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

// ─── Acceptance Rate ────────────────────────────────────────

export async function getAcceptanceRate(
  projectId?: string,
  weeks: number = 12
): Promise<AcceptanceRateResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  params.set("weeks", weeks.toString());
  return fetchApi<AcceptanceRateResponse>(
    `/api/metrics/acceptance-rate?${params.toString()}`
  );
}

// ─── Training ───────────────────────────────────────────────

export async function getTrainingStatus(
  projectId?: string
): Promise<TrainingStatusResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const qs = params.toString();
  return fetchApi<TrainingStatusResponse>(
    `/api/training/status${qs ? `?${qs}` : ""}`
  );
}

export async function triggerTraining(
  projectId?: string
): Promise<{ run_id: string; status: string }> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const qs = params.toString();
  return fetchApi<{ run_id: string; status: string }>(
    `/api/training/trigger${qs ? `?${qs}` : ""}`,
    { method: "POST" }
  );
}

// ─── Events ─────────────────────────────────────────────────

export async function captureEvent(
  payload: EventPayload
): Promise<EventResponse> {
  return fetchApi<EventResponse>("/api/events", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Stats ──────────────────────────────────────────────────

export async function getCaptureStats(): Promise<CaptureStats> {
  return fetchApi<CaptureStats>("/stats");
}

export async function getMetrics(): Promise<MetricsSummary> {
  return fetchApi<MetricsSummary>("/metrics");
}

// ─── Projects ───────────────────────────────────────────────

export async function getProjects(): Promise<Project[]> {
  return fetchApi<Project[]>("/api/projects");
}

export async function createProject(
  name: string,
  repoPath: string
): Promise<Project> {
  return fetchApi<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, repo_path: repoPath }),
  });
}

// ─── SEAL ───────────────────────────────────────────────────

export async function getSealStats(): Promise<SealStats> {
  return fetchApi<SealStats>("/api/seal/status");
}

export async function triggerSealCycle(
  dryRun: boolean = true
): Promise<{ seal: { status: string; action?: Record<string, unknown> } }> {
  return fetchApi<{ seal: { status: string; action?: Record<string, unknown> } }>(
    `/api/seal/cycle?dry_run=${dryRun}`,
    { method: "POST" }
  );
}

// ─── RAG ────────────────────────────────────────────────────

export async function getRagStats(): Promise<RagStats> {
  return fetchApi<RagStats>("/api/rag/stats");
}

export async function indexProject(
  projectId: string,
  repoPath: string,
  forceReindex: boolean = false
): Promise<{ job_id: string; status: string }> {
  return fetchApi<{ job_id: string; status: string }>("/api/rag/index", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      repo_path: repoPath,
      force_reindex: forceReindex,
    }),
  });
}

export async function searchRag(
  query: string,
  projectId: string
): Promise<{ chunks: unknown[]; answer: string }> {
  return fetchApi<{ chunks: unknown[]; answer: string }>("/api/rag/search", {
    method: "POST",
    body: JSON.stringify({ query, project_id: projectId }),
  });
}

// ─── WebSocket ─────────────────────────────────────────────

export function createTrainingWs(): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/ws/training-progress`);
}

export function createEventsWs(): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/ws/events`);
}
