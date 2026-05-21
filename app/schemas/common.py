"""Common Pydantic schemas shared across endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: str | None = None


class PaginatedResponse(BaseModel):
    """Generic paginated list response."""
    items: list[Any]
    total: int
    page: int = 1
    page_size: int = 50


class TimestampMixin(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
