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
    advanced_tools_id = f'id="{grid_id}-advanced-tools"'
    select_button_id = f'id="toggle-selection-{grid_id}"'
    filter_panel_id = f'id="{grid_id}-filter-panel"'

    assert 'class="advanced-list-tools"' in content
    assert advanced_tools_id in content
    assert select_button_id in content
    assert filter_panel_id in content
    assert content.index(advanced_tools_id) < content.index(select_button_id)
    assert content.index(advanced_tools_id) < content.index(filter_panel_id)


@pytest.mark.django_db
def test_status_filters_are_advanced_without_bulk_selection(authenticated_client):
    response = authenticated_client.get(reverse("gift_manager:relation_statuses"))

    assert response.status_code == 200
    content = response.content.decode()

    assert 'id="status-grid-advanced-tools"' in content
    assert 'id="status-grid-filter-panel"' in content
    assert 'id="toggle-selection-status-grid"' not in content
    assert "GridUtils.setupAdvancedControls('status-grid', true" in content


@pytest.mark.django_db
@pytest.mark.parametrize(("url_name", "grid_id"), BULK_LIST_PAGES)
def test_basic_page_actions_stay_before_advanced_tools(authenticated_client, url_name, grid_id):
    response = authenticated_client.get(reverse(f"gift_manager:{url_name}"))

    assert response.status_code == 200
    content = response.content.decode()

    assert content.index('data-action="create"') < content.index(f'id="{grid_id}-advanced-tools"')


def test_standard_grid_features_are_gated_by_advanced_controls():
    grid_utils = Path("gift_manager/static/gift_manager/grid-utils.js").read_text()

    assert "function setupAdvancedControls" in grid_utils
    assert "function setupRowStateMarkers" in grid_utils
    assert "var advancedControls = features.advancedControls;" in grid_utils
    assert (
        "setupAdvancedControls(gridId, advancedControls, initializeAdvancedFeatures)" in grid_utils
    )
    assert "setupRowStateMarkers(gridId, features.rowStateMarkers)" in grid_utils
    assert "missingDataClass" in grid_utils
    assert "inlineEditing && !useAdvancedControls" in grid_utils
