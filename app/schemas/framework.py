"""Framework-related request/response Pydantic models."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class FrameworkBase(BaseModel):
    code: str
    name: str
    category: str | None = None
    description: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    is_scf: bool = False


class FrameworkResponse(FrameworkBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FrameworkListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str | None = None
    is_scf: bool = False
    version_count: int = 0
    control_count: int = 0


class FrameworkDetailResponse(FrameworkResponse):
    model_config = ConfigDict(from_attributes=True)
    versions: list["FrameworkVersionResponse"] = []
    jurisdiction_codes: list[str] = []
    related_framework_codes: list[str] = []


class FrameworkVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    framework_id: int
    version_label: str
    release_date: date | None = None
    status: str | None = None
    notes: str | None = None
    created_at: datetime | None = None


class FrameworkWithVersionResponse(BaseModel):
    """Framework + its active version info, used in recommendation contexts."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str | None = None
    version_label: str | None = None
    is_scf: bool = False


class FrameworkListResponse(BaseModel):
    items: list[FrameworkListItem]
    total: int
