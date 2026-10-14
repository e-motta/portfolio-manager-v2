import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";

function renderWithProviders(ui: React.ReactElement, initialEntries = ["/"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  let originalMatchMedia: typeof window.matchMedia;

  beforeEach(() => {
    originalMatchMedia = window.matchMedia;

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          id: "test-user",
          email: "test@example.com",
          name: "Test User",
          picture_url: "",
          display_timezone_label: "UTC",
        }),
    } as Response);
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.restoreAllMocks();
  });

  function mockMediaQuery(matches: boolean) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }

  describe("Desktop viewport (isMobile = false)", () => {
    beforeEach(() => {
      mockMediaQuery(false);
    });

    it("sidebar is NOT aria-hidden on desktop", async () => {
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).toBeInTheDocument();
      expect(sidebar).not.toHaveAttribute("aria-hidden");
    });

    it("sidebar navigation links are accessible on desktop", async () => {
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const nav = screen.getByRole("navigation", { name: "Main" });
      expect(nav).toBeInTheDocument();

      const dashboardLink = screen.getByRole("link", { name: /Dashboard/i });
      expect(dashboardLink).toBeInTheDocument();
    });
  });

  describe("Mobile viewport (isMobile = true)", () => {
    beforeEach(() => {
      mockMediaQuery(true);
    });

    it("sidebar IS aria-hidden when drawer is closed on mobile", async () => {
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).toBeInTheDocument();
      expect(sidebar).toHaveAttribute("aria-hidden", "true");
    });

    it("sidebar is NOT aria-hidden when drawer is open on mobile", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const menuButton = screen.getByRole("button", { name: /Open menu/i });
      await user.click(menuButton);

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).not.toHaveAttribute("aria-hidden");
      expect(sidebar).toHaveClass("is-open");
    });

    it("drawer links are clickable when drawer is open", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const menuButton = screen.getByRole("button", { name: /Open menu/i });
      await user.click(menuButton);

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).toHaveClass("is-open");

      const dashboardLink = screen.getByRole("link", { name: /Dashboard/i });
      expect(dashboardLink).toBeInTheDocument();

      await user.click(dashboardLink);
      expect(sidebar).not.toHaveClass("is-open");
    });

    it("drawer closes when pressing Escape and returns focus to menu button", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const menuButton = screen.getByRole("button", { name: /Open menu/i });
      await user.click(menuButton);

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).toHaveClass("is-open");

      fireEvent.keyDown(window, { key: "Escape" });

      expect(sidebar).not.toHaveClass("is-open");
      expect(menuButton).toHaveFocus();
    });

    it("drawer closes when clicking backdrop and returns focus to menu button", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AppShell />);

      await waitFor(() => {
        expect(screen.getAllByText("Test User").length).toBeGreaterThan(0);
      });

      const menuButton = screen.getByRole("button", { name: /Open menu/i });
      await user.click(menuButton);

      const backdrop = document.querySelector(".drawer-backdrop.is-open");
      expect(backdrop).toBeInTheDocument();

      await user.click(backdrop!);

      const sidebar = document.getElementById("app-sidebar");
      expect(sidebar).not.toHaveClass("is-open");
      expect(menuButton).toHaveFocus();
    });
  });
});
