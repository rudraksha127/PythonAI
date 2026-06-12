import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ─── Recharts mock ──────────────────────────────────────────────

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

// ─── Lucide-react mock ──────────────────────────────────────────

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    BarChart3: icon("bar-chart-3"),
    TrendingUp: icon("trending-up"),
    TrendingDown: icon("trending-down"),
    Zap: icon("zap"),
    Layers: icon("layers"),
    Activity: icon("activity"),
    RefreshCw: icon("refresh-cw"),
    Flame: icon("flame"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
  };
});

// ─── API mock ────────────────────────────────────────────────────

const mockGetImprovementHeatmap = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({
  getImprovementHeatmap: () => mockGetImprovementHeatmap(),
}));

import ImprovementHeatmap from "@/components/ImprovementHeatmap";

// ─── Sample Data ─────────────────────────────────────────────────

const SAMPLE_HEATMAP_DATA = {
  version: "2.0.0",
  timestamp: Date.now() / 1000,
  languages: [
    { name: "python", signal_count: 15, signal_pct: 60.0, rate_before: 40.0, rate_after: 52.0, delta: 12.0 },
    { name: "typescript", signal_count: 10, signal_pct: 40.0, rate_before: 45.0, rate_after: 53.0, delta: 8.0 },
  ],
  patterns: [
    { name: "Accepted Suggestions", key: "accept", count: 10, percentage: 40.0, rate_before: 35.0, rate_after: 45.0, delta: 10.0 },
    { name: "Rejected Suggestions", key: "reject", count: 8, percentage: 32.0, rate_before: 37.0, rate_after: 33.0, delta: -4.0 },
  ],
  weekly_data: [
    { period: "Week 1", date: "2026-06-01", acceptance_rate: 40.0, accepts: 4, rejects: 4, edits: 2, total: 10 },
    { period: "Week 2", date: "2026-06-08", acceptance_rate: 52.0, accepts: 6, rejects: 3, edits: 1, total: 10 },
  ],
  slots: {
    overall_delta: 12.0,
    baseline_rate: 40.0,
    current_rate: 50.0,
    target_rate: 59.0,
    heat_index: 42.5,
    training_run_count: 3,
    language_count: 2,
    total_signals_used: 25,
  },
  language_weekly_trend: [
    { language: "python", trend: [{ week: 1, rate: 40.0 }, { week: 2, rate: 52.0 }] },
    { language: "typescript", trend: [{ week: 1, rate: 45.0 }, { week: 2, rate: 53.0 }] },
  ],
  training_runs: [
    { run_id: "run-1", timestamp: Date.now() / 1000 - 86400, delta: 5.0, signals_used: 100, model: "Qwen2.5-Coder-7B" },
    { run_id: "run-2", timestamp: Date.now() / 1000 - 172800, delta: 3.0, signals_used: 80, model: "Qwen2.5-Coder-7B" },
  ],
};

// ─── Tests ───────────────────────────────────────────────────────

