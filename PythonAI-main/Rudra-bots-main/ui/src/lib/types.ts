// ─── Chat Messages ──────────────────────────────────────────────

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  model?: string;
  sources?: { title: string; url?: string }[];
}

// ─── Chat Sessions ──────────────────────────────────────────────

export interface ChatSession {
  id: string;
  title: string;
  model: string;
  messages: Message[];
  created_at: number;
  updated_at: number;
}

// ─── Models ─────────────────────────────────────────────────────

export interface AIModel {
  id: string;
  name: string;
  provider: string;
  description: string;
  context_window: number;
  capabilities: {
    vision: boolean;
    reasoning: boolean;
    coding: boolean;
  };
  available: boolean;
}

// ─── API Responses ──────────────────────────────────────────────

export interface HealthCheck {
  status: string;
  version: string;
  timestamp: number;
  uptime_seconds: number;
}

export interface StatsResponse {
  signals_by_type: Record<string, number>;
  signals_by_language: Record<string, number>;
  total_sessions: number;
  overall_acceptance_rate: number;
}

export interface ChatResponse {
  answer: string;
  sources?: { title: string; url?: string }[];
  model?: string;
}

// ─── Theme ──────────────────────────────────────────────────────

export interface ThemeConfig {
  name: string;
  colors: {
    bg: string;
    fg: string;
    panel: string;
    border: string;
    accent: string;
  };
  font?: "mono" | "sans" | "serif";
  density?: "comfortable" | "compact" | "spacious";
}

export interface ThemePreset {
  name: string;
  colors: string[];
  accent: string;
}
