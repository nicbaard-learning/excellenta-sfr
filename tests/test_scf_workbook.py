"""SCF release upgrade: the importers against the shipped 2026.1 and 2026.3 workbooks.

Runs on an in-memory SQLite database (never the .env database). The
2026.1 state is rebuilt from the 2026.1 workbook's control numbers and the
framework codes the live database had, then upgraded with 2026.3.

The counts (270 frameworks, 1591 controls, 1468 old, 23 merged) are those of
these two pinned workbooks; a later SCF release needs its own expectations.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "secure-controls-framework-scf-2026-1.xlsx"
NEW = ROOT / "secure-controls-framework-scf-2026-3.xlsx"

pytestmark = pytest.mark.skipif(not (OLD.exists() and NEW.exists()), reason="SCF workbooks not present")


@pytest.fixture(scope="module")
def new_wb():
    wb = openpyxl.load_workbook(NEW, read_only=True, data_only=True)
    yield wb
    wb.close()


@pytest.fixture(scope="module")
def old_ids():
    from app.importers.controls import read_control_rows

    wb = openpyxl.load_workbook(OLD, read_only=True, data_only=True)
    ids = [rec["scf_id"] for rec in read_control_rows(wb)]  # SCF # found by header
    wb.close()
    assert len(ids) == 1468
    return ids


@pytest.fixture()
def session():
    import app.models  # noqa: F401

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _seed_2026_1(session, old_ids):
    """Controls numbered as in 2026.1, in an old-style 'initials' domain."""
    from app.models.control import Control, Domain

    junk = Domain(code="SCRG", name="Security, Compliance & Resilience Governance")
    session.add(junk)
    session.flush()
    for scf_id in old_ids:
        session.add(Control(scf_id=scf_id, title=f"old {scf_id}", description="old text", domain_id=junk.id))
    session.flush()
    return {c.scf_id: c.id for c in session.query(Control)}


# ── Workbook helpers ────────────────────────────────────────────────────


def test_version_and_sheets(new_wb):
    from app.importers.workbook import scf_sheet_name, scf_version, sources_sheet_name, versioned_sheet_name

    assert scf_version(new_wb) == "2026.3"
    assert scf_sheet_name(new_wb) == "SCF 2026.3"
    assert sources_sheet_name(new_wb) == "Focal Documents (FD)"
    assert versioned_sheet_name(new_wb, "Evidence Request List") == "Evidence Request List 2026.3"
    assert versioned_sheet_name(new_wb, "Compensating Controls") is None


def test_parse_scf_ids():
    from app.importers.workbook import parse_scf_ids

    assert parse_scf_ids("NONE") == []
    assert parse_scf_ids("N/A - New Control") == []
    assert parse_scf_ids("CHG-04\nEND-03.2") == ["CHG-04", "END-03.2"]
    assert parse_scf_ids("VPM-03, VPM-05") == ["VPM-03", "VPM-05"]


def test_needs_renumbering():
    from app.importers.load_scf import needs_renumbering

    assert needs_renumbering("2026.1", "2026.3") is True
    assert needs_renumbering("2026.3", "2026.3") is False
    assert needs_renumbering(None, "2026.3") is False
    with pytest.raises(ValueError):
        needs_renumbering("2026.3", "2026.1")


def test_resolve_db_version_refuses_to_guess():
    from app.importers.load_scf import resolve_db_version

    assert resolve_db_version("2026.1", True, None) == "2026.1"
    assert resolve_db_version(None, False, None) is None          # empty database: fresh load
    assert resolve_db_version(None, True, "2026.1") == "2026.1"   # stated explicitly
    with pytest.raises(ValueError, match="--db-version"):
        resolve_db_version(None, True, None)                      # would wipe every control id
    with pytest.raises(ValueError):
        resolve_db_version("2026.1", True, "2026.2")


# ── Frameworks keep their codes and ids ─────────────────────────────────


def test_catalogue_keeps_2026_1_codes(new_wb):
    from app.importers.catalogue import load_catalogue
    from app.importers.framework_codes import FRAMEWORK_CODES

    entries = load_catalogue(new_wb)
    assert len(entries) == 270
    codes = {e.code for e in entries}
    lost = set(FRAMEWORK_CODES.values()) - codes
    assert lost == {"EMEA-ES", "AU-Privacy", "EMEA-SPAIN-BOE-A-2022-7191"}
    # Codes the TPRM app (Excellenta) matches on, LOCAL_CODE_TO_SFR_CODE.
    tprm = {"EMEA-ZA", "ISO27001", "ISO27002", "ISO22301", "PCI-DSS", "NIST-CSF", "NIST-800-171",
            "NIST-800-53", "CIS-CSC", "COBIT", "US-HIPAA", "US-SOX", "EU-GDPR", "US-CA-CCPA",
            "BR-LGPD", "CA", "US-CMMC", "US-GLBA", "EU-NIS2", "EU-AI-Act"}
    assert tprm <= codes
    by_code = {e.code: e for e in entries}
    assert by_code["EMEA-ZA"].fdi == "emea-zaf-popia-2013"
    assert by_code["EMEA-UK-DPA"].fdi == "emea-gbr-dpa-2018"
    assert by_code["NIST-800-53"].fdi == "general-nist-800-53-r5-2"
    assert len(codes) == len(entries)


def test_framework_sync_keeps_ids(session, new_wb):
    from app.importers.framework_codes import FRAMEWORK_CODES
    from app.importers.frameworks import current_scf_version, import_frameworks, set_scf_version
    from app.models.framework import Framework

    scf = Framework(code="SCF", name="Secure Controls Framework", is_scf=True)
    session.add(scf)
    for code in FRAMEWORK_CODES.values():
        session.add(Framework(code=code, name=code))
    session.flush()
    set_scf_version(session, scf.id, "2026.1", "SCF 2026.1")
    before = {f.code: f.id for f in session.query(Framework)}

    ids = import_frameworks(session, new_wb)

    for code in ("EMEA-ZA", "ISO27001", "PCI-DSS", "NIST-800-53", "EU-GDPR", "EMEA-UK-DPA", "US-CMMC-2.0-LEVEL-2"):
        assert ids[code] == before[code], code
    assert session.query(Framework).filter_by(code="EMEA-ES").first() is None
    assert session.query(Framework).filter_by(code="EMEA-ZA").one().fdi == "emea-zaf-popia-2013"
    assert "2018" in session.query(Framework).filter_by(code="EMEA-UK-DPA").one().name
    assert current_scf_version(session) == "2026.3"

    # Second run: codes now come from the stored FDI; nothing moves.
    assert import_frameworks(session, new_wb) == ids


# ── Controls are renumbered in place ────────────────────────────────────


def test_controls_renumbered_in_place(session, new_wb, old_ids):
    from app.importers.controls import import_controls, import_domains, prune_domains
    from app.models.control import Control, Domain

    old = _seed_2026_1(session, old_ids)
    domain_ids = import_domains(session, new_wb)
    assert len(domain_ids) == 34 and "GOV" in domain_ids

    assert import_controls(session, new_wb, domain_ids, renumber=True) == 1591
    prune_domains(session, set(domain_ids))
    now = {c.scf_id: c for c in session.query(Control)}

    assert len(now) == 1591
    # GOV-01 became GOV-02; the new GOV-01 is a new control.
    assert now["GOV-02"].id == old["GOV-01"]
    assert now["GOV-01"].id not in old.values()
    assert now["GOV-02"].legacy_scf_ids == "GOV-01"
    assert now["GOV-01"].legacy_scf_ids is None
    # AST-22 merges AST-09 and TDA-11.2: it keeps AST-09's row, TDA-11.2's goes.
    assert now["AST-22"].id == old["AST-09"]
    assert old["TDA-11.2"] not in {c.id for c in now.values()}
    # Text refreshed from the workbook, domain by SCF identifier.
    assert now["GOV-02"].title == "Security, Compliance & Resilience Program (SCRP)"
    assert now["GOV-02"].description and now["GOV-02"].description != "old text"
    assert now["GOV-02"].domain.code == "GOV"
    assert now["GOV-02"].source_sheet == "SCF 2026.3"
    assert session.query(Domain).filter_by(code="SCRG").first() is None
    # 1468 old controls: every one kept except the 23 merged away.
    assert len(set(old.values()) & {c.id for c in now.values()}) == 1468 - 23

    # Re-running on the same release changes nothing.
    ids = {k: c.id for k, c in now.items()}
    import_controls(session, new_wb, domain_ids, renumber=False)
    assert {c.scf_id: c.id for c in session.query(Control)} == ids


def test_legacy_lookup(session, new_wb, old_ids):
    from app.importers.controls import import_controls, import_domains
    from app.services.control_service import ControlService

    old = _seed_2026_1(session, old_ids)
    import_controls(session, new_wb, import_domains(session, new_wb), renumber=True)
    svc = ControlService(session)
    # SEA-01.1 is no longer a current number: found through its legacy entry.
    assert svc.get_control_by_scf_id("SEA-01.1").scf_id == "GOV-03"
    assert svc.get_control_by_scf_id("SEA-01.1").id == old["SEA-01.1"]
    # GOV-01 is current again (a new control): the current one wins.
    assert svc.get_control_by_scf_id("GOV-01").legacy_scf_ids is None


# ── Workbook-derived data is replaced, not appended ─────────────────────


def test_related_data_refreshed(session, new_wb, old_ids):
    from app.importers.compensating import import_compensating_controls
    from app.importers.controls import import_controls, import_domains
    from app.importers.evidence import import_evidence
    from app.importers.objectives import import_assessment_objectives
    from app.models.assessment import AssessmentObjective
    from app.models.evidence import EvidenceArtifact

    _seed_2026_1(session, old_ids)
    import_controls(session, new_wb, import_domains(session, new_wb), renumber=True)

    n_ao = import_assessment_objectives(session, new_wb)
    n_ev = import_evidence(session, new_wb)
    n_cc = import_compensating_controls(session, new_wb)
    assert n_ao > 6000
    assert n_ev > 400
    assert n_cc > 0
    # Evidence links come from "SCF Control Mappings", not the legacy column.
    ev = session.query(EvidenceArtifact).filter_by(erl_number="E-AAT-01").all()
    assert sorted(e.control.scf_id for e in ev) == ["AAT-02", "AAT-05", "AAT-08"]
    assert session.query(AssessmentObjective).filter_by(objective_code="GOV-01_A01").one().control.scf_id == "GOV-01"

    assert import_assessment_objectives(session, new_wb) == n_ao
    assert import_evidence(session, new_wb) == n_ev
    assert import_compensating_controls(session, new_wb) == n_cc
    assert session.query(AssessmentObjective).count() == n_ao


def test_mappings_synced(session, new_wb, old_ids):
    from app.importers.catalogue import load_catalogue
    from app.importers.controls import import_controls, import_domains
    from app.importers.frameworks import import_frameworks
    from app.importers.mappings import import_mappings
    from app.models.mapping import ControlMapping

    _seed_2026_1(session, old_ids)
    framework_ids = import_frameworks(session, new_wb)
    import_controls(session, new_wb, import_domains(session, new_wb), renumber=True)
    entries = load_catalogue(new_wb)

    added = import_mappings(session, new_wb, framework_ids, entries)
    assert added > 10000
    assert import_mappings(session, new_wb, framework_ids, entries) == 0

    # A mapping the workbook doesn't have is removed on the next run.
    first = session.query(ControlMapping).first()
    session.add(ControlMapping(control_id=first.control_id, framework_id=first.framework_id,
                               mapped_control_id="not-in-workbook"))
    session.flush()
    import_mappings(session, new_wb, framework_ids, entries)
    assert session.query(ControlMapping).filter_by(mapped_control_id="not-in-workbook").count() == 0
    assert session.query(ControlMapping).count() == added


def test_resync_refuses_other_release(session, new_wb):
    from app.importers.catalogue import resync_from_workbook
    from app.importers.frameworks import set_scf_version
    from app.models.framework import Framework

    scf = Framework(code="SCF", name="SCF", is_scf=True)
    session.add(scf)
    session.flush()
    set_scf_version(session, scf.id, "2026.1", "SCF 2026.1")
    with pytest.raises(ValueError, match="full import"):
        resync_from_workbook(session, new_wb)
