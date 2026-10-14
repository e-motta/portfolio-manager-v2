import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { DonutChart } from "./DonutChart";

describe("DonutChart", () => {
  it("renders slices with unique keys even with existing Outros slice", () => {
    const slices = [
      { label: "Outros", value: 5000 },
      { label: "Alimentação", value: 3000 },
      { label: "Transporte", value: 2000 },
      { label: "Small1", value: 10 },
      { label: "Small2", value: 10 },
    ];
    const { container } = render(<DonutChart slices={slices} />);
    const legendItems = container.querySelectorAll(".donut-legend li");
    expect(legendItems.length).toBeGreaterThan(0);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBeGreaterThan(1);
  });

  it("groups small slices into Outros without key collision", () => {
    const slices = [
      { label: "Outros", value: 5000 },
      { label: "Big", value: 10000 },
      { label: "Tiny1", value: 1 },
      { label: "Tiny2", value: 1 },
      { label: "Tiny3", value: 1 },
    ];
    const { container } = render(<DonutChart slices={slices} />);
    const outrosItems = Array.from(container.querySelectorAll(".donut-legend li span"))
      .filter((el) => el.textContent === "Outros");
    expect(outrosItems.length).toBe(2);
  });

  it("has accessible role and aria-label", () => {
    const slices = [
      { label: "Food", value: 100 },
      { label: "Transport", value: 50 },
    ];
    const { container } = render(<DonutChart slices={slices} centerLabel="Expenses" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("role", "img");
    expect(svg).toHaveAttribute("aria-label");
    expect(svg?.getAttribute("aria-label")).toContain("Expenses");
  });
});
