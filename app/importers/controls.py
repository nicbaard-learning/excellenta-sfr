"""Import SCF domains and controls from the workbook.

Controls keep their database id across SCF releases. When the workbook is a
newer release than the database, each existing control is matched to its
new SCF # through the workbook's "Legacy SCF #" column and renumbered in
place (see ``renumber_controls``). Every control's text is then refreshed
from the workbook.
"""

from __future__ import annotations

import logging
from typing import Any

from app.importers.base import safe_float, safe_int, safe_str
from app.importers.workbook import norm_header, parse_scf_ids, scf_sheet_name
from app.models.control import Control, Domain

logger = logging.getLogger(__name__)

DOMAINS_SHEET = "SCF Domains & Principles"

# Control fields filled from the main sheet: attribute -> normalised header
# prefixes (first match wins). A field whose column is missing is left as is.
_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "description": ("secure controls framework (scf) control description",),
    "control_question": ("scf control question",),
    "conformity_cadence": ("conformity validation cadence",),
    "evidence_request_list_refs": ("evidence request list (erl) #",),
    "applicability_context": ("applicability/context",),
    "pptdf_applicability": ("pptdf applicability",),
    "solutions_micro_small": ("possible solutions & considerations micro-small",),
    "solutions_small": ("possible solutions & considerations small",),
    "solutions_medium": ("possible solutions & considerations medium",),
    "solutions_large": ("possible solutions & considerations large",),
    "solutions_enterprise": ("possible solutions & considerations enterprise",),
    "cmm_level_0": ("scr-cmm level 0",),
    "cmm_level_1": ("scr-cmm level 1",),
    "cmm_level_2": ("scr-cmm level 2",),
    "cmm_level_3": ("scr-cmm level 3",),
    "cmm_level_4": ("scr-cmm level 4",),
    "cmm_level_5": ("scr-cmm level 5",),
}


def _column_index(header: list[Any]) -> dict[str, int]:
    """Positions of the columns we read, by our own key."""
    norm = [norm_header(h) for h in header]

    def find(*prefixes: str, exact: bool = False) -> int | None:
        for i, h in enumerate(norm):
            if any(h == p if exact else h.startswith(p) for p in prefixes):
                return i
        return None

    cols: dict[str, int | None] = {
        "scf_id": find("scf #", exact=True),
        "domain": find("scf domain", exact=True),
        "title": find("scf control", exact=True),
        "legacy": find("legacy scf #", exact=True),
        "relative_weighting": find("relative control weighting"),
        "relative_weight": find("relative weight", exact=True),
    }
    for field, prefixes in _TEXT_FIELDS.items():
        cols[field] = find(*prefixes)
    if cols["scf_id"] is None:
        raise ValueError("SCF # column not found in the SCF sheet")
    return {k: v for k, v in cols.items() if v is not None}


def read_control_rows(wb) -> list[dict[str, Any]]:
    """The main sheet's control rows as dicts keyed like ``_column_index``."""
    ws = wb[scf_sheet_name(wb)]
    rows = ws.iter_rows(values_only=True)
    cols = _column_index(list(next(rows)))
    out: list[dict[str, Any]] = []
    for n, row in enumerate(rows, start=2):
        scf_id = safe_str(row[cols["scf_id"]]) if cols["scf_id"] < len(row) else None
        if not scf_id:
            continue
        rec = {k: (row[i] if i < len(row) else None) for k, i in cols.items()}
        rec["scf_id"] = scf_id
        rec["_row"] = n
        rec["_legacy"] = parse_scf_ids(rec.get("legacy"))
        out.append(rec)
    if not out:
        raise ValueError("No controls found in the SCF sheet")
    return out


def domain_code_of(scf_id: str) -> str:
    """Domain identifier of an SCF # ("GOV-01.2" -> "GOV")."""
    return scf_id.split("-", 1)[0].strip().upper()


def import_domains(session, wb) -> dict[str, int]:
    """Create/update one domain per SCF identifier (GOV, AAT, ...).

    Names and principles come from the "SCF Domains & Principles" sheet.
    Returns {domain code: domain id}.
    """
    existing = {d.code: d for d in session.query(Domain).all()}
    if DOMAINS_SHEET not in wb.sheetnames:
        logger.warning("%r sheet not found – domains come from control rows only", DOMAINS_SHEET)
        return {code: d.id for code, d in existing.items()}

    rows = wb[DOMAINS_SHEET].iter_rows(values_only=True)
    norm = [norm_header(h) for h in next(rows)]

    def idx(prefix: str) -> int | None:
        return next((i for i, h in enumerate(norm) if h.startswith(prefix)), None)

    i_name, i_code = idx("scf domain"), idx("scf identifier")
    i_principle, i_order = idx("security, compliance & resilience (scr) principles"), idx("#")
    if i_name is None or i_code is None:
        raise ValueError(f"{DOMAINS_SHEET!r} sheet lacks 'SCF Domain' / 'SCF Identifier' columns")

    ids: dict[str, int] = {}
    for row in rows:
        code = safe_str(row[i_code]) if i_code < len(row) else None
        name = safe_str(row[i_name]) if i_name < len(row) else None
        if not code or not name:
            continue
        code = code.upper()
        domain = existing.get(code)
        if domain is None:
            domain = Domain(code=code, name=name[:255])
            session.add(domain)
            existing[code] = domain
        domain.name = name[:255]
        if i_principle is not None and i_principle < len(row):
            domain.description = safe_str(row[i_principle])
        if i_order is not None and i_order < len(row):
            domain.display_order = safe_int(row[i_order])
        session.flush()
        ids[code] = domain.id
    logger.info("Synced %d domains", len(ids))
    return ids


