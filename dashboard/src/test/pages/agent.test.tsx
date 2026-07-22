import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    Send: icon("send"), Bot: icon("bot"), User: icon("user"),
    Code: icon("code"), Terminal: icon("terminal"), RefreshCw: icon("refresh-cw"),
    Trash2: icon("trash-2"),
  };
});

import AgentPage from "@/app/agent/page";

describe("Agent Page", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { vi.restoreAllMocks(); });

  it("renders welcome message and preset prompts", async () => {
    render(<AgentPage />);
    // The h1 is "Agent"
    expect(screen.getByText("Agent")).toBeTruthy();
    // Shows the welcome message (use getAllByText since the text may appear once)
    expect(screen.getAllByText(/ForgeAI coding agent/).length).toBeGreaterThanOrEqual(1);
    // Preset prompts use labels: "Debug this code", "Write a test", "Explain concept"
    expect(screen.getByText("Debug this code")).toBeTruthy();
    expect(screen.getByText("Write a test")).toBeTruthy();
    expect(screen.getByText("Explain concept")).toBeTruthy();
  });

  it("allows typing in the input field", async () => {
    const user = userEvent.setup();
    render(<AgentPage />);
    const input = screen.getByPlaceholderText("Ask a question... (Shift+Enter for new line)");
    await user.type(input, "Explain recursion");
    expect((input as HTMLTextAreaElement).value).toBe("Explain recursion");
  });

  it("sends message and shows user message in chat", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ token: "Hello!" })}\n\n`));
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ done: true, sources: [] })}\n\n`));
          controller.close();
        },
      }),
    });

    const user = userEvent.setup();
    render(<AgentPage />);
    const input = screen.getByPlaceholderText("Ask a question... (Shift+Enter for new line)");
    await user.type(input, "Hello world");
    // Press Enter to submit
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(screen.getByText("Hello world")).toBeTruthy();
    });
  });

  it("clicking preset populates input", async () => {
    const user = userEvent.setup();
    render(<AgentPage />);
    await waitFor(() => expect(screen.getByText("Debug this code")).toBeTruthy());
    await user.click(screen.getByText("Debug this code"));
    const input = screen.getByPlaceholderText("Ask a question... (Shift+Enter for new line)");
    expect((input as HTMLTextAreaElement).value).toBe(
      "Help me debug a Python function that's throwing an unexpected error"
    );
  });

  it("shows model selector dropdown", async () => {
    const user = userEvent.setup();
    render(<AgentPage />);
    // Default shows "Auto" button
    await user.click(screen.getByText("Auto"));
    await waitFor(() => {
      expect(screen.getByText("Auto (Recommended)")).toBeTruthy();
      expect(screen.getByText("Qwen 2.5 Coder 7B")).toBeTruthy();
      expect(screen.getByText("Qwen 2.5 Coder 14B")).toBeTruthy();
      expect(screen.getByText("GPT-4o")).toBeTruthy();
      expect(screen.getByText("Claude Opus 4")).toBeTruthy();
    });
    await user.click(screen.getByText("GPT-4o"));
    await waitFor(() => expect(screen.getByText("GPT-4o")).toBeTruthy());
  });

  it("clears conversation", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("data: {\"token\":\"Response\"}\n\n"));
          controller.enqueue(new TextEncoder().encode("data: {\"done\":true,\"sources\":[]}\n\n"));
          controller.close();
        },
      }),
    });

    const user = userEvent.setup();
    render(<AgentPage />);
    const input = screen.getByPlaceholderText("Ask a question... (Shift+Enter for new line)");
    await user.type(input, "Test message");
    await user.keyboard('{Enter}');
    await waitFor(() => expect(screen.getByText("Test message")).toBeTruthy());

    // Click the clear button (Trash2 icon button with title "Clear conversation")
    const clearBtn = screen.getByTitle("Clear conversation");
    await user.click(clearBtn);
    await waitFor(() => {
      expect(screen.getByText(/Conversation cleared/)).toBeTruthy();
    });
  });

  it("handles streaming error gracefully", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("Network error"));
    const user = userEvent.setup();
    render(<AgentPage />);
    const input = screen.getByPlaceholderText("Ask a question... (Shift+Enter for new line)");
    await user.type(input, "Hello");
    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(screen.getByText(/Error:|Network error/)).toBeTruthy();
    });
  });
});
