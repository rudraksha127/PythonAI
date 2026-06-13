// ─── API Response Types ─────────────────────────────────────────

export interface HealthCheck {
  status: string;
  version: string;
  timestamp: number;
  uptime_seconds: number;
  inference_connected: boolean;
  db_ok: boolean;
}

// ─── Acceptance Rate ────────────────────────────────────────────

export interface AcceptanceRatePoint {
  date: string;
  accepts: number;
  rejects: number;
  edits: number;
  total: number;
  acceptance_rate: number;
  edit_rate: number;
}

export interface AcceptanceRateResponse {
  data: AcceptanceRatePoint[];
  training_markers: TrainingMarker[];
}

export interface TrainingMarker {
  timestamp: number;
  delta: number;
  signals: number;
}

// ─── Training ───────────────────────────────────────────────────

export interface TrainingRun {
  run_id: string;
  timestamp: number;
  model_name: string;
  signals_used: number;
  train_loss: number | null;
  eval_loss: number | null;
  acceptance_rate_before: number;
  acceptance_rate_after: number;
  acceptance_delta: number;
  adapter_path: string | null;
}

export interface TrainingStatusResponse {
  active_run: ActiveTrainingRun | null;
  history: TrainingRun[];
}

export interface ActiveTrainingRun {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  started_at: number;
  progress: number;
}

// ─── Events ─────────────────────────────────────────────────────

export interface EventPayload {
  event_type: "accept" | "reject" | "edit" | "pr_merge" | "test_pass" | "test_fail";
  session_id: string;
  project_id: string;
  file_path: string;
  line_number: number;
  language: string;
  framework?: string;
  project_type: string;
  suggestion: string;
  suggestion_metadata?: Record<string, unknown>;
  context_before?: string;
  context_after?: string;
  full_context?: string;
  final_code?: string;
  edit_distance?: number;
  developer_id?: string;
}

export interface EventResponse {
  event_id: string;
  captured: boolean;
}

// ─── Stats / Metrics ────────────────────────────────────────────

export interface CaptureStats {
  signals_by_type: Record<string, number>;
  signals_by_language: Record<string, number>;
  total_sessions: number;
  overall_acceptance_rate: number;
  avg_edit_distance: number;
}

export interface MetricsSummary {
  total_requests?: number;
  avg_latency_ms?: number;
  error_rate?: number;
  requests_by_endpoint?: Record<string, number>;
}

// ─── Projects ───────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  repo_path: string;
  languages: string[];
  rag_indexed_at?: string;
  current_adapter_version: number;
  training_phase: number;
  base_model: string;
  training_schedule: string;
}

// ─── SEAL Status ──────────────────────────────────────────────────

export interface SealStats {
  system: string;
  cycle: number;
  status: "active" | "idle";
  curriculum_state: {
    total_actions_taken: number;
    domains_explored: number;
    difficulties_tried: Record<string, number>;
  };
  meta_learning: {
    ready_to_train: boolean;
    reward_count: number;
    total_rewards: number;
  };
  best_action: {
    action: string;
    domain: string;
    reward_delta: number;
    cycle: number;
    difficulty: string;
  } | null;
  config: Record<string, unknown>;
}

// ─── RAG Status ───────────────────────────────────────────────────

export interface RagStats {
  status: string;
  backend?: string;
  chunks: number;
  db_path: string;
  embedding_model: string;
  has_bm25: boolean;
  has_knowledge_graph: boolean;
  last_indexed: string | null;
  // LightRAG-specific fields
  queries_run?: number;
  avg_query_ms?: number;
  files_indexed?: number;
  insert_errors?: number;
  query_errors?: number;
}

export interface RagCacheStats {
  backend: string;
  cache_active: boolean;
  size: number;
  maxsize: number;
  ttl: number;
  hits: number;
  misses: number;
  hit_rate: number;
}

export interface RagBackendInfo {
  backend: string;
  lightrag_available: boolean;
  lightrag_stats: Record<string, unknown> | null;
  chroma_available: boolean;
}

// ─── WebSocket Messages ─────────────────────────────────────────

export interface WsEventCaptured {
  type: "event_captured";
  event_type: string;
  signal_id: string;
  timestamp: number;
}

export interface WsTrainingProgress {
  type: "training_progress";
  run_id: string;
  progress: number;
  loss?: number;
  step?: number;
}

export interface WsTrainingStarted {
  type: "training_started";
  run_id: string;
}

export interface WsSyncStatus {
  type: "sync_status";
  status: string;
  last_sync: number;
  total_syncs: number;
}

export type WsMessage = WsEventCaptured | WsTrainingProgress | WsTrainingStarted | WsSyncStatus;

// ─── Signal Pattern Analysis (REQ-DASH-005) ────────────────────

export interface SignalTypeInfo {
  key: string;
  label: string;
  count: number;
  percentage: number;
}

export interface LanguageRateInfo {
  language: string;
  signal_count: number;
  signal_pct: number;
  acceptance_rate: number;
  accepts: number;
  rejects: number;
}

export interface WeeklySignalTrendPoint {
  period: string;
  date: string;
  acceptance_rate: number;
  accepts: number;
  rejects: number;
  edits: number;
  total: number;
}

export interface RejectionPattern {
  language: string;
  signal_count: number;
  rejection_rate: number;
  acceptance_rate: number;
  severity: "high" | "medium" | "low";
}

export interface DeveloperStat {
  developer_id: string;
  total_signals: number;
  accepts: number;
  rejects: number;
  edits: number;
  acceptance_rate: number;
  is_anonymous: boolean;
}

export interface SignalPatternOverall {
  total_signals: number;
  total_sessions: number;
  languages_count: number;
  developers_count: number;
  overall_acceptance_rate: number;
  avg_edit_distance: number;
  trend_direction: "up" | "down" | "stable";
  trend_value: number;
}

