"""Import assessment objectives from the Assessment Objectives sheet."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_str
from app.models.assessment import AssessmentObjective
from app.models.control import Control

logger = logging.getLogger(__name__)


def import_assessment_objectives(session, wb) -> int:
    """Load assessment objectives from the 'Assessment Objectives 2026.1' sheet."""
    df = load_sheet_dataframe(wb, "Assessment Objectives 2026.1")
    if df is None:
        sheet = find_sheet(wb, "Assessment Objectives")
        if sheet is None:
            logger.warning("Assessment Objectives sheet not found – skipping")
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    col_map = _map_columns(df)

    count = 0
    sheet_name = getattr(df, "sheet_name", "Assessment Objectives")

    for idx, row in df.iterrows():
        control_ref = safe_str(row.get(col_map.get("control_ref"))) if col_map.get("control_ref") else None
        control_id = control_map.get(control_ref) if control_ref else None
        if not control_id:
            continue

        objective_code = safe_str(row.get(col_map.get("code"))) if col_map.get("code") else None
        objective_text = safe_str(row.get(col_map.get("text"))) if col_map.get("text") else safe_str(_fallback_text(row))

        if not objective_text:
            continue

        objective = AssessmentObjective(
            control_id=control_id,
            objective_code=objective_code,
            objective_text=objective_text,
            source_sheet=sheet_name,
            source_row=int(idx) + 2,
        )
        session.add(objective)
        count += 1

    session.flush()
    logger.info("Imported %d assessment objectives", count)
    return count


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map column headers to standardized keys.

    The Assessment Objectives 2026.1 sheet has these relevant columns:
        'SCF #'                                      -> control_ref
        'SCF AO #'                                   -> code
        'SCF Assessment Objective (AO)\n...'          -> text  (the real objective)
        'SCF Assessment Objective (AO) Origin(s)'    -> SKIP  (metadata, not actual text)
    """
    col_map: dict[str, str] = {}
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = str(col).strip().lower()
        if any(x in s for x in ("control #", "scf #", "control ref", "scf number", "scf_id")):
            col_map["control_ref"] = col
        elif any(x in s for x in ("objective #", "objective code", "obj #", "obj code",
                                   "reference", "ao #", "ao number")):
            col_map["code"] = col
        elif any(x in s for x in ("objective", "assessment objective", "objective text", "description")):
            # Skip columns that contain 'origin' – they're metadata, not the actual text
            if "origin" not in s:
                col_map["text"] = col
    return col_map


def _fallback_text(row) -> str | None:
    """Fallback: use any non-null string column as the objective text."""
    for val in row:
        if val and not pd.isna(val) and isinstance(val, str) and len(val) > 10:
            return val
    return None
