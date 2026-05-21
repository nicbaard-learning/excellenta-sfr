"""Reference data API routes – jurisdictions, business models, domains."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.recommendation import (
    BusinessModelResponse,
    DomainResponse,
    JurisdictionResponse,
)
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/api", tags=["Reference"])


@router.get("/jurisdictions", response_model=list[JurisdictionResponse])
def list_jurisdictions(
    session: Session = Depends(get_session),
):
    """List all jurisdictions."""
    svc = RecommendationService(session)
    return [JurisdictionResponse(**j) for j in svc.list_jurisdictions()]


@router.get("/business-models", response_model=list[BusinessModelResponse])
def list_business_models(
    session: Session = Depends(get_session),
):
    """List all business models."""
    svc = RecommendationService(session)
    return [BusinessModelResponse(**m) for m in svc.list_business_models()]


@router.get("/domains", response_model=list[DomainResponse])
def list_domains(
    session: Session = Depends(get_session),
):
    """List all SCF domains."""
    svc = RecommendationService(session)
    return [DomainResponse(**d) for d in svc.list_domains()]
