"""Base Django settings for GiftManager project.

This module contains settings common to all environments.
Environment-specific settings should override these in their respective modules.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv()


def get_env_variable(var_name: str, default: str | None = None, *, required: bool = False) -> str:
    """Get an environment variable or raise an exception if required and not set.

    Args:
        var_name: The name of the environment variable.
        default: Default value if not set (ignored if required=True).
        required: If True, raises ImproperlyConfigured when variable is not set.

    Returns:
        The value of the environment variable.

    Raises:
        ImproperlyConfigured: If required=True and variable is not set.
    """
    value = os.environ.get(var_name, default)
    if required and value is None:
        msg = f"The {var_name} environment variable is required but not set."
        raise ImproperlyConfigured(msg)
    return value


def get_bool_env(var_name: str, *, default: bool = False) -> bool:
    """Get a boolean environment variable.

    Args:
        var_name: The name of the environment variable.
        default: Default value if not set.

    Returns:
        True if the value is 'true', '1', or 'yes' (case-insensitive).
    """
    value = os.environ.get(var_name, str(default)).lower()
    return value in ("true", "1", "yes")


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "gift_manager",
    "modeltranslation",
    "allauth",
    "allauth.account",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "GiftManager.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "gift_manager" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "GiftManager.wsgi.app"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env_variable("DB_NAME", "gift_manager"),
        "USER": get_env_variable("DB_USER", ""),
        "PASSWORD": get_env_variable("DB_PASSWORD", ""),
        "HOST": get_env_variable("DB_HOST", "localhost"),
        "PORT": get_env_variable("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,  # Persistent connections
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 10,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Allauth configuration
ACCOUNT_SIGNUP_FIELDS = ["email*", "email2*", "username*", "password1*", "password2*"]
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_RATE_LIMITS = {
    # Limit login attempts
    "login_failed": "5/5m",
}

# Invitation settings
INVITATION_EXPIRY_DAYS = 7


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/
LANGUAGES = [
    ("en", gettext_lazy("English")),
    ("fr", gettext_lazy("French")),
]

LANGUAGE_CODE = "en-us"

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

TIME_ZONE = "Europe/Paris"

USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/
STATIC_URL = "/staticfiles/"
STATICFILES_DIRS = [
    BASE_DIR / "gift_manager" / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files (Uploaded files)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Site ID configuration
SITE_ID = 1


# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "json": {
            "format": (
                '{"level": "%(levelname)s",'
                ' "time": "%(asctime)s",'
                ' "module": "%(module)s",'
                ' "message": "%(message)s"}'
            ),
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "gift_manager": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
