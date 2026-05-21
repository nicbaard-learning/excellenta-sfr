"""Control-related request/response Pydantic models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ControlBase(BaseModel):
    scf_id: str
    title: str
    description: str | None = None
    control_question: str | None = None
    conformity_cadence: str | None = None
    relative_weighting: float | None = None
    applicability_context: str | None = None


class ControlResponse(ControlBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    domain_code: str | None = None
    domain_name: str | None = None
    principle_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ControlMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    framework_code: str
    framework_name: str
    mapped_control_id: str | None = None
    mapped_control_title: str | None = None
    mapping_type: str | None = None


class ControlDetailResponse(ControlResponse):
    mappings: list[ControlMappingResponse] = []
    objective_count: int = 0
    evidence_count: int = 0
    compensating_count: int = 0


class AssessmentObjectiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    objective_code: str | None = None
    objective_text: str | None = None


class EvidenceArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    erl_number: str | None = None
    evidence_title: str | None = None
    evidence_description: str | None = None
    evidence_type: str | None = None


class CompensatingControlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    compensating_control_id: str | None = None
    compensating_control_title: str | None = None
    compensating_control_description: str | None = None
    compensation_type: str | None = None
    justification: str | None = None


class ControlListResponse(BaseModel):
    items: list[ControlResponse]
    total: int
    framework_id: int | None = None
