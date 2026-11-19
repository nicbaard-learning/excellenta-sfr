"""Framework catalogue derived from the SCF workbook.

The SCF workbook describes every mapped framework twice:

* the main ``SCF <version>`` sheet has one mapping column per framework, and
* the framework sources sheet ("Focal Documents (FD)" from 2026.3,
  "Authoritative Sources" before) has one row per mapping column (in the
  same order), giving its Focal Document Identifier (FDI), name,
  source/publisher, URL and geography.

This module pairs the two so that each workbook column becomes exactly one
framework, with its metadata and jurisdiction taken from the workbook rather
than guessed from the framework code.

Usage (re-sync an existing database with the workbook):
    python -m app.importers.catalogue --file secure-controls-framework-scf-2026-3.xlsx
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.importers.framework_codes import pinned_code
from app.importers.workbook import norm_header, scf_sheet_name, sources_sheet_name
from app.models.framework import Framework
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)

# Workbook "Source" values (for non-US geographies) that differ from the
# seeded jurisdiction names.
_SOURCE_TO_JURISDICTION: dict[str, str] = {
    "EU": "EU",
    "UAE": "AE",
}

# Sources-sheet columns, by normalised header prefix.
_SOURCE_COLUMNS = {
    "geography": "geography",
    "scf column header": "header",
    "focal document identifier": "fdi",
    "source": "source",
    "focal document name": "name",
    "focal document title": "title",
    "focal document source": "url",
}


@dataclass
class CatalogueEntry:
    """One framework mapping column of the SCF sheet plus its source metadata."""

    column_index: int
    header: str            # exact SCF sheet header (used as ControlMapping.source_column)
    fdi: str | None        # Focal Document Identifier
    source: str | None     # e.g. "NIST", "PCI SSC", "Federal", "South Africa"
    name: str | None       # Focal Document Name
    title: str | None      # Focal Document Title (not in 2026.3 workbooks)
    url: str | None        # Focal Document Source
    geography: str | None  # General, US, EMEA, APAC, Americas
    code: str = ""

    @property
    def jurisdiction_key(self) -> str | None:
        """The jurisdiction code or name this framework applies to, or None if global."""
        geo = (self.geography or "").strip()
        if not geo or geo.lower() == "general":
            return None
        if geo.upper() in ("US", "USA"):
            return "US"
        src = (self.source or "").strip()
        return _SOURCE_TO_JURISDICTION.get(src, src) or None


def _norm(value: object) -> str:
    """Normalise a header for comparison: lowercase, no whitespace."""
    return re.sub(r"\s+", "", str(value or "")).lower()


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _code_from_header(header: str) -> str:
    """Derive a framework code from a workbook column header."""
    code = re.sub(r"[^A-Za-z0-9.]+", "-", header).strip("-").upper()
    return code[:50].rstrip("-.")


def _source_column_index(header_row: tuple) -> dict[str, int]:
    """Map our field names to column positions in the sources sheet."""
    index: dict[str, int] = {}
    for i, h in enumerate(header_row):
        s = norm_header(h)
        for prefix, field in _SOURCE_COLUMNS.items():
            # "source" must not swallow "focal document source"
            if field not in index and (s == prefix or (prefix != "source" and s.startswith(prefix))):
                index[field] = i
    missing = {"header", "fdi"} - set(index)
    if missing:
        raise ValueError(f"Framework sources sheet lacks columns: {sorted(missing)}")
    return index


def load_catalogue(wb, known_codes: dict[str, str] | None = None) -> list[CatalogueEntry]:
    """Pair the SCF sheet's framework columns with the sources sheet rows.

    ``wb`` is an openpyxl workbook. Rows are paired by position (the sheets
    list frameworks in the same order) and checked header-by-header; the
    import is aborted if the sheets have drifted apart.

    ``known_codes`` ({fdi: code}, from the frameworks table) keeps the codes
    of frameworks already loaded.
    """
    scf_sheet = scf_sheet_name(wb)
    src_sheet = sources_sheet_name(wb)
    scf_headers = list(next(wb[scf_sheet].iter_rows(min_row=1, max_row=1, values_only=True)))
    src_rows = wb[src_sheet].iter_rows(values_only=True)
    cols = _source_column_index(next(src_rows))

    def cell(row: tuple, field: str) -> object:
        i = cols.get(field)
        return row[i] if i is not None and i < len(row) else None

    source_rows = [r for r in src_rows if r and cell(r, "header") and cell(r, "fdi")]
    if not source_rows:
        raise ValueError(f"No framework rows found in the {src_sheet!r} sheet")

    norm_headers = [_norm(h) for h in scf_headers]
    first = _norm(cell(source_rows[0], "header"))
    if first not in norm_headers:
        raise ValueError(f"First {src_sheet!r} header {cell(source_rows[0], 'header')!r} not found in {scf_sheet!r}")
    start = norm_headers.index(first)
    if start + len(source_rows) > len(scf_headers):
        raise ValueError(f"{src_sheet!r} lists more frameworks than {scf_sheet!r} has columns")

    entries: list[CatalogueEntry] = []
    mismatches: list[str] = []
    for offset, row in enumerate(source_rows):
        col = start + offset
        header = str(scf_headers[col])
        if _norm(cell(row, "header")) != norm_headers[col]:
            mismatches.append(f"{header!r} ≠ {cell(row, 'header')!r}")
        url = cell(row, "url")
        entries.append(CatalogueEntry(
            column_index=col,
            header=header,
            fdi=_clean(cell(row, "fdi")),
            source=_clean(cell(row, "source")),
            name=_clean(cell(row, "name")),
            title=_clean(cell(row, "title")),
            url=_clean(url) if url and str(url).startswith("http") else None,
            geography=_clean(cell(row, "geography")),
        ))

    # A couple of header spelling differences between the sheets are normal;
    # many means the sheets are no longer in step and pairing is unsafe.
    if len(mismatches) > 5:
        raise ValueError(f"{len(mismatches)} header mismatches between sheets, e.g. {mismatches[:3]}")
    for m in mismatches:
        logger.info("Header differs between sheets (paired by position): %s", m)

    # Assign codes: the code the framework already has, else derived from the header.
    used: set[str] = set()
    for e in entries:
        code = pinned_code(e.fdi, known_codes) or _code_from_header(e.header)
        base, n = code, 2
        while code.upper() in used:
            code = f"{base[:46]}-{n}"
            n += 1
        e.code = code
        used.add(code.upper())

    return entries


def known_framework_codes(session: Session) -> dict[str, str]:
    """{fdi: code} for frameworks already loaded."""
    return {fdi: code for fdi, code in session.query(Framework.fdi, Framework.code) if fdi}


def sync_frameworks(session: Session, entries: list[CatalogueEntry]) -> dict[str, int]:
    """Create/update one framework per catalogue entry and set its jurisdiction.

    Also removes non-SCF frameworks that are not in the catalogue (legacy
    duplicates such as "FedRAMP" next to "US-FedRAMP", and frameworks SCF
    has dropped), together with their mappings, jurisdiction links and
    applicability rules.

    Returns a dict of framework code -> framework id for the catalogue.
    """
    from app.seed.jurisdictions import seed_jurisdictions

    seed_jurisdictions(session)
    jurisdictions = session.query(Jurisdiction).all()
    jur_by_key: dict[str, Jurisdiction] = {}
    for j in jurisdictions:
        jur_by_key[j.code.upper()] = j
        jur_by_key[j.name.upper()] = j

    by_code = {fw.code: fw for fw in session.query(Framework).all()}
    framework_ids: dict[str, int] = {}

    for e in entries:
        fw = by_code.get(e.code)
        if fw is None:
            fw = Framework(code=e.code, name=e.name or e.code, category="framework")
            session.add(fw)
        fw.name = (e.name or e.code)[:255]
        fw.description = e.title
        fw.publisher = (e.source or None) and e.source[:255]
        fw.source_url = (e.url or None) and e.url[:500]
        fw.fdi = e.fdi
        fw.is_scf = False
        session.flush()
        framework_ids[e.code] = fw.id

        # Jurisdiction links mirror the workbook's geography exactly.
        wanted: set[int] = set()
        key = e.jurisdiction_key
        if key:
            jur = jur_by_key.get(key.upper())
            if jur is None:
                logger.warning("Jurisdiction %r for %s not found – left untagged", key, e.code)
            else:
                wanted.add(jur.id)
        links = session.query(FrameworkJurisdiction).filter_by(framework_id=fw.id).all()
        for link in links:
            if link.jurisdiction_id not in wanted:
                session.delete(link)
        have = {link.jurisdiction_id for link in links}
        for jid in wanted - have:
            session.add(FrameworkJurisdiction(framework_id=fw.id, jurisdiction_id=jid, is_primary=True))

    # Remove frameworks the workbook no longer describes.
    catalogue_codes = set(framework_ids)
    for code, fw in by_code.items():
        if not fw.is_scf and code not in catalogue_codes:
            logger.info("Removing framework %s (not a column in the SCF workbook)", code)
            session.delete(fw)

    session.flush()
    logger.info("Framework catalogue synced: %d frameworks", len(framework_ids))
    return framework_ids


def prune_stale_mappings(session: Session, entries: list[CatalogueEntry], framework_ids: dict[str, int]) -> int:
    """Delete mappings that were imported from a column other than the framework's own."""
    removed = 0
    for e in entries:
        fw_id = framework_ids.get(e.code)
        if fw_id is None:
            continue
        removed += (
            session.query(ControlMapping)
            .filter(
                ControlMapping.framework_id == fw_id,
                (ControlMapping.source_column != e.header[:100]) | ControlMapping.source_column.is_(None),
            )
            .delete(synchronize_session=False)
        )
    session.flush()
    if removed:
        logger.info("Removed %d mappings imported from the wrong workbook column", removed)
    return removed


