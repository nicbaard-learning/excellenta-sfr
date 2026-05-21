"""Control service – business logic for control lookup and detail."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.assessment import AssessmentObjective
from app.models.compensating import CompensatingControlLink
from app.models.control import Control, Domain
from app.models.evidence import EvidenceArtifact
from app.models.framework import Framework
from app.models.mapping import AuthoritativeSource, ControlMapping


class ControlService:
    """Service layer for control-related operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_control(self, control_id: int) -> Control | None:
        """Get a single control by ID."""
        return self.session.query(Control).filter(Control.id == control_id).first()

    def get_control_by_scf_id(self, scf_id: str) -> Control | None:
        """Lookup a control by its SCF # identifier."""
        return self.session.query(Control).filter(Control.scf_id == scf_id).first()

    def get_mappings(self, control_id: int) -> list[dict]:
        """Get all framework mappings for a control, with framework details."""
        mappings = (
            self.session.query(ControlMapping, Framework)
            .join(Framework, ControlMapping.framework_id == Framework.id)
            .filter(ControlMapping.control_id == control_id)
            .all()
        )
        return [
            {
                "id": mapping.id,
                "framework_code": framework.code,
                "framework_name": framework.name,
                "mapped_control_id": mapping.mapped_control_id,
                "mapped_control_title": mapping.mapped_control_title,
                "mapping_type": mapping.mapping_type,
            }
            for mapping, framework in mappings
        ]

    def get_assessment_objectives(self, control_id: int) -> list[AssessmentObjective]:
        """Get all assessment objectives for a control."""
        return (
            self.session.query(AssessmentObjective)
            .filter(AssessmentObjective.control_id == control_id)
            .all()
        )

    def get_evidence_artifacts(self, control_id: int) -> list[EvidenceArtifact]:
        """Get all evidence artifacts for a control."""
        return (
            self.session.query(EvidenceArtifact)
            .filter(EvidenceArtifact.control_id == control_id)
            .all()
        )

    def get_compensating_controls(self, control_id: int) -> list[CompensatingControlLink]:
        """Get all compensating controls for a control."""
        return (
            self.session.query(CompensatingControlLink)
            .filter(CompensatingControlLink.control_id == control_id)
            .all()
        )

    def get_authoritative_sources(self, control_id: int) -> list[AuthoritativeSource]:
        """Get all authoritative sources for a control."""
        return (
            self.session.query(AuthoritativeSource)
            .filter(AuthoritativeSource.control_id == control_id)
            .all()
        )

    def get_control_detail(self, control_id: int) -> dict | None:
        """Get full control detail with counts of related entities."""
        control = self.get_control(control_id)
        if control is None:
            return None

        domain = self.session.query(Domain).filter(Domain.id == control.domain_id).first() if control.domain_id else None

        return {
            "id": control.id,
            "scf_id": control.scf_id,
            "title": control.title,
            "description": control.description,
            "control_question": control.control_question,
            "conformity_cadence": control.conformity_cadence,
            "relative_weighting": control.relative_weighting,
            "applicability_context": control.applicability_context,
            "domain_code": domain.code if domain else None,
            "domain_name": domain.name if domain else None,
            "created_at": control.created_at,
            "updated_at": control.updated_at,
            "mappings": self.get_mappings(control_id),
            "objective_count": len(self.get_assessment_objectives(control_id)),
            "evidence_count": len(self.get_evidence_artifacts(control_id)),
            "compensating_count": len(self.get_compensating_controls(control_id)),
        }
