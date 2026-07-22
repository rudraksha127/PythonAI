import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    TrendingUp: icon("trending-up"),
    Brain: icon("brain"),
    Zap: icon("zap"),
    Activity: icon("activity"),
    Layers: icon("layers"),
    GitBranch: icon("git-branch"),
    Bot: icon("bot"),
    Settings: icon("settings"),
    Cpu: icon("cpu"),
    Menu: icon("menu"),
    X: icon("x"),
    CheckCircle2: icon("check-circle-2"),
    XCircle: icon("x-circle"),
    ChevronRight: icon("chevron-right"),
    BarChart3: icon("bar-chart-3"),
    Play: icon("play"),
    FileCode: icon("file-code"),
    AlertCircle: icon("alert-circle"),
    Terminal: icon("terminal"),
    RefreshCw: icon("refresh-cw"),
    TrendingDown: icon("trending-down"),
  };
});

vi.mock("@/lib/api", () => ({
  getTrainingStatus: vi.fn(),
  triggerTraining: vi.fn(),
  createTrainingWs: vi.fn(() => ({ close: vi.fn(), send: vi.fn(), addEventListener: vi.fn() })),
}));

import TrainingPage from "@/app/training/page";
import * as api from "@/lib/api";

describe("Training Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading skeleton", () => {
    (api.getTrainingStatus as any).mockReturnValue(new Promise(() => {}));
    const { container } = render(<TrainingPage />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders empty state when no training runs", async () => {
    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: [] });

    render(<TrainingPage />);

    // Header renders as "Training" (not "Training & Fine-tuning")
    await waitFor(() => {
      expect(screen.getByText("Training")).toBeTruthy();
    });

    // Empty state shows "No Training Runs Yet"
    await waitFor(() => {
      expect(screen.getByText("No Training Runs Yet")).toBeTruthy();
    });

    // The button in header says "Trigger Training"
    const triggerBtns = screen.getAllByText("Trigger Training");
    expect(triggerBtns.length).toBeGreaterThanOrEqual(1);
  });

  it("renders training history table", async () => {
    const runs = [
      {
        run_id: "run-1", timestamp: Date.now() / 1000 - 86400 * 2,
        model_name: "Qwen/Qwen2.5-Coder-14B", signals_used: 500,
        train_loss: 0.45, eval_loss: 1.02,
        acceptance_rate_before: 0.45, acceptance_rate_after: 0.52,
        acceptance_delta: 0.07, adapter_path: "/adapters/run-1",
      },
      {
        run_id: "run-2", timestamp: Date.now() / 1000 - 86400 * 7,
        model_name: "Qwen/Qwen2.5-Coder-14B", signals_used: 300,
        train_loss: 0.55, eval_loss: 1.10,
        acceptance_rate_before: 0.50, acceptance_rate_after: 0.48,
        acceptance_delta: -0.02, adapter_path: null,
      },
    ];

    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: runs });

    render(<TrainingPage />);

    await waitFor(() => {
      expect(screen.getByText("Run History")).toBeTruthy();
    });

    // Delta is formatted as toFixed(2) so 0.07 → "+7.00%"
    expect(screen.getByText("+7.00%")).toBeTruthy();
  });

  it("shows active training run progress", async () => {
    (api.getTrainingStatus as any).mockResolvedValue({
      active_run: { run_id: "active-1", status: "running", started_at: Date.now() / 1000 - 300, progress: 0.45 },
      history: [],
    });

    render(<TrainingPage />);

    // Active run shows "Training in Progress" heading
    await waitFor(() => {
      expect(screen.getByText("Training in Progress")).toBeTruthy();
    });

    // Progress is 0.45 → Math.round(0.45 * 100) = "45%"
    expect(screen.getByText("45%")).toBeTruthy();
  });

  it("triggers training on button click", async () => {
    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: [] });
    (api.triggerTraining as any).mockResolvedValue({ run_id: "new-run", status: "queued" });

    const user = userEvent.setup();
    render(<TrainingPage />);

    // Use getAllByText since "Trigger Training" appears multiple times
    await waitFor(() => {
      expect(screen.getAllByText("Trigger Training").length).toBeGreaterThanOrEqual(1);
    });

    // Click the header button (first button with text "Trigger Training")
    await user.click(screen.getAllByText("Trigger Training")[0]);
    await waitFor(() => expect(api.triggerTraining).toHaveBeenCalledOnce());
  });

  it("handles trigger training error gracefully", async () => {
    (api.getTrainingStatus as any).mockResolvedValue({ active_run: null, history: [] });
    (api.triggerTraining as any).mockRejectedValue(new Error("Server error"));

    const user = userEvent.setup();
    render(<TrainingPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Trigger Training").length).toBeGreaterThanOrEqual(1);
    });

    await user.click(screen.getAllByText("Trigger Training")[0]);

    // Error displays when trigger fails
    await waitFor(() => {
      expect(screen.getByText(/Failed to trigger training|Server error/)).toBeTruthy();
    });
  });
});
