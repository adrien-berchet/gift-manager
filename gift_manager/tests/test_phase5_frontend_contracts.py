"""Static frontend contract tests for Phase 5 UX fixes."""

from pathlib import Path

from django.template.loader import render_to_string
from django.utils.translation import override

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


def test_unsaved_changes_use_central_panel_safe_flow():
    unsaved_changes = read(STATIC_ROOT / "unsaved-changes.js")
    form_initializer = read(STATIC_ROOT / "form-initializer.js")
    offcanvas = read(TEMPLATE_ROOT / "includes/offcanvas_base.html")
    translations = read(TEMPLATE_ROOT / "includes/unsaved_changes_translations.html")
    styles = read(STATIC_ROOT / "css/unsaved-changes.css")

    assert "window.unsavedChangesTranslations" in translations
    assert "{% trans " in translations
    assert 'include "gift_manager/includes/unsaved_changes_translations.html"' in offcanvas
    assert offcanvas.index("unsaved_changes_translations.html") < offcanvas.index(
        "unsaved-changes.js"
    )
    assert "window.unsavedChangesTranslations || {}" in unsaved_changes
    assert "...translatedMessages" in unsaved_changes
    assert "function escapeHtml" in unsaved_changes
    assert "escapeHtml(CONFIG.messages.modalTitle)" in unsaved_changes
    assert "escapeHtml(CONFIG.messages.statusText)" in unsaved_changes
    assert "requestSubmit" in unsaved_changes
    assert ".submit()" not in unsaved_changes
    assert "confirm(" not in unsaved_changes
    assert "confirm(" not in form_initializer
    assert "hide.bs.offcanvas" in unsaved_changes
    assert "htmx:afterRequest" in unsaved_changes
    assert "event.detail?.successful" in unsaved_changes
    assert "clearForm(form);" in unsaved_changes
    assert "confirmPanelReplacement" in unsaved_changes
    assert "pendingBaselines" in unsaved_changes
    assert "checkForChanges(form);" in unsaved_changes
    assert "event.button !== 0" in unsaved_changes
    assert "permission-select" in unsaved_changes
    assert "confirmPanelReplacement(target" in read(TEMPLATE_ROOT / "base.html")
    assert 'new Event("change", { bubbles: true })' in form_initializer

    assert "unsaved-changes-badge" in styles
    assert "unsaved-changes-status" in styles
    assert "field-group-unsaved" in styles
    assert "save-indicator" not in styles
    assert "unsaved-actions" not in styles
    assert "pulse" not in styles


def test_unsaved_changes_translations_render_for_french_locale():
    with override("fr"):
        rendered = render_to_string("gift_manager/includes/unsaved_changes_translations.html")

    assert "window.unsavedChangesTranslations" in rendered
    assert "Modifications non sauvegardées" in rendered
    assert "Abandonner les modifications" in rendered
    assert "Continuer la modification" in rendered
    assert "Ce champ a été modifié" in rendered
    assert "Keep editing" not in rendered
    assert "Discard changes" not in rendered


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


def test_bulk_relation_status_updates_are_scoped_and_refresh_lists():
    relation_list = read(TEMPLATE_ROOT / "relation_list.html")
    bulk_operations = read(STATIC_ROOT / "bulk-operations.js")
    bulk_styles = read(STATIC_ROOT / "bulk-operations.css")

    assert "enableBulkStatus: true" in relation_list
    assert "statusOptions: relationStatusOptions" in relation_list
    assert "bulkStatusLabels" in relation_list

    assert "bulk_update_status" in bulk_operations
    assert 'this.state.currentEntityType !== "relation"' in bulk_operations
    assert "handleBulkUpdateStatus(selectedIds)" in bulk_operations
    assert "this.triggerListUpdate();" in bulk_operations
    assert "result.permission_denied" in bulk_operations
    assert "result.failed" in bulk_operations

    assert ".bulk-status-action" in bulk_styles
    assert ".bulk-status-select" in bulk_styles


