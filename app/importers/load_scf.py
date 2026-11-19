"""Main SCF workbook import orchestrator.

Usage:
    python -m app.importers.load_scf --file secure-controls-framework-scf-2026-3.xlsx

Safe to re-run. When the workbook is a newer SCF release than the database,
existing controls are renumbered in place through the workbook's Legacy
SCF # column, so their database ids (and anything that stored them) stay
valid. Everything else derived from the workbook is brought in line with it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

import openpyxl

from app.config import settings
from app.database import SessionLocal, utcnow
from app.importers.backfill_applicability import backfill_applicability_rules
from app.importers.catalogue import known_framework_codes, load_catalogue, prune_stale_mappings
from app.importers.compensating import import_compensating_controls
from app.importers.controls import import_controls, import_domains, prune_domains
from app.importers.evidence import import_evidence
from app.importers.frameworks import current_scf_version, import_frameworks
from app.importers.mappings import import_mappings
from app.importers.objectives import import_assessment_objectives
from app.importers.requirements import import_requirement_files
from app.importers.risks import import_risks
from app.importers.sources import import_authoritative_sources
from app.importers.threats import import_threats
from app.importers.workbook import scf_sheet_name, scf_version
from app.models.import_run import ImportRun

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def _version_key(label: str) -> tuple[int, ...]:
    return tuple(int(p) for p in label.split(".") if p.isdigit())


def needs_renumbering(db_version: str | None, wb_version: str) -> bool:
    """True when the database holds an older SCF release than the workbook.

    Raises if the workbook is older than the database (a downgrade would
    renumber controls the wrong way).
    """
    if db_version is None or db_version == wb_version:
        return False
    if _version_key(wb_version) < _version_key(db_version):
        raise ValueError(f"Workbook is SCF {wb_version} but the database already holds SCF {db_version}")
    return True


def resolve_db_version(db_version: str | None, has_controls: bool, assume: str | None) -> str | None:
    """The SCF release the database holds, refusing to guess.

    Without a recorded version, existing controls can't be matched to new
    numbers, and the import would replace them all (new ids, related data
    lost). ``assume`` (from --db-version) states the release explicitly.
    """
    if db_version is not None:
        if assume and assume != db_version:
            raise ValueError(f"--db-version {assume} given but the database records SCF {db_version}")
        return db_version
    if has_controls and not assume:
        raise ValueError(
            "The database has controls but no active SCF version row; "
            "pass --db-version (e.g. 2026.1) to say which release they are"
        )
    return assume


def load_workbook(filepath: str, assume_db_version: str | None = None) -> None:
    """Orchestrate a full import of the SCF workbook in one transaction."""
    from app.database import engine
    from app.schema_upgrade import ensure_schema

    ensure_schema(engine)  # new columns, in case the app hasn't started on this code yet
    logger.info("Opening workbook: %s", filepath)
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=False)
    logger.info("Workbook sheets: %s", wb.sheetnames)

    session = SessionLocal()
    import_run = ImportRun(filename=filepath, status="running")
    session.add(import_run)
    session.flush()

    sheets_processed: list[str] = []
    total_loaded = 0

    try:
        wb_version = scf_version(wb)
        scf_sheet = scf_sheet_name(wb)
        from app.models.control import Control

        db_version = resolve_db_version(
            current_scf_version(session),
            session.query(Control.id).first() is not None,
            assume_db_version,
        )
        renumber = needs_renumbering(db_version, wb_version)
        logger.info("Database SCF version: %s; workbook: %s; renumber controls: %s", db_version, wb_version, renumber)

        logger.info("Phase 1: Frameworks")
        framework_ids = import_frameworks(session, wb)
        sheets_processed.append(f"{scf_sheet} (frameworks)")
        total_loaded += len(framework_ids)

        logger.info("Phase 2: Domains")
        domain_ids = import_domains(session, wb)
        sheets_processed.append("SCF Domains & Principles")
        total_loaded += len(domain_ids)

        logger.info("Phase 3: Controls")
        total_loaded += import_controls(session, wb, domain_ids, renumber=renumber)
        prune_domains(session, set(domain_ids))
        sheets_processed.append(f"{scf_sheet} (controls)")

        logger.info("Phase 4: Control mappings")
        entries = load_catalogue(wb, known_framework_codes(session))
        prune_stale_mappings(session, entries, framework_ids)
        total_loaded += import_mappings(session, wb, framework_ids, entries)
        sheets_processed.append(f"{scf_sheet} (mappings)")

        logger.info("Phase 5: Assessment objectives")
        total_loaded += import_assessment_objectives(session, wb)
        sheets_processed.append("Assessment Objectives")

        logger.info("Phase 6: Evidence artifacts")
        total_loaded += import_evidence(session, wb)
        sheets_processed.append("Evidence Request List")

        logger.info("Phase 7: Compensating controls")
        total_loaded += import_compensating_controls(session, wb)
        sheets_processed.append("Compensating controls")

        logger.info("Phase 8: Authoritative sources")
        total_loaded += import_authoritative_sources(session, wb)
        sheets_processed.append("Focal Documents")

        # Framework–jurisdiction links are set in Phase 1 from the geography column.

        logger.info("Phase 9: Applicability rules (business-model, privacy, size)")
        app_counts = backfill_applicability_rules(session)
        total_loaded += sum(app_counts.values())

        logger.info("Phase 10: Threat catalog")
        total_loaded += import_threats(session, wb)
        sheets_processed.append("Threat Catalog")

        logger.info("Phase 11: Risk catalog")
        total_loaded += import_risks(session, wb)
        sheets_processed.append("Risk Catalog")

        # Official framework text (data/requirements), not from the workbook.
        logger.info("Phase 12: Framework provisions")
        total_loaded += import_requirement_files(session)

        wb.close()

        import_run.status = "completed"
        import_run.completed_at = utcnow()
        import_run.sheets_processed = json.dumps(sheets_processed)
        import_run.rows_loaded = total_loaded
        import_run.rows_skipped = 0

        session.commit()
        from app.services.recommendation_service import clear_recommendation_cache

        clear_recommendation_cache()
        logger.info("Import of SCF %s completed: %d rows", wb_version, total_loaded)

    except Exception as exc:
        logger.exception("Import failed: %s", exc)
        session.rollback()
        import_run = ImportRun(filename=filepath, status="failed", completed_at=utcnow(),
                               error_log=json.dumps([str(exc)]))
        session.add(import_run)
        session.commit()
        raise
    finally:
        session.close()


def main() -> None:
    """CLI entry point for the SCF importer."""
    parser = argparse.ArgumentParser(
        description="Load SCF workbook data into the SFR database."
    )
    parser.add_argument(
        "--file",
        default=settings.default_workbook,
        help=f"Path to the SCF workbook file (default: {settings.default_workbook})",
    )
    parser.add_argument(
        "--db-version",
        default=None,
        help="SCF release the database holds, only needed if it has controls but no SCF version row",
    )
    args = parser.parse_args()

    start = time.time()
    try:
        load_workbook(args.file, assume_db_version=args.db_version)
    except Exception as exc:
        logger.error("Import failed: %s", exc)
        sys.exit(1)
    elapsed = time.time() - start
    logger.info("Total time: %.2f seconds", elapsed)


if __name__ == "__main__":
    main()
