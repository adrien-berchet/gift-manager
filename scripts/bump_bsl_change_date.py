#!/usr/bin/env python
"""Bump the Business Source License 1.1 Change Date by four years.

Updates the ``Change Date`` line in ``LICENSE`` (and the matching date note in
``README.md``, if present) to four years from today's UTC date when non-license
changes have been committed since the last ``LICENSE`` update.

Standard library only; designed for scheduled GitHub Actions maintenance.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LICENSE_CHANGE_DATE_RE = re.compile(r"^(Change Date:\s*)(\d{4}-\d{2}-\d{2})$", re.MULTILINE)
README_CHANGE_DATE_RE = re.compile(
    r"(4 years after release;\s*`)(\d{4}-\d{2}-\d{2})(`\s*for the current version)"
)


def compute_target_date(today: date | None = None, years: int = 4) -> date:
    """Return ``today`` shifted forward by ``years`` calendar years (leap-day safe)."""
    base = today or datetime.now(tz=timezone.utc).date()
    target_year = base.year + years
    max_day = calendar.monthrange(target_year, base.month)[1]
    return date(target_year, base.month, min(base.day, max_day))


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
    """Return True if files other than LICENSE and README.md changed since LICENSE was updated."""
    last_license_commit = _run_git(repo_root, "log", "-n", "1", "--format=%H", "--", "LICENSE")
    if not last_license_commit:
        return True

    commits_since = _run_git(
        repo_root,
        "log",
        f"{last_license_commit}..HEAD",
        "--format=%H",
        "--",
        ".",
        ":!LICENSE",
        ":!README.md",
    )
    return bool(commits_since)


def update_files(
    repo_root: Path,
    target_date: date,
    *,
    dry_run: bool = False,
) -> tuple[bool, date]:
    """Update Change Date in LICENSE and README.md if ``target_date`` is newer.

    Returns:
        A tuple of ``(changed, target_date)``.
    """
    license_path = repo_root / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8")

    match = LICENSE_CHANGE_DATE_RE.search(license_text)
    if match is None:
        msg = f"Could not find 'Change Date: YYYY-MM-DD' in {license_path}"
        raise ValueError(msg)

    current_date = date.fromisoformat(match.group(2))
    if current_date >= target_date:
        logger.info(
            "Current Change Date (%s) is already on or after target (%s); no update needed.",
            current_date.isoformat(),
            target_date.isoformat(),
        )
        return False, target_date

    new_date_str = target_date.isoformat()
    updated_license = LICENSE_CHANGE_DATE_RE.sub(rf"\g<1>{new_date_str}", license_text, count=1)

    readme_path = repo_root / "README.md"
    updated_readme: str | None = None
    if readme_path.is_file():
        readme_text = readme_path.read_text(encoding="utf-8")
        if README_CHANGE_DATE_RE.search(readme_text):
            candidate = README_CHANGE_DATE_RE.sub(
                rf"\g<1>{new_date_str}\g<3>",
                readme_text,
                count=1,
            )
            if candidate != readme_text:
                updated_readme = candidate

    if dry_run:
        logger.info("[DRY RUN] Would bump Change Date: %s -> %s", current_date, new_date_str)
        if updated_readme is not None:
            logger.info("[DRY RUN] Would also update Change Date in %s", readme_path)
        return True, target_date

    license_path.write_text(updated_license, encoding="utf-8")
    if updated_readme is not None:
        readme_path.write_text(updated_readme, encoding="utf-8")

    logger.info("Updated Change Date: %s -> %s", current_date.isoformat(), new_date_str)
    return True, target_date


def _write_github_output(target_date: date, *, changed: bool) -> None:
    """Append outputs for GitHub Actions when GITHUB_OUTPUT is set."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"changed={'true' if changed else 'false'}\n")
        handle.write(f"target_date={target_date.isoformat()}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Bump BSL 1.1 Change Date by 4 years.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Path to repository root (defaults to parent of scripts/).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bump even if no non-license files changed since the last LICENSE commit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the change without modifying files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for bumping the BSL 1.1 Change Date."""
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    target_date = compute_target_date()

    if not args.force and not has_changes_since_last_license_update(repo_root):
        logger.info("No non-license changes since last LICENSE update; skipping bump.")
        _write_github_output(target_date, changed=False)
        return 0

    changed, target_date = update_files(repo_root, target_date, dry_run=args.dry_run)
    _write_github_output(target_date, changed=changed and not args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
