import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MonthChart, ChartPoint } from "./MonthChart";

describe("MonthChart", () => {
  const mockOnSelect = vi.fn();

  const pointsWithFuture: ChartPoint[] = [
    { month: 1, label: "Jan", income: 5000, expense: -3000, balance: 2000 },
    { month: 2, label: "Feb", income: 6000, expense: -4000, balance: 4000 },
    { month: 3, label: "Mar", income: 0, expense: 0, balance: 0 },
    { month: 4, label: "Apr", income: 0, expense: 0, balance: 0 },
  ];

  it("renders without crashing", () => {
    render(
      <MonthChart
        points={pointsWithFuture}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("does not render balance line for future months with no data", () => {
    const { container } = render(
      <MonthChart
        points={pointsWithFuture}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );

    const lines = container.querySelectorAll(".chart-line");
    expect(lines.length).toBe(1);

    const dots = container.querySelectorAll(".chart-dot");
    expect(dots.length).toBe(2);
  });

  it("shows all bars even for months with no data", () => {
    const { container } = render(
      <MonthChart
        points={pointsWithFuture}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );

    const incomeBarGroups = container.querySelectorAll(".chart-bar.income");
    expect(incomeBarGroups.length).toBe(4);
  });

  it("uses asymmetric axis when expenses are smaller than income", () => {
    const asymmetricPoints: ChartPoint[] = [
      { month: 1, label: "Jan", income: 10000, expense: -1000, balance: 9000 },
      { month: 2, label: "Feb", income: 12000, expense: -1500, balance: 19500 },
    ];

    const { container } = render(
      <MonthChart
        points={asymmetricPoints}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );

    const axisLabels = container.querySelectorAll(".chart-axis");
    const labelTexts = Array.from(axisLabels).map((el) => el.textContent);

    const positiveLabels = labelTexts.filter(
      (t) => t && !t.startsWith("-") && t !== "0"
    );
    const negativeLabels = labelTexts.filter((t) => t && t.startsWith("-"));

    expect(positiveLabels.length).toBeGreaterThan(0);
    expect(negativeLabels.length).toBeGreaterThan(0);
  });

  it("renders month labels", () => {
    const { container } = render(
      <MonthChart
        points={pointsWithFuture}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );

    const labels = container.querySelectorAll(".chart-label");
    expect(labels.length).toBe(4);
  });

  it("shows tap message on touch devices hint", () => {
    render(
      <MonthChart
        points={pointsWithFuture}
        variant="summary"
        onSelect={mockOnSelect}
      />
    );

    const hoverText = screen.getByText(/Click a month|Tap a month/);
    expect(hoverText).toBeInTheDocument();
  });
});
