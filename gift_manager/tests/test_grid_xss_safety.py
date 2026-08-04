"""Regression tests for Grid.js HTML rendering safety."""

import shutil
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

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


@pytest.mark.skipif(NODE_BIN is None, reason="Node.js is required")
def test_status_update_helper_reverts_failed_updates():
    """Status update helper should not replace forms with error JSON."""
    script = r"""
const fs = require("fs");
const vm = require("vm");

const context = {
  window: {},
  document: { cookie: "csrftoken=test-token" },
  URLSearchParams,
  console,
  alert: (message) => { context.alertMessage = message; },
  fetch: async (url, options) => {
    context.request = { url, options };
    return {
      ok: false,
      status: 403,
      headers: { get: () => "application/json" },
      json: async () => ({ error: "Forbidden" }),
      text: async () => "Forbidden",
    };
  },
};
vm.createContext(context);

vm.runInContext(
  fs.readFileSync("gift_manager/static/gift_manager/grid-utils.js", "utf8"),
  context
);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

(async () => {
  const fakeForm = {
    outerHTML: "<form>original</form>",
    classList: {
      classes: new Set(),
      add(name) { this.classes.add(name); },
      remove(name) { this.classes.delete(name); },
    },
  };
  const fakeSelect = {
    dataset: { relationId: "rel-1", updateUrl: "/status/", currentValue: "1" },
    defaultValue: "1",
    value: "2",
    disabled: false,
    isConnected: true,
    attrs: {},
    closest(selector) { return selector === "form" ? fakeForm : null; },
    setAttribute(name, value) { this.attrs[name] = value; },
    removeAttribute(name) { delete this.attrs[name]; },
  };

  context.window.showNotification = (message, type) => {
    context.toast = { message, type };
  };

  const updated = await context.window.GridUtils.updateStatusSelect(fakeSelect);

  assert(updated === false, "failed updates should return false");
  assert(fakeSelect.value === "1", "failed updates should restore the previous value");
  assert(fakeSelect.disabled === false, "failed updates should re-enable the select");
  assert(!("aria-busy" in fakeSelect.attrs), "failed updates should clear aria-busy");
  assert(fakeForm.outerHTML === "<form>original</form>", "failed updates should not replace form HTML");
  assert(context.toast.type === "error", "failed updates should show an error toast");

  const body = new URLSearchParams(context.request.options.body);
  assert(body.get("relation_id") === "rel-1", "request should send the relation id");
  assert(body.get("new_status") === "2", "request should send the selected status");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""

    subprocess.run(  # noqa: S603 - fixed Node.js test harness with no shell.
        [NODE_BIN, "-e", script],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
    )


@pytest.mark.frontend
@pytest.mark.playwright
def test_grid_html_helpers_render_hostile_values_safely_in_browser():
    """Hostile formatter values should render as text in a real browser DOM."""
    payload = '<img src=x onerror="window.__xssExecuted = true">'
    grid_utils = (PROJECT_ROOT / "gift_manager/static/gift_manager/grid-utils.js").read_text()

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Playwright Chromium browser is not installed")

        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium could not launch: {exc}")

        try:
            page = browser.new_page()
            page.set_content(
                """
                <!doctype html>
                <html>
                  <body>
                    <div id="root"></div>
                    <script>
                      window.__xssExecuted = false;
                      window.gridjs = { html: (value) => value };
                    </script>
                  </body>
                </html>
                """,
            )
            page.add_script_tag(content=grid_utils)

            safe_html = page.evaluate(
                "payload => window.GridUtils.linkHtml('/safe/', payload)",
                payload,
            )
            page.locator("#root").evaluate("(node, html) => { node.innerHTML = html; }", safe_html)
            page.wait_for_timeout(100)

            assert page.evaluate("window.__xssExecuted") is False
            assert page.locator("#root img").count() == 0
            assert payload in page.locator("#root").inner_text()
        finally:
            browser.close()


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
        has_inline_grid_renderer = (
            "GridUtils." in content or "gridjs.html" in content or "formatter:" in content
        )
        if not has_inline_grid_renderer:
            continue

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
