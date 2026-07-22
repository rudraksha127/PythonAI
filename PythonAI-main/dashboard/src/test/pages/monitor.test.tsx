import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} />;
    };
  return {
    Activity: icon("activity"), Wifi: icon("wifi"), WifiOff: icon("wifi-off"),
    Terminal: icon("terminal"), Cpu: icon("cpu"), Shield: icon("shield"),
    DollarSign: icon("dollar-sign"), ChevronRight: icon("chevron-right"),
    Server: icon("server"), HardDrive: icon("hard-drive"), Bot: icon("bot"),
    Brain: icon("brain"),
    Play: icon("play"),
    FileCode: icon("file-code"),
    AlertCircle: icon("alert-circle"),
    RefreshCw: icon("refresh-cw"),
    TrendingDown: icon("trending-down"),
  };
});

import MonitorPage from "@/app/monitor/page";

class MockWebSocket {
  close = vi.fn();
  send = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  readyState = WebSocket.OPEN;
  onopen: any = null;
  onclose: any = null;
  onmessage: any = null;
  onerror: any = null;
  url = "";
  protocol = "";
  extensions = "";
  bufferedAmount = 0;
  binaryType: BinaryType = "blob";
}

describe("Monitor Page", () => {
  let mockWsInstances: MockWebSocket[];

  beforeEach(() => {
    vi.clearAllMocks();
    mockWsInstances = [];

    // Use a regular function (not arrow function) so vitest 4.x treats it as constructable
    global.WebSocket = vi.fn().mockImplementation(function () {
      // eslint-disable-next-line prefer-rest-params
      const ws = new MockWebSocket();
      mockWsInstances.push(ws);
      return ws;
    }) as any;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the header with god mode title", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Omniscient AI — God Mode")).toBeTruthy();
  });

  it("renders all pipeline phases", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Active Pipelines")).toBeTruthy();
    expect(screen.getAllByText("arXiv Papers").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Synthetic Generation/)).toBeTruthy();
    expect(screen.getByText(/RAG Pipeline Indexing/)).toBeTruthy();
  });

  it("renders agent swarm", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Multi-Agent Swarm")).toBeTruthy();
    expect(screen.getByText("Orchestrator")).toBeTruthy();
    expect(screen.getByText("Retrieval")).toBeTruthy();
    expect(screen.getByText("Docs")).toBeTruthy();
    expect(screen.getByText("Teacher")).toBeTruthy();
  });

  it("renders RAG architecture flow", () => {
    render(<MonitorPage />);
    expect(screen.getByText("RAG Pipeline — Triple Hybrid Search")).toBeTruthy();
    expect(screen.getByText("Query")).toBeTruthy();
    expect(screen.getByText("Dense")).toBeTruthy();
    expect(screen.getByText("BM25")).toBeTruthy();
    expect(screen.getByText("RRF")).toBeTruthy();
  });

  it("renders constitutional checks", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Constitutional Core")).toBeTruthy();
    expect(screen.getByText("Truth over Confidence")).toBeTruthy();
    expect(screen.getByText("Verify before Trust")).toBeTruthy();
  });

  it("renders data storage section", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Data Storage — Live")).toBeTruthy();
    expect(screen.getAllByText("arXiv Papers").length).toBeGreaterThanOrEqual(1);
  });

  it("renders cost tracker", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Cost Tracker")).toBeTruthy();
  });

  it("renders live console", () => {
    render(<MonitorPage />);
    expect(screen.getByText("Live System Console")).toBeTruthy();
  });

  it("renders stats bar", () => {
    render(<MonitorPage />);
    const statLabels = ["Total Files", "GB Collected", "arXiv Papers", "OpenAlex Works", "Synthetic Rows", "RAG Indexed", "Errors"];
    // Use getAllByText for labels that may appear multiple times
    statLabels.forEach(label => {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("handles FULL_STATE WebSocket message and updates UI", async () => {
    render(<MonitorPage />);

    await waitFor(() => {
      expect(mockWsInstances.length).toBeGreaterThan(0);
    });

    const ws = mockWsInstances[0];
    expect(ws.onmessage).toBeDefined();

    // Simulate receiving a FULL_STATE message
    ws.onmessage({
      data: JSON.stringify({
        type: "FULL_STATE",
        data: {
          state: {
            stats: { total_files: 500, total_size_gb: 2.5, arxiv_papers: 1200, openalex_works: 800, synthetic_rows: 3000, rag_indexed: 450, errors: 3 },
            agents: { orchestrator: { status: "active", last_action: "Coordinating" } },
            providers: { openai: { label: "OpenAI", tier: "standard", has_key: true, status: "online" } },
            phases: { "arXiv Papers": "RUNNING", "Synthetic Data Generation": "COMPLETE ✓" },
          },
          history: [],
        },
      }),
    });

    // Assert that the updated stats appear in the UI
    await waitFor(() => {
      expect(screen.getByText("500")).toBeTruthy();
    });
  });

  it("disconnects on unmount", () => {
    const { unmount } = render(<MonitorPage />);
    unmount();
    expect(mockWsInstances.length).toBeGreaterThan(0);
    mockWsInstances.forEach(ws => {
      expect(ws.close).toHaveBeenCalled();
    });
  });
});
