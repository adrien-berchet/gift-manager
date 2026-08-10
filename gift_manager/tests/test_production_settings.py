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
        "VERCEL",
        "VERCEL_ENV",
        "VERCEL_URL",
        "VERCEL_BRANCH_URL",
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


@pytest.mark.parametrize(
    "allowed_hosts",
    [
        "*",
        ".vercel.app",
        "*.vercel.app",
        "https://example.com",
        "example.com:443",
        "example.com/path",
    ],
)
def test_production_settings_reject_broad_allowed_hosts(allowed_hosts):
    """Production host validation should only accept exact hostnames."""
    env = _production_env()
    env["ALLOWED_HOSTS"] = allowed_hosts

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "ALLOWED_HOSTS" in result.stderr


@pytest.mark.parametrize(
    "csrf_origin",
    [
        "http://example.com",
        "https://*.vercel.app",
        "https://other.example.com",
        "https://example.com/path",
        "https://example.com?next=/",
    ],
)
def test_production_settings_reject_broad_csrf_origins(csrf_origin):
    """Production CSRF origins should be exact HTTPS origins for allowed hosts."""
    env = _production_env()
    env["ALLOWED_HOSTS"] = "example.com"
    env["CSRF_TRUSTED_ORIGINS"] = csrf_origin

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "CSRF_TRUSTED_ORIGINS" in result.stderr


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


def test_vercel_preview_host_is_added_to_hosts_and_csrf_origins():
    """Vercel previews should trust only the exact generated preview host."""
    env = _production_env()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-pr-123-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'example.com', 'gift-manager-pr-123-adrien.vercel.app'"
        "]; "
        "assert settings.CSRF_TRUSTED_ORIGINS == ["
        "'https://example.com', 'https://gift-manager-pr-123-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_branch_url_is_added_alongside_deployment_url():
    """Reviewers reaching a preview via its stable branch alias should be trusted too."""
    env = _production_env()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-abc123-adrien.vercel.app",
            "VERCEL_BRANCH_URL": "gift-manager-git-my-branch-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'example.com', "
        "'gift-manager-abc123-adrien.vercel.app', "
        "'gift-manager-git-my-branch-adrien.vercel.app'"
        "]; "
        "assert settings.CSRF_TRUSTED_ORIGINS == ["
        "'https://example.com', "
        "'https://gift-manager-abc123-adrien.vercel.app', "
        "'https://gift-manager-git-my-branch-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_branch_url_is_optional():
    """Previews should still work when the branch alias variable is absent."""
    env = _production_env()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-abc123-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'example.com', 'gift-manager-abc123-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_branch_url_duplicate_of_deployment_url_is_not_repeated():
    """A branch alias identical to the deployment host should not create duplicates."""
    env = _production_env()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-abc123-adrien.vercel.app",
            "VERCEL_BRANCH_URL": "gift-manager-abc123-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'example.com', 'gift-manager-abc123-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_preview_host_can_supply_hosts_when_runtime_host_env_is_unset():
    """Vercel previews should not need per-PR host variables."""
    env = _production_env()
    env.pop("ALLOWED_HOSTS")
    env.pop("CSRF_TRUSTED_ORIGINS")
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-pr-456-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'gift-manager-pr-456-adrien.vercel.app'"
        "]; "
        "assert settings.CSRF_TRUSTED_ORIGINS == ["
        "'https://gift-manager-pr-456-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_preview_ignores_inherited_csrf_env_when_allowed_hosts_is_unset():
    """Preview deploys should not fail on production CSRF origins inherited from Vercel env."""
    env = _production_env()
    env.pop("ALLOWED_HOSTS")
    env["CSRF_TRUSTED_ORIGINS"] = "https://production.example.com"
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-pr-789-adrien.vercel.app",
        }
    )

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ["
        "'gift-manager-pr-789-adrien.vercel.app'"
        "]; "
        "assert settings.CSRF_TRUSTED_ORIGINS == ["
        "'https://gift-manager-pr-789-adrien.vercel.app'"
        "]",
        env,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_preview_keeps_strict_csrf_matching_when_allowed_hosts_is_set():
    """Explicit preview host config should still fail closed on CSRF host mismatches."""
    env = _production_env()
    env["ALLOWED_HOSTS"] = "preview.example.com"
    env["CSRF_TRUSTED_ORIGINS"] = "https://production.example.com"
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "gift-manager-pr-999-adrien.vercel.app",
        }
    )

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "CSRF_TRUSTED_ORIGINS hosts must be present in ALLOWED_HOSTS" in result.stderr


