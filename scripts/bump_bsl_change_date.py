#!/usr/bin/env python
"""Check or bump the Business Source License 1.1 Change Date.

Supports two modes:
- Default (bump): updates ``Change Date`` in ``LICENSE`` to four years from
  today's UTC date when non-license changes have occurred since the last
  ``Change Date`` update.
- ``--check``: verifies that ``Change Date`` in ``LICENSE`` is at least 42
  months (~3.5 years) in the future, exiting non-zero otherwise.

Standard library only.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import re
import shutil
import subprocess
import sys
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LICENSE_CHANGE_DATE_RE = re.compile(r"^(Change Date:\s*)(\d{4}-\d{2}-\d{2})$", re.MULTILINE)
DEFAULT_BUMP_MONTHS = 48
DEFAULT_MIN_MONTHS = 42


def shift_months(base: date, months: int) -> date:
    """Return ``base`` shifted forward by ``months`` calendar months (month-end safe)."""
    zero_based_month = (base.month - 1) + months
    target_year = base.year + zero_based_month // 12
    target_month = (zero_based_month % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    return date(target_year, target_month, min(base.day, max_day))


def compute_target_date(today: date | None = None, years: int = 4) -> date:
    """Return ``today`` shifted forward by ``years`` calendar years (leap-day safe)."""
    base = today or datetime.now(tz=timezone.utc).date()
    return shift_months(base, years * 12)


def _run_git(repo_root: Path, *args: str) -> str:
    """Run a git subcommand inside ``repo_root`` and return stripped stdout."""
    git_exe = shutil.which("git")
    if git_exe is None:
        msg = "git executable not found on PATH"
        raise RuntimeError(msg)
    result = subprocess.run(  # noqa: S603
        [git_exe, "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def has_changes_since_last_license_update(repo_root: Path) -> bool:
    """Return True if files other than LICENSE/README.md changed since Change Date was updated."""
    last_date_commit = _run_git(
        repo_root,
        "log",
        "-n",
        "1",
        "-G",
        "^Change Date:",
        "--format=%H",
        "--",
        "LICENSE",
    )
    if not last_date_commit:
        return True

    commits_since = _run_git(
        repo_root,
        "log",
        f"{last_date_commit}..HEAD",
        "--format=%H",
        "--",
        ".",
        ":!LICENSE",
        ":!README.md",
    )
    return bool(commits_since)


def read_change_date(repo_root: Path) -> tuple[Path, str, date]:
    """Read ``LICENSE`` and return ``(license_path, license_text, change_date)``."""
    license_path = repo_root / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8")
    match = LICENSE_CHANGE_DATE_RE.search(license_text)
    if match is None:
        msg = f"Could not find 'Change Date: YYYY-MM-DD' in {license_path}"
        raise ValueError(msg)
    return license_path, license_text, date.fromisoformat(match.group(2))


def check_change_date(
    repo_root: Path,
    *,
    min_months: int = DEFAULT_MIN_MONTHS,
    today: date | None = None,
) -> bool:
    """Return True if ``Change Date`` in ``LICENSE`` is at least ``min_months`` away."""
    _, _, current_date = read_change_date(repo_root)
    base = today or datetime.now(tz=timezone.utc).date()
    min_required = shift_months(base, min_months)
    if current_date < min_required:
        suggested = compute_target_date(base)
        logger.error(
            "BSL Change Date (%s) is less than %d months away (minimum %s). "
            "Run 'python scripts/bump_bsl_change_date.py --force' to bump it to %s.",
            current_date.isoformat(),
            min_months,
            min_required.isoformat(),
            suggested.isoformat(),
        )
        return False

    logger.info(
        "BSL Change Date (%s) meets minimum threshold (%s).",
        current_date.isoformat(),
        min_required.isoformat(),
    )
    return True


def update_files(
    repo_root: Path,
    target_date: date,
    *,
    dry_run: bool = False,
) -> tuple[bool, date]:
    """Update Change Date in ``LICENSE`` if ``target_date`` is newer.

    Returns:
        A tuple of ``(changed, target_date)``.
    """
    license_path, license_text, current_date = read_change_date(repo_root)
    if current_date >= target_date:
        logger.info(
            "Current Change Date (%s) is already on or after target (%s); no update needed.",
            current_date.isoformat(),
            target_date.isoformat(),
        )
        return False, target_date

    new_date_str = target_date.isoformat()
    updated_license = LICENSE_CHANGE_DATE_RE.sub(rf"\g<1>{new_date_str}", license_text, count=1)

    if dry_run:
        logger.info("[DRY RUN] Would bump Change Date: %s -> %s", current_date, new_date_str)
        return True, target_date

    license_path.write_text(updated_license, encoding="utf-8")
    logger.info("Updated Change Date: %s -> %s", current_date.isoformat(), new_date_str)
    return True, target_date


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Check or bump BSL 1.1 Change Date.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Path to repository root (defaults to parent of scripts/).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail with exit code 1 if Change Date is less than --min-months away.",
    )
    parser.add_argument(
        "--min-months",
        type=int,
        default=DEFAULT_MIN_MONTHS,
        help="Minimum remaining horizon in months required by --check (default: 42).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bump even if no non-license files changed since the last Change Date commit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the change without modifying files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for checking or bumping the BSL 1.1 Change Date."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()

    if args.check:
        return 0 if check_change_date(repo_root, min_months=args.min_months) else 1

    target_date = compute_target_date()
    if not args.force and not has_changes_since_last_license_update(repo_root):
        logger.info("No non-license changes since last Change Date update; skipping bump.")
        return 0

    update_files(repo_root, target_date, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
