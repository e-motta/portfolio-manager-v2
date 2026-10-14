import { describe, expect, it } from "vitest";
import {
  formatBrl,
  formatSignedBrl,
  formatCompactBrl,
  formatPct,
  parseDecimalInput,
  parsePercentInput,
} from "./format";

describe("formatBrl", () => {
  it("formats positive values in pt-BR style", () => {
    const result = formatBrl(1234.5);
    expect(result).toMatch(/R\$\s*1\.234,50/);
  });

  it("formats negative values with minus sign", () => {
    const result = formatBrl(-1234.5);
    expect(result).toMatch(/-R\$\s*1\.234,50/);
  });

  it("formats zero", () => {
    const result = formatBrl(0);
    expect(result).toMatch(/R\$\s*0,00/);
  });

  it("formats large values", () => {
    const result = formatBrl(123456.78);
    expect(result).toMatch(/R\$\s*123\.456,78/);
  });
});

describe("formatSignedBrl", () => {
  it("formats positive values with + prefix", () => {
    const result = formatSignedBrl(1234.5);
    expect(result).toMatch(/\+R\$\s*1\.234,50/);
  });

  it("formats negative values with - prefix", () => {
    const result = formatSignedBrl(-1234.5);
    expect(result).toMatch(/-R\$\s*1\.234,50/);
  });

  it("formats zero without sign", () => {
    const result = formatSignedBrl(0);
    expect(result).toMatch(/R\$\s*0,00/);
    expect(result).not.toMatch(/[+-]/);
  });
});

describe("formatCompactBrl", () => {
  it("formats small values without compaction", () => {
    const result = formatCompactBrl(1234.5);
    expect(result).toMatch(/R\$\s*1\.234,50/);
  });

  it("formats large values with compact notation", () => {
    const result = formatCompactBrl(103000);
    expect(result).toMatch(/R\$\s*103\s*mil/);
  });

  it("formats millions", () => {
    const result = formatCompactBrl(2500000);
    expect(result).toMatch(/R\$\s*2,5\s*mi/);
  });

  it("formats negative compact values", () => {
    const result = formatCompactBrl(-50000);
    expect(result).toMatch(/-R\$\s*50\s*mil/);
  });
});

describe("formatPct", () => {
  it("formats decimal as percentage in pt-BR style", () => {
    const result = formatPct(0.621);
    expect(result).toBe("62,1%");
  });

  it("formats with custom digits", () => {
    const result = formatPct(0.6215, 2);
    expect(result).toBe("62,15%");
  });

  it("returns dash for null/undefined", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(undefined)).toBe("—");
  });
});

describe("parseDecimalInput", () => {
  it("parses pt-BR format with comma as decimal: 0,125 -> 0.13", () => {
    expect(parseDecimalInput("0,125")).toBe("0.13");
  });

  it("parses pt-BR comma decimal: 1,234 -> 1.23", () => {
    expect(parseDecimalInput("1,234")).toBe("1.23");
  });

  it("parses dot-only thousands: 1.234 (dot+3 digits) -> 1234.00", () => {
    expect(parseDecimalInput("1.234")).toBe("1234.00");
  });

  it("parses multiple dots as thousands: 1.234.567 -> 1234567.00", () => {
    expect(parseDecimalInput("1.234.567")).toBe("1234567.00");
  });

  it("parses full pt-BR format: 1.234,56 -> 1234.56", () => {
    expect(parseDecimalInput("1.234,56")).toBe("1234.56");
  });

  it("parses comma decimal: 12,5 -> 12.50", () => {
    expect(parseDecimalInput("12,5")).toBe("12.50");
  });

  it("parses dot decimal: 12.5 -> 12.50", () => {
    expect(parseDecimalInput("12.5")).toBe("12.50");
  });

  it("parses dot decimal: 1.5 -> 1.50", () => {
    expect(parseDecimalInput("1.5")).toBe("1.50");
  });

  it("parses integer: 1234 -> 1234.00", () => {
    expect(parseDecimalInput("1234")).toBe("1234.00");
  });

  it("returns null for empty string", () => {
    expect(parseDecimalInput("")).toBe(null);
  });

  it("returns null for invalid input: abc", () => {
    expect(parseDecimalInput("abc")).toBe(null);
  });

  it("parses negative values: -1234,56 -> -1234.56", () => {
    expect(parseDecimalInput("-1234,56")).toBe("-1234.56");
  });

  it("parses negative values: -1.234 -> -1234.00", () => {
    expect(parseDecimalInput("-1.234")).toBe("-1234.00");
  });

  it("parses values with R$ prefix", () => {
    expect(parseDecimalInput("R$ 1.234,56")).toBe("1234.56");
  });

  it("handles whitespace", () => {
    expect(parseDecimalInput("  1234,56  ")).toBe("1234.56");
  });
});

describe("parsePercentInput", () => {
  it("parses percent with comma: 33,333 -> 33.333", () => {
    expect(parsePercentInput("33,333")).toBe("33.333");
  });

  it("parses percent with dot: 33.333 -> 33.333", () => {
    expect(parsePercentInput("33.333")).toBe("33.333");
  });

  it("parses percent with trailing %: 50,5% -> 50.5", () => {
    expect(parsePercentInput("50,5%")).toBe("50.5");
  });

  it("parses integer percent: 100 -> 100", () => {
    expect(parsePercentInput("100")).toBe("100");
  });

  it("parses small decimal: 0,125 -> 0.125", () => {
    expect(parsePercentInput("0,125")).toBe("0.125");
  });

  it("returns null for empty string", () => {
    expect(parsePercentInput("")).toBe(null);
  });

  it("returns null for invalid input", () => {
    expect(parsePercentInput("abc")).toBe(null);
  });

  it("parses negative percent: -5,5 -> -5.5", () => {
    expect(parsePercentInput("-5,5")).toBe("-5.5");
  });
});