@pytest.mark.parametrize(
    "vercel_flags",
    [
        {"VERCEL": "1", "VERCEL_ENV": "production"},
        {"VERCEL_ENV": "preview"},
    ],
)
def test_vercel_url_is_only_added_for_vercel_preview_deployments(vercel_flags):
    """Production and non-Vercel deploys should not inherit preview hosts."""
    env = _production_env()
    env.update(vercel_flags)
    env["VERCEL_URL"] = "gift-manager-production.vercel.app"

    result = _run_python(
        "import GiftManager.settings as settings; "
        "assert settings.ALLOWED_HOSTS == ['example.com']; "
        "assert settings.CSRF_TRUSTED_ORIGINS == ['https://example.com']",
        env,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("vercel_url", [None, "", " "])
def test_vercel_preview_requires_system_preview_url(vercel_url):
    """Vercel previews should fail clearly if the exact preview host is absent."""
    env = _production_env()
    env.update({"VERCEL": "1", "VERCEL_ENV": "preview"})
    if vercel_url is None:
        env.pop("VERCEL_URL", None)
    else:
        env["VERCEL_URL"] = vercel_url

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "VERCEL_URL must be set" in result.stderr


@pytest.mark.parametrize(
    "vercel_url",
    [
        "*.vercel.app",
        ".vercel.app",
        "https://preview.vercel.app",
        "preview.vercel.app/path",
        "preview.vercel.app:443",
        "evil.com,example.com",
        "preview.vercel.app example.com",
    ],
)
def test_vercel_preview_url_must_be_an_exact_hostname(vercel_url):
    """Vercel preview support should not relax exact-host validation."""
    env = _production_env()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": vercel_url,
        }
    )

    result = _run_settings_import(env)

    assert result.returncode != 0
    assert "ALLOWED_HOSTS" in result.stderr


def test_production_settings_define_content_security_policy():
    """Production should expose an enforced CSP for app responses."""
    script = (
        "import GiftManager.settings as settings; "
        "policy = settings.CONTENT_SECURITY_POLICY; "
        "assert \"default-src 'self'\" in policy; "
        "assert 'https://cdn.jsdelivr.net' in policy; "
        "assert 'code.jquery.com' not in policy; "
        "assert 'unpkg.com' not in policy; "
        "assert \"object-src 'none'\" in policy; "
        "assert \"frame-ancestors 'none'\" in policy"
    )

    result = _run_python(script, _production_env())

    assert result.returncode == 0, result.stderr


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


def test_explicit_build_settings_module_imports_without_runtime_env():
    """Static build settings should not require production runtime variables."""
    env = _isolated_env()
    env["DJANGO_SETTINGS_MODULE"] = "GiftManager.settings.build"

    result = _run_python(
        "import django; django.setup(); "
        "from django.conf import settings; "
        "assert settings.DEBUG is False; "
        "assert settings.ALLOWED_HOSTS == ['localhost']; "
        "assert settings.STATIC_ROOT.name == 'staticfiles'",
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
    assert "DB_SSLMODE=${DB_SSLMODE:-disable}" in compose
    assert "static_volume:/app/staticfiles\n" in compose


def test_production_compose_keeps_web_internal_and_migrations_explicit():
    """Production web startup should not publish dev ports or mutate the schema."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    web_section = compose.split("  web:", maxsplit=1)[1].split("  nginx:", maxsplit=1)[0]

    assert "ports: !override []" in web_section
    assert 'expose:\n      - "8000"' in web_section
    assert "static_volume:/app/staticfiles:ro" in web_section
    assert "python manage.py migrate" not in web_section
    assert "python manage.py collectstatic" not in web_section
    assert "collectstatic:" in web_section
    assert "  migrate:" in compose
    assert 'profiles: ["release"]' in compose
    assert "scripts/pre_migration_snapshot.sh" in compose
    assert "--profile release run --rm migrate" in compose


def test_production_nginx_rejects_unknown_hosts_and_uses_exact_names():
    """Nginx should reject unknown hosts and only serve configured hostnames."""
    nginx = (PROJECT_ROOT / "nginx.conf").read_text()
    health_location = nginx.split("location /health/ {", maxsplit=1)[1].split("}", maxsplit=1)[0]

    assert "listen 80 default_server;" in nginx
    assert "listen 443 ssl http2 default_server;" in nginx
    assert "return 444;" in nginx
    assert "server_name ${NGINX_SERVER_NAME};" in nginx
    assert "https://${NGINX_CANONICAL_HOST}$request_uri" in nginx
    assert "https://$host$request_uri" not in nginx
    assert "proxy_set_header Host $host;" in health_location
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in health_location
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in health_location


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
