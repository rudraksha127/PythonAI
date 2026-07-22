import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} />;
    };
  return {
    CheckCircle2: icon("check-circle-2"), Clock: icon("clock"),
    ArrowRight: icon("arrow-right"), FileText: icon("file-text"),
    TestTube: icon("test-tube"), Code: icon("code"), Layers: icon("layers"),
    Server: icon("server"), Zap: icon("zap"), Cpu: icon("cpu"),
    Users: icon("users"), GitFork: icon("git-fork"),
    Play: icon("play"),
    Bot: icon("bot"),
    Terminal: icon("terminal"),
    AlertCircle: icon("alert-circle"),
    RefreshCw: icon("refresh-cw"),
    TrendingDown: icon("trending-down"),
  };
});

import ProgressPage from "@/app/progress/page";

describe("Progress Page", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders header and progress section", () => {
    render(<ProgressPage />);
    expect(screen.getByText("Project Progress")).toBeTruthy();
    expect(screen.getByText(/Multi-provider Agent System/)).toBeTruthy();
    expect(screen.getByText("Live Progress")).toBeTruthy();
    expect(screen.getByText("Overall Progress")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("P1")).toBeTruthy();
    expect(screen.getByText("P10 ★")).toBeTruthy();
  });

  it("renders all stat cards", () => {
    render(<ProgressPage />);
    expect(screen.getByText("Tests Passing")).toBeTruthy();
    expect(screen.getByText("Source Lines")).toBeTruthy();
    expect(screen.getByText("Test Lines")).toBeTruthy();
    expect(screen.getByText("Source Files")).toBeTruthy();
    expect(screen.getByText("Test Files")).toBeTruthy();
  });

  it("renders all 10 phase timeline entries", () => {
    render(<ProgressPage />);
    expect(screen.getByText("Phase Timeline")).toBeTruthy();
    expect(screen.getByText("Phase 1 — Foundation")).toBeTruthy();
    expect(screen.getByText("Phase 10 — UI & Polish")).toBeTruthy();
    const badges = screen.getAllByText("✓ Done");
    expect(badges.length).toBe(10);
  });

  it("renders architecture cards", () => {
    render(<ProgressPage />);
    expect(screen.getByText("Core Agent Architecture")).toBeTruthy();
    expect(screen.getByText("orchestrator.py")).toBeTruthy();
    expect(screen.getByText("sub_agent.py")).toBeTruthy();
    expect(screen.getByText("swarm.py")).toBeTruthy();
    expect(screen.getByText("executor.py")).toBeTruthy();
    expect(screen.getByText("rag_engine.py")).toBeTruthy();
    expect(screen.getByText("trainer.py")).toBeTruthy();
    expect(screen.getByText("plan_task()")).toBeTruthy();
    expect(screen.getByText("AgentSwarm")).toBeTruthy();
    expect(screen.getByText("Hybrid Search")).toBeTruthy();
    expect(screen.getByText("QLoRA")).toBeTruthy();
  });

  it("renders test suite results", () => {
    render(<ProgressPage />);
    expect(screen.getByText("Test Suite Breakdown")).toBeTruthy();
    expect(screen.getByText("test_orchestrator_llm_planning.py")).toBeTruthy();
    expect(screen.getByText("test_rag.py")).toBeTruthy();
  });

  it("renders footer with stats", () => {
    render(<ProgressPage />);
    expect(screen.getByText(/336 tests passing/)).toBeTruthy();
    expect(screen.getByText(/0 failures/)).toBeTruthy();
  });
});
