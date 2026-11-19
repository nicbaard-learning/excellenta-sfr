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
        2. Re-imports from the configured workbook (`DEFAULT_WORKBOOK`)
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


@router.post("/resync-frameworks")
def resync_frameworks(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Re-sync frameworks, jurisdictions and control mappings with the SCF workbook.

    Protected by `X-API-Key` header – must match `ADMIN_API_KEY`.

    One framework per mapping column of the SCF sheet, named and tagged from
    the Authoritative Sources sheet. Mappings imported from the wrong column
    are removed and missing ones added; frameworks that are not workbook
    columns (legacy duplicates) are deleted.
    """
    api_key = request.headers.get("X-API-Key", "")
    if not api_key or not settings.admin_api_key or api_key != settings.admin_api_key:
        return JSONResponse(status_code=403, content={"detail": "Forbidden – valid X-API-Key header required"})

    workbook_path = settings.default_workbook
    if not os.path.exists(workbook_path):
        return JSONResponse(status_code=500, content={"detail": f"Workbook not found at {workbook_path!r}"})

    from app.importers.catalogue import resync_from_workbook

    wb = openpyxl.load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        result = resync_from_workbook(session, wb)
        session.commit()
        return {"success": True, **result}
    except Exception:
        session.rollback()
        logger.exception("Framework resync failed")
        return JSONResponse(status_code=500, content={"detail": "Framework resync failed – see server logs"})
    finally:
        wb.close()


@router.post("/reload-requirements")
def reload_requirements(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Reload framework provisions (official text) from `data/requirements/*.json`.

    Protected by `X-API-Key` header – must match `ADMIN_API_KEY`. Each file
    replaces that framework's provisions and licence/attribution fields.
    """
    api_key = request.headers.get("X-API-Key", "")
    if not api_key or not settings.admin_api_key or api_key != settings.admin_api_key:
        return JSONResponse(status_code=403, content={"detail": "Forbidden – valid X-API-Key header required"})

    from app.importers.requirements import REQUIREMENTS_DIR, import_requirement_files

    if not any(REQUIREMENTS_DIR.glob("*.json")):
        return JSONResponse(
            status_code=500,
            content={"detail": f"No requirement files found in {REQUIREMENTS_DIR} – was data/requirements deployed?"},
        )

    try:
        loaded = import_requirement_files(session)
        session.commit()
        return {"success": True, "provisions": loaded}
    except Exception:
        session.rollback()
        logger.exception("Requirement reload failed")
        return JSONResponse(status_code=500, content={"detail": "Requirement reload failed – see server logs"})


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