def test_comment_columns_wrap_in_list_views():
    grid_utils = read(STATIC_ROOT / "grid-utils.js")
    theme_styles = read(STATIC_ROOT / "theme.css")
    fallback_template = read(TEMPLATE_ROOT / "fallback/list_fallback.html")
    fallback_styles = read(STATIC_ROOT / "css/fallback-mode.css")
    comment_templates = [
        TEMPLATE_ROOT / "gift_list.html",
        TEMPLATE_ROOT / "event_list.html",
        TEMPLATE_ROOT / "relation_list.html",
        TEMPLATE_ROOT / "gift_tag_detail.html",
        TEMPLATE_ROOT / "relation_status_detail.html",
        TEMPLATE_ROOT / "person_group_detail.html",
    ]

    assert "function applyColumnDataAttributes" in grid_utils
    assert "cell.setAttribute('data-column-id', column.id)" in grid_utils
    assert "applyColumnDataAttributes(container, columns)" in grid_utils

    for template in comment_templates:
        assert "id: 'comment'" in read(template)

    assert '.gridjs-td[data-column-id="comment"]' in theme_styles
    assert "white-space: normal;" in theme_styles
    assert "overflow-wrap: anywhere;" in theme_styles
    assert "max-width: clamp(12rem, 28vw, 26rem);" in theme_styles

    assert 'data-column-field="{{ column.field }}"' in fallback_template
    assert '.fallback-table td[data-column-field="comment"]' in fallback_styles
    assert "overflow-wrap: anywhere;" in fallback_styles


def test_group_detail_tables_reserve_action_columns_and_refresh_contextual_creates():
    content = read(TEMPLATE_ROOT / "person_group_detail.html")

    assert "href=\"{% url 'gift_manager:person_create' %}?group={{ group.group_id }}\"" in content
    assert 'data-action="create"' in content
    assert "data-group-detail-create" in content
    assert "document.addEventListener('list:update'" in content
    assert "window.location.reload();" in content

    assert "@media (min-width: 577px) and (max-width: 1200px)" in content
    assert "#main-content" in content
    assert "max-width: none" in content
    assert "clamp(var(--space-3, 0.75rem), 2vw, var(--space-6, 1.5rem))" in content

    assert content.count("id: 'actions'") == 4
    assert "width: 'var(--group-detail-actions-width, 1%)'" not in content
    assert "table-layout: auto" not in content
    assert "--group-detail-actions-width" in content
    assert "table-layout: fixed" in content
    assert "applyGroupDetailColumnWidths" in content
    assert "document.createElement('colgroup')" in content
    assert "document.createElement('col')" in content
    assert "header.style.removeProperty('width')" in content
    assert "column.style.width = `${actionWidth}px`" in content
    assert "const adaptiveColumnWidth" in content
    assert "column.style.width = adaptiveColumnWidth" in content
    assert "const minimumAdaptiveColumnWidth = 6 * rootFontSize" in content
    assert "--group-detail-min-column-width" in content
    assert "--group-detail-min-table-width" in content
    assert "min-width: max(" in content
    assert "measureGroupDetailActionsWidth" in content
    assert "MutationObserver" in content
    assert "shown.bs.tab" in content
    assert "grid:refreshed" in content
    assert "document.fonts.ready" in content
    assert "max-width: 2.5rem" in content
    assert "max-height: 2.5rem" in content
    assert "padding: 0" in content
    assert "font-size: var(--text-sm)" in content
    assert "@media (max-width: 991.98px)" in content
    assert "@media (max-width: 767.98px)" in content
    assert "@media (max-width: 576px)" in content
    assert "#shares-grid .gridjs-td[data-label]::before" in content
    assert "#groupTabContent .gridjs-td[data-label]::before" in content
    assert "display: none" in content
    assert "content: none" in content
    assert "var(--group-detail-actions-width, 14rem)" in content
    assert "position: sticky" not in content
    assert "padding-right: var(--space-1, 0.25rem)" in content
    assert "padding-left: var(--space-1, 0.25rem)" in content
    assert "margin-right: auto" in content
    assert "margin-left: auto" in content
    assert "opacity: 1" in content
    assert "width: '18%'" not in content
    assert "width: '17%'" not in content
    assert "width: '150px'" not in content
    assert "width: '180px'" not in content


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
    main_styles = read(STATIC_ROOT / "main.css")

    assert 'aria-expanded="false"' in template
    assert 'aria-controls="{{ grid_id }}-filter-content"' in template
    assert 'id="toggle-selection-{{ grid_id }}"' in template
    assert "filter-selection-section" in template
    assert 'for="{{ grid_id }}-search"' in visible_search_template
    assert 'id="{{ grid_id }}-search"' in visible_search_template
    assert 'aria-pressed="false"' in template
    assert 'aria-pressed="true"' in template

    assert "syncFilterExpanded" in script
    assert "const isInAdvancedTools" in script
    assert "syncFilterExpanded(isInAdvancedTools)" in script
    assert "const controlRoot = listTools || filterPanel || filterContent;" in script
    assert "filterToggle.setAttribute('aria-expanded'" in script
    assert "multiSortToggle.setAttribute('aria-pressed'" in script
    assert "btn.setAttribute('aria-pressed'" in script
    assert "searchableIndices: getSearchableColumnIndices(columns)" in dynamic_filters
    assert "function matchesSearchTerm" in dynamic_filters
    assert "applyFilters(grid, originalData, filterState);" in dynamic_filters
    assert ".advanced-list-tools .filter-toggle-btn" in main_styles
    assert ".advanced-list-tools .filter-content.expanded" in main_styles
    assert ".advanced-list-tools .filter-selection-section" in main_styles
    assert "grid-template-columns: auto auto minmax(120px, 1fr);" in main_styles


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


