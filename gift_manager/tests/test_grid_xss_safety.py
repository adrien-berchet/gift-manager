"""Regression tests for Grid.js HTML rendering safety."""

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


NODE_BIN = shutil.which("node")


@pytest.mark.skipif(NODE_BIN is None, reason="Node.js is required")
def test_grid_html_helpers_escape_untrusted_values():
    """Shared Grid.js helpers must escape labels, attributes, and dangerous URLs."""
    script = r"""
const fs = require("fs");
const vm = require("vm");

const context = {
  window: {},
  gridjs: { html: (value) => value },
  console,
  setTimeout,
  MouseEvent: function MouseEvent() {},
};
vm.createContext(context);

vm.runInContext(
  fs.readFileSync("gift_manager/static/gift_manager/grid-utils.js", "utf8"),
  context
);

const GridUtils = context.window.GridUtils;
function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const payload = '<img src=x onerror="alert(1)">';
assert(
  GridUtils.escapeHtml(payload) === '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;',
  "escapeHtml should encode executable markup"
);

const link = GridUtils.linkHtml("javascript:alert(1)", payload);
assert(
  link === '<a href="#">&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</a>',
  "linkHtml should sanitize href and text"
);

const externalRelative = GridUtils.linkHtml("//evil.example/path", "off-site");
assert(
  externalRelative === '<a href="#">off-site</a>',
  "protocol-relative URLs should not pass as local URLs"
);

const badge = GridUtils.badgeHtml('x" onmouseover="alert(1)', null, 'badge bg-primary');
assert(
  badge === '<span class="badge bg-primary">x&quot; onmouseover=&quot;alert(1)</span>',
  "badgeHtml should encode badge text"
);

const statusForm = GridUtils.statusSelectFormHtml({
  relationId: 'abc" autofocus onfocus="alert(1)',
  updateUrl: "javascript:alert(1)",
  currentValue: "<script>alert(1)</script>",
  options: [
    { value: "<script>alert(1)</script>", label: "<script>alert(1)</script>" },
  ],
  selectClass: 'foo" onclick="alert(1)',
});
assert(!statusForm.includes("javascript:alert"), "status forms should sanitize update URLs");
assert(statusForm.includes('data-update-url="#"'), "status forms should replace unsafe update URLs");
assert(!statusForm.includes("<script>alert(1)</script>"), "status forms should encode option text and values");
assert(statusForm.includes("&lt;script&gt;alert(1)&lt;/script&gt;"), "status forms should retain escaped labels");
assert(statusForm.includes("abc&quot; autofocus onfocus=&quot;alert(1)"), "status forms should escape relation IDs");

vm.runInContext(
  fs.readFileSync("gift_manager/static/gift_manager/permission-utils.js", "utf8"),
  context
);

const formatter = context.window.PermissionUtils.permissionAwareActionFormatter(
  { details: "/objects/{id}/", edit: "javascript:alert(1)" },
  ["details", "edit"],
  {},
  { [payload]: 20 }
);
const actionsHtml = formatter(payload, { cells: [] });
assert(!actionsHtml.includes("javascript:alert"), "permission action URLs should be sanitized");
assert(actionsHtml.includes('data-entity-id="&lt;img'), "permission action IDs should be escaped");

const fallbackContext = {
  window: {},
  gridjs: { html: (value) => value },
  console,
};
vm.createContext(fallbackContext);
vm.runInContext(
  fs.readFileSync("gift_manager/static/gift_manager/permission-utils.js", "utf8"),
  fallbackContext
);
const fallbackFormatter = fallbackContext.window.PermissionUtils.permissionAwareActionFormatter(
  { details: "//evil.example/path" },
  ["details"],
  {},
  { 1: 10 }
);
const fallbackActionsHtml = fallbackFormatter(1, { cells: [] });
assert(!fallbackActionsHtml.includes("//evil.example"), "fallback URL sanitizer should reject protocol-relative URLs");
"""

    subprocess.run(  # noqa: S603 - fixed Node.js test harness with no shell.
        [NODE_BIN, "-e", script],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
    )


def test_grid_templates_route_html_renderers_through_safe_helpers():
    """Inline Grid.js renderers should build untrusted HTML through GridUtils helpers."""
    unsafe_patterns = [
        'href="${',
        ">${cell",
        ">${name}",
        ">${giftName}",
        ">${eventName}",
        ">${recipientName}",
        '<option value="${',
    ]
    template_paths = [
        PROJECT_ROOT / "gift_manager/templates/gift_manager/gift_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/person_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/event_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/gift_tag_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/relation_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/relation_status_detail.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/relation_list.html",
        PROJECT_ROOT / "gift_manager/templates/gift_manager/person_group_detail.html",
    ]

    for template_path in template_paths:
        content = template_path.read_text()
        assert "GridUtils.linkHtml" in content or "GridUtils.escapeHtml" in content
        for pattern in unsafe_patterns:
            assert pattern not in content, f"{template_path.name} contains unsafe pattern {pattern}"


def test_grid_template_tags_escape_json_and_html():
    """Custom Grid.js template tags should not mark raw user values safe."""
    from gift_manager.templatetags import grid_tags

    payload = '</script><img src=x onerror="alert(1)">'

    data = grid_tags.to_grid_data([{"name": payload}], {"name": "Name"})
    assert "<" not in str(data)
    assert "\\u003C/script\\u003E" in str(data)

    row = grid_tags.grid_data_row({"name": payload, "id": payload}, {"name": "Name"})
    assert "<" not in str(row)
    assert "\\u003Cimg" in str(row)

    email = grid_tags.format_grid_value('x" onclick="alert(1)', "email")
    assert 'onclick="alert(1)' not in str(email)
    assert "&quot; onclick=&quot;alert(1)" in str(email)
