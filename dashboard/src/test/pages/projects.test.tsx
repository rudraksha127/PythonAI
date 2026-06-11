import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("lucide-react", () => {
  const icon = (name: string) =>
    function MockIcon({ size, className }: { size?: number; className?: string }) {
      return <span data-testid={`icon-${name}`} data-size={size} className={className} />;
    };
  return {
    GitBranch: icon("git-branch"), Plus: icon("plus"), RefreshCw: icon("refresh-cw"),
    Database: icon("database"), BookOpen: icon("book-open"), Code: icon("code"),
    Search: icon("search"), CheckCircle2: icon("check-circle-2"),
    AlertCircle: icon("alert-circle"), FileCode: icon("file-code"),
    Layers: icon("layers"), Clock: icon("clock"), ExternalLink: icon("external-link"),
    ChevronRight: icon("chevron-right"),
  };
});

vi.mock("@/lib/api", () => ({
  getProjects: vi.fn(),
  createProject: vi.fn(),
  searchRag: vi.fn(),
  indexProject: vi.fn(),
}));

import ProjectsPage from "@/app/projects/page";
import * as api from "@/lib/api";

describe("Projects Page", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders loading state", () => {
    (api.getProjects as any).mockReturnValue(new Promise(() => {}));
    const { container } = render(<ProjectsPage />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders empty state when no projects", async () => {
    (api.getProjects as any).mockResolvedValue([]);
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText("Projects")).toBeTruthy());
    await waitFor(() => expect(screen.getByText("No Projects Yet")).toBeTruthy());
    // Both the header button and empty state button say "Add Project"
    expect(screen.getAllByText("Add Project").length).toBeGreaterThanOrEqual(1);
  });

  it("renders project cards with data", async () => {
    (api.getProjects as any).mockResolvedValue([
      {
        id: "p1", name: "forgeai-server", repo_path: "/home/forgeai",
        languages: ["python", "typescript"], current_adapter_version: 3,
        training_phase: 2, base_model: "qwen2.5-coder:14b",
        training_schedule: "weekly", rag_indexed_at: new Date().toISOString(),
      },
      {
        id: "p2", name: "frontend-app", repo_path: "/home/frontend",
        languages: ["typescript", "css"], current_adapter_version: 1,
        training_phase: 1, base_model: "qwen2.5-coder:7b",
        training_schedule: "daily",
      },
    ]);

    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText("forgeai-server")).toBeTruthy());
    expect(screen.getByText("frontend-app")).toBeTruthy();
  });

  it("opens add project modal and handles creation", async () => {
    (api.getProjects as any).mockResolvedValue([]);
    (api.createProject as any).mockResolvedValue({
      id: "new-p", name: "test-project", repo_path: "/home/test",
      languages: [], current_adapter_version: 0, training_phase: 1,
      base_model: "qwen2.5-coder:14b", training_schedule: "weekly",
    });

    const user = userEvent.setup();
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getAllByText("Add Project").length).toBeGreaterThanOrEqual(1));
    await user.click(screen.getAllByText("Add Project")[0]);
    // Modal shows "Add Project" as the heading
    await waitFor(() => expect(screen.getAllByText("Add Project").length).toBeGreaterThanOrEqual(2));

    // Fill in the form
    const nameInput = screen.getByPlaceholderText("e.g., my-web-app");
    await user.type(nameInput, "test-project");
    const pathInput = screen.getByPlaceholderText("e.g., /home/user/projects/my-app");
    await user.type(pathInput, "/home/test");
    
    // Use getAllByRole to find all buttons with "Add Project" as accessible name
    const addBtns = screen.getAllByRole("button", { name: /Add Project/ });
    // The last button should be the enabled modal submit button
    await user.click(addBtns[addBtns.length - 1]);

    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith("test-project", "/home/test"));
  });

  it("handles API error gracefully", async () => {
    (api.getProjects as any).mockRejectedValue(new Error("Failed to fetch"));
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText("Cannot load projects")).toBeTruthy());
  });
});
