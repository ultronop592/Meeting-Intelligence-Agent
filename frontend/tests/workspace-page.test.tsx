import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkspacePage from "@/app/workspace/page";

vi.mock("@/components/workspace/meeting-workspace", () => ({
  MeetingWorkspace: () => <div data-testid="meeting-workspace">Workspace Loaded</div>,
}));

describe("WorkspacePage", () => {
  it("renders the meeting workspace inside auth guard", () => {
    render(<WorkspacePage />);
    expect(screen.getByTestId("meeting-workspace")).toBeInTheDocument();
  });
});
