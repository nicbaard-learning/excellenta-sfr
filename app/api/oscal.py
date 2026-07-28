"""OSCAL export API routes – serialize SFR data to NIST OSCAL JSON format.

Endpoints:
  GET /api/oscal/catalog              — Full control catalog
  GET /api/oscal/profile              — Framework-specific controls
  GET /api/oscal/assessment-results   — Maturity assessment results
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.oscal_service import OscalService

router = APIRouter(prefix="/api/oscal", tags=["OSCAL Export"])


@router.get("/catalog")
def export_catalog(
    domain: str | None = Query(None, description="Optional domain code to restrict export"),
    session: Session = Depends(get_session),
):
    """Export the full SCF control catalog in NIST OSCAL JSON format.

    Returns controls grouped by domain (group), with assessment objectives
    as control parts. Compatible with NIST SP 800-53 OSCAL 1.1.2.
    """
    svc = OscalService(session)
    catalog = svc.export_catalog(domain_code=domain)

    control_count = _count_controls(catalog)
    return JSONResponse(
        content=catalog,
        headers={
            "Content-Type": "application/oscal+catalog+json",
            "Content-Disposition": "attachment; filename=scf-catalog.json",
            "X-Total-Controls": str(control_count),
        },
    )


@router.get("/profile")
def export_profile(
    framework_name: str = Query(..., description="Framework name (e.g. 'ISO 27001', 'POPIA')"),
    session: Session = Depends(get_session),
):
    """Export a framework's control selection as an OSCAL profile.

    Shows which SCF controls apply to the specified framework, including
    framework-specific mapped IDs and STRM relationship types.
    """
    svc = OscalService(session)
    profile = svc.export_profile(framework_name=framework_name)

    if "error" in profile:
        return JSONResponse(content=profile, status_code=404)

    return JSONResponse(
        content=profile,
        headers={
            "Content-Type": "application/oscal+profile+json",
            "Content-Disposition": f"attachment; filename={framework_name.lower().replace(' ', '-')}-profile.json",
        },
    )


@router.get("/profile/{framework_id}")
def export_profile_by_id(
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Export a framework's control selection as an OSCAL profile by numeric ID."""
    svc = OscalService(session)
    profile = svc.export_profile(framework_id=framework_id)

    if "error" in profile:
        return JSONResponse(content=profile, status_code=404)

    return JSONResponse(
        content=profile,
        headers={"Content-Type": "application/oscal+profile+json"},
    )


@router.get("/assessment-results")
def export_assessment_results(
    framework_name: str = Query(..., description="Framework name"),
    session: Session = Depends(get_session),
):
    """Export maturity assessment data as an OSCAL assessment-results document.

    Shows evidence artifacts and assessment objectives per control.
    To include custom SCR-CMM maturity level assessments, use the
    `assessed_levels` query parameter (comma-separated scf_id=level pairs,
    e.g. AC-01-01=3,IR-04-02=2).
    """
    svc = OscalService(session)
    results = svc.export_assessment_results(framework_name=framework_name)

    if "error" in results:
        return JSONResponse(content=results, status_code=404)

    return JSONResponse(
        content=results,
        headers={"Content-Type": "application/oscal+assessment-results+json"},
    )


def _count_controls(catalog: dict) -> int:
    """Count total controls in an OSCAL catalog document."""
    count = 0
    cat = catalog.get("catalog", {})
    for group in cat.get("groups", []):
        count += len(group.get("controls", []))
    count += len(cat.get("controls", []))
    return count
