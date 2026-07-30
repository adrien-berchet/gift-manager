"""Static frontend contract tests for Phase 5 UX fixes."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = PROJECT_ROOT / "gift_manager/templates/gift_manager"
STATIC_ROOT = PROJECT_ROOT / "gift_manager/static/gift_manager"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_htmx_forms_use_trigger_contract_without_inline_success_handler():
    base = read(TEMPLATE_ROOT / "base.html")
    partials = [
        TEMPLATE_ROOT / "includes/form_partial.html",
        TEMPLATE_ROOT / "includes/person_form_partial.html",
        TEMPLATE_ROOT / "includes/gift_form_partial.html",
        TEMPLATE_ROOT / "includes/event_form_partial.html",
        TEMPLATE_ROOT / "includes/relation_form_partial.html",
        TEMPLATE_ROOT / "includes/person_group_form_partial.html",
        TEMPLATE_ROOT / "includes/gift_tag_form_partial.html",
    ]

    assert "htmx:beforeSwap" in base
    assert "xhr.status === 400 || xhr.status === 422" in base
    assert "showNotification('Changes saved successfully'" not in base
    assert "triggerHeader" not in base
    assert "escapeNotificationHtml(message)" in base

    for partial in partials:
        content = read(partial)
        assert "data-form-type=" in content
        assert "hx-on::after-request" not in content


def test_status_updates_use_shared_helper_and_revert_contract():
    grid_utils = read(STATIC_ROOT / "grid-utils.js")
    status_templates = [
        TEMPLATE_ROOT / "gift_detail.html",
        TEMPLATE_ROOT / "person_detail.html",
        TEMPLATE_ROOT / "event_detail.html",
        TEMPLATE_ROOT / "relation_list.html",
        TEMPLATE_ROOT / "person_group_detail.html",
    ]

    assert "async function updateStatusSelect" in grid_utils
    assert "select.value = previousValue" in grid_utils
    assert "if (!response.ok)" in grid_utils
    assert "document.dispatchEvent(new CustomEvent('list:update'))" in grid_utils
    assert 'data-current-value="${escapeAttribute(currentValue)}"' in grid_utils

    for template in status_templates:
        content = read(template)
        assert "GridUtils.updateStatusSelect(e.target)" in content
        assert "fetch(updateUrl" not in content


def test_share_page_uses_bootstrap5_and_accessible_collapse_controls():
    content = read(TEMPLATE_ROOT / "share_objects.html")

    assert "form-check-input" in content
    assert "form-check-label" in content
    assert "form-check form-switch" in content
    assert "badge text-bg-info" in content
    assert 'data-bs-toggle="collapse"' in content
    assert 'aria-controls="collapsePersons"' in content
    assert "document.addEventListener('DOMContentLoaded'" in content
    assert "$(" not in content

    for legacy_class in [
        "custom-control",
        "custom-checkbox",
        "custom-control-input",
        "custom-control-label",
        "badge badge-info",
        "ml-2",
    ]:
        assert legacy_class not in content


def test_filter_panel_aria_state_is_rendered_and_synchronized():
    template = read(TEMPLATE_ROOT / "includes/filter_panel.html")
    script = read(STATIC_ROOT / "filter-panel.js")

    assert 'aria-expanded="false"' in template
    assert 'aria-controls="{{ grid_id }}-filter-content"' in template
    assert 'for="{{ grid_id }}-search"' in template
    assert 'aria-pressed="false"' in template
    assert 'aria-pressed="true"' in template

    assert "syncFilterExpanded" in script
    assert "filterToggle.setAttribute('aria-expanded'" in script
    assert "multiSortToggle.setAttribute('aria-pressed'" in script
    assert "btn.setAttribute('aria-pressed'" in script


def test_group_tree_has_keyboard_and_touch_move_workflow():
    content = read(TEMPLATE_ROOT / "person_group_list.html")

    assert "tree-move-btn" in content
    assert "groupMoveModal" in content
    assert "group-move-parent" in content
    assert "groupMoveForm.addEventListener('submit'" in content
    assert "validMoveTargets" in content
    assert "await reparentGroup(sourceGroupId, parentIds)" in content


def test_global_search_combobox_and_stale_response_contract():
    content = read(TEMPLATE_ROOT / "base.html")

    assert 'role="combobox"' in content
    assert 'role="listbox"' in content
    assert 'aria-activedescendant=""' in content
    assert "new AbortController()" in content
    assert "searchRequestId" in content
    assert "requestId !== searchRequestId" in content
    assert "safeIconClass" in content
    assert "safeSearchUrl" in content
