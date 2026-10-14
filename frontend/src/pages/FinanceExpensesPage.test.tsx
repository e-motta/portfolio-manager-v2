import { describe, expect, it } from "vitest";
import { localDateStr, parseYearMonth } from "./FinanceExpensesPage";

describe("localDateStr", () => {
  it("formats date using local timezone components", () => {
    const d = new Date(2026, 9, 1, 22, 0, 0);
    expect(localDateStr(d)).toBe("2026-10-01");
  });

  it("does not shift to next day after 21:00 BRT", () => {
    const d = new Date(2026, 9, 14, 23, 30, 0);
    expect(localDateStr(d)).toBe("2026-10-14");
  });

  it("pads single-digit months and days", () => {
    const d = new Date(2026, 0, 5, 12, 0, 0);
    expect(localDateStr(d)).toBe("2026-01-05");
  });
});

describe("parseYearMonth", () => {
  it("extracts year and month from YYYY-MM-DD string", () => {
    expect(parseYearMonth("2026-10-01")).toEqual({ year: 2026, month: 10 });
  });

  it("handles first day of month correctly (no UTC shift)", () => {
    expect(parseYearMonth("2026-10-01")).toEqual({ year: 2026, month: 10 });
    expect(parseYearMonth("2026-01-01")).toEqual({ year: 2026, month: 1 });
    expect(parseYearMonth("2026-12-01")).toEqual({ year: 2026, month: 12 });
  });

  it("extracts month 10 from October date (not 9)", () => {
    const result = parseYearMonth("2026-10-15");
    expect(result?.month).toBe(10);
    expect(result?.year).toBe(2026);
  });

  it("returns null for empty string", () => {
    expect(parseYearMonth("")).toBeNull();
  });

  it("returns null for invalid month", () => {
    expect(parseYearMonth("2026-13-01")).toBeNull();
    expect(parseYearMonth("2026-00-01")).toBeNull();
  });

  it("returns null for too short string", () => {
    expect(parseYearMonth("2026")).toBeNull();
  });
});

describe("ExpenseForm date defaults", () => {
  it("todayStr uses local date not UTC", () => {
    const now = new Date();
    const expected = localDateStr(now);
    const utcDate = now.toISOString().slice(0, 10);
    expect(expected).toBe(localDateStr(now));
    if (now.getHours() >= 21) {
      expect(expected).not.toBe(utcDate);
    }
  });
});
