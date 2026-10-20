"""Card view polish of the gifts, events, and gift plan lists: field icons and action bar."""

import re
from datetime import date
from datetime import timedelta

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GiftTagFactory
from gift_manager.tests.factories import RelationFactory
from gift_manager.tests.factories import UserFactory

pytestmark = [pytest.mark.frontend, pytest.mark.django_db(transaction=True)]

PAGES = [
    ("gifts", "gift-grid"),
    ("events", "event-grid"),
    ("relations/advanced", "relation-grid"),
]

# Gecko (e.g. Firefox 144 in CI) keeps attr() unresolved in computed ::before content;
# resolve it against the element so all browsers produce consistent string content.
PSEUDO_CONTENT_JS = """(el, pseudo) => getComputedStyle(el, pseudo).content
    .replace(/attr\\(\\s*([\\w-]+)\\s*\\)/g,
             (_, name) => JSON.stringify(el.getAttribute(name) ?? ''))"""

# Fields of each card: icon key, role and the label drawn in ::before
CARD_FIELDS_JS = f"""card => [...card.querySelectorAll('.gridjs-td[data-label]')]
    .filter(td => !td.querySelector('.grid-action-bar'))
    .filter(td => getComputedStyle(td).display !== 'none')
    .map(td => ({{
        label: td.dataset.label,
        role: td.dataset.cardRole || '',
        icon: td.dataset.cardIcon || '',
        before: ({PSEUDO_CONTENT_JS})(td, '::before'),
        top: td.getBoundingClientRect().top,
    }}))"""

STYLE_JS = """el => {
    const s = getComputedStyle(el);
    return {
        backgroundColor: s.backgroundColor,
        borderColor: s.borderTopColor,
        color: s.color,
        borderRadius: s.borderTopLeftRadius,
        height: el.getBoundingClientRect().height,
    };
}"""


@pytest.fixture
def logged_in_page(page: Page, client, live_server, seed_data_e2e, settings):
    client.force_login(seed_data_e2e.alice)
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    return page


def _own(user, *objects):
    for obj in objects:
        create_or_update_permission(user, obj, permission_level=PermissionLevel.OWNER)


def _wait_for_grid(page: Page, grid: str):
    """Wait until the grid rows are rendered and no page size update re-renders them."""
    page.wait_for_selector(f'#{grid}:not([aria-busy="true"]) .gridjs-tbody .gridjs-tr')


def _set_view(page: Page, grid: str, view: str):
    """Switch the view mode; the page size update it triggers re-renders the rows."""
    _wait_for_grid(page, grid)
    page.evaluate(f"window.FilterPanel.setView('{grid}', '{view}')")
    _wait_for_grid(page, grid)


def _open_list(page: Page, live_server, path: str, grid: str, view: str, language: str = "en"):
    page.goto(f"{live_server.url}/{language}/{path}/")
    _set_view(page, grid, view)
    if view == "card":
        page.wait_for_selector(f'#{grid}[data-view="card"] .gridjs-td[data-label]')
    page.evaluate("document.fonts.ready")
    return page.locator(f"#{grid} .gridjs-tbody .gridjs-tr")


def _has_icon_glyph(content: str) -> bool:
    return any("" <= character <= "" for character in content)


