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
    size: str | None = None  # deprecated, use firm_size instead
    firm_size: str | None = None
    threat_profile: str | None = None
    search: str | None = None


class RecommendedControl(BaseModel):
    """A control within a recommended framework blueprint."""
    scf_id: str
    title: str
    description: str | None = None
    domain_code: str | None = None
    relative_weighting: float | None = None
    cmm_level_0: str | None = None
    cmm_level_1: str | None = None
    cmm_level_2: str | None = None
    cmm_level_3: str | None = None
    cmm_level_4: str | None = None
    cmm_level_5: str | None = None
    solutions_micro_small: str | None = None
    solutions_small: str | None = None
    solutions_medium: str | None = None
    solutions_large: str | None = None
    solutions_enterprise: str | None = None


class FrameworkBlueprint(BaseModel):
    """A data-rich compliance blueprint for a recommended framework."""
    id: int
    code: str
    name: str
    category: str | None = None
    version_label: str | None = None
    is_scf: bool = False
    jurisdiction_codes: list[str] = []
    control_count: int = 0
    top_controls: list[RecommendedControl] = []


class FrameworkRecommendationResponse(BaseModel):
    """Recommended frameworks matching the provided context."""
    recommendations: list[FrameworkBlueprint]
    total: int
    applied_filters: list[str]
    firm_size: str | None = None
    threat_profile: str | None = None
    note: str | None = None


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
