"""Compliance Roadmap API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.roadmap_service import RoadmapService


class RoadmapRequest(BaseModel):
    """Request body for roadmap generation."""
    framework_name: str
    firm_size: str = "small"
    current_maturity: dict[str, int] | None = None
    focus_domain: str | None = None


router = APIRouter(prefix="/api/roadmap", tags=["Compliance Roadmap"])


@router.get("/generate")
def generate_roadmap(
    framework_id: int | None = Query(None),
    framework_name: str | None = Query(None),
    firm_size: str = Query("small"),
    focus_domain: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Generate a compliance roadmap (without maturity data for baseline view)."""
    svc = RoadmapService(session)
    return svc.generate_roadmap(
        framework_id=framework_id,
        framework_name=framework_name,
        firm_size=firm_size,
        focus_domain=focus_domain,
    )


@router.post("/generate")
def generate_roadmap_post(
    req: RoadmapRequest,
    session: Session = Depends(get_session),
):
    """Generate a compliance roadmap with maturity data."""
    svc = RoadmapService(session)
    return svc.generate_roadmap(
        framework_name=req.framework_name,
        firm_size=req.firm_size,
        current_maturity=req.current_maturity,
        focus_domain=req.focus_domain,
    )
