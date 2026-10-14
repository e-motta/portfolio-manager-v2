import { test, expect } from "@playwright/test";

test.describe("Viewport screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("Dashboard has no horizontal overflow", async ({ page }) => {
    const scrollWidth = await page.evaluate(
      () => document.scrollingElement?.scrollWidth || 0
    );
    const viewportWidth = page.viewportSize()?.width || 0;

    expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("Dashboard screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/dashboard-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});

test.describe("Holdings page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/portfolio/holdings");
    await page.waitForLoadState("networkidle");
  });

  test("Holdings has no horizontal overflow", async ({ page }) => {
    const scrollWidth = await page.evaluate(
      () => document.scrollingElement?.scrollWidth || 0
    );
    const viewportWidth = page.viewportSize()?.width || 0;

    expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("Holdings screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/holdings-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});

test.describe("Expenses page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/finance/expenses");
    await page.waitForLoadState("networkidle");
  });

  test("Expenses has no horizontal overflow", async ({ page }) => {
    const scrollWidth = await page.evaluate(
      () => document.scrollingElement?.scrollWidth || 0
    );
    const viewportWidth = page.viewportSize()?.width || 0;

    expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("Expenses screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/expenses-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});

test.describe("Summary page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/finance/summary");
    await page.waitForLoadState("networkidle");
  });

  test("Summary has no horizontal overflow", async ({ page }) => {
    const scrollWidth = await page.evaluate(
      () => document.scrollingElement?.scrollWidth || 0
    );
    const viewportWidth = page.viewportSize()?.width || 0;

    expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("Summary screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/summary-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});

test.describe("Backups page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/backups");
    await page.waitForLoadState("networkidle");
  });

  test("Backups screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/backups-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});

test.describe("Rebalance page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/portfolio/rebalance");
    await page.waitForLoadState("networkidle");
  });

  test("Rebalance has no horizontal overflow", async ({ page }) => {
    const scrollWidth = await page.evaluate(
      () => document.scrollingElement?.scrollWidth || 0
    );
    const viewportWidth = page.viewportSize()?.width || 0;

    expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("Rebalance screenshot", async ({ page }) => {
    await page.screenshot({
      path: `screenshots/rebalance-${page.viewportSize()?.width}.png`,
      fullPage: true,
    });
  });
});
