"""Playwright configuration for Gift Manager end-to-end tests.

This configuration file sets up Playwright for testing the modern UX interface
with proper browser settings, timeouts, and test organization.
"""

from playwright.sync_api import Playwright
import os


def pytest_configure_node(node):
    """Configure pytest-playwright settings."""
    # Set default browser if not specified
    if not hasattr(node.config.option, 'browser_name'):
        node.config.option.browser_name = ['chromium']


# Playwright configuration
PLAYWRIGHT_CONFIG = {
    # Test directory
    "testDir": "gift_manager/tests/e2e",

    # Global test timeout (30 seconds)
    "timeout": 30000,

    # Expect timeout for assertions (5 seconds)
    "expect": {
        "timeout": 5000
    },

    # Fail the build on CI if you accidentally left test.only in the source code
    "forbidOnly": bool(os.environ.get("CI")),

    # Retry on CI only
    "retries": 2 if os.environ.get("CI") else 0,

    # Opt out of parallel tests on CI
    "workers": 1 if os.environ.get("CI") else None,

    # Reporter configuration
    "reporter": [
        ["html", {"outputFolder": "reports/playwright"}],
        ["junit", {"outputFile": "reports/playwright-results.xml"}],
        ["list"] if not os.environ.get("CI") else ["github"],
    ],

    # Shared settings for all projects
    "use": {
        # Base URL for tests
        "baseURL": "http://localhost:8000",

        # Browser context options
        "viewport": {"width": 1920, "height": 1080},
        "ignoreHTTPSErrors": True,
        "screenshot": "only-on-failure",
        "video": "retain-on-failure",
        "trace": "retain-on-failure",

        # Permissions
        "permissions": ["clipboard-read", "clipboard-write"],

        # Locale
        "locale": "en-US",
        "timezoneId": "America/New_York",
    },

    # Browser projects
    "projects": [
        {
            "name": "chromium",
            "use": {
                "browserName": "chromium",
                "channel": "chrome",  # Use Google Chrome if available
                "launchOptions": {
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                    ]
                }
            },
        },
        {
            "name": "firefox",
            "use": {
                "browserName": "firefox",
                "launchOptions": {
                    "firefoxUserPrefs": {
                        "dom.webnotifications.enabled": False,
                        "media.navigator.permission.disabled": True,
                    }
                }
            },
        },
        {
            "name": "webkit",
            "use": {
                "browserName": "webkit",
            },
        },
        # Mobile testing
        {
            "name": "mobile-chrome",
            "use": {
                "browserName": "chromium",
                "viewport": {"width": 375, "height": 667},
                "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "deviceScaleFactor": 2,
                "isMobile": True,
                "hasTouch": True,
            },
        },
        {
            "name": "mobile-safari",
            "use": {
                "browserName": "webkit",
                "viewport": {"width": 375, "height": 667},
                "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "deviceScaleFactor": 2,
                "isMobile": True,
                "hasTouch": True,
            },
        },
    ],

    # Output directories
    "outputDir": "test-results/",

    # Web server configuration for Django
    "webServer": {
        "command": "python manage.py runserver 8000",
        "port": 8000,
        "timeout": 120000,  # 2 minutes to start Django
        "reuseExistingServer": not os.environ.get("CI"),
        "env": {
            "DJANGO_SETTINGS_MODULE": "GiftManager.settings.testing",
            "DJANGO_ENV": "testing",
        }
    } if not os.environ.get("PYTEST_CURRENT_TEST") else None,  # Only when not running via pytest
}


def configure_playwright_for_pytest():
    """Configure Playwright settings for pytest integration."""
    return {
        # Browser launch options
        "browser_type_launch_args": {
            "headless": not os.environ.get("HEADED", False),
            "slow_mo": int(os.environ.get("SLOW_MO", 0)),
        },

        # Browser context options
        "browser_context_args": {
            "viewport": {"width": 1920, "height": 1080},
            "ignore_https_errors": True,
            "permissions": ["clipboard-read", "clipboard-write"],
            "locale": "en-US",
            "timezone_id": "America/New_York",
        },

        # Test configuration
        "device": None,  # Use custom viewport instead of device presets
    }


# Environment-specific configurations
if os.environ.get("CI"):
    # CI-specific settings
    PLAYWRIGHT_CONFIG["use"]["screenshot"] = "only-on-failure"
    PLAYWRIGHT_CONFIG["use"]["video"] = "retain-on-failure"
    PLAYWRIGHT_CONFIG["use"]["trace"] = "retain-on-failure"
    PLAYWRIGHT_CONFIG["workers"] = 1
    PLAYWRIGHT_CONFIG["retries"] = 2
else:
    # Local development settings
    PLAYWRIGHT_CONFIG["use"]["screenshot"] = "off"
    PLAYWRIGHT_CONFIG["use"]["video"] = "off"
    PLAYWRIGHT_CONFIG["use"]["trace"] = "off"
    PLAYWRIGHT_CONFIG["workers"] = None  # Use all available cores
    PLAYWRIGHT_CONFIG["retries"] = 0


# Export for pytest-playwright
def pytest_playwright_configure(config):
    """Configure pytest-playwright with our settings."""
    playwright_config = configure_playwright_for_pytest()

    # Apply configuration to pytest
    for key, value in playwright_config.items():
        setattr(config, key, value)
