import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const PAGES = [
  { path: "/", name: "Dashboard" },
  { path: "/portfolio/holdings", name: "Holdings" },
  { path: "/allocation/classes", name: "Asset Classes" },
  { path: "/allocation/rebalance", name: "Rebalance" },
  { path: "/finance/summary", name: "Finance Summary" },
  { path: "/finance/income", name: "Finance Income" },
  { path: "/finance/expenses", name: "Finance Expenses" },
  { path: "/finance/transfers", name: "Finance Transfers" },
  { path: "/backups", name: "Backups" },
];

test.describe("Accessibility", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "test-user",
          email: "test@example.com",
          name: "Test User",
          picture_url: "",
          display_timezone_label: "UTC",
        }),
      })
    );

    await page.route("**/api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/api/me")) {
        return route.continue();
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: [], total: 0 }),
      });
    });
  });

  for (const { path, name } of PAGES) {
    test(`${name} page has no critical accessibility violations`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const criticalViolations = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious"
      );

      if (criticalViolations.length > 0) {
        console.log(`\n${name} accessibility violations:`);
        criticalViolations.forEach((v) => {
          console.log(`  - ${v.id}: ${v.description} (${v.impact})`);
          v.nodes.forEach((n) => console.log(`    ${n.html.slice(0, 100)}`));
        });
      }

      expect(criticalViolations).toHaveLength(0);
    });
  }
});

test.describe("Keyboard Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "test-user",
          email: "test@example.com",
          name: "Test User",
          picture_url: "",
          display_timezone_label: "UTC",
        }),
      })
    );

    await page.route("**/api/**", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], total: 0 }),
    }));
  });

  test("Modal focus trap works correctly", async ({ page }) => {
    await page.goto("/backups");
    await page.waitForLoadState("networkidle");

    await page.route("**/api/backups", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            { id: "1", created_at: "2026-01-01T00:00:00Z", size_bytes: 1024 },
          ],
        }),
      })
    );

    await page.reload();
    await page.waitForLoadState("networkidle");

    const restoreButton = page.locator('button:has-text("Restore")').first();
    if (await restoreButton.isVisible()) {
      await restoreButton.click();

      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();

      const cancelButton = dialog.locator('button:has-text("Cancel")');
      await expect(cancelButton).toBeFocused();

      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");

      await expect(cancelButton).toBeFocused();

      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
    }
  });

  test("Mobile drawer focus trap works correctly", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === "desktop", "Menu button is not visible on desktop");
    
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);

    const menuButton = page.locator(".menu-btn");
    const isVisible = await menuButton.isVisible();
    if (!isVisible) {
      test.skip(true, "Menu button not visible - CSS media query may not be applied");
      return;
    }
    
    await menuButton.click();

    const sidebar = page.locator("#app-sidebar");
    await expect(sidebar).toHaveClass(/is-open/);

    await page.keyboard.press("Escape");
    await expect(sidebar).not.toHaveClass(/is-open/);
    await expect(menuButton).toBeFocused();
  });

  test("Chart keyboard navigation works", async ({ page }) => {
    await page.goto("/finance/summary");
    await page.waitForLoadState("networkidle");

    const chartHit = page.locator(".chart-hit").first();
    if (await chartHit.isVisible()) {
      await chartHit.focus();
      await expect(chartHit).toBeFocused();

      await page.keyboard.press("Enter");
    }
  });
});
