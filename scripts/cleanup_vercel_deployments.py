#!/usr/bin/env python
"""Clean up Vercel preview deployments to conserve deployment storage credits.

This script supports:
1. Removing preview deployments associated with a closed PR branch (--branch).
2. Pruning stale preview deployments older than N days (--older-than-days).
3. Configuring project deployment retention policy (--configure-retention).

Safety guarantees:
- Always enforces target='preview' so production deployments are never deleted.
- Supports --dry-run to preview actions before deleting.
- Standard library only (no external dependencies required).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

VERCEL_API_BASE = "https://api.vercel.com"
DEFAULT_PROJECT_ID = "prj_6aigFVVxxgFpZmB2tkGVAWlBWmAd"
DEFAULT_TEAM_ID = "team_EAAIdCUS0FCvbNVCybOZMLa1"


def get_default_project_credentials() -> tuple[str, str]:
    """Attempt to read project and team/org IDs from .vercel/project.json or fallback."""
    project_id = DEFAULT_PROJECT_ID
    team_id = DEFAULT_TEAM_ID

    project_json_path = Path(__file__).resolve().parent.parent / ".vercel" / "project.json"
    if project_json_path.is_file():
        try:
            with project_json_path.open(encoding="utf-8") as f:
                data = json.load(f)
                project_id = data.get("projectId", project_id)
                team_id = data.get("orgId", team_id)
        except Exception as exc:
            logger.debug("Could not read %s: %s", project_json_path, exc)

    return project_id, team_id


def resolve_config(
    token: str | None = None,
    project_id: str | None = None,
    team_id: str | None = None,
) -> tuple[str | None, str, str | None]:
    """Resolve API token, project ID, and team ID from args, env, or file."""
    default_project_id, default_team_id = get_default_project_credentials()

    resolved_token = token or os.environ.get("VERCEL_TOKEN")
    resolved_project_id = project_id or os.environ.get("VERCEL_PROJECT_ID") or default_project_id
    resolved_team_id = (
        team_id
        or os.environ.get("VERCEL_TEAM_ID")
        or os.environ.get("VERCEL_ORG_ID")
        or default_team_id
    )

    return resolved_token, resolved_project_id, resolved_team_id


def make_api_request(
    endpoint: str,
    method: str = "GET",
    token: str | None = None,
    team_id: str | None = None,
    query_params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated HTTP request to the Vercel REST API."""
    params = dict(query_params or {})
    if team_id and "teamId" not in params:
        params["teamId"] = team_id

    url = f"{VERCEL_API_BASE}{endpoint}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "GiftManager-Cleanup/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data_bytes: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)  # noqa: S310

    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
            if body:
                return json.loads(body)
            return {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.exception("Vercel API error (%s %s): HTTP %s - %s", method, url, exc.code, err_body)
        raise


def list_preview_deployments(
    token: str,
    project_id: str,
    team_id: str | None = None,
    branch: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List preview deployments for a given project and optional branch filter."""
    params: dict[str, str] = {
        "projectId": project_id,
        "target": "preview",  # strictly preview deployments
        "limit": str(limit),
    }
    if branch:
        params["branch"] = branch

    data = make_api_request(
        endpoint="/v6/deployments",
        method="GET",
        token=token,
        team_id=team_id,
        query_params=params,
    )

    deployments = data.get("deployments", [])
    # Extra safety guard: never include any deployment that claims production target
    safe_deployments = [d for d in deployments if d.get("target") != "production"]

    # If filtering by branch, ensure branch matches either 'branch' or meta.githubCommitRef
    if branch:
        safe_deployments = [
            d
            for d in safe_deployments
            if d.get("meta", {}).get("githubCommitRef") == branch or d.get("branch") == branch
        ]

    return safe_deployments


def delete_deployment(
    token: str,
    deployment_id: str,
    team_id: str | None = None,
) -> bool:
    """Delete a single deployment by its UID."""
    try:
        make_api_request(
            endpoint=f"/v13/deployments/{deployment_id}",
            method="DELETE",
            token=token,
            team_id=team_id,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info("Deployment %s was already deleted (404).", deployment_id)
            return True
        logger.exception("Failed to delete deployment %s: HTTP %s", deployment_id, exc.code)
        return False
    else:
        return True


def update_retention_policy(
    token: str,
    project_id: str,
    team_id: str | None = None,
    expiration_days: int = 7,
    expiration_days_canceled: int = 2,
    expiration_days_errored: int = 7,
) -> bool:
    """Update project deploymentExpiration setting via Vercel PATCH API."""
    payload = {
        "deploymentExpiration": {
            "expirationDays": expiration_days,
            "expirationDaysCanceled": expiration_days_canceled,
            "expirationDaysErrored": expiration_days_errored,
        }
    }
    try:
        make_api_request(
            endpoint=f"/v9/projects/{project_id}",
            method="PATCH",
            token=token,
            team_id=team_id,
            payload=payload,
        )
    except urllib.error.HTTPError as exc:
        logger.exception("Failed to update retention policy: HTTP %s", exc.code)
        return False
    else:
        logger.info(
            "Updated deployment retention for project %s (previews: %d days).",
            project_id,
            expiration_days,
        )
        return True


def prune_deployments(
    token: str,
    project_id: str,
    team_id: str | None = None,
    branch: str | None = None,
    older_than_days: int | None = None,
    *,
    dry_run: bool = False,
) -> int:
    """Find and delete matching preview deployments. Returns the count of deleted deployments."""
    deployments = list_preview_deployments(
        token=token,
        project_id=project_id,
        team_id=team_id,
        branch=branch,
    )

    if not deployments:
        logger.info("No preview deployments found matching criteria (branch=%s).", branch)
        return 0

    to_delete: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for dep in deployments:
        created_ms = dep.get("created")
        if created_ms:
            created_dt = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)
            age_days = (now - created_dt).total_seconds() / 86400.0
        else:
            created_dt = None
            age_days = 0.0

        if older_than_days is not None and age_days < older_than_days:
            continue

        to_delete.append(dep)

    if not to_delete:
        logger.info("No deployments matched the age cutoff (older_than_days=%s).", older_than_days)
        return 0

    action_label = "delete (dry-run)" if dry_run else "delete"
    logger.info(
        "Found %d preview deployment(s) to %s (branch=%s, older_than_days=%s):",
        len(to_delete),
        action_label,
        branch,
        older_than_days,
    )

    deleted_count = 0
    for dep in to_delete:
        dep_id = dep.get("uid") or dep.get("id", "unknown")
        url = dep.get("url", "unknown-url")
        created_str = (
            datetime.fromtimestamp(dep["created"] / 1000.0, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            if dep.get("created")
            else "unknown"
        )
        branch_name = dep.get("meta", {}).get("githubCommitRef") or dep.get("branch", "unknown")

        logger.info(" - %s (%s, branch: %s, created: %s)", dep_id, url, branch_name, created_str)

        if dry_run:
            deleted_count += 1
            continue

        if delete_deployment(token=token, deployment_id=dep_id, team_id=team_id):
            deleted_count += 1
            logger.info("   -> Deleted successfully.")
        else:
            logger.warning("   -> Failed to delete %s.", dep_id)

    return deleted_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Clean up Vercel preview deployments to reduce storage credits usage."
    )
    parser.add_argument(
        "--branch",
        type=str,
        help="Clean up preview deployments for a specific Git branch (e.g. from closed PR).",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        help="Prune preview deployments older than N days.",
    )
    parser.add_argument(
        "--configure-retention",
        type=int,
        metavar="DAYS",
        help="Update project retention policy: set preview expiration to DAYS days.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect deployments that would be deleted without deleting them.",
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Vercel API token (or VERCEL_TOKEN environment variable).",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="Vercel project ID (or VERCEL_PROJECT_ID environment variable).",
    )
    parser.add_argument(
        "--team-id",
        type=str,
        help="Vercel team/org ID (or VERCEL_TEAM_ID / VERCEL_ORG_ID environment variable).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for the cleanup script."""
    args = parse_args(argv)

    token, project_id, team_id = resolve_config(
        token=args.token,
        project_id=args.project_id,
        team_id=args.team_id,
    )

    if not token and not args.dry_run:
        logger.error("VERCEL_TOKEN is required. Pass via --token or VERCEL_TOKEN env var.")
        return 1

    if args.configure_retention is not None:
        if not token:
            logger.error("VERCEL_TOKEN is required to configure retention.")
            return 1
        success = update_retention_policy(
            token=token,
            project_id=project_id,
            team_id=team_id,
            expiration_days=args.configure_retention,
        )
        if not success:
            return 1

    if args.branch or args.older_than_days is not None:
        if not token and not args.dry_run:
            return 1
        prune_deployments(
            token=token or "",
            project_id=project_id,
            team_id=team_id,
            branch=args.branch,
            older_than_days=args.older_than_days,
            dry_run=args.dry_run,
        )
    elif args.configure_retention is None:
        logger.info("Nothing to do. Specify --branch, --older-than-days, or --configure-retention.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
