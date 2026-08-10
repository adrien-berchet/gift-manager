"""Production settings for GiftManager project.

This module contains security-hardened settings for production deployment.
All sensitive values MUST be set via environment variables.
"""

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import get_bool_env
from .base import get_env_variable


def get_csv_env(var_name: str, *, required: bool) -> list[str]:
    """Return values from a comma-separated environment variable."""
    values = [
        value.strip() for value in get_env_variable(var_name, "", required=required).split(",")
    ]
    values = [value for value in values if value]
    if required and not values:
        msg = f"The {var_name} environment variable must contain at least one value."
        raise ImproperlyConfigured(msg)
    return values


def get_required_csv_env(var_name: str) -> list[str]:
    """Return a non-empty comma-separated environment variable."""
    return get_csv_env(var_name, required=True)


def has_env_value(var_name: str) -> bool:
    """Return whether an environment variable contains a non-blank value."""
    return bool(os.environ.get(var_name, "").strip())


def validate_allowed_hosts(hosts: list[str]) -> list[str]:
    """Require exact hostnames for production host validation."""
    for host in hosts:
        if not host or "," in host or any(character.isspace() for character in host):
            msg = "ALLOWED_HOSTS values must be exact non-empty hostnames."
            raise ImproperlyConfigured(msg)
        if host == "*" or host.startswith(".") or "*" in host:
            msg = "ALLOWED_HOSTS must contain exact hostnames; wildcards are not allowed."
            raise ImproperlyConfigured(msg)
        if "://" in host or "/" in host or ":" in host:
            msg = "ALLOWED_HOSTS values must be hostnames only, without schemes, ports, or paths."
            raise ImproperlyConfigured(msg)
    return hosts


def validate_csrf_origins(origins: list[str], allowed_hosts: list[str]) -> list[str]:
    """Require exact HTTPS CSRF origins that match allowed production hosts."""
    allowed_host_set = {host.lower() for host in allowed_hosts}
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.hostname:
            msg = "CSRF_TRUSTED_ORIGINS must contain exact https:// origins."
            raise ImproperlyConfigured(msg)
        if "*" in parsed.hostname:
            msg = "CSRF_TRUSTED_ORIGINS must not contain wildcard hosts."
            raise ImproperlyConfigured(msg)
        if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
            msg = "CSRF_TRUSTED_ORIGINS must not include paths, queries, or fragments."
            raise ImproperlyConfigured(msg)
        if parsed.hostname.lower() not in allowed_host_set:
            msg = "CSRF_TRUSTED_ORIGINS hosts must be present in ALLOWED_HOSTS."
            raise ImproperlyConfigured(msg)
    return origins


def get_vercel_preview_hosts() -> list[str]:
    """Return Vercel's exact generated preview hostnames when available.

    Vercel serves each preview deployment on its own unique deployment host
    (``VERCEL_URL``) as well as a stable per-branch alias host
    (``VERCEL_BRANCH_URL``, e.g. the URL linked from PR checks). Both are
    exact, Vercel-controlled hostnames, so trusting both keeps ALLOWED_HOSTS
    wildcard-free while covering how reviewers actually reach a preview.
    """
    if os.environ.get("VERCEL") != "1":
        return []
    if os.environ.get("VERCEL_ENV", "").strip().lower() != "preview":
        return []
    deployment_host = os.environ.get("VERCEL_URL", "").strip()
    if not deployment_host:
        msg = (
            "VERCEL_URL must be set for Vercel preview deployments. "
            "Enable Vercel system environment variables for this project."
        )
        raise ImproperlyConfigured(msg)
    branch_host = os.environ.get("VERCEL_BRANCH_URL", "").strip()
    hosts = [deployment_host]
    if branch_host and branch_host not in hosts:
        hosts.append(branch_host)
    return hosts


def include_vercel_preview_hosts(hosts: list[str], preview_hosts: list[str]) -> list[str]:
    """Add Vercel's exact preview hosts without allowing wildcard preview hosts."""
    result = list(hosts)
    for preview_host in preview_hosts:
        if preview_host not in result:
            result.append(preview_host)
    return result


def include_vercel_preview_origins(origins: list[str], preview_hosts: list[str]) -> list[str]:
    """Add Vercel's exact preview HTTPS origins for CSRF validation."""
    result = list(origins)
    for preview_host in preview_hosts:
        preview_origin = f"https://{preview_host}"
        if preview_origin not in result:
            result.append(preview_origin)
    return result


# SECURITY: Secret key must be set in production
SECRET_KEY = get_env_variable("DJANGO_SECRET_KEY", required=True)

# SECURITY: Never run with debug in production
DEBUG = False

# Allowed hosts - configure based on your domain
VERCEL_PREVIEW_HOSTS = get_vercel_preview_hosts()
ALLOWED_HOSTS_ENV_CONFIGURED = has_env_value("ALLOWED_HOSTS")
ALLOWED_HOSTS = validate_allowed_hosts(
    include_vercel_preview_hosts(
        get_csv_env("ALLOWED_HOSTS", required=not VERCEL_PREVIEW_HOSTS),
        VERCEL_PREVIEW_HOSTS,
    )
)

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
CSRF_ENV_REQUIRED = not VERCEL_PREVIEW_HOSTS
CSRF_ENV_USABLE = CSRF_ENV_REQUIRED or ALLOWED_HOSTS_ENV_CONFIGURED
CSRF_TRUSTED_ORIGINS = validate_csrf_origins(
    include_vercel_preview_origins(
        get_csv_env("CSRF_TRUSTED_ORIGINS", required=CSRF_ENV_REQUIRED) if CSRF_ENV_USABLE else [],
        VERCEL_PREVIEW_HOSTS,
    ),
    ALLOWED_HOSTS,
)

# Content security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
    "https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "upgrade-insecure-requests"
)

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