describe("ImprovementHeatmap Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading skeleton on mount", () => {
    mockGetImprovementHeatmap.mockReturnValue(new Promise(() => {}));

    const { container } = render(<ImprovementHeatmap />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders error state when API returns error", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: false,
      data: null,
      error: "Server unreachable",
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Server unreachable")).toBeTruthy();
    });
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("renders fallback message when API returns no data (null error)", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: false,
      data: null,
      error: null,
    });

    render(<ImprovementHeatmap />);

    // Component sets error = result.error || "No data", so "No data" is shown
    await waitFor(() => {
      expect(screen.getByText("No data")).toBeTruthy();
    });
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("renders heatmap with complete data when API succeeds", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: SAMPLE_HEATMAP_DATA,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });

    // Slots overview
    expect(screen.getByText("Overall Delta")).toBeTruthy();
    expect(screen.getByText("Current Rate")).toBeTruthy();
    expect(screen.getByText("Target Rate")).toBeTruthy();
    expect(screen.getByText("Training Runs")).toBeTruthy();

    // Language grid header
    expect(screen.getByText("Language Improvement Grid")).toBeTruthy();

    // Language names appear in both grid and per-language trend sections
    const pythonTexts = screen.getAllByText("python");
    expect(pythonTexts.length).toBeGreaterThanOrEqual(1);
    const tsTexts = screen.getAllByText("typescript");
    expect(tsTexts.length).toBeGreaterThanOrEqual(1);

    // Pattern section
    expect(screen.getByText("Signal Pattern Trends")).toBeTruthy();
    expect(screen.getByText("Accepted Suggestions")).toBeTruthy();
    expect(screen.getByText("Rejected Suggestions")).toBeTruthy();

    // Training timeline
    expect(screen.getByText("Training Run Impact")).toBeTruthy();

    // Per-language weekly trend
    expect(screen.getByText("Per-Language Weekly Trend")).toBeTruthy();

    // Version
    expect(screen.getByText(/v2\.0\.0/)).toBeTruthy();

    // REQ label
    expect(screen.getByText("REQ-DASH-003")).toBeTruthy();
  });

  it("renders heat index gauge with correct rounded value", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: SAMPLE_HEATMAP_DATA,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Moderate Improvement")).toBeTruthy();
    });

    // heat_index = 42.5, Math.round(42.5) = 43 in JS
    expect(screen.getByText("43")).toBeTruthy();
  });

  it("renders delta values with correct formatting", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: SAMPLE_HEATMAP_DATA,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });

    // "+12.0%" appears multiple times (Overall Delta slot + python delta)
    // Just check it exists at least once
    const deltaTexts = screen.getAllByText("+12.0%");
    expect(deltaTexts.length).toBeGreaterThanOrEqual(1);

    // Also check negative delta renders
    expect(screen.getByText("-4.0pp")).toBeTruthy();
  });

  it("collapses and expands content on header button click", async () => {
    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: SAMPLE_HEATMAP_DATA,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Moderate Improvement")).toBeTruthy();
    });

    // Click the collapsible header to collapse
    const headers = screen.getAllByText("Model Improvement Heatmap");
    expect(headers.length).toBeGreaterThanOrEqual(1);
    headers[0].click();

    // Content should now be hidden
    await waitFor(() => {
      expect(screen.queryByText("Moderate Improvement")).toBeNull();
    });
    expect(screen.queryByText("Language Improvement Grid")).toBeNull();

    // Click the chevron-down icon which appears when collapsed
    const chevronIcon = screen.getByTestId("icon-chevron-down");
    chevronIcon.click();

    await waitFor(() => {
      expect(screen.getByText("Moderate Improvement")).toBeTruthy();
    });
  });

  it("handles empty languages array", async () => {
    const emptyData = {
      ...SAMPLE_HEATMAP_DATA,
      languages: [],
      language_weekly_trend: [],
    };

    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: emptyData,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });

    // Language sections should not render when languages is empty
    expect(screen.queryByText("Language Improvement Grid")).toBeNull();
    expect(screen.queryByText("Per-Language Weekly Trend")).toBeNull();
  });

  it("handles empty patterns array", async () => {
    const noPatternsData = {
      ...SAMPLE_HEATMAP_DATA,
      patterns: [],
    };

    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: noPatternsData,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });

    expect(screen.queryByText("Signal Pattern Trends")).toBeNull();
  });

  it("handles empty training runs", async () => {
    const noRunsData = {
      ...SAMPLE_HEATMAP_DATA,
      training_runs: [],
    };

    mockGetImprovementHeatmap.mockResolvedValue({
      success: true,
      data: noRunsData,
    });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });

    expect(screen.queryByText("Training Run Impact")).toBeNull();
  });

  it("recovers from error via retry button", async () => {
    mockGetImprovementHeatmap
      .mockResolvedValueOnce({
        success: false,
        data: null,
        error: "Connection failed",
      })
      .mockResolvedValueOnce({
        success: true,
        data: SAMPLE_HEATMAP_DATA,
      });

    render(<ImprovementHeatmap />);

    await waitFor(() => {
      expect(screen.getByText("Connection failed")).toBeTruthy();
    });

    screen.getByText("Retry").click();

    await waitFor(() => {
      expect(screen.getByText("Model Improvement Heatmap")).toBeTruthy();
    });
  });
});
