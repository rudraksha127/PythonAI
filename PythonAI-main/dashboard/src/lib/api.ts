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
  RagCacheStats,
  RagBackendInfo,
  SealStats,
  ImprovementHeatmapData,
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

export async function getRagCacheStats(): Promise<RagCacheStats> {
  return fetchApi<RagCacheStats>("/api/rag/cache");
}

export async function getRagBackendInfo(): Promise<RagBackendInfo> {
  return fetchApi<RagBackendInfo>("/api/rag/backend");
}

export async function clearRagCache(): Promise<{ cleared: number; message: string }> {
  return fetchApi<{ cleared: number; message: string }>("/api/rag/cache/clear", { method: "POST" });
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

// ─── Ecosystem ──────────────────────────────────────────────

export interface EcosystemMetrics {
  version: string;
  timestamp: number;
  total_signals: number;
  server: {
    uptime_seconds: number;
    status: string;
    inference_connected: boolean;
    db_ok: boolean;
  };
  statistics: {
    signals_by_type: Record<string, number>;
    signals_by_language: Record<string, number>;
    total_sessions: number;
    overall_acceptance_rate: number;
    avg_edit_distance: number;
  };
  training: {
    active_run: Record<string, unknown> | null;
    history: Array<Record<string, unknown>>;
    schedule: {
      enabled: boolean;
      cron: string;
      description: string;
      next_run: string | null;
      total_runs: number;
    };
  };
  signal_distribution: Array<{ name: string; value: number; percentage: number }>;
  sync_daemon?: {
    running: boolean;
    last_sync_time: number | null;
    total_syncs: number;
    fail_count: number;
    consecutive_fails: number;
    interval: number;
    last_sync_result: string | null;
    started_at: number | null;
  };
}

export interface EcosystemFetchResponse {
  success: boolean;
  data: EcosystemMetrics | null;
  cached: boolean;
  error?: string;
  hint?: string;
}

export async function getEcosystemMetrics(): Promise<EcosystemFetchResponse> {
  return fetchApi<EcosystemFetchResponse>("/api/forgeai/ecosystem-metrics");
}

// ─── Signal Pattern Analysis (REQ-DASH-005) ─────────────────

export async function getSignalPatterns(): Promise<{
  success: boolean;
  data: import("./types").SignalPatternData | null;
  error?: string;
}> {
  try {
    const data = await fetchApi<import("./types").SignalPatternData>(
      "/api/metrics/signal-patterns"
    );
    return { success: true, data };
  } catch (e) {
    return {
      success: false,
      data: null,
      error: e instanceof Error ? e.message : "Failed to fetch signal patterns",
    };
  }
}

// ─── Improvement Heatmap (REQ-DASH-003) ─────────────────────
// NOTE: uses try/catch envelope rather than throwing, because
// the heatmap is a non-critical visual feature — the UI should
// gracefully degrade rather than throw an unhandled rejection.

export async function getImprovementHeatmap(): Promise<{
  success: boolean;
  data: ImprovementHeatmapData | null;
  error?: string;
}> {
  try {
    const data = await fetchApi<ImprovementHeatmapData>(
      "/api/metrics/improvement-heatmap"
    );
    return { success: true, data };
  } catch (e) {
    return {
      success: false,
      data: null,
      error: e instanceof Error ? e.message : "Failed to fetch heatmap data",
    };
  }
}

// ─── TTS (Test-Time Scaling) ────────────────────────────────────

export async function getTtsStatus(): Promise<import("./types").TtsStatusResponse> {
  return fetchApi<import("./types").TtsStatusResponse>("/api/tts/status");
}

export async function updateTtsConfig(
  config: Partial<import("./types").TtsConfig>
): Promise<{ status: string; config: import("./types").TtsConfig }> {
  return fetchApi<{ status: string; config: import("./types").TtsConfig }>("/api/tts/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function resetTtsStats(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>("/api/tts/reset-stats", { method: "POST" });
}

// ─── RAG Benchmark Reports ──────────────────────────────────────

export interface BenchmarkReportListItem {
  filename: string;
  path: string;
  timestamp: number;
  size_bytes: number;
}

export interface BenchmarkListResponse {
  success: boolean;
  reports: BenchmarkReportListItem[];
  error?: string;
}

export interface BenchmarkReportResponse {
  success: boolean;
  report: import("./types").BenchmarkReport | null;
  error?: string;
}

export async function getBenchmarkReports(): Promise<BenchmarkListResponse> {
  return fetchApi<BenchmarkListResponse>("/api/benchmark/reports");
}

export async function getBenchmarkReport(
  filename: string
): Promise<BenchmarkReportResponse> {
  return fetchApi<BenchmarkReportResponse>(
    `/api/benchmark/report/${encodeURIComponent(filename)}`
  );
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
