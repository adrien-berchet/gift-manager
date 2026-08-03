"""Static frontend contract tests for Phase 5 UX fixes."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = PROJECT_ROOT / "gift_manager/templates/gift_manager"
STATIC_ROOT = PROJECT_ROOT / "gift_manager/static/gift_manager"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def css_block(styles: str, selector: str) -> str:
    start = styles.index(f"\n{selector} {{")
    block_start = styles.index("{", start)
    block_end = styles.index("}", block_start)
    return styles[block_start:block_end]


def test_htmx_forms_use_trigger_contract_without_inline_success_handler():
    base = read(TEMPLATE_ROOT / "base.html")
    offcanvas = read(TEMPLATE_ROOT / "includes/offcanvas_base.html")
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
    assert "parseHxTriggerEvents" in base
    assert "dispatchManagedFormTriggerFallback" in base
    assert "offcanvas:close" in base
    assert "list:update" in base
    assert "escapeNotificationHtml(message)" in base
    assert "function loadFormInPanel" in base
    assert "loadFormInPanel(editUrl, target)" in base
    assert "loadFormInPanel(createUrl, 'editPanel')" in base
    assert "offcanvas.classList.add('is-saving')" in offcanvas
    assert "showOffcanvasLoading(panelId);" not in offcanvas

    for partial in partials:
        content = read(partial)
        assert "data-form-type=" in content
        assert "hx-on::after-request" not in content

    relation_form = read(TEMPLATE_ROOT / "includes/relation_form_partial.html")
    assert 'hx-trigger="submit"' in relation_form
    assert 'hx-target="this"' in relation_form
    assert 'hx-swap="outerHTML"' in relation_form
    assert 'hx-target="#offcanvasContent"' not in relation_form


def test_status_updates_use_shared_helper_and_revert_contract():
    grid_utils = read(STATIC_ROOT / "grid-utils.js")
    status_templates = [
        TEMPLATE_ROOT / "relation_list.html",
        TEMPLATE_ROOT / "person_group_detail.html",
    ]
    unified_detail_templates = [
        TEMPLATE_ROOT / "gift_detail.html",
        TEMPLATE_ROOT / "person_detail.html",
        TEMPLATE_ROOT / "event_detail.html",
        TEMPLATE_ROOT / "relation_detail.html",
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

    for template in unified_detail_templates:
        content = read(template)
        assert "GridUtils.updateStatusSelect(e.target)" not in content
        assert "includes/" in content
        assert "full_page_detail=True" in content


def test_share_page_uses_bootstrap5_and_accessible_collapse_controls():
    content = read(TEMPLATE_ROOT / "share_objects.html")

    assert "form-check-input" in content
    assert "form-check-label" in content
    assert "form-check form-switch" in content
    assert "badge text-bg-info" in content
    assert 'data-bs-toggle="collapse"' in content
    assert 'aria-controls="collapsePersons"' in content
    assert "document.addEventListener('DOMContentLoaded'" in content
    assert 'id="share-button"' in content
    assert 'id="share-button" disabled' not in content
    assert "shareButton.disabled = true;" in content
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
    visible_search_template = read(TEMPLATE_ROOT / "includes/list_search_control.html")
    script = read(STATIC_ROOT / "filter-panel.js")
    dynamic_filters = read(STATIC_ROOT / "dynamic-filters.js")

    assert 'aria-expanded="false"' in template
    assert 'aria-controls="{{ grid_id }}-filter-content"' in template
    assert 'for="{{ grid_id }}-search"' in visible_search_template
    assert 'id="{{ grid_id }}-search"' in visible_search_template
    assert 'aria-pressed="false"' in template
    assert 'aria-pressed="true"' in template

    assert "syncFilterExpanded" in script
    assert "const controlRoot = listTools || filterPanel || filterContent;" in script
    assert "filterToggle.setAttribute('aria-expanded'" in script
    assert "multiSortToggle.setAttribute('aria-pressed'" in script
    assert "btn.setAttribute('aria-pressed'" in script
    assert "searchableIndices: getSearchableColumnIndices(columns)" in dynamic_filters
    assert "function matchesSearchTerm" in dynamic_filters
    assert "applyFilters(grid, originalData, filterState);" in dynamic_filters


def test_base_renders_skip_link_and_static_live_region():
    content = read(TEMPLATE_ROOT / "base.html")
    accessibility_styles = read(STATIC_ROOT / "css/accessibility.css")
    accessibility_script = read(STATIC_ROOT / "js/accessibility.js")

    assert 'class="skip-link" href="#main-content"' in content
    assert 'id="sr-live-region"' in content
    assert 'aria-live="polite"' in content
    assert '<main class="container mt-4" id="main-content" tabindex="-1">' in content
    assert "[tabindex]:focus:not(.offcanvas):not(.modal)" in accessibility_styles
    assert "#main-content:focus,\n#main-content:focus-visible" in accessibility_styles
    assert "#main-content.skip-link-focus-visible:focus" in accessibility_styles
    assert "setupSkipLinkFocusTarget()" in accessibility_script
    assert "skip-link-focus-visible" in accessibility_script


def test_runtime_compatibility_mode_banner_is_removed_from_app_shell():
    base = read(TEMPLATE_ROOT / "base.html")
    fallback_base = read(TEMPLATE_ROOT / "fallback/base_fallback.html")
    fallback_styles = read(STATIC_ROOT / "css/progressive-enhancement.css")

    assert not (STATIC_ROOT / "progressive-enhancement.js").exists()
    assert "progressive-enhancement.js" not in base
    assert "progressive-enhancement.js" not in fallback_base
    assert "css/progressive-enhancement.css" not in base
    assert "css/progressive-enhancement.css" in fallback_base
    assert "Enhanced features temporarily unavailable" not in base
    assert "fallback-message" not in fallback_styles


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


def test_gift_plan_set_date_uses_detached_picker_and_quick_action_refresh_contract():
    template = read(TEMPLATE_ROOT / "includes/gift_plan_card.html")
    script = read(STATIC_ROOT / "js/gift-plan-quick-actions.js")
    main_styles = read(STATIC_ROOT / "main.css")
    styles = read(STATIC_ROOT / "css/gift-plan-workspace.css")

    assert "data-gift-plan-date-picker-button" in template
    assert "data-gift-plan-planning-button" in template
    assert "data-gift-plan-event-options" in template
    assert "card.has_missing_event" in template
    assert "gift-plan-missing-data-badge" in template
    assert 'type="date"' not in template
    assert "gift-plan-date-action-input" not in template
    assert "gift-plan-quick-actions.js" in read(TEMPLATE_ROOT / "home.html")
    relation_list = read(TEMPLATE_ROOT / "relation_list.html")
    assert "gift-plan-quick-actions.js" in relation_list
    assert "window.htmx.process(nextWorkspace)" in relation_list
    assert relation_list.index("window.htmx.process(nextWorkspace)") < relation_list.index(
        "gift-plan-workspace:refreshed"
    )

    assert 'activeInput.type = "text"' in script
    assert "appendTo: document.body" in script
    assert "positionElement: button" in script
    assert "disableMobile: true" in script
    assert 'formData.set("action"' in script
    assert 'formData.set("due_date"' in script
    assert '"HX-Request": "true"' in script
    assert '"X-CSRFToken": getCsrfToken(form)' in script
    assert "dispatchHxTriggerEvents(response)" in script
    assert script.index("closePicker();\n                dispatchHxTriggerEvents(response)") > -1
    assert "rememberScrollPosition()" in script
    assert "finishPendingScrollRestore()" in script
    assert 'document.addEventListener("list:update", closeQuickActionControls)' in script
    assert 'document.body.addEventListener("htmx:afterSwap"' in script
    assert "createPlanningPanel" in script
    assert "gift-plan-plan-popover" in script
    assert 'formData.set("action", (actionInput && actionInput.value) || "plan")' in script
    assert 'formData.set("event"' in script
    assert "[data-gift-plan-planning-button]" in script
    assert "showPicker" not in script

    assert ".gift-plan-date-picker-source" in styles
    assert "position: fixed;" in styles
    assert ".gift-plan-quick-date-picker" in styles
    assert ".gift-plan-plan-popover" in styles
    assert ".gift-plan-missing-data-badge" in styles
    assert ".gift-plan-status--given" in main_styles
    assert ".gift-plan-due-badge--completed" in main_styles
    assert ".gift-plan-due-badge--due_soon" in main_styles
    assert ".gift-plan-due-badge--overdue" in main_styles
    assert ".gift-plan-card--needs_details .gift-plan-due-badge--no_date" in styles
    assert "background-color: var(--color-success-light)" in main_styles
    assert "background-color: var(--color-warning-light)" in main_styles

    missing_badge_styles = css_block(styles, ".gift-plan-missing-data-badge")
    missing_row_marker_styles = css_block(
        styles,
        "#relation-grid .gridjs-tr.gift-plan-grid-row--missing-data td.gridjs-td:first-child",
    )
    assert "background-color: var(--color-danger-light)" in missing_badge_styles
    assert "color: var(--color-danger-hover)" in missing_badge_styles
    assert "rgba(239, 68, 68, 0.35)" in missing_badge_styles
    assert "var(--color-danger)" in missing_row_marker_styles
