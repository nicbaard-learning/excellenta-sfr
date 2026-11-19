"""Framework service – business logic for framework browsing and reference."""

from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from sqlalchemy.orm import joinedload

from app.models.control import Control, Domain, Principle
from app.models.framework import Framework, FrameworkVersion
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping
from app.models.requirement import FrameworkRequirement

# Provision kinds that SCF mapping references point at.
MAPPABLE_KINDS = {"section", "article"}

_PROVISION_NUMBER = re.compile(
    r"^\s*(?:(?:sec(?:tion)?|art(?:icle)?|s)\.?\s*)?(\d+[A-Z]?)\b", re.IGNORECASE
)


def provision_number(mapped_ref: str | None) -> str | None:
    """The section/article number an SCF mapping reference points at.

    "19(1)(a)" -> "19", "Sec 22" -> "22", "Art. 33(1)" -> "33", "s 3A" -> "3A".
    Returns None when the reference doesn't start with a number.
    """
    if not mapped_ref:
        return None
    m = _PROVISION_NUMBER.match(mapped_ref)
    return m.group(1).upper() if m else None


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

    def get_requirement_counts(self) -> dict[int, int]:
        """Number of loaded provisions per framework id (frameworks with none are absent)."""
        rows = (
            self.session.query(FrameworkRequirement.framework_id, func.count(FrameworkRequirement.id))
            .group_by(FrameworkRequirement.framework_id)
            .all()
        )
        return {fw_id: count for fw_id, count in rows}

    def get_framework(self, framework_id: int) -> Framework | None:
        """Get a single framework by ID."""
        return self.session.query(Framework).filter(Framework.id == framework_id).first()

    def get_framework_by_code(self, code: str) -> Framework | None:
        """Lookup a framework by its short code."""
        return self.session.query(Framework).filter(Framework.code == code).first()

    def get_scf_framework(self) -> Framework | None:
        """The canonical SCF framework row."""
        return self.session.query(Framework).filter(Framework.is_scf.is_(True)).first()

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

    def get_requirements(self, framework_id: int) -> list[dict]:
        """The framework's own provisions in display order, each with the SCF controls mapped to it.

        Each item has ``requirement`` and ``controls`` (Control rows, sorted by
        SCF #). SCF names provisions in its own style ("19(1)(a)", "Sec 22"),
        so mappings are matched on the section/article number only; that
        matching applies to sections and articles, not to chapters or
        regulations.
        """
        requirements = (
            self.session.query(FrameworkRequirement)
            .filter(FrameworkRequirement.framework_id == framework_id)
            .order_by(FrameworkRequirement.display_order, FrameworkRequirement.id)
            .all()
        )
        if not requirements:
            return []

        by_number: dict[str, set[int]] = {}
        rows = (
            self.session.query(ControlMapping.mapped_control_id, ControlMapping.control_id)
            .filter(ControlMapping.framework_id == framework_id)
            .all()
        )
        for mapped_ref, control_id in rows:
            number = provision_number(mapped_ref)
            if number:
                by_number.setdefault(number, set()).add(control_id)

        wanted = set().union(*by_number.values()) if by_number else set()
        controls = {
            c.id: c
            for c in self.session.query(Control).filter(Control.id.in_(wanted))
        } if wanted else {}

        result = []
        for req in requirements:
            ids = by_number.get(req.number.upper(), set()) if (
                req.number and req.kind in MAPPABLE_KINDS
            ) else set()
            mapped = sorted((controls[i] for i in ids if i in controls), key=lambda c: c.scf_id)
            result.append({"requirement": req, "controls": mapped})
        return result

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