@pytest.mark.parametrize(("path", "grid"), PAGES)
def test_every_card_field_and_title_has_an_icon(logged_in_page: Page, live_server, path, grid):
    page = logged_in_page
    cards = _open_list(page, live_server, path, grid, "card")
    assert cards.count() >= 1

    for fields in cards.evaluate_all(f"cards => cards.map({CARD_FIELDS_JS})"):
        title = [field for field in fields if field["role"] == "title"]
        assert len(title) == 1, fields
        # The title leads the card, whatever the column order
        assert title[0]["top"] == min(field["top"] for field in fields)
        for field in fields:
            assert field["icon"], f"{field['label']} has no icon"
            assert _has_icon_glyph(field["before"]), field
            if field["role"] != "title":
                assert field["label"] in field["before"], field

    # The glyphs come from the icon font, the label text from the page font
    assert page.evaluate("document.fonts.check('12px \"Grid Card Icons\"', '\\uf075')")
    assert page.evaluate(
        "[...document.fonts].some(f => f.family.includes('Grid Card Icons') && f.status === 'loaded')"
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("view", ["card", "list"])
def test_action_bar_matches_the_dashboard_card(
    logged_in_page: Page, live_server, seed_data_e2e, theme, view
):
    """Details, duplicate, and edit use the dashboard card buttons in both views."""
    page = logged_in_page
    relation = RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name="Parity plan gift"),
        event=None,
        status=seed_data_e2e.statuses["planned"],
    )
    _own(seed_data_e2e.alice, relation, relation.gift)

    page.goto(f"{live_server.url}/", wait_until="networkidle")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    dashboard_details = page.locator('.gift-plan-card-utility-action[data-action="detail"]').first
    expect(dashboard_details).to_be_visible()
    page.wait_for_timeout(300)  # theme transition
    dashboard_style = dashboard_details.evaluate(STYLE_JS)

    rows = _open_list(page, live_server, "relations/advanced", "relation-grid", view)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.wait_for_timeout(300)
    bar = rows.filter(has_text="Parity plan gift").locator(".grid-action-bar")
    details = bar.locator('[data-action="detail"]')
    duplicate = bar.locator('[data-action-type="duplicate"]')
    edit = bar.locator('[data-action="edit"]')
    toggle = bar.locator(".grid-action-menu-toggle")
    for button in (details, duplicate, edit, toggle):
        expect(button).to_be_visible()
    expect(details.locator("i")).to_have_class("fas fa-eye")
    expect(duplicate.locator("i")).to_have_class("fas fa-copy")
    expect(edit.locator("i")).to_have_class("fas fa-pen")
    expect(toggle.locator("i")).to_have_class("fas fa-ellipsis")
    assert bar.locator(".btn-primary").count() == 1
    assert "btn-primary" in (edit.get_attribute("class") or "")

    for utility in (details, duplicate, toggle):
        style = utility.evaluate(STYLE_JS)
        for key in ("backgroundColor", "borderColor", "color", "borderRadius", "height"):
            assert style[key] == dashboard_style[key], (key, style, dashboard_style)
    expected_primary = "rgb(67, 56, 202)" if theme == "light" else "rgb(79, 70, 229)"
    assert edit.evaluate("el => getComputedStyle(el).backgroundColor") == expected_primary
    assert edit.evaluate("el => getComputedStyle(el).opacity") == "1"
    # Edit keeps its label in cards and on wide screens
    expect(edit.locator(".btn-text")).to_be_visible()

    # Share and Delete wait in the overflow menu
    expect(bar.locator('[data-action="delete"]')).to_be_hidden()
    expect(bar.locator('[data-action="share"]')).to_be_hidden()


@pytest.mark.parametrize("position", ["first", "last"])
@pytest.mark.parametrize("view", ["card", "list"])
def test_overflow_menu_is_keyboard_operable_and_not_clipped(
    logged_in_page: Page, live_server, view, position
):
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", view)
    # The first row's menu overlaps the following rows; the last row's menu is the most exposed
    # to the clipping of the grid wrapper and of the card
    row = rows.first if position == "first" else rows.last
    toggle = row.locator(".grid-action-menu-toggle")
    menu = row.locator(".grid-action-menu-list")
    toggle.scroll_into_view_if_needed()

    toggle.focus()
    page.keyboard.press("Enter")
    expect(menu).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("ArrowDown")
    share = menu.locator('[data-action="share"]')
    delete = menu.locator('[data-action="delete"]')
    expect(share).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(delete).to_be_focused()

    for item in (share, delete):
        assert item.evaluate(
            """el => {
                const r = el.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                return r.width > 0 && el.contains(hit);
            }"""
        ), "menu item is clipped or covered"

    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    expect(toggle).to_be_focused()


