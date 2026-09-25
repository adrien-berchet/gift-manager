"""Mobile layout checks for the reaction prompt."""

from itertools import pairwise

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.e2e.test_relation_reaction import make_plan
from gift_manager.tests.e2e.test_relation_reaction import open_page


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("viewport_width", [390, 1280], ids=["phone", "desktop"])
def test_reaction_prompt_layout(page: Page, live_server, seed_data_e2e, viewport_width):
    """Stars stay evenly spaced and the prompt never scrolls horizontally."""
    page.set_viewport_size({"width": viewport_width, "height": 800})
    make_plan(seed_data_e2e, gift_name="Layout Gift", status="planned", due_in_days=1)
    open_page(page, live_server, "/")

    page.locator(
        ".dashboard-action-group--upcoming .gift-plan-card", has_text="Layout Gift"
    ).locator("[data-action='quick-given']").click()
    panel = page.locator("#editPanel")
    expect(panel).to_be_visible()
    page.wait_for_timeout(600)
    page.locator("#editPanel label[for$='reaction_rating_3']").click()

    lefts = page.locator("#editPanel .rating-input-star").evaluate_all(
        "stars => stars.map((star) => star.getBoundingClientRect().left)"
    )
    gaps = [round(right - left) for left, right in pairwise(lefts)]
    assert len(gaps) == 4
    assert max(gaps) - min(gaps) <= 1
    assert panel.evaluate("el => el.scrollWidth <= el.clientWidth")


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_rated_and_unrated_stars_stay_distinguishable(
    page: Page, live_server, seed_data_e2e, theme
):
    """Filled stars keep the accent colour in both themes; unrated stars stay outlined."""
    rated = make_plan(seed_data_e2e, gift_name="Rated Colour", status="given")
    rated.reaction_rating = 5
    rated.save()
    make_plan(seed_data_e2e, gift_name="Unrated Colour", status="given")
    open_page(page, live_server, "/relations/")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")

    filled = page.locator(".gift-plan-card", has_text="Rated Colour").locator(
        ".rating-stars-filled"
    )
    expect(filled).to_have_count(5)
    expect(filled.first).to_have_css("color", "rgb(245, 158, 11)")
    unrated = page.locator(".gift-plan-card", has_text="Unrated Colour").locator(
        ".rating-input-star i"
    )
    expect(unrated).to_have_count(5)
    expect(unrated.first).to_have_class("far fa-star")
    expect(unrated.first).not_to_have_css("color", "rgb(245, 158, 11)")
