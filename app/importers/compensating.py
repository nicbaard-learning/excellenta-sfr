"""Import compensating controls.

From 2026.3 they are columns of the main SCF sheet ("Possible Compensating
Control #1", "Compensating Control #1 Name", "Compensating Control # 1
Description", "Compensating Control #1 Justification", and the same for
#2). Older workbooks had a separate "Compensating Controls <version>" sheet
whose headers repeat without numbers; there the first and second
occurrence of each header are #1 and #2.
"""

from __future__ import annotations

import logging
import re

from app.importers.base import safe_str
from app.importers.workbook import norm_header, scf_sheet_name, versioned_sheet_name
from app.models.compensating import CompensatingControlLink
from app.models.control import Control

logger = logging.getLogger(__name__)

_NUMBERED = {
    "scf_id": re.compile(r"^possible compensating control #\s*(\d)$"),
    "title": re.compile(r"^compensating control #\s*(\d) name$"),
    "description": re.compile(r"^compensating control #\s*(\d) description$"),
    "justification": re.compile(r"^compensating control #\s*(\d) justification$"),
}
# Old separate sheet: unnumbered, repeated headers ("Compensating Control #"
# held the description).
_REPEATED = {
    "scf_id": lambda s: s.startswith("possible compensating control"),
    "title": lambda s: s == "compensating control name",
    "description": lambda s: s == "compensating control #",
    "justification": lambda s: s == "compensating control justification",
}


def _sections(header: list) -> tuple[int | None, list[dict[str, int]]]:
    """(primary SCF # column, [{field: column} for #1, #2])."""
    norm = [norm_header(h) for h in header]
    primary = next((i for i, s in enumerate(norm) if s in ("scf #", "scf control #")), None)
    sections: dict[int, dict[str, int]] = {}
    for i, s in enumerate(norm):
        for field, rx in _NUMBERED.items():
            m = rx.match(s)
            if m:
                sections.setdefault(int(m.group(1)), {})[field] = i
    if not sections:
        counts: dict[str, int] = {}
        for i, s in enumerate(norm):
            for field, test in _REPEATED.items():
                if test(s):
                    counts[field] = counts.get(field, 0) + 1
                    sections.setdefault(counts[field], {})[field] = i
    return primary, [sections[k] for k in sorted(sections) if "scf_id" in sections[k]]


def import_compensating_controls(session, wb) -> int:
    """Replace all compensating control links with those in the workbook."""
    sheet = versioned_sheet_name(wb, "Compensating Controls") or scf_sheet_name(wb)
    rows = wb[sheet].iter_rows(values_only=True)
    primary, sections = _sections(list(next(rows)))
    if primary is None or not sections:
        logger.warning("No compensating control columns in %r – skipping", sheet)
        return 0

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    session.query(CompensatingControlLink).delete(synchronize_session="evaluate")

    seen: set[tuple[int, str]] = set()
    count = 0
    for n, row in enumerate(rows, start=2):
        control_id = control_map.get(safe_str(row[primary]) if primary < len(row) else "")
        if not control_id:
            continue
        for sec in sections:
            def cell(field: str):
                i = sec.get(field)
                return safe_str(row[i]) if i is not None and i < len(row) else None

            comp_id = cell("scf_id")
            if not comp_id or comp_id.upper() in ("N/A", "NA", "NONE"):
                continue
            if (control_id, comp_id) in seen:
                continue
            seen.add((control_id, comp_id))
            session.add(CompensatingControlLink(
                control_id=control_id,
                compensating_control_id=comp_id,
                compensating_control_title=cell("title"),
                compensating_control_description=cell("description"),
                justification=cell("justification"),
                source_sheet=sheet,
                source_row=n,
            ))
            count += 1

    session.flush()
    logger.info("Imported %d compensating control links", count)
    return count
