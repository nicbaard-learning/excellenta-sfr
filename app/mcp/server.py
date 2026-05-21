"""MCP (Model Context Protocol) server for the SFR Shared Framework Repository.

Provides AI-agent-friendly tools over the existing repository logic.
Supports two transport modes:
  - stdio (default): for Claude Desktop, Cursor, Windsurf, etc.
  - SSE: for remote HTTP access when mounted inside the FastAPI app.

Run locally:
    python -m app.mcp.server                           # stdio (CLI)
    uvicorn app.main:app --reload                       # SSE at http://localhost:8000/mcp
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from app.database import SessionLocal
from app.mcp.resolver import resolve_framework_id, resolve_frameworks
from app.services.comparison_service import ComparisonService
from app.services.control_service import ControlService
from app.services.framework_service import FrameworkService
from app.services.recommendation_service import RecommendationService

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sfr.mcp")

# ── Server ────────────────────────────────────────────────────────────
mcp = FastMCP(
    "SFR – Shared Framework Repository",
)


# ── Helper ────────────────────────────────────────────────────────────
def _get_session():
    """Create and return a new database session."""
    return SessionLocal()


# ═══════════════════════════════════════════════════════════════════════
# Tool 1: get_applicable_frameworks
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="get_applicable_frameworks",
    description=(
        "Recommend compliance frameworks applicable to a company or vendor "
        "based on context attributes. Use this to answer questions like "
        "'What frameworks apply to a South African SaaS company?' or "
        "'What privacy frameworks apply in the US?'"
    ),
)
def get_applicable_frameworks(
    category: str | None = None,
    business_model: str | None = None,
    jurisdiction: str | None = None,
    domain: str | None = None,
    privacy_context: str | None = None,
    size: str | None = None,
) -> dict:
    """Recommend frameworks matching the provided context.

    Args:
        category: Framework category (e.g. "international", "industry", "regulatory").
        business_model: Business model / vendor category (e.g. "SAAS", "IAAS", "MSP").
        jurisdiction: Jurisdiction code or name (e.g. "ZA", "US", "EU").
        domain: SCF domain code or name (e.g. "AC", "AU", "IA").
        privacy_context: Privacy-context flag (e.g. "privacy", "security").
        size: Organisation size (e.g. "small", "medium", "large").

    Returns:
        A dict with "recommendations" (list of frameworks with id/code/name/category),
        "total" count, and "applied_filters" summary.
    """
    session = _get_session()
    try:
        svc = RecommendationService(session)
        result = svc.recommend_by_context(
            category=category,
            business_model=business_model,
            jurisdiction=jurisdiction,
            domain=domain,
            privacy_context=privacy_context,
            size=size,
        )
        return result
    except Exception as exc:
        logger.exception("get_applicable_frameworks failed")
        return {"error": str(exc), "recommendations": [], "total": 0, "applied_filters": []}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 2: get_framework_details
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="get_framework_details",
    description=(
        "Retrieve detailed metadata for a compliance framework. "
        "Provide either framework_id (numeric) or framework_name (natural name like "
        "'ISO 27001', 'PCI-DSS', 'POPIA', 'NIST CSF', 'GDPR'). "
        "Returns description, publisher, versions, jurisdictions, and related frameworks."
    ),
)
def get_framework_details(
    framework_id: int | None = None,
    framework_name: str | None = None,
) -> dict:
    """Get full framework details by ID or name.

    Args:
        framework_id: Internal numeric framework ID.
        framework_name: Natural framework name (e.g. "ISO 27001", "PCI-DSS", "POPIA").

    Returns:
        Framework metadata including description, publisher, versions, jurisdictions.
    """
    if not framework_id and not framework_name:
        return {"error": "Provide either framework_id or framework_name."}

    session = _get_session()
    try:
        resolved_id = resolve_framework_id(session, framework_name=framework_name, framework_id=framework_id)
        if resolved_id is None:
            return {
                "error": f"Framework not found: '{framework_name or framework_id}'",
                "framework_id": framework_id,
                "framework_name": framework_name,
            }

        fw_svc = FrameworkService(session)
        fw = fw_svc.get_framework(resolved_id)
        if not fw:
            return {"error": f"Framework with id {resolved_id} not found in database."}

        versions = fw_svc.get_versions(resolved_id)
        jurisdictions = fw_svc.get_framework_jurisdictions(resolved_id)
        related = fw_svc.get_related_frameworks(resolved_id)

        return {
            "id": fw.id,
            "code": fw.code,
            "name": fw.name,
            "category": fw.category,
            "description": fw.description,
            "publisher": fw.publisher,
            "source_url": fw.source_url,
            "is_scf": fw.is_scf,
            "versions": [
                {
                    "version_label": v.version_label,
                    "release_date": v.release_date.isoformat() if v.release_date else None,
                    "status": v.status,
                    "notes": v.notes,
                }
                for v in versions
            ],
            "jurisdictions": [
                {"code": j.code, "name": j.name, "region": j.region} for j in jurisdictions
            ],
            "related_frameworks": [{"code": r.code, "name": r.name} for r in related],
        }
    except Exception as exc:
        logger.exception("get_framework_details failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 3: get_framework_controls
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="get_framework_controls",
    description=(
        "List controls mapped to a compliance framework. "
        "Provide either framework_id or framework_name (e.g. 'PCI-DSS', 'ISO 27001'). "
        "Use this to answer questions like 'Show me the controls for PCI-DSS'."
    ),
)
def get_framework_controls(
    framework_id: int | None = None,
    framework_name: str | None = None,
    limit: int | None = 100,
) -> dict:
    """Get controls mapped to a framework.

    Args:
        framework_id: Internal numeric framework ID.
        framework_name: Natural framework name (e.g. "ISO 27001", "PCI-DSS", "NIST CSF").
        limit: Maximum number of controls to return (default 100, max 500).

    Returns:
        A list of controls with scf_id, title, description, domain, and principle info.
    """
    if not framework_id and not framework_name:
        return {"error": "Provide either framework_id or framework_name."}

    limit = min(limit, 500) if limit else 100

    session = _get_session()
    try:
        resolved_id = resolve_framework_id(session, framework_name=framework_name, framework_id=framework_id)
        if resolved_id is None:
            return {"error": f"Framework not found: '{framework_name or framework_id}'"}

        fw_svc = FrameworkService(session)
        fw = fw_svc.get_framework(resolved_id)
        if not fw:
            return {"error": f"Framework with id {resolved_id} not found."}

        controls = fw_svc.get_controls_for_framework(resolved_id)

        limited = controls[:limit]
        return {
            "framework_id": resolved_id,
            "framework_code": fw.code,
            "framework_name": fw.name,
            "total_controls": len(controls),
            "returned": len(limited),
            "controls": [
                {
                    "id": c.id,
                    "scf_id": c.scf_id,
                    "title": c.title,
                    "description": c.description[:500] if c.description else None,
                    "control_question": c.control_question[:300] if c.control_question else None,
                    "domain_code": c.domain.code if c.domain else None,
                    "domain_name": c.domain.name if c.domain else None,
                    "principle_code": c.principle.code if c.principle else None,
                }
                for c in limited
            ],
        }
    except Exception as exc:
        logger.exception("get_framework_controls failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 4: compare_frameworks
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="compare_frameworks",
    description=(
        "Compare two or more compliance frameworks to find overlapping controls, "
        "gaps, or differences. Use this to answer questions like "
        "'Compare ISO 27001 and NIST CSF' or 'What overlaps between POPIA and GDPR?'."
    ),
)
def compare_frameworks(
    framework_ids: list[int] | None = None,
    framework_names: list[str] | None = None,
    mode: str = "intersection",
) -> dict:
    """Compare frameworks to find overlaps and differences.

    Args:
        framework_ids: List of framework IDs to compare (provide this or framework_names).
        framework_names: List of natural framework names to compare (e.g. ["ISO 27001", "NIST CSF"]).
        mode: Comparison mode:
            - "intersection" (default): return only the controls common to ALL frameworks.
            - "differences": return controls in one but not the other (requires exactly 2 frameworks).
            - "common_controls": detailed common controls with per-framework mapping info.

    Returns:
        Comparison results depending on mode.
    """
    if not framework_ids and not framework_names:
        return {"error": "Provide either framework_ids or framework_names."}

    mode = mode.lower()
    if mode not in ("intersection", "differences", "common_controls"):
        return {
            "error": f"Invalid mode '{mode}'. Choose: intersection, differences, common_controls."
        }

    session = _get_session()
    try:
        ids = resolve_frameworks(session, framework_names=framework_names, framework_ids=framework_ids)
        if ids is None:
            return {"error": "Could not resolve one or more framework names to known frameworks."}

        if len(ids) < 2:
            return {"error": "At least two frameworks are required for comparison."}

        if mode == "differences" and len(ids) != 2:
            return {"error": "Differences mode requires exactly two frameworks."}

        comp_svc = ComparisonService(session)

        if mode == "intersection":
            result = comp_svc.intersection(ids)
            # Convert ORM objects to dicts
            result["common_controls"] = [
                {
                    "id": c.id,
                    "scf_id": c.scf_id,
                    "title": c.title,
                    "description": c.description[:300] if c.description else None,
                    "control_question": c.control_question[:200] if c.control_question else None,
                    "domain_code": c.domain.code if c.domain else None,
                    "principle_code": c.principle.code if c.principle else None,
                }
                for c in result["common_controls"]
            ]
            return result

        elif mode == "differences":
            result = comp_svc.differences(ids[0], ids[1])
            result["in_base_not_compare"] = [
                {
                    "id": c.id,
                    "scf_id": c.scf_id,
                    "title": c.title,
                    "description": c.description[:300] if c.description else None,
                    "domain_code": c.domain.code if c.domain else None,
                }
                for c in result["in_base_not_compare"]
            ]
            result["in_compare_not_base"] = [
                {
                    "id": c.id,
                    "scf_id": c.scf_id,
                    "title": c.title,
                    "description": c.description[:300] if c.description else None,
                    "domain_code": c.domain.code if c.domain else None,
                }
                for c in result["in_compare_not_base"]
            ]
            return result

        elif mode == "common_controls":
            result = comp_svc.common_control_set(ids)
            # The common_control_set already returns dicts with control + mappings
            # But the "control" key has ORM objects - let's convert them
            for item in result["controls"]:
                ctrl = item["control"]
                item["control"] = {
                    "id": ctrl.id,
                    "scf_id": ctrl.scf_id,
                    "title": ctrl.title,
                    "description": ctrl.description[:300] if ctrl.description else None,
                    "domain_code": ctrl.domain.code if ctrl.domain else None,
                }
            return result

    except Exception as exc:
        logger.exception("compare_frameworks failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# SSE transport ASGI app (for mounting inside FastAPI)
# ═══════════════════════════════════════════════════════════════════════
def create_sse_app():
    """Return the MCP server as a Starlette ASGI app for SSE transport.

    Mount this inside the FastAPI app:

        from app.mcp.server import create_sse_app
        app.mount("/mcp", create_sse_app())

    The MCP client connects via GET /mcp/sse and sends messages via POST /mcp/messages.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Mount

    sse = mcp.sse_app()

    return Starlette(
        routes=[
            Mount("/", app=sse),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
        allowed_hosts=["*"],  # Accept all hosts; for production, restrict to your domain
    )


# ═══════════════════════════════════════════════════════════════════════
# Entry point (stdio)
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("Starting SFR MCP server (stdio transport)...")
    mcp.run()
