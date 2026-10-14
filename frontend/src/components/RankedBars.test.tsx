import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RankedBars, RankedBarItem } from "./RankedBars";

describe("RankedBars", () => {
  const mockItems: RankedBarItem[] = [
    { label: "Alimentação fora", slug: "alimentacao-fora", value: -2500, count: 15 },
    { label: "Supermercado", slug: "supermercado", value: -1800, count: 8 },
    { label: "Bills", slug: "bills", value: -3200, count: 5 },
    { label: "Transporte", slug: "transporte", value: -500, count: 20 },
    { label: "Academia e treino", slug: "academia", value: -150, count: 1 },
    { label: "Assinaturas digitais", slug: "assinaturas", value: -300, count: 3 },
    { label: "Casa", slug: "casa", value: -800, count: 2 },
    { label: "Saúde", slug: "saude", value: -400, count: 4 },
    { label: "Bar e lazer", slug: "bar-lazer", value: -600, count: 6 },
    { label: "Outros", slug: "outros", value: -100, count: 2 },
  ];

  it("renders items sorted by absolute value descending", () => {
    render(<RankedBars items={mockItems} topN={10} />);

    const labels = screen.getAllByText(/Bills|Alimentação fora|Supermercado/);
    expect(labels[0]).toHaveTextContent("Bills");
  });

  it("shows only top N items by default", () => {
    render(<RankedBars items={mockItems} topN={5} />);

    const rows = document.querySelectorAll(".ranked-bar-row");
    expect(rows.length).toBe(5);
  });

  it("shows +N more button when items exceed topN", () => {
    render(<RankedBars items={mockItems} topN={5} />);

    const moreButton = screen.getByRole("button", { name: /\+5 more/ });
    expect(moreButton).toBeInTheDocument();
  });

  it("expands to show all items when clicking +N more", () => {
    render(<RankedBars items={mockItems} topN={5} />);

    const moreButton = screen.getByRole("button", { name: /\+5 more/ });
    fireEvent.click(moreButton);

    const rows = document.querySelectorAll(".ranked-bar-row");
    expect(rows.length).toBe(10);
  });

  it("shows Show less button after expanding", () => {
    render(<RankedBars items={mockItems} topN={5} />);

    const moreButton = screen.getByRole("button", { name: /\+5 more/ });
    fireEvent.click(moreButton);

    const lessButton = screen.getByRole("button", { name: /Show less/ });
    expect(lessButton).toBeInTheDocument();
  });

  it("displays percentages that add up to approximately 100%", () => {
    render(<RankedBars items={mockItems} topN={10} showGroupLegend={false} />);

    const pctElements = document.querySelectorAll(".ranked-bar-pct");
    let totalPct = 0;
    pctElements.forEach((el) => {
      const text = el.textContent || "0";
      const num = parseFloat(text.replace(",", ".").replace("%", ""));
      totalPct += num;
    });

    expect(totalPct).toBeGreaterThan(99);
    expect(totalPct).toBeLessThan(101);
  });

  it("shows group legend when enabled", () => {
    render(<RankedBars items={mockItems} topN={5} showGroupLegend={true} />);

    const legend = document.querySelector(".ranked-bars-legend");
    expect(legend).toBeInTheDocument();
  });

  it("hides group legend when disabled", () => {
    render(<RankedBars items={mockItems} topN={5} showGroupLegend={false} />);

    const legend = document.querySelector(".ranked-bars-legend");
    expect(legend).not.toBeInTheDocument();
  });

  it("creates links to category anchors", () => {
    render(<RankedBars items={mockItems} topN={3} />);

    const links = document.querySelectorAll(".ranked-bar-row");
    const firstLink = links[0] as HTMLAnchorElement;
    expect(firstLink.getAttribute("href")).toMatch(/#category-/);
  });

  it("renders bar widths > 0 for negative input values", () => {
    render(<RankedBars items={mockItems} topN={10} showGroupLegend={false} />);

    const fills = document.querySelectorAll(".ranked-bar-fill");
    fills.forEach((fill) => {
      const style = (fill as HTMLElement).style;
      const widthStr = style.width || style.getPropertyValue("width");
      const width = parseFloat(widthStr);
      expect(width).toBeGreaterThan(0);
    });
  });

  it("renders bar widths proportional to absolute values", () => {
    render(<RankedBars items={mockItems} topN={10} showGroupLegend={false} />);

    const fills = document.querySelectorAll(".ranked-bar-fill");
    const widths: number[] = [];
    fills.forEach((fill) => {
      const style = (fill as HTMLElement).style;
      const widthStr = style.width || style.getPropertyValue("width");
      widths.push(parseFloat(widthStr));
    });

    expect(widths[0]).toBe(100);

    const alimentacaoWidth = widths[1];
    const supermercadoWidth = widths[2];

    expect(alimentacaoWidth).toBeCloseTo((2500 / 3200) * 100, 0);
    expect(supermercadoWidth).toBeCloseTo((1800 / 3200) * 100, 0);
  });

  it("displays amounts as absolute values without minus sign", () => {
    render(<RankedBars items={mockItems} topN={3} showGroupLegend={false} />);

    const amounts = document.querySelectorAll(".ranked-bar-amount");
    amounts.forEach((amount) => {
      const text = amount.textContent || "";
      expect(text).not.toMatch(/^-/);
      expect(text).toMatch(/R\$/);
    });
  });

  it("displays +N more total as absolute value without minus sign", () => {
    render(<RankedBars items={mockItems} topN={5} showGroupLegend={false} />);

    const moreButton = screen.getByRole("button", { name: /\+5 more/ });
    const buttonText = moreButton.textContent || "";
    expect(buttonText).not.toMatch(/-R\$/);
    expect(buttonText).toMatch(/R\$/);
  });

  it("applies category group colors to bar fills", () => {
    render(<RankedBars items={mockItems} topN={3} showGroupLegend={false} />);

    const fills = document.querySelectorAll(".ranked-bar-fill");
    fills.forEach((fill) => {
      const style = (fill as HTMLElement).style;
      const bgColor = style.backgroundColor;
      expect(bgColor).toBeTruthy();
      expect(bgColor).not.toBe("");
    });
  });
});
