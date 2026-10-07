"""Browser tests for the readability of the profile friends list in light and dark mode."""

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.tests.factories import UserFactory

FRIENDS_CONTRAST_JS = """
() => {
  const parse = (value) => {
    const [r, g, b, a = 1] = value.match(/[\\d.]+/g).map(Number);
    return {r, g, b, a};
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const channel = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const luminance = ({r, g, b}) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  const pageBg = {r: 15, g: 23, b: 42, a: 1};
  // Blend the translucent backgrounds of an element and its ancestors, nearest first.
  const effectiveBackground = (el) => {
    const layers = [];
    for (let node = el; node; node = node.parentElement) {
      layers.push(parse(getComputedStyle(node).backgroundColor));
    }
    return layers.reduceRight((below, layer) => (layer.a > 0 ? blend(layer, below) : below), pageBg);
  };
  const section = [...document.querySelectorAll('.profile-section')]
    .find((el) => el.textContent.includes('My Friends'));
  return [...section.querySelectorAll('.friends-list .list-group-item *')]
    .filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() !== ''))
    .map((el) => {
      const [hi, lo] = [
        luminance(parse(getComputedStyle(el).color)),
        luminance(effectiveBackground(el)),
      ].sort((a, b) => b - a);
      return {text: el.textContent.trim(), contrast: (hi + 0.05) / (lo + 0.05)};
    });
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.frontend
@pytest.mark.e2e
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_friends_list_is_readable(page: Page, live_server, seed_data_e2e, theme):
    friend = UserFactory(username="bob-friend")
    seed_data_e2e.alice.profile.friends.add(friend.profile)

    page.goto(f"{live_server.url}/accounts/login/", wait_until="domcontentloaded")
    page.fill('input[name="login"]', "alice")
    page.fill('input[name="password"]', "alice_password")
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/accounts/login/" not in url, timeout=30_000)
    page.goto(
        f"{live_server.url}{reverse('gift_manager:profile_detail')}", wait_until="domcontentloaded"
    )
    # Buttons animate their colours; measure the settled state, not a mid-transition frame.
    page.add_style_tag(content="*, *::before, *::after { transition: none !important; }")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    expect(page.locator(".friends-list", has_text="bob-friend")).to_be_visible()

    cells = page.evaluate(FRIENDS_CONTRAST_JS)

    assert cells, "the friends list has no text"
    unreadable = [cell for cell in cells if cell["contrast"] < 4.5]
    assert unreadable == [], unreadable
