from __future__ import annotations

"""MCP (Model Context Protocol) server for the SFR Shared Framework Repository.

Provides AI-agent-friendly tools over the existing repository logic.
Supports two transport modes:
    - stdio (default): for Claude Desktop, Cursor, Windsurf, etc.
    - SSE: for remote HTTP access when mounted inside the FastAPI app.

Run locally:
        python -m app.mcp.server                           # stdio (CLI)
        uvicorn app.main:app --reload                       # SSE at http://localhost:8000/mcp
"""

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import TransportSecuritySettings

from app.config import settings
from app.database import SessionLocal
from app.mcp.resolver import resolve_framework_id, resolve_frameworks
from app.services.comparison_service import ComparisonService
from app.services.control_service import ControlService
from app.services.framework_service import FrameworkService
from app.services.recommendation_service import RecommendationService
from app.services.evidence_service import EvidenceIntelligenceService
from app.services.translation_service import TranslationService
from app.services.maturity_service import MaturityService
from app.services.roadmap_service import RoadmapService
from app.services.risk_intelligence_service import RiskIntelligenceService

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
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.mcp_allowed_hosts_list,
        allowed_origins=settings.mcp_allowed_origins_list,
    ),
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
        "\n\n"
        "STRATEGY FOR USING THIS TOOL:\n"
        "1. Start with just `business_model` — that's the most reliable filter.\n"
        "2. If the results are too broad, call again with additional filters like\n"
        "   `firm_size`, `jurisdiction`, or `privacy_context`.\n"
        "3. If you can't cleanly map a natural-language description to one of the\n"
        "   structured parameters, use the `search` parameter for free-text matching\n"
        "   against framework names, descriptions, and publishers.\n"
        "4. Jurisdiction accepts ISO codes (\"US\", \"ZA\"), country names \n"
        "   (\"United States\"), or region names (\"NA\", \"North America\")."
    ),
)
def get_applicable_frameworks(
    category: str | None = None,
    business_model: str | None = None,
    jurisdiction: str | None = None,
    domain: str | None = None,
    privacy_context: str | None = None,
    size: str | None = None,
    firm_size: str | None = None,
    threat_profile: str | None = None,
    search: str | None = None,
) -> dict:
    """Recommend frameworks matching the provided context.

    Returns data-rich compliance blueprints including framework metadata,
    jurisdiction mappings, top controls with maturity levels (SCR-CMM),
    and firm-size solutions.

    Args:
        business_model: Business model / vendor category (e.g. "SAAS", "IAAS", "MSP").
            Start here — it's the most reliable way to get recommendations.
        jurisdiction: Jurisdiction code, name, or region
            (e.g. "US", "United States", "NA", "North America").
        category: Framework category (e.g. "international", "industry", "regulatory").
        domain: SCF domain code or name (e.g. "AC", "AU", "IA").
        privacy_context: Privacy-context flag (e.g. "privacy", "security").
        size: Organisation size (deprecated, use firm_size).
        firm_size: Organisation size (e.g. "micro", "small", "medium", "large", "enterprise").
        threat_profile: Threat profile / sector (e.g. "healthcare", "financial", "government").
        search: Free-text search against framework names, descriptions,
            codes, and publishers. Use this when you can't cleanly map
            a natural-language question to structured params.

    Returns:
        A dict with "recommendations" (list of framework blueprints),
        "total" count, "applied_filters" summary, and context metadata.
        If zero results are returned, try calling with fewer filters
        (e.g. just business_model) for broader results.
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
            firm_size=firm_size,
            threat_profile=threat_profile,
            search=search,
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
        "Use this to answer questions like 'Show me the controls for PCI-DSS'.\n"
        "If you need controls within a specific domain (e.g. Incident Response), "
        "use the `domain` parameter with a domain code like 'IR', 'AC', 'AU', etc."
    ),
)
def get_framework_controls(
    framework_id: int | None = None,
    framework_name: str | None = None,
    limit: int | None = 100,
    domain: str | None = None,
) -> dict:
    """List controls for a framework.

    Args:
        framework_id: Internal numeric framework ID.
        framework_name: Natural framework name (e.g. "ISO 27001", "PCI-DSS").
        limit: Maximum number of controls to return (default 100).
        domain: Optional SCF domain code to filter controls
            (e.g. "IR" for Incident Response, "AC" for Access Control).

    Returns:
        Dict with framework info and list of controls.
    """
    if not framework_id and not framework_name:
        return {"error": "Provide either framework_id or framework_name."}

    session = _get_session()
    try:
        resolved_id = resolve_framework_id(session, framework_name=framework_name, framework_id=framework_id)
        if resolved_id is None:
            return {"error": f"Framework not found: '{framework_name or framework_id}'"}

        fw_svc = FrameworkService(session)
        fw = fw_svc.get_framework(resolved_id)
        if not fw:
            return {"error": f"Framework with id {resolved_id} not found in database."}

        all_controls = fw_svc.get_controls_for_framework(resolved_id)

        # Filter by domain if requested
        if domain:
            from app.models.control import Domain
            domain_obj = (
                session.query(Domain)
                .filter(Domain.code.ilike(domain) | Domain.name.ilike(domain))
                .first()
            )
            if domain_obj:
                all_controls = [c for c in all_controls if c.domain_id == domain_obj.id]

        limited = all_controls[: limit] if limit else all_controls

        return {
            "framework_id": resolved_id,
            "framework_code": fw.code,
            "framework_name": fw.name,
            "total_controls": len(all_controls),
            "returned": len(limited),
            "domain_filter": domain,
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
        "\n\n"
        "If you need to compare controls within a specific domain (e.g. Incident Response, "
        "Access Control), use the `domain` parameter to filter results by SCF domain code:\n"
        "- IR = Incident Response\n"
        "- AC = Access Control\n"
        "- AU = Audit & Accountability\n"
        "- etc.\n"
        "You can also first call get_framework_controls with a domain filter, then compare."
    ),
)
def compare_frameworks(
    framework_ids: list[int] | None = None,
    framework_names: list[str] | None = None,
    mode: str = "intersection",
    domain: str | None = None,
) -> dict:
    """Compare frameworks to find overlaps and differences.

    Args:
        framework_ids: List of framework IDs to compare (provide this or framework_names).
        framework_names: List of natural framework names to compare (e.g. ["ISO 27001", "NIST CSF"]).
        mode: Comparison mode:
            - "intersection" (default): return only the controls common to ALL frameworks.
            - "differences": return controls in one but not the other (requires exactly 2 frameworks).
            - "common_controls": detailed common controls with per-framework mapping info.
        domain: Optional SCF domain code to filter results (e.g. "IR" for Incident Response,
            "AC" for Access Control, "AU" for Audit & Accountability).

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
            result = comp_svc.intersection(ids, domain_code=domain)
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
            result = comp_svc.differences(ids[0], ids[1], domain_code=domain)
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
            result = comp_svc.common_control_set(ids, domain_code=domain)
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
# Tool 5: generate_evidence_checklist
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="generate_evidence_checklist",
    description=(
        "Generate a comprehensive evidence checklist for a compliance framework or control. "
        "Use this to answer questions like 'What evidence do I need for POPIA?' or "
        "'What evidence is needed for this specific control?' "
        "Returns required evidence, supporting evidence, recommended evidence, "
        "an audit readiness score, and evidence grouped by audit effort (low/medium/high)."
    ),
)
def generate_evidence_checklist(
    framework_id: int | None = None,
    framework_name: str | None = None,
    control_id: int | None = None,
    firm_size: str | None = None,
    domain: str | None = None,
) -> dict:
    """Generate evidence checklist for a framework or specific control.

    Args:
        framework_id: Internal framework ID.
        framework_name: Natural framework name (e.g. 'POPIA', 'PCI-DSS').
        control_id: Specific control ID for a single-control checklist.
        firm_size: Optional firm-size filter ('micro', 'small', 'medium', 'large', 'enterprise').
        domain: Optional SCF domain code to narrow scope (e.g. 'IR', 'AC').

    Returns:
        Evidence checklist with readiness score, gaps, and effort breakdown.
    """
    session = _get_session()
    try:
        svc = EvidenceIntelligenceService(session)
        if control_id:
            return svc.generate_control_evidence_checklist(control_id)
        return svc.generate_framework_evidence_checklist(
            framework_id=framework_id,
            framework_name=framework_name,
            firm_size=firm_size,
            domain=domain,
        )
    except Exception as exc:
        logger.exception("generate_evidence_checklist failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 6: translate_framework
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="translate_framework",
    description=(
        "Translate controls from one compliance framework to another using 41,000+ STRM-annotated "
        "cross-framework mappings. Use this to answer questions like "
        "'We have ISO 27001 — what additional controls are needed for POPIA?' or "
        "'How much overlap is there between NIST CSF and PCI-DSS?' "
        "Returns already-covered controls, missing controls, unique obligations, "
        "and a suggested implementation order."
    ),
)
def translate_framework(
    source_framework_id: int | None = None,
    source_framework_name: str | None = None,
    target_framework_id: int | None = None,
    target_framework_name: str | None = None,
    domain: str | None = None,
) -> dict:
    """Translate controls from one framework to another via SCF pivot.

    Args:
        source_framework_id: Source framework ID.
        source_framework_name: Source framework name (e.g. 'ISO 27001').
        target_framework_id: Target framework ID.
        target_framework_name: Target framework name (e.g. 'POPIA').
        domain: Optional SCF domain code to narrow results.

    Returns:
        Translation with covered controls, gaps, and implementation priority.
    """
    session = _get_session()
    try:
        svc = TranslationService(session)
        return svc.translate_framework(
            source_framework_id=source_framework_id,
            source_framework_name=source_framework_name,
            target_framework_id=target_framework_id,
            target_framework_name=target_framework_name,
            domain=domain,
        )
    except Exception as exc:
        logger.exception("translate_framework failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 7: find_control_equivalents
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="find_control_equivalents",
    description=(
        "Find equivalent controls across all compliance frameworks for a given SCF control. "
        "Uses STRM types (EQUAL, SUBSET OF, SUPERSET OF, INTERSECTS WITH) to classify relationships. "
        "Use this to answer questions like 'What is the NIST equivalent of AC-01-01?' "
    ),
)
def find_control_equivalents(
    scf_id: str | None = None,
    control_id: int | None = None,
) -> dict:
    """Find equivalent controls across all frameworks for a given control.

    Args:
        scf_id: SCF control ID (e.g. 'AC-01-01').
        control_id: Internal control ID (alternative to scf_id).

    Returns:
        List of equivalent controls with framework info and STRM relationship types.
    """
    session = _get_session()
    try:
        svc = TranslationService(session)
        return svc.find_control_equivalents(scf_id=scf_id, control_id=control_id)
    except Exception as exc:
        logger.exception("find_control_equivalents failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 8: assess_maturity
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="assess_maturity",
    description=(
        "Assess compliance maturity against a framework using SCR-CMM maturity levels (0-5). "
        "Provide assessed maturity levels per control to get a weighted compliance score. "
        "Use this to answer questions like 'What is our POPIA compliance score?' or "
        "'Which domains have the biggest maturity gaps?' "
        "When used without assessed_levels, returns the theoretical SCR-CMM framework."
    ),
)
def assess_maturity(
    framework_id: int | None = None,
    framework_name: str | None = None,
    assessed_levels: dict[str, int] | None = None,
) -> dict:
    """Assess compliance maturity for a framework using SCR-CMM levels.

    Args:
        framework_id: Internal framework ID.
        framework_name: Natural framework name (e.g. 'POPIA', 'ISO 27001').
        assessed_levels: Dict mapping scf_id -> assessed maturity level (0-5).
            Controls not listed are treated as Level 0.

    Returns:
        Compliance score with per-domain breakdown, top gaps, and maturity distribution.
    """
    session = _get_session()
    try:
        svc = MaturityService(session)
        return svc.assess_framework_maturity(
            framework_id=framework_id,
            framework_name=framework_name,
            assessed_levels=assessed_levels,
        )
    except Exception as exc:
        logger.exception("assess_maturity failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 9: generate_roadmap
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="generate_roadmap",
    description=(
        "Generate a prioritized compliance implementation roadmap for achieving compliance with a framework. "
        "Uses firm-size-specific implementation guidance from the SCF. "
        "Returns a phased plan (30/90/180 days) prioritized by control weighting and maturity gap. "
        "Use this to answer questions like 'What's our 90-day plan for POPIA compliance?' or "
        "'Give me a compliance roadmap for a small business implementing NIST CSF.'"
    ),
)
def generate_roadmap(
    framework_id: int | None = None,
    framework_name: str | None = None,
    firm_size: str = "small",
    current_maturity: dict[str, int] | None = None,
    focus_domain: str | None = None,
) -> dict:
    """Generate a prioritized compliance implementation roadmap.

    Args:
        framework_id: Internal framework ID.
        framework_name: Natural framework name.
        firm_size: Organization size ('micro', 'small', 'medium', 'large', 'enterprise').
        current_maturity: Dict of {scf_id: current_maturity_level} (0-5).
        focus_domain: Optional SCF domain to narrow the scope.

    Returns:
        Phased roadmap with 30/90/180-day action items, prioritized by weight and gap.
    """
    session = _get_session()
    try:
        svc = RoadmapService(session)
        return svc.generate_roadmap(
            framework_id=framework_id,
            framework_name=framework_name,
            firm_size=firm_size,
            current_maturity=current_maturity,
            focus_domain=focus_domain,
        )
    except Exception as exc:
        logger.exception("generate_roadmap failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 10: map_risks_to_controls
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="map_risks_to_controls",
    description=(
        "Find compliance controls that mitigate a specific risk or threat using "
        "semantic matching. Translates business language (e.g. 'vendor data leakage', "
        "'ransomware', 'insider threat', 'phishing', 'credential theft', "
        "'cloud misconfiguration') into SCF risk catalog entries automatically.\n\n"
        "Uses a multi-strategy matching pipeline:\n"
        "1. Synonym dictionary — 60+ pre-configured business-to-catalog mappings\n"
        "2. Token overlap scoring — Jaccard similarity against all 273 risk entries\n"
        "3. Risk grouping matching — matches by risk category\n"
        "4. Fuzzy fallback — difflib-based closest group matching\n\n"
        "Each result includes a confidence score (HIGH/MEDIUM/LOW/NO_MATCH), "
        "mitigating controls, relevant frameworks, and remediation suggestions. "
        "When no good match is found, fallback recommendations are provided "
        "suggesting the closest risk categories to explore.\n\n"
        "STRATEGY FOR USING THIS TOOL:\n"
        "1. Start with a natural-language risk description — the synonym "
        "   dictionary handles most common business terms.\n"
        "2. Check the confidence tier in the response:\n"
        "   - HIGH (>=0.8): strong match, results are reliable\n"
        "   - MEDIUM (>=0.5): good match, verify a few results\n"
        "   - LOW (>=0.2): weak match, use fallback suggestions\n"
        "3. If confidence is LOW, try a more specific term or use the "
        "   suggested groupings from the fallback.\n"
        "4. Use the risk_id output to make follow-up calls by ID.\n\n"
        "Example queries that work well:\n"
        "- 'vendor data leakage' — maps to Supply Chain and Exposure risks\n"
        "- 'ransomware' — maps to Business Continuity risks\n"
        "- 'insider threat' — maps to Access Control risks\n"
        "- 'phishing' — maps to Incident Response risks\n"
        "- 'credential theft' — maps to Access Control risks\n"
        "- 'cloud misconfiguration' — maps to Asset Management risks\n"
        "- 'data breach' — maps to Exposure risks\n"
        "- 'third party risk' — maps to Governance risks"
    ),
)
def map_risks_to_controls(
    risk_id: int | None = None,
    risk_keyword: str | None = None,
) -> dict:
    """Map risks to mitigating controls.

    Args:
        risk_id: Specific risk ID to look up.
        risk_keyword: Free-text search for risks (e.g. 'vendor data leakage', 'ransomware').

    Returns:
        Matching risks with mitigating controls, frameworks, and remediation suggestions.
    """
    session = _get_session()
    try:
        svc = RiskIntelligenceService(session)
        return svc.find_controls_for_risk(risk_id=risk_id, risk_keyword=risk_keyword)
    except Exception as exc:
        logger.exception("map_risks_to_controls failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 11: generate_risk_heat_map
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="generate_risk_heat_map",
    description=(
        "Generate a risk heat map showing control coverage by risk grouping. "
        "Identifies which risk areas have the weakest control coverage. "
        "Use this to answer questions like 'Which risk areas are most under-controlled?' or "
        "'Show me a risk heat map for our compliance program.'"
    ),
)
def generate_risk_heat_map(
    risk_grouping: str | None = None,
) -> dict:
    """Generate a risk heat map by risk grouping.

    Args:
        risk_grouping: Optional filter for a specific risk grouping.

    Returns:
        Heat map data with risk density, control coverage, and heat levels.
    """
    session = _get_session()
    try:
        svc = RiskIntelligenceService(session)
        return svc.generate_risk_heat_map(risk_grouping=risk_grouping)
    except Exception as exc:
        logger.exception("generate_risk_heat_map failed")
        return {"error": str(exc)}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Tool 12: audit_readiness_report
