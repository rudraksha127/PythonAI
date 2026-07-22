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

// ─── API mock — realistic backend responses ─────────────────────

const mockGetCaptureStats = vi.hoisted(() => vi.fn());
const mockGetTrainingStatus = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  getCaptureStats: () => mockGetCaptureStats(),
  getTrainingStatus: () => mockGetTrainingStatus(),
}));

import RoiCalculator from "@/components/RoiCalculator";

// ─── Realistic data matching actual backend shapes ──────────────

/**
 * These data shapes are designed to match exactly what the Python
 * backend would return — the same field names, types, and patterns
 * that the ROI Calculator component expects.
 *
 * Backend reference:
 *   GET /stats → CaptureEngine.get_statistics()
 *   GET /api/training/status → CaptureEngine.get_training_runs()
 */

const REALISTIC_STATS = {
  // Matches actual /stats response
  signals_by_type: {
    accept: 150,
    reject: 40,
    edit: 25,
    pr_merge: 10,
  },
  signals_by_language: {
    python: 120,
    typescript: 60,
    go: 30,
    rust: 15,
  },
  total_sessions: 25,
  overall_acceptance_rate: 65.0,  // Used as currentRate
  avg_edit_distance: 0.35,
};

const REALISTIC_TRAINING = {
  // Matches actual /api/training/status response
  active_run: null,
  history: [
    {
      run_id: "run-001",
      timestamp: Date.now() / 1000 - 7 * 86400,
      model_name: "Qwen/Qwen2.5-Coder-7B-Instruct",
      signals_used: 100,
      train_loss: 0.45,
      eval_loss: 1.02,
      acceptance_rate_before: 0.55,  // Used as before-rate
      acceptance_rate_after: 0.58,   // Used as after-rate
      acceptance_delta: 0.03,        // Used for avgTrainingDelta
      adapter_path: "/home/user/.forgeai/adapters/v1",
    },
    {
      run_id: "run-002",
      timestamp: Date.now() / 1000 - 14 * 86400,
      model_name: "Qwen/Qwen2.5-Coder-7B-Instruct",
      signals_used: 120,
      train_loss: 0.38,
      eval_loss: 0.95,
      acceptance_rate_before: 0.52,
      acceptance_rate_after: 0.55,
      acceptance_delta: 0.03,
      adapter_path: "/home/user/.forgeai/adapters/v2",
    },
    {
      run_id: "run-003",
      timestamp: Date.now() / 1000 - 21 * 86400,
      model_name: "Qwen/Qwen2.5-Coder-7B-Instruct",
      signals_used: 80,
      train_loss: 0.52,
      eval_loss: 1.10,
      acceptance_rate_before: 0.48,
      acceptance_rate_after: 0.52,
      acceptance_delta: 0.04,
      adapter_path: "/home/user/.forgeai/adapters/v3",
    },
  ],
};

// ─── Expected computed values ───────────────────────────────────
// Based on: rate=65%, deltas=[0.03, 0.03, 0.04], teamSize=10, salary=150000
//
// avgTrainingDelta = avg(3, 3, 4) = 3.333...%
// projectedRuns = max(1, 12-3) = 9
// improvement = min(3.333 * 9, 40) = min(30, 40) = 30pp
// productivityGainPct = min(30 * 0.75, 35) = min(22.5, 35) = 22.5%
// annualValueTotal = 10 * 150000 * (22.5 / 100) = $337,500
// tier = Scale ($199/mo, $2,388/yr)
// netAnnualSavings = $337,500 - $2,388 = $335,112
// roiPercent = round($335,112 / $2,388 * 100) = 14,033%
// paybackDays = round(199 / (337500 / 365)) = round(199 / 924.66) = 0 days

const EXPECTED = {
  annualValueDisplay: "$337,500",     // formatCurrency(337500)
  productivityGain: "22.5%",
  tier: "Scale",
  tierMonthly: "$199/mo",
  teamSize: "10 developers",
};

// ─── Tests ───────────────────────────────────────────────────────