def test_card_menu_stays_next_to_its_toggle(logged_in_page: Page, live_server):
    """Opening the menu of a hovered (lifted) card must not leave the menu anchored to the card.

    The lift is a transitioned transform: while it animated back to none, the fixed menu was
    positioned against the card, then jumped across the page once the transform was gone.
    """
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    row = rows.first
    toggle = row.locator(".grid-action-menu-toggle")
    menu = row.locator(".grid-action-menu-list")
    toggle.hover()
    page.wait_for_timeout(400)

    toggle.click()
    expect(menu).to_be_visible()
    row_transform_when_shown = row.evaluate("row => getComputedStyle(row).transform")
    offsets = []
    for _ in range(6):
        offsets.append(
            menu.evaluate(
                """menu => {
                    const m = menu.getBoundingClientRect();
                    const t = menu.parentElement
                        .querySelector('.grid-action-menu-toggle')
                        .getBoundingClientRect();
                    return [Math.round(m.right - t.right), Math.round(m.top - t.bottom)];
                }"""
            )
        )
        page.wait_for_timeout(100)

    assert row_transform_when_shown == "none"
    assert all(offset == offsets[0] for offset in offsets), offsets
    right_gap, top_gap = offsets[0]
    assert abs(right_gap) <= 24, offsets
    assert 0 <= top_gap <= 8, offsets


def test_delete_from_the_menu_uses_the_confirmation_flow(logged_in_page: Page, live_server):
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    row = rows.filter(has_text="Scarf")
    toggle = row.locator(".grid-action-menu-toggle")
    toggle.click()
    row.locator('.grid-action-menu-list [data-action="delete"]').click()

    modal = page.locator("#confirmModal")
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("Scarf")
    modal.locator('[data-bs-dismiss="modal"]').first.click()
    expect(modal).to_be_hidden()
    # Focus goes back to the menu toggle, as the menu item is hidden again
    expect(toggle).to_be_focused()
    expect(rows.filter(has_text="Scarf")).to_have_count(1)


def test_viewer_sees_a_lock_and_no_overflow_actions(
    logged_in_page: Page, live_server, seed_data_e2e
):
    gift = GiftFactory(name="Viewer only gift")
    create_or_update_permission(seed_data_e2e.alice, gift, permission_level=PermissionLevel.VIEWER)
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    bar = rows.filter(has_text="Viewer only gift").locator(".grid-action-bar")

    locked = bar.locator(".grid-action--locked")
    expect(locked).to_be_visible()
    expect(locked).to_be_disabled()
    expect(locked.locator("i")).to_have_class("fas fa-lock")
    expect(locked).to_have_attribute("aria-label", "Edit")
    expect(locked).to_have_attribute("title", "You do not have permission to edit this item")
    expect(bar.locator('[data-action="edit"]')).to_have_count(0)
    expect(bar.locator('[data-action="delete"]')).to_have_count(0)
    expect(bar.locator(".grid-action-menu")).to_have_count(0)
    expect(bar.locator('[data-action="detail"]')).to_be_enabled()


def test_actions_are_translated(logged_in_page: Page, live_server):
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card", language="fr")
    bar = rows.first.locator(".grid-action-bar")

    expect(bar.locator('[data-action="edit"] .btn-text')).to_have_text("Éditer")
    expect(bar.locator('[data-action="create"] .btn-text')).to_have_text("Offrir")
    expect(bar.locator('[data-action="detail"]')).to_have_attribute("aria-label", "Détails")
    expect(bar.locator(".grid-action-menu-toggle")).to_have_attribute(
        "aria-label", "Plus d'actions"
    )
    expect(bar.locator('[data-action="delete"] span')).to_have_text("Supprimer")


