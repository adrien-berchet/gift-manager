"""Testing settings for GiftManager project.

This module contains settings optimized for running tests.
These settings prioritize speed and isolation over security.
"""

from .base import *  # noqa: F403

# Use a simple secret key for testing
SECRET_KEY = "testing-secret-key-not-for-production"

# Enable debug for better error messages in tests
DEBUG = False  # Keep False for realistic testing

ALLOWED_HOSTS = ["*"]

# Use a fast password hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use SQLite for faster tests
# For live_server tests, use a real file (not in-memory) so it's visible across threads
# The file will be created/destroyed automatically by Django's test runner
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Use a temporary file instead of memory for live_server compatibility
        "NAME": "/tmp/test_gift_manager.db",
        "TEST": {
            "NAME": "/tmp/test_gift_manager.db",
        },
    }
}

# Use in-memory email backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

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

# Disable migrations for faster test setup (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()

# Minimal logging during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
        "level": "CRITICAL",
    },
    "loggers": {
        "django": {
            "handlers": ["null"],
            "level": "CRITICAL",
            "propagate": False,
        },
        "gift_manager": {
            "handlers": ["null"],
            "level": "CRITICAL",
            "propagate": False,
        },
    },
}

# Speed up file handling in tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.InMemoryStorage"

# Celery eager mode for testing (if using Celery)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
