"""Reference service – lightweight lookups for reference/taxonomy data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.control import Domain
from app.models.framework import FrameworkVersion


class ReferenceService:
    """Service layer for reference data lookups."""

    def __init__(self, session: Session):
        self.session = session

    def get_version_history(self, framework_id: int) -> list[dict]:
        """Get version history for a framework."""
        versions = (
            self.session.query(FrameworkVersion)
            .filter(FrameworkVersion.framework_id == framework_id)
            .order_by(FrameworkVersion.release_date.desc().nullslast())
            .all()
        )
        return [
            {
                "id": v.id,
                "framework_id": v.framework_id,
                "version_label": v.version_label,
                "release_date": v.release_date.isoformat() if v.release_date else None,
                "status": v.status,
                "notes": v.notes,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    def search_domains(self, query_str: str) -> list[Domain]:
        """Search domains by code or name."""
        return (
            self.session.query(Domain)
            .filter(
                Domain.code.ilike(f"%{query_str}%")
                | Domain.name.ilike(f"%{query_str}%")
            )
            .order_by(Domain.code)
            .all()
        )
