"""Import assessment objectives from the Assessment Objectives sheet."""

from __future__ import annotations

import logging

from app.importers.base import safe_str
from app.importers.workbook import norm_header, versioned_sheet_name
from app.models.assessment import AssessmentObjective
from app.models.control import Control

logger = logging.getLogger(__name__)


def _column_index(header: list) -> dict[str, int]:
    """Find the control #, AO # and AO text columns.

    "Legacy SCF #" and "... (AO) Origin(s)" look alike but must be skipped.
    """
    cols: dict[str, int] = {}
    for i, h in enumerate(header):
        s = norm_header(h)
        if s in ("scf #", "scf control #") and "control_ref" not in cols:
            cols["control_ref"] = i
        elif s in ("scf ao #", "ao #") and "code" not in cols:
            cols["code"] = i
        elif s.startswith("scf assessment objective (ao)") and "origin" not in s and "text" not in cols:
            cols["text"] = i
    return cols


def import_assessment_objectives(session, wb) -> int:
    """Replace all assessment objectives with those in the workbook."""
    sheet = versioned_sheet_name(wb, "Assessment Objectives")
    if sheet is None:
        logger.warning("Assessment Objectives sheet not found – skipping")
        return 0

    rows = wb[sheet].iter_rows(values_only=True)
    cols = _column_index(list(next(rows)))
    if "control_ref" not in cols or "text" not in cols:
        raise ValueError(f"{sheet!r} lacks the SCF # or Assessment Objective column")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    session.query(AssessmentObjective).delete(synchronize_session="evaluate")

    count = 0
    for n, row in enumerate(rows, start=2):
        def cell(key: str):
            i = cols.get(key)
            return row[i] if i is not None and i < len(row) else None

        control_id = control_map.get(safe_str(cell("control_ref")) or "")
        text = safe_str(cell("text"))
        if not control_id or not text:
            continue
        session.add(AssessmentObjective(
            control_id=control_id,
            objective_code=safe_str(cell("code")),
            objective_text=text,
            source_sheet=sheet,
            source_row=n,
        ))
        count += 1
        if count % 1000 == 0:
            session.flush()

    session.flush()
    logger.info("Imported %d assessment objectives", count)
    return count
