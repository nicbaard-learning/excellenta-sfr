"""Import cross-framework control mappings by pivoting framework columns."""

from __future__ import annotations

import logging

from app.importers.catalogue import SCF_SHEET, CatalogueEntry, load_catalogue
from app.models.control import Control
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)


def import_mappings(
    session,
    wb,
    framework_ids: dict[str, int],
    entries: list[CatalogueEntry] | None = None,
) -> int:
    """Pivot each framework column of the SCF sheet into control_mapping records.

    Each workbook column maps to exactly one framework (see
    ``app.importers.catalogue``). Existing mappings are kept; only missing
    ones are inserted.
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

    ws = wb[SCF_SHEET]
    header = list(next(ws.iter_rows(min_row=1, max_row=1, values_only=True)))
    try:
        scf_col = next(i for i, h in enumerate(header) if str(h or "").strip().lower() == "scf #")
    except StopIteration:
        logger.warning("SCF # column not found – cannot create mappings")
        return 0

    fw_id_set = {fw_id for _, fw_id in columns}
    existing = {
        (m.control_id, m.framework_id, m.mapped_control_id)
        for m in session.query(
            ControlMapping.control_id, ControlMapping.framework_id, ControlMapping.mapped_control_id
        ).filter(ControlMapping.framework_id.in_(fw_id_set))
    }

    count = 0
    batch: list[ControlMapping] = []

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

            for mapped_val in [x.strip() for x in str(raw).splitlines() if x.strip()]:
                key = (control_id, fw_id, mapped_val[:100])
                if key in existing:
                    continue
                batch.append(
                    ControlMapping(
                        control_id=control_id,
                        framework_id=fw_id,
                        mapped_control_id=mapped_val[:100],
                        source_sheet=SCF_SHEET,
                        source_column=entry.header[:100],
                    )
                )
                existing.add(key)
                count += 1

                if len(batch) >= 500:
                    session.add_all(batch)
                    session.flush()
                    batch.clear()

    if batch:
        session.add_all(batch)
        session.flush()

    logger.info("Imported %d control mappings", count)
    return count
