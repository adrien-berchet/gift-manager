"""Development settings for GiftManager project.

This module contains settings for local development.
DO NOT use these settings in production.
"""

from dotenv import load_dotenv

from .base import *  # noqa: F401, F403
from .base import BASE_DIR
from .base import INSTALLED_APPS
from .base import MIDDLEWARE

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
# In development, we use a default key for convenience
SECRET_KEY = "dev-secret-key-do-not-use-in-production-change-me-immediately"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
INTERNAL_IPS = ["127.0.0.1"]

# Development-specific apps
INSTALLED_APPS = [
    "debug_toolbar",
    *INSTALLED_APPS,
]

# Add debug toolbar middleware
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE,
]

# Database for development
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "gift_manager_dev",
        "USER": "dev_user",
        "PASSWORD": "dev_password",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# Email backend for development - prints to console
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable security features in development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Cache settings for development
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# Debug Toolbar settings
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}

# Logging - more verbose in development
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
        "level": "DEBUG",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",  # Set to DEBUG to see SQL queries
            "propagate": False,
        },
        "gift_manager": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
