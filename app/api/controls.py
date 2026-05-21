"""Control and mapping access API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.control import (
    AssessmentObjectiveResponse,
    CompensatingControlResponse,
    ControlDetailResponse,
    ControlMappingResponse,
    ControlResponse,
    EvidenceArtifactResponse,
)
from app.services.control_service import ControlService

router = APIRouter(prefix="/api/controls", tags=["Controls"])


@router.get("/{control_id}", response_model=ControlDetailResponse)
def get_control(
    control_id: int,
    session: Session = Depends(get_session),
):
    """Get full control detail including mapping counts."""
    svc = ControlService(session)
    detail = svc.get_control_detail(control_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Control not found")
    return ControlDetailResponse(**detail)


@router.get("/{control_id}/mappings", response_model=list[ControlMappingResponse])
def get_control_mappings(
    control_id: int,
    session: Session = Depends(get_session),
):
    """Get all framework mappings for a control."""
    svc = ControlService(session)
    if not svc.get_control(control_id):
        raise HTTPException(status_code=404, detail="Control not found")
    mappings = svc.get_mappings(control_id)
    return [ControlMappingResponse(**m) for m in mappings]


@router.get("/{control_id}/objectives", response_model=list[AssessmentObjectiveResponse])
def get_control_objectives(
    control_id: int,
    session: Session = Depends(get_session),
):
    """Get assessment objectives for a control."""
    svc = ControlService(session)
    if not svc.get_control(control_id):
        raise HTTPException(status_code=404, detail="Control not found")
    objectives = svc.get_assessment_objectives(control_id)
    return [AssessmentObjectiveResponse(
        id=o.id,
        objective_code=o.objective_code,
        objective_text=o.objective_text,
    ) for o in objectives]


@router.get("/{control_id}/evidence", response_model=list[EvidenceArtifactResponse])
def get_control_evidence(
    control_id: int,
    session: Session = Depends(get_session),
):
    """Get evidence artifacts for a control."""
    svc = ControlService(session)
    if not svc.get_control(control_id):
        raise HTTPException(status_code=404, detail="Control not found")
    artifacts = svc.get_evidence_artifacts(control_id)
    return [EvidenceArtifactResponse(
        id=a.id,
        erl_number=a.erl_number,
        evidence_title=a.evidence_title,
        evidence_description=a.evidence_description,
        evidence_type=a.evidence_type,
    ) for a in artifacts]


@router.get("/{control_id}/compensating-controls", response_model=list[CompensatingControlResponse])
def get_control_compensating(
    control_id: int,
    session: Session = Depends(get_session),
):
    """Get compensating controls for a control."""
    svc = ControlService(session)
    if not svc.get_control(control_id):
        raise HTTPException(status_code=404, detail="Control not found")
    comps = svc.get_compensating_controls(control_id)
    return [CompensatingControlResponse(
        id=c.id,
        compensating_control_id=c.compensating_control_id,
        compensating_control_title=c.compensating_control_title,
        compensating_control_description=c.compensating_control_description,
        compensation_type=c.compensation_type,
        justification=c.justification,
    ) for c in comps]