def test_gift_plan_due_date_and_status_read_as_dashboard_badges(
    logged_in_page: Page, live_server, seed_data_e2e
):
    relation = RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name="Late plan gift"),
        status=seed_data_e2e.statuses["planned"],
        due_date=date.today() - timedelta(days=3),
    )
    _own(seed_data_e2e.alice, relation, relation.gift, relation.event)
    page = logged_in_page

    rows = _open_list(page, live_server, "relations/advanced", "relation-grid", "card")
    card = rows.filter(has_text="Late plan gift")
    due = card.locator(".grid-due-date")
    assert "gift-plan-due-badge--overdue" in (due.get_attribute("class") or "")
    assert due.evaluate("el => getComputedStyle(el).backgroundColor") not in (
        "rgba(0, 0, 0, 0)",
        "transparent",
    )
    # Compact like the dashboard status badge (once the view switch transition is over)
    card.locator(".gift-plan-status-select").evaluate(
        """el => new Promise(resolve => {
            const check = () => el.getBoundingClientRect().height <= 32
                ? resolve() : requestAnimationFrame(check);
            check();
        })"""
    )
    # The urgency colors the card accent, like the dashboard card
    danger = page.evaluate(
        """() => {
            const probe = document.createElement('span');
            probe.style.color = 'var(--color-danger)';
            document.body.append(probe);
            const color = getComputedStyle(probe).color;
            probe.remove();
            return color;
        }"""
    )
    assert card.evaluate("el => getComputedStyle(el).borderLeftColor") == danger
    # The type badge is replaced by the person/group icon, but stays for screen readers
    recipient = card.locator('.gridjs-td[data-card-icon="recipient"]')
    expect(recipient).to_have_count(1)
    assert (
        recipient.locator(".recipient-type-badge").evaluate(
            "el => el.getBoundingClientRect().width"
        )
        <= 1
    )

    _set_view(page, "relation-grid", "list")
    due = page.locator("#relation-grid .gridjs-tr", has_text="Late plan gift").locator(
        ".grid-due-date"
    )
    assert due.evaluate("el => getComputedStyle(el).backgroundColor") == "rgba(0, 0, 0, 0)"


def test_card_title_opens_details_and_double_click_still_edits(logged_in_page: Page, live_server):
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    # Address the row by entity, as an edited title no longer contains its text
    entity_id = rows.filter(has_text="Scarf").get_attribute("data-entity-id")
    title = page.locator(
        f'#gift-grid .gridjs-tr[data-entity-id="{entity_id}"] .gridjs-td[data-card-role="title"]'
    )
    expect(title).to_have_class(re.compile(r"\binline-editable\b"))

    title.dblclick()
    expect(title.locator("input, textarea")).to_be_visible()
    page.wait_for_timeout(400)  # past the single-click delay
    expect(page.locator("#detailPanel")).to_be_hidden()
    page.keyboard.press("Escape")
    expect(title.locator("input, textarea")).to_have_count(0)

    title.click()
    expect(page.locator("#detailPanel")).to_be_visible()
    expect(page.locator("#detailContent")).to_contain_text("Scarf")


def test_opening_advanced_tools_keeps_the_rendered_rows(logged_in_page: Page, live_server):
    """Without saved filters, activating the advanced tools must not re-render the grid.

    A needless re-render replaced the rows while the user (or a test) was already using
    them, e.g. right after entering selection mode.
    """
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    rows.first.evaluate("row => { window.__firstRow = row; }")

    page.locator("details.advanced-list-tools").first.evaluate("el => { el.open = true; }")
    page.locator("[id^='toggle-selection-']").first.click()
    expect(rows.first.locator(".bulk-select-item")).to_be_visible()
    page.wait_for_timeout(500)

    assert rows.first.evaluate("row => row === window.__firstRow && row.isConnected")


def test_opening_advanced_tools_restores_a_saved_search(
    logged_in_page: Page, live_server, seed_data_e2e
):
    """A search saved by a previous visit is still applied when the tools activate."""
    _own(seed_data_e2e.alice, GiftFactory(name="Saved search target"))
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    assert rows.count() > 1
    page.evaluate(
        """() => localStorage.setItem('filter-state-gift-grid', JSON.stringify({
            search: 'saved search target', columnFilters: [], timestamp: Date.now(),
        }))"""
    )
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")

    page.locator("details.advanced-list-tools").first.evaluate("el => { el.open = true; }")

    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Saved search target")


