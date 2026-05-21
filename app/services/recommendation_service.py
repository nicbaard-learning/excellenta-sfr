"""Recommendation service – TPRM use cases for framework recommendations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.business_model import BusinessModel
from app.models.control import Domain
from app.models.framework import Framework, FrameworkVersion
from app.models.jurisdiction import Jurisdiction


class RecommendationService:
    """Service layer for framework recommendation operations."""

    def __init__(self, session: Session):
        self.session = session

    def recommend_by_context(
        self,
        category: str | None = None,
        business_model: str | None = None,
        jurisdiction: str | None = None,
        domain: str | None = None,
        privacy_context: str | None = None,
        size: str | None = None,
        search: str | None = None,
    ) -> dict:
        """Recommend frameworks based on context attributes.

        Uses applicability rules and category hints to suggest relevant frameworks.
        Falls back to keyword text search (code, name, description, publisher)
        when junction tables are empty.
        """
        query = self.session.query(Framework).filter(Framework.is_scf == False)  # noqa: E712

        # Build filter criteria from applicability rules
        filters_applied: list[str] = []

        if jurisdiction:
            j = (
                self.session.query(Jurisdiction)
                .filter(
                    Jurisdiction.code.ilike(jurisdiction) | Jurisdiction.name.ilike(jurisdiction)
                )
                .first()
            )
            if j:
                filters_applied.append(f"jurisdiction={j.code}")
                # Find frameworks linked to this jurisdiction
                query = query.filter(
                    Framework.jurisdictions.any(jurisdiction_id=j.id)
                )

        if domain:
            d = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain) | Domain.name.ilike(domain))
                .first()
            )
            if d:
                filters_applied.append(f"domain={d.code}")

        if category:
            filters_applied.append(f"category={category}")
            query = query.filter(Framework.category.ilike(f"%{category}%"))

        if business_model:
            filters_applied.append(f"business_model={business_model}")
            # Filter via applicability_rules
            query = query.filter(
                Framework.applicability_rules.any(
                    attribute_name="business_model",
                    attribute_value=business_model,
                )
            )

        if privacy_context:
            filters_applied.append(f"privacy_context={privacy_context}")
            query = query.filter(
                Framework.applicability_rules.any(
                    attribute_name="privacy_context",
                    attribute_value=privacy_context,
                )
            )

        if size:
            filters_applied.append(f"size={size}")
            query = query.filter(
                Framework.applicability_rules.any(
                    attribute_name="size",
                    attribute_value=size,
                )
            )

        if search:
            filters_applied.append(f"search={search}")
            pattern = f"%{search}%"
            query = query.filter(
                Framework.code.ilike(pattern)
                | Framework.name.ilike(pattern)
                | Framework.description.ilike(pattern)
                | Framework.publisher.ilike(pattern)
            )

        frameworks = query.order_by(Framework.code).all()

        results = []
        for fw in frameworks:
            active_ver = (
                self.session.query(FrameworkVersion)
                .filter(
                    FrameworkVersion.framework_id == fw.id,
                    FrameworkVersion.status == "active",
                )
                .first()
            )
            results.append({
                "id": fw.id,
                "code": fw.code,
                "name": fw.name,
                "category": fw.category,
                "version_label": active_ver.version_label if active_ver else None,
                "is_scf": fw.is_scf,
            })

        return {
            "recommendations": results,
            "total": len(results),
            "applied_filters": filters_applied,
        }

    def recommend_by_category(self, category: str) -> dict:
        """Recommend frameworks for a given TPRM vendor category."""
        return self.recommend_by_context(category=category)

    def recommend_by_business_model(self, business_model: str) -> dict:
        """Recommend frameworks for a given business model."""
        return self.recommend_by_context(business_model=business_model)

    def list_categories(self) -> list[str]:
        """List distinct framework categories (non-SCF)."""
        results = (
            self.session.query(Framework.category)
            .filter(Framework.is_scf == False, Framework.category.isnot(None))  # noqa: E712
            .distinct()
            .order_by(Framework.category)
            .all()
        )
        return [r[0] for r in results]

    def list_domains(self) -> list[dict[str, Any]]:
        """List all SCF domains with control counts."""
        from sqlalchemy import func

        from app.models.control import Control

        results = (
            self.session.query(
                Domain.id,
                Domain.code,
                Domain.name,
                Domain.description,
                func.count(Control.id).label("control_count"),
            )
            .outerjoin(Control, Control.domain_id == Domain.id)
            .group_by(Domain.id, Domain.code, Domain.name, Domain.description)
            .order_by(Domain.code)
            .all()
        )
        return [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "control_count": r.control_count,
            }
            for r in results
        ]

    def list_jurisdictions(self) -> list[dict[str, Any]]:
        """List all jurisdictions."""
        jurs = self.session.query(Jurisdiction).order_by(Jurisdiction.code).all()
        return [
            {"id": j.id, "code": j.code, "name": j.name, "region": j.region}
            for j in jurs
        ]

    def list_business_models(self) -> list[dict[str, Any]]:
        """List all business models."""
        models = self.session.query(BusinessModel).order_by(BusinessModel.code).all()
        return [
            {
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "category": m.category,
            }
            for m in models
        ]
