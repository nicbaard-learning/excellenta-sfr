"""Evidence Intelligence API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.evidence_service import EvidenceIntelligenceService

router = APIRouter(prefix="/api/evidence", tags=["Evidence Intelligence"])


@router.get("/checklist")
def get_evidence_checklist(
    framework_id: int | None = Query(None),
    framework_name: str | None = Query(None),
    control_id: int | None = Query(None),
    firm_size: str | None = Query(None),
    domain: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Generate an evidence checklist for a framework or specific control."""
    svc = EvidenceIntelligenceService(session)
    if control_id:
        return svc.generate_control_evidence_checklist(control_id)
    return svc.generate_framework_evidence_checklist(
        framework_id=framework_id,
        framework_name=framework_name,
        firm_size=firm_size,
        domain=domain,
    )


@router.get("/examples")
def get_evidence_examples(
    evidence_type: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Get examples of strong vs weak evidence from the repository."""
    svc = EvidenceIntelligenceService(session)
    return svc.get_evidence_examples(evidence_type=evidence_type)


@router.get("/audit-pack")
def get_audit_preparation_pack(
    framework_id: int | None = Query(None),
    framework_name: str | None = Query(None),
    domain: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Generate a comprehensive audit preparation pack for a framework."""
    svc = EvidenceIntelligenceService(session)
    return svc.generate_audit_preparation_pack(
        framework_id=framework_id,
        framework_name=framework_name,
        domain=domain,
    )
