"""Import SCF domains, principles, and controls from the workbook."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_float, safe_int, safe_str
from app.models.control import Control, Domain, Principle

logger = logging.getLogger(__name__)

_RE_SPECIAL = re.compile(r"[.*+?\[\](){}^$|\\]")

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
COL_PPTDF = "PPTDF Applicability"
COL_REL_WEIGHT = "Relative Weight"

# Firm-size solution columns (from "Possible Solutions & Considerations" for each size)
COL_FIRM_MICRO_SMALL = "Possible Solutions & Considerations - Micro-Small"
COL_FIRM_SMALL = "Possible Solutions & Considerations - Small"
COL_FIRM_MEDIUM = "Possible Solutions & Considerations - Medium"
COL_FIRM_LARGE = "Possible Solutions & Considerations - Large"
COL_FIRM_ENTERPRISE = "Possible Solutions & Considerations - Enterprise"

# SCR-CMM Maturity level columns
COL_CMM_L0 = "SCR-CMM Level 0"
COL_CMM_L1 = "SCR-CMM Level 1"
COL_CMM_L2 = "SCR-CMM Level 2"
COL_CMM_L3 = "SCR-CMM Level 3"
COL_CMM_L4 = "SCR-CMM Level 4"
COL_CMM_L5 = "SCR-CMM Level 5"


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


def _find_flex_column(df: pd.DataFrame, *candidates: str) -> str | None:
    """Find a column by trying multiple candidate strings (case-insensitive).

    Candidates containing regex special characters (``.*+?[](){}^$|\\``)
    are treated as regex patterns; others use plain substring match.
    """
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = " ".join(str(col).strip().lower().split())
        for candidate in candidates:
            if _re_special.search(candidate):
                if re.search(candidate.lower(), s):
                    return col
            elif candidate.lower() in s:
                return col
    return None


def import_controls(
    session,
    wb,
    domain_ids: dict[str, int],
    principle_ids: dict[str, int],
) -> int:
    """Import canonical SCF controls from the main sheet.

    Now imports:
    - Firm-size solutions columns (Micro-Small, Small, Medium, Large, Enterprise)
    - SCR-CMM Maturity levels (Level 0 through Level 5)
    - PPTDF Applicability and Relative Weight
    """
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    _rename_columns(df)
    # Pre-load ALL existing controls into a dict keyed by scf_id for fast in-memory updates
    existing_ctrls: dict[str, Control] = {c.scf_id: c for c in session.query(Control).all()}
    existing_ids: dict[str, int] = {scf_id: c.id for scf_id, c in existing_ctrls.items()}

    scf_num_col = _find_column(df, COL_SCF_NUM)
    domain_col = _find_column(df, COL_DOMAIN)
    scf_control_col = _find_column(df, COL_CONTROL)
    desc_col = _find_column(df, COL_DESCRIPTION)
    cadence_col = _find_column(df, COL_CADENCE)
    erl_col = _find_column(df, COL_ERL)
    question_col = _find_column(df, COL_QUESTION)
    weighting_col = _find_column(df, COL_WEIGHTING)
    applicability_col = _find_column(df, COL_APPLICABILITY)

    # New columns - flex matching for Possible Solutions & Considerations columns
    pptdf_col = _find_flex_column(df, COL_PPTDF, "pptdf")
    rel_weight_col = _find_flex_column(df, COL_REL_WEIGHT, "relative weight")

    # Firm-size columns: match on "Possible Solutions & Considerations" with size keyword
    firm_micro_col = _find_flex_column(df, COL_FIRM_MICRO_SMALL, "micro-small", "micro small", "solutions.*micro")
    firm_small_col = _find_flex_column(df, COL_FIRM_SMALL, "solutions.*small", " small business")
    firm_medium_col = _find_flex_column(df, COL_FIRM_MEDIUM, "solutions.*medium", "medium business")
    firm_large_col = _find_flex_column(df, COL_FIRM_LARGE, "solutions.*large", "large business")
    firm_enterprise_col = _find_flex_column(df, COL_FIRM_ENTERPRISE, "solutions.*enterprise", "enterprise (>")

    # Position-based fallback: if micro was found but some other size columns are missing,
    # assume they're in adjacent columns (cols 6-10 in the workbook)
    if firm_micro_col is not None and (firm_small_col is None or firm_medium_col is None or firm_large_col is None or firm_enterprise_col is None):
        cols_list = list(df.columns)
        if firm_micro_col in cols_list:
            micro_idx = cols_list.index(firm_micro_col)
            for offset, attr_name in [(1, "solutions_small"), (2, "solutions_medium"), (3, "solutions_large"), (4, "solutions_enterprise")]:
                idx = micro_idx + offset
                if idx < len(cols_list):
                    col_at = cols_list[idx]
                    if col_at is not None and not pd.isna(col_at):
                        s_at = " ".join(str(col_at).strip().lower().split())
                        if "solutions" in s_at or "business" in s_at or "staff" in s_at:
                            if offset == 1 and firm_small_col is None:
                                firm_small_col = col_at
                            elif offset == 2 and firm_medium_col is None:
                                firm_medium_col = col_at
                            elif offset == 3 and firm_large_col is None:
                                firm_large_col = col_at
                            elif offset == 4 and firm_enterprise_col is None:
                                firm_enterprise_col = col_at

    # Maturity columns
    cmm_l0_col = _find_flex_column(df, COL_CMM_L0, "cmm level 0", "scr-cmm.*0")
    cmm_l1_col = _find_flex_column(df, COL_CMM_L1, "cmm level 1", "scr-cmm.*1")
    cmm_l2_col = _find_flex_column(df, COL_CMM_L2, "cmm level 2", "scr-cmm.*2")
    cmm_l3_col = _find_flex_column(df, COL_CMM_L3, "cmm level 3", "scr-cmm.*3")
    cmm_l4_col = _find_flex_column(df, COL_CMM_L4, "cmm level 4", "scr-cmm.*4")
    cmm_l5_col = _find_flex_column(df, COL_CMM_L5, "cmm level 5", "scr-cmm.*5")

    if scf_num_col is None:
        logger.warning("SCF # column not found – cannot import controls")
        return 0

    count = 0
    update_count = 0
    sheet_name = "SCF 2026.1"

    for idx, row in df.iterrows():
        scf_id = safe_str(row.get(scf_num_col))
        if not scf_id:
            continue

        domain_raw = safe_str(row.get(domain_col)) if domain_col else None
        domain_code = _domain_code(domain_raw) if domain_raw else None
        domain_id = domain_ids.get(domain_code)
        control_raw = safe_str(row.get(scf_control_col)) if scf_control_col else None
        principle_id = principle_ids.get(control_raw) if control_raw else None

        if scf_id in existing_ctrls:
            # Update existing control in-memory (no extra DB query needed)
            ctrl = existing_ctrls[scf_id]
            ctrl.relative_weight = safe_int(row.get(rel_weight_col)) if rel_weight_col else ctrl.relative_weight
            ctrl.pptdf_applicability = safe_str(row.get(pptdf_col)) if pptdf_col else ctrl.pptdf_applicability
            if firm_micro_col:
                ctrl.solutions_micro_small = safe_str(row.get(firm_micro_col))
            if firm_small_col:
                ctrl.solutions_small = safe_str(row.get(firm_small_col))
            if firm_medium_col:
                ctrl.solutions_medium = safe_str(row.get(firm_medium_col))
            if firm_large_col:
                ctrl.solutions_large = safe_str(row.get(firm_large_col))
            if firm_enterprise_col:
                ctrl.solutions_enterprise = safe_str(row.get(firm_enterprise_col))
            if cmm_l0_col:
                ctrl.cmm_level_0 = safe_str(row.get(cmm_l0_col))
            if cmm_l1_col:
                ctrl.cmm_level_1 = safe_str(row.get(cmm_l1_col))
            if cmm_l2_col:
                ctrl.cmm_level_2 = safe_str(row.get(cmm_l2_col))
            if cmm_l3_col:
                ctrl.cmm_level_3 = safe_str(row.get(cmm_l3_col))
            if cmm_l4_col:
                ctrl.cmm_level_4 = safe_str(row.get(cmm_l4_col))
            if cmm_l5_col:
                ctrl.cmm_level_5 = safe_str(row.get(cmm_l5_col))
            update_count += 1
            count += 1
            continue

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
            # New fields
            relative_weight=safe_int(row.get(rel_weight_col)) if rel_weight_col else None,
            pptdf_applicability=safe_str(row.get(pptdf_col)) if pptdf_col else None,
            # Firm-size solutions
            solutions_micro_small=safe_str(row.get(firm_micro_col)) if firm_micro_col else None,
            solutions_small=safe_str(row.get(firm_small_col)) if firm_small_col else None,
            solutions_medium=safe_str(row.get(firm_medium_col)) if firm_medium_col else None,
            solutions_large=safe_str(row.get(firm_large_col)) if firm_large_col else None,
            solutions_enterprise=safe_str(row.get(firm_enterprise_col)) if firm_enterprise_col else None,
            # SCR-CMM Maturity levels
            cmm_level_0=safe_str(row.get(cmm_l0_col)) if cmm_l0_col else None,
            cmm_level_1=safe_str(row.get(cmm_l1_col)) if cmm_l1_col else None,
            cmm_level_2=safe_str(row.get(cmm_l2_col)) if cmm_l2_col else None,
            cmm_level_3=safe_str(row.get(cmm_l3_col)) if cmm_l3_col else None,
            cmm_level_4=safe_str(row.get(cmm_l4_col)) if cmm_l4_col else None,
            cmm_level_5=safe_str(row.get(cmm_l5_col)) if cmm_l5_col else None,
            source_sheet=sheet_name,
            source_row=int(idx) + 2,  # +2 for 0-index + header
        )
        session.add(control)
        session.flush()
        existing[scf_id] = control.id
        count += 1

    session.flush()
    logger.info("Imported %d controls (%d new, %d updated)", count, count - update_count, update_count)
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
