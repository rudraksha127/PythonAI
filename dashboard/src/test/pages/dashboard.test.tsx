import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Inline module mocks — most reliable vitest pattern
vi.mock("recharts", () => ({
  LineChart: ({ children }: any) => <div data-testid="recharts-linechart">{children}</div>,
  AreaChart: ({ children }: any) => <div data-testid="recharts-areachart">{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="recharts-barchart">{children}</div>,
  Line: () => <div data-testid="recharts-line" />,
  Area: () => <div data-testid="recharts-area" />,
  Bar: () => <div data-testid="recharts-bar" />,
  XAxis: () => <div data-testid="recharts-xaxis" />,
  YAxis: () => <div data-testid="recharts-yaxis" />,
  CartesianGrid: () => <div data-testid="recharts-grid" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ResponsiveContainer: ({ children }: any) => <div data-testid="recharts-container">{children}</div>,
  Legend: () => <div data-testid="recharts-legend" />,
  PieChart: ({ children }: any) => <div data-testid="recharts-piechart">{children}</div>,
  Pie: () => <div data-testid="recharts-pie" />,
  Cell: () => <div data-testid="recharts-cell" />,
}));

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    TrendingUp: icon("trending-up"),
    Brain: icon("brain"),
    Zap: icon("zap"),
    BarChart3: icon("bar-chart-3"),
    CheckCircle2: icon("check-circle-2"),
    XCircle: icon("x-circle"),
    Edit3: icon("edit-3"),
    GitMerge: icon("git-merge"),
    Activity: icon("activity"),
    GitBranch: icon("git-branch"),
    Bot: icon("bot"),
    Settings: icon("settings"),
    Menu: icon("menu"),
    X: icon("x"),
    LayoutDashboard: icon("layout-dashboard"),
    Cpu: icon("cpu"),
    Layers: icon("layers"),
    Play: icon("play"),
    FileCode: icon("file-code"),
    AlertCircle: icon("alert-circle"),
    Terminal: icon("terminal"),
    RefreshCw: icon("refresh-cw"),
    TrendingDown: icon("trending-down"),
    Target: icon("target"),
    DollarSign: icon("dollar-sign"),
    Users: icon("users"),
    Sliders: icon("sliders"),
    Calculator: icon("calculator"),
    Database: icon("database"),
    Search: icon("search"),
    Network: icon("network"),
    Flame: icon("flame"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
    Clock: icon("clock"),
    Server: icon("server"),
  };
});

vi.mock("@/lib/api", () => ({
  getHealth: vi.fn(),
  getAcceptanceRate: vi.fn(),
  getTrainingStatus: vi.fn(),
  getCaptureStats: vi.fn(),
  getRagStats: vi.fn().mockResolvedValue(null),
  getSealStats: vi.fn().mockResolvedValue(null),
  getImprovementHeatmap: vi.fn().mockResolvedValue({
    success: false,
    data: null,
    error: "No server",
  }),
}));

import DashboardPage from "@/app/page";
import * as api from "@/lib/api";

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading skeleton initially", () => {
    (api.getHealth as any).mockReturnValue(new Promise(() => {}));
    (api.getAcceptanceRate as any).mockReturnValue(new Promise(() => {}));
    (api.getTrainingStatus as any).mockReturnValue(new Promise(() => {}));
    (api.getCaptureStats as any).mockReturnValue(new Promise(() => {}));

    const { container } = render(<DashboardPage />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders dashboard with complete data", async () => {
    (api.getHealth as any).mockResolvedValue({
      status: "ok", version: "2.0.0", timestamp: Date.now() / 1000,
      uptime_seconds: 3600, inference_connected: true, db_ok: true,
    });
    (api.getAcceptanceRate as any).mockResolvedValue({
      data: [
        { date: "2026-06-01", accepts: 10, rejects: 5, edits: 2, total: 17, acceptance_rate: 58.8, edit_rate: 11.8 },
        { date: "2026-06-02", accepts: 15, rejects: 3, edits: 1, total: 19, acceptance_rate: 78.9, edit_rate: 5.3 },
      ],
      training_markers: [],
    });
    (api.getTrainingStatus as any).mockResolvedValue({
      active_run: null,
      history: [{
        run_id: "run-1", timestamp: Date.now() / 1000 - 86400,
        model_name: "Qwen/Qwen2.5-Coder-14B", signals_used: 500,
        train_loss: 0.45, eval_loss: 1.02,
        acceptance_rate_before: 0.45, acceptance_rate_after: 0.52,
        acceptance_delta: 0.07, adapter_path: null,
      }],
    });
    (api.getCaptureStats as any).mockResolvedValue({
      signals_by_type: { accept: 25, reject: 8, edit: 3, test_pass: 10, test_fail: 2 },
      signals_by_language: { python: 30, typescript: 10, go: 8 },
      total_sessions: 5, overall_acceptance_rate: 52.1, avg_edit_distance: 0.3,
    });

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeTruthy();
    });

    // Acceptance Rate appears in both StatsCard and ROI Calculator
    const acceptRates = screen.getAllByText("Acceptance Rate");
    expect(acceptRates.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Training Runs")).toBeTruthy();
    // "Languages" appears as both a StatsCard title and section heading
    expect(screen.getAllByText("Languages").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Sessions")).toBeTruthy();

    // Model name appears in training table
    await waitFor(() => {
      expect(screen.getByText(/Qwen2\.5-Coder-14B/)).toBeTruthy();
    });

    // Signal distribution
    expect(screen.getByText("Signal Distribution")).toBeTruthy();

    // Quick action buttons
    expect(screen.getByText("View Training")).toBeTruthy();
    expect(screen.getByText("Manage Projects")).toBeTruthy();
    expect(screen.getByText("Open Agent")).toBeTruthy();
  });

  it("renders fallback state when all APIs fail (caught internally)", async () => {
    // All 4 API calls fail but are caught via .catch() in the component
    (api.getHealth as any).mockResolvedValue(null);  // caught by getHealth().catch(() => null)
    (api.getAcceptanceRate as any).mockResolvedValue({ data: [], training_markers: [] });
    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: [] });
    (api.getCaptureStats as any).mockResolvedValue(null);

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeTruthy();
    });

    // Should render with "—" for unavailable values (may appear multiple times)
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);

    // No training runs yet text
    expect(screen.getByText(/No training runs yet/)).toBeTruthy();
  });

  it("renders empty states when no data exists", async () => {
    (api.getHealth as any).mockResolvedValue({
      status: "ok", version: "2.0.0", timestamp: Date.now() / 1000,
      uptime_seconds: 3600, inference_connected: true, db_ok: true,
    });
    (api.getAcceptanceRate as any).mockResolvedValue({ data: [], training_markers: [] });
    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: [] });
    (api.getCaptureStats as any).mockResolvedValue(null);

    render(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText(/No training runs yet/)).toBeTruthy();
    });

    expect(screen.getByText(/No acceptance rate data yet/)).toBeTruthy();
  });
});