describe("ROI Calculator End-to-End Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Pipeline: Data Ingestion → Computation → Render ────────

  it("fetches real stats and training data then computes correct ROI", async () => {
    // Simulate the backend returning realistic data
    mockGetCaptureStats.mockResolvedValue(REALISTIC_STATS);
    mockGetTrainingStatus.mockResolvedValue(REALISTIC_TRAINING);

    render(<RoiCalculator />);

    // Wait for data to load and component to render
    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // ── API was called ─────────────────────────────────────────
    expect(mockGetCaptureStats).toHaveBeenCalledTimes(1);
    expect(mockGetTrainingStatus).toHaveBeenCalledTimes(1);

    // ── Current acceptance rate from stats ─────────────────────
    // 65.0% appears in the gauge subtitle AND disclaimer text
    const rateTexts = screen.getAllByText("65.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // ── Annual Value from computation ──────────────────────────
    // teamSize=10, salary=150000, gain=22.5%
    // Annual Value = 10 * 150000 * 0.225 = $337,500
    expect(screen.getByText(EXPECTED.annualValueDisplay)).toBeTruthy();

    // ── Productivity Gain ───────────────────────────────────────
    expect(screen.getByText(EXPECTED.productivityGain)).toBeTruthy();

    // ── Team size label ────────────────────────────────────────
    expect(screen.getByText("medium team")).toBeTruthy();

    // ── Pricing tier ───────────────────────────────────────────
    const scaleTexts = screen.getAllByText(EXPECTED.tier);
    expect(scaleTexts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(EXPECTED.tierMonthly)).toBeTruthy();

    // ── Training delta sparkline shows ─────────────────────────
    expect(screen.getByText("Training Run Deltas")).toBeTruthy();

    // ── Calculation breakdown ──────────────────────────────────
    expect(screen.getByText(EXPECTED.teamSize)).toBeTruthy();

    // ── ROI gauge category (14,033% > 5000 → "Exceptional") ───
    expect(screen.getByText("Exceptional")).toBeTruthy();

    // ── Disclaimer mentioning training runs ────────────────────
    expect(screen.getByText(/3 training runs/)).toBeTruthy();
  });

  // ── Scenario: Different team sizes ───────────────────────────

  it("computes correct values for a 25-person enterprise team", async () => {
    mockGetCaptureStats.mockResolvedValue(REALISTIC_STATS);
    mockGetTrainingStatus.mockResolvedValue(REALISTIC_TRAINING);

    // Override defaults and render
    render(<RoiCalculator initialTeamSize={25} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Team size 25 → "large team"
    expect(screen.getByText("large team")).toBeTruthy();

    // Team size 25 → Enterprise tier ($3000/mo — no comma in template literal)
    expect(screen.getByText("$3000/mo")).toBeTruthy();

    // Annual Value = 25 * 150000 * 0.225 = $843,750
    expect(screen.getByText("$843,750")).toBeTruthy();

    // 25 developers in breakdown
    expect(screen.getByText("25 developers")).toBeTruthy();
  });

  // ── Scenario: Different salary ───────────────────────────────

  it("computes correct values for high salary team", async () => {
    mockGetCaptureStats.mockResolvedValue(REALISTIC_STATS);
    mockGetTrainingStatus.mockResolvedValue(REALISTIC_TRAINING);

    render(<RoiCalculator initialSalary={250000} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Annual Value = 10 * 250000 * 0.225 = $562,500
    expect(screen.getByText("$562,500")).toBeTruthy();

    // Salary display should include "250" or "2,50" depending on locale
    const salaryTexts = screen.getAllByText(/(250|2,50)/);
    expect(salaryTexts.length).toBeGreaterThanOrEqual(1);
  });

  // ── Scenario: Low acceptance rate ────────────────────────────

  it("computes correct values with low acceptance rate", async () => {
    mockGetCaptureStats.mockResolvedValue({
      ...REALISTIC_STATS,
      overall_acceptance_rate: 31.0,  // industry average
    });
    mockGetTrainingStatus.mockResolvedValue(REALISTIC_TRAINING);

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Acceptance rate appears in multiple places
    const rateTexts = screen.getAllByText("31.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // avgTrainingDelta = 0.0333 → 3.33%
    // projectedRuns = 9
    // improvement = min(3.33*9, 40) = 30pp
    // projectedRate = 31.0 + 30 = 61.0%
    // productivityGainPct = min(30 * 0.75, 35) = 22.5%
    // Annual Value = 10 * 150000 * 0.225 = $337,500
    expect(screen.getByText("$337,500")).toBeTruthy();

    // Productivity gain still 22.5%
    expect(screen.getByText("22.5%")).toBeTruthy();
  });

  // ── Scenario: Maximum team size ─────────────────────────────

  it("computes ROI for maximum team size of 100", async () => {
    mockGetCaptureStats.mockResolvedValue(REALISTIC_STATS);
    mockGetTrainingStatus.mockResolvedValue(REALISTIC_TRAINING);

    render(<RoiCalculator initialTeamSize={100} />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Enterprise tier + label
    const enterpriseTexts = screen.getAllByText("Enterprise");
    expect(enterpriseTexts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("enterprise team")).toBeTruthy();

    // Annual Value = 100 * 150000 * 0.225 = $3,375,000 → "$3.4M"
    expect(screen.getByText("$3.4M")).toBeTruthy();

    // 100 developers in breakdown
    expect(screen.getByText("100 developers")).toBeTruthy();
  });

  // ── Pipeline: All APIs fail → graceful fallback ─────────────

  it("gracefully falls back when all APIs fail", async () => {
    mockGetCaptureStats.mockRejectedValue(new Error("Connection refused"));
    mockGetTrainingStatus.mockRejectedValue(new Error("Connection refused"));

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Should render with default values
    // 50.0% appears in gauge + disclaimer
    const defaultRateTexts = screen.getAllByText("50.0%");
    expect(defaultRateTexts.length).toBeGreaterThanOrEqual(1);

    // No training delta section
    expect(screen.queryByText("Training Run Deltas")).toBeNull();

    // Default disclaimer
    expect(screen.getByText(/0 training runs/)).toBeTruthy();
  });

  // ── Pipeline: Partial data (stats available, no training) ────

  it("computes ROI with stats but no training history", async () => {
    mockGetCaptureStats.mockResolvedValue(REALISTIC_STATS);
    mockGetTrainingStatus.mockResolvedValue({
      active_run: null,
      history: [],
    });

    render(<RoiCalculator />);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // No training sparkline
    expect(screen.queryByText("Training Run Deltas")).toBeNull();

    // Disclaimer mentions 0 training runs
    expect(screen.getByText(/0 training runs/)).toBeTruthy();

    // Stats data still renders
    const rateTexts = screen.getAllByText("65.0%");
    expect(rateTexts.length).toBeGreaterThanOrEqual(1);

    // With default delta 3% and 0 runs:
    // projectedRuns = max(1, 12-0) = 12
    // improvement = min(3*12, 40) = 36pp
    // productivityGainPct = min(36*0.75, 35) = 27.0%
    expect(screen.getByText("27.0%")).toBeTruthy();
  });

  // ── Pipeline: Loading state → Data state ────────────────────

  it("transitions from loading skeleton to data display", async () => {
    // Delay resolution to trigger loading state
    let resolveStats!: (v: unknown) => void;
    let resolveTraining!: (v: unknown) => void;

    mockGetCaptureStats.mockReturnValue(new Promise((r) => { resolveStats = r; }));
    mockGetTrainingStatus.mockReturnValue(new Promise((r) => { resolveTraining = r; }));

    const { container } = render(<RoiCalculator />);

    // Should show loading skeleton
    expect(container.querySelector(".animate-pulse")).toBeTruthy();

    // Resolve with realistic data
    resolveStats(REALISTIC_STATS);
    resolveTraining(REALISTIC_TRAINING);

    await waitFor(() => {
      expect(screen.getByText("ROI Calculator")).toBeTruthy();
    });

    // Loading skeleton should be gone
    expect(container.querySelector(".animate-pulse")).toBeNull();

    // Data should be rendered
    expect(screen.getAllByText("65.0%").length).toBeGreaterThanOrEqual(1);
  });
});
