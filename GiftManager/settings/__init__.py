"""Django settings package for GiftManager project.

This module automatically imports the appropriate settings based on the
DJANGO_ENV environment variable:
- 'production' -> production.py
- 'testing' -> testing.py

Usage:
    Set DJANGO_ENV environment variable before running Django:
    $ export DJANGO_ENV=production
    $ python manage.py runserver
"""

import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")

if settings_module in (None, __name__):
    load_dotenv()
    raw_env = os.environ.get("DJANGO_ENV")

    if raw_env is None or not raw_env.strip():
        msg = "DJANGO_ENV is required and must be one of: development, testing, production."
        raise ImproperlyConfigured(msg)

    env = raw_env.strip().lower()

    if env == "production":
        from .production import *  # noqa: F403
    elif env == "testing":
        from .testing import *  # noqa: F403
    elif env == "development":
        from .development import *  # noqa: F403
    else:
        msg = "DJANGO_ENV must be one of: development, testing, production."
        raise ImproperlyConfigured(msg)
