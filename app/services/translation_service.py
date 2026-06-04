"""Framework Translation Service – translates between compliance frameworks using the 41,000+ STRM mappings.

Leverages existing data:
- ControlMapping (41,000+ cross-framework mappings with STRM types: EQUAL, SUBSET OF, SUPERSET OF, INTERSECTS WITH)
- Control (canonical SCF controls as the translation pivot)
- Framework (source and target framework metadata)
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


class TranslationService:
    """Service for translating between compliance frameworks using SCF as a pivot."""

    def __init__(self, session: Session):
        self.session = session

    # ── Core: Framework-to-Framework Translation ─────────────────────

    def translate_framework(
        self,
        source_framework_id: int | None = None,
        source_framework_name: str | None = None,
        target_framework_id: int | None = None,
        target_framework_name: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """Translate controls from one framework to another via SCF pivot.

        Uses the 41,000+ STRM-annotated control mappings to determine:
        - Which controls are equivalent across frameworks (EQUAL)
        - Which controls partially overlap (SUBSET/SUPERSET OF, INTERSECTS WITH)

        Translation path: Source Framework → SCF Controls (via mappings) → Target Framework (via mappings)

        Args:
            source_framework_id: Source framework ID.
            source_framework_name: Source framework name (e.g. 'ISO 27001').
            target_framework_id: Target framework ID.
            target_framework_name: Target framework name (e.g. 'POPIA').

        Returns:
            Translation result with covered controls, gaps, unique obligations, and implementation order.
        """
        if not source_framework_id and not source_framework_name:
            return {"error": "Provide source_framework_id or source_framework_name."}
        if not target_framework_id and not target_framework_name:
            return {"error": "Provide target_framework_id or target_framework_name."}

        from app.mcp.resolver import resolve_framework_id
        src_id = resolve_framework_id(self.session, framework_name=source_framework_name, framework_id=source_framework_id)
        tgt_id = resolve_framework_id(self.session, framework_name=target_framework_name, framework_id=target_framework_id)

        if src_id is None:
            return {"error": f"Source framework not found: '{source_framework_name or source_framework_id}'"}
        if tgt_id is None:
            return {"error": f"Target framework not found: '{target_framework_name or target_framework_id}'"}

        if src_id == tgt_id:
            return {"error": "Source and target frameworks are the same."}

        src_fw = self.session.query(Framework).filter(Framework.id == src_id).first()
        tgt_fw = self.session.query(Framework).filter(Framework.id == tgt_id).first()

        # Get all SCF control IDs mapped to source framework
        src_control_ids = {
            r[0] for r in
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == src_id)
            .all()
        }

        # Get all SCF control IDs mapped to target framework
        tgt_control_ids = {
            r[0] for r in
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == tgt_id)
            .all()
        }

        # Already covered = intersection (controls present in both, so they translate)
        covered_ids = src_control_ids & tgt_control_ids

        # Missing = in target but NOT in source
        missing_ids = tgt_control_ids - src_control_ids

        # Unique to source (no translation needed, but documented)
        source_unique_ids = src_control_ids - tgt_control_ids

        # Get detailed mapping info for covered controls
        covered_details = self._get_translation_details(covered_ids, src_id, tgt_id, src_fw, tgt_fw)

        # Get missing control details
        missing_controls = self._get_controls_with_mappings(missing_ids, tgt_id)
        source_unique_controls = self._get_controls_with_mappings(source_unique_ids, src_id)

        # Apply domain filter if requested
        if domain:
            domain_obj = self.session.query(Domain).filter(
                Domain.code.ilike(domain) | Domain.name.ilike(domain)
            ).first()
            if domain_obj:
                covered_details = [c for c in covered_details if c.get("domain_code") == domain_obj.code]
                missing_controls = [c for c in missing_controls if c.get("domain_code") == domain_obj.code]
                source_unique_controls = [c for c in source_unique_controls if c.get("domain_code") == domain_obj.code]

        # Build summary
        coverage_pct = round(len(covered_ids) / max(len(tgt_control_ids), 1) * 100, 1)

        # Implementation order: sort missing controls by weight descending
        implementation_order = sorted(
            [m for m in missing_controls if m.get("relative_weighting")],
            key=lambda x: x.get("relative_weighting", 0) or 0,
            reverse=True,
        )
        # Append those without weights
        no_weight = [m for m in missing_controls if not m.get("relative_weighting")]
        implementation_order.extend(no_weight)

        return {
            "translation": {
                "source": {"id": src_id, "code": src_fw.code if src_fw else "", "name": src_fw.name if src_fw else ""},
                "target": {"id": tgt_id, "code": tgt_fw.code if tgt_fw else "", "name": tgt_fw.name if tgt_fw else ""},
            },
            "summary": {
                "source_total_controls": len(src_control_ids),
                "target_total_controls": len(tgt_control_ids),
                "already_covered": len(covered_ids),
                "missing_controls": len(missing_ids),
                "source_unique": len(source_unique_ids),
                "coverage_percentage": coverage_pct,
                "domain_filter": domain,
            },
            "already_covered": covered_details[:100],
            "missing_controls": missing_controls,
            "source_unique_controls": source_unique_controls,
            "implementation_order": implementation_order[:100],
        }

    # ── Control Equivalency Lookup ──────────────────────────────────

    def find_control_equivalents(
        self,
        scf_id: str | None = None,
        control_id: int | None = None,
    ) -> dict:
        """Find equivalent controls across all frameworks for a given SCF control.

        Uses STRM types to classify the nature of each equivalence.

        Args:
            scf_id: SCF control ID (e.g. 'AC-01-01').
            control_id: Internal control ID (alternative to scf_id).

        Returns:
            List of equivalent controls with framework info and mapping type.
        """
        if scf_id:
            ctrl = self.session.query(Control).filter(Control.scf_id == scf_id).first()
        elif control_id:
            ctrl = self.session.query(Control).filter(Control.id == control_id).first()
        else:
            return {"error": "Provide either scf_id or control_id."}

        if not ctrl:
            return {"error": f"Control not found: scf_id={scf_id}, control_id={control_id}"}

        mappings = (
            self.session.query(ControlMapping)
            .filter(ControlMapping.control_id == ctrl.id)
            .all()
        )

        equivalents = []
        for m in mappings:
            fw = self.session.query(Framework).filter(Framework.id == m.framework_id).first()
            equivalents.append({
                "framework_code": fw.code if fw else "",
                "framework_name": fw.name if fw else "",
                "mapped_control_id": m.mapped_control_id,
                "mapped_control_title": m.mapped_control_title,
                "mapping_type": m.mapping_type,
                "strm_type": m.strm_type,
                "relationship_description": self._describe_strm_relationship(m.strm_type),
            })

        return {
            "control": {
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "description": ctrl.description,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
            },
            "equivalents": equivalents,
            "total_frameworks": len(equivalents),
        }

    # ── Gap Analysis ────────────────────────────────────────────────

    def identify_gaps(
        self,
        source_framework_id: int | None = None,
        source_framework_name: str | None = None,
        target_framework_id: int | None = None,
        target_framework_name: str | None = None,
    ) -> dict:
        """Identify compliance gaps between two frameworks.

        This is essentially the 'differences' mode with enhanced detail:
        - Which controls exist in source but not target (excess)
        - Which controls exist in target but not source (gaps)
        - STRM-annotated partial coverage analysis
        """
        return self.translate_framework(
            source_framework_id=source_framework_id,
            source_framework_name=source_framework_name,
            target_framework_id=target_framework_id,
            target_framework_name=target_framework_name,
        )

    # ── Private Helpers ─────────────────────────────────────────────

    def _get_translation_details(
        self,
        control_ids: set[int],
        src_fw_id: int,
        tgt_fw_id: int,
        src_fw: Framework | None,
        tgt_fw: Framework | None,
    ) -> list[dict]:
        """Get detailed translation info for a set of shared controls."""
        if not control_ids:
            return []

        controls = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(control_ids))
            .order_by(Control.scf_id)
            .all()
        )

        details = []
        for ctrl in controls:
            # Get source mapping
            src_mapping = (
                self.session.query(ControlMapping)
                .filter(
                    ControlMapping.control_id == ctrl.id,
                    ControlMapping.framework_id == src_fw_id,
                )
                .first()
            )
            # Get target mapping
            tgt_mapping = (
                self.session.query(ControlMapping)
                .filter(
                    ControlMapping.control_id == ctrl.id,
                    ControlMapping.framework_id == tgt_fw_id,
                )
                .first()
            )

            details.append({
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
                "source_mapped_id": src_mapping.mapped_control_id if src_mapping else None,
                "target_mapped_id": tgt_mapping.mapped_control_id if tgt_mapping else None,
                "strm_type": tgt_mapping.strm_type if tgt_mapping else None,
                "relationship": self._describe_strm_relationship(tgt_mapping.strm_type if tgt_mapping else None),
                "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
            })

        return details

    def _get_controls_with_mappings(self, control_ids: set[int], fw_id: int) -> list[dict]:
        """Get controls with their mappings for a specific framework."""
        if not control_ids:
            return []

        controls = (
            self.session.query(Control)
            .options(joinedload(Control.domain))
            .filter(Control.id.in_(control_ids))
            .order_by(Control.scf_id)
            .all()
        )

        result = []
        for ctrl in controls:
            mapping = (
                self.session.query(ControlMapping)
                .filter(
                    ControlMapping.control_id == ctrl.id,
                    ControlMapping.framework_id == fw_id,
                )
                .first()
            )
            result.append({
                "scf_id": ctrl.scf_id,
                "title": ctrl.title,
                "description": ctrl.description[:300] if ctrl.description else None,
                "domain_code": ctrl.domain.code if ctrl.domain else None,
                "mapped_control_id": mapping.mapped_control_id if mapping else None,
                "relative_weighting": float(ctrl.relative_weighting) if ctrl.relative_weighting else None,
            })

        return result

    def _describe_strm_relationship(self, strm_type: str | None) -> str:
        """Provide a human-readable description of an STRM relationship type."""
        descriptions = {
            "EQUAL": "The controls are equivalent in scope and intent",
            "SUBSET OF": "This control is a subset of the corresponding control — it covers fewer requirements",
            "SUPERSET OF": "This control is a superset — it covers additional requirements beyond the corresponding control",
            "INTERSECTS WITH": "The controls overlap partially but each has unique requirements not in the other",
        }
        if strm_type and strm_type in descriptions:
            return descriptions[strm_type]
        return "Relationship not specified — further analysis needed"