def resync_from_workbook(session: Session, wb) -> dict[str, int]:
    """Bring an existing database's frameworks and mappings in line with the workbook."""
    from app.importers.backfill_applicability import backfill_applicability_rules
    from app.importers.frameworks import current_scf_version
    from app.importers.mappings import import_mappings
    from app.importers.workbook import scf_version
    from app.services.recommendation_service import clear_recommendation_cache

    # Mappings are keyed by SCF #, so the controls must already be on the
    # workbook's release (a new release renumbers them: use load_scf).
    db_version, wb_version = current_scf_version(session), scf_version(wb)
    if db_version != wb_version:
        raise ValueError(
            f"Database holds SCF {db_version} but the workbook is SCF {wb_version}; "
            "run the full import (app.importers.load_scf) instead"
        )

    entries = load_catalogue(wb, known_framework_codes(session))
    framework_ids = sync_frameworks(session, entries)
    pruned = prune_stale_mappings(session, entries, framework_ids)
    added = import_mappings(session, wb, framework_ids, entries)
    rules = backfill_applicability_rules(session)
    clear_recommendation_cache()
    return {
        "frameworks": len(framework_ids),
        "mappings_removed": pruned,
        "mappings_added": added,
        "applicability_rules_added": sum(rules.values()),
    }


def main() -> None:
    """CLI entry point."""
    import openpyxl

    from app.config import settings
    from app.database import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Re-sync frameworks and mappings with the SCF workbook.")
    parser.add_argument("--file", default=settings.default_workbook)
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.file, data_only=True, read_only=True)
    session = SessionLocal()
    try:
        result = resync_from_workbook(session, wb)
        session.commit()
        print("Done:", result)
    except Exception:
        session.rollback()
        logger.exception("Catalogue sync failed")
        raise
    finally:
        session.close()
        wb.close()


if __name__ == "__main__":
    main()
