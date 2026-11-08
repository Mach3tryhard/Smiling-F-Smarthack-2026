"""Automated UI checks for the PPC EV Siting Lab frontend.

Runs the local frontend in headless Edge via Playwright and asserts the
interactions that were broken:

* wheel/button zoom changes the scale smoothly instead of snapping,
* confidence filters update the map, the list and the details panel,
* double-clicking a recommended site opens its decision trace (not Rankings),
* the trace includes driver values and city medians,
* rank digits use the body font (not the display face) and are centred.

Usage (server already running at http://127.0.0.1:8000):
    .venv\\Scripts\\python.exe tools\\ui_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000/"
ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-6
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

        page.goto(URL, wait_until="networkidle")
        page.wait_for_function("window.__ppc && window.__ppc.state.data && window.__ppc.state.map.fitted")
        page.wait_for_timeout(300)

        check("no JS errors on load", not errors, "; ".join(errors[:3]))

        # ---- zoom -------------------------------------------------------
        canvas = page.locator("#mapCanvas")
        box = canvas.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        fit_scale = page.evaluate("window.__ppc.state.map.fitScale")
        check("fit scale is the fitted city scale", fit_scale > 10, f"fitScale={fit_scale:.1f}")

        page.mouse.move(cx, cy)
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(150)
        zoomed = page.evaluate("window.__ppc.state.map.scale")
        check("wheel zoom in is a small step, not a snap", fit_scale < zoomed < fit_scale * 1.5, f"{fit_scale:.1f} -> {zoomed:.1f}")

        page.mouse.wheel(0, 120)
        page.wait_for_timeout(150)
        restored = page.evaluate("window.__ppc.state.map.scale")
        check("wheel zoom out returns near the fit", abs(restored - fit_scale) < fit_scale * 0.15, f"{restored:.1f}")

        page.click("#zoomIn")
        page.wait_for_timeout(120)
        button_zoom = page.evaluate("window.__ppc.state.map.scale")
        check("zoom-in button changes the scale", button_zoom > restored, f"{restored:.1f} -> {button_zoom:.1f}")
        page.click("#fitMap")
        page.wait_for_timeout(120)
        refit = page.evaluate("window.__ppc.state.map.scale")
        check("fit button restores the fit", abs(refit - fit_scale) < TOLERANCE, f"{refit:.3f}")

        # ---- filters ----------------------------------------------------
        counts = page.locator("#confidenceFilters .chip b").all_text_contents()
        total = page.locator("#cityActionList .action-item").count()
        check("chips show per-city counts", len(counts) == 4 and counts[0].isdigit(), f"{counts}")
        check("list starts with all sites", total > 0, f"{total} items")

        page.click("#confidenceFilters .chip[data-confidence='medium']")
        page.wait_for_timeout(150)
        medium_items = page.locator("#cityActionList .action-item").count()
        kpis = page.locator("#mapKpis").inner_text()
        hidden_note = page.locator("#emptyFilterNote").is_visible()
        check("medium filter empties a high-only city", medium_items == 0, f"{medium_items} items")
        check("map KPI reflects the filter", "0 din" in kpis, kpis.replace("\n", " "))
        check("details show the filter empty state", hidden_note)

        page.click("#confidenceFilters .chip[data-confidence='high']")
        page.wait_for_timeout(150)
        high_items = page.locator("#cityActionList .action-item").count()
        check("high filter restores the high sites", high_items == int(counts[1]), f"{high_items} items")

        page.click("#confidenceFilters .chip[data-confidence='all']")
        page.wait_for_timeout(150)
        check("all filter restores every site", page.locator("#cityActionList .action-item").count() == total)

        # selected action must not survive a filter that excludes it
        page.locator("#cityActionList .action-item").first.click()
        page.wait_for_timeout(100)
        selected_before = page.evaluate("window.__ppc.state.selectedNode")
        page.click("#confidenceFilters .chip[data-confidence='low']")
        page.wait_for_timeout(150)
        selected_after = page.evaluate("window.__ppc.state.selectedNode")
        check("selection follows the filter", selected_after is None or selected_after != selected_before,
              f"{selected_before} -> {selected_after}")
        page.click("#confidenceFilters .chip[data-confidence='all']")
        page.wait_for_timeout(150)

        # ---- double-click a recommendation ------------------------------
        coords = page.evaluate(
            """() => {
                const city = window.__ppc.currentCity();
                const action = city.actions[0];
                const [x, y] = window.__ppc.worldToScreen(city.nodes[action.node_id][0], city.nodes[action.node_id][1]);
                const rect = document.querySelector('#mapCanvas').getBoundingClientRect();
                return { x: rect.left + x, y: rect.top + y, action: action.action_id, node: action.node_id };
            }"""
        )
        page.mouse.dblclick(coords["x"], coords["y"])
        page.wait_for_timeout(400)
        view = page.evaluate("window.__ppc.state.view")
        modal = page.locator("#whyModal").is_visible()
        driver_text = page.locator("#whyContent .why-row .feat small").first.inner_text()
        check("double-click opens the decision trace", view == "map" and modal, f"{view}, modal={modal}")
        check("decision trace shows values and medians", "valoare" in driver_text and "mediana" in driver_text, driver_text)
        page.locator("#closeWhyBtn").click()
        page.wait_for_timeout(150)
        check("decision trace closes", page.locator("#whyModal").is_hidden())

        page.click(".tab[data-view='map']")
        page.wait_for_timeout(200)

        # ---- mixed-confidence city --------------------------------------
        page.select_option("#citySelect", "test_204618")
        page.wait_for_timeout(350)
        mixed_counts = page.locator("#confidenceFilters .chip b").all_text_contents()
        check("mixed city has a medium site", mixed_counts[2] == "1", f"{mixed_counts}")
        page.click("#confidenceFilters .chip[data-confidence='medium']")
        page.wait_for_timeout(150)
        check("medium filter shows exactly one site", page.locator("#cityActionList .action-item").count() == 1)
        check("medium site is selected", page.evaluate("window.__ppc.state.selectedNode") is not None)

        # Selecting a recommendation from another city must reveal it (reset filter).
        page.locator("#topRecommendations .top-item").first.click()
        page.wait_for_timeout(350)
        check("opening a filtered-out site resets the filter", page.evaluate("window.__ppc.state.confidence") == "all",
              page.evaluate("window.__ppc.state.confidence"))

        # ---- review-only filter -----------------------------------------
        page.select_option("#citySelect", "test_204606")
        page.wait_for_timeout(350)
        page.evaluate("document.querySelector('#reviewOnly').click()")
        page.wait_for_timeout(150)
        review_items = page.locator("#cityActionList .action-item").count()
        review_kpi = page.locator("#mapKpis").inner_text()
        check("review-only filter shows the review sites", review_items > 0, f"{review_items} items")
        check("map KPI reflects review-only", f"{review_items} din" in review_kpi, review_kpi.replace("\n", " "))
        page.evaluate("document.querySelector('#reviewOnly').click()")
        page.wait_for_timeout(150)
        check("review-only toggle can be cleared", page.locator("#cityActionList .action-item").count() == 8)

        # ---- K control ---------------------------------------------------
        page.select_option("#citySelect", "test_204600")
        page.wait_for_timeout(300)
        page.fill("#kInput", "3")
        page.locator("#kInput").press("Enter")
        page.wait_for_timeout(250)
        check("K=3 limits the city list", page.locator("#cityActionList .action-item").count() == 3)
        checks_kpi = page.locator("#mapKpis").inner_text()
        check("K=3 is shown in the map KPI", "3 recomandări" in checks_kpi, checks_kpi.replace("\n", " "))
        page.click(".tab[data-view='leaderboard']")
        page.wait_for_timeout(250)
        check("K=3 limits the ranking", page.locator("#leaderboardBody tr").count() == 120)
        page.click(".tab[data-view='map']")
        page.wait_for_timeout(200)
        page.fill("#kInput", "12")
        page.locator("#kInput").press("Enter")
        page.wait_for_timeout(350)
        check("K=12 allows the extended list", page.locator("#cityActionList .action-item").count() == 12)
        page.click(".tab[data-view='leaderboard']")
        page.wait_for_timeout(250)
        check("K=12 extends the ranking", page.locator("#leaderboardBody tr").count() == 480)
        page.click(".tab[data-view='map']")
        page.wait_for_timeout(200)
        page.locator("#cityActionList .action-item").last.click()
        page.wait_for_timeout(250)
        extension_copy = page.locator("[data-copy-action]").is_disabled()
        check("K>8 marks the CSV row as unavailable", extension_copy, "copy disabled")
        page.fill("#kInput", "8")
        page.locator("#kInput").press("Enter")
        page.wait_for_timeout(300)

        # ---- typography -------------------------------------------------
        fonts = page.evaluate(
            """() => {
                const pick = (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;
                    const style = getComputedStyle(el);
                    return { font: style.fontFamily, size: style.fontSize, line: style.lineHeight };
                };
                return { top: pick('.top-rank'), step: pick('.step-num'), rank: pick('.rank-badge strong') };
            }"""
        )
        for key, value in fonts.items():
            if value:
                size = float(value["size"].replace("px", ""))
                line = value["line"]
                line_px = size if line in ("normal", "1") else float(line.replace("px", ""))
                check(f"{key} rank digits use the body font", "Inter" in value["font"], value["font"])
                check(f"{key} rank digits are optically centred", abs(line_px - size) <= 1.5, f"{value['size']} / {value['line']}")

        page.screenshot(path=str(ROOT / "tools" / "ui_check_map.png"), full_page=False)
        page.click(".tab[data-view='model']")
        page.wait_for_timeout(250)
        page.screenshot(path=str(ROOT / "tools" / "ui_check_model.png"), full_page=False)

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: " + ", ".join(failures))
        return 1
    print("All UI checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
