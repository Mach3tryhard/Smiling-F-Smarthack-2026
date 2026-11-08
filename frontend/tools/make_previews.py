"""Regenerate the README preview screenshots from the running frontend.

Usage (server already running at http://127.0.0.1:8000):
    .venv\\Scripts\\python.exe tools\\make_previews.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000/"
ROOT = Path(__file__).resolve().parents[1]


def capture(page, name: str) -> None:
    path = ROOT / name
    page.screenshot(path=str(path))
    print(f"wrote {path.name}")


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(URL, wait_until="networkidle")
        page.wait_for_function("window.__ppc && window.__ppc.state.data && window.__ppc.state.map.fitted")
        page.wait_for_timeout(400)
        page.locator("#cityActionList .action-item").first.click()
        page.wait_for_timeout(300)
        capture(page, "preview.png")

        page.locator("[data-why-action]").click()
        page.wait_for_timeout(300)
        capture(page, "preview-why.png")
        page.locator("#closeWhyBtn").click()
        page.wait_for_timeout(200)

        page.click(".tab[data-view='leaderboard']")
        page.wait_for_timeout(300)
        capture(page, "preview-leaderboard.png")

        page.click(".tab[data-view='csv']")
        page.wait_for_timeout(300)
        capture(page, "preview-csv.png")

        page.click(".tab[data-view='model']")
        page.wait_for_timeout(300)
        capture(page, "preview-model.png")

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.goto(URL, wait_until="networkidle")
        mobile.wait_for_function("window.__ppc && window.__ppc.state.data && window.__ppc.state.map.fitted")
        mobile.wait_for_timeout(400)
        mobile.screenshot(path=str(ROOT / "preview-mobile.png"))
        print("wrote preview-mobile.png")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
