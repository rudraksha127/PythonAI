import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

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
    Activity: icon("activity"),
    RefreshCw: icon("refresh-cw"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
    XCircle: icon("x-circle"),
    CheckCircle2: icon("check-circle-2"),
    Edit3: icon("edit-3"),
    GitMerge: icon("git-merge"),
    Users: icon("users"),
    Code2: icon("code-2"),
    AlertTriangle: icon("alert-triangle"),
    Shield: icon("shield"),
    UserCheck: icon("user-check"),
  };
});

// ─── API mock ────────────────────────────────────────────────────

const mockGetSignalPatterns = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  getSignalPatterns: () => mockGetSignalPatterns(),
}));

import SignalPatternAnalysis from "@/components/SignalPatternAnalysis";

// ─── Sample Data ─────────────────────────────────────────────────

const SAMPLE_DATA = {
  version: "2.0.0",
  timestamp: Date.now() / 1000,
  signal_types: [
    { key: "accept", label: "Accepted", count: 120, percentage: 60.0 },
    { key: "reject", label: "Rejected", count: 40, percentage: 20.0 },
    { key: "edit", label: "Edited", count: 30, percentage: 15.0 },
    { key: "pr_merge", label: "PR Merges", count: 10, percentage: 5.0 },
  ],
  language_rates: [
    { language: "python", signal_count: 80, signal_pct: 40.0, acceptance_rate: 65.0, accepts: 52, rejects: 28 },
    { language: "typescript", signal_count: 60, signal_pct: 30.0, acceptance_rate: 72.0, accepts: 43, rejects: 17 },
    { language: "go", signal_count: 40, signal_pct: 20.0, acceptance_rate: 55.0, accepts: 22, rejects: 18 },
  ],
  weekly_trend: [
    { period: "Week 1", date: "2026-06-01", acceptance_rate: 58.8, accepts: 10, rejects: 5, edits: 2, total: 17 },
    { period: "Week 2", date: "2026-06-08", acceptance_rate: 65.0, accepts: 15, rejects: 4, edits: 3, total: 22 },
    { period: "Week 3", date: "2026-06-15", acceptance_rate: 72.0, accepts: 18, rejects: 3, edits: 1, total: 22 },
  ],
  rejection_patterns: [
    { language: "python", signal_count: 80, rejection_rate: 35.0, acceptance_rate: 65.0, severity: "medium" },
    { language: "go", signal_count: 40, rejection_rate: 45.0, acceptance_rate: 55.0, severity: "medium" },
    { language: "typescript", signal_count: 60, rejection_rate: 28.0, acceptance_rate: 72.0, severity: "low" },
  ],
  developer_stats: [
    { developer_id: "dev-abc123...", total_signals: 50, accepts: 35, rejects: 10, edits: 5, acceptance_rate: 70.0, is_anonymous: false },
    { developer_id: "dev-def456...", total_signals: 30, accepts: 15, rejects: 10, edits: 5, acceptance_rate: 50.0, is_anonymous: false },
    { developer_id: "anon-xyz...", total_signals: 20, accepts: 10, rejects: 6, edits: 4, acceptance_rate: 50.0, is_anonymous: true },
  ],
  overall: {
    total_signals: 200,
    total_sessions: 15,
    languages_count: 3,
    developers_count: 3,
    overall_acceptance_rate: 65.0,
    avg_edit_distance: 0.35,
    trend_direction: "up" as const,
    trend_value: 13.2,
  },
};

// ─── Tests ───────────────────────────────────────────────────────

