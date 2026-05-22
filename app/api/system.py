"""System API routes – update checks, health, and configuration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.github_service import check_for_updates, get_cached_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/update-check")
def system_update_check(
    force: bool = False,
    session: Session = Depends(get_session),
) -> dict:
    """Check if a newer version of the SCF framework is available on GitHub.

    By default returns the cached result (updated every 24h via background task).
    Pass `?force=true` to force a fresh check against the GitHub API.

    Returns:
        - update_available: bool
        - current_tag: the tag stored in our database (latest imported version)
        - latest_tag: the latest tag on GitHub
        - latest_commit: latest commit SHA on default branch
        - latest_release_url: URL to the latest release on GitHub
        - release_notes: truncated release notes
        - checked_at: ISO timestamp of when the check was performed
    """
    if force:
        result = check_for_updates(session)
        return result.to_dict()

    cached = get_cached_check()
    if cached:
        return cached

    # No cache, perform a fresh check
    result = check_for_updates(session)
    return result.to_dict()
