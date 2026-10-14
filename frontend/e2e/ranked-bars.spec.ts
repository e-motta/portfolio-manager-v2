import { test, expect } from "@playwright/test";

test.describe("RankedBars component", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/finance/expenses");
    await page.waitForLoadState("networkidle");
  });

  test("bar fills have rendered width > 0", async ({ page }) => {
    const fills = page.locator(".ranked-bar-fill");
    const count = await fills.count();
    expect(count).toBeGreaterThan(0);

    const firstFill = fills.first();
    const box = await firstFill.boundingBox();

    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);
  });

  test("bar widths are proportional to values", async ({ page }) => {
    const fills = page.locator(".ranked-bar-fill");
    const count = await fills.count();
    expect(count).toBeGreaterThanOrEqual(2);

    const widths: number[] = [];
    for (let i = 0; i < Math.min(count, 8); i++) {
      const box = await fills.nth(i).boundingBox();
      expect(box).not.toBeNull();
      widths.push(box!.width);
    }

    expect(widths[0]).toBeGreaterThan(0);
    expect(widths[0]).toBeGreaterThanOrEqual(widths[1]);

    for (let i = 1; i < widths.length; i++) {
      expect(widths[i]).toBeGreaterThan(0);
      expect(widths[i]).toBeLessThanOrEqual(widths[0]);
    }
  });

  test("amounts display without minus sign", async ({ page }) => {
    const amounts = page.locator(".ranked-bar-amount");
    const count = await amounts.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < Math.min(count, 5); i++) {
      const text = await amounts.nth(i).textContent();
      expect(text).not.toBeNull();
      expect(text).toMatch(/^R\$/);
      expect(text).not.toMatch(/^-/);
    }
  });
});
