"""Recommendation and applicability API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.recommendation import (
    BusinessModelResponse,
    DomainResponse,
    FrameworkRecommendationRequest,
    FrameworkRecommendationResponse,
    JurisdictionResponse,
)
from app.services.recommendation_service import RecommendationInputError, RecommendationService

router = APIRouter(prefix="/api/recommend", tags=["Recommend"])


@router.post("/frameworks", response_model=FrameworkRecommendationResponse)
def recommend_frameworks(
    req: FrameworkRecommendationRequest,
    session: Session = Depends(get_session),
):
    """Get framework recommendations based on vendor/profile attributes.

    Returns data-rich compliance blueprints with:
    - Framework metadata and jurisdiction mappings
    - Top controls with maturity levels (SCR-CMM) and firm-size solutions
    - Applied filter summary

    `jurisdiction` is a hard filter: results are frameworks specific to that
    jurisdiction (`scope="jurisdiction"`) plus global frameworks
    (`scope="global"`), never frameworks for other jurisdictions. Other
    filters are relaxed if their combination matches nothing.

    Returns 422 for an unknown jurisdiction or a request with no filters.
    """
    svc = RecommendationService(session)
    try:
        result = svc.recommend_by_context(
            category=req.category,
            business_model=req.business_model,
            jurisdiction=req.jurisdiction,
            domain=req.domain,
            privacy_context=req.privacy_context,
            size=req.size,
            firm_size=req.firm_size,
            threat_profile=req.threat_profile,
            search=req.search,
            max_controls=req.max_controls,
        )
    except RecommendationInputError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict())
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
