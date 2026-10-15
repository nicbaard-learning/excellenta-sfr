"""Import frameworks and versions from the workbook."""

from __future__ import annotations

import logging

from app.importers.catalogue import load_catalogue, sync_frameworks
from app.models.framework import Framework, FrameworkVersion

logger = logging.getLogger(__name__)


def import_frameworks(session, wb) -> dict[str, int]:
    """Import framework definitions from the workbook.

    One framework per mapping column of the SCF sheet, described by the
    matching row of the Authoritative Sources sheet (see
    ``app.importers.catalogue``), plus the canonical SCF framework itself.

    Returns a dict mapping framework code -> framework id.
    """
    framework_ids = sync_frameworks(session, load_catalogue(wb))

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

    _import_scf_version(session, scf.id)

    session.flush()
    logger.info("Imported %d frameworks", len(framework_ids))
    return framework_ids


def _import_scf_version(session, scf_framework_id: int) -> None:
    """Create the SCF version record if missing."""
    version = session.query(FrameworkVersion).filter_by(
        framework_id=scf_framework_id, version_label="2026.1"
    ).first()
    if not version:
        session.add(FrameworkVersion(
            framework_id=scf_framework_id,
            version_label="2026.1",
            status="active",
            source_sheet="SCF 2026.1",
        ))
