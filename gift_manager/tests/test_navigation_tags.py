import pytest

from gift_manager.templatetags.navigation_tags import navigation_section


@pytest.mark.parametrize(
    ("url_name", "section"),
    [
        ("home", "home"),
        ("relations", "gift_plans"),
        ("relation_create", "gift_plans"),
        ("relation_guided_create", "gift_plans"),
        ("relation_advanced_list", "gift_plans"),
        ("recipients", "recipients"),
        ("person_create", "recipients"),
        ("person_group_detail", "recipients"),
        ("gifts", "gifts"),
        ("gift_create", "gifts"),
        ("events", "more"),
        ("gift_tag_explorer", "more"),
        ("relation_statuses", "more"),
        ("share_objects", "more"),
        ("profile_detail", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_navigation_section(url_name, section):
    assert navigation_section(url_name) == section
