import { describe, expect, it } from "vitest";
import {
  formatBrl,
  formatSignedBrl,
  formatCompactBrl,
  formatPct,
  parseDecimalInput,
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
  it("parses pt-BR format with thousand separator", () => {
    expect(parseDecimalInput("1.234,56")).toBe("1234.56");
  });

  it("parses pt-BR format without thousand separator", () => {
    expect(parseDecimalInput("1234,56")).toBe("1234.56");
  });

  it("parses US format", () => {
    expect(parseDecimalInput("1234.56")).toBe("1234.56");
  });

  it("parses values with R$ prefix", () => {
    expect(parseDecimalInput("R$ 1.234,56")).toBe("1234.56");
  });

  it("returns null for empty string", () => {
    expect(parseDecimalInput("")).toBe(null);
  });

  it("returns null for non-numeric input", () => {
    expect(parseDecimalInput("abc")).toBe(null);
  });

  it("handles whitespace", () => {
    expect(parseDecimalInput("  1234,56  ")).toBe("1234.56");
  });

  it("handles integer input", () => {
    expect(parseDecimalInput("1234")).toBe("1234.00");
  });
});
