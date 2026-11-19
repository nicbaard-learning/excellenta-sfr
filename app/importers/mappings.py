"""Import cross-framework control mappings by pivoting framework columns."""

from __future__ import annotations

import logging

from app.importers.catalogue import CatalogueEntry, load_catalogue
from app.importers.workbook import norm_header, scf_sheet_name
from app.models.control import Control
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)


def import_mappings(
    session,
    wb,
    framework_ids: dict[str, int],
    entries: list[CatalogueEntry] | None = None,
) -> int:
    """Make each framework's control mappings match its SCF sheet column.

    Each workbook column maps to exactly one framework (see
    ``app.importers.catalogue``). Missing mappings are inserted and mappings
    the column no longer has (e.g. after SCF renumbered or remapped a
    control) are deleted. Returns the number inserted.
    """
    if entries is None:
        entries = load_catalogue(wb)
    columns = [(e, framework_ids[e.code]) for e in entries if e.code in framework_ids]
    if not columns:
        logger.info("No framework mapping columns detected")
        return 0

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    if not control_map:
        logger.warning("No controls loaded yet – cannot create mappings")
        return 0

    sheet = scf_sheet_name(wb)
    ws = wb[sheet]
    header = list(next(ws.iter_rows(min_row=1, max_row=1, values_only=True)))
    try:
        scf_col = next(i for i, h in enumerate(header) if norm_header(h) == "scf #")
    except StopIteration:
        logger.warning("SCF # column not found – cannot create mappings")
        return 0

    wanted: set[tuple[int, int, str]] = set()
    source_column: dict[int, str] = {}
    for entry, fw_id in columns:
        source_column[fw_id] = entry.header[:100]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if scf_col >= len(row) or row[scf_col] is None:
            continue
        control_id = control_map.get(str(row[scf_col]).strip())
        if control_id is None:
            continue
        for entry, fw_id in columns:
            if entry.column_index >= len(row):
                continue
            raw = row[entry.column_index]
            if raw is None or not str(raw).strip():
                continue
            for mapped_val in (x.strip() for x in str(raw).splitlines()):
                if mapped_val:
                    wanted.add((control_id, fw_id, mapped_val[:100]))

    fw_id_set = set(source_column)
    existing: dict[tuple[int, int, str], int] = {}
    stale_ids: list[int] = []
    for m_id, c_id, f_id, val in session.query(
        ControlMapping.id, ControlMapping.control_id, ControlMapping.framework_id, ControlMapping.mapped_control_id
    ).filter(ControlMapping.framework_id.in_(fw_id_set)):
        key = (c_id, f_id, val)
        if key in wanted and key not in existing:
            existing[key] = m_id
        else:
            stale_ids.append(m_id)

    for i in range(0, len(stale_ids), 1000):
        session.query(ControlMapping).filter(ControlMapping.id.in_(stale_ids[i:i + 1000])).delete(
            synchronize_session="evaluate"
        )
    session.flush()

    batch: list[ControlMapping] = []
    count = 0
    for control_id, fw_id, val in wanted:
        if (control_id, fw_id, val) in existing:
            continue
        batch.append(ControlMapping(
            control_id=control_id,
            framework_id=fw_id,
            mapped_control_id=val,
            source_sheet=sheet,
            source_column=source_column[fw_id],
        ))
        count += 1
        if len(batch) >= 500:
            session.add_all(batch)
            session.flush()
            batch.clear()
    if batch:
        session.add_all(batch)
        session.flush()

    logger.info("Control mappings: %d added, %d removed", count, len(stale_ids))
    return count
