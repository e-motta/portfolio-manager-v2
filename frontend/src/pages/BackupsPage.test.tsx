import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetJson = vi.fn();
const mockSendForm = vi.fn();

vi.mock("../api/client", () => ({
  getJson: (path: string) => mockGetJson(path),
  sendForm: (path: string, data: Record<string, unknown>) => mockSendForm(path, data),
}));

vi.mock("../components/QueryFlash", () => ({
  QueryFlash: () => null,
}));

vi.mock("../components/inputs", () => ({
  showToast: vi.fn(),
}));

import { BackupsPage } from "./BackupsPage";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("BackupsPage", () => {
  beforeEach(() => {
    mockGetJson.mockReset();
    mockSendForm.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockGetJson.mockImplementation(() => new Promise(() => {}));

    render(<BackupsPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/Loading backups/)).toBeInTheDocument();
  });

  it("shows connect card when drive is not connected", async () => {
    mockGetJson.mockResolvedValueOnce({
      google_configured: true,
      drive_connected: false,
    });

    render(<BackupsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Connect Google Drive" })).toBeInTheDocument();
    });
  });

  it("shows backup list when drive is connected", async () => {
    mockGetJson
      .mockResolvedValueOnce({
        google_configured: true,
        drive_connected: true,
      })
      .mockResolvedValueOnce({
        backups: [
          {
            file_id: "123",
            name: "backup-2026-10-14.json",
            created_at: "2026-10-14T12:00:00Z",
            size_bytes: 1024,
          },
        ],
        drive_error: null,
      });

    render(<BackupsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("backup-2026-10-14.json")).toBeInTheDocument();
    });
  });

  it("does not call restore API until user confirms", async () => {
    mockGetJson
      .mockResolvedValueOnce({
        google_configured: true,
        drive_connected: true,
      })
      .mockResolvedValueOnce({
        backups: [
          {
            file_id: "123",
            name: "backup-2026-10-14.json",
            created_at: "2026-10-14T12:00:00Z",
            size_bytes: 1024,
          },
        ],
        drive_error: null,
      });

    render(<BackupsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("backup-2026-10-14.json")).toBeInTheDocument();
    });

    const restoreButton = screen.getByRole("button", { name: "Restore" });
    fireEvent.click(restoreButton);

    expect(mockSendForm).not.toHaveBeenCalled();

    expect(
      screen.getByText(/This will overwrite all current portfolio/)
    ).toBeInTheDocument();
  });

  it("calls restore API only after confirmation", async () => {
    mockGetJson
      .mockResolvedValueOnce({
        google_configured: true,
        drive_connected: true,
      })
      .mockResolvedValueOnce({
        backups: [
          {
            file_id: "123",
            name: "backup-2026-10-14.json",
            created_at: "2026-10-14T12:00:00Z",
            size_bytes: 1024,
          },
        ],
        drive_error: null,
      });

    mockSendForm.mockResolvedValueOnce({});

    render(<BackupsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("backup-2026-10-14.json")).toBeInTheDocument();
    });

    const restoreButton = screen.getByRole("button", { name: "Restore" });
    fireEvent.click(restoreButton);

    const confirmButton = screen.getAllByRole("button", { name: "Restore" })[1];
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockSendForm).toHaveBeenCalledWith(
        "/api/backups/123/restore",
        expect.any(Object)
      );
    });
  });

  it("shows delete confirmation dialog", async () => {
    mockGetJson
      .mockResolvedValueOnce({
        google_configured: true,
        drive_connected: true,
      })
      .mockResolvedValueOnce({
        backups: [
          {
            file_id: "123",
            name: "backup-2026-10-14.json",
            created_at: "2026-10-14T12:00:00Z",
            size_bytes: 1024,
          },
        ],
        drive_error: null,
      });

    render(<BackupsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("backup-2026-10-14.json")).toBeInTheDocument();
    });

    const deleteButton = screen.getByRole("button", { name: "Delete" });
    fireEvent.click(deleteButton);

    expect(mockSendForm).not.toHaveBeenCalled();

    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument();
  });
});
