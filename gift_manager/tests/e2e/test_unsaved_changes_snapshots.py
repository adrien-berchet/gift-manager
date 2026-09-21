"""Browser regressions for form snapshots independent of server responses."""

from pathlib import Path

import pytest
from playwright.sync_api import Page

pytestmark = [pytest.mark.frontend]


@pytest.fixture
def tracked_page(page: Page):
    """Load the real tracker with the field types used by editable forms."""
    page.set_content("""
        <form id="main-form" data-track-changes>
            <input name="name" value="Original">
            <textarea name="comment">Original comment</textarea>
            <input type="checkbox" name="groups" value="one" checked>
            <input type="checkbox" name="groups" value="two">
            <input type="radio" name="schedule" value="one" checked>
            <input type="radio" name="schedule" value="two">
            <select name="status">
                <option value="one" selected>One</option><option value="two">Two</option>
            </select>
            <select name="tags" multiple>
                <option value="one" selected>One</option><option value="two">Two</option>
            </select>
            <input type="file" name="attachment" multiple>
            <input name="locked" value="Read only" disabled>
            <input name="name" value="Ignored hidden value" type="hidden">
            <input name="permission" class="permission-select" value="view">
            <input name="search" class="no-track">
        </form>
    """)
    script = Path(__file__).parents[2] / "static/gift_manager/unsaved-changes.js"
    page.add_script_tag(path=script)
    return page


def navigation_is_blocked(page: Page) -> bool:
    """Refresh dirty state through the same guard used when leaving a page."""
    return page.evaluate("""() => {
        const event = new Event('beforeunload', {cancelable: true});
        window.dispatchEvent(event);
        return event.defaultPrevented;
    }""")


def test_untouched_form_and_ignored_fields_do_not_warn(tracked_page: Page):
    """Repeated snapshots and changes outside editable data stay clean."""
    for _ in range(3):
        assert not navigation_is_blocked(tracked_page)
    tracked_page.locator("[name=locked]").evaluate("field => { field.value = 'Updated'; }")
    tracked_page.locator("[name=permission]").fill("edit")
    tracked_page.locator("[name=search]").fill("filter")
    assert not navigation_is_blocked(tracked_page)


@pytest.mark.parametrize("successful", [True, False])
def test_temporary_loading_state_preserves_edits(tracked_page: Page, *, successful: bool):
    """Saving keeps real values; a failed save keeps genuine changes protected."""
    tracked_page.locator("input[name=name]:not([type=hidden])").fill("Edited")
    assert navigation_is_blocked(tracked_page)
    tracked_page.evaluate("""() => {
        document.querySelectorAll('input, select, textarea').forEach(field => {
            field.dataset.originalDisabled = field.disabled;
            field.disabled = true;
        });
    }""")
    assert navigation_is_blocked(tracked_page)
    tracked_page.evaluate(
        """successful => {
        document.querySelector('form').dispatchEvent(new CustomEvent('htmx:afterRequest', {
            bubbles: true, detail: {successful}
        }));
    }""",
        successful,
    )
    assert navigation_is_blocked(tracked_page) is not successful
    tracked_page.evaluate("""() => {
        document.querySelectorAll('input, select, textarea').forEach(field => {
            field.disabled = field.dataset.originalDisabled === 'true';
            delete field.dataset.originalDisabled;
        });
    }""")
    assert navigation_is_blocked(tracked_page) is not successful


@pytest.mark.parametrize("field_name", ["name", "comment", "groups", "schedule", "status", "tags"])
def test_editing_and_reverting_fields(tracked_page: Page, field_name: str):
    """Each editable field type warns immediately, and undoing the edit clears it."""
    tracked_page.evaluate(
        """name => {
        const field = document.querySelector(`[name="${name}"]`);
        if (field.type === 'checkbox' || field.type === 'radio') {
            document.querySelectorAll(`[name="${name}"]`)[1].checked = true;
        } else if (field.tagName === 'SELECT') {
            field.options[1].selected = true;
        } else {
            field.value = 'Edited';
        }
    }""",
        field_name,
    )
    assert navigation_is_blocked(tracked_page)
    tracked_page.locator("form").evaluate("form => form.reset()")
    assert not navigation_is_blocked(tracked_page)


def test_selected_empty_file_is_an_edit(tracked_page: Page):
    """An empty upload control is clean, but choosing a zero-byte file is an edit."""
    attachment = tracked_page.locator("[name=attachment]")
    attachment.set_input_files({"name": "empty.txt", "mimeType": "text/plain", "buffer": b""})
    assert navigation_is_blocked(tracked_page)
    attachment.set_input_files([])
    assert not navigation_is_blocked(tracked_page)
