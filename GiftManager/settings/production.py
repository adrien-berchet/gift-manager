"""Production settings for GiftManager project.

This module contains security-hardened settings for production deployment.
All sensitive values MUST be set via environment variables.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import get_bool_env
from .base import get_env_variable


def get_required_csv_env(var_name: str) -> list[str]:
    """Return a non-empty comma-separated environment variable."""
    values = [value.strip() for value in get_env_variable(var_name, required=True).split(",")]
    values = [value for value in values if value]
    if not values:
        msg = f"The {var_name} environment variable must contain at least one value."
        raise ImproperlyConfigured(msg)
    return values


# SECURITY: Secret key must be set in production
SECRET_KEY = get_env_variable("DJANGO_SECRET_KEY", required=True)

# SECURITY: Never run with debug in production
DEBUG = False

# Allowed hosts - configure based on your domain
ALLOWED_HOSTS = get_required_csv_env("ALLOWED_HOSTS")

EMAIL_ENCRYPTION_KEY = get_env_variable("EMAIL_ENCRYPTION_KEY", required=True)

try:
    from cryptography.fernet import Fernet

    Fernet(EMAIL_ENCRYPTION_KEY.encode())
except (ImportError, ValueError) as exc:
    msg = "EMAIL_ENCRYPTION_KEY must be a valid Fernet key."
    raise ImproperlyConfigured(msg) from exc

# Database configuration from environment
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env_variable("DB_NAME", required=True),
        "USER": get_env_variable("DB_USER", required=True),
        "PASSWORD": get_env_variable("DB_PASSWORD", required=True),
        "HOST": get_env_variable("DB_HOST", required=True),
        "PORT": get_env_variable("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
            "sslmode": get_env_variable("DB_SSLMODE", "require"),
        },
    }
}

# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# HTTPS/SSL Settings
SECURE_SSL_REDIRECT = get_bool_env("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 1209600  # 2 weeks

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = get_required_csv_env("CSRF_TRUSTED_ORIGINS")

# Content security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# Referrer policy
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = get_env_variable("EMAIL_HOST", required=True)
EMAIL_PORT = int(get_env_variable("EMAIL_PORT", "587"))
EMAIL_USE_TLS = get_bool_env("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = get_bool_env("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = get_env_variable("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = get_env_variable("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = get_env_variable("DEFAULT_FROM_EMAIL", required=True)
SERVER_EMAIL = get_env_variable("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Admin emails for error notifications
ADMINS = [
    (name.strip(), email.strip())
    for admin in get_env_variable("DJANGO_ADMINS", "").split(";")
    if admin.strip()
    for name, email in [admin.split(":")]
]

# =============================================================================
# CACHING
# =============================================================================

REDIS_URL = get_env_variable("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
    # Use Redis for sessions in production
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL = get_env_variable("LOG_LEVEL", "WARNING")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": (
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "module": "%(module)s", "message": "%(message)s"}'
            ),
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
        "gift_manager": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# =============================================================================
# SENTRY ERROR TRACKING (Optional)
# =============================================================================

SENTRY_DSN = get_env_variable("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
            ),
            LoggingIntegration(
                level=None,  # Capture all logs
                event_level=None,  # Don't send logs as events (use breadcrumbs)
            ),
        ],
        traces_sample_rate=float(get_env_variable("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(get_env_variable("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment=get_env_variable("SENTRY_ENVIRONMENT", "production"),
    )
