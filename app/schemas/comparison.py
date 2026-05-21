"""Comparison request/response Pydantic models for GRC use cases."""

from pydantic import BaseModel

from app.schemas.control import ControlResponse, ControlMappingResponse


class FrameworkCompareRequest(BaseModel):
    """Request to compare two or more frameworks."""
    framework_ids: list[int]
    include_objectives: bool = False
    include_evidence: bool = False
    include_mappings: bool = True


class FrameworkCompareResponse(BaseModel):
    """Comparison result showing overlapping and gap controls."""
    framework_ids: list[int]
    framework_names: dict[int, str]
    overlap_count: int
    overlapping_controls: list[ControlResponse]
    gap_controls: dict[int, list[ControlResponse]]
    unique_control_count: dict[int, int]


class FrameworkIntersectionResponse(BaseModel):
    """Deduplicated common control set across selected frameworks."""
    framework_ids: list[int]
    framework_names: dict[int, str]
    total_common_controls: int
    common_controls: list[ControlResponse]


class FrameworkDifferenceResponse(BaseModel):
    """Framework-specific gaps / differences."""
    base_framework_id: int
    base_framework_name: str
    compare_framework_id: int
    compare_framework_name: str
    in_base_not_compare: list[ControlResponse]
    in_compare_not_base: list[ControlResponse]
    base_count: int
    compare_count: int


class CommonControlSetResponse(BaseModel):
    """Deduplicated common control set with mapping details."""
    control: ControlResponse
    mappings: dict[int, ControlMappingResponse]
    frameworks_present: list[int]


class DeduplicatedControlSetResponse(BaseModel):
    """Full deduplicated set for multiple frameworks."""
    framework_ids: list[int]
    framework_names: dict[int, str]
    total_controls: int
    controls: list[CommonControlSetResponse]
