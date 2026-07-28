"""System API routes – update checks, health, reimport, and configuration."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import openpyxl
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_session
from app.importers.objectives import import_assessment_objectives
from app.models.assessment import AssessmentObjective
from app.services.github_service import check_for_updates, get_cached_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System"])


@router.post("/reimport-objectives")
def reimport_objectives(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Re-import assessment objectives from the SCF workbook.

    Protected by `X-API-Key` header – must match the `ADMIN_API_KEY`
    environment variable set on the server.

    Workflow:
        1. Deletes all existing assessment objectives
        2. Re-imports from `secure-controls-framework-scf-2026-1.xlsx`
        3. Verifies integrity (no null codes, no placeholder text)

    Returns counts for deleted, imported, and verification results.
    """
    # ── Auth check ────────────────────────────────────────────────────
    api_key = request.headers.get("X-API-Key", "")
    if not api_key or not settings.admin_api_key:
        msg = "Forbidden – valid X-API-Key header required (configure ADMIN_API_KEY on server)"
        return JSONResponse(status_code=403, content={"detail": msg})
    if api_key != settings.admin_api_key:
        return JSONResponse(status_code=403, content={"detail": "Forbidden – invalid API key"})

    # ── Load workbook ─────────────────────────────────────────────────
    workbook_path = settings.default_workbook
    if not os.path.exists(workbook_path):
        return JSONResponse(
            status_code=500,
            content={"detail": f"Workbook not found at {workbook_path!r}"},
        )

    wb = openpyxl.load_workbook(workbook_path, data_only=True, read_only=False)

    try:
        # 1. Delete existing objectives
        deleted = session.query(AssessmentObjective).delete()
        session.commit()
        logger.info("Deleted %d stale assessment objectives", deleted)

        # 2. Re-import from the spreadsheet
        imported = import_assessment_objectives(session, wb)
        session.commit()
        logger.info("Imported %d fresh assessment objectives", imported)

        # 3. Verify
        r = session.execute(
            text("SELECT COUNT(*) FROM assessment_objectives WHERE objective_code IS NULL")
        )
        null_codes = r.scalar()

        r = session.execute(
            text("SELECT COUNT(*) FROM assessment_objectives WHERE objective_text = 'SCF Created'")
        )
        placeholders = r.scalar()

        return {
            "success": True,
            "deleted": deleted,
            "imported": imported,
            "verification": {
                "total": imported,
                "null_codes": null_codes,
                "scf_created_placeholders": placeholders,
                "clean": null_codes == 0 and placeholders == 0,
            },
        }
    finally:
        wb.close()


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
