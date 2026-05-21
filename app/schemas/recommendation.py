"""Recommendation request/response Pydantic models for TPRM use cases."""

from pydantic import BaseModel

from app.schemas.framework import FrameworkWithVersionResponse


class FrameworkRecommendationRequest(BaseModel):
    """Request for framework recommendations based on vendor/profile attributes."""
    category: str | None = None
    business_model: str | None = None
    jurisdiction: str | None = None
    domain: str | None = None
    privacy_context: str | None = None
    size: str | None = None


class FrameworkRecommendationResponse(BaseModel):
    """Recommended frameworks matching the provided context."""
    recommendations: list[FrameworkWithVersionResponse]
    total: int
    applied_filters: list[str]


class CategoryFrameworkResponse(BaseModel):
    """Category-to-framework mappings."""
    category: str
    recommended_frameworks: list[FrameworkWithVersionResponse]


class JurisdictionResponse(BaseModel):
    id: int
    code: str
    name: str
    region: str | None = None


class BusinessModelResponse(BaseModel):
    id: int
    code: str
    name: str
    category: str | None = None


class DomainResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    control_count: int = 0
