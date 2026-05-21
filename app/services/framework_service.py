"""Framework service – business logic for framework browsing and reference."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from sqlalchemy.orm import joinedload

from app.models.control import Control, Domain, Principle
from app.models.framework import Framework, FrameworkVersion
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping


class FrameworkService:
    """Service layer for framework-related operations."""

    def __init__(self, session: Session):
        self.session = session

    def list_frameworks(self, category: str | None = None) -> list[Framework]:
        """List all frameworks, optionally filtered by category."""
        query = self.session.query(Framework).order_by(Framework.code)
        if category:
            query = query.filter(Framework.category == category)
        return query.all()

    def get_framework(self, framework_id: int) -> Framework | None:
        """Get a single framework by ID."""
        return self.session.query(Framework).filter(Framework.id == framework_id).first()

    def get_framework_by_code(self, code: str) -> Framework | None:
        """Lookup a framework by its short code."""
        return self.session.query(Framework).filter(Framework.code == code).first()

    def get_versions(self, framework_id: int) -> list[FrameworkVersion]:
        """Get all versions of a framework, newest first."""
        return (
            self.session.query(FrameworkVersion)
            .filter(FrameworkVersion.framework_id == framework_id)
            .order_by(FrameworkVersion.release_date.desc().nullslast())
            .all()
        )

    def get_active_version(self, framework_id: int) -> FrameworkVersion | None:
        """Get the active version of a framework."""
        return (
            self.session.query(FrameworkVersion)
            .filter(
                FrameworkVersion.framework_id == framework_id,
                FrameworkVersion.status == "active",
            )
            .first()
        )

    def get_related_frameworks(self, framework_id: int) -> list[Framework]:
        """Find frameworks that share control mappings with the given framework."""
        # Find controls mapped to this framework
        mapped_control_ids = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == framework_id)
            .subquery()
        )
        # Find other frameworks mapped to the same controls
        related_ids = (
            self.session.query(ControlMapping.framework_id)
            .filter(
                ControlMapping.control_id.in_(mapped_control_ids),
                ControlMapping.framework_id != framework_id,
            )
            .distinct()
            .subquery()
        )
        return self.session.query(Framework).filter(Framework.id.in_(related_ids)).all()

    def get_control_count(self, framework_id: int) -> int:
        """Count controls mapped to a framework (via control_mappings)."""
        return (
            self.session.query(func.count(ControlMapping.id))
            .filter(ControlMapping.framework_id == framework_id)
            .scalar()
            or 0
        )

    def get_all_control_counts(self) -> dict[int, int]:
        """Get control counts for ALL frameworks in a single query."""
        rows = (
            self.session.query(
                ControlMapping.framework_id,
                func.count(ControlMapping.id),
            )
            .group_by(ControlMapping.framework_id)
            .all()
        )
        return {row[0]: row[1] for row in rows}

    def get_framework_jurisdictions(self, framework_id: int) -> list[Jurisdiction]:
        """Get all jurisdictions associated with a framework."""
        return (
            self.session.query(Jurisdiction)
            .join(FrameworkJurisdiction)
            .filter(FrameworkJurisdiction.framework_id == framework_id)
            .all()
        )

    def get_controls_for_framework(self, framework_id: int) -> list[Control]:
        """Get all controls mapped to a given framework."""
        mapped_control_ids = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == framework_id)
            .subquery()
        )
        return (
            self.session.query(Control)
            .options(joinedload(Control.domain), joinedload(Control.principle))
            .filter(Control.id.in_(mapped_control_ids))
            .order_by(Control.scf_id)
            .all()
        )
