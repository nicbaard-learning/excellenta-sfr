"""One-time backfill: populate firm-size, maturity, relative_weight, PPTDF columns
on existing controls from the workbook.

Usage: python -m app.importers.fix_columns
"""

import logging
import re

import pandas as pd

from app.database import SessionLocal
from app.importers.base import safe_str
from app.models.control import Control

logger = logging.getLogger(__name__)

FIRM_ATTRS = [
    "solutions_micro_small",
    "solutions_small",
    "solutions_medium",
    "solutions_large",
    "solutions_enterprise",
]

CMM_ATTRS = [
    "cmm_level_0", "cmm_level_1", "cmm_level_2",
    "cmm_level_3", "cmm_level_4", "cmm_level_5",
]


def _find_col_idx(headers: list[str], patterns: list[str]) -> int | None:
    """Find the first column whose normalized name matches one of the regex patterns."""
    for i, h in enumerate(headers):
        if not h:
            continue
        s = " ".join(str(h).strip().lower().split())
        for pat in patterns:
            if re.search(pat, s):
                return i
    return None


def backfill_missing_columns():
    wb_path = "secure-controls-framework-scf-2026-1.xlsx"

    # Read directly with pandas — avoids openpyxl non-read_only memory issues
    logger.info("Reading workbook: %s", wb_path)
    df = pd.read_excel(wb_path, sheet_name="SCF 2026.1", engine="openpyxl")
    headers_norm = [" ".join(str(c).strip().lower().split()) if not pd.isna(c) else "" for c in df.columns]
    logger.info("Read %d rows x %d columns", len(df), len(headers_norm))

    # Locate SCF # column
    scf_col = _find_col_idx(headers_norm, [r"scf #"])
    if scf_col is None:
        logger.error("SCF # column not found!")
        return
    logger.info("SCF # column at index %d", scf_col)

    # Locate firm-size columns — individual regex patterns
    firm_patterns = [
        r"micro.small",    # micro-small
        r"(?<!micro)\bsmall\b.*\bstaff\b",  # small (but NOT micro)
        r"\bmedium\b.*\bstaff\b",
        r"\blarge\b.*\bstaff\b",
        r"\benterprise\b.*\bstaff\b",
    ]

    firm_cols: dict[str, int] = {}
    for attr, pat in zip(FIRM_ATTRS, firm_patterns):
        idx = _find_col_idx(headers_norm, [pat])
        if idx is not None:
            firm_cols[attr] = idx

    # Positional fallback for any missed firm-size columns
    if "solutions_micro_small" in firm_cols:
        micro_idx = firm_cols["solutions_micro_small"]
        for offset, attr in enumerate(FIRM_ATTRS[1:], 1):
            if attr not in firm_cols and micro_idx + offset < len(headers_norm):
                h = headers_norm[micro_idx + offset]
                if h and any(kw in h for kw in ["solutions", "business", "staff"]):
                    firm_cols[attr] = micro_idx + offset

    # Locate CMM maturity columns
    cmm_cols: dict[str, int] = {}
    for attr in CMM_ATTRS:
        level = attr.split("_")[-1]
        pat = rf"scr.cmm.*level\s*{level}(?!\d)"
        idx = _find_col_idx(headers_norm, [pat, attr.replace("_", " ")])
        if idx is not None:
            cmm_cols[attr] = idx

    # Locate other columns
    rel_weight_idx = _find_col_idx(headers_norm, [r"relative.*weight", r"weighting"])
    pptdf_idx = _find_col_idx(headers_norm, [r"pptdf"])

    logger.info("Firm columns: %s", firm_cols)
    logger.info("CMM columns: %s", cmm_cols)
    logger.info("Relative weight col: %s, PPTDF col: %s", rel_weight_idx, pptdf_idx)

    if not firm_cols and not cmm_cols and rel_weight_idx is None and pptdf_idx is None:
        logger.warning("No target columns found — nothing to backfill")
        return

    # Load all controls into dict
    session = SessionLocal()
    try:
        controls: dict[str, Control] = {c.scf_id: c for c in session.query(Control).all()}
        logger.info("Loaded %d controls from DB", len(controls))
        update_count = 0
        batch_size = 200

        for idx, row in df.iterrows():
            scf_id = safe_str(row.iat[scf_col])
            if not scf_id or scf_id not in controls:
                continue

            ctrl = controls[scf_id]
            dirty = False

            for attr, col_idx in firm_cols.items():
                val = safe_str(row.iat[col_idx])
                if val and getattr(ctrl, attr) is None:
                    setattr(ctrl, attr, val)
                    dirty = True

            for attr, col_idx in cmm_cols.items():
                val = safe_str(row.iat[col_idx])
                if val and getattr(ctrl, attr) is None:
                    setattr(ctrl, attr, val)
                    dirty = True

            if rel_weight_idx is not None:
                val = row.iat[rel_weight_idx]
                if val is not None and not pd.isna(val):
                    try:
                        int_val = int(float(val))
                        if ctrl.relative_weight is None:
                            ctrl.relative_weight = int_val
                            dirty = True
                    except (ValueError, TypeError):
                        pass

            if pptdf_idx is not None:
                val = safe_str(row.iat[pptdf_idx])
                if val and ctrl.pptdf_applicability is None:
                    ctrl.pptdf_applicability = val
                    dirty = True

            if dirty:
                update_count += 1
                if update_count % batch_size == 0:
                    session.flush()

        session.commit()
        logger.info("Backfill complete: %d controls updated", update_count)
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    backfill_missing_columns()
