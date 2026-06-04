"""Compliance Roadmap Service – generates prioritized implementation roadmaps.

Leverages existing data:
- Control (solutions_micro_small through solutions_enterprise for implementation guidance)
- Control (relative_weighting for prioritization)
- Control (conformity_cadence for timeline alignment)
- Control (cmm_level_0-5 for maturity baseline)
- Domain (for grouping)
- ControlMapping (for framework-specific scoping)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.control import Control, Domain
from app.models.framework import Framework, FrameworkVersion
from app.models.mapping import ControlMapping
from app.models.assessment import AssessmentObjective
from app.models.evidence import EvidenceArtifact

logger = logging.getLogger(__name__)


class RoadmapService:
    """Service for generating compliance implementation roadmaps."""

    def __init__(self, session: Session):
        self.session = session

    # ── Compliance Roadmap Generator ────────────────────────────────

    def generate_roadmap(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        firm_size: str = "small",
        current_maturity: dict[str, int] | None = None,
        focus_domain: str | None = None,
    ) -> dict:
        """Generate a prioritized compliance implementation roadmap.

        Input:
            framework_id / framework_name: Which framework to build a roadmap for.
            firm_size: 'micro', 'small', 'medium', 'large', 'enterprise'.
            current_maturity: Dict of {scf_id: current_maturity_level} (0-5).
                Controls not listed are assumed at Level 0.
            focus_domain: Optional SCF domain to narrow the scope.

        Output:
            Prioritized action plan divided into 30/90/180-day phases,
            ordered by control weighting and maturity gap.
        """
        if not framework_id and not framework_name:
            return {"error": "Provide either framework_id or framework_name."}

        firm_size = firm_size.lower()
        if firm_size not in ("micro", "small", "medium", "large", "enterprise"):
            return {"error": f"Invalid firm_size '{firm_size}'. Choose: micro, small, medium, large, enterprise."}

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
        controls_query = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(mapped_ids))
            .order_by(Control.scf_id)
        )

        if focus_domain:
            domain_obj = self.session.query(Domain).filter(
                Domain.code.ilike(focus_domain) | Domain.name.ilike(focus_domain)
            ).first()
            if domain_obj:
                controls_query = controls_query.filter(Control.domain_id == domain_obj.id)

        controls = controls_query.all()

        if not controls:
            return {
                "framework": {"code": fw.code if fw else "", "name": fw.name if fw else ""},
                "error": "No controls found for this framework",
            }

        # Score and rank each control by priority
        size_column = {
            "micro": "solutions_micro_small",
            "small": "solutions_small",
            "medium": "solutions_medium",
            "large": "solutions_large",
            "enterprise": "solutions_enterprise",
        }.get(firm_size, "solutions_small")

        scored_items = []
        for ctrl in controls:
            weight = float(ctrl.relative_weighting) if ctrl.relative_weighting else 1.0
            current_level = (current_maturity or {}).get(ctrl.scf_id, 0)
            maturity_gap = 5 - current_level

            # Priority = weight × maturity_gap
            priority = weight * maturity_gap

            # Get firm-size guidance
            guidance = getattr(ctrl, size_column, None)
            if not guidance:
                guidance = None

            # Get evidence for this control
            evidence_count = (
                self.session.query(EvidenceArtifact)
                .filter(EvidenceArtifact.control_id == ctrl.id)
                .count()
            )

            # Get objectives
            objectives = self.session.query(AssessmentObjective).filter(
                AssessmentObjective.control_id == ctrl.id
            ).all()

            scored_items.append({
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
                "domain_name": ctrl.domain.name if ctrl.domain else None,
                "description": ctrl.description[:200] if ctrl.description else None,
                "relative_weighting": weight,
                "current_maturity": current_level,
                "maturity_gap": maturity_gap,
                "priority_score": round(priority, 2),
                "implementation_guidance": guidance[:500] if guidance else None,
                "conformity_cadence": ctrl.conformity_cadence,
                "evidence_count": evidence_count,
                "assessment_objectives_count": len(objectives),
            })

        # Sort by priority (highest first)
        scored_items.sort(key=lambda x: x["priority_score"], reverse=True)

        # Group by phase
        total_items = len(scored_items)
        if total_items == 0:
            phases = {"30_day": [], "90_day": [], "180_day": []}
        elif total_items <= 5:
            phases = {"30_day": scored_items, "90_day": [], "180_day": []}
        else:
            split_30 = max(1, int(total_items * 0.25))  # 25% in first 30 days
            split_90 = max(1, int(total_items * 0.40))  # 40% in next 60 days
            phases = {
                "30_day": scored_items[:split_30],
                "90_day": scored_items[split_30:split_30 + split_90],
                "180_day": scored_items[split_30 + split_90:],
            }

        # Compute timeline
        today = datetime.now()
        phase_dates = {
            "30_day": {
                "target": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
                "label": "Next 30 Days (Quick Wins)",
            },
            "90_day": {
                "target": (today + timedelta(days=90)).strftime("%Y-%m-%d"),
                "label": "30–90 Days (Build Foundation)",
            },
            "180_day": {
                "target": (today + timedelta(days=180)).strftime("%Y-%m-%d"),
                "label": "90–180 Days (Mature & Optimize)",
            },
        }

        # Generate domain-level summary
        domain_summary: dict[str, dict] = {}
        for item in scored_items:
            dc = item.get("domain_code", "UNKNOWN")
            if dc not in domain_summary:
                domain_summary[dc] = {
                    "domain_code": dc,
                    "domain_name": item.get("domain_name") or dc,
                    "total_controls": 0,
                    "avg_maturity": 0.0,
                    "total_priority": 0.0,
                }
            domain_summary[dc]["total_controls"] += 1
            domain_summary[dc]["avg_maturity"] += item.get("current_maturity", 0)
            domain_summary[dc]["total_priority"] += item.get("priority_score", 0)

        for dc in domain_summary:
            tc = domain_summary[dc]["total_controls"]
            if tc > 0:
                domain_summary[dc]["avg_maturity"] = round(
                    domain_summary[dc]["avg_maturity"] / tc, 1
                )
            domain_summary[dc]["priority_rank"] = sorted(
                domain_summary.values(),
                key=lambda x: x["total_priority"],
                reverse=True,
            ).index(domain_summary[dc]) + 1

        # Extract maturity baseline summary
        if current_maturity:
            maturity_summary = {
                "overall_avg_maturity": round(
                    sum(current_maturity.get(item["scf_id"], 0) for item in scored_items) / max(len(scored_items), 1), 1
                ),
                "controls_at_level_0": sum(1 for item in scored_items if item["current_maturity"] == 0),
                "controls_at_level_3_plus": sum(1 for item in scored_items if item["current_maturity"] >= 3),
            }
        else:
            maturity_summary = {
                "overall_avg_maturity": 0,
                "note": "No maturity data provided. All controls assumed at Level 0.",
            }

        return {
            "roadprint": f"Compliance Roadmap: {fw.name if fw else ''} ({firm_size} organization)",
            "framework": {
                "id": resolved_id,
                "code": fw.code if fw else "",
                "name": fw.name if fw else "",
            },
            "context": {
                "firm_size": firm_size,
                "focus_domain": focus_domain,
                "total_controls": len(controls),
                "controls_in_roadmap": len(scored_items),
                "maturity_summary": maturity_summary,
            },
            "domain_priorities": sorted(
                domain_summary.values(),
                key=lambda x: x["total_priority"],
                reverse=True,
            ),
            "roadmap": {
                "phases": {
                    phase: {
                        "timeline": phase_dates[phase],
                        "control_count": len(items),
                        "items": items,
                    }
                    for phase, items in phases.items()
                }
            },
            "recommended_start": phases["30_day"][:3] if phases["30_day"] else [],
        }
