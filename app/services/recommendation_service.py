"""Recommendation service – TPRM use cases for framework recommendations."""

from __future__ import annotations

import logging

from typing import Any

from sqlalchemy import or_ as _or
from sqlalchemy.orm import Session

from app.models.business_model import BusinessModel
from app.models.control import Control, Domain
from app.models.framework import Framework, FrameworkVersion
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)


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
        firm_size: str | None = None,
        threat_profile: str | None = None,
        search: str | None = None,
    ) -> dict:
        """Recommend frameworks based on context attributes.

        Returns data-rich compliance blueprints including control details,
        maturity levels, and firm-size solutions where available.
        """
        query = self.session.query(Framework).filter(Framework.is_scf == False)  # noqa: E712

        # Build filter criteria from applicability rules
        filters_applied: list[str] = []

        if jurisdiction:
            # Try lookup by code, name, or region — so "NA", "North America",
            # "United States", and "US" all resolve to the matching jurisdictions.
            j = (
                self.session.query(Jurisdiction)
                .filter(
                    Jurisdiction.code.ilike(jurisdiction)
                    | Jurisdiction.name.ilike(jurisdiction)
                    | Jurisdiction.region.ilike(jurisdiction)
                )
                .first()
            )
            if j:
                filters_applied.append(f"jurisdiction={j.code}")
                # Find frameworks linked to this jurisdiction
                query = query.filter(
                    Framework.jurisdictions.any(jurisdiction_id=j.id)
                )
            else:
                # Jurisdiction didn't match — note it but don't filter
                filters_applied.append(f"jurisdiction='{jurisdiction}' (not found, skipped)")

        if domain:
            d = (
                self.session.query(Domain)
                .filter(Domain.code.ilike(domain) | Domain.name.ilike(domain))
                .first()
            )
            if d:
                filters_applied.append(f"domain={d.code}")
                # Filter to frameworks that have controls in this domain
                fw_ids_in_domain = (
                    self.session.query(ControlMapping.framework_id)
                    .join(Control, ControlMapping.control_id == Control.id)
                    .filter(Control.domain_id == d.id)
                    .distinct()
                    .subquery()
                )
                query = query.filter(Framework.id.in_(fw_ids_in_domain))

        if category:
            filters_applied.append(f"category={category}")
            query = query.filter(Framework.category.ilike(f"%{category}%"))

        if business_model:
            filters_applied.append(f"business_model={business_model}")

            # Use module-level imports for Control, Domain, ControlMapping

            # Condition 1: via applicability_rules (exact business_model match)
            rule_condition = Framework.applicability_rules.any(
                attribute_name="business_model",
                attribute_value=business_model,
            )

            bm = self.session.query(BusinessModel).filter(
                BusinessModel.code == business_model
            ).first()

            conditions = [rule_condition]

            if bm:
                # Build search keywords from business model code + name
                keywords = {bm.code}  # e.g. "IAM"
                for part in bm.name.replace("&", "").split():
                    part = part.strip()
                    if len(part) >= 3:
                        keywords.add(part)

                # Remove overly generic words that would match too broadly
                generic = {
                    "management", "service", "services", "provider",
                    "platform", "software", "technology", "solution",
                    "vendor", "professional", "security", "data",
                    "financial", "administration", "system", "systems",
                }
                keywords = keywords - generic

                if keywords:
                    # Match against control titles, SCF IDs, and domain names
                    match_conditions = []
                    for kw in keywords:
                        match_conditions.append(
                            Control.title.ilike(f"%{kw}%")
                        )
                        match_conditions.append(
                            Control.scf_id.ilike(f"{kw}%")
                        )
                        match_conditions.append(
                            Domain.name.ilike(f"%{kw}%")
                        )
                        match_conditions.append(
                            Domain.code.ilike(f"%{kw}%")
                        )

                    fw_via_controls = (
                        self.session.query(ControlMapping.framework_id)
                        .join(Control, ControlMapping.control_id == Control.id)
                        .join(Domain, Control.domain_id == Domain.id)
                        .filter(_or(*match_conditions))
                        .distinct()
                        .subquery()
                    )
                    conditions.append(Framework.id.in_(fw_via_controls))

            query = query.filter(_or(*conditions))

        if privacy_context:
            filters_applied.append(f"privacy_context={privacy_context}")
            query = query.filter(
                Framework.applicability_rules.any(
                    attribute_name="privacy_context",
                    attribute_value=privacy_context,
                )
            )

        # Support both size (deprecated) and firm_size (new)
        effective_size = firm_size or size
        if effective_size:
            filters_applied.append(f"size={effective_size}")
            query = query.filter(
                Framework.applicability_rules.any(
                    attribute_name="size",
                    attribute_value=effective_size,
                )
            )

        if threat_profile:
            filters_applied.append(f"threat_profile={threat_profile}")
            # Threat profile filtering via keyword search on framework name/category
            pattern = f"%{threat_profile}%"
            query = query.filter(
                Framework.name.ilike(pattern)
                | Framework.description.ilike(pattern)
                | Framework.category.ilike(pattern)
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

        # ── Graceful fallback: if combined strict filters return 0 results,
        #    try again without jurisdiction and privacy_context (the most
        #    common over-filters from natural-language queries).
        if not frameworks and filters_applied:
            retry_filters = [f for f in filters_applied
                             if not f.startswith("jurisdiction=") and not f.startswith("privacy_context=")]
            if len(retry_filters) < len(filters_applied):
                logger.info(
                    "0 results with strict filters (%s) — retrying without jurisdiction/privacy",
                    filters_applied,
                )
                return self.recommend_by_context(
                    category=category,
                    business_model=business_model,
                    domain=domain,
                    size=size,
                    firm_size=firm_size,
                    threat_profile=threat_profile,
                    search=search,
                )

        # Build data-rich compliance blueprints (imports are at module level)
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

            # Get jurisdictions for this framework
            jur_codes = [
                j.code for j in
                (self.session.query(Jurisdiction)
                 .join(FrameworkJurisdiction)
                 .filter(FrameworkJurisdiction.framework_id == fw.id)
                 .all())
            ]

            # Get top controls (first 10) with maturity and firm-size data
            mapped_control_ids = (
                self.session.query(ControlMapping.control_id)
                .filter(ControlMapping.framework_id == fw.id)
                .subquery()
            )
            controls = (
                self.session.query(Control)
                .filter(Control.id.in_(mapped_control_ids))
                .order_by(Control.scf_id)
                .limit(25)
                .all()
            )

            top_controls = []
            for c in controls:
                tc = {
                    "scf_id": c.scf_id,
                    "title": c.title,
                    "description": c.description[:300] if c.description else None,
                    "domain_code": c.domain.code if c.domain else None,
                    "relative_weighting": float(c.relative_weighting) if c.relative_weighting else None,
                    "cmm_level_0": c.cmm_level_0,
                    "cmm_level_1": c.cmm_level_1,
                    "cmm_level_2": c.cmm_level_2,
                    "cmm_level_3": c.cmm_level_3,
                    "cmm_level_4": c.cmm_level_4,
                    "cmm_level_5": c.cmm_level_5,
                    "solutions_micro_small": c.solutions_micro_small,
                    "solutions_small": c.solutions_small,
                    "solutions_medium": c.solutions_medium,
                    "solutions_large": c.solutions_large,
                    "solutions_enterprise": c.solutions_enterprise,
                }
                top_controls.append(tc)

            results.append({
                "id": fw.id,
                "code": fw.code,
                "name": fw.name,
                "category": fw.category,
                "version_label": active_ver.version_label if active_ver else None,
                "is_scf": fw.is_scf,
                "jurisdiction_codes": jur_codes,
                "control_count": len(controls),
                "top_controls": top_controls,
            })

        return {
            "recommendations": results,
            "total": len(results),
            "applied_filters": filters_applied,
            "firm_size": effective_size,
            "threat_profile": threat_profile,
            "note": (
                "Some optional filters were skipped because they matched no data. "
                "Try calling with fewer filters (e.g. just business_model) for broader results."
                if not frameworks and filters_applied
                else None
            ),
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
