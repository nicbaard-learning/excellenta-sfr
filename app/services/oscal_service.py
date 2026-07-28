"""OSCAL Export Service – serializes SFR data to NIST OSCAL JSON format.

Supports two OSCAL models:
- Catalog: Full control catalog (all domains + controls + assessment objectives)
- Profile: Framework-specific control selection (which controls map to a framework)

References:
  NIST SP 800-53: https://pages.nist.gov/OSCAL/
  OSCAL JSON Schema: https://github.com/usnistgov/OSCAL
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.models.assessment import AssessmentObjective
from app.models.control import Control, Domain
from app.models.evidence import EvidenceArtifact
from app.models.framework import Framework
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)


class OscalService:
    """Service for generating OSCAL JSON exports from SFR data."""

    def __init__(self, session: Session):
        self.session = session

    # ── Catalog Export ──────────────────────────────────────────────

    def export_catalog(
        self,
        domain_code: str | None = None,
    ) -> dict:
        """Generate an OSCAL catalog JSON document.

        An OSCAL catalog describes a control framework as a hierarchy of
        groups (domains) and controls. Includes assessment objectives
        as control parts.

        Args:
            domain_code: Optional domain code to restrict the export.

        Returns:
            Complete OSCAL catalog JSON dict.
        """
        catalog_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Build groups = domains with their controls
        query = self.session.query(Domain).order_by(Domain.code)
        domains = query.all()

        groups = []
        for domain in domains:
            if domain_code and domain.code.lower() != domain_code.lower():
                continue

            controls = (
                self.session.query(Control)
                .options(
                    joinedload(Control.domain),
                    joinedload(Control.assessment_objectives),
                )
                .filter(Control.domain_id == domain.id)
                .order_by(Control.scf_id)
                .all()
            )

            if not controls:
                continue

            oscal_controls = []
            for ctrl in controls:
                oscal_ctrl = self._control_to_oscal(
                    ctrl,
                    objectives=ctrl.assessment_objectives,
                )
                if oscal_ctrl:
                    oscal_controls.append(oscal_ctrl)

            if oscal_controls:
                groups.append({
                    "id": domain.code,
                    "class": "domain",
                    "title": domain.name or domain.code,
                    "controls": oscal_controls,
                })

        # Top-level controls (those without a domain)
        ungrouped = (
            self.session.query(Control)
            .options(joinedload(Control.assessment_objectives))
            .filter(Control.domain_id.is_(None))
            .order_by(Control.scf_id)
            .all()
        )
        top_controls = []
        for ctrl in ungrouped:
            oc = self._control_to_oscal(
                ctrl,
                objectives=ctrl.assessment_objectives,
            )
            if oc:
                top_controls.append(oc)

        catalog: dict[str, Any] = {
            "catalog": {
                "uuid": catalog_uuid,
                "metadata": {
                    "title": "Secure Controls Framework (SCF) 2026.1",
                    "published": now,
                    "last-modified": now,
                    "version": "2026.1",
                    "oscal-version": "1.1.2",
                    "parties": [
                        {
                            "uuid": str(uuid.uuid4()),
                            "name": "Secure Controls Framework",
                            "type": "organization",
                        }
                    ],
                    "props": [
                        {"name": "catalog-type", "value": "scf-control-catalog"},
                        {"name": "total-domains", "value": str(len(groups))},
                    ],
                },
                "groups": groups,
                "back-matter": {
                    "resources": [
                        {
                            "uuid": str(uuid.uuid4()),
                            "title": "Secure Controls Framework (SCF) 2026.1",
                            "description": (
                                "The SCF is a comprehensive controls framework "
                                "that maps to multiple regulatory and industry standards."
                            ),
                        }
                    ]
                },
            }
        }

        if top_controls:
            catalog["catalog"]["controls"] = top_controls

        return catalog

    # ── Profile Export ──────────────────────────────────────────────

    def export_profile(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
    ) -> dict:
        """Generate an OSCAL profile JSON document for a specific framework.

        An OSCAL profile represents which controls from a catalog are
        selected/required by a particular compliance framework.

        Args:
            framework_id: Internal framework ID.
            framework_name: Natural framework name.

        Returns:
            Complete OSCAL profile JSON dict.
        """
        if not framework_id and not framework_name:
            return {"error": "Provide framework_id or framework_name."}

        from app.mcp.resolver import resolve_framework_id
        resolved_id = resolve_framework_id(
            self.session,
            framework_name=framework_name,
            framework_id=framework_id,
        )
        if resolved_id is None:
            return {"error": f"Framework not found: '{framework_name or framework_id}'"}

        fw = self.session.query(Framework).filter(Framework.id == resolved_id).first()
        if not fw:
            return {"error": f"Framework {resolved_id} not found"}

        profile_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Get all mapped controls for this framework
        mappings = (
            self.session.query(ControlMapping)
            .filter(ControlMapping.framework_id == resolved_id)
            .all()
        )

        # Get unique controls
        control_ids = {m.control_id for m in mappings}
        controls = (
            self.session.query(Control)
            .options(
                joinedload(Control.domain),
                joinedload(Control.assessment_objectives),
            )
            .filter(Control.id.in_(control_ids))
            .order_by(Control.scf_id)
            .all()
        )

        # Get framework-specific mapping details
        mapping_by_scf: dict[str, list[dict]] = {}
        for m in mappings:
            ctrl = next((c for c in controls if c.id == m.control_id), None)
            scf_id = ctrl.scf_id if ctrl else f"id-{m.control_id}"
            if scf_id not in mapping_by_scf:
                mapping_by_scf[scf_id] = []
            mapping_by_scf[scf_id].append({
                "mapped_control_id": m.mapped_control_id,
                "strm_type": m.strm_type,
                "mapping_type": m.mapping_type,
            })

        # Group controls by domain for the profile
        domain_map: dict[str, list[dict]] = {}
        ungrouped: list[dict] = []

        for ctrl in controls:
            oscal_ctrl = self._control_to_oscal(
                ctrl,
                framework_mappings=mapping_by_scf.get(ctrl.scf_id, []),
                objectives=ctrl.assessment_objectives,
            )
            if not oscal_ctrl:
                continue

            domain_code = ctrl.domain.code if ctrl.domain else None
            domain_name = ctrl.domain.name if ctrl.domain else None

            if domain_code:
                if domain_code not in domain_map:
                    domain_map[domain_code] = {
                        "id": domain_code,
                        "class": "domain",
                        "title": domain_name or domain_code,
                        "controls": [],
                    }
                domain_map[domain_code]["controls"].append(oscal_ctrl)
            else:
                ungrouped.append(oscal_ctrl)

        profile: dict[str, Any] = {
            "profile": {
                "uuid": profile_uuid,
                "metadata": {
                    "title": f"{fw.name} — SCF Profile",
                    "published": now,
                    "last-modified": now,
                    "version": fw.code or "1.0",
                    "oscal-version": "1.1.2",
                    "description": (
                        f"Controls from the SCF catalog applicable to {fw.name}. "
                        f"Total: {len(controls)} controls across {len(domain_map)} domains."
                    ),
                    "props": [
                        {"name": "framework-code", "value": fw.code or ""},
                        {"name": "framework-category", "value": fw.category or ""},
                        {"name": "is-scf", "value": str(fw.is_scf or False).lower()},
                        {"name": "total-controls", "value": str(len(controls))},
                    ],
                },
                "imports": [
                    {
                        "href": "#scf-catalog",
                        "include-controls": [
                            {
                                "with-ids": [c.scf_id for c in controls],
                            }
                        ],
                    }
                ],
                "groups": list(domain_map.values()),
                "back-matter": {
                    "resources": [
                        {
                            "uuid": str(uuid.uuid4()),
                            "title": fw.name or "Unknown Framework",
                            "description": fw.description or "",
                            "props": [
                                {"name": "source-url", "value": fw.source_url or ""},
                                {"name": "publisher", "value": fw.publisher or ""},
                            ],
                        }
                    ]
                },
            }
        }

        if ungrouped:
            profile["profile"]["controls"] = ungrouped

        return profile

    # ── Assessment Results Export ───────────────────────────────────

    def export_assessment_results(
        self,
        framework_id: int | None = None,
        framework_name: str | None = None,
        assessed_levels: dict[str, int] | None = None,
    ) -> dict:
        """Generate an OSCAL assessment-results JSON document.

        This maps assessed SCR-CMM maturity levels to OSCAL's
        assessment results format, showing which controls have
        evidence artifacts and their assessed maturity.

        Args:
            framework_id: Internal framework ID.
            framework_name: Natural framework name.
            assessed_levels: Dict mapping scf_id -> assessed maturity level (0-5).

        Returns:
            Partial OSCAL assessment-results JSON dict.
        """
        if not framework_id and not framework_name:
            return {"error": "Provide framework_id or framework_name."}

        from app.mcp.resolver import resolve_framework_id
        resolved_id = resolve_framework_id(
            self.session,
            framework_name=framework_name,
            framework_id=framework_id,
        )
        if resolved_id is None:
            return {"error": f"Framework not found: '{framework_name or framework_id}'"}

        fw = self.session.query(Framework).filter(Framework.id == resolved_id).first()
        if not fw:
            return {"error": f"Framework {resolved_id} not found"}

        now = datetime.now(timezone.utc).isoformat()
        result_uuid = str(uuid.uuid4())

        # Get controls for this framework
        mapped_ids = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == resolved_id)
            .all()
        )
        control_ids = {r[0] for r in mapped_ids}
        controls = (
            self.session.query(Control)
            .options(
                joinedload(Control.domain),
                joinedload(Control.assessment_objectives),
                joinedload(Control.evidence_artifacts),
            )
            .filter(Control.id.in_(control_ids))
            .order_by(Control.scf_id)
            .all()
        )

        # Build observations per control
        observations = []
        for ctrl in controls:
            artifacts = ctrl.evidence_artifacts  # pre-loaded
            objectives = ctrl.assessment_objectives  # pre-loaded

            assessed_level = (assessed_levels or {}).get(ctrl.scf_id, 0)

            observation = {
                "uuid": str(uuid.uuid4()),
                "description": f"Maturity assessment for {ctrl.scf_id}: {ctrl.title}",
                "props": [
                    {"name": "scf-id", "value": ctrl.scf_id},
                    {"name": "assessed-maturity-level", "value": str(assessed_level)},
                    {"name": "maturity-gap", "value": str(5 - assessed_level)},
                    {"name": "evidence-count", "value": str(len(artifacts))},
                    {"name": "objective-count", "value": str(len(objectives))},
                ],
                "subjects": [
                    {
                        "uuid-ref": ctrl.scf_id,
                        "type": "control",
                        "title": ctrl.title,
                    }
                ],
                "relevant-evidence": [
                    {
                        "href": f"#erl-{a.erl_number}" if a.erl_number else "#",
                        "description": a.evidence_title or "",
                    }
                    for a in artifacts[:5]
                ],
            }
            observations.append(observation)

        return {
            "assessment-results": {
                "uuid": result_uuid,
                "metadata": {
                    "title": f"Maturity Assessment: {fw.name}",
                    "published": now,
                    "last-modified": now,
                    "version": "1.0",
                    "oscal-version": "1.1.2",
                    "props": [
                        {"name": "framework-code", "value": fw.code or ""},
                        {"name": "total-controls", "value": str(len(controls))},
                        {"name": "total-assessed", "value": str(len(observations))},
                    ],
                },
                "results": [
                    {
                        "uuid": str(uuid.uuid4()),
                        "title": f"Assessment Results: {fw.name}",
                        "description": (
                            f"SCR-CMM based maturity assessment for {fw.name}. "
                            f"Assessed {len(observations)} controls."
                        ),
                        "start": now,
                        "observations": observations,
                    }
                ],
            }
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _control_to_oscal(
        self,
        ctrl: Control,
        framework_mappings: list[dict] | None = None,
        objectives: list[AssessmentObjective] | None = None,
    ) -> dict | None:
        """Convert a Control model instance to an OSCAL control object.

        Args:
            ctrl: Control model instance.
            framework_mappings: Optional list of framework mapping dicts
                (only used for profile exports).
            objectives: Optional pre-loaded list of AssessmentObjective instances.
                If not provided, queries the DB (fallback). Avoids N+1 queries
                when callers pre-load via joinedload.
        """
        oscal_ctrl: dict[str, Any] = {
            "id": ctrl.scf_id,
            "title": ctrl.title,
            "props": [
                {"name": "scf-id", "value": ctrl.scf_id},
            ],
            "parts": [],
        }

        # Add weighting if present
        if ctrl.relative_weighting is not None:
            oscal_ctrl["props"].append({
                "name": "relative-weighting",
                "value": str(float(ctrl.relative_weighting)),
            })

        # Add description as a part
        if ctrl.description:
            oscal_ctrl["parts"].append({
                "id": f"{ctrl.scf_id}_desc",
                "name": "description",
                "prose": ctrl.description[:2000],
            })

        # Add control question
        if ctrl.control_question:
            oscal_ctrl["parts"].append({
                "id": f"{ctrl.scf_id}_question",
                "name": "question",
                "prose": ctrl.control_question[:2000],
            })

        # Add assessment objectives as parts (use pre-loaded if provided)
        if objectives is None:
            objectives = (
                self.session.query(AssessmentObjective)
                .filter(AssessmentObjective.control_id == ctrl.id)
                .all()
            )
        for obj in objectives:
            part: dict[str, Any] = {
                "id": obj.objective_code or f"{ctrl.scf_id}_obj_{obj.id}",
                "name": "objective",
                "prose": obj.objective_text or "",
            }
            if obj.objective_code:
                part["props"] = [
                    {"name": "objective-code", "value": obj.objective_code}
                ]
            oscal_ctrl["parts"].append(part)

        # Add framework-specific mapping info (for profiles)
        if framework_mappings:
            for fm in framework_mappings:
                if fm.get("mapped_control_id"):
                    oscal_ctrl["props"].append({
                        "name": "mapped-control-id",
                        "value": fm["mapped_control_id"],
                        "remarks": (
                            f"strm: {fm.get('strm_type', 'unknown')}"
                            if fm.get("strm_type") else None
                        ),
                    })

        # Add conformity cadence
        if ctrl.conformity_cadence:
            oscal_ctrl["props"].append({
                "name": "conformity-cadence",
                "value": ctrl.conformity_cadence,
            })

        # Add PPTDF applicability
        if ctrl.pptdf_applicability:
            oscal_ctrl["props"].append({
                "name": "pptdf-applicability",
                "value": ctrl.pptdf_applicability,
            })

        return oscal_ctrl
