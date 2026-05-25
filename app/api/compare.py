"""Comparison and GRC API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.comparison import (
    DeduplicatedControlSetResponse,
    FrameworkCompareRequest,
    FrameworkCompareResponse,
    FrameworkDifferenceResponse,
    FrameworkIntersectionResponse,
)
from app.services.comparison_service import ComparisonService

router = APIRouter(prefix="/api/compare", tags=["Compare"])


@router.post("/frameworks", response_model=FrameworkCompareResponse)
def compare_frameworks(
    req: FrameworkCompareRequest,
    session: Session = Depends(get_session),
):
    """Compare two or more frameworks – returns overlap and gaps."""
    if len(req.framework_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two framework IDs are required")
    svc = ComparisonService(session)
    try:
        result = svc.compare(req.framework_ids)
        # Convert ORM objects to dicts for the response model
        result["overlapping_controls"] = [
            _control_to_dict(c) for c in result["overlapping_controls"]
        ]
        result["gap_controls"] = {
            str(fid): [_control_to_dict(c) for c in controls]
            for fid, controls in result["gap_controls"].items()
        }
        return FrameworkCompareResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/intersection", response_model=FrameworkIntersectionResponse)
def compare_intersection(
    req: FrameworkCompareRequest,
    session: Session = Depends(get_session),
):
    """Return the intersection (overlapping controls) of selected frameworks."""
    if len(req.framework_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two framework IDs are required")
    svc = ComparisonService(session)
    try:
        result = svc.intersection(req.framework_ids, domain_code=req.domain)
        result["common_controls"] = [_control_to_dict(c) for c in result["common_controls"]]
        return FrameworkIntersectionResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/differences", response_model=FrameworkDifferenceResponse)
def compare_differences(
    req: FrameworkCompareRequest,
    session: Session = Depends(get_session),
):
    """Return differences between the first two frameworks in the request."""
    if len(req.framework_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two framework IDs are required")
    svc = ComparisonService(session)
    try:
        result = svc.differences(req.framework_ids[0], req.framework_ids[1], domain_code=req.domain)
        result["in_base_not_compare"] = [_control_to_dict(c) for c in result["in_base_not_compare"]]
        result["in_compare_not_base"] = [_control_to_dict(c) for c in result["in_compare_not_base"]]
        return FrameworkDifferenceResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/common-controls", response_model=DeduplicatedControlSetResponse)
def compare_common_controls(
    req: FrameworkCompareRequest,
    session: Session = Depends(get_session),
):
    """Return deduplicated common controls with mapping details."""
    if len(req.framework_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two framework IDs are required")
    svc = ComparisonService(session)
    try:
        result = svc.common_control_set(req.framework_ids, domain_code=req.domain)
        return DeduplicatedControlSetResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _control_to_dict(c) -> dict:
    return {
        "id": c.id,
        "scf_id": c.scf_id,
        "title": c.title,
        "description": c.description,
        "control_question": c.control_question,
        "conformity_cadence": c.conformity_cadence,
        "relative_weighting": float(c.relative_weighting) if c.relative_weighting else None,
        "applicability_context": c.applicability_context,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }
