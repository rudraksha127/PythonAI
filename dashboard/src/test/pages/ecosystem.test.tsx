import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ─── Mock lucide-react ──────────────────────────────────────────

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    Server: icon("server"),
    Activity: icon("activity"),
    TrendingUp: icon("trending-up"),
    Brain: icon("brain"),
    Zap: icon("zap"),
    RefreshCw: icon("refresh-cw"),
    BarChart3: icon("bar-chart-3"),
    Cpu: icon("cpu"),
    Clock: icon("clock"),
    Database: icon("database"),
    XCircle: icon("x-circle"),
    Wifi: icon("wifi"),
    WifiOff: icon("wifi-off"),
    Gauge: icon("gauge"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
    Layers: icon("layers"),
    Bot: icon("bot"),
    Monitor: icon("monitor"),
    Globe: icon("globe"),
    Terminal: icon("terminal"),
    ArrowDown: icon("arrow-down"),
    GitBranch: icon("git-branch"),
    Library: icon("library"),
    BookOpen: icon("book-open"),
    CheckCircle2: icon("check-circle-2"),
    Edit3: icon("edit-3"),
    GitMerge: icon("git-merge"),
  };
});

// ─── Mock API module ────────────────────────────────────────────
// NOTE: vi.hoisted is required because vi.mock gets hoisted above const declarations
const mockGetEcosystemMetrics = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  getEcosystemMetrics: mockGetEcosystemMetrics,
}));

import EcosystemPage from "@/app/ecosystem/page";

// ─── Sample data ────────────────────────────────────────────────

const MOCK_METRICS = {
  success: true,
  cached: false,
  data: {
    version: "2.0.0",
    timestamp: Date.now() / 1000,
    total_signals: 100,
    server: {
      uptime_seconds: 86400,
      status: "ok",
      inference_connected: true,
      db_ok: true,
    },
    statistics: {
      signals_by_type: { accept: 45, reject: 20, edit: 15, pr_merge: 10, test_pass: 8, test_fail: 2 },
      signals_by_language: { python: 40, typescript: 30, go: 20, rust: 10 },
      total_sessions: 12,
      overall_acceptance_rate: 55.0,
      avg_edit_distance: 0.35,
    },
    training: {
      active_run: null,
      history: [
        {
          run_id: "run-001",
          timestamp: Date.now() / 1000 - 86400 * 2,
          model_name: "Qwen/Qwen2.5-Coder-7B-Instruct",
          signals_used: 250,
          train_loss: 0.42,
          eval_loss: 1.05,
          acceptance_rate_before: 0.45,
          acceptance_rate_after: 0.52,
          acceptance_delta: 0.07,
          adapter_path: null,
        },
      ],
      schedule: {
        enabled: true,
        cron: "0 2 * * 1",
        description: "Weekly — Monday at 02:00",
        next_run: "2026-06-15T02:00:00",
        total_runs: 5,
      },
    },
    signal_distribution: [
      { name: "Accept", value: 45, percentage: 45.0 },
      { name: "Reject", value: 20, percentage: 20.0 },
      { name: "Edit", value: 15, percentage: 15.0 },
      { name: "Pr_merge", value: 10, percentage: 10.0 },
      { name: "Test_pass", value: 8, percentage: 8.0 },
      { name: "Test_fail", value: 2, percentage: 2.0 },
    ],
    health: { status: "ok", version: "2.0.0", uptime_seconds: 86400 },
    sync_daemon: {
      running: true,
      last_sync_time: Date.now() / 1000 - 15,
      total_syncs: 42,
      fail_count: 1,
      consecutive_fails: 0,
      interval: 30,
      last_sync_result: "success",
      started_at: Date.now() / 1000 - 3600,
    },
  },
};

// ─── Tests ──────────────────────────────────────────────────────

