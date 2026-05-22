"""Import evidence request items from the Evidence Request List sheet."""

from __future__ import annotations

import logging

import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, safe_str
from app.models.control import Control
from app.models.evidence import EvidenceArtifact

logger = logging.getLogger(__name__)


def _parse_control_mappings(raw: str) -> list[str]:
    """Parse the SCF Control Mappings column value into a list of SCF IDs.

    Handles:
    - Newline-separated IDs (e.g. 'VPM-03\\nVPM-05')
    - Comma-separated IDs (e.g. 'VPM-03, VPM-05')
    - Mixed newline+comma separators
    - Whitespace trimming
    - Empty/invalid entries are filtered out
    """
    if not raw or not raw.strip():
        return []

    # First split by newlines (both \n and literal newlines in the cell)
    parts = []
    for line in raw.split("\n"):
        # Then split each line by commas
        for item in line.split(","):
            cleaned = item.strip()
            if cleaned:
                parts.append(cleaned)
    return parts


def import_evidence(session, wb) -> int:
    """Load evidence artifacts from the 'Evidence Request List 2026.1' sheet.

    The Evidence sheet links to controls via the 'SCF Control Mappings' column,
    which contains SCF #s separated by newlines and/or commas
    (e.g. 'VPM-03\\nVPM-05' or 'VPM-03, VPM-05').
    Each evidence row may map to multiple controls.
    """
    df = load_sheet_dataframe(wb, "Evidence Request List 2026.1")
    if df is None:
        sheet = find_sheet(wb, "Evidence Request List")
        if sheet is None:
            logger.warning("Evidence Request List sheet not found – skipping")
            return 0
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    control_map = {c.scf_id: c.id for c in session.query(Control).all()}
    if not control_map:
        logger.warning("No controls loaded – cannot create evidence artifacts")
        return 0

    # Build a set of existing (control_id, erl_number) pairs for idempotency
    existing_pairs: set[tuple[int, str]] = set()
    for e in session.query(EvidenceArtifact).all():
        if e.control_id and e.erl_number:
            existing_pairs.add((e.control_id, e.erl_number))

    col_map = _map_columns(df)
    control_mappings_col = col_map.get("control_mappings")
    erl_col = col_map.get("erl_number")
    title_col = col_map.get("title")
    desc_col = col_map.get("description")

    if not control_mappings_col:
        logger.warning(
            "Could not find 'SCF Control Mappings' column in Evidence sheet "
            "– cannot link evidence to controls"
        )
        return 0

    count = 0
    skipped_no_scf = 0
    skipped_unmatched = 0
    skipped_duplicate = 0
    sheet_name = getattr(df, "sheet_name", "Evidence Request List")

    for idx, row in df.iterrows():
        raw_mappings = safe_str(row.get(control_mappings_col))
        if not raw_mappings:
            skipped_no_scf += 1
            continue

        erl_number = safe_str(row.get(erl_col)) if erl_col else None
        evidence_title = safe_str(row.get(title_col)) if title_col else None
        evidence_description = safe_str(row.get(desc_col)) if desc_col else None

        # Parse the SCF Control Mappings column: split on newlines AND commas
        scf_ids = _parse_control_mappings(raw_mappings)

        for scf_id in scf_ids:
            control_id = control_map.get(scf_id)
            if not control_id:
                skipped_unmatched += 1
                continue

            # Check for duplicate (control_id, erl_number) pair
            if erl_number and (control_id, erl_number) in existing_pairs:
                skipped_duplicate += 1
                continue

            artifact = EvidenceArtifact(
                control_id=control_id,
                erl_number=erl_number,
                evidence_title=evidence_title,
                evidence_description=evidence_description,
                source_sheet=sheet_name,
                source_row=int(idx) + 2,
            )
            session.add(artifact)
            count += 1
            if erl_number:
                existing_pairs.add((control_id, erl_number))

    session.flush()
    if skipped_no_scf:
        logger.info("  Evidence rows with no SCF Control Mappings: %d", skipped_no_scf)
    if skipped_unmatched:
        logger.info("  SCF IDs in mappings that did not match any control: %d", skipped_unmatched)
    if skipped_duplicate:
        logger.info("  Duplicate evidence entries skipped: %d", skipped_duplicate)
    logger.info("Imported %d evidence artifacts", count)
    return count


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map column headers to standardized keys for the Evidence Request List sheet.

    Known columns in Evidence Request List 2026.1:
        # | ERL # | Area of Focus | Documentation Artifact |
        Artifact Description | SCF Control Mappings | Relevant CMMC 2.0 L2 Control
    """
    col_map: dict[str, str] = {}
    for col in df.columns:
        if col is None or pd.isna(col):
            continue
        s = str(col).strip().lower()
        # Normalize newlines/spaces like normalize_headers does
        s = " ".join(s.split())

        # Detect SCF Control Mappings (the primary control reference column)
        if "scf control mappings" in s or "scf mapping" in s:
            col_map["control_mappings"] = col
        elif any(x in s for x in ("erl #", "erl number", "evidence request list")):
            col_map["erl_number"] = col
        elif any(x in s for x in ("documentation artifact", "artifact title", "evidence title")):
            col_map["title"] = col
        elif any(x in s for x in ("artifact description", "evidence description", "description")):
            col_map["description"] = col
        elif any(x in s for x in ("evidence type", "artifact type", "type")):
            col_map["type"] = col
    return col_map
