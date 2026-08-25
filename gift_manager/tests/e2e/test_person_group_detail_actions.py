"""Focused browser regressions for person-group detail actions and grids."""

import re

import pytest
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect

from gift_manager.models import PermissionLevel
from gift_manager.permissions import create_or_update_permission
from gift_manager.tests.e2e.base_test import BaseE2ETest
from gift_manager.tests.factories import GiftFactory
from gift_manager.tests.factories import GroupRelationFactory
from gift_manager.tests.factories import PersonFactory
from gift_manager.tests.factories import PersonGroupFactory
from gift_manager.tests.factories import UserFactory


class TestPersonGroupDetailActions(BaseE2ETest):
    """Contextual creates use the panel and leave every Actions column reachable."""

    def test_page_container_is_fluid_between_mobile_and_desktop(
        self, page: Page, live_server, test_user
    ):
        group = PersonGroupFactory(name="Fluid layout regression group")
        create_or_update_permission(
            test_user,
            group,
            permission_level=PermissionLevel.OWNER,
        )

        page.set_viewport_size({"width": 577, "height": 1000})
        self.login_as_user(page, live_server, test_user)
        detail_path = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        page.goto(f"{live_server.url}{detail_path}")
        page.wait_for_load_state("networkidle")

        main_content = page.locator("#main-content")
        for viewport_width in (577, 640, 767, 896, 991, 1100, 1199, 1200, 1440):
            page.set_viewport_size({"width": viewport_width, "height": 1000})
            layout = main_content.evaluate(
                """main => {
                    const style = getComputedStyle(main);
                    const bounds = main.getBoundingClientRect();
                    return {
                        width: bounds.width,
                        maxWidth: style.maxWidth,
                        paddingLeft: parseFloat(style.paddingLeft),
                        paddingRight: parseFloat(style.paddingRight),
                        bodyWidth: document.body.getBoundingClientRect().width,
                        documentClientWidth: document.documentElement.clientWidth,
                        documentScrollWidth: document.documentElement.scrollWidth
                    };
                }"""
            )

            assert layout["documentScrollWidth"] <= layout["documentClientWidth"] + 1
            if viewport_width <= 1200:
                assert layout["maxWidth"] == "none"
                assert abs(layout["width"] - layout["bodyWidth"]) <= 1
                assert abs(layout["paddingLeft"] - layout["paddingRight"]) <= 1
                assert 12 <= layout["paddingLeft"] <= 24
            else:
                assert layout["maxWidth"] == "1400px"
                assert layout["width"] <= 1401

    def test_only_non_action_columns_absorb_viewport_width_changes(
        self, page: Page, live_server, test_user
    ):
        group = PersonGroupFactory(name="Adaptive column regression group")
        person = PersonFactory(first_name="Adaptive", family_name="Member", groups=[group])
        for entity in (group, person):
            create_or_update_permission(
                test_user,
                entity,
                permission_level=PermissionLevel.OWNER,
            )

        page.set_viewport_size({"width": 768, "height": 1000})
        self.login_as_user(page, live_server, test_user)
        detail_path = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        page.goto(f"{live_server.url}{detail_path}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#persons-grid tbody tr").first).to_be_visible()

        def column_widths_at(viewport_width):
            page.set_viewport_size({"width": viewport_width, "height": 1000})
            page.evaluate(
                """() => new Promise(resolve => requestAnimationFrame(
                    () => requestAnimationFrame(resolve)
                ))"""
            )
            return page.locator("#persons-grid").evaluate(
                """grid => {
                    const cells = Array.from(grid.querySelectorAll('tbody tr:first-child td'));
                    const actionCell = cells.at(-1);
                    const columns = Array.from(
                        grid.querySelectorAll(
                            'table > colgroup[data-group-detail-columns] > col'
                        )
                    );
                    return {
                        action: actionCell.getBoundingClientRect().width,
                        actionButtons: actionCell.querySelector(
                            '.quick-actions-container'
                        ).getBoundingClientRect().width,
                        measuredAction: parseFloat(
                            getComputedStyle(grid).getPropertyValue(
                                '--group-detail-actions-width'
                            )
                        ),
                        nonActions: cells.slice(0, -1).reduce(
                            (width, cell) => width + cell.getBoundingClientRect().width,
                            0
                        ),
                        columnWidths: columns.map(
                            column => column.getBoundingClientRect().width
                        ),
                        columnStyleWidths: columns.map(column => column.style.width),
                        headerStyleWidths: Array.from(
                            grid.querySelectorAll('thead tr:first-child th')
                        ).map(header => header.style.width)
                    };
                }"""
            )

        compact_narrow = column_widths_at(768)
        compact_wide = column_widths_at(900)
        assert abs(compact_narrow["action"] - compact_wide["action"]) <= 1, (
            compact_narrow,
            compact_wide,
        )
        assert compact_wide["nonActions"] >= compact_narrow["nonActions"] + 100

        expanded_narrow = column_widths_at(1000)
        expanded_wide = column_widths_at(1200)
        assert abs(expanded_narrow["action"] - expanded_wide["action"]) <= 1, (
            expanded_narrow,
            expanded_wide,
        )
        assert expanded_wide["nonActions"] >= expanded_narrow["nonActions"] + 160
        assert expanded_narrow["action"] >= compact_wide["action"] + 80

        for layout in (compact_narrow, compact_wide, expanded_narrow, expanded_wide):
            assert abs(layout["action"] - layout["measuredAction"]) <= 1
            assert layout["columnStyleWidths"][-1].endswith("px")
            assert all(width.startswith("calc(") for width in layout["columnStyleWidths"][:-1])
            assert all(width == "" for width in layout["headerStyleWidths"])

    def test_dense_table_columns_keep_a_readable_minimum_width(
        self, page: Page, live_server, test_user
    ):
        page.set_viewport_size({"width": 320, "height": 1000})
        group = PersonGroupFactory(name="Minimum-width regression group")
        gift = GiftFactory(name="Minimum-width regression gift")
        relation = GroupRelationFactory(group=group, gift=gift)
        for entity in (group, gift, relation):
            create_or_update_permission(
                test_user,
                entity,
                permission_level=PermissionLevel.OWNER,
            )

        self.login_as_user(page, live_server, test_user)
        detail_path = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        page.goto(f"{live_server.url}{detail_path}")
        page.wait_for_load_state("networkidle")
        page.locator("#nested-gifts-tab").click()

        grid = page.locator("#nested-gifts-grid")
        expect(grid.locator("tbody tr").first).to_be_visible()
        page.wait_for_function(
            """() => parseFloat(
                getComputedStyle(document.querySelector('#nested-gifts-grid')).getPropertyValue(
                    '--group-detail-min-table-width'
                )
            ) > 0"""
        )

        layout = grid.evaluate(
            """grid => {
                const wrapper = grid.querySelector('.gridjs-wrapper');
                const cells = Array.from(grid.querySelectorAll('tbody tr:first-child td'));
                const actionCell = cells.at(-1);
                const wrapperBounds = wrapper.getBoundingClientRect();
                const actionBounds = actionCell.getBoundingClientRect();
                const style = getComputedStyle(grid);
                return {
                    wrapperClientWidth: wrapper.clientWidth,
                    wrapperScrollWidth: wrapper.scrollWidth,
                    minimumColumnWidth: parseFloat(
                        style.getPropertyValue('--group-detail-min-column-width')
                    ),
                    minimumTableWidth: parseFloat(
                        style.getPropertyValue('--group-detail-min-table-width')
                    ),
                    tableWidth: grid.querySelector('.gridjs-table').getBoundingClientRect().width,
                    nonActionWidths: cells.slice(0, -1).map(
                        cell => cell.getBoundingClientRect().width
                    ),
                    actionStartsAfterViewport: actionBounds.x >= (
                        wrapperBounds.x + wrapperBounds.width
                    )
                };
            }"""
        )

        assert 95 <= layout["minimumColumnWidth"] <= 97
        assert all(width >= layout["minimumColumnWidth"] - 1 for width in layout["nonActionWidths"])
        assert layout["tableWidth"] >= layout["minimumTableWidth"] - 1
        assert layout["wrapperScrollWidth"] > layout["wrapperClientWidth"]
        assert layout["actionStartsAfterViewport"]

        wrapper = grid.locator(".gridjs-wrapper")
        wrapper.evaluate("element => { element.scrollLeft = element.scrollWidth; }")
        assert wrapper.evaluate("element => element.scrollLeft") > 0
        action_button = grid.locator("tbody tr").first.locator(".quick-action-btn").first
        action_button.focus()
        assert action_button.evaluate("button => document.activeElement === button")
        wrapper_bounds = wrapper.bounding_box()
        button_bounds = action_button.bounding_box()
        assert wrapper_bounds is not None and button_bounds is not None
        assert button_bounds["x"] >= wrapper_bounds["x"]
        assert button_bounds["x"] + button_bounds["width"] <= (
            wrapper_bounds["x"] + wrapper_bounds["width"]
        )

        page.set_viewport_size({"width": 768, "height": 1000})
        page.evaluate(
            """() => new Promise(resolve => requestAnimationFrame(
                () => requestAnimationFrame(resolve)
            ))"""
        )
        wrapper.evaluate("element => { element.scrollLeft = 0; }")
        boundary_layout = grid.evaluate(
            """grid => {
                const wrapper = grid.querySelector('.gridjs-wrapper');
                const cells = Array.from(grid.querySelectorAll('tbody tr:first-child td'));
                return {
                    clientWidth: wrapper.clientWidth,
                    scrollWidth: wrapper.scrollWidth,
                    nonActionWidths: cells.slice(0, -1).map(
                        cell => cell.getBoundingClientRect().width
                    )
                };
            }"""
        )
        assert boundary_layout["scrollWidth"] <= boundary_layout["clientWidth"] + 8
        assert all(
            width >= layout["minimumColumnWidth"] - 1
            for width in boundary_layout["nonActionWidths"]
        )

    @pytest.mark.parametrize("viewport_width", [575, 767, 768, 991, 992, 1200, 1440])
    def test_contextual_panels_and_action_columns_follow_responsive_layout(
        self, page: Page, live_server, test_user, viewport_width
    ):
        page.set_viewport_size({"width": viewport_width, "height": 1000})

        def run_mobile_table_enhancement():
            page.evaluate(
                """() => {
                    document.querySelectorAll('.gridjs-table').forEach(
                        table => table.removeAttribute('data-mobile-enhanced')
                    );
                    window.UIEnhancements.enhanceMobileTables();
                }"""
            )

        group = PersonGroupFactory(name="Panel and grid regression group")
        person = PersonFactory(
            first_name="Direct",
            family_name="Member",
            groups=[group],
        )
        gift = GiftFactory(
            name="A deliberately long gift plan name that must not push Actions off screen"
        )
        panel_gift = GiftFactory(name="Created from the group panel")
        relation = GroupRelationFactory(group=group, gift=gift)
        shared_user = UserFactory(username="mobile-label-shared-user")

        for entity in (group, person, gift, panel_gift, relation):
            create_or_update_permission(
                test_user,
                entity,
                permission_level=PermissionLevel.OWNER,
            )
        create_or_update_permission(
            shared_user,
            group,
            permission_level=PermissionLevel.VIEWER,
        )

        self.login_as_user(page, live_server, test_user)
        detail_path = reverse("gift_manager:person_group_detail", kwargs={"pk": group.group_id})
        page.goto(f"{live_server.url}{detail_path}")
        page.wait_for_load_state("networkidle")

        if viewport_width <= 576:
            run_mobile_table_enhancement()
            shared_user_cell = (
                page.locator("#shares-grid tbody tr").first.locator("td[data-label]").first
            )
            expect(shared_user_cell).to_be_visible()
            expect(shared_user_cell).to_have_attribute("data-label", re.compile(r"\S"))
            assert (
                shared_user_cell.evaluate("cell => getComputedStyle(cell, '::before').content")
                == "none"
            )

        person_create = page.get_by_role("link", name="Create new person")
        expect(person_create).to_be_visible()
        detail_url = page.url
        person_create.click()
        self.wait_for_panel(page)
        assert page.url == detail_url

        panel = page.locator("#editPanel")
        selected_groups = panel.locator('select[name="groups"] option:checked')
        expect(selected_groups).to_have_count(1)
        expect(selected_groups.first).to_have_attribute("value", str(group.pk))
        self.close_panel(page)

        page.locator("#gifts-tab").click()
        expect(page.locator("#gifts-list")).to_have_class(re.compile(r"\bactive\b"))
        gift_tab_url = page.url
        gift_plan_create = page.get_by_role("link", name="New Gift Plan for this group")
        expect(gift_plan_create).to_be_visible()
        gift_plan_create.click()
        self.wait_for_panel(page)
        assert page.url == gift_tab_url
        relation_form = panel.locator("form")
        expect(relation_form).to_be_visible()
        relation_form.locator('select[name="gift"]').select_option(str(panel_gift.pk))
        relation_form.locator('select[name="status"]').select_option(str(relation.status.pk))
        relation_form.locator('textarea[name="comment"]').fill("Created through the panel")

        with page.expect_navigation(wait_until="networkidle"):
            relation_form.locator('button[type="submit"]').click()

        assert page.url == gift_tab_url
        expect(page.locator("#gifts-list")).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator("#gifts-grid")).to_contain_text(panel_gift.name)
        if viewport_width <= 576:
            run_mobile_table_enhancement()

        tab_grids = (
            ("#persons-tab", "#persons-list", "#persons-grid"),
            ("#nested-members-tab", "#nested-members-list", "#nested-members-grid"),
            ("#gifts-tab", "#gifts-list", "#gifts-grid"),
            ("#nested-gifts-tab", "#nested-gifts-list", "#nested-gifts-grid"),
        )
        for tab_selector, pane_selector, grid_selector in tab_grids:
            page.locator(tab_selector).click()
            expect(page.locator(pane_selector)).to_have_class(re.compile(r"\bactive\b"))
            grid = page.locator(grid_selector)
            expect(grid.locator("tbody tr").first).to_be_visible()
            page.wait_for_function(
                """selector => {
                    const grid = document.querySelector(selector);
                    return parseFloat(
                        getComputedStyle(grid).getPropertyValue(
                            '--group-detail-actions-width'
                        )
                    ) > 0;
                }""",
                arg=grid_selector,
            )

            wrapper = grid.locator(".gridjs-wrapper")
            dimensions = wrapper.evaluate(
                """wrapper => ({
                    clientWidth: wrapper.clientWidth,
                    scrollWidth: wrapper.scrollWidth,
                    scrollLeft: wrapper.scrollLeft,
                    actionWidth: parseFloat(
                        getComputedStyle(wrapper.closest('[id$="-grid"]')).getPropertyValue(
                            '--group-detail-actions-width'
                        )
                    )
                })"""
            )
            # Grid.js' wrapper contributes a few border/sub-pixel pixels in Chromium.
            overflow_tolerance = 8 if viewport_width <= 768 else 4
            if viewport_width < 768:
                assert dimensions["scrollWidth"] >= (
                    dimensions["clientWidth"] + dimensions["actionWidth"] + 24
                ), f"{grid_selector} does not expose Actions through scrolling: {dimensions}"
            else:
                assert dimensions["scrollWidth"] <= (
                    dimensions["clientWidth"] + overflow_tolerance
                ), f"{grid_selector} requires horizontal scrolling: {dimensions}"
            assert dimensions["scrollLeft"] == 0

            table_layout = grid.locator(".gridjs-table").evaluate(
                "table => getComputedStyle(table).tableLayout"
            )
            assert table_layout == "fixed"

            action_header = grid.locator('.gridjs-th[data-column-id="actions"]')
            action_cell = grid.locator("tbody tr").first.locator("td").last
            action_buttons = action_cell.locator(".quick-actions-container")
            assert action_header.evaluate("cell => getComputedStyle(cell).display") != "none"
            assert action_cell.evaluate("cell => getComputedStyle(cell).display") != "none"
            assert action_cell.evaluate("cell => getComputedStyle(cell).position") != "sticky"
            if viewport_width <= 576:
                mobile_label_cell = grid.locator("tbody tr").first.locator("td[data-label]").first
                expect(mobile_label_cell).to_have_attribute("data-label", re.compile(r"\S"))
                mobile_label_content = mobile_label_cell.evaluate(
                    "cell => getComputedStyle(cell, '::before').content"
                )
                assert mobile_label_content == "none"

            wrapper_bounds = wrapper.bounding_box()
            initial_cell_bounds = action_cell.bounding_box()
            assert wrapper_bounds is not None and initial_cell_bounds is not None
            if viewport_width < 768:
                assert initial_cell_bounds["x"] >= (
                    wrapper_bounds["x"] + wrapper_bounds["width"] + 20
                )
                wrapper.evaluate("element => { element.scrollLeft = element.scrollWidth; }")
                assert wrapper.evaluate("element => element.scrollLeft") > 0

            expect(action_header).to_be_visible()
            expect(action_buttons).to_be_visible()
            assert action_buttons.evaluate("buttons => getComputedStyle(buttons).opacity") == "1"
            button_colors = action_buttons.locator(".quick-action-btn").evaluate_all(
                """buttons => buttons.map(button => {
                    const style = getComputedStyle(button);
                    return {
                        backgroundColor: style.backgroundColor,
                        opacity: style.opacity
                    };
                })"""
            )
            assert all(color["opacity"] == "1" for color in button_colors)
            assert all(
                color["backgroundColor"] not in ("transparent", "rgba(0, 0, 0, 0)")
                for color in button_colors
            )
            action_bounds = action_buttons.bounding_box()
            cell_bounds = action_cell.bounding_box()
            assert (
                action_bounds is not None and cell_bounds is not None and wrapper_bounds is not None
            )
            assert action_bounds["x"] >= wrapper_bounds["x"] - 1
            assert action_bounds["x"] + action_bounds["width"] <= (
                wrapper_bounds["x"] + wrapper_bounds["width"] + 1
            )
            assert cell_bounds["x"] + cell_bounds["width"] <= (
                wrapper_bounds["x"] + wrapper_bounds["width"] + 1
            )

            action_padding = action_cell.evaluate(
                """cell => {
                    const style = getComputedStyle(cell);
                    return parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
                }"""
            )
            expected_action_width = action_bounds["width"] + action_padding
            assert abs(cell_bounds["width"] - expected_action_width) <= 2
            measured_action_width = grid.evaluate(
                """container => parseFloat(
                    getComputedStyle(container).getPropertyValue(
                        '--group-detail-actions-width'
                    )
                )"""
            )
            assert abs(measured_action_width - expected_action_width) <= 2

            button_text = action_buttons.locator(".btn-text").first
            if viewport_width < 992:
                expect(button_text).not_to_be_visible()
                button_widths = action_buttons.locator(".quick-action-btn").evaluate_all(
                    "buttons => buttons.map(button => button.getBoundingClientRect().width)"
                )
                assert all(abs(width - 40) <= 1 for width in button_widths)
                button_heights = action_buttons.locator(".quick-action-btn").evaluate_all(
                    "buttons => buttons.map(button => button.getBoundingClientRect().height)"
                )
                assert all(abs(height - 40) <= 1 for height in button_heights)
                button_internal_styles = action_buttons.locator(".quick-action-btn").evaluate_all(
                    """buttons => buttons.map(button => {
                        const style = getComputedStyle(button);
                        return {
                            fontSize: parseFloat(style.fontSize),
                            paddingTop: parseFloat(style.paddingTop),
                            paddingRight: parseFloat(style.paddingRight),
                            paddingBottom: parseFloat(style.paddingBottom),
                            paddingLeft: parseFloat(style.paddingLeft)
                        };
                    })"""
                )
                assert all(abs(style["fontSize"] - 14) <= 0.1 for style in button_internal_styles)
                assert all(
                    all(
                        abs(style[side]) <= 0.1
                        for side in (
                            "paddingTop",
                            "paddingRight",
                            "paddingBottom",
                            "paddingLeft",
                        )
                    )
                    for style in button_internal_styles
                )
            else:
                expect(button_text).to_be_visible()

            left_gap = action_bounds["x"] - cell_bounds["x"]
            right_gap = (
                cell_bounds["x"]
                + cell_bounds["width"]
                - action_bounds["x"]
                - action_bounds["width"]
            )
            assert abs(left_gap - right_gap) <= 2
            assert 3.5 <= left_gap <= 5.5
            assert 3.5 <= right_gap <= 5.5
            assert left_gap + right_gap <= 10.5

            outline_budget = 4
            for action_button in (
                action_buttons.locator(".quick-action-btn").first,
                action_buttons.locator(".quick-action-btn").last,
            ):
                action_button.focus()
                assert action_button.evaluate("button => document.activeElement === button")
                button_bounds = action_button.bounding_box()
                assert button_bounds is not None
                assert button_bounds["x"] - outline_budget >= cell_bounds["x"] - 1
                assert button_bounds["x"] - outline_budget >= wrapper_bounds["x"] - 1
                assert button_bounds["x"] + button_bounds["width"] + outline_budget <= (
                    cell_bounds["x"] + cell_bounds["width"] + 1
                )
                assert button_bounds["x"] + button_bounds["width"] + outline_budget <= (
                    wrapper_bounds["x"] + wrapper_bounds["width"] + 1
                )
