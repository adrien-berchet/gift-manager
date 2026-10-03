"""htmx treats ``hx-indicator`` as a CSS selector and logs an error when nothing matches."""

import re
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"
INVALID_INDICATOR = re.compile(r'hx-indicator\s*=\s*["\']\s*(none|false|null|)\s*["\']', re.I)


def test_templates_do_not_use_a_selectorless_hx_indicator():
    offenders = [
        str(path.relative_to(TEMPLATE_ROOT))
        for path in TEMPLATE_ROOT.rglob("*.html")
        if INVALID_INDICATOR.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "hx-indicator needs a CSS selector; omit it to show no indicator"
