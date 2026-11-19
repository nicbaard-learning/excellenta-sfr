"""Recommendation service – TPRM use cases for framework recommendations."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import func, or_ as _or
from sqlalchemy.orm import Session, joinedload

from app.models.applicability import FrameworkApplicabilityRule
from app.models.business_model import BusinessModel
from app.models.control import Control, Domain
from app.models.framework import Framework, FrameworkVersion
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)

# EU member states: frameworks tagged "EU" (GDPR, NIS2, DORA, ...) also apply
# to a request for any of these jurisdictions.
EU_MEMBER_STATES: frozenset[str] = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})

# Common names that differ from the seeded jurisdiction code/name.
JURISDICTION_ALIASES: dict[str, str] = {
    "UK": "GB",
    "GREAT BRITAIN": "GB",
    "USA": "US",
    "UAE": "AE",
    "RSA": "ZA",
}

# Optional filters, in the order they are relaxed when the combination
# matches nothing. Jurisdiction is never relaxed; free-text search is the
# most explicit signal and is relaxed last.
RELAX_ORDER = ("category", "size", "threat_profile", "privacy_context", "domain", "business_model", "search")

DEFAULT_MAX_CONTROLS = 25
_CACHE_TTL_SECONDS = 3600
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def clear_recommendation_cache() -> None:
    """Drop cached recommendation results (call after data changes)."""
    with _cache_lock:
        _cache.clear()


class RecommendationInputError(ValueError):
    """Raised for requests that cannot be answered (unknown jurisdiction, no filters)."""

    def __init__(self, message: str, **extra: Any):
        super().__init__(message)
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        return {"detail": str(self), **self.extra}


class RecommendationService:
    """Service layer for framework recommendation operations."""

    def __init__(self, session: Session):
        self.session = session

    # ── Public API ────────────────────────────────────────────────────
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
        max_controls: int = DEFAULT_MAX_CONTROLS,
    ) -> dict:
        """Recommend frameworks based on context attributes.

        * ``jurisdiction`` is a hard filter: results are frameworks tagged for
          that jurisdiction (scope ``"jurisdiction"``) plus untagged, global
          frameworks (scope ``"global"``). Frameworks tagged only for other
          jurisdictions are never returned.
        * The other filters are optional and are relaxed in ``RELAX_ORDER``
          when their combination matches nothing.

        Raises RecommendationInputError when no filter is given or the
        jurisdiction is unknown.
        """
        filters = {
            "category": _clean(category),
            "business_model": _clean(business_model),
            "domain": _clean(domain),
            "privacy_context": _clean(privacy_context),
            "size": _clean(firm_size) or _clean(size),
            "threat_profile": _clean(threat_profile),
            "search": _clean(search),
        }
        jurisdiction = _clean(jurisdiction)
        if not jurisdiction and not any(filters.values()):
            raise RecommendationInputError(
                "At least one filter is required (e.g. jurisdiction, business_model, search).",
                valid_filters=["jurisdiction", *RELAX_ORDER],
            )
        max_controls = max(0, min(int(max_controls or 0), 100))

        cache_key = (jurisdiction and jurisdiction.upper(), tuple(sorted(filters.items())), max_controls)
        with _cache_lock:
            hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]

        result = self._recommend(jurisdiction, filters, max_controls)
        with _cache_lock:
            _cache[cache_key] = (time.monotonic(), result)
        return result

    # ── Core logic ────────────────────────────────────────────────────
    def _recommend(self, jurisdiction: str | None, filters: dict[str, str | None], max_controls: int) -> dict:
        # Validate the jurisdiction before doing any other work.
        jur_codes, jur_label = self._resolve_jurisdiction(jurisdiction) if jurisdiction else (set(), "")
        fw_jurisdictions = self._framework_jurisdiction_codes()
        all_ids = {
            fid for (fid,) in self.session.query(Framework.id).filter(Framework.is_scf == False)  # noqa: E712
        }

        # Each supplied filter resolves to the set of framework ids it allows.
        matches: dict[str, set[int]] = {}
        labels: dict[str, str] = {}
        unmatched: list[str] = []
        for name in RELAX_ORDER:
            value = filters[name]
            if not value:
                continue
            ids, label = self._filter_ids(name, value)
            if ids is None:
                unmatched.append(f"{name}='{value}' (unknown value, ignored)")
                continue
            matches[name] = ids
            labels[name] = label

        notes: list[str] = []
        if jurisdiction:
            country_pool = {fid for fid in all_ids if fw_jurisdictions.get(fid, set()) & jur_codes}
            global_pool = {fid for fid in all_ids if not fw_jurisdictions.get(fid)}

            country_ids, country_applied, country_relaxed = _apply_with_relaxation(
                country_pool, matches, allow_empty_filters=True
            )
            global_ids, global_applied, global_relaxed = _apply_with_relaxation(
                global_pool, matches, allow_empty_filters=not matches
            )
            groups = [("jurisdiction", country_ids), ("global", global_ids)]
            scope_filters = {
                "jurisdiction": [jur_label] + [labels[n] for n in country_applied],
                "global": [labels[n] for n in global_applied],
            }
            applied = [jur_label] + [labels[n] for n in RELAX_ORDER if n in country_applied or n in global_applied]
            relaxed = sorted(set(country_relaxed) | set(global_relaxed), key=RELAX_ORDER.index)
            if not country_pool:
                notes.append(f"No frameworks in the SCF workbook are specific to {jur_label.split('=', 1)[1]}.")
            elif country_relaxed and len(country_relaxed) == len(matches):
                notes.append("Jurisdiction-specific frameworks are listed regardless of the other filters.")
        else:
            ids, applied_names, relaxed = _apply_with_relaxation(all_ids, matches, allow_empty_filters=False)
            groups = [
                ("jurisdiction", {fid for fid in ids if fw_jurisdictions.get(fid)}),
                ("global", {fid for fid in ids if not fw_jurisdictions.get(fid)}),
            ]
            applied = [labels[n] for n in RELAX_ORDER if n in applied_names]
            scope_filters = {"jurisdiction": applied, "global": applied}

        if relaxed:
            notes.append(
                "No frameworks matched every filter, so these were relaxed: "
                + ", ".join(labels[n] for n in relaxed) + "."
            )
        notes.extend(unmatched)

        recommendations = self._build_blueprints(groups, fw_jurisdictions, max_controls)
        if not recommendations:
            notes.append("No frameworks matched. Try fewer filters.")

        return {
            "recommendations": recommendations,
            "total": len(recommendations),
            "applied_filters": applied,
            "applied_filters_by_scope": scope_filters,
            "relaxed_filters": [labels[n] for n in relaxed],
            "firm_size": filters["size"],
            "threat_profile": filters["threat_profile"],
            "note": " ".join(notes) or None,
        }

    def _resolve_jurisdiction(self, value: str) -> tuple[set[str], str]:
        """Resolve a code, name or region to the set of jurisdiction codes it covers."""
        key = JURISDICTION_ALIASES.get(value.upper(), value).upper()
        # One query for the whole (small) table: each extra round trip to a
        # remote database adds noticeable latency, and an unknown value must
        # return 422 quickly.
        rows = self.session.query(Jurisdiction.code, Jurisdiction.name, Jurisdiction.region).all()
        match = next((c for c, _, _ in rows if (c or "").upper() == key), None) or next(
            (c for c, n, _ in rows if (n or "").upper() == key), None
        )
        if match:
            codes = {match}
            label = match
        else:
            codes = {c for c, _, r in rows if (r or "").upper() == key}
            if not codes:
                raise RecommendationInputError(
                    f"Unknown jurisdiction '{value}'. Use an ISO code or name from "
                    "GET /api/recommend/jurisdictions.",
                    valid_jurisdictions=sorted(c for c, _, _ in rows),
                )
            label = key
        if codes & EU_MEMBER_STATES:
            codes.add("EU")
        return codes, f"jurisdiction={label}"

    def _framework_jurisdiction_codes(self) -> dict[int, set[str]]:
        rows = (
            self.session.query(FrameworkJurisdiction.framework_id, Jurisdiction.code)
            .join(Jurisdiction, FrameworkJurisdiction.jurisdiction_id == Jurisdiction.id)
            .all()
        )
        result: dict[int, set[str]] = {}
        for fid, code in rows:
            result.setdefault(fid, set()).add(code)
        return result

    def _filter_ids(self, name: str, value: str) -> tuple[set[int] | None, str]:
        """Return (framework ids allowed by this filter, label), or (None, label) if unknown."""
        s = self.session
        if name == "domain":
            d = s.query(Domain).filter(Domain.code.ilike(value) | Domain.name.ilike(value)).first()
            if not d:
                return None, f"domain={value}"
            rows = (
                s.query(ControlMapping.framework_id)
                .join(Control, ControlMapping.control_id == Control.id)
                .filter(Control.domain_id == d.id)
                .distinct()
            )
            return {r[0] for r in rows}, f"domain={d.code}"

        if name == "category":
            rows = s.query(Framework.id).filter(Framework.category.ilike(f"%{value}%"))
            return {r[0] for r in rows}, f"category={value}"

        if name == "business_model":
            ids = self._rule_ids("business_model", value)
            bm = s.query(BusinessModel).filter(func.upper(BusinessModel.code) == value.upper()).first()
            if bm:
                ids |= self._business_model_keyword_ids(bm)
            return ids, f"business_model={bm.code if bm else value}"

        if name == "privacy_context":
            return self._rule_ids("privacy_context", value), f"privacy_context={value}"

        if name == "size":
            return self._rule_ids("size", value.lower()), f"size={value}"

        if name == "threat_profile":
            pattern = f"%{value}%"
            rows = s.query(Framework.id).filter(
                Framework.name.ilike(pattern) | Framework.description.ilike(pattern) | Framework.category.ilike(pattern)
            )
            return {r[0] for r in rows}, f"threat_profile={value}"

        if name == "search":
            pattern = f"%{value}%"
            rows = s.query(Framework.id).filter(
                Framework.code.ilike(pattern)
                | Framework.name.ilike(pattern)
                | Framework.description.ilike(pattern)
                | Framework.publisher.ilike(pattern)
            )
            return {r[0] for r in rows}, f"search={value}"

        raise ValueError(name)

    def _rule_ids(self, attribute: str, value: str) -> set[int]:
        rows = self.session.query(FrameworkApplicabilityRule.framework_id).filter(
            FrameworkApplicabilityRule.attribute_name == attribute,
            func.upper(FrameworkApplicabilityRule.attribute_value) == value.upper(),
        )
        return {r[0] for r in rows}

    def _business_model_keyword_ids(self, bm: BusinessModel) -> set[int]:
        """Frameworks mapped to controls whose title/ID/domain mentions the business model."""
        keywords = {bm.code}
        for part in bm.name.replace("&", "").split():
            part = part.strip()
            if len(part) >= 3:
                keywords.add(part)
        # Overly generic words would match almost every framework.
        keywords = {k for k in keywords if k.lower() not in {
            "management", "service", "services", "provider", "platform", "software", "technology",
            "solution", "vendor", "professional", "security", "data", "financial", "administration",
            "system", "systems",
        }}
        if not keywords:
            return set()
        conditions = []
        for kw in keywords:
            conditions += [
                Control.title.ilike(f"%{kw}%"),
                Control.scf_id.ilike(f"{kw}%"),
                Domain.name.ilike(f"%{kw}%"),
                Domain.code.ilike(f"%{kw}%"),
            ]
        rows = (
            self.session.query(ControlMapping.framework_id)
            .join(Control, ControlMapping.control_id == Control.id)
            .join(Domain, Control.domain_id == Domain.id)
            .filter(_or(*conditions))
            .distinct()
        )
        return {r[0] for r in rows}

    # ── Result building (constant number of queries) ──────────────────
    def _build_blueprints(
        self,
        groups: list[tuple[str, set[int]]],
        fw_jurisdictions: dict[int, set[str]],
        max_controls: int,
    ) -> list[dict]:
        ids = set().union(*(g for _, g in groups))
        if not ids:
            return []

        frameworks = {fw.id: fw for fw in self.session.query(Framework).filter(Framework.id.in_(ids))}
        versions = {
            v.framework_id: v.version_label
            for v in self.session.query(FrameworkVersion).filter(
                FrameworkVersion.framework_id.in_(ids), FrameworkVersion.status == "active"
            )
        }
        control_counts = dict(
            self.session.query(ControlMapping.framework_id, func.count(func.distinct(ControlMapping.control_id)))
            .filter(ControlMapping.framework_id.in_(ids))
            .group_by(ControlMapping.framework_id)
            .all()
        )
        top_controls = self._top_controls(ids, max_controls) if max_controls else {}

        results = []
        for scope, group in groups:
            for fid in sorted(group, key=lambda i: frameworks[i].code):
                fw = frameworks[fid]
                results.append({
                    "id": fw.id,
                    "code": fw.code,
                    "name": fw.name,
                    "description": fw.description,
                    "publisher": fw.publisher,
                    "source_url": fw.source_url,
                    "category": fw.category,
                    "version_label": versions.get(fid),
                    "is_scf": fw.is_scf,
                    "scope": scope,
                    "jurisdiction_codes": sorted(fw_jurisdictions.get(fid, set())),
                    "control_count": control_counts.get(fid, 0),
                    "top_controls": top_controls.get(fid, []),
                })
        return results

    def _top_controls(self, framework_ids: set[int], limit: int) -> dict[int, list[dict]]:
        """First ``limit`` mapped controls (by SCF #) for each framework, in one query."""
        pairs = (
            self.session.query(ControlMapping.framework_id, ControlMapping.control_id)
            .filter(ControlMapping.framework_id.in_(framework_ids))
            .distinct()
            .subquery()
        )
        ranked = (
            self.session.query(
                pairs.c.framework_id,
                pairs.c.control_id,
                func.row_number().over(
                    partition_by=pairs.c.framework_id, order_by=Control.scf_id
                ).label("rn"),
            )
            .join(Control, Control.id == pairs.c.control_id)
            .subquery()
        )
        rows = (
            self.session.query(ranked.c.framework_id, Control)
            .join(Control, Control.id == ranked.c.control_id)
            .options(joinedload(Control.domain))
            .filter(ranked.c.rn <= limit)
            .order_by(ranked.c.framework_id, Control.scf_id)
            .all()
        )
        result: dict[int, list[dict]] = {}
        for fid, c in rows:
            result.setdefault(fid, []).append({
                "scf_id": c.scf_id,
                "title": c.title,
                "description": c.description,
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
            })
        return result

    # ── Reference lists ───────────────────────────────────────────────
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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _apply_with_relaxation(
    pool: set[int],
    matches: dict[str, set[int]],
    *,
    allow_empty_filters: bool,
) -> tuple[set[int], list[str], list[str]]:
    """Intersect ``pool`` with every filter, relaxing filters in RELAX_ORDER until something matches.

    Returns (ids, applied filter names, relaxed filter names). When
    ``allow_empty_filters`` is False, the last remaining filter is never
    dropped, so an empty result is returned instead of the whole pool.
    """
    active = [n for n in RELAX_ORDER if n in matches]
    relaxed: list[str] = []
    while True:
        ids = set(pool)
        for n in active:
            ids &= matches[n]
        if ids or not active:
            return ids, active, relaxed
        if len(active) == 1 and not allow_empty_filters:
            return ids, active, relaxed
        relaxed.append(active.pop(0))
