import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Snackbar from "../components/Snackbar";
import { useAppStore } from "../store";

describe("Snackbar", () => {
  beforeEach(() => {
    useAppStore.setState({ snackbars: [] });
  });

  it("renders nothing when no snackbars", () => {
    const { container } = render(<Snackbar />);
    expect(container.firstChild).toBeNull();
  });

  it("renders snackbar message", () => {
    useAppStore.setState({
      snackbars: [
        { id: "s1", message: "Upload complete", type: "success", createdAt: Date.now() },
      ],
    });
    render(<Snackbar />);
    expect(screen.getByText("Upload complete")).toBeTruthy();
  });

  it("renders multiple snackbars", () => {
    useAppStore.setState({
      snackbars: [
        { id: "s1", message: "First", type: "info", createdAt: Date.now() },
        { id: "s2", message: "Second", type: "error", createdAt: Date.now() },
      ],
    });
    render(<Snackbar />);
    expect(screen.getByText("First")).toBeTruthy();
    expect(screen.getByText("Second")).toBeTruthy();
  });

  it("removes snackbar on close button click", () => {
    useAppStore.setState({
      snackbars: [
        { id: "s1", message: "Dismissable", type: "info", createdAt: Date.now() },
      ],
    });
    render(<Snackbar />);
    const closeBtn = screen.getByTitle("Dismiss");
    fireEvent.click(closeBtn);
    // After click, removeSnackbar should have been called — snackbar gone
    expect(useAppStore.getState().snackbars).toHaveLength(0);
  });
});