describe("Ecosystem Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock fetch for service pings — all fail by default (services offline)
    global.fetch = vi.fn().mockRejectedValue(new Error("Unreachable"));
  });

  it("renders loading skeleton initially", () => {
    // Keep promise pending so it stays in loading state
    mockGetEcosystemMetrics.mockReturnValue(new Promise(() => {}));

    const { container } = render(<EcosystemPage />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders error banner when API call fails", async () => {
    // Reject the promise so the catch() block sets the error state
    mockGetEcosystemMetrics.mockRejectedValue(new Error("Failed to fetch ecosystem data"));

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to fetch ecosystem data/)).toBeTruthy();
    });

    // Still renders the page header
    expect(screen.getByText("Ecosystem Status")).toBeTruthy();
  });

  it("renders not connected state when PythonAI is unreachable with retry button and services", async () => {
    mockGetEcosystemMetrics.mockResolvedValue({
      success: false,
      data: null,
      cached: false,
    });

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("PythonAI Server Not Reachable")).toBeTruthy();
    });

    // Should show retry button and services count
    expect(screen.getByText(/Retry Connection/)).toBeTruthy();
    // Service cards are still rendered (superview-sh is 9th service)
    expect(screen.getAllByText("PythonAI").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Superview-sh")).toBeTruthy();
  });

  it("renders complete ecosystem metrics when data is available", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("Ecosystem Status")).toBeTruthy();
    });

    // Header + PythonAI Live Metrics sections
    expect(screen.getByText("Service Health")).toBeTruthy();
    expect(screen.getByText("PythonAI Live Metrics")).toBeTruthy();
    expect(screen.getByText("Signal & Language Distribution")).toBeTruthy();

    // Quick stat tiles
    expect(screen.getByText("55.0%")).toBeTruthy();
    expect(screen.getByText("100")).toBeTruthy();

    // Training section
    expect(screen.getByText("Training Schedule")).toBeTruthy();
  });

  it("renders auto-refresh toggle and refresh button", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("Auto On")).toBeTruthy();
    });

    expect(screen.getByText("Refresh")).toBeTruthy();
  });

  it("renders cached data indicator", async () => {
    mockGetEcosystemMetrics.mockResolvedValue({
      ...MOCK_METRICS,
      cached: true,
    });

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText(/Showing cached data/)).toBeTruthy();
    });

    // Metrics still render even when cached
    expect(screen.getByText("PythonAI Live Metrics")).toBeTruthy();
  });

  it("renders signal and language distribution sections", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("By Signal Type")).toBeTruthy();
    });

    expect(screen.getByText("By Language")).toBeTruthy();

    // Individual distribution items
    expect(screen.getByText("Accept")).toBeTruthy();
    expect(screen.getByText("Reject")).toBeTruthy();
    expect(screen.getByText("python")).toBeTruthy();
    expect(screen.getByText("typescript")).toBeTruthy();
  });

  it("renders training schedule details", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("Training Schedule")).toBeTruthy();
    });

    expect(screen.getByText("Enabled")).toBeTruthy();
    expect(screen.getByText("Schedule")).toBeTruthy();
    expect(screen.getByText("Total Runs")).toBeTruthy();
    expect(screen.getByText("Next Run")).toBeTruthy();

    // Schedule values
    expect(screen.getByText("Yes")).toBeTruthy();
    expect(screen.getByText("Weekly — Monday at 02:00")).toBeTruthy();
  });

  it("renders system health status indicators", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("System Health")).toBeTruthy();
    });

    expect(screen.getByText("Inference")).toBeTruthy();
    expect(screen.getByText("Database")).toBeTruthy();
    expect(screen.getByText(/v2\.0\.0/)).toBeTruthy();
  });

  it("renders architecture overview section", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("Architecture Overview")).toBeTruthy();
    });

    // Layer names from ArchitectureFlow
    expect(screen.getByText("Layer 1: User Interfaces")).toBeTruthy();
    expect(screen.getByText("Layer 2: Agent Orchestration")).toBeTruthy();
    expect(screen.getByText("Layer 3: Core Engine (PythonAI)")).toBeTruthy();
    expect(screen.getByText("Layer 4: Infrastructure")).toBeTruthy();

    // Data Flow section
    expect(screen.getByText("Data Flow")).toBeTruthy();
  });

  // NOTE: both success=false + data=null and success=true + data=null render the same
  // "PythonAI Server Not Reachable" fallback — the component checks data, not success.
  // This test is kept as a regression guard for the null-data path.
  it("renders fallback when API returns null data (success or not)", async () => {
    mockGetEcosystemMetrics.mockResolvedValue({
      success: true,
      data: null,
      cached: false,
    });

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("PythonAI Server Not Reachable")).toBeTruthy();
    });
  });

  it("renders architecture with research backing details", async () => {
    mockGetEcosystemMetrics.mockResolvedValue(MOCK_METRICS);

    render(<EcosystemPage />);

    await waitFor(() => {
      expect(screen.getByText("Architecture Overview")).toBeTruthy();
    });

    // Research backing should be a <details> element
    expect(screen.getByText("Research Backing")).toBeTruthy();
    expect(screen.getByText(/EMNLP 2025/)).toBeTruthy();
    expect(screen.getByText(/MIT SEAL architecture/)).toBeTruthy();
  });
});
