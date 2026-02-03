"""Testing settings for GiftManager project.

This module contains settings optimized for running tests.
These settings prioritize speed and isolation over security.

Database selection:
- If DB_* environment variables are set: Uses PostgreSQL (for CI and full compatibility)
- Otherwise: Falls back to SQLite (for quick local testing, but some features may not work)
"""

import os
import tempfile

from .base import *  # noqa: F403

print("#########################")
print("USING TESTING ENVIRONMENT")
print("#########################")

# Flag to indicate we're in testing mode
TESTING = True

# Use a simple secret key for testing
SECRET_KEY = "testing-secret-key-not-for-production"

# Enable debug for better error messages in tests
DEBUG = True  # Keep False for realistic testing

ALLOWED_HOSTS = ["*"]

# Use a fast password hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


def _get_test_database_config() -> dict:
    """Get database configuration for tests.

    Returns PostgreSQL config if DB_* env vars are set, otherwise SQLite.
    """
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_host = os.environ.get("DB_HOST")

    # If PostgreSQL environment variables are set, use PostgreSQL
    if all([db_name, db_user, db_password, db_host]):
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": db_name,
                "USER": db_user,
                "PASSWORD": db_password,
                "HOST": db_host,
                "PORT": os.environ.get("DB_PORT", "5432"),
                "TEST": {
                    "NAME": f"test_{db_name}",
                },
            }
        }

    # Otherwise, fall back to SQLite for quick local testing
    # Note: Some PostgreSQL-specific features (JSONB) won't work with SQLite
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    temp_db.close()
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": temp_db.name,
            "OPTIONS": {
                # Enable shared cache for SQLite to allow multiple connections
                # This is crucial for Playwright tests with live_server
                "init_command": "PRAGMA cache=shared;",
            },
            "TEST": {
                "NAME": temp_db.name,
            },
        }
    }


DATABASES = _get_test_database_config()

print("#########################")
print("USING DB:", DATABASES.get("default", {}).get("NAME", "# UNKNOWN #"))
print("#########################")

# Use in-memory email backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_ENCRYPTION_KEY = "THIS-IS-NOT-A-SECURE-KEY-FOR-TESTING-ONLY--="

# Use local memory cache for testing
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# Use non-manifest storage in tests so collectstatic isn't required
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Disable security features that slow down tests
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Disable allauth rate limits for testing
# Set very high limits that won't be reached during testing
ACCOUNT_RATE_LIMITS = {
    "login": "1000/m",  # 1000 login attempts per minute
    "login_failed": "1000/m",  # 1000 failed login attempts per minute
    "signup": "1000/m",
    "add_email": "1000/m",
    "confirm_email": "1000/m",
    "reset_password": "1000/m",
    "reset_password_from_key": "1000/m",
    "change_password": "1000/m",
    "manage_email": "1000/m",
}

# Disable any other potential rate limiting
RATELIMIT_ENABLE = False

# Enable email verification for testing authentication flows
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

# Disable migrations for faster test setup (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()

# Logging during tests - show errors for debugging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "gift_manager": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# Speed up file handling in tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.InMemoryStorage"

# Celery eager mode for testing (if using Celery)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
