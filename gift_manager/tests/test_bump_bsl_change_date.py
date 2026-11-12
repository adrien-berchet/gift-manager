"""Unit tests for the BSL 1.1 Change Date bump script."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from scripts.bump_bsl_change_date import compute_target_date
from scripts.bump_bsl_change_date import main
from scripts.bump_bsl_change_date import update_files

if TYPE_CHECKING:
    from pathlib import Path


def test_compute_target_date_normal_and_leap_day():
    """compute_target_date shifts by 4 years and preserves Feb 29 on leap years."""
    assert compute_target_date(date(2026, 11, 12)) == date(2030, 11, 12)
    assert compute_target_date(date(2024, 2, 29)) == date(2028, 2, 29)
    # 2100 is not a leap year, so Feb 29 clamps to Feb 28
    assert compute_target_date(date(2096, 2, 29)) == date(2100, 2, 28)


def test_update_files_bumps_license_and_readme(tmp_path: Path):
    """update_files updates Change Date in both LICENSE and README.md."""
    license_file = tmp_path / "LICENSE"
    readme_file = tmp_path / "README.md"
    license_file.write_text(
        "Business Source License 1.1\n\nChange Date: 2030-11-12\nChange License: Apache License 2.0\n",
        encoding="utf-8",
    )
    readme_file.write_text(
        "- **Open-source conversion:** Each released version transitions to **Apache License 2.0** "
        "on its Change Date (4 years after release; `2030-11-12` for the current version).\n",
        encoding="utf-8",
    )

    changed, target = update_files(tmp_path, date(2031, 1, 1))
    assert changed is True
    assert target == date(2031, 1, 1)
    assert "Change Date: 2031-01-01" in license_file.read_text(encoding="utf-8")
    assert "`2031-01-01` for the current version" in readme_file.read_text(encoding="utf-8")


def test_update_files_dry_run_leaves_files_untouched(tmp_path: Path):
    """update_files with dry_run=True reports a change without editing files."""
    license_file = tmp_path / "LICENSE"
    original = "Business Source License 1.1\n\nChange Date: 2030-11-12\n"
    license_file.write_text(original, encoding="utf-8")

    changed, _ = update_files(tmp_path, date(2031, 1, 1), dry_run=True)
    assert changed is True
    assert license_file.read_text(encoding="utf-8") == original


def test_update_files_skips_when_already_current(tmp_path: Path):
    """update_files does not modify files if Change Date is already >= target_date."""
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


def test_main_skips_when_no_code_changes_unless_forced(tmp_path: Path, monkeypatch):
    """Ensure main skips bumping without --force when no non-license changes exist."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Change Date: 2029-01-01\n", encoding="utf-8")
    output_file = tmp_path / "gh_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    with (
        patch("scripts.bump_bsl_change_date.compute_target_date", return_value=date(2031, 1, 1)),
        patch(
            "scripts.bump_bsl_change_date.has_changes_since_last_license_update",
            return_value=False,
        ),
    ):
        assert main(["--repo-root", str(tmp_path)]) == 0
        assert "Change Date: 2029-01-01" in license_file.read_text(encoding="utf-8")
        assert "changed=false\n" in output_file.read_text(encoding="utf-8")

        output_file.write_text("", encoding="utf-8")
        assert main(["--repo-root", str(tmp_path), "--force"]) == 0
        assert "Change Date: 2031-01-01" in license_file.read_text(encoding="utf-8")
        assert output_file.read_text(encoding="utf-8") == "changed=true\ntarget_date=2031-01-01\n"
