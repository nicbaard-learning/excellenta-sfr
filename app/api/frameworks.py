"""Framework browsing API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.framework import (
    FrameworkDetailResponse,
    FrameworkListItem,
    FrameworkListResponse,
    FrameworkResponse,
    FrameworkVersionResponse,
)
from app.schemas.control import ControlListResponse, ControlResponse
from app.services.framework_service import FrameworkService
from app.services.control_service import ControlService

router = APIRouter(prefix="/api/frameworks", tags=["Frameworks"])


@router.get("", response_model=FrameworkListResponse)
def list_frameworks(
    category: str | None = Query(None, description="Filter by framework category"),
    session: Session = Depends(get_session),
):
    """List all compliance frameworks with summary counts."""
    svc = FrameworkService(session)
    frameworks = svc.list_frameworks(category=category)
    items = []
    for fw in frameworks:
        ver_count = len(svc.get_versions(fw.id))
        ctrl_count = svc.get_control_count(fw.id)
        items.append(FrameworkListItem(
            id=fw.id,
            code=fw.code,
            name=fw.name,
            category=fw.category,
            is_scf=fw.is_scf,
            version_count=ver_count,
            control_count=ctrl_count,
        ))
    return FrameworkListResponse(items=items, total=len(items))


@router.get("/{framework_id}", response_model=FrameworkDetailResponse)
def get_framework(
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Get full framework detail including versions and jurisdictions."""
    svc = FrameworkService(session)
    fw = svc.get_framework(framework_id)
    if not fw:
        raise HTTPException(status_code=404, detail="Framework not found")

    versions = svc.get_versions(framework_id)
    jurisdictions = svc.get_framework_jurisdictions(framework_id)
    related = svc.get_related_frameworks(framework_id)

    return FrameworkDetailResponse(
        id=fw.id,
        code=fw.code,
        name=fw.name,
        category=fw.category,
        description=fw.description,
        publisher=fw.publisher,
        source_url=fw.source_url,
        is_scf=fw.is_scf,
        created_at=fw.created_at,
        updated_at=fw.updated_at,
        versions=[FrameworkVersionResponse(
            id=v.id,
            framework_id=v.framework_id,
            version_label=v.version_label,
            release_date=v.release_date,
            status=v.status,
            notes=v.notes,
            created_at=v.created_at,
        ) for v in versions],
        jurisdiction_codes=[j.code for j in jurisdictions],
        related_framework_codes=[r.code for r in related],
    )


@router.get("/{framework_id}/versions", response_model=list[FrameworkVersionResponse])
def get_framework_versions(
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Get all versions of a framework."""
    svc = FrameworkService(session)
    if not svc.get_framework(framework_id):
        raise HTTPException(status_code=404, detail="Framework not found")
    versions = svc.get_versions(framework_id)
    return [FrameworkVersionResponse(
        id=v.id,
        framework_id=v.framework_id,
        version_label=v.version_label,
        release_date=v.release_date,
        status=v.status,
        notes=v.notes,
        created_at=v.created_at,
    ) for v in versions]


@router.get("/{framework_id}/related", response_model=list[FrameworkResponse])
def get_related_frameworks(
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Find frameworks related to the given one (via shared control mappings)."""
    svc = FrameworkService(session)
    if not svc.get_framework(framework_id):
        raise HTTPException(status_code=404, detail="Framework not found")
    related = svc.get_related_frameworks(framework_id)
    return [FrameworkResponse(
        id=fw.id,
        code=fw.code,
        name=fw.name,
        category=fw.category,
        description=fw.description,
        publisher=fw.publisher,
        source_url=fw.source_url,
        is_scf=fw.is_scf,
        created_at=fw.created_at,
        updated_at=fw.updated_at,
    ) for fw in related]


@router.get("/{framework_id}/controls", response_model=ControlListResponse)
def get_framework_controls(
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Get all controls mapped to a given framework."""
    svc = FrameworkService(session)
    if not svc.get_framework(framework_id):
        raise HTTPException(status_code=404, detail="Framework not found")
    controls = svc.get_controls_for_framework(framework_id)
    return ControlListResponse(
        items=[ControlResponse(
            id=c.id,
            scf_id=c.scf_id,
            title=c.title,
            description=c.description,
            control_question=c.control_question,
            conformity_cadence=c.conformity_cadence,
            relative_weighting=c.relative_weighting,
            applicability_context=c.applicability_context,
            domain_code=c.domain.code if c.domain else None,
            domain_name=c.domain.name if c.domain else None,
            principle_code=c.principle.code if c.principle else None,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ) for c in controls],
        total=len(controls),
        framework_id=framework_id,
    )
