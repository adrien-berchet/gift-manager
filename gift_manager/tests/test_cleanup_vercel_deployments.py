"""Unit tests for the Vercel preview deployment cleanup script."""

from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock
from unittest.mock import patch

from scripts.cleanup_vercel_deployments import DEFAULT_PROJECT_ID
from scripts.cleanup_vercel_deployments import DEFAULT_TEAM_ID
from scripts.cleanup_vercel_deployments import delete_deployment
from scripts.cleanup_vercel_deployments import list_preview_deployments
from scripts.cleanup_vercel_deployments import main
from scripts.cleanup_vercel_deployments import make_api_request
from scripts.cleanup_vercel_deployments import prune_deployments
from scripts.cleanup_vercel_deployments import resolve_config
from scripts.cleanup_vercel_deployments import update_retention_policy


def test_resolve_config_defaults(monkeypatch):
    """resolve_config should use defaults when no env or args are passed."""
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_ID", raising=False)
    monkeypatch.delenv("VERCEL_TEAM_ID", raising=False)
    monkeypatch.delenv("VERCEL_ORG_ID", raising=False)

    token, project_id, team_id = resolve_config()
    assert token is None
    assert project_id == DEFAULT_PROJECT_ID
    assert team_id == DEFAULT_TEAM_ID


def test_resolve_config_env_vars(monkeypatch):
    """resolve_config should prefer environment variables over defaults."""
    monkeypatch.setenv("VERCEL_TOKEN", "test-token-env")
    monkeypatch.setenv("VERCEL_PROJECT_ID", "prj_custom_123")
    monkeypatch.setenv("VERCEL_TEAM_ID", "team_custom_456")

    token, project_id, team_id = resolve_config()
    assert token == "test-token-env"
    assert project_id == "prj_custom_123"
    assert team_id == "team_custom_456"


def test_resolve_config_args_override():
    """Explicit arguments should take precedence over env and defaults."""
    token, project_id, team_id = resolve_config(
        token="token-arg",
        project_id="prj-arg",
        team_id="team-arg",
    )
    assert token == "token-arg"
    assert project_id == "prj-arg"
    assert team_id == "team-arg"


def test_make_api_request_success():
    """make_api_request should send correct headers, method, and parse json response."""
    mock_response = io.BytesIO(b'{"key": "value"}')
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_cm) as mock_urlopen:
        res = make_api_request(
            endpoint="/v6/deployments",
            method="GET",
            token="secret-tok",
            team_id="team_xyz",
            query_params={"target": "preview"},
        )
        assert res == {"key": "value"}

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "GET"
        assert req.get_header("Authorization") == "Bearer secret-tok"
        assert "teamId=team_xyz" in req.full_url
        assert "target=preview" in req.full_url


def test_list_preview_deployments_excludes_production():
    """list_preview_deployments must strictly reject any deployment marked target=production."""
    api_data = {
        "deployments": [
            {
                "uid": "dpl_preview_1",
                "target": "preview",
                "url": "preview-1.vercel.app",
                "branch": "feat-a",
            },
            {
                "uid": "dpl_prod_1",
                "target": "production",
                "url": "prod.gift-manager.app",
                "branch": "main",
            },
            {
                "uid": "dpl_preview_2",
                "target": "preview",
                "url": "preview-2.vercel.app",
                "meta": {"githubCommitRef": "feat-b"},
            },
        ]
    }

    with patch("scripts.cleanup_vercel_deployments.make_api_request", return_value=api_data):
        results = list_preview_deployments(
            token="test-token",
            project_id="prj_123",
            team_id="team_123",
        )
        assert len(results) == 2
        uids = [d["uid"] for d in results]
        assert "dpl_prod_1" not in uids
        assert uids == ["dpl_preview_1", "dpl_preview_2"]


def test_list_preview_deployments_branch_filtering():
    """Branch filter should match branch field or meta.githubCommitRef."""
    api_data = {
        "deployments": [
            {"uid": "dpl_1", "target": "preview", "branch": "feature/ui"},
            {"uid": "dpl_2", "target": "preview", "meta": {"githubCommitRef": "feature/ui"}},
            {"uid": "dpl_3", "target": "preview", "branch": "other-branch"},
        ]
    }

    with patch("scripts.cleanup_vercel_deployments.make_api_request", return_value=api_data):
        results = list_preview_deployments(
            token="test-token",
            project_id="prj_123",
            branch="feature/ui",
        )
        assert len(results) == 2
        assert [d["uid"] for d in results] == ["dpl_1", "dpl_2"]


