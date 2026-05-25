"""Comparison service – GRC use cases for framework comparison and deduplication."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.framework import Framework
from app.models.mapping import ControlMapping


class ComparisonService:
    """Service layer for framework comparison operations."""

    def __init__(self, session: Session):
        self.session = session

    def _get_control_ids_for_framework(self, framework_id: int) -> set[int]:
        """Get all control IDs mapped to a framework."""
        results = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == framework_id)
            .all()
        )
        return {r[0] for r in results}

    def _get_controls(self, control_ids: set[int]) -> list[Control]:
        """Get Control objects for a set of IDs, ordered by scf_id."""
        if not control_ids:
            return []
        return (
            self.session.query(Control)
            .filter(Control.id.in_(control_ids))
            .order_by(Control.scf_id)
            .all()
        )

    def _get_framework_name(self, framework_id: int) -> str:
        """Get framework name by ID."""
        fw = self.session.query(Framework).filter(Framework.id == framework_id).first()
        return fw.name if fw else f"Framework {framework_id}"

    def compare(self, framework_ids: list[int]) -> dict:
        """Full comparison: overlapping controls and gaps per framework."""
        if len(framework_ids) < 2:
            raise ValueError("At least two framework IDs are required for comparison.")

        fw_controls = {fid: self._get_control_ids_for_framework(fid) for fid in framework_ids}
        names = {fid: self._get_framework_name(fid) for fid in framework_ids}

        # Overlap = intersection of all sets
        all_sets = list(fw_controls.values())
        overlap_ids = all_sets[0].intersection(*all_sets[1:])

        # Gaps = controls in each framework not in the overlap
        gaps: dict[int, set[int]] = {}
        for fid in framework_ids:
            gaps[fid] = fw_controls[fid] - overlap_ids

        return {
            "framework_ids": framework_ids,
            "framework_names": names,
            "overlap_count": len(overlap_ids),
            "overlapping_controls": self._get_controls(overlap_ids),
            "gap_controls": {fid: self._get_controls(gaps[fid]) for fid in framework_ids},
            "unique_control_count": {fid: len(gaps[fid]) for fid in framework_ids},
        }

    def intersection(self, framework_ids: list[int], domain_code: str | None = None) -> dict:
        """Return the intersection (common controls) across all given frameworks.

        Args:
            framework_ids: List of framework IDs to compare.
            domain_code: Optional SCF domain code to filter results (e.g. "IR", "AC", "AU").
        """
        if len(framework_ids) < 2:
            raise ValueError("At least two framework IDs are required.")

        fw_controls = [self._get_control_ids_for_framework(fid) for fid in framework_ids]
        common_ids = fw_controls[0].intersection(*fw_controls[1:])
        names = {fid: self._get_framework_name(fid) for fid in framework_ids}

        controls = self._get_controls(common_ids)

        # Filter by domain if requested
        if domain_code:
            from app.models.control import Domain
            domain = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain_code) | Domain.name.ilike(domain_code))
                .first()
            )
            if domain:
                controls = [c for c in controls if c.domain_id == domain.id]

        return {
            "framework_ids": framework_ids,
            "framework_names": names,
            "total_common_controls": len(controls),
            "common_controls": controls,
            "domain_filter": domain_code,
        }

    def differences(self, base_framework_id: int, compare_framework_id: int, domain_code: str | None = None) -> dict:
        """Return controls in one but not the other (symmetric difference).

        Args:
            base_framework_id: The reference framework.
            compare_framework_id: The framework to compare against.
            domain_code: Optional SCF domain code to filter results (e.g. "IR", "AC", "AU").
        """
        base_ids = self._get_control_ids_for_framework(base_framework_id)
        compare_ids = self._get_control_ids_for_framework(compare_framework_id)

        in_base_not_compare = base_ids - compare_ids
        in_compare_not_base = compare_ids - base_ids

        def _filter_by_domain(controls: list[Control]) -> list[Control]:
            if not domain_code:
                return controls
            from app.models.control import Domain
            domain = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain_code) | Domain.name.ilike(domain_code))
                .first()
            )
            if domain:
                controls = [c for c in controls if c.domain_id == domain.id]
            return controls

        base_controls = _filter_by_domain(self._get_controls(in_base_not_compare))
        compare_controls = _filter_by_domain(self._get_controls(in_compare_not_base))

        return {
            "base_framework_id": base_framework_id,
            "base_framework_name": self._get_framework_name(base_framework_id),
            "compare_framework_id": compare_framework_id,
            "compare_framework_name": self._get_framework_name(compare_framework_id),
            "in_base_not_compare": base_controls,
            "in_compare_not_base": compare_controls,
            "base_count": len(base_controls),
            "compare_count": len(compare_controls),
            "domain_filter": domain_code,
        }

    def common_control_set(self, framework_ids: list[int], domain_code: str | None = None) -> dict:
        """Return deduplicated common controls with mapping details per framework.

        Args:
            framework_ids: List of framework IDs to compare.
            domain_code: Optional SCF domain code to filter results (e.g. "IR", "AC", "AU").
        """
        if len(framework_ids) < 2:
            raise ValueError("At least two framework IDs are required.")

        fw_control_sets = [self._get_control_ids_for_framework(fid) for fid in framework_ids]
        common_ids = fw_control_sets[0].intersection(*fw_control_sets[1:])
        names = {fid: self._get_framework_name(fid) for fid in framework_ids}

        if not common_ids:
            return {
                "framework_ids": framework_ids,
                "framework_names": names,
                "total_controls": 0,
                "controls": [],
            }

        common_controls = self._get_controls(common_ids)

        # Filter by domain if requested (before building details)
        if domain_code:
            from app.models.control import Domain
            domain = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain_code) | Domain.name.ilike(domain_code))
                .first()
            )
            if domain:
                common_controls = [c for c in common_controls if c.domain_id == domain.id]

        controls_with_details = []

        for ctrl in common_controls:
            # Get mappings for this control across all requested frameworks
            mappings = (
                self.session.query(ControlMapping)
                .filter(
                    ControlMapping.control_id == ctrl.id,
                    ControlMapping.framework_id.in_(framework_ids),
                )
                .all()
            )
            mapping_dict: dict[int, dict] = {}
            frameworks_present = set()
            for m in mappings:
                fw = self.session.query(Framework).filter(Framework.id == m.framework_id).first()
                mapping_dict[m.framework_id] = {
                    "id": m.id,
                    "framework_code": fw.code if fw else "",
                    "framework_name": self._get_framework_name(m.framework_id),
                    "mapped_control_id": m.mapped_control_id,
                    "mapped_control_title": m.mapped_control_title,
                    "mapping_type": m.mapping_type,
                }
                frameworks_present.add(m.framework_id)

            controls_with_details.append({
                "control": {
                    "id": ctrl.id,
                    "scf_id": ctrl.scf_id,
                    "title": ctrl.title,
                    "description": ctrl.description,
                    "control_question": ctrl.control_question,
                    "conformity_cadence": ctrl.conformity_cadence,
                    "relative_weighting": ctrl.relative_weighting,
                    "applicability_context": ctrl.applicability_context,
                    "created_at": ctrl.created_at,
                    "updated_at": ctrl.updated_at,
                },
                "mappings": mapping_dict,
                "frameworks_present": list(frameworks_present),
            })

        return {
            "framework_ids": framework_ids,
            "framework_names": names,
            "total_controls": len(controls_with_details),
            "controls": controls_with_details,
            "domain_filter": domain_code,
        }
