"""Unit tests for the shared Grid.js row action bar (grid-actions.js)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NODE_BIN = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE_BIN is None, reason="Node.js is required")

# Loads the static files into a fake browser window and prints the result of SCENARIO as JSON.
HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const context = {
  window: { gridTranslations: TRANSLATIONS },
  gridjs: { html: (value) => value },
  console: { log: console.log, warn: () => {} },
};
vm.createContext(context);
for (const file of ["grid-utils.js", "grid-actions.js", "permission-utils.js"]) {
  vm.runInContext(fs.readFileSync(`gift_manager/static/gift_manager/${file}`, "utf8"), context);
}
const { window } = context;
const urls = {
  give: "/gifts/{id}/give/",
  details: "/gifts/{id}/",
  edit: "/gifts/{id}/edit/",
  duplicate: "/gifts/{id}/duplicate/",
  delete: "/gifts/{id}/delete/",
  share: "/share/",
};
const row = { cells: [] };
function bar(level, actions) {
  const formatter = level === null
    ? window.GridUtils.actionButtonsFormatter(urls, actions)
    : window.PermissionUtils.permissionAwareActionFormatter(urls, actions, {}, { 7: level });
  return formatter(7, row);
}
console.log(JSON.stringify((() => { SCENARIO })()));
"""


def run_scenario(scenario: str, translations: dict | None = None):
    script = HARNESS.replace("TRANSLATIONS", json.dumps(translations or {})).replace(
        "SCENARIO", scenario
    )
    result = subprocess.run(  # noqa: S603 - fixed Node.js test harness with no shell.
        [NODE_BIN, "-e", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def parse(html: str):
    """Split a rendered bar into its inline part and its overflow menu."""
    inline, _, menu = html.partition('<div class="dropdown grid-action-menu">')
    return inline, menu


ALL_ACTIONS = '["give", "details", "edit", "duplicate", "delete", "share"]'


@pytest.mark.parametrize("level", ["null", "30"])
def test_both_formatters_render_the_dashboard_buttons(level):
    """Plain and permission-aware formatters share icons, variants, and the overflow menu."""
    html = run_scenario(f"return bar({level}, {ALL_ACTIONS});")
    inline, menu = parse(html)

    assert 'class="quick-actions-container grid-action-bar"' in html
    # Inline: quiet utility buttons, one soft Give, and Edit as the only primary action
    assert inline.count("btn-primary") == 1
    assert 'btn-primary quick-action-btn grid-action grid-action--labeled"' in inline
    assert "fa-pen" in inline and "fa-edit" not in inline
    assert "btn-outline-primary quick-action-btn grid-action grid-action--labeled" in inline
    assert inline.count('btn-outline-secondary quick-action-btn grid-action"') == 2
    assert "fa-eye" in inline and "fa-copy" in inline
    for retired in ("btn-info", "btn-warning", "btn-danger", "btn-success", "btn-secondary "):
        assert retired not in html
    # Share and Delete live in the overflow menu only
    assert "fa-trash" not in inline and "fa-share-nodes" not in inline
    assert 'data-bs-toggle="dropdown"' in menu
    assert '"strategy":"fixed"' in menu
    assert 'data-action="delete" data-delete-url="/gifts/7/delete/"' in menu
    assert 'data-action="share"' in menu
    assert menu.index("fa-share-nodes") < menu.index("fa-trash")


def test_actions_follow_the_shared_order_whatever_the_page_lists():
    html = run_scenario('return bar(30, ["delete", "edit", "share", "duplicate", "details"]);')
    inline, _ = parse(html)
    positions = [inline.index(icon) for icon in ("fa-eye", "fa-copy", "fa-pen")]
    assert positions == sorted(positions)


def test_viewer_sees_locked_edit_and_no_overflow_menu():
    html = run_scenario(f"return bar(10, {ALL_ACTIONS});")

    assert "fa-lock" in html
    assert "grid-action--locked" in html
    # The locked button is not an edit trigger for the offcanvas or touch handlers
    assert 'data-action="edit"' not in html
    assert 'data-action-type="edit"' in html
    assert "grid-action-menu" not in html  # neither Share nor Delete is allowed
    assert 'data-action="detail"' in html
    assert 'data-action="create" data-create-url="/gifts/7/duplicate/"' in html
    # Give needs the editor level: shown, but disabled
    assert 'disabled title="You do not have permission to perform this action."' in html


def test_editor_menu_has_share_but_not_delete():
    html = run_scenario(f"return bar(20, {ALL_ACTIONS});")
    _, menu = parse(html)
    assert "fa-share-nodes" in menu
    assert "fa-trash" not in menu
    assert 'data-action="edit"' in html


def test_icons_are_decorative_and_buttons_keep_accessible_names():
    html = run_scenario(f"return bar(30, {ALL_ACTIONS});")
    assert html.count("<i ") == html.count('aria-hidden="true"')
    for label in ("Give", "Details", "Edit", "Duplicate", "More actions"):
        assert f'aria-label="{label}"' in html


def test_labels_and_tooltips_are_translated():
    translations = {
        "actionGive": "Offrir",
        "actionDetails": "Détails",
        "actionEdit": "Éditer",
        "actionDuplicate": "Dupliquer",
        "actionDelete": "Supprimer",
        "actionShare": "Partager",
        "moreActions": "Plus d'actions",
        "editNotPermitted": "Vous n'avez pas la permission de modifier cet élément",
    }
    owner, viewer = run_scenario(
        f"return [bar(30, {ALL_ACTIONS}), bar(10, {ALL_ACTIONS})];", translations
    )
    for text in ("Offrir", "Détails", "Éditer", "Dupliquer", "Supprimer", "Partager"):
        assert text in owner
    assert 'aria-label="Plus d&#39;actions"' in owner
    assert "Vous n&#39;avez pas la permission de modifier cet élément" in viewer
    assert ">Edit<" not in owner


def test_action_config_is_shared():
    config = run_scenario(
        "return Object.fromEntries(Object.entries(window.GridActions.ACTION_CONFIG)"
        ".map(([type, value]) => [type, value.icon]));"
    )
    assert config == {
        "give": "fa-hand-holding-heart",
        "details": "fa-eye",
        "expand": "fa-chevron-down",
        "duplicate": "fa-copy",
        "edit": "fa-pen",
        "share": "fa-share-nodes",
        "delete": "fa-trash",
    }
    sources = {
        name: (PROJECT_ROOT / "gift_manager/static/gift_manager" / name).read_text()
        for name in ("grid-utils.js", "permission-utils.js")
    }
    for name, source in sources.items():
        assert "GridActions.renderActionBar" in source, name
        assert "actionConfig" not in source, f"{name} keeps its own action config"
