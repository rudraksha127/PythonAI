import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ─── Lucide-react mock ──────────────────────────────────────────

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    DollarSign: icon("dollar-sign"),
    Users: icon("users"),
    TrendingUp: icon("trending-up"),
    Target: icon("target"),
    Zap: icon("zap"),
    Calculator: icon("calculator"),
    Sliders: icon("sliders"),
    ChevronDown: icon("chevron-down"),
    ChevronUp: icon("chevron-up"),
    Brain: icon("brain"),
  };
});

// ─── API mock ────────────────────────────────────────────────────

const mockGetCaptureStats = vi.hoisted(() => vi.fn());
const mockGetTrainingStatus = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  getCaptureStats: () => mockGetCaptureStats(),
  getTrainingStatus: () => mockGetTrainingStatus(),
}));

import RoiCalculator from "@/components/RoiCalculator";

// ─── Sample Data ─────────────────────────────────────────────────

const SAMPLE_STATS = {
  signals_by_type: { accept: 50, reject: 30, edit: 20 },
  signals_by_language: { python: 60, typescript: 40 },
  total_sessions: 100,
  overall_acceptance_rate: 52.0,
  avg_edit_distance: 5.2,
};

const SAMPLE_TRAINING = {
  active_run: null,
  history: [
    {
      run_id: "run-1",
      timestamp: Date.now() / 1000 - 86400,
      model_name: "Qwen2.5-Coder-7B",
      signals_used: 100,
      train_loss: null,
      eval_loss: null,
      acceptance_rate_before: 49.0,
      acceptance_rate_after: 52.0,
      acceptance_delta: 0.03,
      adapter_path: null,
    },
    {
      run_id: "run-2",
      timestamp: Date.now() / 1000 - 172800,
      model_name: "Qwen2.5-Coder-7B",
      signals_used: 80,
      train_loss: null,
      eval_loss: null,
      acceptance_rate_before: 52.0,
      acceptance_rate_after: 56.0,
      acceptance_delta: 0.04,
      adapter_path: null,
    },
  ],
};

// ─── Tests ───────────────────────────────────────────────────────

