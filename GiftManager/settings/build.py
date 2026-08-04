"""Build-time settings for static asset collection.

These settings are only for commands such as ``collectstatic`` during hosting
builds. Runtime deployments must use ``GiftManager.settings.production`` with
the required production environment variables.
"""

from .base import *  # noqa: F403

SECRET_KEY = "build-time-secret-key-not-used-at-runtime"  # noqa: S105
DEBUG = False
ALLOWED_HOSTS = ["localhost"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "build@example.invalid"
EMAIL_ENCRYPTION_KEY = "THIS-IS-NOT-A-SECURE-KEY-FOR-BUILD-ONLY--="

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "build-cache",
    }
}