def test_selection_checkbox_sits_in_the_card_header(logged_in_page: Page, live_server):
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")
    page.locator("details.advanced-list-tools").first.evaluate("el => { el.open = true; }")
    page.locator("[id^='toggle-selection-']").first.click()
    checkbox = rows.first.locator(".bulk-select-item")
    expect(checkbox).to_be_visible()

    title_box = rows.first.locator('.gridjs-td[data-card-role="title"]').bounding_box()
    checkbox_box = checkbox.bounding_box()
    card_box = rows.first.bounding_box()
    assert (
        title_box["y"]
        <= checkbox_box["y"] + checkbox_box["height"] / 2
        <= (title_box["y"] + title_box["height"])
    )
    assert checkbox_box["x"] + checkbox_box["width"] <= card_box["x"] + card_box["width"]
    assert checkbox_box["x"] >= title_box["x"] + title_box["width"] / 2


def test_tags_are_compact_chips_on_one_line(logged_in_page: Page, live_server, seed_data_e2e):
    tags = [GiftTagFactory(name="Wool"), GiftTagFactory(name="Red")]
    gift = GiftFactory(name="Tagged scarf", tags=tags)
    _own(seed_data_e2e.alice, gift, *tags)
    page = logged_in_page
    rows = _open_list(page, live_server, "gifts", "gift-grid", "card")

    chips = rows.filter(has_text="Tagged scarf").locator(".grid-tag-list .badge")
    expect(chips).to_have_count(2)
    tops = chips.evaluate_all("chips => chips.map(c => Math.round(c.getBoundingClientRect().top))")
    assert len(set(tops)) == 1
    assert chips.first.evaluate("el => getComputedStyle(el).textTransform") == "none"


def test_cards_fit_phone_width(logged_in_page: Page, live_server):
    page = logged_in_page
    page.set_viewport_size({"width": 360, "height": 800})
    for path, grid in PAGES:
        rows = _open_list(page, live_server, path, grid, "card")
        expect(rows.first).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        sizes = rows.first.locator(".grid-action").evaluate_all(
            "btns => btns.map(b => Math.min(b.offsetWidth, b.offsetHeight))"
        )
        assert sizes and min(sizes) >= 44


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_field_icons_share_one_color_per_kind_across_pages(
    logged_in_page: Page, live_server, seed_data_e2e, theme
):
    """Event, recipient, and comment icons have the same color on the dashboard and in cards."""
    page = logged_in_page
    relation = RelationFactory(
        person=seed_data_e2e.persons["dad"],
        gift=GiftFactory(name="Toned plan gift"),
        status=seed_data_e2e.statuses["planned"],
    )
    _own(seed_data_e2e.alice, relation, relation.gift, relation.event)

    def tones(selector_by_kind):
        return page.evaluate(
            """selectors => Object.fromEntries(Object.entries(selectors).map(([kind, selector]) => {
                const el = document.querySelector(selector);
                const style = el && getComputedStyle(el);
                // Grid card fields expose their icon color as a custom property
                const tone = style && (style.getPropertyValue('--card-field-icon-color').trim()
                    ? (() => {
                        const probe = document.createElement('span');
                        probe.style.color = 'var(--card-field-icon-color)';
                        el.append(probe);
                        const color = getComputedStyle(probe).color;
                        probe.remove();
                        return color;
                    })()
                    : style.color);
                return [kind, tone];
            }))""",
            selector_by_kind,
        )

    page.goto(f"{live_server.url}/", wait_until="networkidle")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.wait_for_timeout(300)
    dashboard = tones(
        {
            "event": ".gift-plan-card .field-icon--event",
            "person": ".gift-plan-card .recipient-type-marker--person",
            "comment": ".gift-plan-card .field-icon--comment",
        }
    )

    _open_list(page, live_server, "relations/advanced", "relation-grid", "card")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.wait_for_timeout(300)
    cards = tones(
        {
            "event": '#relation-grid .gridjs-td[data-card-icon="event"]',
            "person": '#relation-grid .gridjs-td[data-card-icon="recipient"]',
            "comment": '#relation-grid .gridjs-td[data-card-icon="comment"]',
        }
    )

    assert dashboard == cards
    assert len(set(cards.values())) == len(cards), "each kind of information has its own color"


