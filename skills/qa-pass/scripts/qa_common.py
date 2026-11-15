# ruff: noqa: INP001, EM102, TRY003 - command-line QA scripts, not app code
"""Shared helpers for the QA pass scripts (run against the local Docker app)."""

import os
import re
import subprocess

import requests

WEB_CONTAINER = "gift-manager-web"  # container_name in docker-compose.yml


def _base_url() -> str:
    """Return QA_BASE_URL, else the host port Docker publishes for the web container.

    docker-compose.yml publishes ``${WEB_PORT:-8000}``, and WEB_PORT is set in a machine's
    ``.env`` (read by compose, not by this shell), so the port is asked from Docker.
    """
    if os.environ.get("QA_BASE_URL"):
        return os.environ["QA_BASE_URL"].rstrip("/")
    try:
        published = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            ["docker", "port", WEB_CONTAINER, "8000/tcp"],  # noqa: S607 - docker from PATH
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        published = ""
    # One line per address, such as "127.0.0.1:8001"; they share the port
    match = re.search(r":(\d+)$", published.strip().split("\n")[0])
    return f"http://localhost:{match.group(1) if match else 8000}"


BASE_URL = _base_url()

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
