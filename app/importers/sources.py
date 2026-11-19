"""Import the framework source list ("Focal Documents (FD)" / "Authoritative Sources")."""

from __future__ import annotations

import logging

from app.importers.base import safe_str
from app.importers.workbook import norm_header, sources_sheet_name
from app.models.mapping import AuthoritativeSource

logger = logging.getLogger(__name__)

# AuthoritativeSource field -> normalised header prefix
_COLUMNS = {
    "geography": "geography",
    "focal_document_identifier": "focal document identifier",
    "source_organization": "source",
    "source_title": "focal document name",
    "source_url": "focal document source",
    "strm_url": "set theory relationship mapping",
}
_MAX_LEN = {"source_url": 500, "source_organization": 255}


def import_authoritative_sources(session, wb) -> int:
    """Make the authoritative_sources table match the workbook, one row per FDI."""
    sheet = sources_sheet_name(wb)
    rows = wb[sheet].iter_rows(values_only=True)
    norm = [norm_header(h) for h in next(rows)]
    cols: dict[str, int] = {}
    for field, prefix in _COLUMNS.items():
        for i, s in enumerate(norm):
            if s == prefix or (prefix != "source" and s.startswith(prefix)):
                cols[field] = i
                break
    if "focal_document_identifier" not in cols:
        raise ValueError(f"{sheet!r} lacks the Focal Document Identifier column")

    existing: dict[str, AuthoritativeSource] = {}
    for src in session.query(AuthoritativeSource).all():
        if src.focal_document_identifier and src.focal_document_identifier not in existing:
            existing[src.focal_document_identifier] = src
        else:
            session.delete(src)  # rows without an FDI or duplicates from older imports

    seen: set[str] = set()
    for row in rows:
        values = {f: safe_str(row[i]) if i < len(row) else None for f, i in cols.items()}
        fdi = values.get("focal_document_identifier")
        if not fdi or fdi in seen:
            continue
        seen.add(fdi)
        src = existing.get(fdi)
        if src is None:
            src = AuthoritativeSource(focal_document_identifier=fdi, source_title=values.get("source_title") or fdi)
            session.add(src)
        for field, value in values.items():
            setattr(src, field, value[:_MAX_LEN[field]] if value and field in _MAX_LEN else value)
        src.source_title = (values.get("source_title") or fdi)[:500]
        src.source_sheet = sheet

    for fdi, src in existing.items():
        if fdi not in seen:
            session.delete(src)

    session.flush()
    logger.info("Synced %d authoritative sources", len(seen))
    return len(seen)
