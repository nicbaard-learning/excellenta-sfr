"""Import frameworks and the SCF version from the workbook."""

from __future__ import annotations

import logging

from app.importers.catalogue import known_framework_codes, load_catalogue, sync_frameworks
from app.importers.workbook import scf_sheet_name, scf_version
from app.models.framework import Framework, FrameworkVersion

logger = logging.getLogger(__name__)


def import_frameworks(session, wb) -> dict[str, int]:
    """Import framework definitions from the workbook.

    One framework per mapping column of the SCF sheet, described by the
    matching row of the framework sources sheet (see
    ``app.importers.catalogue``), plus the canonical SCF framework itself.

    Returns a dict mapping framework code -> framework id.
    """
    framework_ids = sync_frameworks(session, load_catalogue(wb, known_framework_codes(session)))

    scf = session.query(Framework).filter_by(code="SCF").first()
    if scf is None:
        scf = Framework(
            code="SCF",
            name="Secure Controls Framework",
            category="canonical",
            is_scf=True,
            description="The Secure Controls Framework (SCF) – a canonical control library.",
        )
        session.add(scf)
        session.flush()
    framework_ids["SCF"] = scf.id

    set_scf_version(session, scf.id, scf_version(wb), scf_sheet_name(wb))

    session.flush()
    logger.info("Imported %d frameworks", len(framework_ids))
    return framework_ids


def current_scf_version(session) -> str | None:
    """The SCF release the database was last loaded from, or None if never."""
    row = (
        session.query(FrameworkVersion.version_label)
        .join(Framework, Framework.id == FrameworkVersion.framework_id)
        .filter(Framework.code == "SCF", FrameworkVersion.status == "active")
        .order_by(FrameworkVersion.id.desc())
        .first()
    )
    return row[0] if row else None


def set_scf_version(session, scf_framework_id: int, label: str, sheet: str) -> None:
    """Make ``label`` the active SCF version; earlier ones become superseded."""
    versions = session.query(FrameworkVersion).filter_by(framework_id=scf_framework_id).all()
    found = False
    for v in versions:
        if v.version_label == label:
            v.status = "active"
            v.source_sheet = sheet
            found = True
        elif v.status == "active":
            v.status = "superseded"
    if not found:
        session.add(FrameworkVersion(
            framework_id=scf_framework_id,
            version_label=label,
            status="active",
            source_sheet=sheet,
        ))
