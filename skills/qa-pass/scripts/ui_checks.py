# ruff: noqa: T201, INP001 - command-line QA scripts, not app code
"""Phone overflow and dark/light contrast checks with Playwright.

Usage: .tox/e2e/bin/python skills/qa-pass/scripts/ui_checks.py alice /en/ /en/profile/ \
           [--contrast ".future-date-warning"] [--shots /tmp/qa-shots]
Reports horizontal overflow at 390 px for each path, and the contrast ratio (WCAG, 4.5:1 for
normal text) of the first element matching each --contrast selector in both themes.
"""

import argparse
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_common import BASE_URL
from qa_common import password_for

HIDE_TOOLBAR = "#djDebug{display:none!important}"
COLORS_JS = """el => {
    let node = el, bg = 'rgba(0, 0, 0, 0)';
    while (node && bg === 'rgba(0, 0, 0, 0)') {
        bg = getComputedStyle(node).backgroundColor;
        node = node.parentElement;
    }
    return [getComputedStyle(el).color, bg === 'rgba(0, 0, 0, 0)' ? null : bg];
}"""


def contrast(foreground: str, background: str) -> float:
    def luminance(rgb: str) -> float:
        channels = [int(value) / 255 for value in re.findall(r"\d+", rgb)[:3]]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def open_page(browser, user: str, width: int, height: int):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(f"{BASE_URL}/accounts/login/")
    page.fill("#id_login", user)
    page.fill("#id_password", password_for(user))
    page.press("#id_password", "Enter")
    page.wait_for_url(lambda url: "/accounts/login/" not in url)
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--contrast", nargs="*", default=[])
    parser.add_argument("--shots")
    args = parser.parse_args()
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        phone = open_page(browser, args.user, 390, 844)
        desktop = open_page(browser, args.user, 1400, 900)
        for path in args.paths:
            phone.goto(BASE_URL + path, wait_until="networkidle")
            phone.add_style_tag(content=HIDE_TOOLBAR)
            overflow = phone.evaluate("() => document.documentElement.scrollWidth - innerWidth")
            state = "OK" if overflow <= 0 else f"scrolls sideways by {overflow}px"
            print(f"phone {path}: {state}")
            if shots:
                phone.screenshot(path=str(shots / f"phone{path.replace('/', '_')}.png"))
            desktop.goto(BASE_URL + path, wait_until="networkidle")
            for selector in args.contrast:
                element = desktop.locator(selector).first
                if not element.count():
                    continue
                for theme in ("light", "dark"):
                    desktop.evaluate(
                        f"document.documentElement.setAttribute('data-theme', '{theme}')"
                    )
                    desktop.wait_for_timeout(600)  # let colour transitions finish
                    foreground, background = element.evaluate(COLORS_JS)
                    label = f"contrast {path} {selector} [{theme}]"
                    if background is None:
                        # Backgrounds drawn with gradients or images: check the screenshot
                        print(f"{label}: no solid background found, check visually")
                        continue
                    ratio = contrast(foreground, background)
                    flag = "" if ratio >= 4.5 else "  LOW"
                    print(f"{label}: {ratio:.2f}{flag}")
        browser.close()


if __name__ == "__main__":
    main()
