"""GitHub update checker – monitors the official SCF repository for new releases.

Target repository: https://github.com/securecontrolsframework/securecontrolsframework

Uses the GitHub REST API to check for latest releases and commits.
Results are cached in memory and persisted to the latest ImportRun record.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.import_run import ImportRun

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────
GITHUB_API_URL = "https://api.github.com/repos/securecontrolsframework/securecontrolsframework"
RELEASES_URL = f"{GITHUB_API_URL}/releases/latest"
COMMITS_URL = f"{GITHUB_API_URL}/commits?per_page=1"
DEFAULT_TIMEOUT = 15.0  # seconds

# In-memory cache of the last check result
_last_check: dict[str, Any] | None = None
_last_check_time: datetime | None = None


class GitHubCheckResult:
    """Result of a GitHub update check."""

    def __init__(
        self,
        update_available: bool = False,
        current_tag: str | None = None,
        latest_tag: str | None = None,
        latest_commit: str | None = None,
        latest_release_url: str | None = None,
        release_notes: str | None = None,
        error: str | None = None,
        checked_at: str | None = None,
    ):
        self.update_available = update_available
        self.current_tag = current_tag
        self.latest_tag = latest_tag
        self.latest_commit = latest_commit
        self.latest_release_url = latest_release_url
        self.release_notes = release_notes
        self.error = error
        self.checked_at = checked_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "update_available": self.update_available,
            "current_tag": self.current_tag,
            "latest_tag": self.latest_tag,
            "latest_commit": self.latest_commit,
            "latest_release_url": self.latest_release_url,
            "release_notes": self.release_notes,
            "error": self.error,
            "checked_at": self.checked_at,
        }


def get_latest_github_release() -> dict[str, Any] | None:
    """Fetch the latest release from the SCF GitHub repository.

    Returns:
        Dict with tag_name, html_url, body, published_at if successful.
        None if the request fails.
    """
    try:
        response = httpx.get(
            RELEASES_URL,
            timeout=DEFAULT_TIMEOUT,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        response.raise_for_status()
        data = response.json()
        return {
            "tag_name": data.get("tag_name"),
            "html_url": data.get("html_url"),
            "body": data.get("body", ""),
            "published_at": data.get("published_at"),
        }
    except httpx.TimeoutException:
        logger.warning("Timed out fetching latest release from GitHub")
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("GitHub API error fetching latest release: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error fetching latest release: %s", exc)
        return None


def get_latest_github_commit() -> str | None:
    """Fetch the latest commit SHA from the SCF GitHub repository's default branch.

    Returns:
        The full commit SHA string if successful, None otherwise.
    """
    try:
        response = httpx.get(
            COMMITS_URL,
            timeout=DEFAULT_TIMEOUT,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0].get("sha")
        return None
    except httpx.TimeoutException:
        logger.warning("Timed out fetching latest commit from GitHub")
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("GitHub API error fetching latest commit: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error fetching latest commit: %s", exc)
        return None


def check_for_updates(session: Session | None = None) -> GitHubCheckResult:
    """Check the official SCF GitHub repository for new releases.

    Compares the latest GitHub release tag against what's stored in our
    database to determine if an update is available.

    Args:
        session: Optional DB session. If None, creates one.

    Returns:
        GitHubCheckResult with update status and metadata.
    """
    global _last_check, _last_check_time

    own_session = False
    if session is None:
        session = SessionLocal()
        own_session = True

    try:
        # Get the latest stored tag from the most recent ImportRun
        latest_import = (
            session.query(ImportRun)
            .filter(ImportRun.latest_github_tag.isnot(None))
            .order_by(ImportRun.created_at.desc())
            .first()
        )
        current_tag = latest_import.latest_github_tag if latest_import else None

        # Fetch latest from GitHub
        release_data = get_latest_github_release()
        latest_commit = get_latest_github_commit()

        if not release_data and not latest_commit:
            result = GitHubCheckResult(
                error="Could not reach GitHub API",
                current_tag=current_tag,
            )
        else:
            latest_tag = release_data.get("tag_name") if release_data else None
            latest_release_url = release_data.get("html_url") if release_data else None
            release_notes = release_data.get("body") if release_data else None

            # Determine if an update is available
            update_available = False
            if current_tag and latest_tag:
                update_available = current_tag != latest_tag
            elif not current_tag and latest_tag:
                # No tag stored yet, treat as update available if we have a tag
                update_available = True

            # Persist the latest tag and commit to the ImportRun table
            if latest_tag or latest_commit:
                # Update the most recent ImportRun or create a tracking record
                tracking = latest_import
                if tracking:
                    if latest_tag:
                        tracking.latest_github_tag = latest_tag
                    if latest_commit:
                        tracking.last_checked_github_commit = latest_commit
                else:
                    tracking = ImportRun(
                        filename="github-check",
                        status="completed",
                        latest_github_tag=latest_tag or "",
                        last_checked_github_commit=latest_commit or "",
                        sheets_processed="[]",
                        rows_loaded=0,
                    )
                    session.add(tracking)
                session.commit()

            result = GitHubCheckResult(
                update_available=update_available,
                current_tag=current_tag,
                latest_tag=latest_tag,
                latest_commit=latest_commit,
                latest_release_url=latest_release_url,
                release_notes=release_notes,
            )

        # Update cache
        _last_check = result.to_dict()
        _last_check_time = datetime.now(timezone.utc)

        return result

    except Exception as exc:
        logger.exception("GitHub update check failed: %s", exc)
        return GitHubCheckResult(error=str(exc))
    finally:
        if own_session:
            session.close()


def get_cached_check() -> dict[str, Any] | None:
    """Get the last cached GitHub check result, if any."""
    global _last_check
    return _last_check
