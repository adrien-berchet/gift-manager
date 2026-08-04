"""Property-Based Testing Configuration.

This module provides configuration settings and utilities for property-based
testing with Hypothesis in the Gift Manager application.
"""

from hypothesis import Verbosity
from hypothesis import settings

# Hypothesis configuration for property-based tests
# Minimum 100 iterations per property test as specified in design document
PBT_SETTINGS = settings(
    max_examples=100,  # Minimum iterations per property test
    deadline=30000,  # 30 seconds timeout per test case
    verbosity=Verbosity.normal,
    suppress_health_check=[
        # Suppress health checks that might interfere with Django testing
        # HealthCheck.too_slow,  # Allow slower tests for comprehensive coverage
        # HealthCheck.data_too_large,  # Allow larger test data for realistic scenarios
    ],
    # Database setting removed - not needed for Django tests
)

# Fast settings for development/debugging
PBT_FAST_SETTINGS = settings(
    max_examples=10,  # Fewer examples for faster feedback during development
    deadline=10000,  # 10 seconds timeout
    verbosity=Verbosity.quiet,
)

# PR settings keep property tests in the review gate while reducing example count
PBT_PR_SETTINGS = settings(
    max_examples=25,
    deadline=30000,
    verbosity=Verbosity.normal,
)

# Comprehensive settings for CI/production testing
PBT_COMPREHENSIVE_SETTINGS = settings(
    max_examples=200,  # More examples for thorough testing
    deadline=60000,  # 60 seconds timeout
    verbosity=Verbosity.verbose,
)

# Entity type mappings for property tests
ENTITY_TYPE_MAPPINGS = {
    "person": {
        "model": "gift_manager.models.Person",
        "factory": "gift_manager.tests.factories.PersonFactory",
        "pk_field": "person_id",
        "required_fields": ["first_name"],
        "optional_fields": ["family_name", "email_address"],
        "url_patterns": {
            "create": "gift_manager:person_create",
            "edit": "gift_manager:person_edit",
            "delete": "gift_manager:person_delete",
            "detail": "gift_manager:person_detail",
            "list": "gift_manager:persons",
        },
    },
    "gift": {
        "model": "gift_manager.models.Gift",
        "factory": "gift_manager.tests.factories.GiftFactory",
        "pk_field": "gift_id",
        "required_fields": ["name"],
        "optional_fields": ["comment"],
        "url_patterns": {
            "create": "gift_manager:gift_create",
            "edit": "gift_manager:gift_edit",
            "delete": "gift_manager:gift_delete",
            "detail": "gift_manager:gift_detail",
            "list": "gift_manager:gifts",
        },
    },
    "event": {
        "model": "gift_manager.models.Event",
        "factory": "gift_manager.tests.factories.EventFactory",
        "pk_field": "event_id",
        "required_fields": ["name"],
        "optional_fields": ["comment", "schedule_type", "date", "recurrence"],
        "url_patterns": {
            "create": "gift_manager:event_create",
            "edit": "gift_manager:event_edit",
            "delete": "gift_manager:event_delete",
            "detail": "gift_manager:event_detail",
            "list": "gift_manager:events",
        },
    },
    "relation": {
        "model": "gift_manager.models.Relation",
        "factory": "gift_manager.tests.factories.RelationFactory",
        "pk_field": "relation_id",
        "required_fields": ["person", "gift"],  # Either person or group required
        "optional_fields": ["comment", "event", "status", "due_date"],
        "url_patterns": {
            "create": "gift_manager:relation_create",
            "edit": "gift_manager:relation_edit",
            "delete": "gift_manager:relation_delete",
            "detail": "gift_manager:relation_detail",
            "list": "gift_manager:relations",
        },
    },
    "persongroup": {
        "model": "gift_manager.models.PersonGroup",
        "factory": "gift_manager.tests.factories.PersonGroupFactory",
        "pk_field": "group_id",
        "required_fields": ["name"],
        "optional_fields": ["parent_groups"],
        "url_patterns": {
            "create": "gift_manager:person_group_create",
            "edit": "gift_manager:person_group_edit",
            "delete": "gift_manager:person_group_delete",
            "detail": "gift_manager:person_group_detail",
            "list": "gift_manager:person_groups",
        },
    },
    "gifttag": {
        "model": "gift_manager.models.GiftTag",
        "factory": "gift_manager.tests.factories.GiftTagFactory",
        "pk_field": "tag_id",
        "required_fields": ["name"],
        "optional_fields": ["parent_tags", "is_public"],
        "url_patterns": {
            "create": "gift_manager:gift_tag_create",
            "edit": "gift_manager:gift_tag_edit",
            "delete": "gift_manager:gift_tag_delete",
            "detail": "gift_manager:gift_tag_detail",
            "list": "gift_manager:gift_tags",
        },
    },
}

