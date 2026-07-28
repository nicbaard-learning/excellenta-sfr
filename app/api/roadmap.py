"""Compliance Roadmap API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
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

templates = Jinja2Templates(directory="app/templates")


@router.get("/print")
async def print_roadmap(
    request: Request,
    framework_name: str = Query(...),
    firm_size: str = Query("small"),
    focus_domain: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Render a print-optimized HTML page of the full roadmap.

    Open this in your browser and use Ctrl+P / Cmd+P → Save as PDF
    to export the complete roadmap with all implementation guidance.
    """
    svc = RoadmapService(session)
    data = svc.generate_roadmap(
        framework_name=framework_name,
        firm_size=firm_size,
        focus_domain=focus_domain,
    )
    return templates.TemplateResponse(
        "roadmap_print.html",
        {"request": request, "data": data},
    )


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