def prune_domains(session, keep: set[str]) -> int:
    """Delete domains that are not SCF identifiers and have no controls.

    Older imports created extra domains keyed by name or initials.
    """
    removed = 0
    for d in session.query(Domain).all():
        if d.code in keep:
            continue
        if session.query(Control.id).filter(Control.domain_id == d.id).first() is None:
            session.delete(d)
            removed += 1
    session.flush()
    if removed:
        logger.info("Removed %d unused domains", removed)
    return removed


def renumber_controls(session, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Give existing controls their new SCF # using the Legacy SCF # column.

    For use when the workbook is a newer SCF release than the database.
    Each workbook row takes over the first existing control listed in its
    Legacy SCF # cell; other controls listed there were merged into it and
    are deleted, as are controls no row lists. Rows whose legacy cell is
    "NONE" become new controls later.

    Returns counts: renumbered, unchanged, merged_away, removed.
    """
    existing: dict[str, Control] = {c.scf_id: c for c in session.query(Control).all()}
    claimed: dict[int, str] = {}            # control id -> new scf_id
    listed: set[str] = set()
    merged_away: list[Control] = []

    for rec in rows:
        owner: Control | None = None
        for old in rec["_legacy"]:
            listed.add(old)
            ctrl = existing.get(old)
            if ctrl is None or ctrl.id in claimed:
                continue
            if owner is None:
                owner = ctrl
                claimed[ctrl.id] = rec["scf_id"]
            else:
                merged_away.append(ctrl)

    removed = [c for scf_id, c in existing.items() if c.id not in claimed and c not in merged_away]
    for ctrl in merged_away + removed:
        session.delete(ctrl)
    session.flush()

    by_id = {c.id: c for c in existing.values()}
    # Two steps so that swapping numbers never breaks the unique scf_id.
    for cid in claimed:
        by_id[cid].scf_id = f"~{cid}"
    session.flush()
    unchanged = 0
    for cid, new_scf_id in claimed.items():
        ctrl = by_id[cid]
        old = next((k for k, v in existing.items() if v is ctrl), None)
        unchanged += old == new_scf_id
        ctrl.scf_id = new_scf_id
    session.flush()

    counts = {
        "renumbered": len(claimed) - unchanged,
        "unchanged": unchanged,
        "merged_away": len(merged_away),
        "removed": len(removed),
    }
    logger.info("Renumbered controls: %s", counts)
    return counts


def import_controls(session, wb, domain_ids: dict[str, int], renumber: bool = False) -> int:
    """Create or refresh every control in the main sheet.

    With ``renumber`` (workbook newer than the database) existing controls
    are first matched to their new SCF # (``renumber_controls``). Controls no
    longer in the workbook are removed either way.
    """
    rows = read_control_rows(wb)
    sheet = scf_sheet_name(wb)
    if renumber:
        renumber_controls(session, rows)

    existing: dict[str, Control] = {c.scf_id: c for c in session.query(Control).all()}
    wanted = {rec["scf_id"] for rec in rows}
    stale = [c for scf_id, c in existing.items() if scf_id not in wanted]
    for ctrl in stale:
        session.delete(ctrl)
    if stale:
        logger.info("Removed %d controls not in the workbook", len(stale))
    session.flush()

    created = 0
    for rec in rows:
        scf_id = rec["scf_id"]
        code = domain_code_of(scf_id)
        if code not in domain_ids:
            domain = session.query(Domain).filter_by(code=code).first()
            if domain is None:
                domain = Domain(code=code, name=(safe_str(rec.get("domain")) or code)[:255])
                session.add(domain)
                session.flush()
            domain_ids[code] = domain.id

        ctrl = existing.get(scf_id)
        if ctrl is None:
            ctrl = Control(scf_id=scf_id, title=scf_id)
            session.add(ctrl)
            created += 1
        ctrl.domain_id = domain_ids[code]
        ctrl.title = (safe_str(rec.get("title")) or scf_id)[:500]
        for field in _TEXT_FIELDS:
            if field in rec:
                setattr(ctrl, field, safe_str(rec[field]))
        if "relative_weighting" in rec:
            ctrl.relative_weighting = safe_float(rec["relative_weighting"])
        if "relative_weight" in rec:
            ctrl.relative_weight = safe_int(rec["relative_weight"])
        if "legacy" in rec:
            ctrl.legacy_scf_ids = ", ".join(rec["_legacy"]) or None
        ctrl.source_sheet = sheet
        ctrl.source_row = rec["_row"]

    session.flush()
    logger.info("Imported %d controls (%d new, %d refreshed)", len(rows), created, len(rows) - created)
    return len(rows)
