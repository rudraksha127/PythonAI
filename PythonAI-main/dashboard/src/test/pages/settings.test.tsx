import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    Settings: icon("settings"), Eye: icon("eye"), EyeOff: icon("eye-off"),
    Save: icon("save"), Sun: icon("sun"), Moon: icon("moon"),
    Play: icon("play"),
    FileCode: icon("file-code"),
    AlertCircle: icon("alert-circle"),
    Terminal: icon("terminal"),
    Bot: icon("bot"),
    RefreshCw: icon("refresh-cw"),
    TrendingDown: icon("trending-down"),
    Brain: icon("brain"),
    Server: icon("server"),
    Key: icon("key"),
  };
});

import SettingsPage from "@/app/settings/page";

describe("Settings Page", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders all tabs with Model active by default", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getAllByText("Model").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Training")).toBeTruthy();
    expect(screen.getByText("System")).toBeTruthy();
    expect(screen.getByText("API Keys")).toBeTruthy();
    expect(screen.getByText("Inference Backend")).toBeTruthy();
    expect(screen.getByText("Max Tokens")).toBeTruthy();
  });

  it("switches between tabs", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);

    await user.click(screen.getByText("Training"));
    await waitFor(() => expect(screen.getByText("Frequency")).toBeTruthy());
    expect(screen.getByText("Training Phase")).toBeTruthy();

    await user.click(screen.getByText("System"));
    await waitFor(() => expect(screen.getByText("Host")).toBeTruthy());
    expect(screen.getByText("Port")).toBeTruthy();
  });

  it("shows API key env var references", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(screen.getByText("API Keys"));
    await waitFor(() => expect(screen.getByText("Provider API Keys")).toBeTruthy());
  });
});
