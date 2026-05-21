"""Import SCF domains, principles, and controls from the workbook."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_float, safe_int, safe_str
from app.models.control import Control, Domain, Principle

logger = logging.getLogger(__name__)

# Expected columns in the SCF sheet
COL_DOMAIN = "SCF Domain"
COL_CONTROL = "SCF Control"
COL_SCF_NUM = "SCF #"
COL_DESCRIPTION = "Secure Controls Framework (SCF) Control Description"
COL_CADENCE = "Conformity Validation Cadence"
COL_ERL = "Evidence Request List (ERL) #"
COL_QUESTION = "SCF Control Question"
COL_WEIGHTING = "Relative Control Weighting"
COL_APPLICABILITY = "Applicability/context"


def import_domains(session, wb) -> dict[str, int]:
    """Extract unique SCF Domains from the main sheet."""
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            return {}
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    _rename_columns(df)
    domain_col = _find_column(df, COL_DOMAIN)
    if domain_col is None:
        logger.warning("SCF Domain column not found – skipping domain import")
        return {}

    domain_ids: dict[str, int] = {}
    existing = {d.code: d.id for d in session.query(Domain).all()}

    # Collect unique domains by code prefix
    for _, row in df.iterrows():
        raw = safe_str(row.get(domain_col))
        if not raw:
            continue
        code = _domain_code(raw)
        if code and code not in existing and code not in domain_ids:
            domain = Domain(code=code, name=raw)
            session.add(domain)
            session.flush()
            domain_ids[code] = domain.id

    session.flush()
    domain_ids.update(existing)
    logger.info("Imported %d domains", len(domain_ids))
    return domain_ids


def import_principles(session, wb, domain_ids: dict[str, int]) -> dict[str, int]:
    """Extract SCF Control (principle) entries from the main sheet."""
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            return {}
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    _rename_columns(df)
    principle_ids: dict[str, int] = {}
    existing = {(p.code, p.domain_id): p.id for p in session.query(Principle).all()}

    scf_col = _find_column(df, COL_CONTROL)
    domain_col = _find_column(df, COL_DOMAIN)
    if scf_col is None:
        logger.warning("SCF Control column not found – skipping principle import")
        return {}

    seen = set()
    for _, row in df.iterrows():
        raw = safe_str(row.get(scf_col))
        domain_raw = safe_str(row.get(domain_col)) if domain_col else None
        if not raw:
            continue
        domain_code = _domain_code(domain_raw) if domain_raw else None
        domain_id = domain_ids.get(domain_code) if domain_code else None

        if (raw, domain_id) in seen:
            continue
        seen.add((raw, domain_id))
        if (raw, domain_id) in existing:
            principle_ids[raw] = existing[(raw, domain_id)]
            continue

        principle = Principle(code=raw, name=raw, domain_id=domain_id)
        session.add(principle)
        session.flush()
        principle_ids[raw] = principle.id

    session.flush()
    logger.info("Imported %d principles", len(principle_ids))
    return principle_ids


def import_controls(
    session,
    wb,
    domain_ids: dict[str, int],
    principle_ids: dict[str, int],
) -> int:
    """Import canonical SCF controls from the main sheet."""
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    _rename_columns(df)
    existing = {c.scf_id: c.id for c in session.query(Control).all()}

    scf_num_col = _find_column(df, COL_SCF_NUM)
    domain_col = _find_column(df, COL_DOMAIN)
    scf_control_col = _find_column(df, COL_CONTROL)
    desc_col = _find_column(df, COL_DESCRIPTION)
    cadence_col = _find_column(df, COL_CADENCE)
    erl_col = _find_column(df, COL_ERL)
    question_col = _find_column(df, COL_QUESTION)
    weighting_col = _find_column(df, COL_WEIGHTING)
    applicability_col = _find_column(df, COL_APPLICABILITY)

    if scf_num_col is None:
        logger.warning("SCF # column not found – cannot import controls")
        return 0

    count = 0
    sheet_name = "SCF 2026.1"

    for idx, row in df.iterrows():
        scf_id = safe_str(row.get(scf_num_col))
        if not scf_id or scf_id in existing:
            if scf_id and scf_id in existing:
                count += 1
            continue

        domain_raw = safe_str(row.get(domain_col)) if domain_col else None
        domain_code = _domain_code(domain_raw) if domain_raw else None
        domain_id = domain_ids.get(domain_code)

        control_raw = safe_str(row.get(scf_control_col)) if scf_control_col else None
        principle_id = principle_ids.get(control_raw) if control_raw else None

        control = Control(
            scf_id=scf_id,
            domain_id=domain_id,
            principle_id=principle_id,
            title=safe_str(row.get(scf_control_col)) or scf_id,
            description=safe_str(row.get(desc_col)) if desc_col else None,
            control_question=safe_str(row.get(question_col)) if question_col else None,
            conformity_cadence=safe_str(row.get(cadence_col)) if cadence_col else None,
            relative_weighting=safe_float(row.get(weighting_col)) if weighting_col else None,
            evidence_request_list_refs=safe_str(row.get(erl_col)) if erl_col else None,
            applicability_context=safe_str(row.get(applicability_col)) if applicability_col else None,
            source_sheet=sheet_name,
            source_row=int(idx) + 2,  # +2 for 0-index + header
        )
        session.add(control)
        session.flush()
        existing[scf_id] = control.id
        count += 1

    session.flush()
    logger.info("Imported %d controls", count)
    return count


def _find_column(df: pd.DataFrame, name: str) -> str | None:
    """Find an actual column name in the DataFrame that matches the given name (case-insensitive)."""
    for col in df.columns:
        if str(col).strip().lower() == name.lower():
            return col
    return None


def _rename_columns(df: pd.DataFrame) -> None:
    """Rename common aliased columns to expected names."""
    mapping = {}
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = str(col).strip().lower()
        if s in ("scf domain", "domain", "scf domain "):
            mapping[col] = COL_DOMAIN
        elif s in ("scf control", "control name", "scf control name", "control", "scf control "):
            mapping[col] = COL_CONTROL
        elif s in ("scf #", "scf # ", "scf number", "control #", "control number"):
            mapping[col] = COL_SCF_NUM
        elif s in ("scf control description", "secure controls framework (scf) control description", "description"):
            mapping[col] = COL_DESCRIPTION
    if mapping:
        df.rename(columns=mapping, inplace=True)


def _domain_code(domain_name: str | None) -> str | None:
    """Derive a short domain code from the domain name."""
    if not domain_name:
        return None
    parts = domain_name.strip().split(" – ")
    if len(parts) > 1:
        return parts[0].strip()
    parts = domain_name.strip().split(" - ")
    if len(parts) > 1:
        return parts[0].strip()
    # Use first 2-4 uppercase letters
    words = domain_name.strip().split()
    if len(words) >= 2:
        return "".join(w[0].upper() for w in words if w[0].isalpha())[:6]
    return domain_name.strip()[:6].upper()