describe("RoiCalculator Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading ──────────────────────────────────────────────────

  it("renders loading skeleton on mount", () => {
    mockGetCaptureStats.mockReturnValue(new Promise(() => {}));
    mockGetTrainingStatus.mockReturnValue(new Promise(() => {}));

    const { container } = render(<RoiCalculator />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  // ── Complete Data ────────────────────────────────────────────

  it("renders all sections with complete data", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Summary value displays
    expect(screen.getByText("Annual Value")).toBeTruthy();
    expect(screen.getByText("Net Savings")).toBeTruthy();
    expect(screen.getByText("Acceptance Rate")).toBeTruthy();
    expect(screen.getByText("Productivity Gain")).toBeTruthy();

    // ROI gauge — "ROI" appears in gauge title + rows; use getAllByText
    const roiElements = screen.getAllByText("ROI");
    expect(roiElements.length).toBeGreaterThanOrEqual(1);

    // Controls
    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBe(2);
    expect(screen.getByText("Avg Annual Salary")).toBeTruthy();

    // Pricing tiers
    expect(screen.getByText("Pricing Tiers")).toBeTruthy();

    // Training sparkline
    expect(screen.getByText("Training Run Deltas")).toBeTruthy();

    // Calculation breakdown
    expect(screen.getByText("Calculation Breakdown")).toBeTruthy();
    // "Team Size" appears in InputSlider label AND breakdown; use getAllByText
    const teamSizeTexts = screen.getAllByText("Team Size");
    expect(teamSizeTexts.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Avg Salary")).toBeTruthy();
    expect(screen.getByText("Rate Improvement")).toBeTruthy();
    expect(screen.getByText("ForgeAI Cost")).toBeTruthy();

    // Disclaimer
    expect(screen.getByText(/Based on current acceptance rate/)).toBeTruthy();
  });

  // ── Calculation Values ───────────────────────────────────────

  it("displays correct calculated values with known inputs", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Calculated values based on: rate=52%, deltas=[0.03,0.04], teamSize=10, salary=150000
    // avgTrainingDelta = 3.5, projectedRuns = 10, improvement = min(35, 40) = 35pp
    // productivity = min(35*0.75, 35) = 26.25 → 26.3%
    // tier = Scale ($199/mo)

    // Acceptance rate shows in ValueDisplay AND disclaimer; use getAllByText
    const rateTexts = screen.getAllByText("52.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // Productivity gain
    expect(screen.getByText("26.3%")).toBeTruthy();

    // Team size label
    expect(screen.getByText("medium team")).toBeTruthy();

    // Pricing tier: "Scale" appears in tier list + recommended; use getAllByText
    const scaleTexts = screen.getAllByText("Scale");
    expect(scaleTexts.length).toBeGreaterThanOrEqual(1);

    // Tier breakdown: should show $199/mo entry
    expect(screen.getByText("$199/mo")).toBeTruthy();

    // Calculation breakdown: developers count
    expect(screen.getByText("10 developers")).toBeTruthy();
  });

  // ── Input Variations (via initial props) ─────────────────────

  it("renders with team size 20 via initial prop", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialTeamSize={20} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Team size InputSlider displays String(20) = "20"
    const sizeTexts = screen.getAllByText(/^20$/);
    expect(sizeTexts.length).toBeGreaterThanOrEqual(1);

    // Should still show Scale tier ($199/mo)
    expect(screen.getByText("$199/mo")).toBeTruthy();
  });

  it("maps team size 50 to Enterprise tier with large team label", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialTeamSize={50} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Enterprise team label
    expect(screen.getByText("large team")).toBeTruthy();

    // Should show Enterprise in the pricing breakdown
    const enterpriseElements = screen.getAllByText("Enterprise");
    expect(enterpriseElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders with custom salary via initial prop", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialSalary={200000} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // The InputSlider displays "$" + value.toLocaleString()
    // toLocaleString() output depends on Node.js locale (e.g. "200,000" or "2,00,000")
    // "200" appears in both InputSlider display and calculation breakdown; use getAllByText
    const salaryMatches = screen.getAllByText(/(200|2,00)/);
    expect(salaryMatches.length).toBeGreaterThanOrEqual(1);
  });

  // ── Null / Empty States ──────────────────────────────────────

  it("uses default 50% acceptance rate when capture stats returns null", async () => {
    mockGetCaptureStats.mockResolvedValue(null);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Acceptance rate shows in ValueDisplay AND disclaimer; use getAllByText
    const rateTexts = screen.getAllByText("50.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);
  });

  it("uses default 3% delta per run when training history is empty", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue({
      active_run: null,
      history: [],
    });

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Training delta section should not appear (no runs)
    expect(screen.queryByText("Training Run Deltas")).toBeNull();

    // With default 3% delta, rate 52%, 0 training runs:
    // avgTrainingDelta = 0.03 * 100 = 3
    // projectedRuns = max(1, 12-0) = 12
    // improvement = min(3*12, 40) = min(36, 40) = 36
    // productivityGainPct = min(36*0.75, 35) = min(27, 35) = 27 → 27.0%
    expect(screen.getByText("27.0%")).toBeTruthy();

    // Disclaimer should mention 0 training runs
    expect(screen.getByText(/0 training runs/)).toBeTruthy();
  });

  it("handles both APIs failing gracefully", async () => {
    mockGetCaptureStats.mockRejectedValue(new Error("Network error"));
    mockGetTrainingStatus.mockRejectedValue(new Error("Network error"));

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Should render with default values (50.0% appears in ValueDisplay AND disclaimer)
    const rateTexts = screen.getAllByText("50.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // No training delta section
    expect(screen.queryByText("Training Run Deltas")).toBeNull();

    // Should show Scale tier (teamSize=10 maps to Scale)
    const scaleTexts = screen.getAllByText("Scale");
    expect(scaleTexts.length).toBeGreaterThanOrEqual(1);
  });

  // ── Collapse / Expand ────────────────────────────────────────

  it("collapses and expands content on header click", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("Annual Value")).toBeTruthy();
    });

    // Click the header button to collapse
    const headerButton = screen.getByRole("button", { name: /ROI Calculator/i });
    headerButton.click();

    await waitFor(() => {
      expect(screen.queryByText("Annual Value")).toBeNull();
    });
    // Only header/ROI badge should remain
    expect(screen.getByText("ROI Calculator")).toBeTruthy();

    // Click again (chevron-down icon appears when collapsed)
    const chevronIcon = screen.getByTestId("icon-chevron-down");
    chevronIcon.click();

    await waitFor(() => {
      expect(screen.getByText("Annual Value")).toBeTruthy();
    });
  });

  it("shows ROI badge when collapsed", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("Annual Value")).toBeTruthy();
    });

    // Collapse
    const headerButton = screen.getByRole("button", { name: /ROI Calculator/i });
    headerButton.click();

    await waitFor(() => {
      expect(screen.queryByText("Annual Value")).toBeNull();
    });

    // Should show ROI value
    // roiPercent = 16390 → display as "16.4k% ROI"
    // Use substring matching for just the recognizable part to avoid regex escaping issues
    expect(screen.getByText(/4k% ROI/)).toBeTruthy();
  });

  // ── Training Delta Sparkline ─────────────────────────────────

  it("hides training sparkline when no training runs exist", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue({
      active_run: null,
      history: [],
    });

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    expect(screen.queryByText("Training Run Deltas")).toBeNull();
  });

  // ── Edge Cases ───────────────────────────────────────────────

  it("maps team size 1 to Go tier with solo label", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialTeamSize={1} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Solo team label
    expect(screen.getByText("solo team")).toBeTruthy();

    // Go tier ($9/mo)
    expect(screen.getByText("$9/mo")).toBeTruthy();

    // 1 developer in breakdown
    expect(screen.getByText("1 developer")).toBeTruthy();
  });

  it("maps team size 100 to Enterprise tier with enterprise label", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialTeamSize={100} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Enterprise team label
    expect(screen.getByText("enterprise team")).toBeTruthy();

    // Enterprise tier
    const enterpriseElements = screen.getAllByText("Enterprise");
    expect(enterpriseElements.length).toBeGreaterThanOrEqual(1);

    // 100 developers in breakdown
    expect(screen.getByText("100 developers")).toBeTruthy();
  });

  it("applies custom initial props", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator initialTeamSize={5} initialSalary={120000} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Team size shows 5
    expect(screen.getByText("5")).toBeTruthy();

    // Salary display: "$" + value.toLocaleString() which depends on locale
    // Combined regex matches both "120,000" (en-US) and "1,20,000" (Indian)
    // Appears in both InputSlider display and calculation breakdown; use getAllByText
    const salaryMatches = screen.getAllByText(/(120|1,20)/);
    expect(salaryMatches.length).toBeGreaterThanOrEqual(1);

    // Team size 5 → "small team" label
    expect(screen.getByText("small team")).toBeTruthy();

    // Team size 5 → Team tier ($49/mo)
    expect(screen.getByText("$49/mo")).toBeTruthy();
  });

  // ── Gauge ────────────────────────────────────────────────────

  it("renders ROI gauge category text", async () => {
    mockGetCaptureStats.mockResolvedValue(SAMPLE_STATS);
    mockGetTrainingStatus.mockResolvedValue(SAMPLE_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // roiPercent calculated above: ~16390%, which is > 5000 → "Exceptional"
    expect(screen.getByText("Exceptional")).toBeTruthy();
  });
});
