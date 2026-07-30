"""Regression tests for deployment and operations hardening."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_build_script_does_not_mutate_database_state():
    """Builds should not create or apply migrations."""
    build_script = (PROJECT_ROOT / "build.sh").read_text()

    assert "uv sync --frozen --no-dev" in build_script
    assert "DJANGO_SETTINGS_MODULE=GiftManager.settings.build" in build_script
    assert "collectstatic" in build_script
    assert "makemigrations" not in build_script
    assert "manage.py migrate" not in build_script


def test_ci_security_scans_are_blocking_and_locked():
    """Security jobs should fail CI on high-severity findings or vulnerable deps."""
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text()

    assert "uv sync --frozen --extra test" in ci
    assert "uv run --frozen bandit" in ci
    assert "--severity-level high" in ci
    assert "uv run --frozen pip-audit" in ci
    assert "--no-deps --disable-pip" in ci
    assert "makemigrations --check --dry-run" in ci
    assert "python manage.py check --deploy --fail-level WARNING" in ci
    assert "uqevclFMYjSZMFLOrZFDGwiIjQHKTUKDb7S6uFRumpQ=" in ci
    assert "opmn+^k8y5sqp^1*ni2irm8#rr2htl$6#=6f_al-q%8miorik5" in ci
    assert "docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet" in ci
    assert "|| true" not in ci
    assert 'pip install -e ".[test]"' not in ci


def test_e2e_workflow_uses_frozen_uv_environment():
    """Browser test workflows should use the same locked dependency set as CI."""
    workflow = (PROJECT_ROOT / ".github/workflows/e2e-tests.yml").read_text()

    assert "uv sync --frozen --extra test" in workflow
    assert "uv run --frozen pytest" in workflow
    assert "uv run --frozen python manage.py migrate" in workflow
    assert "pip install -e .[test]" not in workflow


def test_dockerignore_excludes_local_secrets_reports_and_backups():
    """Docker build context should not include local secret or tool artifacts."""
    patterns = {
        line.strip()
        for line in (PROJECT_ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    for pattern in (
        ".env*",
        "**/.env*",
        "*.pem",
        "*.key",
        "*.crt",
        "certs/",
        "deploy",
        ".agents",
        ".codex",
        ".vercel/",
        "bandit-report.json",
        "pip-audit-report.json",
        "playwright-report/",
        "*.dump",
        "*.sql",
        "*.gpg",
        "*.backup",
    ):
        assert pattern in patterns


def test_main_template_uses_pinned_runtime_cdns():
    """Remaining external runtime assets should be versioned for CSP/SRI follow-up."""
    template = (PROJECT_ROOT / "gift_manager/templates/gift_manager/base.html").read_text()

    assert "https://code.jquery.com" not in template
    assert "https://unpkg.com" not in template
    for url in (
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/",
        "https://cdn.jsdelivr.net/npm/htmx.org@1.9.10/",
        "https://cdn.jsdelivr.net/npm/gridjs@6.2.0/",
        "https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/",
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/",
    ):
        assert url in template


def test_backup_scripts_have_required_safety_controls():
    """Backup and restore scripts should enforce encryption and destructive restore gates."""
    backup = (PROJECT_ROOT / "scripts/postgres_backup.sh").read_text()
    restore = (PROJECT_ROOT / "scripts/postgres_restore.sh").read_text()
    media = (PROJECT_ROOT / "scripts/media_backup.sh").read_text()
    snapshot = (PROJECT_ROOT / "scripts/pre_migration_snapshot.sh").read_text()
    runbook = (PROJECT_ROOT / "docs/operations/backup-restore.md").read_text()

    assert "pg_dump" in backup
    assert "--format=custom" in backup
    assert "BACKUP_AGE_RECIPIENT" in backup
    assert "BACKUP_GPG_RECIPIENT" in backup
    assert "BACKUP_PASSPHRASE" in backup
    assert "BACKUP_UPLOAD_CMD" in backup
    assert "BACKUP_MONITOR_SUCCESS_URL" in backup
    assert 'sha256sum "$(basename "${encrypted_backup}")"' in backup
    assert "pg_restore" in restore
    assert "BACKUP_AGE_IDENTITY_FILE" in restore
    assert "sha256sum --check" in restore
    assert 'basename "${candidate}"' in restore
    assert "ALLOW_DESTRUCTIVE_RESTORE" in restore
    assert "tar -czf" in media
    assert "Media backup is enabled, but media directory does not exist" in media
    assert 'sha256sum "$(basename "${encrypted_backup}")"' in media
    assert "BACKUP_MONITOR_FAILURE_URL" in media
    assert "BACKUP_MONITOR_SUCCESS_URL" in media
    assert 'BACKUP_REASON="${BACKUP_REASON:-pre-migration}"' in snapshot
    assert "BACKUP_AGE_IDENTITY_FILE" in runbook
    assert "deploy/systemd/" in runbook
    assert "quarterly restore drill" in runbook
    assert "Restore Drill" in runbook


def test_backup_schedule_templates_are_present():
    """Backup timers should provide a concrete schedule for operators."""
    postgres_service = (
        PROJECT_ROOT / "deploy/systemd/gift-manager-postgres-backup.service"
    ).read_text()
    postgres_timer = (
        PROJECT_ROOT / "deploy/systemd/gift-manager-postgres-backup.timer"
    ).read_text()
    media_service = (PROJECT_ROOT / "deploy/systemd/gift-manager-media-backup.service").read_text()
    media_timer = (PROJECT_ROOT / "deploy/systemd/gift-manager-media-backup.timer").read_text()
    env_example = (PROJECT_ROOT / "deploy/systemd/backup.env.example").read_text()

    assert "EnvironmentFile=/etc/gift-manager/backup.env" in postgres_service
    assert "ExecStart=/opt/gift-manager/scripts/postgres_backup.sh" in postgres_service
    assert "OnCalendar=*-*-* 02:15:00" in postgres_timer
    assert "Persistent=true" in postgres_timer
    assert "ExecStart=/opt/gift-manager/scripts/media_backup.sh" in media_service
    assert "OnCalendar=*-*-* 02:45:00" in media_timer
    assert "BACKUP_AGE_RECIPIENT=age1..." in env_example
    assert "BACKUP_UPLOAD_CMD" in env_example
    assert "BACKUP_MONITOR_FAILURE_URL" in env_example


def test_backup_scripts_are_parseable_bash():
    """Shell scripts should pass bash syntax checks."""
    scripts = [
        PROJECT_ROOT / "scripts/postgres_backup.sh",
        PROJECT_ROOT / "scripts/postgres_restore.sh",
        PROJECT_ROOT / "scripts/media_backup.sh",
        PROJECT_ROOT / "scripts/pre_migration_snapshot.sh",
    ]

    result = subprocess.run(  # noqa: S603 - fixed bash syntax check against repo scripts.
        ["/usr/bin/bash", "-n", *map(str, scripts)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