def test_root_scrollbar_gutter_prevents_main_content_shift():
    theme_styles = read(STATIC_ROOT / "theme.css")
    html_styles = css_block(theme_styles, "html")

    assert "scrollbar-gutter: stable;" in html_styles
    assert "@supports not (scrollbar-gutter: stable)" in theme_styles
    assert "overflow-y: scroll;" in theme_styles


def test_runtime_compatibility_mode_banner_is_removed_from_app_shell():
    base = read(TEMPLATE_ROOT / "base.html")
    fallback_base = read(TEMPLATE_ROOT / "fallback/base_fallback.html")
    fallback_styles = read(STATIC_ROOT / "css/fallback-mode.css")

    assert not (STATIC_ROOT / "progressive-enhancement.js").exists()
    assert not (STATIC_ROOT / "css/progressive-enhancement.css").exists()
    assert "progressive-enhancement.js" not in base
    assert "progressive-enhancement.js" not in fallback_base
    assert "css/progressive-enhancement.css" not in base
    assert "css/progressive-enhancement.css" not in fallback_base
    assert "css/fallback-mode.css" not in base
    assert "css/fallback-mode.css" in fallback_base
    assert "Enhanced features temporarily unavailable" not in base
    assert "fallback-message" not in fallback_styles
    assert "ajax-disabled" not in fallback_styles
    assert "css3-disabled" not in fallback_styles
    assert "loading-states-disabled" not in fallback_styles


