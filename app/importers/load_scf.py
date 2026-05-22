"""Main SCF workbook import orchestrator.

Usage:
    python -m app.importers.load_scf --file secure-controls-framework-scf-2026-1.xlsx
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time


import openpyxl

from app.database import SessionLocal, utcnow
from app.importers.compensating import import_compensating_controls
from app.importers.controls import import_controls, import_domains, import_principles
from app.importers.domains import import_domains_and_principles
from app.importers.evidence import import_evidence
from app.importers.backfill_jurisdictions import backfill_framework_jurisdictions
from app.importers.backfill_applicability import backfill_applicability_rules
from app.seed.jurisdictions import seed_jurisdictions
from app.importers.frameworks import import_frameworks
from app.importers.mappings import import_mappings
from app.importers.objectives import import_assessment_objectives
from app.importers.sources import import_authoritative_sources
from app.importers.threats import import_threats
from app.importers.risks import import_risks
from app.models.import_run import ImportRun

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def load_workbook(filepath: str) -> None:
    """Orchestrate a full import of the SCF workbook.

    The process is designed to be safely re-runnable: existing records are
    skipped (on conflict) so subsequent runs only load new data.
    """
    logger.info("Opening workbook: %s", filepath)
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=False)
    logger.info("Workbook sheets: %s", wb.sheetnames)

    session = SessionLocal()
    import_run = ImportRun(filename=filepath, status="running")
    session.add(import_run)
    session.flush()

    sheets_processed: list[str] = []
    total_loaded = 0
    total_skipped = 0
    error_log: list[str] = []

    try:
        # ---- Phase 1: Frameworks ----
        logger.info("─" * 50)
        logger.info("Phase 1: Importing frameworks...")
        framework_ids = import_frameworks(session, wb)
        sheets_processed.append("SCF 2026.1 (frameworks)")
        total_loaded += len(framework_ids)
        logger.info("  → %d frameworks registered", len(framework_ids))

        # ---- Phase 2: Domains & Principles ----
        logger.info("─" * 50)
        logger.info("Phase 2: Importing domains...")
        domain_ids = import_domains(session, wb)
        sheets_processed.append("SCF 2026.1 (domains)")
        total_loaded += len(domain_ids)

        # Also try the dedicated Domains & Principles sheet
        d_count, p_count = import_domains_and_principles(session, wb)
        if d_count or p_count:
            sheets_processed.append("SCF Domains & Principles")
            total_loaded += d_count + p_count
        logger.info("  → %d domains", len(domain_ids))

        logger.info("Phase 2b: Skipping principles import for now...")
        principle_ids = {}
        logger.info(" → 0 principles")
        
        # logger.info("Phase 2b: Importing principles...")
        # principle_ids = import_principles(session, wb, domain_ids)
        # total_loaded += len(principle_ids)
        # logger.info("  → %d principles", len(principle_ids))

        # ---- Phase 3: Controls ----
        logger.info("─" * 50)
        logger.info("Phase 3: Importing controls...")
        control_count = import_controls(session, wb, domain_ids, principle_ids)
        sheets_processed.append("SCF 2026.1 (controls)")
        total_loaded += control_count
        logger.info("  → %d controls", control_count)

        # ---- Phase 4: Control Mappings ----
        logger.info("─" * 50)
        logger.info("Phase 4: Importing control mappings...")
        mapping_count = import_mappings(session, wb, framework_ids)
        sheets_processed.append("SCF 2026.1 (mappings)")
        total_loaded += mapping_count
        logger.info("  → %d mappings", mapping_count)

        # ---- Phase 5: Assessment Objectives ----
        logger.info("─" * 50)
        logger.info("Phase 5: Importing assessment objectives...")
        obj_count = import_assessment_objectives(session, wb)
        sheets_processed.append("Assessment Objectives 2026.1")
        total_loaded += obj_count
        logger.info("  → %d assessment objectives", obj_count)

        # ---- Phase 6: Evidence Artifacts ----
        logger.info("─" * 50)
        logger.info("Phase 6: Importing evidence artifacts...")
        ev_count = import_evidence(session, wb)
        sheets_processed.append("Evidence Request List 2026.1")
        total_loaded += ev_count
        logger.info("  → %d evidence artifacts", ev_count)

        # ---- Phase 7: Compensating Controls ----
        logger.info("─" * 50)
        logger.info("Phase 7: Importing compensating controls...")
        comp_count = import_compensating_controls(session, wb)
        sheets_processed.append("Compensating Controls 2026.1")
        total_loaded += comp_count
        logger.info("  → %d compensating controls", comp_count)

        # ---- Phase 8: Authoritative Sources ----
        logger.info("─" * 50)
        logger.info("Phase 8: Importing authoritative sources...")
        src_count = import_authoritative_sources(session, wb)
        sheets_processed.append("Authoritative Sources")
        total_loaded += src_count
        logger.info("  → %d authoritative sources", src_count)

        # ---- Phase 9: Framework–Jurisdiction Links ----
        logger.info("─" * 50)
        logger.info("Phase 9a: Seeding jurisdictions...")
        seed_count = seed_jurisdictions(session)
        logger.info("  → %d jurisdictions seeded", seed_count)
        logger.info("Phase 9b: Backfilling framework–jurisdiction links...")
        link_count = backfill_framework_jurisdictions(session)
        total_loaded += link_count
        logger.info("  → %d framework–jurisdiction links created", link_count)

        # ---- Phase 10: Applicability Rules ----
        logger.info("─" * 50)
        logger.info("Phase 10: Backfilling applicability rules (business-model, privacy, size)...")
        app_counts = backfill_applicability_rules(session)
        total_app = sum(app_counts.values())
        total_loaded += total_app
        logger.info(
            "  → %d rules: %d business-model, %d privacy-context, %d size",
            total_app,
            app_counts.get("business_model", 0),
            app_counts.get("privacy_context", 0),
            app_counts.get("size", 0),
        )

        # ---- Phase 11: Threat Catalog ----
        logger.info("─" * 50)
        logger.info("Phase 11: Importing threat catalog...")
        threat_count = import_threats(session, wb)
        sheets_processed.append("Threat Catalog")
        total_loaded += threat_count
        logger.info("  → %d threats", threat_count)

        # ---- Phase 12: Risk Catalog ----
        logger.info("─" * 50)
        logger.info("Phase 12: Importing risk catalog...")
        risk_count = import_risks(session, wb)
        sheets_processed.append("Risk Catalog")
        total_loaded += risk_count
        logger.info("  → %d risks", risk_count)

        # ---- Finalise ----
        wb.close()

        import_run.status = "completed"
        import_run.completed_at = utcnow()
        import_run.sheets_processed = json.dumps(sheets_processed)
        import_run.rows_loaded = total_loaded
        import_run.rows_skipped = total_skipped
        if error_log:
            import_run.error_log = json.dumps(error_log)

        session.commit()
        logger.info("=" * 50)
        logger.info("Import completed successfully!")
        logger.info("  Rows loaded: %d", total_loaded)
        logger.info("  Rows skipped: %d", total_skipped)
        logger.info("  Sheets processed: %s", ", ".join(sheets_processed))
        logger.info("=" * 50)

    except Exception as exc:
        logger.exception("Import failed: %s", exc)
        import_run.status = "failed"
        import_run.completed_at = utcnow()
        import_run.error_log = json.dumps([str(exc)])
        session.commit()
        raise


def main() -> None:
    """CLI entry point for the SCF importer."""
    parser = argparse.ArgumentParser(
        description="Load SCF workbook data into the SFR database."
    )
    parser.add_argument(
        "--file",
        default="secure-controls-framework-scf-2026-1.xlsx",
        help="Path to the SCF workbook file (default: secure-controls-framework-scf-2026-1.xlsx)",
    )
    args = parser.parse_args()

    start = time.time()
    try:
        load_workbook(args.file)
    except Exception as exc:
        logger.error("Import failed: %s", exc)
        sys.exit(1)
    elapsed = time.time() - start
    logger.info("Total time: %.2f seconds", elapsed)


if __name__ == "__main__":
    main()
