"""UI router – server-rendered HTML pages for the SFR internal browser.

This router provides read-only HTML pages that reuse the existing service
layer. The same service methods can later be wrapped as MCP tools.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_session
from app.services.comparison_service import ComparisonService
from app.services.control_service import ControlService
from app.services.framework_service import FrameworkService
from app.services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["UI"])


@router.get("/")
async def home(
    request: Request,
    session: Session = Depends(get_session),
):
    """New landing page – Compliance Intelligence Engine."""
    return templates.TemplateResponse(
        "home.html",
        {"request": request},
    )


@router.get("/evidence")
async def evidence_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Evidence Intelligence page."""
    return templates.TemplateResponse(
        "evidence.html",
        {"request": request},
    )


@router.get("/translate")
async def translate_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Framework Translation page."""
    return templates.TemplateResponse(
        "translate.html",
        {"request": request},
    )


@router.get("/maturity")
async def maturity_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Maturity Assessment page."""
    return templates.TemplateResponse(
        "maturity.html",
        {"request": request},
    )


@router.get("/roadmap")
async def roadmap_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Compliance Roadmap page."""
    return templates.TemplateResponse(
        "roadmap.html",
        {"request": request},
    )


@router.get("/risk-intelligence")
async def risk_intelligence_page(
    request: Request,
    session: Session = Depends(get_session),
):
    """Risk Intelligence page."""
    return templates.TemplateResponse(
        "risk_intelligence.html",
        {"request": request},
    )


@router.get("/about")
async def about(
    request: Request,
    session: Session = Depends(get_session),
):
    """About page with repository stats and description."""
    from sqlalchemy import text

    queries = {
        "total_controls": "SELECT COUNT(*) FROM controls",
        "total_frameworks": "SELECT COUNT(*) FROM frameworks",
        "scf_count": "SELECT COUNT(*) FROM frameworks WHERE is_scf",
        "total_mappings": "SELECT COUNT(*) FROM control_mappings",
        "total_domains": "SELECT COUNT(*) FROM domains",
        "total_objectives": "SELECT COUNT(*) FROM assessment_objectives",
        "total_evidence": "SELECT COUNT(*) FROM evidence_artifacts",
        "total_compensating": "SELECT COUNT(*) FROM compensating_control_links",
        "total_auth_sources": "SELECT COUNT(*) FROM authoritative_sources",
        "total_jurisdictions": "SELECT COUNT(*) FROM jurisdictions",
        "total_business_models": "SELECT COUNT(*) FROM business_models",
        "total_applicability_rules": "SELECT COUNT(*) FROM framework_applicability_rules",
        "total_threats": "SELECT COUNT(*) FROM threats",
        "total_risks": "SELECT COUNT(*) FROM risks",
    }

    stats = {}
    for key, q in queries.items():
        try:
            stats[key] = session.execute(text(q)).scalar() or 0
        except Exception:
            stats[key] = 0

    return templates.TemplateResponse(
        "about.html",
        {"request": request, "stats": stats},
    )



@router.get("/frameworks")
async def framework_list(
    request: Request,
    session: Session = Depends(get_session),
):
    """List all frameworks with summary counts."""
    svc = FrameworkService(session)
    frameworks = svc.list_frameworks()
    counts = svc.get_all_control_counts()
    items = []
    for fw in frameworks:
        items.append({
            "id": fw.id,
            "code": fw.code,
            "name": fw.name,
            "category": fw.category,
            "is_scf": fw.is_scf,
            "control_count": counts.get(fw.id, 0),
        })
    return templates.TemplateResponse(
        "frameworks_list.html",
        {"request": request, "frameworks": items, "total": len(items)},
    )


@router.get("/frameworks/{framework_id}")
async def framework_detail(
    request: Request,
    framework_id: int,
    session: Session = Depends(get_session),
):
    """Show framework detail with its mapped controls."""
    svc = FrameworkService(session)
    fw = svc.get_framework(framework_id)
    if not fw:
        return templates.TemplateResponse(
            "framework_detail.html",
            {"request": request, "fw": None, "controls": [], "versions": [],
             "jurisdiction_codes": [], "related": [],
             "error": "Framework not found"},
            status_code=404,
        )

    versions = svc.get_versions(framework_id)
    jurisdictions = svc.get_framework_jurisdictions(framework_id)
    related = svc.get_related_frameworks(framework_id)
    controls = svc.get_controls_for_framework(framework_id)

    control_list = []
    for c in controls:
        control_list.append({
            "id": c.id,
            "scf_id": c.scf_id,
            "title": c.title,
            "domain_code": c.domain.code if c.domain else None,
            "domain_name": c.domain.name if c.domain else None,
            "relative_weighting": float(c.relative_weighting) if c.relative_weighting else None,
        })

    related_list = []
    for r in related:
        related_list.append({"id": r.id, "code": r.code, "name": r.name})

    return templates.TemplateResponse(
        "framework_detail.html",
        {
            "request": request,
            "fw": {
                "id": fw.id,
                "code": fw.code,
                "name": fw.name,
                "category": fw.category,
                "description": fw.description,
                "publisher": fw.publisher,
                "source_url": fw.source_url,
                "is_scf": fw.is_scf,
            },
            "controls": control_list,
            "versions": [{"id": v.id, "version_label": v.version_label} for v in versions],
            "jurisdiction_codes": [j.code for j in jurisdictions],
            "related": related_list,
        },
    )


@router.get("/controls/{control_id}")
async def control_detail(
    request: Request,
    control_id: str,
    session: Session = Depends(get_session),
):
    """Show full control detail with mappings, objectives, evidence, compensating.

    Accepts both numeric control IDs (e.g. /controls/42) and SCF # strings
    (e.g. /controls/AAT-01) for flexible linking from translate results.
    """
    ctrl_svc = ControlService(session)

    # Try lookup by integer ID first, then by SCF # string
    ctrl = None
    try:
        ctrl = ctrl_svc.get_control(int(control_id))
    except ValueError:
        pass

    if ctrl is None:
        ctrl = ctrl_svc.get_control_by_scf_id(control_id)

    if not ctrl:
        return templates.TemplateResponse(
            "control_detail.html",
            {"request": request, "control": None, "mappings": [],
             "objectives": [], "evidence": [], "compensating": [],
             "auth_sources": [],
             "error": "Control not found"},
            status_code=404,
        )

    ctrl_id = ctrl.id
    mappings = ctrl_svc.get_mappings(ctrl_id)
    objectives = ctrl_svc.get_assessment_objectives(ctrl_id)
    evidence = ctrl_svc.get_evidence_artifacts(ctrl_id)
    compensating = ctrl_svc.get_compensating_controls(ctrl_id)
    auth_sources = ctrl_svc.get_authoritative_sources(ctrl_id)

    control_data = {
        "id": ctrl.id,
        "scf_id": ctrl.scf_id,
        "title": ctrl.title,
        "description": ctrl.description,
        "control_question": ctrl.control_question,
        "conformity_cadence": ctrl.conformity_cadence,
        "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
        "relative_weight": ctrl.relative_weight,
        "pptdf_applicability": ctrl.pptdf_applicability,
        "applicability_context": ctrl.applicability_context,
        "domain_code": ctrl.domain.code if ctrl.domain else None,
        "domain_name": ctrl.domain.name if ctrl.domain else None,
        # Firm-size solutions
        "solutions_micro_small": ctrl.solutions_micro_small,
        "solutions_small": ctrl.solutions_small,
        "solutions_medium": ctrl.solutions_medium,
        "solutions_large": ctrl.solutions_large,
        "solutions_enterprise": ctrl.solutions_enterprise,
        # SCR-CMM Maturity levels
        "cmm_level_0": ctrl.cmm_level_0,
        "cmm_level_1": ctrl.cmm_level_1,
        "cmm_level_2": ctrl.cmm_level_2,
        "cmm_level_3": ctrl.cmm_level_3,
        "cmm_level_4": ctrl.cmm_level_4,
        "cmm_level_5": ctrl.cmm_level_5,
    }

    # Map objectives to dicts
    objective_list = [{"id": o.id, "objective_code": o.objective_code,
                       "objective_text": o.objective_text} for o in objectives]

    evidence_list = [{"id": a.id, "erl_number": a.erl_number,
                      "evidence_title": a.evidence_title,
                      "evidence_description": a.evidence_description,
                      "evidence_type": a.evidence_type} for a in evidence]

    compensating_list = [{"id": cp.id,
                          "compensating_control_id": cp.compensating_control_id,
                          "compensating_control_title": cp.compensating_control_title,
                          "compensating_control_description": cp.compensating_control_description,
                          "compensation_type": cp.compensation_type,
                          "justification": cp.justification} for cp in compensating]

    auth_source_list = [{
        "id": a.id,
        "source_title": a.source_title,
        "source_url": a.source_url,
        "source_organization": a.source_organization,
        "reference_number": a.reference_number,
    } for a in auth_sources]

    return templates.TemplateResponse(
        "control_detail.html",
        {
            "request": request,
            "control": control_data,
            "mappings": mappings,
            "objectives": objective_list,
            "evidence": evidence_list,
            "compensating": compensating_list,
            "auth_sources": auth_source_list,
        },
    )


@router.get("/recommend")
async def recommend_frameworks(
    request: Request,
    jurisdiction: str | None = Query(None),
    business_model: str | None = Query(None),
    category: str | None = Query(None),
    firm_size: str | None = Query(None),
    threat_profile: str | None = Query(None),
    search: str | None = Query(None),
    session: Session = Depends(get_session),
):
    """Recommend frameworks based on context, with select-to-compare flow."""
    rec_svc = RecommendationService(session)

    jurisdictions = rec_svc.list_jurisdictions()
    business_models = rec_svc.list_business_models()
    categories = rec_svc.list_categories()

    has_query = bool(jurisdiction or business_model or category or firm_size or threat_profile or search)
    recommendations = None
    applied_filters = []
    recommended_ids = set()
    error = None
    selected_jurisdiction = jurisdiction
    selected_business_model = business_model
    selected_category = category
    selected_firm_size = firm_size
    selected_threat_profile = threat_profile
    selected_search = search

    if has_query:
        try:
            result = rec_svc.recommend_by_context(
                jurisdiction=jurisdiction,
                business_model=business_model,
                category=category,
                firm_size=firm_size,
                threat_profile=threat_profile,
                search=search,
            )
            recommendations = result["recommendations"]
            applied_filters = result["applied_filters"]
            recommended_ids = {fw["id"] for fw in recommendations}
        except Exception as exc:
            error = str(exc)
            recommendations = []

    return templates.TemplateResponse(
        "recommend.html",
        {
            "request": request,
            "jurisdictions": jurisdictions,
            "business_models": business_models,
            "categories": categories,
            "has_query": has_query,
            "selected_jurisdiction": selected_jurisdiction,
            "selected_business_model": selected_business_model,
            "selected_category": selected_category,
            "selected_firm_size": selected_firm_size,
            "selected_threat_profile": selected_threat_profile,
            "selected_search": selected_search,
            "recommendations": recommendations,
            "applied_filters": applied_filters,
            "recommended_ids": recommended_ids,
            "error": error,
        },
    )


@router.get("/compare")
async def compare_frameworks(
    request: Request,
    fw1: int | None = Query(None),
    fw2: int | None = Query(None),
    session: Session = Depends(get_session),
):
    """Compare two frameworks — show overlap, gaps, and differences."""
    fw_svc = FrameworkService(session)
    all_frameworks = []
    for fw in fw_svc.list_frameworks():
        all_frameworks.append({
            "id": fw.id,
            "code": fw.code,
            "name": fw.name,
        })

    result = None
    if fw1 and fw2 and fw1 != fw2:
        comp_svc = ComparisonService(session)
        try:
            raw = comp_svc.compare([fw1, fw2])
            result = {
                "framework_ids": raw["framework_ids"],
                "framework_names": raw["framework_names"],
                "overlap_count": raw["overlap_count"],
                "overlapping_controls": [
                    {"id": c.id, "scf_id": c.scf_id, "title": c.title}
                    for c in raw["overlapping_controls"]
                ],
                "gap_controls": {
                    fid: [
                        {"id": c.id, "scf_id": c.scf_id, "title": c.title}
                        for c in controls
                    ]
                    for fid, controls in raw["gap_controls"].items()
                },
                "unique_control_count": raw["unique_control_count"],
            }
        except ValueError as exc:
            result = {"error": str(exc)}

    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "all_frameworks": all_frameworks,
            "fw1_id": fw1,
            "fw2_id": fw2,
            "result": result,
        },
    )
