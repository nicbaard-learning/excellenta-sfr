"""Evidence Intelligence Service – generates evidence checklists, audit preparation packs, and readiness scoring.

Leverages existing data:
- EvidenceArtifact (ERL #, title, description, type)
- AssessmentObjective (what to assess per control)
- Control (title, description, domain, weighting, conformity_cadence)
- ControlMapping (framework associations)
- CompensatingControlLink (alternative evidence paths)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.assessment import AssessmentObjective
from app.models.control import Control, Domain
from app.models.evidence import EvidenceArtifact
from app.models.framework import Framework
from app.models.mapping import ControlMapping
from app.models.compensating import CompensatingControlLink

logger = logging.getLogger(__name__)

# ── Evidence type classification ──────────────────────────────────────
HIGH_EFFORT_TYPES = {"audit report", "penetration test", "third-party assessment",
                     "source code review", "architecture review"}
MEDIUM_EFFORT_TYPES = {"policy", "procedure", "standard", "risk assessment",
                       "business impact analysis", "incident response plan"}
LOW_EFFORT_TYPES = {"screenshot", "configuration export", "log", "attestation",
                    "certificate", "training record", "acknowledgement"}

STRONG_EVIDENCE_TYPES = {"audit report", "penetration test", "third-party assessment",
                         "certificate", "attestation", "source code review"}
WEAK_EVIDENCE_TYPES = {"screenshot", "self-assessment", "verbal confirmation",
                       "email confirmation"}


class EvidenceIntelligenceService:
    """Service for evidence intelligence – checklists, audit packs, readiness scoring."""

    def __init__(self, session: Session):
        self.session = session

    # ── Core: Evidence Checklist for a Framework ─────────────────────

    def generate_framework_evidence_checklist(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        firm_size: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """Generate a complete evidence checklist for a compliance framework.

        Args:
            framework_id: Internal framework ID.
            framework_name: Natural framework name (e.g. 'POPIA', 'PCI-DSS').
            firm_size: Optional firm-size filter for tailored guidance.
            domain: Optional SCF domain code to narrow scope.

        Returns:
            Evidence checklist with required, supporting, and recommended evidence,
            grouped by audit effort, plus an audit readiness score.
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
        mapped_control_ids = (
            select(ControlMapping.control_id)
            .where(ControlMapping.framework_id == resolved_id)
            .scalar_subquery()
        )
        controls_query = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(mapped_control_ids))
            .order_by(Control.scf_id)
        )

        # Optional domain filter
        if domain:
            domain_obj = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain) | Domain.name.ilike(domain))
                .first()
            )
            if domain_obj:
                controls_query = controls_query.filter(Control.domain_id == domain_obj.id)

        controls = controls_query.all()

        # Build evidence checklist from all controls
        all_evidence = []
        high_effort = []
        medium_effort = []
        low_effort = []
        total_evidence_count = 0
        evidence_by_domain: dict[str, list[dict]] = {}

        for ctrl in controls:
            artifacts = (
                self.session.query(EvidenceArtifact)
                .filter(EvidenceArtifact.control_id == ctrl.id)
                .all()
            )
            objectives = (
                self.session.query(AssessmentObjective)
                .filter(AssessmentObjective.control_id == ctrl.id)
                .all()
            )
            comp_controls = (
                self.session.query(CompensatingControlLink)
                .filter(CompensatingControlLink.control_id == ctrl.id)
                .all()
            )

            domain_code = ctrl.domain.code if ctrl.domain else "UNKNOWN"

            for art in artifacts:
                item = {
                    "erl_number": art.erl_number,
                    "evidence_title": art.evidence_title,
                    "evidence_description": art.evidence_description,
                    "evidence_type": art.evidence_type,
                    "control_scf_id": ctrl.scf_id,
                    "control_title": ctrl.title,
                    "domain_code": domain_code,
                    "conformity_cadence": ctrl.conformity_cadence,
                    "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
                }

                # Classify by effort level
                etype = (art.evidence_type or "").lower()
                if any(t in etype for t in HIGH_EFFORT_TYPES):
                    item["effort_level"] = "high"
                    high_effort.append(item)
                elif any(t in etype for t in MEDIUM_EFFORT_TYPES):
                    item["effort_level"] = "medium"
                    medium_effort.append(item)
                elif any(t in etype for t in LOW_EFFORT_TYPES):
                    item["effort_level"] = "low"
                    low_effort.append(item)
                else:
                    item["effort_level"] = "unclassified"
                    medium_effort.append(item)

                all_evidence.append(item)
                total_evidence_count += 1

                if domain_code not in evidence_by_domain:
                    evidence_by_domain[domain_code] = []
                evidence_by_domain[domain_code].append(item)

        # Also add controls without evidence artifacts as "gaps"
        controls_with_evidence = {
            r[0] for r in self.session.query(EvidenceArtifact.control_id).filter(
                EvidenceArtifact.control_id.in_([c.id for c in controls])
            ).all()
        }

        evidence_gaps = []
        for ctrl in controls:
            if ctrl.id not in controls_with_evidence:
                objectives_text = [o.objective_text for o in
                                   self.session.query(AssessmentObjective)
                                   .filter(AssessmentObjective.control_id == ctrl.id)
                                   .all()]
                evidence_gaps.append({
                    "scf_id": ctrl.scf_id,
                    "title": ctrl.title,
                    "domain_code": ctrl.domain.code if ctrl.domain else None,
                    "description": ctrl.description[:200] if ctrl.description else None,
                    "assessment_objectives": objectives_text[:3],
                    "suggested_evidence_types": self._suggest_evidence_types(ctrl),
                })

        # Compute readiness score
        readiness_score = self._compute_readiness_score(controls, all_evidence)

        # Apply firm-size filter if requested
        firm_size_guidance = None
        if firm_size:
            firm_size_guidance = self._get_firm_size_guidance(controls, firm_size)

        return {
            "framework": {
                "id": fw.id,
                "code": fw.code,
                "name": fw.name,
                "category": fw.category,
            },
            "summary": {
                "total_controls": len(controls),
                "total_evidence_items": total_evidence_count,
                "evidence_gaps": len(evidence_gaps),
                "readiness_score": readiness_score,
                "firm_size_filter": firm_size,
            },
            "evidence_by_effort": {
                "high_effort": {
                    "count": len(high_effort),
                    "items": high_effort[:50],
                    "description": "Audit reports, pen tests, third-party assessments",
                },
                "medium_effort": {
                    "count": len(medium_effort),
                    "items": medium_effort[:50],
                    "description": "Policies, procedures, risk assessments",
                },
                "low_effort": {
                    "count": len(low_effort),
                    "items": low_effort[:50],
                    "description": "Screenshots, configs, logs, training records",
                },
            },
            "evidence_by_domain": {
                domain: {
                    "count": len(items),
                    "items": items[:20],
                }
                for domain, items in evidence_by_domain.items()
            },
            "evidence_gaps": evidence_gaps[:50],
            "firm_size_guidance": firm_size_guidance,
        }

    # ── Evidence Checklist for a Single Control ─────────────────────

    def generate_control_evidence_checklist(self, control_id: int) -> dict:
        """Generate a detailed evidence checklist for a single control."""
        ctrl = self.session.query(Control).filter(Control.id == control_id).first()
        if not ctrl:
            return {"error": f"Control {control_id} not found"}

        artifacts = (
            self.session.query(EvidenceArtifact)
            .filter(EvidenceArtifact.control_id == ctrl.id)
            .all()
        )
        objectives = (
            self.session.query(AssessmentObjective)
            .filter(AssessmentObjective.control_id == ctrl.id)
            .all()
        )
        comp_controls = (
            self.session.query(CompensatingControlLink)
            .filter(CompensatingControlLink.control_id == ctrl.id)
            .all()
        )

        # Classify each artifact
        strong_evidence = []
        weak_evidence = []
        for art in artifacts:
            etype = (art.evidence_type or "").lower()
            entry = {
                "erl_number": art.erl_number,
                "evidence_title": art.evidence_title,
                "evidence_description": art.evidence_description,
                "evidence_type": art.evidence_type,
            }
            if any(t in etype for t in STRONG_EVIDENCE_TYPES):
                entry["strength"] = "strong"
                strong_evidence.append(entry)
            elif any(t in etype for t in WEAK_EVIDENCE_TYPES):
                entry["strength"] = "weak"
                weak_evidence.append(entry)
            else:
                entry["strength"] = "moderate"
                strong_evidence.append(entry)

        # Suggested evidence types for this control
        suggested = self._suggest_evidence_types(ctrl)

        return {
            "control": {
                "id": ctrl.id,
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "description": ctrl.description,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
                "conformity_cadence": ctrl.conformity_cadence,
                "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
            },
            "assessment_objectives": [
                {"code": o.objective_code, "text": o.objective_text}
                for o in objectives
            ],
            "evidence_artifacts": {
                "total": len(artifacts),
                "strong_evidence": {
                    "count": len(strong_evidence),
                    "examples": strong_evidence,
                    "description": "Audit reports, certifications, third-party assessments, pen tests",
                },
                "weak_evidence": {
                    "count": len(weak_evidence),
                    "examples": weak_evidence,
                    "description": "Screenshots, self-assessments, verbal confirmations",
                },
            },
            "compensating_controls": [
                {
                    "compensating_control_id": c.compensating_control_id,
                    "title": c.compensating_control_title,
                    "description": c.compensating_control_description,
                    "compensation_type": c.compensation_type,
                    "justification": c.justification,
                }
                for c in comp_controls
            ],
            "suggested_evidence_types": suggested,
        }

    # ── Audit Preparation Pack ──────────────────────────────────────

    def generate_audit_preparation_pack(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """Generate a comprehensive audit preparation pack for a framework.

        Includes:
        - Control inventory with objectives
        - Evidence checklist grouped by domain
        - Compensating control alternatives
        - Audit readiness assessment
        """
        checklist = self.generate_framework_evidence_checklist(
            framework_id=framework_id,
            framework_name=framework_name,
            domain=domain,
        )

        if "error" in checklist:
            return checklist

        if not framework_id and framework_name:
            from app.mcp.resolver import resolve_framework_id
            framework_id = resolve_framework_id(self.session, framework_name=framework_name)

        if framework_id:
            fw = self.session.query(Framework).filter(Framework.id == framework_id).first()
            # Build control-by-control detail
            control_details = []
            mapped_ids = (
                select(ControlMapping.control_id)
                .where(ControlMapping.framework_id == framework_id)
                .scalar_subquery()
            )
            controls = (
                self.session.query(Control)
                .options(joinedload(Control.domain))
                .filter(Control.id.in_(mapped_ids))
                .order_by(Control.scf_id)
                .all()
            )

            if domain:
                domain_obj = self.session.query(Domain).filter(
                    Domain.code.ilike(domain) | Domain.name.ilike(domain)
                ).first()
                if domain_obj:
                    controls = [c for c in controls if c.domain_id == domain_obj.id]

            for ctrl in controls:
                objectives = self.session.query(AssessmentObjective).filter(
                    AssessmentObjective.control_id == ctrl.id
                ).all()
                artifacts = self.session.query(EvidenceArtifact).filter(
                    EvidenceArtifact.control_id == ctrl.id
                ).all()
                comps = self.session.query(CompensatingControlLink).filter(
                    CompensatingControlLink.control_id == ctrl.id
                ).all()

                control_details.append({
                    "scf_id": ctrl.scf_id,
                    "title": ctrl.title,
                    "domain_code": ctrl.domain.code if ctrl.domain else None,
                    "objectives_count": len(objectives),
                    "evidence_count": len(artifacts),
                    "compensating_count": len(comps),
                    "conformity_cadence": ctrl.conformity_cadence,
                    "weight": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
                })

            return {
                "pack_title": f"Audit Preparation Pack: {fw.name if fw else 'Unknown'}",
                "framework": checklist["framework"],
                "summary": {
                    **checklist["summary"],
                    "total_control_details": len(control_details),
                },
                "control_by_domain": self._group_controls_by_domain(control_details),
                "evidence_by_effort": checklist["evidence_by_effort"],
                "evidence_gaps": checklist["evidence_gaps"],
                "audit_readiness": {
                    "score": checklist["summary"]["readiness_score"],
                    "recommendations": self._generate_readiness_recommendations(
                        checklist["summary"]["readiness_score"],
                        len(checklist["evidence_gaps"]),
                    ),
                },
            }

        return checklist

    # ── Strong vs Weak Evidence Examples ────────────────────────────

    def get_evidence_examples(self, evidence_type: str | None = None) -> dict:
        """Get examples of strong vs weak evidence from the repository.

        Args:
            evidence_type: Optional filter by evidence type (e.g. 'policy', 'audit report').

        Returns:
            Examples of strong and weak evidence artifacts.
        """
        query = self.session.query(EvidenceArtifact)

        if evidence_type:
            query = query.filter(EvidenceArtifact.evidence_type.ilike(f"%{evidence_type}%"))

        artifacts = query.limit(100).all()

        strong = []
        weak = []
        for art in artifacts:
            etype = (art.evidence_type or "").lower()
            entry = {
                "erl_number": art.erl_number,
                "evidence_title": art.evidence_title,
                "evidence_type": art.evidence_type,
                "control_id": art.control_id,
            }
            if any(t in etype for t in STRONG_EVIDENCE_TYPES):
                entry["reason"] = f"'{art.evidence_type}' is verifiable and independently auditable"
                strong.append(entry)
            elif any(t in etype for t in WEAK_EVIDENCE_TYPES):
                entry["reason"] = f"'{art.evidence_type}' is self-reported and harder to verify"
                weak.append(entry)

        return {
            "strong_evidence_examples": strong[:20],
            "weak_evidence_examples": weak[:20],
            "note": "Strong evidence is independently verifiable (audit reports, certifications). "
                    "Weak evidence is self-reported (screenshots, self-assessments).",
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _compute_readiness_score(self, controls: list[Control], evidence_items: list[dict]) -> dict:
        """Compute an audit readiness score based on evidence coverage.

        Methodology:
        - Each control gets a base score of 0-100 based on evidence coverage
        - Controls with evidence artifacts score higher
        - Controls with strong evidence score higher than weak
        - Weighted by relative_control_weighting
        """
        if not controls:
            return {"overall": 0, "by_domain": {}, "methodology": "No controls to assess"}

        control_evidence_map: dict[int, list[dict]] = {}
        for item in evidence_items:
            ctrl_id = item.get("control_scf_id")
            if ctrl_id:
                if ctrl_id not in control_evidence_map:
                    control_evidence_map[ctrl_id] = []
                control_evidence_map[ctrl_id].append(item)

        total_weight = 0.0
        weighted_score = 0.0
        domain_scores: dict[str, list[float]] = {}

        for ctrl in controls:
            weight = float(ctrl.relative_weighting) if ctrl.relative_weighting else 1.0
            total_weight += weight

            ev_list = control_evidence_map.get(ctrl.scf_id, [])
            if not ev_list:
                score = 0.0
            else:
                # Score based on count and type of evidence
                strong_count = sum(1 for e in ev_list if e.get("effort_level") in ("high", "medium"))
                total_count = len(ev_list)
                score = min(100.0, (strong_count / max(total_count, 1)) * 60 + (total_count / 5) * 40)
                score = min(100.0, score)

            weighted_score += score * weight

            domain_code = ctrl.domain.code if ctrl.domain else "UNKNOWN"
            if domain_code not in domain_scores:
                domain_scores[domain_code] = []
            domain_scores[domain_code].append(score)

        overall = round(weighted_score / max(total_weight, 1), 1)

        # Domain breakdown
        by_domain = {}
        for dcode, scores in domain_scores.items():
            by_domain[dcode] = {
                "score": round(sum(scores) / len(scores), 1),
                "control_count": len(scores),
            }

        return {
            "overall": overall,
            "by_domain": by_domain,
            "interpretation": self._interpret_score(overall),
            "methodology": "Weighted by relative_control_weighting; controls with strong evidence score highest",
        }

    def _interpret_score(self, score: float) -> str:
        if score >= 80:
            return "Strong readiness – most controls have verifiable evidence"
        elif score >= 60:
            return "Moderate readiness – key controls have evidence, gaps remain"
        elif score >= 40:
            return "Limited readiness – significant evidence gaps exist"
        else:
            return "Weak readiness – substantial evidence collection needed"

    def _suggest_evidence_types(self, ctrl: Control) -> list[str]:
        """Suggest evidence types based on control characteristics."""
        suggestions = ["policy", "procedure", "screenshot"]
        title_lower = (ctrl.title or "").lower()
        desc_lower = (ctrl.description or "").lower()

        if any(w in title_lower or w in desc_lower for w in ["audit", "review", "assessment"]):
            suggestions.append("audit report")
        if any(w in title_lower or w in desc_lower for w in ["training", "awareness"]):
            suggestions.append("training record")
        if any(w in title_lower or w in desc_lower for w in ["incident", "breach", "response"]):
            suggestions.extend(["incident response plan", "incident log"])
        if any(w in title_lower or w in desc_lower for w in ["risk", "bcm", "business continuity"]):
            suggestions.append("risk assessment")
        if any(w in title_lower or w in desc_lower for w in ["access", "authentication"]):
            suggestions.append("access review report")
        if any(w in title_lower or w in desc_lower for w in ["encrypt", "cryptograph", "key"]):
            suggestions.append("encryption configuration")
        if any(w in title_lower or w in desc_lower for w in ["vendor", "third-party", "supplier"]):
            suggestions.append("vendor assessment report")
        if any(w in title_lower or w in desc_lower for w in ["penetration", "vulnerability"]):
            suggestions.append("penetration test report")
        if any(w in title_lower or w in desc_lower for w in ["config", "change", "patch"]):
            suggestions.append("configuration management report")

        return list(set(suggestions))

    def _get_firm_size_guidance(self, controls: list[Control], firm_size: str) -> dict:
        """Extract firm-size-specific implementation guidance."""
        size_col = {
            "micro": "solutions_micro_small",
            "small": "solutions_small",
            "medium": "solutions_medium",
            "large": "solutions_large",
            "enterprise": "solutions_enterprise",
        }.get(firm_size, "solutions_small")

        guidance = []
        for ctrl in controls[:50]:
            solution = getattr(ctrl, size_col, None)
            if solution:
                guidance.append({
                    "scf_id": ctrl.scf_id,
                    "title": ctrl.title,
                    "guidance": solution[:300] if solution else None,
                    "domain_code": ctrl.domain.code if ctrl.domain else None,
                })

        return {
            "firm_size": firm_size,
            "controls_with_guidance": len(guidance),
            "guidance_items": guidance,
        }

    def _group_controls_by_domain(self, control_details: list[dict]) -> dict:
        """Group a flat list of control details by domain code."""
        grouped: dict[str, list[dict]] = {}
        for c in control_details:
            dc = c.get("domain_code", "UNKNOWN")
            if dc not in grouped:
                grouped[dc] = []
            grouped[dc].append(c)
        return grouped

    def _generate_readiness_recommendations(self, score: dict, gap_count: int) -> list[str]:
        """Generate human-readable readiness improvement recommendations."""
        overall = score.get("overall", 0)
        recs = []
        if overall < 40:
            recs.append("Priority: Collect evidence for all controls with no artifacts")
            recs.append("Focus on high-weight controls first (largest compliance impact)")
        if overall < 60:
            recs.append("Replace self-reported evidence with auditable artifacts where possible")
            recs.append("Ensure evidence covers all domains evenly")
        if gap_count > 10:
            recs.append(f"Address {gap_count} controls with missing evidence artifacts")
        recs.append("Schedule evidence reviews aligned with conformity cadence requirements")
        return recs
