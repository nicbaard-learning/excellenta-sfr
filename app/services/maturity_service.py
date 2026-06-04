"""Maturity Assessment Service – uses SCR-CMM levels and control weighting for compliance scoring.

Leverages existing data:
- Control (cmm_level_0 through cmm_level_5 with full descriptive text)
- Control (relative_weighting for prioritizing)
- Domain (for grouping by domain)
- ControlMapping (for framework-specific assessments)
- Framework (for framework-level assessment)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.control import Control, Domain
from app.models.framework import Framework
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)

# ── SCR-CMM Level Definitions ─────────────────────────────────────────
SCR_CMM_LEVELS = [
    {"level": 0, "name": "Incomplete", "description": "No process or capability exists"},
    {"level": 1, "name": "Performed", "description": "The process is performed in an ad-hoc manner"},
    {"level": 2, "name": "Managed", "description": "The process is planned, monitored, and adjusted"},
    {"level": 3, "name": "Defined", "description": "The process is standardized across the organization"},
    {"level": 4, "name": "Quantitatively Managed", "description": "The process is measured and controlled using metrics"},
    {"level": 5, "name": "Optimizing", "description": "The process is continuously improved through quantitative feedback"},
]

SCR_CMM_COLUMNS = ["cmm_level_0", "cmm_level_1", "cmm_level_2", "cmm_level_3", "cmm_level_4", "cmm_level_5"]


class MaturityService:
    """Service for maturity assessment, scoring, and reporting."""

    def __init__(self, session: Session):
        self.session = session

    # ── Assess Maturity for a Framework ─────────────────────────────

    def assess_framework_maturity(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        assessed_levels: dict[str, int] | None = None,
    ) -> dict:
        """Calculate compliance score for a framework based on SCR-CMM levels.

        When assessed_levels is provided, computes a weighted compliance score.
        When not provided, returns the baseline maturity profile.

        Args:
            framework_id: Internal framework ID.
            framework_name: Natural framework name.
            assessed_levels: Dict mapping scf_id -> assessed maturity level (0-5).
                If provided, scores are computed against these assessments.
                If omitted, returns the theoretical maturity framework only.

        Returns:
            Compliance score with per-domain breakdown, top gaps, and maturity profile.
        """
        if not framework_id and not framework_name:
            return {"error": "Provide either framework_id or framework_name."}

        from app.mcp.resolver import resolve_framework_id
        resolved_id = resolve_framework_id(self.session, framework_name=framework_name, framework_id=framework_id)
        if resolved_id is None:
            return {"error": f"Framework not found: '{framework_name or framework_id}'"}

        fw = self.session.query(Framework).filter(Framework.id == resolved_id).first()
        if not fw:
            return {"error": f"Framework {resolved_id} not found"}

        # Get controls for this framework
        mapped_ids = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == resolved_id)
            .subquery()
        )
        controls = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(mapped_ids))
            .order_by(Control.scf_id)
            .all()
        )

        if not controls:
            return {
                "framework": {"id": resolved_id, "code": fw.code if fw else "", "name": fw.name if fw else ""},
                "error": "No controls found for this framework",
                "overall_score": 0,
            }

        # Compute maturity profile for each control
        control_maturities = []
        for ctrl in controls:
            maturity_profile = self._get_maturity_profile(ctrl)
            assessed = (assessed_levels or {}).get(ctrl.scf_id, 0)

            control_maturities.append({
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
                "domain_name": ctrl.domain.name if ctrl.domain else None,
                "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
                "assessed_level": assessed,
                "maturity_profile": maturity_profile,
                "gap": 5 - assessed,  # How far from Level 5
            })

        # Calculate scores
        scores = self._calculate_scores(control_maturities)

        # Identify top gaps (controls with lowest assessed levels, weighted by importance)
        gaps = self._identify_top_gaps(control_maturities, assessed_levels)

        return {
            "framework": {
                "id": resolved_id,
                "code": fw.code if fw else "",
                "name": fw.name if fw else "",
            },
            "overall_score": scores["overall"],
            "by_domain": scores["by_domain"],
            "maturity_distribution": scores["maturity_distribution"],
            "control_breakdown": control_maturities,
            "scoring_methodology": {
                "model": "SCR-CMM (Secure Controls Reference Capability Maturity Model)",
                "levels": SCR_CMM_LEVELS,
                "weighting": "Controls are weighted by relative_weighting when available (default: 1.0)",
                "formula": "Score = sum(assessed_level / 5 * weight) / sum(weight) * 100",
            },
            "top_gaps": gaps[:20] if assessed_levels else [],
            "note": "Provide assessed_levels as a dict of {scf_id: level} to compute scores."
                    if not assessed_levels else None,
        }

    # ── Compliance Summary Dashboard ────────────────────────────────

    def compliance_dashboard(
        self,
        assessments: dict[str, dict[str, int]],  # framework_code -> {scf_id: level}
    ) -> dict:
        """Generate a multi-framework compliance dashboard.

        Args:
            assessments: Dict mapping framework codes to their assessed maturity levels.
                e.g. {"POPIA": {"AC-01-01": 3, ...}, "ISO27001": {"AC-01-01": 4, ...}}

        Returns:
            Multi-framework compliance summary with rankings, top gaps, and domain breakdown.
        """
        if not assessments:
            return {"error": "Provide at least one framework assessment."}

        results = []
        for fw_code, levels in assessments.items():
            result = self.assess_framework_maturity(
                framework_name=fw_code,
                assessed_levels=levels,
            )
            if "error" not in result or not result.get("overall_score"):
                results.append({
                    "framework_code": fw_code,
                    "framework_name": result.get("framework", {}).get("name", fw_code),
                    "overall_score": result.get("overall_score", 0),
                    "by_domain": result.get("by_domain", {}),
                    "top_gaps": result.get("top_gaps", [])[:5],
                })

        # Sort by score ascending (worst-first)
        results.sort(key=lambda r: r["overall_score"])

        # Find common gaps across frameworks
        all_gaps: dict[str, list[dict]] = {}
        for r in results:
            for gap in r.get("top_gaps", []):
                scf_id = gap.get("scf_id", "")
                if scf_id not in all_gaps:
                    all_gaps[scf_id] = []
                all_gaps[scf_id].append({
                    "framework": r["framework_code"],
                    "score": r["overall_score"],
                    "assessed_level": gap.get("assessed_level", 0),
                })

        # Cross-cutting gaps = same control weak across multiple frameworks
        cross_cutting = [
            {"scf_id": scf_id, "affected_frameworks": len(fws), "details": fws}
            for scf_id, fws in all_gaps.items()
            if len(fws) > 1
        ]
        cross_cutting.sort(key=lambda x: x["affected_frameworks"], reverse=True)

        return {
            "frameworks_assessed": len(results),
            "dashboard": results,
            "cross_cutting_gaps": cross_cutting[:20],
            "summary": {
                "lowest_score": min((r["overall_score"] for r in results), default=0),
                "highest_score": max((r["overall_score"] for r in results), default=0),
                "average_score": round(
                    sum(r["overall_score"] for r in results) / max(len(results), 1), 1
                ),
            },
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _get_maturity_profile(self, ctrl: Control) -> dict:
        """Extract the SCR-CMM maturity level descriptions for a control."""
        profile = {}
        for i, col in enumerate(SCR_CMM_COLUMNS):
            val = getattr(ctrl, col, None)
            if val:
                profile[f"level_{i}"] = val[:200] if val else None
            else:
                profile[f"level_{i}"] = None
        return profile

    def _calculate_scores(self, control_maturities: list[dict]) -> dict:
        """Calculate weighted compliance scores.

        Score per control = (assessed_level / 5) * 100
        Overall score = weighted average across all controls
        """
        total_weight = 0.0
        weighted_sum = 0.0
        domain_data: dict[str, list[float]] = {}
        maturity_distribution = {f"level_{i}": 0 for i in range(6)}

        for cm in control_maturities:
            weight = cm.get("relative_weighting") or 1.0
            assessed = cm.get("assessed_level", 0)
            total_weight += weight

            # Score for this control: percentage of max maturity
            control_score = (assessed / 5.0) * 100
            weighted_sum += control_score * weight

            # Track domain data
            domain_code = cm.get("domain_code", "UNKNOWN")
            if domain_code not in domain_data:
                domain_data[domain_code] = []
            domain_data[domain_code].append(control_score)

            # Track distribution
            level_key = f"level_{int(assessed)}"
            if level_key in maturity_distribution:
                maturity_distribution[level_key] += 1

        overall = round(weighted_sum / max(total_weight, 1), 1)

        # Per-domain scores
        by_domain = {}
        for dcode, scores in domain_data.items():
            by_domain[dcode] = {
                "score": round(sum(scores) / len(scores), 1),
                "control_count": len(scores),
            }

        return {
            "overall": overall,
            "by_domain": by_domain,
            "maturity_distribution": maturity_distribution,
        }

    def _identify_top_gaps(self, control_maturities: list[dict], assessed_levels: dict | None) -> list[dict]:
        """Identify the controls with the largest maturity gaps, weighted by importance."""
        if not assessed_levels:
            return []

        scored_gaps = []
        for cm in control_maturities:
            weight = cm.get("relative_weighting") or 1.0
            assessed = cm.get("assessed_level", 0)
            gap = 5 - assessed
            # Prioritize: big gap × high weight = most important to fix
            priority = gap * weight
            scored_gaps.append({
                "scf_id": cm["scf_id"],
                "title": cm["title"],
                "domain_code": cm.get("domain_code"),
                "current_level": assessed,
                "target_level": 5,
                "gap": gap,
                "weight": weight,
                "priority_score": round(priority, 2),
            })

        scored_gaps.sort(key=lambda x: x["priority_score"], reverse=True)
        return scored_gaps

    def get_maturity_level_descriptions(self) -> list[dict]:
        """Return the SCR-CMM maturity level definitions."""
        return SCR_CMM_LEVELS
