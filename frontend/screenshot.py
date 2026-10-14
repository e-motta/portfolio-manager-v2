#!/usr/bin/env python3
"""
Take Playwright screenshots at specified viewports for UI comparison.
Injects a session cookie to authenticate as demo user.
"""
import sys
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Page


VIEWPORTS = [
    ("desktop", 1440, 900),
    ("phone", 390, 844),
]

PAGES = [
    ("/", "dashboard"),
    ("/portfolio/holdings", "holdings"),
    ("/finance/summary?year=2026", "finance-summary"),
    ("/finance/expenses?year=2026&month=5", "expenses"),
    ("/portfolio/rebalance", "rebalance"),
    ("/finance/expenses?year=2026", "expenses-year"),
]


def take_screenshots(output_dir: str, base_url: str = "http://127.0.0.1:8000"):
    """Take screenshots of all pages at all viewports."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp_name, width, height in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2,
            )
            # Set session cookie to authenticate
            context.add_cookies([
                {
                    "name": "session",
                    "value": "1",  # user_id=1
                    "domain": "127.0.0.1",
                    "path": "/",
                }
            ])
            page = context.new_page()

            for path, name in PAGES:
                url = f"{base_url}{path}"
                print(f"Capturing {vp_name} {name}: {url}")
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(500)  # Wait for animations
                filename = f"{name}-{vp_name}.png"
                page.screenshot(path=str(out / filename), full_page=False)

            context.close()
        browser.close()
    print(f"Screenshots saved to {output_dir}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "/opt/cursor/artifacts/screenshots"
    take_screenshots(output)
