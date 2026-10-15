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

    def get_related_frameworks(self, framework_id: int, limit: int = 10) -> list[Framework]:
        """Frameworks sharing the most SCF controls with the given framework."""
        return [r["framework"] for r in self.get_related_with_overlap(framework_id, limit=limit)]

    def get_related_with_overlap(self, framework_id: int, limit: int = 10) -> list[dict]:
        """Rank other frameworks by the number of SCF controls they share with this one.

        Each item has ``framework``, ``shared_controls`` and ``overlap_percent``
        (shared controls as a percentage of this framework's mapped controls).
        """
        own = (
            self.session.query(ControlMapping.control_id)
            .filter(ControlMapping.framework_id == framework_id)
            .distinct()
            .subquery()
        )
        total = self.session.query(func.count()).select_from(own).scalar() or 0
        if not total:
            return []
        shared = func.count(func.distinct(ControlMapping.control_id))
        rows = (
            self.session.query(ControlMapping.framework_id, shared.label("shared"))
            .filter(
                ControlMapping.control_id.in_(self.session.query(own.c.control_id)),
                ControlMapping.framework_id != framework_id,
            )
            .group_by(ControlMapping.framework_id)
            .order_by(shared.desc(), ControlMapping.framework_id)
            .limit(limit)
            .all()
        )
        frameworks = {
            fw.id: fw
            for fw in self.session.query(Framework).filter(Framework.id.in_([r[0] for r in rows]))
        }
        return [
            {
                "framework": frameworks[fid],
                "shared_controls": n,
                "overlap_percent": round(100.0 * n / total, 1),
            }
            for fid, n in rows
            if fid in frameworks
        ]

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

    def get_all_version_counts(self) -> dict[int, int]:
        """Get version counts for ALL frameworks in a single query."""
        rows = (
            self.session.query(FrameworkVersion.framework_id, func.count(FrameworkVersion.id))
            .group_by(FrameworkVersion.framework_id)
            .all()
        )
        return {row[0]: row[1] for row in rows}

    def get_all_jurisdiction_codes(self) -> dict[int, list[str]]:
        """Get jurisdiction codes for ALL frameworks in a single query."""
        rows = (
            self.session.query(FrameworkJurisdiction.framework_id, Jurisdiction.code)
            .join(Jurisdiction, FrameworkJurisdiction.jurisdiction_id == Jurisdiction.id)
            .order_by(Jurisdiction.code)
            .all()
        )
        result: dict[int, list[str]] = {}
        for fid, code in rows:
            result.setdefault(fid, []).append(code)
        return result

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