CARD_GRID_JS = """grid => {
    const tbody = document.querySelector(`#${grid} .gridjs-tbody`);
    return {
        columns: getComputedStyle(tbody).gridTemplateColumns.split(' ').length,
        cards: tbody.querySelectorAll('.gridjs-tr').length,
    };
}"""


@pytest.mark.parametrize("viewport", [(1600, 1000), (900, 1100), (390, 844)])
def test_card_pages_fill_complete_rows(logged_in_page: Page, live_server, seed_data_e2e, viewport):
    """The dynamic page size counts cards per row, so no page ends with a lone card."""
    page = logged_in_page
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    for index in range(60):
        _own(seed_data_e2e.alice, GiftFactory(name=f"Row fill gift {index:02d}"))

    _open_list(page, live_server, "gifts", "gift-grid", "card")
    page.wait_for_function(
        f"""() => {{
            const r = ({CARD_GRID_JS})('gift-grid');
            return r.cards % r.columns === 0;
        }}"""
    )
    layout = page.evaluate(CARD_GRID_JS, "gift-grid")
    assert layout["cards"] >= 5
    assert layout["cards"] % layout["columns"] == 0, layout

    # Going back to the table restores a row-based page size
    _set_view(page, "gift-grid", "list")
    assert page.locator("#gift-grid .gridjs-tbody .gridjs-tr").count() >= 5


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("path", "grid"), [*PAGES, ("persons", "person-grid")])
def test_last_card_keeps_the_title_rule(logged_in_page: Page, live_server, path, grid, theme):
    """The list view drops the last row's bottom border; the last card's title rule must stay."""
    page = logged_in_page
    page.emulate_media(color_scheme=theme)
    cards = _open_list(page, live_server, path, grid, "card")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert cards.count() >= 2

    rules = cards.evaluate_all(
        """cards => cards.map(card => {
            const s = getComputedStyle(card.querySelector('.gridjs-td[data-card-role="title"]'));
            return [s.borderBottomStyle, s.borderBottomWidth, s.borderBottomColor].join(' ');
        })"""
    )
    assert rules[0].startswith("solid 1px"), rules
    assert set(rules) == {rules[0]}, rules


def test_group_cards_show_the_member_count(logged_in_page: Page, live_server, seed_data_e2e):
    """Each group card of the recipients page lists how many members the group has."""
    page = logged_in_page
    page.goto(f"{live_server.url}/en/recipients/?view=groups", wait_until="networkidle")
    _set_view(page, "person-group-grid", "card")
    page.wait_for_selector('#person-group-grid[data-view="card"] .gridjs-td[data-label]')

    counts = page.locator("#person-group-grid .gridjs-tbody .gridjs-tr").evaluate_all(
        f"""cards => Object.fromEntries(cards.map(card => {{
            const members = card.querySelector('.gridjs-td[data-card-icon="members"]');
            return [
                card.querySelector('.gridjs-td[data-card-role="title"]').textContent.trim(),
                members && getComputedStyle(members).display !== 'none'
                    ? [members.textContent.trim(), ({PSEUDO_CONTENT_JS})(members, '::before')]
                    : null,
            ];
        }}))"""
    )
    expected = {
        group.name: str(group.person_set.count()) for group in seed_data_e2e.groups.values()
    }
    assert {name: value and value[0] for name, value in counts.items()} == expected
    assert all("Members" in value[1] for value in counts.values()), counts


@pytest.mark.parametrize("view", ["card", "list"])
@pytest.mark.parametrize(("path", "grid"), [*PAGES, ("persons", "person-grid")])
def test_empty_list_shows_the_no_records_message(
    page: Page, client, live_server, settings, path, grid, view
):
    """A user without any entity sees the "no records" message instead of an empty grid."""
    client.force_login(UserFactory())
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": live_server.url,
            }
        ]
    )
    page.goto(f"{live_server.url}/en/{path}/", wait_until="networkidle")
    _set_view(page, grid, view)
    page.wait_for_timeout(300)  # past the deferred empty state check

    message = page.locator(f"#{grid} .gridjs-notfound, #{grid} .grid-empty-state")
    expect(message.first).to_be_visible()
    expect(message.first).to_contain_text("No")
    # In the card view, the message is not drawn as an (empty) card
    assert page.locator(f"#{grid} .gridjs-tbody .gridjs-tr:not(:has(.gridjs-message))").count() == 0
    if view == "card":
        style = message.first.evaluate(
            "el => { const s = getComputedStyle(el.closest('.gridjs-tr') || el);"
            " return [s.borderTopStyle, s.boxShadow]; }"
        )
        assert style == ["none", "none"], style


