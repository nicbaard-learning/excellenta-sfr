"""Import Threat Catalog entries from the SCF workbook."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, safe_str
from app.models.threat import Threat

logger = logging.getLogger(__name__)


# Column name patterns to look for in the Threat Catalog sheet
_COL_GROUPING = "Threat Grouping"
_COL_NUMBER = "Threat #"
_COL_TITLE = "Threat"
_COL_DESCRIPTION = "Threat Description"
_COL_MATERIALITY = "Materiality Considerations"


def _find_threat_headers(df: pd.DataFrame) -> dict[str, str]:
    """Identify Threat Catalog column names from the dataframe headers.

    Since pandas parsed the header row, we just inspect df.columns directly.
    """
    col_map: dict[str, str] = {}

    for col in df.columns:
        s = str(col).strip().lower() if col else ""
        if s in ("threat grouping", "threat grouping "):
            col_map[_COL_GROUPING] = col
        elif s in ("threat #", "threat # ", "threat number"):
            col_map[_COL_NUMBER] = col
        elif s in ("threat*", "threat", "threat title"):
            col_map[_COL_TITLE] = col
        elif "threat description" in s:
            col_map[_COL_DESCRIPTION] = col
        elif "materiality" in s:
            col_map[_COL_MATERIALITY] = col

    return col_map


def import_threats(session, wb) -> int:
    """Load threats from the 'Threat Catalog' sheet.

    The sheet contains introductory rows before a structured header.
    We scan to find the actual data rows.
    """
    sheet = find_sheet(wb, "Threat Catalog")
    if sheet is None:
        logger.warning("Threat Catalog sheet not found – skipping")
        return 0

    df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl", header=None)
    logger.info("Threat Catalog sheet: %d rows x %d cols", len(df), len(df.columns))

    # Try to dynamically find the header row by looking for "Threat #"
    header_row_idx = None
    for idx, row in df.iterrows():
        for cell in row:
            if pd.notna(cell) and str(cell).strip().lower() in ("threat #", "threat # "):
                header_row_idx = idx
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        logger.warning("Could not find 'Threat #' header in Threat Catalog – skipping")
        return 0

    # Re-read with the proper header row
    df_data = pd.read_excel(
        wb, sheet_name=sheet.title, engine="openpyxl",
        header=header_row_idx
    )
    # Skip any trailing empty rows
    df_data = df_data.dropna(how="all").reset_index(drop=True)

    col_map = _find_threat_headers(df_data)

    if _COL_NUMBER not in col_map:
        logger.warning("Could not find Threat # column after header detection – skipping")
        return 0

    count = 0
    sheet_name = sheet.title

    for idx, row in df_data.iterrows():
        threat_number = safe_str(row.get(col_map.get(_COL_NUMBER)))
        if not threat_number:
            continue

        threat = Threat(
            threat_number=threat_number,
            threat_grouping=safe_str(row.get(col_map.get(_COL_GROUPING))) if _COL_GROUPING in col_map else None,
            threat_title=safe_str(row.get(col_map.get(_COL_TITLE))) if _COL_TITLE in col_map else None,
            threat_description=safe_str(row.get(col_map.get(_COL_DESCRIPTION))) if _COL_DESCRIPTION in col_map else None,
            materiality_considerations=safe_str(row.get(col_map.get(_COL_MATERIALITY))) if _COL_MATERIALITY in col_map else None,
            source_sheet=sheet_name,
            source_row=int(idx) + header_row_idx + 2,
        )
        session.add(threat)
        count += 1

    session.flush()
    logger.info("Imported %d threats", count)
    return count
