"""Framework Translation API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.translation_service import TranslationService

router = APIRouter(prefix="/api/translate", tags=["Framework Translation"])


@router.get("/framework")
def translate_framework(
    source_framework_id: int | None = Query(None),
    source_framework_name: str | None = Query(None),
    target_framework_id: int | None = Query(None),
    target_framework_name: str | None = Query(None),
    domain: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Translate controls from one framework to another via SCF pivot."""
    svc = TranslationService(session)
    return svc.translate_framework(
        source_framework_id=source_framework_id,
        source_framework_name=source_framework_name,
        target_framework_id=target_framework_id,
        target_framework_name=target_framework_name,
        domain=domain,
    )


@router.get("/control-equivalents")
def find_control_equivalents(
    scf_id: str | None = Query(None),
    control_id: int | None = Query(None),
    session: Session = Depends(get_session),
):
    """Find equivalent controls across all frameworks for a given control."""
    svc = TranslationService(session)
    return svc.find_control_equivalents(scf_id=scf_id, control_id=control_id)