# Property test metadata for tracking and reporting
PROPERTY_METADATA = {
    1: {
        "name": "UI Component Display Consistency",
        "description": (
            "For any entity type and any UI action, clicking the corresponding "
            "button should display the appropriate UI component with the correct "
            "content and structure."
        ),
        "requirements": ["1.1", "2.1", "3.1", "5.1"],
        "test_method": "test_property_1_ui_component_display_consistency",
    },
    2: {
        "name": "Data Population Accuracy",
        "description": (
            "For any entity and any form or detail view, when the UI component "
            "is displayed, all fields and information should be populated with "
            "the current entity data accurately and completely."
        ),
        "requirements": ["2.2", "3.2", "5.2"],
        "test_method": "test_property_2_data_population_accuracy",
    },
    3: {
        "name": "Successful Operation Completion",
        "description": (
            "For any valid CRUD operation, when the operation completes "
            "successfully, the entity should be modified as expected and the "
            "current view should be updated without page reload."
        ),
        "requirements": ["1.3", "2.4", "4.4", "5.3"],
        "test_method": "test_property_3_successful_operation_completion",
    },
    4: {
        "name": "Error Handling Consistency",
        "description": (
            "For any operation that fails due to validation errors, constraints, "
            "or permissions, appropriate error messages should be displayed "
            "within the current UI component without closing it."
        ),
        "requirements": ["1.5", "2.6", "5.4"],
        "test_method": "test_property_4_error_handling_consistency",
    },
    5: {
        "name": "Cancellation Behavior",
        "description": (
            "For any UI component, when a user cancels or closes the component, "
            "it should close properly and maintain the current application state "
            "without any changes."
        ),
        "requirements": ["1.4", "2.5", "3.5"],
        "test_method": "test_property_5_cancellation_behavior",
    },
    6: {
        "name": "Permission-Based UI Adaptation",
        "description": (
            "For any user with specific permissions, the UI should only display "
            "action buttons and operations that the user is authorized to perform."
        ),
        "requirements": ["4.5", "5.5", "6.5"],
        "test_method": "test_property_6_permission_based_ui_adaptation",
    },
    7: {
        "name": "Quick Actions Availability",
        "description": (
            "For any entity list, each item should display appropriate quick "
            "action buttons that are accessible and functional."
        ),
        "requirements": ["4.1", "4.2"],
        "test_method": "test_property_7_quick_actions_availability",
    },
    8: {
        "name": "Inline Editing Functionality",
        "description": (
            "For any editable field in list views, double-clicking should "
            "activate inline editing, and completing the edit should save the "
            "change via AJAX with visual feedback."
        ),
        "requirements": ["4.3", "4.4"],
        "test_method": "test_property_8_inline_editing_functionality",
    },
    9: {
        "name": "Bulk Operations Support",
        "description": (
            "For any entity list with multiple items selected, the system should "
            "provide bulk operation capabilities with appropriate confirmation "
            "dialogs and progress feedback."
        ),
        "requirements": ["6.1", "6.2", "6.3", "6.4"],
        "test_method": "test_property_9_bulk_operations_support",
    },
    10: {
        "name": "Real-Time List Features",
        "description": (
            "For any list view, search and filter operations should update "
            "results immediately without page reload, and expandable rows should "
            "reveal details without navigation."
        ),
        "requirements": ["7.1", "7.2", "7.3"],
        "test_method": "test_property_10_real_time_list_features",
    },
    11: {
        "name": "Loading State Feedback",
        "description": (
            "For any operation that takes time to complete, appropriate loading "
            "indicators should be displayed, and form controls should be disabled "
            "during submission."
        ),
        "requirements": ["8.1", "8.2", "8.3", "8.4"],
        "test_method": "test_property_11_loading_state_feedback",
    },
    12: {
        "name": "Mobile Responsiveness",
        "description": (
            "For any screen size, UI components should adapt appropriately with "
            "full-screen panels on small screens, touch-friendly elements, and "
            "proper keyboard handling."
        ),
        "requirements": ["9.1", "9.2", "9.3", "9.5"],
        "test_method": "test_property_12_mobile_responsiveness",
    },
    13: {
        "name": "Keyboard Accessibility",
        "description": (
            "For any modal or panel, keyboard navigation should work properly "
            "with visible focus indicators, Escape key should close components, "
            "and common shortcuts should be supported."
        ),
        "requirements": ["10.1", "10.2", "10.3", "10.5"],
        "test_method": "test_property_13_keyboard_accessibility",
    },
    14: {
        "name": "Unsaved Changes Protection",
        "description": (
            "For any form with unsaved changes, attempting to navigate away or "
            "close should prompt the user to save or discard changes, with "
            "visual indicators showing modified state."
        ),
        "requirements": ["12.1", "12.2", "12.3", "12.4", "12.5"],
        "test_method": "test_property_14_unsaved_changes_protection",
    },
}

# Test database configuration for property-based tests
PBT_DATABASE_CONFIG = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",  # Use in-memory database for faster tests
    "OPTIONS": {
        "timeout": 20,
    },
}

# Test fixtures configuration
PBT_FIXTURES_CONFIG = {
    "create_test_users": True,
    "create_test_permissions": True,
    "create_test_data": True,
    "cleanup_after_test": True,
}

# Performance thresholds for property tests
PERFORMANCE_THRESHOLDS = {
    "max_response_time_ms": 5000,  # 5 seconds max response time
    "max_database_queries": 50,  # Maximum database queries per request
    "max_memory_usage_mb": 100,  # Maximum memory usage per test
}

# Error patterns to ignore in property tests
IGNORED_ERROR_PATTERNS = [
    r".*CSRF.*",  # CSRF errors are expected in some test scenarios
    r".*Permission denied.*",  # Permission errors are expected for permission tests
    r".*Not found.*",  # 404 errors are expected for some test scenarios
]


# Utility functions for property-based testing
def get_entity_config(entity_type):
    """Get configuration for a specific entity type."""
    return ENTITY_TYPE_MAPPINGS.get(entity_type.lower())


def get_property_metadata(property_number):
    """Get metadata for a specific property test."""
    return PROPERTY_METADATA.get(property_number)


def is_valid_entity_type(entity_type):
    """Check if an entity type is valid for testing."""
    return entity_type.lower() in ENTITY_TYPE_MAPPINGS


def get_all_entity_types():
    """Get all valid entity types for testing."""
    return list(ENTITY_TYPE_MAPPINGS.keys())


def get_url_pattern(entity_type, action):
    """Get URL pattern for a specific entity type and action."""
    config = get_entity_config(entity_type)
    if config:
        return config.get("url_patterns", {}).get(action)
    return None
