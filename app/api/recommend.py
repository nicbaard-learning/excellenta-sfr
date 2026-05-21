"""Recommendation and applicability API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.recommendation import (
    BusinessModelResponse,
    DomainResponse,
    FrameworkRecommendationRequest,
    FrameworkRecommendationResponse,
    JurisdictionResponse,
)
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/api/recommend", tags=["Recommend"])


@router.post("/frameworks", response_model=FrameworkRecommendationResponse)
def recommend_frameworks(
    req: FrameworkRecommendationRequest,
    session: Session = Depends(get_session),
):
    """Get framework recommendations based on vendor/profile attributes."""
    svc = RecommendationService(session)
    result = svc.recommend_by_context(
        category=req.category,
        business_model=req.business_model,
        jurisdiction=req.jurisdiction,
        domain=req.domain,
        privacy_context=req.privacy_context,
        size=req.size,
    )
    return FrameworkRecommendationResponse(**result)


@router.get("/jurisdictions", response_model=list[JurisdictionResponse])
def list_jurisdictions(
    session: Session = Depends(get_session),
):
    """List all jurisdictions."""
    svc = RecommendationService(session)
    jurisdictions = svc.list_jurisdictions()
    return [JurisdictionResponse(**j) for j in jurisdictions]


@router.get("/business-models", response_model=list[BusinessModelResponse])
def list_business_models(
    session: Session = Depends(get_session),
):
    """List all business models (TPRM vendor categories)."""
    svc = RecommendationService(session)
    models = svc.list_business_models()
    return [BusinessModelResponse(**m) for m in models]


@router.get("/domains", response_model=list[DomainResponse])
def list_domains(
    session: Session = Depends(get_session),
):
    """List all SCF domains with control counts."""
    svc = RecommendationService(session)
    domains = svc.list_domains()
    return [DomainResponse(**d) for d in domains]
