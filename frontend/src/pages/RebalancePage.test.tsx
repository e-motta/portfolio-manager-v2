import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGetJson = vi.fn();

vi.mock("../api/client", () => ({
  getJson: (path: string) => mockGetJson(path),
}));

vi.mock("../components/ComparisonChart", () => ({
  ComparisonChart: () => null,
}));

import { RebalancePage } from "./RebalancePage";

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

describe("RebalancePage", () => {
  beforeEach(() => {
    mockGetJson.mockReset();
    mockGetJson.mockImplementation((path: string) => {
      if (path.includes("/api/allocation/rebalance/")) {
        return Promise.resolve({ suggestions: [], currency: "BRL" });
      }
      return Promise.resolve({ usd_brl_rate: "5.0" });
    });
  });

  it("allows typing '15' without immediate parsing", async () => {
    render(<RebalancePage />, { wrapper: createWrapper() });

    const cashInput = screen.getByLabelText(/Cash to deploy \(BRL\)/i);
    
    fireEvent.change(cashInput, { target: { value: "1" } });
    expect(cashInput).toHaveValue("1");
    
    fireEvent.change(cashInput, { target: { value: "15" } });
    expect(cashInput).toHaveValue("15");
  });

  it("allows typing '12,5' without immediate parsing", async () => {
    render(<RebalancePage />, { wrapper: createWrapper() });

    const cashInput = screen.getByLabelText(/Cash to deploy \(BRL\)/i);
    
    fireEvent.change(cashInput, { target: { value: "12" } });
    expect(cashInput).toHaveValue("12");
    
    fireEvent.change(cashInput, { target: { value: "12," } });
    expect(cashInput).toHaveValue("12,");
    
    fireEvent.change(cashInput, { target: { value: "12,5" } });
    expect(cashInput).toHaveValue("12,5");
  });

  it("formats value on blur", async () => {
    render(<RebalancePage />, { wrapper: createWrapper() });

    const cashInput = screen.getByLabelText(/Cash to deploy \(BRL\)/i);
    
    fireEvent.change(cashInput, { target: { value: "12,5" } });
    expect(cashInput).toHaveValue("12,5");
    
    fireEvent.blur(cashInput);
    expect(cashInput).toHaveValue("12.50");
  });

  it("computes USD value correctly after typing", async () => {
    render(<RebalancePage />, { wrapper: createWrapper() });

    const cashInput = screen.getByLabelText(/Cash to deploy \(BRL\)/i);
    const usdInput = screen.getByLabelText(/Cash to deploy \(USD\)/i);
    
    fireEvent.change(cashInput, { target: { value: "1000" } });
    
    await waitFor(() => {
      expect(usdInput).toHaveValue("200.00");
    });
  });

  it("handles pt-BR thousands input: 1.234,56", async () => {
    render(<RebalancePage />, { wrapper: createWrapper() });

    const cashInput = screen.getByLabelText(/Cash to deploy \(BRL\)/i);
    
    fireEvent.change(cashInput, { target: { value: "1.234,56" } });
    fireEvent.blur(cashInput);
    
    expect(cashInput).toHaveValue("1234.56");
  });
});
