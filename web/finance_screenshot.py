"""Full-page PNG screenshot of the Finance dashboard, for the "visual
snapshot" feature. This is the one place in the project that isn't
Pillow-only (CLAUDE.md documents the e-ink modules as Pillow-only, no
headless browser) — but this dashboard is already React/Chart.js and
never runs on the Pi, so a headless browser here doesn't carry that cost.
Requires a one-time `playwright install chromium` browser download.
"""
import logging

logger = logging.getLogger(__name__)


def capture_finance_screenshot(url: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=30000)
            # Charts render asynchronously after the data fetch resolves and
            # Chart.js animates in — networkidle alone catches them
            # mid-animation, so give them a moment to settle first.
            page.wait_for_timeout(1500)
            return page.screenshot(full_page=True)
        finally:
            browser.close()
