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
  chunks: number;
  db_path: string;
  embedding_model: string;
  has_bm25: boolean;
  has_knowledge_graph: boolean;
  last_indexed: string | null;
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

export type WsMessage = WsEventCaptured | WsTrainingProgress | WsTrainingStarted;

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