# ═══════════════════════════════════════════════════════════════════════
@mcp.tool(
    name="audit_readiness_report",
    description=(
        "Generate a comprehensive audit preparation pack for a compliance framework. "
        "Includes: control inventory with assessment objectives, evidence checklist "
        "grouped by audit effort, compensating control alternatives, evidence gaps, "
        "and an audit readiness assessment with recommendations. "
        "Use this to prepare for an upcoming compliance audit or assessment."
    ),
)
def audit_readiness_report(
    framework_id: int | None = None,
    framework_name: str | None = None,
    domain: str | None = None,
) -> dict:
    """Generate an audit preparation pack.

    Args:
        framework_id: Internal framework ID.
        framework_name: Natural framework name.
        domain: Optional SCF domain code to narrow scope.

    Returns:
        Audit preparation pack with control details, evidence gaps, and readiness score.
    """
    session = _get_session()
    try:
        svc = EvidenceIntelligenceService(session)
        return svc.generate_audit_preparation_pack(
            framework_id=framework_id,
            framework_name=framework_name,
            domain=domain,
        )
    except Exception as exc:
        logger.exception("audit_readiness_report failed")
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
    Authentication is handled by MCPAuthMiddleware (Bearer token required).
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Mount

    from app.auth import MCPAuthMiddleware

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
            Middleware(MCPAuthMiddleware),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════
# Entry point (stdio)
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("Starting SFR MCP server (stdio transport)...")
    mcp.run()