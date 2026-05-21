"""Import cross-framework control mappings by pivoting framework columns."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, normalize_headers, safe_str
from app.importers.frameworks import identify_framework_columns
from app.models.control import Control
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)


def import_mappings(session, wb, framework_ids: dict[str, int]) -> int:
    """Pivot framework-mapped columns into control_mapping records."""
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            logger.warning("No SCF sheet found – skipping mapping import")
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    headers = normalize_headers(df)
    fw_columns = identify_framework_columns(headers)

    if not fw_columns:
        logger.info("No framework mapping columns detected")
        return 0

    col_names = list(df.columns)
    fw_col_map: dict[str, str] = {}
    for idx, code in fw_columns.items():
        if idx < len(col_names):
            fw_col_map[code] = col_names[idx]

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    if not control_map:
        logger.warning("No controls loaded yet – cannot create mappings")
        return 0

    existing = {
        (m.control_id, m.framework_id, m.mapped_control_id)
        for m in session.query(ControlMapping).all()
    }

    count = 0
    scf_num_col = _find_column(df, "SCF #")
    if scf_num_col is None:
        logger.warning("SCF # column not found – cannot create mappings")
        return 0

    batch: list[ControlMapping] = []

    for _, row in df.iterrows():
        scf_id = safe_str(row.get(scf_num_col))
        if not scf_id or scf_id not in control_map:
            continue

        control_id = control_map[scf_id]

        for fw_code, col_name in fw_col_map.items():
            fw_id = framework_ids.get(fw_code)
            if fw_id is None:
                continue

            raw = safe_str(row.get(col_name))
            if not raw:
                continue

            for mapped_val in [x.strip() for x in raw.splitlines() if x.strip()]:
                key = (control_id, fw_id, mapped_val)
                if key in existing:
                    continue

                batch.append(
                    ControlMapping(
                        control_id=control_id,
                        framework_id=fw_id,
                        mapped_control_id=mapped_val[:100],
                        source_sheet="SCF 2026.1",
                        source_column=str(col_name)[:100],
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


def _find_column(df: pd.DataFrame, name: str) -> str | None:
    for col in df.columns:
        if str(col).strip().lower() == name.lower():
            return col
    return None
