"""Import Risk Catalog entries from the SCF workbook."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, safe_str
from app.models.risk import Risk

logger = logging.getLogger(__name__)


# Column name patterns for the Risk Catalog sheet
_COL_GROUPING = "Risk Grouping"
_COL_NUMBER = "Risk #"
_COL_TITLE = "Risk"
_COL_DESCRIPTION = "Description of Possible Risk Due To Control Deficiency"
_COL_NIST_CSF = "NIST CSF Function"
_COL_MATERIALITY = "Materiality Considerations"


def _find_risk_headers(df: pd.DataFrame) -> dict[str, str]:
    """Identify Risk Catalog column names from the dataframe headers.

    Since pandas parsed the header row, we just inspect df.columns directly.
    """
    col_map: dict[str, str] = {}

    for col in df.columns:
        s = str(col).strip().lower() if col else ""
        if s in ("risk grouping", "risk grouping "):
            col_map[_COL_GROUPING] = col
        elif s in ("risk #", "risk # ", "risk number"):
            col_map[_COL_NUMBER] = col
        elif s in ("risk*", "risk", "risk title"):
            col_map[_COL_TITLE] = col
        elif "description of possible risk" in s or "control deficiency" in s:
            col_map[_COL_DESCRIPTION] = col
        elif "nist csf" in s or "csf function" in s:
            col_map[_COL_NIST_CSF] = col
        elif "materiality" in s:
            col_map[_COL_MATERIALITY] = col

    return col_map


def import_risks(session, wb) -> int:
    """Load risks from the 'Risk Catalog' sheet.

    The sheet contains introductory rows before a structured header.
    We scan to find the actual data rows.
    """
    sheet = find_sheet(wb, "Risk Catalog")
    if sheet is None:
        logger.warning("Risk Catalog sheet not found – skipping")
        return 0

    df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl", header=None)
    logger.info("Risk Catalog sheet: %d rows x %d cols", len(df), len(df.columns))

    # Find the header row by looking for "Risk #"
    header_row_idx = None
    for idx, row in df.iterrows():
        for cell in row:
            if pd.notna(cell) and str(cell).strip().lower() in ("risk #", "risk # "):
                header_row_idx = idx
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        logger.warning("Could not find 'Risk #' header in Risk Catalog – skipping")
        return 0

    # Re-read with the proper header row
    df_data = pd.read_excel(
        wb, sheet_name=sheet.title, engine="openpyxl",
        header=header_row_idx
    )
    df_data = df_data.dropna(how="all").reset_index(drop=True)

    col_map = _find_risk_headers(df_data)

    if _COL_NUMBER not in col_map:
        logger.warning("Could not find Risk # column after header detection – skipping")
        return 0

    count = 0
    sheet_name = sheet.title

    for idx, row in df_data.iterrows():
        risk_number = safe_str(row.get(col_map.get(_COL_NUMBER)))
        if not risk_number:
            continue

        risk = Risk(
            risk_number=risk_number,
            risk_grouping=safe_str(row.get(col_map.get(_COL_GROUPING))) if _COL_GROUPING in col_map else None,
            risk_title=safe_str(row.get(col_map.get(_COL_TITLE))) if _COL_TITLE in col_map else None,
            risk_description=safe_str(row.get(col_map.get(_COL_DESCRIPTION))) if _COL_DESCRIPTION in col_map else None,
            nist_csf_function=safe_str(row.get(col_map.get(_COL_NIST_CSF))) if _COL_NIST_CSF in col_map else None,
            materiality_considerations=safe_str(row.get(col_map.get(_COL_MATERIALITY))) if _COL_MATERIALITY in col_map else None,
            source_sheet=sheet_name,
            source_row=int(idx) + header_row_idx + 2,
        )
        session.add(risk)
        count += 1

    session.flush()
    logger.info("Imported %d risks", count)
    return count