def test_field_labels_stay_visible_in_forced_colors(logged_in_page: Page, live_server):
    """High contrast modes drop the gradient that paints the label, so it must not stay transparent."""
    page = logged_in_page
    page.emulate_media(forced_colors="active")
    cards = _open_list(page, live_server, "gifts", "gift-grid", "card")

    fills = cards.first.evaluate(
        """card => [...card.querySelectorAll('.gridjs-td[data-card-icon][data-label]')]
            .filter(td => getComputedStyle(td).display !== 'none')
            .map(td => getComputedStyle(td, '::before').webkitTextFillColor)"""
    )
    assert fills
    assert "rgba(0, 0, 0, 0)" not in fills, fills


def test_switching_to_cards_never_shows_an_incomplete_page(
    logged_in_page: Page, live_server, seed_data_e2e
):
    """The rows of the list page size are not shown as cards while the card page renders."""
    page = logged_in_page
    page.set_viewport_size({"width": 1600, "height": 1000})
    for index in range(60):
        _own(seed_data_e2e.alice, GiftFactory(name=f"Switch gift {index:02d}"))
    _open_list(page, live_server, "gifts", "gift-grid", "list")

    page.evaluate(
        """() => {
            const grid = document.getElementById('gift-grid');
            window.visibleCounts = [];
            const record = () => {
                const tbody = grid.querySelector('.gridjs-tbody');
                if (tbody && getComputedStyle(tbody).visibility === 'visible') {
                    window.visibleCounts.push(tbody.querySelectorAll('.gridjs-tr').length);
                }
            };
            new MutationObserver(record).observe(grid, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['class'],
            });
            window.FilterPanel.setView('gift-grid', 'card');
            record();
        }"""
    )
    _wait_for_grid(page, "gift-grid")
    layout = page.evaluate(CARD_GRID_JS, "gift-grid")
    assert layout["cards"] % layout["columns"] == 0, layout
    counts = [count for count in page.evaluate("window.visibleCounts") if count]
    assert set(counts) == {layout["cards"]}, counts


def test_loading_the_card_view_never_shows_an_incomplete_page(
    logged_in_page: Page, live_server, seed_data_e2e
):
    """The first page is sized for cards, not first rendered with the list page size."""
    page = logged_in_page
    page.set_viewport_size({"width": 1600, "height": 1000})
    for index in range(60):
        _own(seed_data_e2e.alice, GiftFactory(name=f"Load gift {index:02d}"))
    page.add_init_script(
        """
        // Already cleared at login: the saved card view preference applies
        sessionStorage.setItem('viewPreferencesCleared', 'true');
        localStorage.setItem('view-preference-gift-grid', 'card');
        window.visibleCounts = [];
        new MutationObserver(() => {
            const tbody = document.querySelector('#gift-grid .gridjs-tbody');
            if (tbody && getComputedStyle(tbody).visibility === 'visible') {
                window.visibleCounts.push(tbody.querySelectorAll('.gridjs-tr').length);
            }
        }).observe(document, { childList: true, subtree: true, attributes: true });
        """
    )
    page.goto(f"{live_server.url}/en/gifts/", wait_until="networkidle")
    _wait_for_grid(page, "gift-grid")

    layout = page.evaluate(CARD_GRID_JS, "gift-grid")
    assert layout["cards"] % layout["columns"] == 0, layout
    counts = [count for count in page.evaluate("window.visibleCounts") if count]
    assert set(counts) == {layout["cards"]}, counts