def test_group_tree_has_keyboard_and_touch_move_workflow():
    content = read(TEMPLATE_ROOT / "includes/person_group_management_grid.html") + read(
        TEMPLATE_ROOT / "includes/person_group_management_grid_script.html"
    )

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
    assert "activePickerScrollPosition" in script
    assert "rememberScrollPosition(activePickerScrollPosition)" in script
    assert "rememberScrollPosition()" in script
    assert "finishPendingScrollRestore()" in script
    assert 'behavior: "instant"' in script
    restore_start = script.index("function restorePendingScrollPosition()")
    restore_end = script.index("function finishPendingScrollRestore()", restore_start)
    restore_body = script[restore_start:restore_end]
    assert restore_body.index("scrollToPosition(scrollPosition)") < restore_body.index(
        "window.requestAnimationFrame"
    )
    submit_start = script.index("function submitDate(")
    submit_end = script.index("function buildPlanningRequestBody(", submit_start)
    submit_body = script[submit_start:submit_end]
    assert (
        submit_body.index("rememberScrollPosition(activePickerScrollPosition)")
        < (submit_body.index("restorePendingScrollPosition()"))
        < submit_body.index("fetch(url")
    )
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
    assert ".gift-plan-card-actions .btn-primary" in styles
    assert ".gift-plan-card-actions .btn-outline-primary" in styles
    assert ".gift-plan-card-actions .btn-success" in styles
    assert ".gift-plan-card-actions .btn-outline-secondary" in styles
    assert (
        ".gift-plan-quick-action-form,\n.gift-plan-date-action-form,\n.gift-plan-planning-action-form"
        in styles
    )
    assert "background-color: var(--color-success-light)" in main_styles
    assert "background-color: var(--color-warning-light)" in main_styles

    action_palette_styles = css_block(styles, ".gift-plan-card-actions")
    dark_action_palette_styles = css_block(styles, '[data-theme="dark"] .gift-plan-card-actions')
    action_button_styles = css_block(styles, ".gift-plan-card-actions .btn")
    primary_button_styles = css_block(styles, ".gift-plan-card-actions .btn-primary")
    primary_soft_button_styles = css_block(styles, ".gift-plan-card-actions .btn-outline-primary")
    secondary_button_styles = css_block(styles, ".gift-plan-card-actions .btn-outline-secondary")
    missing_badge_styles = css_block(styles, ".gift-plan-missing-data-badge")
    missing_row_marker_styles = css_block(
        styles,
        "#relation-grid .gridjs-tr.gift-plan-grid-row--missing-data td.gridjs-td:first-child",
    )
    assert "--gift-plan-action-primary-bg: #4338ca" in action_palette_styles
    assert "--gift-plan-action-primary-soft-bg: #eef2ff" in action_palette_styles
    assert "--gift-plan-action-success-bg: #047857" in action_palette_styles
    assert "--gift-plan-action-secondary-bg: #e2e8f0" in action_palette_styles
    assert "--gift-plan-action-disabled-bg: #f8fafc" in action_palette_styles
    assert "--gift-plan-action-primary-bg: #4f46e5" in dark_action_palette_styles
    assert "--gift-plan-action-primary-soft-bg: #312e81" in dark_action_palette_styles
    assert "--gift-plan-action-secondary-bg: #334155" in dark_action_palette_styles
    assert "--gift-plan-action-disabled-bg: #0f172a" in dark_action_palette_styles
    assert "display: inline-flex" in action_button_styles
    assert "min-height: 1.75rem" in action_button_styles
    assert "border-width: 1px" in action_button_styles
    assert "font-weight: 700" in action_button_styles
    assert "white-space: nowrap" in action_button_styles
    assert "background-color: var(--gift-plan-action-primary-bg)" in primary_button_styles
    assert "background-color: var(--gift-plan-action-primary-soft-bg)" in primary_soft_button_styles
    assert "color: var(--gift-plan-action-primary-soft-text)" in primary_soft_button_styles
    assert "background-color: var(--gift-plan-action-secondary-bg)" in secondary_button_styles
    assert "color: var(--gift-plan-action-secondary-text)" in secondary_button_styles
    assert "background-color: var(--color-danger-light)" in missing_badge_styles
    assert "color: var(--color-danger-hover)" in missing_badge_styles
    assert "rgba(239, 68, 68, 0.35)" in missing_badge_styles
    assert "var(--color-danger)" in missing_row_marker_styles
