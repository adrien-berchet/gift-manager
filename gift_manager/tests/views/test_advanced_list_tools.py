from pathlib import Path

import pytest
from django.urls import reverse

BULK_LIST_PAGES = (
    ("gifts", "gift-grid"),
    ("persons", "person-grid"),
    ("events", "event-grid"),
    ("person_groups", "person-group-grid"),
    ("relation_advanced_list", "relation-grid"),
)


@pytest.mark.django_db
@pytest.mark.parametrize(("url_name", "grid_id"), BULK_LIST_PAGES)
def test_advanced_list_tools_wrap_filters_and_selection(authenticated_client, url_name, grid_id):
    response = authenticated_client.get(reverse(f"gift_manager:{url_name}"))

    assert response.status_code == 200
    content = response.content.decode()
    list_tools_id = f'id="{grid_id}-list-tools"'
    search_input_id = f'id="{grid_id}-search"'
    advanced_tools_id = f'id="{grid_id}-advanced-tools"'
    select_button_id = f'id="toggle-selection-{grid_id}"'
    filter_panel_id = f'id="{grid_id}-filter-panel"'
    filter_content_id = f'id="{grid_id}-filter-content"'

    assert 'class="list-tools-shell"' in content
    assert list_tools_id in content
    assert search_input_id in content
    assert 'class="advanced-list-tools"' in content
    assert advanced_tools_id in content
    assert select_button_id in content
    assert filter_panel_id in content
    assert filter_content_id in content
    assert 'class="advanced-list-actions"' not in content
    assert content.index(list_tools_id) < content.index(search_input_id)
    assert content.index(search_input_id) < content.index(advanced_tools_id)
    assert content.index(advanced_tools_id) < content.index(filter_panel_id)
    assert content.index(filter_panel_id) < content.index(filter_content_id)
    assert content.index(filter_content_id) < content.index(select_button_id)


@pytest.mark.django_db
def test_status_list_omits_advanced_controls(authenticated_client):
    response = authenticated_client.get(reverse("gift_manager:relation_statuses"))

    assert response.status_code == 200
    content = response.content.decode()

    assert 'id="status-grid"' in content
    assert "GridUtils.initGrid('status-grid'" in content
    assert 'id="status-grid-search"' not in content
    assert 'id="status-grid-advanced-tools"' not in content
    assert 'id="status-grid-filter-panel"' not in content
    assert 'id="toggle-selection-status-grid"' not in content
    assert "FilterPanel.init('status-grid'" not in content
    assert "RealTimeSearch.init('status-grid'" not in content
    assert "DynamicFilters.init('status-grid'" not in content
    assert "GridUtils.setupAdvancedControls('status-grid'" not in content


@pytest.mark.django_db
@pytest.mark.parametrize(("url_name", "grid_id"), BULK_LIST_PAGES)
def test_basic_page_actions_stay_before_advanced_tools(authenticated_client, url_name, grid_id):
    response = authenticated_client.get(reverse(f"gift_manager:{url_name}"))

    assert response.status_code == 200
    content = response.content.decode()

    assert content.index('data-action="create"') < content.index(f'id="{grid_id}-advanced-tools"')


def test_standard_grid_heavy_features_are_gated_by_advanced_controls():
    grid_utils = Path("gift_manager/static/gift_manager/grid-utils.js").read_text()

    assert "function setupAdvancedControls" in grid_utils
    assert "function setupRowStateMarkers" in grid_utils
    assert "var advancedControls = features.advancedControls;" in grid_utils
    assert (
        "setupAdvancedControls(gridId, advancedControls, initializeAdvancedFeatures)" in grid_utils
    )
    assert "setupRowStateMarkers(gridId, features.rowStateMarkers)" in grid_utils
    assert "missingDataClass" in grid_utils
    assert "inlineEditing && !useAdvancedControls" not in grid_utils
    assert "if (inlineEditing) {" in grid_utils
    assert "setupInlineEditingFallback(gridId, inlineEntityType" in grid_utils
