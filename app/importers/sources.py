"""Import authoritative sources from the Authoritative Sources sheet."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_str
from app.models.control import Control
from app.models.mapping import AuthoritativeSource

logger = logging.getLogger(__name__)


def import_authoritative_sources(session, wb) -> int:
    """Load authoritative sources from the 'Authoritative Sources' sheet."""
    df = load_sheet_dataframe(wb, "Authoritative Sources")
    if df is None:
        sheet = find_sheet(wb, "Authoritative Sources")
        if sheet is None:
            logger.warning("Authoritative Sources sheet not found – skipping")
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    col_map = _map_columns(df)

    count = 0
    sheet_name = getattr(df, "sheet_name", "Authoritative Sources")

    # Track authoritative sources to avoid duplicates (source_title per control)
    existing_titles: set[tuple[int | None, str]] = set()
    for a in session.query(AuthoritativeSource).all():
        existing_titles.add((a.control_id, a.source_title))

    for idx, row in df.iterrows():
        control_ref = safe_str(row.get(col_map.get("control_ref"))) if col_map.get("control_ref") else None
        control_id = control_map.get(control_ref) if control_ref else None
        source_title = safe_str(row.get(col_map.get("title"))) or _find_any_title(row)

        # Skip duplicates
        if source_title and (control_id, source_title) in existing_titles:
            continue

        source = AuthoritativeSource(
            control_id=control_id,
            source_title=source_title,
            source_url=safe_str(row.get(col_map.get("url"))) if col_map.get("url") else None,
            source_organization=safe_str(row.get(col_map.get("organization")))
            if col_map.get("organization")
            else None,
            reference_number=safe_str(row.get(col_map.get("reference"))) if col_map.get("reference") else None,
            # New fields: FDI, STRM URL, Geography
            focal_document_identifier=safe_str(row.get(col_map.get("fdi"))) if col_map.get("fdi") else None,
            strm_url=safe_str(row.get(col_map.get("strm_url"))) if col_map.get("strm_url") else None,
            geography=safe_str(row.get(col_map.get("geography"))) if col_map.get("geography") else None,
            source_sheet=sheet_name,
        )
        session.add(source)
        count += 1
        if source_title:
            existing_titles.add((control_id, source_title))

    session.flush()
    logger.info("Imported %d authoritative sources", count)
    return count


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map column headers to standardized keys."""
    col_map: dict[str, str] = {}
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = str(col).strip().lower()
        if any(x in s for x in ("control #", "scf #", "control ref", "scf number", "scf_id")):
            col_map["control_ref"] = col
        elif any(x in s for x in ("source title", "title", "source name", "document", "document title")):
            col_map["title"] = col
        elif any(x in s for x in ("source url", "url", "link", "web", "source link")):
            col_map["url"] = col
        elif any(x in s for x in ("source organization", "organization", "org", "publisher", "authority")):
            col_map["organization"] = col
        elif any(x in s for x in ("reference #", "reference number", "ref #", "ref", "document #")):
            col_map["reference"] = col
        elif any(x in s for x in ("geography", "country", "region")):
            col_map["geography"] = col
        elif any(x in s for x in ("focal document identifier", "fdi", "focal document id")):
            col_map["fdi"] = col
        elif any(x in s for x in ("set theory relationship mapping", "strm url", "strm pdf")):
            col_map["strm_url"] = col
        elif any(x in s for x in ("scf column header", "scf column")):
            col_map["scf_column"] = col
        elif any(x in s for x in ("focal document source", "focal doc source", "fds")):
            col_map["focal_doc_source"] = col
    return col_map


def _find_any_title(row) -> str | None:
    """Find the first non-null string column as a fallback title."""
    for val in row:
        if val and not pd.isna(val) and isinstance(val, str) and len(val) > 5:
            return val
    return "Unknown source"
