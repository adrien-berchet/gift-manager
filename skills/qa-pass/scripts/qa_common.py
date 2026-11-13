# ruff: noqa: INP001, EM102, TRY003 - command-line QA scripts, not app code
"""Shared helpers for the QA pass scripts (run against the local Docker app)."""

import os
import re

import requests

BASE_URL = os.environ.get("QA_BASE_URL", "http://localhost:8001").rstrip("/")

# Seed accounts (`manage.py seed_data`); override with QA_PASSWORD_<USERNAME>
DEFAULT_PASSWORDS = {"alice": "alice_password", "bob": "bob_password", "testuser": "testpass123"}
SUPERUSERS = {"testuser"}  # bypasses most permission checks: never use for access tests

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def password_for(username: str) -> str:
    return os.environ.get(f"QA_PASSWORD_{username.upper()}", DEFAULT_PASSWORDS.get(username, ""))


def login(username: str) -> requests.Session:
    """Return a requests session logged in as ``username`` through the allauth form."""
    session = requests.Session()
    page = session.get(f"{BASE_URL}/accounts/login/", timeout=30)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
    session.post(
        f"{BASE_URL}/accounts/login/",
        data={
            "csrfmiddlewaretoken": token,
            "login": username,
            "password": password_for(username),
        },
        headers={"Referer": f"{BASE_URL}/accounts/login/"},
        timeout=30,
    )
    if "sessionid" not in session.cookies:
        raise SystemExit(f"Login failed for {username!r} (wrong password or app not running)")
    return session


def visible_text(html: str) -> str:
    """Strip scripts, styles, comments and the debug toolbar from a page."""
    html = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", html, flags=re.DOTALL)
    return re.sub(r'<div id="djDebug".*', "", html, flags=re.DOTALL)
