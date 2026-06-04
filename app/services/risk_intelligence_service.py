"""Risk Intelligence Service – maps risks to controls, generates risk heat maps, residual risk reporting.

Leverages existing data:
- Risk (risk catalog with groupings, descriptions, NIST CSF function mappings, materiality)
- Threat (threat catalog with groupings, descriptions, materiality)
- RiskControlLink (many-to-many: risk → control – dormant but can be populated)
- ThreatControlLink (many-to-many: threat → control – dormant but can be populated)
- Control (canonical controls that mitigate risks)
- Control (relative_weighting for prioritization)
- Domain (for risk domain grouping)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.control import Control, Domain
from app.models.framework import Framework
from app.models.mapping import ControlMapping
from app.models.risk import Risk, RiskControlLink
from app.models.threat import Threat, ThreatControlLink

logger = logging.getLogger(__name__)


class RiskIntelligenceService:
    """Service for risk-to-control intelligence – mapping, heat maps, residual risk."""

    def __init__(self, session: Session):
        self.session = session

    # ── Risk Lookup: Find Controls That Mitigate a Risk ────────────

    def find_controls_for_risk(
        self,
        risk_id: int | None = None,
        risk_keyword: str | None = None,
    ) -> dict:
        """Find controls that mitigate a specific risk, using keyword matching.

        Since RiskControlLink and ThreatControlLink tables exist but may not be populated,
        this uses intelligent keyword matching between risk descriptions and control data.

        Args:
            risk_id: Specific risk ID to look up.
            risk_keyword: Free-text search for risks (e.g. 'vendor data leakage', 'ransomware').

        Returns:
            Matching risks with their mitigating controls and suggested actions.
        """
        if risk_id:
            risks = [self.session.query(Risk).filter(Risk.id == risk_id).first()]
        elif risk_keyword:
            pattern = f"%{risk_keyword}%"
            risks = (
                self.session.query(Risk)
                .filter(
                    Risk.risk_title.ilike(pattern)
                    | Risk.risk_description.ilike(pattern)
                    | Risk.risk_grouping.ilike(pattern)
                )
                .order_by(Risk.risk_number)
                .all()
            )
        else:
            return {"error": "Provide either risk_id or risk_keyword."}

        risks = [r for r in risks if r is not None]
        if not risks:
            return {"error": f"No risks found matching the criteria."}

        results = []
        for risk in risks:
            # First, try direct links via RiskControlLink
            linked_control_ids = {
                r[0] for r in
                self.session.query(RiskControlLink.control_id)
                .filter(RiskControlLink.risk_id == risk.id)
                .all()
            }

            # If no direct links, use keyword matching
            if not linked_control_ids:
                linked_control_ids = self._find_controls_by_keyword(
                    risk.risk_title or "",
                    risk.risk_description or "",
                )

            controls = self._get_control_details(linked_control_ids)

            # Also find relevant frameworks that map to these controls
            framework_codes = self._get_frameworks_for_controls(linked_control_ids)

            # Find related threats
            related_threats = (
                self.session.query(Threat)
                .filter(
                    Threat.threat_title.ilike(f"%{risk.risk_grouping or ''}%")
                    | Threat.threat_grouping.ilike(f"%{risk.risk_title or ''}%")
                )
                .limit(5)
                .all()
            )

            results.append({
                "risk": {
                    "number": risk.risk_number,
                    "grouping": risk.risk_grouping,
                    "title": risk.risk_title,
                    "description": risk.risk_description,
                    "nist_csf_function": risk.nist_csf_function,
                    "materiality": risk.materiality_considerations,
                },
                "mitigating_controls": {
                    "count": len(controls),
                    "controls": controls[:30],
                },
                "relevant_frameworks": framework_codes,
                "related_threats": [
                    {
                        "number": t.threat_number,
                        "grouping": t.threat_grouping,
                        "title": t.threat_title,
                    }
                    for t in related_threats
                ],
                "remediation_suggestions": self._generate_remediation_suggestions(controls),
            })

        return {"results": results, "total": len(results)}

    # ── Risk Heat Map ──────────────────────────────────────────────

    def generate_risk_heat_map(self, risk_grouping: str | None = None) -> dict:
        """Generate a risk heat map showing control coverage by risk grouping.

        Args:
            risk_grouping: Optional filter for a specific risk grouping (e.g. 'Access Control', 'Data Protection').

        Returns:
            Heat map data showing risk severity, control coverage, and gaps.
        """
        query = self.session.query(Risk).order_by(Risk.risk_number)
        if risk_grouping:
            query = query.filter(Risk.risk_grouping.ilike(f"%{risk_grouping}%"))

        risks = query.all()

        if not risks:
            return {"error": "No risks found.", "heat_map": []}

        # Group risks by their grouping category
        groupings: dict[str, dict] = {}
        for risk in risks:
            group = risk.risk_grouping or "Uncategorized"
            if group not in groupings:
                groupings[group] = {
                    "grouping": group,
                    "risk_count": 0,
                    "total_materiality": 0,
                    "nist_csf_functions": set(),
                    "controls_mapped": set(),
                    "risks": [],
                }
            groupings[group]["risk_count"] += 1
            groupings[group]["risks"].append({
                "number": risk.risk_number,
                "title": risk.risk_title,
                "nist_csf_function": risk.nist_csf_function,
                "materiality": risk.materiality_considerations,
            })
            if risk.nist_csf_function:
                groupings[group]["nist_csf_functions"].add(risk.nist_csf_function)

            # Find controls for this risk via keyword matching
            control_ids = self._find_controls_by_keyword(
                risk.risk_title or "",
                risk.risk_description or "",
            )
            groupings[group]["controls_mapped"].update(control_ids)

        # Build heat map entries
        heat_map = []
        for group_key, data in groupings.items():
            control_count = len(data["controls_mapped"])
            risk_density = data["risk_count"]

            # Heat level: higher risk density with fewer controls = hotter
            if risk_density > 5 and control_count < risk_density:
                heat_level = "critical"
            elif risk_density > 3 and control_count < risk_density * 1.5:
                heat_level = "high"
            elif risk_density > 1:
                heat_level = "medium"
            else:
                heat_level = "low"

            heat_map.append({
                "grouping": group_key,
                "risk_count": risk_density,
                "control_coverage": control_count,
                "coverage_ratio": round(control_count / max(risk_density, 1), 2),
                "heat_level": heat_level,
                "nist_csf_functions": list(data["nist_csf_functions"]),
            })

        heat_map.sort(key=lambda x: x["heat_level"], reverse=True)

        return {
            "heat_map": heat_map,
            "total_risk_groups": len(heat_map),
            "legend": {
                "critical": "High risk density, low control coverage — urgent attention needed",
                "high": "Significant risk area with moderate controls",
                "medium": "Managed risk with reasonable coverage",
                "low": "Well-controlled risk area",
            },
        }

    # ── Residual Risk Report ───────────────────────────────────────

    def residual_risk_report(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        assessed_maturity: dict[str, int] | None = None,
    ) -> dict:
        """Generate a residual risk report for a compliance framework.

        Based on assessed maturity levels, identifies which risks remain unmitigated.

        Args:
            framework_id / framework_name: The framework to assess.
            assessed_maturity: Dict of {scf_id: assessed_maturity_level}, same as MaturityService.

        Returns:
            Residual risk analysis with unmitigated risks, materiality, and recommendations.
        """
        if not framework_id and not framework_name:
            return {"error": "Provide either framework_id or framework_name."}

        from app.mcp.resolver import resolve_framework_id
        resolved_id = resolve_framework_id(self.session, framework_name=framework_name, framework_id=framework_id)
        if resolved_id is None:
            return {"error": f"Framework not found"}

        fw = self.session.query(Framework).filter(Framework.id == resolved_id).first()

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
            .all()
        )

        # Get all risks
        risks = self.session.query(Risk).all()

        # For each risk, determine if it's mitigated based on control maturity
        risk_analysis = []
        for risk in risks:
            control_ids = self._find_controls_by_keyword(
                risk.risk_title or "",
                risk.risk_description or "",
            )

            # Filter to controls that are in this framework
            framework_control_ids = {c.id for c in controls}
            relevant_control_ids = control_ids & framework_control_ids

            # For each relevant control, check assessed maturity
            mitigated = False
            weak_controls = []
            for c in controls:
                if c.id in relevant_control_ids:
                    maturity = (assessed_maturity or {}).get(c.scf_id, 0)
                    if maturity >= 3:
                        mitigated = True
                    else:
                        weak_controls.append({
                            "scf_id": c.scf_id,
                            "title": c.title,
                            "assessed_maturity": maturity,
                            "gap": 5 - maturity,
                        })

            residual_risk_level = "low" if mitigated else (
                "critical" if len(weak_controls) > 3 else "high"
            )

            risk_analysis.append({
                "risk": {
                    "number": risk.risk_number,
                    "grouping": risk.risk_grouping,
                    "title": risk.risk_title,
                    "nist_csf_function": risk.nist_csf_function,
                    "materiality": risk.materiality_considerations,
                },
                "status": "mitigated" if mitigated else "unmitigated",
                "residual_risk_level": residual_risk_level,
                "related_controls": weak_controls,
                "remediation_priority": 0 if mitigated else len(weak_controls) * 2,
            })

        # Sort: unmitigated first, by remediation priority
        risk_analysis.sort(key=lambda x: (0 if x["status"] == "unmitigated" else 1, -x["remediation_priority"]))

        # Summarize
        total_risks = len(risk_analysis)
        mitigated_count = sum(1 for r in risk_analysis if r["status"] == "mitigated")
        unmitigated_count = total_risks - mitigated_count

        return {
            "framework": {
                "code": fw.code if fw else "",
                "name": fw.name if fw else "",
            },
            "summary": {
                "total_risks_considered": total_risks,
                "mitigated": mitigated_count,
                "unmitigated": unmitigated_count,
                "coverage_percentage": round(mitigated_count / max(total_risks, 1) * 100, 1),
                "critical_risks": sum(1 for r in risk_analysis if r["residual_risk_level"] == "critical"),
            },
            "risk_analysis": risk_analysis[:50],
            "recommendations": self._generate_residual_risk_recommendations(risk_analysis),
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _find_controls_by_keyword(self, title: str, description: str) -> set[int]:
        """Find control IDs that are relevant to a risk based on keyword matching."""
        keywords = set()
        for text in [title, description]:
            if not text:
                continue
            # Extract key words from risk title/description
            for word in text.lower().replace(",", "").replace(".", "").split():
                word = word.strip()
                if len(word) > 3:
                    keywords.add(word)

        # Remove generic words
        generic = {"this", "that", "with", "from", "have", "been", "will",
                   "their", "they", "what", "when", "where", "which", "while",
                   "risk", "threat", "control", "data", "system", "security",
                   "information", "management", "may", "could", "would", "should"}
        keywords = keywords - generic

        if not keywords:
            return set()

        from sqlalchemy import or_
        conditions = []
        for kw in keywords:
            pattern = f"%{kw}%"
            conditions.append(Control.title.ilike(pattern))
            conditions.append(Control.description.ilike(pattern))
            conditions.append(Control.scf_id.ilike(pattern))

        controls = (
            self.session.query(Control.id)
            .filter(or_(*conditions))
            .limit(100)
            .all()
        )
        return {c[0] for c in controls}

    def _get_control_details(self, control_ids: set[int]) -> list[dict]:
        """Get detailed control info for a set of control IDs."""
        if not control_ids:
            return []

        controls = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(control_ids))
            .limit(50)
            .all()
        )

        return [
            {
                "scf_id": c.scf_id,
                "title": c.title,
                "description": c.description[:200] if c.description else None,
                "domain_code": c.domain.code if c.domain else None,
                "mitigation_level": self._estimate_mitigation_level(c),
            }
            for c in controls
        ]

    def _get_frameworks_for_controls(self, control_ids: set[int]) -> list[dict]:
        """Get frameworks that map to the given controls."""
        if not control_ids:
            return []

        fw_ids = (
            self.session.query(ControlMapping.framework_id)
            .filter(ControlMapping.control_id.in_(control_ids))
            .distinct()
            .all()
        )

        frameworks = (
            self.session.query(Framework)
            .filter(Framework.id.in_([r[0] for r in fw_ids]))
            .all()
        )

        return [
            {"code": fw.code, "name": fw.name, "category": fw.category}
            for fw in frameworks
        ]

    def _estimate_mitigation_level(self, ctrl: Control) -> str:
        """Estimate how strongly a control mitigates risk based on its characteristics."""
        title_lower = (ctrl.title or "").lower()
        desc_lower = (ctrl.description or "").lower()

        if any(w in title_lower or w in desc_lower for w in ["prevent", "block", "prohibit", "restrict", "authenticate"]):
            return "preventive"
        if any(w in title_lower or w in desc_lower for w in ["detect", "monitor", "alert", "audit", "review"]):
            return "detective"
        if any(w in title_lower or w in desc_lower for w in ["respond", "recover", "restore", "remediate", "correct"]):
            return "corrective"
        if any(w in title_lower or w in desc_lower for w in ["policy", "procedure", "training", "awareness"]):
            return "directive"

        return "general"

    def _generate_remediation_suggestions(self, controls: list[dict]) -> list[str]:
        """Generate remediation suggestions based on control mitigation types."""
        suggestions = []
        mitigation_types = {c.get("mitigation_level") for c in controls}

        if "preventive" not in mitigation_types:
            suggestions.append("Implement preventive controls (access controls, encryption, authentication)")
        if "detective" not in mitigation_types:
            suggestions.append("Add detective controls (monitoring, logging, audit trails)")
        if "corrective" not in mitigation_types:
            suggestions.append("Establish corrective controls (incident response, backup/restore)")

        if not suggestions:
            suggestions.append("Risk appears well-covered by existing controls")
            suggestions.append("Regularly test control effectiveness through audits and exercises")

        return suggestions

    def _generate_residual_risk_recommendations(self, risk_analysis: list[dict]) -> list[str]:
        """Generate recommendations for residual risk reduction."""
        recs = []
        critical = [r for r in risk_analysis if r["residual_risk_level"] == "critical"]
        high = [r for r in risk_analysis if r["residual_risk_level"] == "high"]

        if critical:
            recs.append(f"CRITICAL: {len(critical)} risk areas have no adequate control coverage")
        if high:
            recs.append(f"HIGH: {len(high)} risk areas need stronger controls")
        if not critical and not high:
            recs.append("Residual risk is within acceptable levels")

        recs.append("Prioritize controls with the highest relative weighting for maximum risk reduction")
        recs.append("Schedule control effectiveness testing for all 'preventive' controls")

        return recs
