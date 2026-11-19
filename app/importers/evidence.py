"""Import evidence request items from the Evidence Request List sheet."""

from __future__ import annotations

import logging

from app.importers.base import safe_str
from app.importers.workbook import norm_header, parse_scf_ids, versioned_sheet_name
from app.models.control import Control
from app.models.evidence import EvidenceArtifact

logger = logging.getLogger(__name__)


def _column_index(header: list) -> dict[str, int]:
    """Find the ERL #, title, description and SCF control mapping columns.

    Headers differ between releases ("Documentation Artifact" in 2026.1,
    "ERL Artifact" in 2026.3). "Legacy SCF Control Mappings" is skipped.
    """
    cols: dict[str, int] = {}
    for i, h in enumerate(header):
        s = norm_header(h)
        if s == "erl #":
            cols.setdefault("erl_number", i)
        elif s in ("scf control mappings", "scf mappings"):
            cols.setdefault("control_mappings", i)
        elif s in ("documentation artifact", "erl artifact"):
            cols.setdefault("title", i)
        elif s.endswith("artifact description"):
            cols.setdefault("description", i)
    return cols


def import_evidence(session, wb) -> int:
    """Replace all evidence artifacts with those in the workbook.

    Each Evidence Request List row lists the SCF #s it supports; one
    artifact row is stored per (control, ERL #).
    """
    sheet = versioned_sheet_name(wb, "Evidence Request List")
    if sheet is None:
        logger.warning("Evidence Request List sheet not found – skipping")
        return 0

    rows = wb[sheet].iter_rows(values_only=True)
    cols = _column_index(list(next(rows)))
    if "control_mappings" not in cols:
        raise ValueError(f"{sheet!r} lacks the 'SCF Control Mappings' column")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    session.query(EvidenceArtifact).delete(synchronize_session="evaluate")

    seen: set[tuple[int, str | None]] = set()
    count = unmatched = 0
    for n, row in enumerate(rows, start=2):
        def cell(key: str):
            i = cols.get(key)
            return row[i] if i is not None and i < len(row) else None

        erl_number = safe_str(cell("erl_number"))
        for scf_id in parse_scf_ids(cell("control_mappings")):
            control_id = control_map.get(scf_id)
            if not control_id:
                unmatched += 1
                continue
            if (control_id, erl_number) in seen:
                continue
            seen.add((control_id, erl_number))
            session.add(EvidenceArtifact(
                control_id=control_id,
                erl_number=erl_number,
                evidence_title=safe_str(cell("title")),
                evidence_description=safe_str(cell("description")),
                source_sheet=sheet,
                source_row=n,
            ))
            count += 1

    session.flush()
    if unmatched:
        logger.info("  SCF #s in evidence mappings that match no control: %d", unmatched)
    logger.info("Imported %d evidence artifacts", count)
    return count
