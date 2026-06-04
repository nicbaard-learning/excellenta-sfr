"""Risk Intelligence API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.risk_intelligence_service import RiskIntelligenceService

router = APIRouter(prefix="/api/risk-intelligence", tags=["Risk Intelligence"])


@router.get("/find-controls")
def find_controls_for_risk(
    risk_id: int | None = Query(None),
    risk_keyword: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Find controls that mitigate a specific risk."""
    svc = RiskIntelligenceService(session)
    return svc.find_controls_for_risk(risk_id=risk_id, risk_keyword=risk_keyword)


@router.get("/heat-map")
def get_risk_heat_map(
    risk_grouping: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Generate a risk heat map by risk grouping."""
    svc = RiskIntelligenceService(session)
    return svc.generate_risk_heat_map(risk_grouping=risk_grouping)


@router.get("/residual-risk")
def get_residual_risk_report(
    framework_id: int | None = Query(None),
    framework_name: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Generate a residual risk report for a framework.
    
    Note: To include assessed maturity data, use POST endpoint.
    """
    svc = RiskIntelligenceService(session)
    return svc.residual_risk_report(
        framework_id=framework_id,
        framework_name=framework_name,
    )