export interface SignalPatternData {
  version: string;
  timestamp: number;
  signal_types: SignalTypeInfo[];
  language_rates: LanguageRateInfo[];
  weekly_trend: WeeklySignalTrendPoint[];
  rejection_patterns: RejectionPattern[];
  developer_stats: DeveloperStat[];
  overall: SignalPatternOverall;
}

// ─── Improvement Heatmap (REQ-DASH-003) ────────────────────────

export interface HeatmapLanguage {
  name: string;
  signal_count: number;
  signal_pct: number;
  rate_before: number;
  rate_after: number;
  delta: number;
}

export interface HeatmapPattern {
  name: string;
  key: string;
  count: number;
  percentage: number;
  rate_before: number;
  rate_after: number;
  delta: number;
}

export interface HeatmapWeeklyPoint {
  period: string;
  date: string;
  acceptance_rate: number;
  accepts: number;
  rejects: number;
  edits: number;
  total: number;
}

export interface HeatmapSlots {
  overall_delta: number;
  baseline_rate: number;
  current_rate: number;
  target_rate: number;
  heat_index: number;
  training_run_count: number;
  language_count: number;
  total_signals_used: number;
}

export interface HeatmapTrend {
  week: number;
  rate: number;
}

export interface LanguageWeeklyTrend {
  language: string;
  trend: HeatmapTrend[];
}

export interface HeatmapTrainingRun {
  run_id: string;
  timestamp: number;
  delta: number;
  signals_used: number;
  model: string;
}

export interface ImprovementHeatmapData {
  version: string;
  timestamp: number;
  languages: HeatmapLanguage[];
  patterns: HeatmapPattern[];
  weekly_data: HeatmapWeeklyPoint[];
  slots: HeatmapSlots;
  language_weekly_trend: LanguageWeeklyTrend[];
  training_runs: HeatmapTrainingRun[];
}

// ─── TTS (Test-Time Scaling) Status ────────────────────────────────

export interface TtsConfig {
  enabled: boolean;
  complexity_threshold: number;
  num_initial_rollouts: number;
  num_pdr_rollouts: number;
}

export interface TtsGeneratorStats {
  total_rollouts: number;
  total_tokens: number;
  total_elapsed_ms: number;
}

export interface TtsTournamentStats {
  rounds: number;
  comparisons: number;
  judge_tokens: number;
}

export interface TtsPdrStats {
  pdr_rounds: number;
  pdr_tokens: number;
}

export interface TtsStats {
  total_pipelines: number;
  hard_tasks: number;
  medium_tasks: number;
  fast_tasks: number;
  total_tokens_used: number;
  total_elapsed_ms: number;
  avg_complexity_score: number;
  complexity_threshold: number;
  config: TtsConfig;
  generator: TtsGeneratorStats;
  tournament: TtsTournamentStats;
  pdr: TtsPdrStats;
}

export interface TtsStatusResponse {
  enabled: boolean;
  pipeline_initialized: boolean;
  config: TtsConfig;
  stats: TtsStats | Record<string, never>;
}

// ─── RAG Benchmark Report ──────────────────────────────────────────

export interface BenchmarkReport {
  version: string;
  timestamp: number;
  config: {
    model: string;
    embed_model: string;
    num_queries: number;
    test_queries: string[];
    cache_test_queries: string[];
  };
  timing: {
    seed_seconds: number;
    cold_queries_seconds: number;
    concurrent_seconds?: number;
    cache_queries_seconds: number;
    total_seconds: number;
  };
  comparisons: Record<string, number>;
  stats: Record<string, {
    avg_total_ms: number;
    min_total_ms: number;
    max_total_ms: number;
    p50_ms: number;
    p95_ms: number;
    avg_retrieval_ms: number;
    avg_answer_len: number;
    count: number;
    errors: number;
  }>;
  details: Array<{
    query: string;
    backend: string;
    mode: string;
    total_ms: number;
    retrieval_ms: number;
    answer_len: number;
    error: string | null;
  }>;
  throughput: {
    concurrent_time_seconds: number;
    results: Array<{
      backend: string;
      concurrency: number;
      total_queries: number;
      wall_time_seconds: number;
      qps: number;
      avg_latency_ms: number;
      p50_ms: number;
      p95_ms: number;
      min_ms: number;
      max_ms: number;
      errors: number;
    }>;
    scaling: Record<string, Record<string, number>>;
    best_qps: number;
    best_backend: string;
    best_concurrency: number;
  };
  cache_stats_from_adapter?: {
    size: number;
    maxsize: number;
    ttl: number;
    hits: number;
    misses: number;
    hit_rate: number;
  };
  per_mode_queries?: Record<string, number>;
}

export interface BenchmarkReportListItem {
  filename: string;
  timestamp: number;
  size_bytes: number;
  report?: BenchmarkReport;
}

export interface BenchmarkListResponse {
  success: boolean;
  reports: BenchmarkReportListItem[];
  error?: string;
}

// ─── UI State ───────────────────────────────────────────────────

export interface PageMeta {
  title: string;
  description: string;
}

export const PAGE_META: Record<string, PageMeta> = {
  dashboard: {
    title: "Dashboard",
    description: "ForgeAI acceptance rate, training status, and system health",
  },
  training: {
    title: "Training",
    description: "Training run history, monitoring, and manual triggers",
  },
  projects: {
    title: "Projects",
    description: "Manage your code projects and RAG indices",
  },
  agent: {
    title: "Agent",
    description: "Chat with the ForgeAI coding agent",
  },
  settings: {
    title: "Settings",
    description: "Configure model, training, and system preferences",
  },
};
