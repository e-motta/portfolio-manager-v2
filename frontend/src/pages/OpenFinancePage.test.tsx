import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const mockGetJson = vi.fn();
const mockSendForm = vi.fn();

vi.mock("../api/client", () => ({
  getJson: (path: string) => mockGetJson(path),
  sendForm: (path: string, data: Record<string, unknown>) => mockSendForm(path, data),
  pathFromRedirect: (path: string) => path,
  redirectLocation: () => null,
}));

vi.mock("../components/QueryFlash", () => ({
  QueryFlash: () => null,
}));

import { OpenFinancePage } from "./OpenFinancePage";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const pluggyOnlyStatus = {
  connected: false,
  cumbuca_connected: false,
  pluggy_connected: true,
  connected_at: null,
  pluggy_available: true,
  connections: [
    {
      id: "pluggy-nubank",
      provider: "pluggy",
      external_id: "550e8400-e29b-41d4-a716-446655440000",
      institution_name: "Nubank",
      status: "active",
      last_synced_at: "2026-10-14T12:00:00Z",
      created_at: "2026-10-01T12:00:00Z",
    },
  ],
  has_cumbuca: false,
  has_pluggy: true,
  total_count: 1,
  same_institution_warning: null,
};

describe("OpenFinancePage", () => {
  beforeEach(() => {
    mockGetJson.mockReset();
    mockSendForm.mockReset();
    mockSendForm.mockRejectedValue(new Error("preview skipped"));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the Pluggy card when Cumbuca is disconnected and pluggy is available", async () => {
    mockGetJson.mockImplementation((path: string) => {
      if (path === "/api/open-finance") return Promise.resolve(pluggyOnlyStatus);
      return Promise.resolve({});
    });

    render(<OpenFinancePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Meu Pluggy" })).toBeInTheDocument();
    });
    expect(screen.getByText("Multiple banks via item ID")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cumbuca" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect" })).toHaveAttribute("href", "/auth/cumbuca");
    expect(screen.queryByText(/both connected/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/appears connected via both/i)).not.toBeInTheDocument();
    expect(screen.getByText("Nubank")).toBeInTheDocument();
  });

  it("calls per-connection Pluggy preview endpoints", async () => {
    mockGetJson.mockImplementation((path: string) => {
      if (path === "/api/open-finance") return Promise.resolve(pluggyOnlyStatus);
      return Promise.resolve({});
    });

    render(<OpenFinancePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText("Nubank")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Account debits" }));
    await waitFor(() => {
      expect(mockSendForm).toHaveBeenCalledWith(
        "/api/open-finance/pluggy/sync/expenses/preview",
        expect.objectContaining({ connection_id: "pluggy-nubank" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Credits" }));
    await waitFor(() => {
      expect(mockSendForm).toHaveBeenCalledWith(
        "/api/open-finance/pluggy/sync/income/preview",
        expect.objectContaining({ connection_id: "pluggy-nubank" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Card purchases" }));
    await waitFor(() => {
      expect(mockSendForm).toHaveBeenCalledWith(
        "/api/open-finance/pluggy/sync/credit-card/preview",
        expect.objectContaining({ connection_id: "pluggy-nubank" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Investments" }));
    await waitFor(() => {
      expect(mockSendForm).toHaveBeenCalledWith(
        "/api/open-finance/pluggy/sync/investments/preview",
        expect.objectContaining({ connection_id: "pluggy-nubank" }),
      );
    });
  });
});