describe("SignalPatternAnalysis Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading ──────────────────────────────────────────────────

  it("renders loading skeleton on mount", () => {
    mockGetSignalPatterns.mockReturnValue(new Promise(() => {}));

    const { container } = render(<SignalPatternAnalysis />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  // ── Error State ──────────────────────────────────────────────

  it("renders error state when API fails", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: false,
      data: null,
      error: "Server unreachable",
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Server unreachable")).toBeTruthy();
    });

    // Retry button should be present
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  // ── Error state from exception ───────────────────────────────

  it("renders fallback when API result has no data", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: null,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("No data")).toBeTruthy();
    });
  });

  // ── Complete Data ────────────────────────────────────────────

  it("renders all sections with complete data", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Overall metrics bar
    expect(screen.getByText("Acceptance Rate")).toBeTruthy();
    expect(screen.getByText("Total Signals")).toBeTruthy();
    expect(screen.getByText("Languages")).toBeTruthy();
    expect(screen.getByText("Developers")).toBeTruthy();

    // Signal type distribution
    expect(screen.getByText("Signal Type Distribution")).toBeTruthy();
    expect(screen.getByText("Accepted")).toBeTruthy();
    expect(screen.getByText("Rejected")).toBeTruthy();
    expect(screen.getByText("Edited")).toBeTruthy();
    expect(screen.getByText("PR Merges")).toBeTruthy();

    // Weekly trend
    expect(screen.getByText("Weekly Signal Trend")).toBeTruthy();

    // Language rates
    expect(screen.getByText("Language Acceptance Rates")).toBeTruthy();
    // "python" appears in both Language Rates and Rejection Patterns; use getAllByText
    const pythonMatches = screen.getAllByText("python");
    expect(pythonMatches.length).toBeGreaterThanOrEqual(1);
    // "typescript" appears in both Language Rates and Rejection Patterns; use getAllByText
    const tsMatches = screen.getAllByText("typescript");
    expect(tsMatches.length).toBeGreaterThanOrEqual(1);
    const goMatches = screen.getAllByText("go");
    expect(goMatches.length).toBeGreaterThanOrEqual(1);

    // Rejection patterns
    expect(screen.getByText("Rejection Patterns")).toBeTruthy();

    // Developer stats
    expect(screen.getByText("Developer Acceptance Rates")).toBeTruthy();
    expect(screen.getByText("dev-abc123...")).toBeTruthy();
    expect(screen.getByText("dev-def456...")).toBeTruthy();

    // Version/timestamp
    expect(screen.getByText(/v2\.0\.0/)).toBeTruthy();
  });

  // ── Specific Values ──────────────────────────────────────────

  it("displays correct computed values", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Acceptance rate appears in overall metrics AND python language row; use getAllByText
    const rateTexts = screen.getAllByText("65.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // Total signals (formatted)
    // formatNumber(200) = "200" in en-US
    expect(screen.getByText("200")).toBeTruthy();

    // Trend direction
    expect(screen.getByText("↑ 13.2pp")).toBeTruthy();
  });

  // ── Empty Data Sub-Sections ──────────────────────────────────

  it("hides language and rejection sections when no language data", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: {
        ...SAMPLE_DATA,
        language_rates: [],
        rejection_patterns: [],
      },
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Language section should be hidden when no data
    expect(screen.queryByText("Language Acceptance Rates")).toBeNull();

    // Rejection patterns section should be hidden when no data
    expect(screen.queryByText("Rejection Patterns")).toBeNull();
  });

  it("handles empty developer stats", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: {
        ...SAMPLE_DATA,
        developer_stats: [],
      },
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Developer section should not render when empty
    expect(screen.queryByText("Developer Acceptance Rates")).toBeNull();
  });

  it("handles empty weekly trend", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: {
        ...SAMPLE_DATA,
        weekly_trend: [],
      },
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Trend chart should not render when empty
    expect(screen.queryByText("Weekly Signal Trend")).toBeNull();
  });

  // ── Collapse / Expand ────────────────────────────────────────

  it("collapses and expands content on header click", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Acceptance Rate")).toBeTruthy();
    });

    // Click the header to collapse
    const headerButton = screen.getByRole("button", { name: /Signal Pattern Analysis/i });
    headerButton.click();

    await waitFor(() => {
      expect(screen.queryByText("Acceptance Rate")).toBeNull();
    });

    // Should still show the header
    expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();

    // Click chevron-down icon to re-expand
    const chevronIcon = screen.getByTestId("icon-chevron-down");
    chevronIcon.click();

    await waitFor(() => {
      expect(screen.getByText("Acceptance Rate")).toBeTruthy();
    });

    // Should now show chevron-up
    expect(screen.getByTestId("icon-chevron-up")).toBeTruthy();
  });

  it("shows acceptance rate badge when collapsed", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Acceptance Rate")).toBeTruthy();
    });

    // Collapse
    const headerButton = screen.getByRole("button", { name: /Signal Pattern Analysis/i });
    headerButton.click();

    await waitFor(() => {
      expect(screen.queryByText("Acceptance Rate")).toBeNull();
    });

    // Badge should show rate
    expect(screen.getByText("65.0%")).toBeTruthy();
  });

  // ── Null / Edge Cases ────────────────────────────────────────

  it("handles null rejection patterns gracefully", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: {
        ...SAMPLE_DATA,
        rejection_patterns: [],
      },
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Rejection patterns section should not render
    expect(screen.queryByText("Rejection Patterns")).toBeNull();
  });

  it("renders with a single developer", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: {
        ...SAMPLE_DATA,
        developer_stats: [SAMPLE_DATA.developer_stats[0]],
        overall: { ...SAMPLE_DATA.overall, developers_count: 1 },
      },
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Should show singular "1 developer"
    expect(screen.getByText(/1 developer/)).toBeTruthy();
  });

  it("renders severity labels correctly", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Should show severity badges
    const lowBadges = screen.getAllByText("low");
    expect(lowBadges.length).toBeGreaterThanOrEqual(1);

    const mediumBadges = screen.getAllByText("medium");
    expect(mediumBadges.length).toBeGreaterThanOrEqual(1);

    // No "high" in sample data
    expect(screen.queryByText("high")).toBeNull();
  });

  it("renders role badges for developers", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // First dev has rate 70% → "Lead"
    expect(screen.getByText("Lead")).toBeTruthy();

    // Other devs have rate 50% → "Dev"
    const devBadges = screen.getAllByText("Dev");
    expect(devBadges.length).toBeGreaterThanOrEqual(1);

    // Should show anonymous badge
    const anonBadges = screen.getAllByText("anon");
    expect(anonBadges.length).toBeGreaterThanOrEqual(1);
  });

  // ── Signal Type Distribution ─────────────────────────────────

  it("shows signal type percentages", async () => {
    mockGetSignalPatterns.mockResolvedValue({
      success: true,
      data: SAMPLE_DATA,
    });

    render(<SignalPatternAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Signal Pattern Analysis")).toBeTruthy();
    });

    // Signal counts should display
    expect(screen.getByText("120")).toBeTruthy(); // accept count
    // "40" appears in signal types (reject count) AND language rates (go signals); use getAllByText
    const fortyMatches = screen.getAllByText("40");
    expect(fortyMatches.length).toBeGreaterThanOrEqual(1);
    // "30" appears in signal types (edit count) AND developer stats (dev-def total); use getAllByText
    const thirtyMatches = screen.getAllByText("30");
    expect(thirtyMatches.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("10")).toBeTruthy();  // pr_merge count
  });
});
