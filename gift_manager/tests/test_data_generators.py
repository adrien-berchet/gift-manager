"""Test data generators for property-based testing.

This module provides Hypothesis strategies for generating test data
for all entity types in the Gift Manager application.
"""

from datetime import date
from datetime import timedelta

from hypothesis import strategies as st

from gift_manager.models import PermissionLevel

# Basic data type strategies
safe_text = st.text(
    alphabet=st.characters(
        min_codepoint=32,  # Space character
        max_codepoint=126,  # Tilde character (printable ASCII)
        blacklist_categories=("Cc", "Cf", "Cs", "Co", "Cn"),  # Exclude control characters
    ),
    min_size=1,
    max_size=100,
).filter(lambda x: x.strip() and "\x00" not in x)

short_text = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_categories=("Cc", "Cf", "Cs", "Co", "Cn"),
    ),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip() and "\x00" not in x)

# Email strategy
email_strategy = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    local=st.text(
        alphabet=st.characters(
            min_codepoint=97,  # 'a'
            max_codepoint=122,  # 'z'
        ),
        min_size=3,
        max_size=20,
    ),
    domain=st.text(
        alphabet=st.characters(
            min_codepoint=97,  # 'a'
            max_codepoint=122,  # 'z'
        ),
        min_size=3,
        max_size=15,
    ),
)

# Date strategies
past_date = st.dates(min_value=date(2020, 1, 1), max_value=date.today() - timedelta(days=1))

future_date = st.dates(min_value=date.today() + timedelta(days=1), max_value=date(2030, 12, 31))

# Entity-specific strategies
person_data = st.fixed_dictionaries(
    {
        "first_name": short_text,
        "family_name": st.one_of(st.none(), short_text),
        "email_address": st.one_of(st.none(), email_strategy),
    }
)

gift_data = st.fixed_dictionaries(
    {
        "name": safe_text,
        "comment": st.one_of(st.none(), safe_text),
    }
)

event_data = st.fixed_dictionaries(
    {
        "name": safe_text,
        "comment": st.one_of(st.none(), safe_text),
        "usual_date": st.one_of(st.none(), future_date),
        "recurrence": st.one_of(
            st.none(), st.sampled_from(["daily", "weekly", "monthly", "yearly"])
        ),
    }
)

person_group_data = st.fixed_dictionaries(
    {
        "name": safe_text,
    }
)

gift_tag_data = st.fixed_dictionaries(
    {
        "name": safe_text,
        "is_public": st.booleans(),
    }
)

relation_data = st.fixed_dictionaries(
    {
        "comment": st.one_of(st.none(), safe_text),
        "due_date": st.one_of(st.none(), future_date),
    }
)

# Combined entity data strategy
entity_data_strategy = st.one_of(
    person_data,
    gift_data,
    event_data,
    person_group_data,
    gift_tag_data,
    relation_data,
)

# UI interaction strategies
entity_types = st.sampled_from(["person", "gift", "event", "relation", "persongroup", "gifttag"])

ui_actions = st.sampled_from(["edit", "delete", "create", "detail", "list"])

permission_levels = st.sampled_from(
    [
        PermissionLevel.NONE,
        PermissionLevel.VIEWER,
        PermissionLevel.EDITOR,
        PermissionLevel.OWNER,
    ]
)

# Screen size strategies for responsive testing
screen_sizes = st.fixed_dictionaries(
    {
        "width": st.integers(min_value=320, max_value=1920),
        "height": st.integers(min_value=568, max_value=1080),
    }
)

mobile_screen_sizes = st.fixed_dictionaries(
    {
        "width": st.integers(min_value=320, max_value=768),
        "height": st.integers(min_value=568, max_value=1024),
    }
)

desktop_screen_sizes = st.fixed_dictionaries(
    {
        "width": st.integers(min_value=1024, max_value=1920),
        "height": st.integers(min_value=768, max_value=1080),
    }
)

# Form data strategies
form_field_names = st.sampled_from(
    [
        "name",
        "first_name",
        "family_name",
        "comment",
        "email_address",
        "usual_date",
        "recurrence",
        "is_public",
        "due_date",
    ]
)

form_data_strategy = st.dictionaries(
    form_field_names,
    st.one_of(safe_text, st.none(), st.booleans()),
    min_size=0,
    max_size=5,
)

# Bulk operation strategies
bulk_actions = st.sampled_from(["bulk_delete", "bulk_share"])

entity_counts = st.integers(min_value=1, max_value=10)

# Search and filter strategies
search_terms = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_categories=("Cc", "Cf", "Cs", "Co", "Cn"),
    ),
    min_size=1,
    max_size=30,
).filter(lambda x: x.strip())

filter_options = st.dictionaries(
    st.sampled_from(["status", "tag", "group", "event", "person"]),
    st.one_of(safe_text, st.integers(min_value=1, max_value=100)),
    min_size=0,
    max_size=3,
)

# Error simulation strategies
invalid_data_strategy = st.one_of(
    st.none(),
    st.text(max_size=0),  # Empty string
    st.text(alphabet="\x00\x01\x02", min_size=1, max_size=5),  # Invalid characters
    st.text(min_size=1000, max_size=2000),  # Too long
)

# HTTP status codes for testing
http_status_codes = st.sampled_from([200, 201, 302, 400, 401, 403, 404, 500])

# HTMX-specific strategies
htmx_triggers = st.sampled_from(
    [
        "list:update",
        "modal:close",
        "offcanvas:close",
        "showNotification",
        "form:reset",
        "page:reload",
    ]
)

htmx_headers = st.fixed_dictionaries(
    {
        "HX-Request": st.just("true"),
        "HX-Target": st.one_of(st.none(), st.sampled_from(["#modal", "#offcanvas", "#list"])),
        "HX-Trigger": st.one_of(st.none(), htmx_triggers),
    }
)

# Accessibility testing strategies
keyboard_keys = st.sampled_from(
    ["Enter", "Escape", "Tab", "Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]
)

aria_attributes = st.sampled_from(
    [
        "aria-label",
        "aria-describedby",
        "aria-hidden",
        "aria-expanded",
        "aria-controls",
        "role",
        "tabindex",
    ]
)

# Performance testing strategies
response_times = st.integers(min_value=50, max_value=5000)  # milliseconds

# Validation error strategies
validation_errors = st.sampled_from(
    [
        "This field is required.",
        "Enter a valid email address.",
        "This value is too long.",
        "This value is too short.",
        "Invalid choice.",
    ]
)
