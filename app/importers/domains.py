"""Import SCF domains and principles from the 'SCF Domains & Principles' sheet."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_str
from app.models.control import Domain, Principle

logger = logging.getLogger(__name__)


def import_domains_and_principles(session, wb) -> tuple[int, int]:
    """Load domains and their principles from the 'SCF Domains & Principles' sheet.

    Returns (domain_count, principle_count).
    """
    df = load_sheet_dataframe(wb, "SCF Domains & Principles")
    if df is None:
        sheet = find_sheet(wb, "Domains & Principles")
        if sheet is None:
            logger.warning("SCF Domains & Principles sheet not found – skipping")
            return 0, 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    col_map = _map_columns(df)
    domain_col = col_map.get("domain_code") or col_map.get("domain_name")
    principle_col = col_map.get("principle_code") or col_map.get("principle_name")

    if not domain_col:
        logger.warning("Could not identify domain column – skipping")
        return 0, 0

    existing_domains = {d.code: d.id for d in session.query(Domain).all()}
    existing_principles = {(p.code, p.domain_id): p.id for p in session.query(Principle).all()}

    domain_count = 0
    principle_count = 0
    current_domain_id: int | None = None
    current_domain_code: str | None = None

    for idx, row in df.iterrows():
        domain_val = safe_str(row.get(domain_col))
        principle_val = safe_str(row.get(principle_col)) if principle_col else None
        principle_desc = safe_str(row.get(col_map.get("principle_description"))) if col_map.get("principle_description") else None

        if domain_val and domain_val not in existing_domains and domain_val != current_domain_code:
            domain = Domain(code=domain_val, name=domain_val)
            session.add(domain)
            session.flush()
            existing_domains[domain_val] = domain.id
            current_domain_id = domain.id
            current_domain_code = domain_val
            domain_count += 1
        elif domain_val and domain_val in existing_domains:
            current_domain_id = existing_domains[domain_val]
            current_domain_code = domain_val
        elif domain_val is None and current_domain_id is None:
            continue

        if principle_val and current_domain_id:
            key = (principle_val, current_domain_id)
            if key not in existing_principles:
                principle = Principle(
                    domain_id=current_domain_id,
                    code=principle_val,
                    name=principle_val,
                    description=principle_desc,
                )
                session.add(principle)
                session.flush()
                existing_principles[key] = principle.id
                principle_count += 1

    session.flush()
    logger.info("Imported %d domains and %d principles from Domains & Principles sheet", domain_count, principle_count)
    return domain_count, principle_count


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map column headers to standardized keys."""
    col_map: dict[str, str] = {}
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = str(col).strip().lower()

        if s in {"domain code", "domain #", "domain id", "scf domain"}:
            col_map["domain_code"] = col
        elif s in {"domain name", "domain title", "domain name "}:
            col_map["domain_name"] = col
        elif s in {"principle code", "principle #", "principle id", "scf principle"}:
            col_map["principle_code"] = col
        elif s in {"principle name", "principle title"}:
            col_map["principle_name"] = col
        elif s in {"principle description", "principle desc", "description"}:
            col_map["principle_description"] = col

    return col_map