def test_delete_deployment_success():
    """delete_deployment should issue a DELETE request to /v13/deployments/{id}."""
    with patch("scripts.cleanup_vercel_deployments.make_api_request", return_value={}) as mock_req:
        success = delete_deployment("test-token", "dpl_abc", team_id="team_123")
        assert success is True
        mock_req.assert_called_once_with(
            endpoint="/v13/deployments/dpl_abc",
            method="DELETE",
            token="test-token",
            team_id="team_123",
        )


def test_delete_deployment_404_treated_as_success():
    """If deployment is already deleted (404), return True."""
    err = urllib.error.HTTPError(
        url="https://api.vercel.com/v13/deployments/dpl_abc",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(b'{"error": {"code": "not_found"}}'),
    )

    with patch("scripts.cleanup_vercel_deployments.make_api_request", side_effect=err):
        success = delete_deployment("test-token", "dpl_abc")
        assert success is True


def test_delete_deployment_failure():
    """HTTP 500 error should return False."""
    err = urllib.error.HTTPError(
        url="https://api.vercel.com/v13/deployments/dpl_abc",
        code=500,
        msg="Internal Error",
        hdrs={},
        fp=io.BytesIO(b"server error"),
    )

    with patch("scripts.cleanup_vercel_deployments.make_api_request", side_effect=err):
        success = delete_deployment("test-token", "dpl_abc")
        assert success is False


def test_update_retention_policy_success():
    """update_retention_policy should PATCH the project configuration."""
    with patch("scripts.cleanup_vercel_deployments.make_api_request", return_value={}) as mock_req:
        success = update_retention_policy(
            token="test-token",
            project_id="prj_123",
            team_id="team_456",
            expiration_days=5,
        )
        assert success is True
        mock_req.assert_called_once_with(
            endpoint="/v9/projects/prj_123",
            method="PATCH",
            token="test-token",
            team_id="team_456",
            payload={
                "deploymentExpiration": {
                    "expirationDays": 5,
                    "expirationDaysCanceled": 2,
                    "expirationDaysErrored": 7,
                }
            },
        )


def test_prune_deployments_dry_run():
    """dry_run=True should find deployments and report count without calling delete."""
    fake_deployments = [
        {"uid": "dpl_1", "url": "preview-1.app", "created": 1700000000000, "target": "preview"},
        {"uid": "dpl_2", "url": "preview-2.app", "created": 1700000000000, "target": "preview"},
    ]

    with (
        patch(
            "scripts.cleanup_vercel_deployments.list_preview_deployments",
            return_value=fake_deployments,
        ),
        patch("scripts.cleanup_vercel_deployments.delete_deployment") as mock_del,
    ):
        deleted = prune_deployments(
            token="token",
            project_id="prj_123",
            dry_run=True,
        )
        assert deleted == 2
        mock_del.assert_not_called()


def test_prune_deployments_older_than_days():
    """Deployments newer than cutoff should be skipped."""
    now_ms = 1700000000000  # benchmark fixed time
    ms_in_day = 86400 * 1000

    old_deployment = {
        "uid": "dpl_old",
        "url": "old.app",
        "created": now_ms - (10 * ms_in_day),
        "target": "preview",
    }
    recent_deployment = {
        "uid": "dpl_recent",
        "url": "recent.app",
        "created": now_ms - (2 * ms_in_day),
        "target": "preview",
    }

    with (
        patch(
            "scripts.cleanup_vercel_deployments.list_preview_deployments",
            return_value=[old_deployment, recent_deployment],
        ),
        patch(
            "scripts.cleanup_vercel_deployments.delete_deployment", return_value=True
        ) as mock_del,
        patch("scripts.cleanup_vercel_deployments.datetime") as mock_dt,
    ):
        # Fix datetime.now(timezone.utc)
        from datetime import datetime
        from datetime import timezone

        fixed_now = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc)
        mock_dt.now.return_value = fixed_now
        mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp

        deleted = prune_deployments(
            token="token",
            project_id="prj_123",
            older_than_days=7,
            dry_run=False,
        )
        assert deleted == 1
        mock_del.assert_called_once_with(token="token", deployment_id="dpl_old", team_id=None)


def test_main_cli_missing_token_fails(monkeypatch):
    """Running main without VERCEL_TOKEN and without --dry-run should return 1."""
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    exit_code = main(["--branch", "feat-test"])
    assert exit_code == 1


def test_main_cli_dry_run_allowed_without_token(monkeypatch):
    """Running main with --dry-run should not require VERCEL_TOKEN."""
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    with patch("scripts.cleanup_vercel_deployments.prune_deployments", return_value=0):
        exit_code = main(["--branch", "feat-test", "--dry-run"])
        assert exit_code == 0
