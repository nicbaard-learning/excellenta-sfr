"""Maturity Assessment API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.maturity_service import MaturityService


class MaturityAssessmentRequest(BaseModel):
    """Request body for maturity assessment."""
    framework_name: str
    assessed_levels: dict[str, int]  # scf_id -> level (0-5)


class ComplianceDashboardRequest(BaseModel):
    """Request body for multi-framework compliance dashboard."""
    assessments: dict[str, dict[str, int]]  # framework_code -> {scf_id: level}


router = APIRouter(prefix="/api/maturity", tags=["Maturity Assessment"])


@router.get("/assess")
def assess_maturity(
    framework_id: int | None = Query(None),
    framework_name: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Get the maturity framework and scoring methodology for a framework.
    
    To compute actual scores, use the POST endpoint with assessed maturity levels.
    """
    svc = MaturityService(session)
    return svc.assess_framework_maturity(
        framework_id=framework_id,
        framework_name=framework_name,
    )


@router.post("/assess")
def assess_maturity_post(
    req: MaturityAssessmentRequest,
    session: Session = Depends(get_session),
):
    """Compute compliance score based on assessed maturity levels."""
    svc = MaturityService(session)
    return svc.assess_framework_maturity(
        framework_name=req.framework_name,
        assessed_levels=req.assessed_levels,
    )


@router.post("/dashboard")
def compliance_dashboard(
    req: ComplianceDashboardRequest,
    session: Session = Depends(get_session),
):
    """Generate a multi-framework compliance dashboard."""
    svc = MaturityService(session)
    return svc.compliance_dashboard(assessments=req.assessments)


@router.get("/levels")
def get_maturity_levels(
    session: Session = Depends(get_session),
):
    """Get the SCR-CMM maturity level definitions."""
    svc = MaturityService(session)
    return svc.get_maturity_level_descriptions()
