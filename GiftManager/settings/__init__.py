"""Django settings package for GiftManager project.

This module automatically imports the appropriate settings based on the
DJANGO_ENV environment variable:
- 'production' -> production.py
- 'testing' -> testing.py
- default -> development.py

Usage:
    Set DJANGO_ENV environment variable before running Django:
    $ export DJANGO_ENV=production
    $ python manage.py runserver
"""

import os

env = os.environ.get("DJANGO_ENV", "development")

if env == "production":
    from .production import *  # noqa: F403
elif env == "testing":
    from .testing import *  # noqa: F403
else:
    from .development import *  # noqa: F403
