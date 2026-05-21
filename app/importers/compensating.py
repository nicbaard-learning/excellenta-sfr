"""Import compensating controls from the Compensating Controls sheet."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_str
from app.models.compensating import CompensatingControlLink
from app.models.control import Control

logger = logging.getLogger(__name__)

# Column positions in the Compensating Controls sheet (0-indexed from pandas).
# Known layout:
#   0: SCF Control Name
#   1: SCF Control #               ← primary control SCF ID
#   2: SCF Control Description
#   3: PPTDF Applicability
#   4: Risk if Primary Control Not Implemented
#   5: Possible Compensating Control #1  ← comp 1 SCF ID
#   6: Compensating Control Name         ← comp 1 title
#   7: Compensating Control #            ← comp 1 DESCRIPTION (misleading header)
#   8: Compensating Control Justification
#   9: Possible Compensating Control #2  ← comp 2 SCF ID
#  10: Compensating Control Name         ← comp 2 title
#  11: Compensating Control #            ← comp 2 DESCRIPTION (misleading header)
#  12: Compensating Control Justification


def _find_col_by_pattern(df: pd.DataFrame, patterns: list[str]) -> str | None:
    """Find a column whose normalized header contains any of the given patterns."""
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = " ".join(str(col).strip().lower().split())
        for pat in patterns:
            if pat in s:
                return col
    return None


def _find_compensating_columns(df: pd.DataFrame) -> dict[str, str] | None:
    """Identify key columns in the Compensating Controls sheet.

    Returns a dict with keys:
      primary_ref   – column containing the primary control SCF #
      comp1_id      – column containing compensating control 1 SCF ID
      comp1_name    – column containing compensating control 1 name/title
      comp1_desc    – column containing compensating control 1 description
      comp1_just    – column containing compensating control 1 justification
      comp2_id      – column containing compensating control 2 SCF ID
      comp2_name    – column containing compensating control 2 name/title
      comp2_desc    – column containing compensating control 2 description
      comp2_just    – column containing compensating control 2 justification
    Returns None if the required primary_ref column is not found.
    """
    cols = list(df.columns)
    result: dict[str, str] = {}

    # Primary control SCF #: look for "SCF Control #" or "SCF #"
    primary = _find_col_by_pattern(df, ["scf control #", "scf #"])
    if not primary:
        return None
    result["primary_ref"] = primary

    # Identify columns by pattern: we need to find the first and second occurrences
    # of each key column group
    possible_ids: list[str] = []
    possible_names: list[str] = []
    possible_descs: list[str] = []
    possible_justs: list[str] = []

    for col in cols:
        if col is None or pd.isna(col):
            continue
        s = " ".join(str(col).strip().lower().split())

        # Possible Compensating Control #1 or #2 → comp ID
        if "possible compensating control" in s:
            possible_ids.append(col)
        # Compensating Control Name → title
        elif s == "compensating control name":
            possible_names.append(col)
        # Compensating Control # → description (misleading header!)
        elif s == "compensating control #":
            possible_descs.append(col)
        # Compensating Control Justification
        elif "compensating control justification" in s:
            possible_justs.append(col)

    if len(possible_ids) >= 1:
        result["comp1_id"] = possible_ids[0]
    if len(possible_ids) >= 2:
        result["comp2_id"] = possible_ids[1]
    if len(possible_names) >= 1:
        result["comp1_name"] = possible_names[0]
    if len(possible_names) >= 2:
        result["comp2_name"] = possible_names[1]
    if len(possible_descs) >= 1:
        result["comp1_desc"] = possible_descs[0]
    if len(possible_descs) >= 2:
        result["comp2_desc"] = possible_descs[1]
    if len(possible_justs) >= 1:
        result["comp1_just"] = possible_justs[0]
    if len(possible_justs) >= 2:
        result["comp2_just"] = possible_justs[1]

    return result


def import_compensating_controls(session, wb) -> int:
    """Load compensating controls from the 'Compensating Controls 2026.1' sheet.

    Each row in the sheet can have up to two compensating controls, stored in
    two sets of columns (#1 and #2).  We create one CompensatingControlLink
    per non-N/A compensating control entry.
    """
    df = load_sheet_dataframe(wb, "Compensating Controls 2026.1")
    if df is None:
        sheet = find_sheet(wb, "Compensating Controls")
        if sheet is None:
            logger.warning("Compensating Controls sheet not found – skipping")
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    if not control_map:
        logger.warning("No controls loaded – cannot create compensating control links")
        return 0

    col_map = _find_compensating_columns(df)
    if not col_map or "primary_ref" not in col_map:
        logger.warning("Could not identify primary control reference column – skipping")
        return 0

    # Build existing keys for idempotency: (control_id, compensating_control_id)
    existing_links: set[tuple[int, str]] = set()
    for link in session.query(CompensatingControlLink).all():
        if link.control_id and link.compensating_control_id:
            existing_links.add((link.control_id, link.compensating_control_id))

    count = 0
    skipped_primary_unmatched = 0
    skipped_no_comp = 0
    skipped_duplicate = 0
    sheet_name = getattr(df, "sheet_name", "Compensating Controls")

    for idx, row in df.iterrows():
        primary_scf_id = safe_str(row.get(col_map["primary_ref"]))
        if not primary_scf_id or primary_scf_id not in control_map:
            skipped_primary_unmatched += 1
            continue

        control_id = control_map[primary_scf_id]

        # Process up to two compensating controls per row
        comp_sections = [
            {
                "scf_id": col_map.get("comp1_id"),
                "title": col_map.get("comp1_name"),
                "description": col_map.get("comp1_desc"),
                "justification": col_map.get("comp1_just"),
            },
            {
                "scf_id": col_map.get("comp2_id"),
                "title": col_map.get("comp2_name"),
                "description": col_map.get("comp2_desc"),
                "justification": col_map.get("comp2_just"),
            },
        ]

        for section in comp_sections:
            comp_scf_id = safe_str(row.get(section["scf_id"])) if section["scf_id"] else None
            # Skip N/A entries (common in the workbook)
            if not comp_scf_id or comp_scf_id.upper() in ("N/A", "NA", "NONE", ""):
                skipped_no_comp += 1
                continue

            comp_title = safe_str(row.get(section["title"])) if section["title"] else None
            comp_desc = safe_str(row.get(section["description"])) if section["description"] else None
            comp_just = safe_str(row.get(section["justification"])) if section["justification"] else None

            # Skip duplicate (control_id, compensating_control_id) pair
            key = (control_id, comp_scf_id)
            if key in existing_links:
                skipped_duplicate += 1
                continue

            link = CompensatingControlLink(
                control_id=control_id,
                compensating_control_id=comp_scf_id,
                compensating_control_title=comp_title,
                compensating_control_description=comp_desc,
                justification=comp_just,
                source_sheet=sheet_name,
                source_row=int(idx) + 2,
            )
            session.add(link)
            existing_links.add(key)
            count += 1

    session.flush()
    if skipped_primary_unmatched:
        logger.info(
            "  Compensating rows with unmatched primary control SCF ID: %d",
            skipped_primary_unmatched,
        )
    if skipped_no_comp:
        logger.info(
            "  Compensating rows with N/A compensating control entries: %d",
            skipped_no_comp,
        )
    if skipped_duplicate:
        logger.info(
            "  Compensating duplicate links skipped (idempotent): %d",
            skipped_duplicate,
        )
    logger.info("Imported %d compensating control links", count)
    return count
