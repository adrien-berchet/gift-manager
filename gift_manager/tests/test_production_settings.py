"""Regression tests for production settings fail-closed behavior."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _isolated_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "DJANGO_SETTINGS_MODULE",
        "DJANGO_ENV",
        "DJANGO_SECRET_KEY",
        "EMAIL_ENCRYPTION_KEY",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "EMAIL_HOST",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
    ):
        env.pop(key, None)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    return env


def _production_env() -> dict[str, str]:
    env = _isolated_env()
    env.update(
        {
            "DJANGO_ENV": "production",
            "DJANGO_SECRET_KEY": "test-production-secret-key-with-enough-entropy",
            "EMAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "DB_NAME": "gift_manager",
            "DB_USER": "gift_manager",
            "DB_PASSWORD": "gift_manager_password",
            "DB_HOST": "localhost",
            "EMAIL_HOST": "smtp.example.com",
            "DEFAULT_FROM_EMAIL": "noreply@example.com",
            "ALLOWED_HOSTS": "example.com",
            "CSRF_TRUSTED_ORIGINS": "https://example.com",
        }
    )
    return env


def _run_python(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and script for settings isolation.
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_settings_import(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run_python("import GiftManager.settings", env)


def test_required_env_variable_rejects_blank(monkeypatch):
    """Required settings should treat blank strings as missing."""
    from GiftManager.settings.base import get_env_variable

    monkeypatch.setenv("REQUIRED_SETTING", " ")

    with pytest.raises(ImproperlyConfigured):
        get_env_variable("REQUIRED_SETTING", required=True)


def test_unknown_django_env_fails_closed():
    """Unknown DJANGO_ENV values should not silently load development settings."""
    env = _isolated_env()
    env["DJANGO_ENV"] = "prodution"

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "DJANGO_ENV must be one of" in result.stderr


def test_missing_django_env_fails_closed():
    """Missing DJANGO_ENV should not silently load development settings."""
    result = _run_settings_import(_isolated_env())

    assert result.returncode != 0
    assert "DJANGO_ENV is required" in result.stderr


@pytest.mark.parametrize(
    "setting_name",
    [
        "DJANGO_SECRET_KEY",
        "EMAIL_ENCRYPTION_KEY",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "EMAIL_HOST",
        "DEFAULT_FROM_EMAIL",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
    ],
)
def test_production_settings_reject_blank_required_values(setting_name):
    """Production imports should fail before startup with blank critical settings."""
    env = _production_env()
    env[setting_name] = " "

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert setting_name in result.stderr


@pytest.mark.parametrize("setting_name", ["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"])
def test_production_settings_reject_empty_required_csv_values(setting_name):
    """CSV settings should parse to at least one usable value."""
    env = _production_env()
    env[setting_name] = ", ,"

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert f"{setting_name} environment variable must contain at least one value" in result.stderr


def test_production_settings_reject_invalid_email_encryption_key():
    """Production should validate EMAIL_ENCRYPTION_KEY as a Fernet key."""
    env = _production_env()
    env["EMAIL_ENCRYPTION_KEY"] = "not-a-valid-fernet-key"

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "EMAIL_ENCRYPTION_KEY must be a valid Fernet key" in result.stderr


def test_production_settings_valid_environment_imports():
    """A complete production environment should import successfully."""
    result = _run_settings_import(_production_env())

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_explicit_testing_settings_module_imports_without_django_env():
    """Explicit settings modules should not require package-level DJANGO_ENV dispatch."""
    env = _isolated_env()
    env["DJANGO_SETTINGS_MODULE"] = "GiftManager.settings.testing"

    result = _run_python(
        "import django; django.setup(); "
        "from django.conf import settings; assert settings.TESTING is True",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_explicit_production_settings_module_imports_without_django_env():
    """Explicit production settings should validate production vars without DJANGO_ENV."""
    env = _production_env()
    env.pop("DJANGO_ENV")
    env["DJANGO_SETTINGS_MODULE"] = "GiftManager.settings.production"

    result = _run_python(
        "import django; django.setup(); "
        "from django.conf import settings; assert settings.DEBUG is False",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_production_compose_requires_critical_environment_values():
    """Production Compose should fail before interpolating blank secrets."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()

    for setting_name in (
        "DJANGO_SECRET_KEY",
        "EMAIL_ENCRYPTION_KEY",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "REDIS_PASSWORD",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "EMAIL_HOST",
        "DEFAULT_FROM_EMAIL",
    ):
        assert f"${{{setting_name}:?" in compose
    assert "DB_SSLMODE=${DB_SSLMODE:-prefer}" in compose
    assert "static_volume:/app/staticfiles\n" in compose


def test_settings_modules_have_no_import_time_prints():
    """Settings imports should not print operational details."""
    for settings_path in (PROJECT_ROOT / "GiftManager/settings").glob("*.py"):
        tree = ast.parse(settings_path.read_text())
        print_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
        assert not print_calls, settings_path.name
