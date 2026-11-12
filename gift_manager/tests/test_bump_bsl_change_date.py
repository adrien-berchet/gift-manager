"""Unit and git integration tests for the BSL 1.1 Change Date script."""

from __future__ import annotations

import shutil
import subprocess
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from scripts.bump_bsl_change_date import check_change_date
from scripts.bump_bsl_change_date import compute_target_date
from scripts.bump_bsl_change_date import has_changes_since_last_license_update
from scripts.bump_bsl_change_date import main
from scripts.bump_bsl_change_date import shift_months
from scripts.bump_bsl_change_date import update_files

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    """Run a git command inside ``repo`` for test fixture setup."""
    git_exe = shutil.which("git")
    assert git_exe is not None
    subprocess.run(  # noqa: S603
        [git_exe, "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_compute_target_date_and_shift_months():
    """compute_target_date and shift_months clamp month-end and leap days cleanly."""
    assert compute_target_date(date(2026, 11, 12)) == date(2030, 11, 12)
    assert compute_target_date(date(2024, 2, 29)) == date(2028, 2, 29)
    assert compute_target_date(date(2096, 2, 29)) == date(2100, 2, 28)
    assert shift_months(date(2026, 10, 31), 42) == date(2030, 4, 30)


def test_update_files_bumps_license(tmp_path: Path):
    """update_files updates Change Date in LICENSE when target date is newer."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text(
        "Business Source License 1.1\n\nChange Date: 2030-11-12\nChange License: Apache License 2.0\n",
        encoding="utf-8",
    )

    changed, target = update_files(tmp_path, date(2031, 1, 1))
    assert changed is True
    assert target == date(2031, 1, 1)
    assert "Change Date: 2031-01-01" in license_file.read_text(encoding="utf-8")


def test_update_files_dry_run_leaves_files_untouched(tmp_path: Path):
    """update_files with dry_run=True reports a change without editing LICENSE."""
    license_file = tmp_path / "LICENSE"
    original = "Business Source License 1.1\n\nChange Date: 2030-11-12\n"
    license_file.write_text(original, encoding="utf-8")

    changed, _ = update_files(tmp_path, date(2031, 1, 1), dry_run=True)
    assert changed is True
    assert license_file.read_text(encoding="utf-8") == original


def test_update_files_skips_when_already_current(tmp_path: Path):
    """update_files does not modify LICENSE if Change Date is already >= target_date."""
    license_file = tmp_path / "LICENSE"
    original = "Business Source License 1.1\n\nChange Date: 2031-06-01\n"
    license_file.write_text(original, encoding="utf-8")

    changed, _ = update_files(tmp_path, date(2031, 1, 1))
    assert changed is False
    assert license_file.read_text(encoding="utf-8") == original


def test_update_files_raises_when_change_date_missing(tmp_path: Path):
    """update_files raises ValueError if Change Date line is absent."""
    (tmp_path / "LICENSE").write_text("Apache License 2.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Could not find 'Change Date: YYYY-MM-DD'"):
        update_files(tmp_path, date(2031, 1, 1))


def test_check_change_date_passes_and_fails(tmp_path: Path):
    """check_change_date enforces the minimum 42-month horizon."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Change Date: 2030-11-12\n", encoding="utf-8")

    assert check_change_date(tmp_path, today=date(2026, 11, 12)) is True
    assert check_change_date(tmp_path, today=date(2027, 5, 12)) is True
    assert check_change_date(tmp_path, today=date(2027, 5, 13)) is False


def test_main_check_mode_exit_codes(tmp_path: Path):
    """Ensure main --check returns 0 when horizon is sufficient and 1 when stale."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Change Date: 2030-11-12\n", encoding="utf-8")

    with patch("scripts.bump_bsl_change_date.check_change_date", return_value=True):
        assert main(["--repo-root", str(tmp_path), "--check"]) == 0

    with patch("scripts.bump_bsl_change_date.check_change_date", return_value=False):
        assert main(["--repo-root", str(tmp_path), "--check"]) == 1


def test_main_skips_when_no_code_changes_unless_forced(tmp_path: Path):
    """Ensure main skips bumping without --force when no non-license changes exist."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Change Date: 2029-01-01\n", encoding="utf-8")

    with (
        patch("scripts.bump_bsl_change_date.compute_target_date", return_value=date(2031, 1, 1)),
        patch(
            "scripts.bump_bsl_change_date.has_changes_since_last_license_update",
            return_value=False,
        ),
    ):
        assert main(["--repo-root", str(tmp_path)]) == 0
        assert "Change Date: 2029-01-01" in license_file.read_text(encoding="utf-8")

        assert main(["--repo-root", str(tmp_path), "--force"]) == 0
        assert "Change Date: 2031-01-01" in license_file.read_text(encoding="utf-8")


def test_has_changes_since_last_license_update_real_git(tmp_path: Path):
    """Verify -G '^Change Date:' baseline does not reset on typo-only LICENSE edits."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "user.email", "test@example.com")

    license_file = tmp_path / "LICENSE"
    app_file = tmp_path / "app.py"

    license_file.write_text(
        "Business Source License 1.1\n\nChange Date: 2030-11-12\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "LICENSE")
    _git(tmp_path, "commit", "-m", "Chore: Add LICENSE")

    assert has_changes_since_last_license_update(tmp_path) is False

    app_file.write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "Feat: Add app")
    assert has_changes_since_last_license_update(tmp_path) is True

    # A typo-only LICENSE commit must not hide the earlier code commit
    license_file.write_text(
        "Business Source License 1.1\n\nChange Date: 2030-11-12\n\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "LICENSE")
    _git(tmp_path, "commit", "-m", "Docs: Fix LICENSE trailing newline")
    assert has_changes_since_last_license_update(tmp_path) is True

    # An actual Change Date bump resets the baseline
    license_file.write_text(
        "Business Source License 1.1\n\nChange Date: 2031-05-01\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "LICENSE")
    _git(tmp_path, "commit", "-m", "Chore: Bump Change Date")
    assert has_changes_since_last_license_update(tmp_path) is False
