"""Base import utilities – shared helpers for parsing workbook sheets."""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def normalize_headers(df: pd.DataFrame) -> list[str]:
    """Normalize column headers: strip whitespace, collapse internal whitespace, drop nulls."""
    headers: list[str] = []
    for col in df.columns:
        if pd.isna(col):
            headers.append("")
            continue
        cleaned = str(col).strip().replace("\n", " ").replace("\r", "")
        # Collapse multiple spaces
        while "  " in cleaned:
            cleaned = cleaned.replace("  ", " ")
        headers.append(cleaned)
    return headers


def safe_str(val: Any) -> str | None:
    """Return a stripped string or None if the value is empty/missing."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None


def safe_float(val: Any) -> float | None:
    """Return a float or None."""
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: Any) -> int | None:
    """Return an int or None."""
    if pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_bool(val: Any) -> bool | None:
    """Return a bool or None."""
    if pd.isna(val):
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("yes", "true", "1", "y")


def iter_sheet_rows(
    df: pd.DataFrame,
    header_row: int = 0,
) -> Generator[dict[str, Any], None, None]:
    """Yield each row as a dict with normalized keys from the header row."""
    df = df.reset_index(drop=True)
    if header_row != 0:
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
    else:
        df.columns = normalize_headers(df)
    for _, row in df.iterrows():
        yield dict(row)


def find_sheet(wb, name_contains: str) -> Any | None:
    """Find a sheet by substring match on its name."""
    for sheet in wb.worksheets:
        if name_contains.lower() in sheet.title.lower():
            return sheet
    return None


def load_sheet_dataframe(wb, sheet_name: str) -> pd.DataFrame | None:
    """Load a worksheet by exact name into a DataFrame, or None if not found."""
    try:
        return pd.read_excel(wb, sheet_name=sheet_name, engine="openpyxl")
    except ValueError:
        logger.warning("Sheet %r not found in workbook", sheet_name)
        return None
