"""Framework provisions (official text) – importer, SCF matching and page.

The database tests need migration 0004 (`alembic upgrade head`) and a
database loaded from the SCF workbook. They write inside a transaction that
is rolled back.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import inspect

from app.database import SessionLocal, engine
from app.importers.requirements import REQUIREMENTS_DIR, _validate, import_requirements
from app.models.framework import Framework
from app.models.mapping import ControlMapping
from app.services.framework_service import FrameworkService, provision_number


# ── provision_number ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "ref, expected",
    [
        ("19(1)(a)", "19"),
        ("22", "22"),
        ("Sec 22", "22"),
        ("Section 72(1)", "72"),
        ("s. 11(3)", "11"),
        ("Art 33", "33"),
        ("Article 5(1)(b)", "5"),
        ("3A", "3A"),
        ("19a(2)", "19A"),
        ("Chapter 3", None),
        ("", None),
        (None, None),
    ],
)
def test_provision_number(ref, expected):
    assert provision_number(ref) == expected


# ── file validation ────────────────────────────────────────────────────

def _file(*items, **extra):
    return {"framework_code": "EMEA-ZA", "requirements": list(items), **extra}


SECTION = {"ref": "s22", "instrument": "Act", "kind": "section", "number": "22"}


@pytest.mark.parametrize(
    "data, message",
    [
        ({"requirements": []}, "framework_code"),
        ({"framework_code": "X"}, "must be a list"),
        (_file({"instrument": "Act", "kind": "section"}), "missing ref"),
        (_file(SECTION, SECTION), "duplicate ref"),
        (_file({**SECTION, "kind": "clause"}), "unknown kind"),
        (_file({**SECTION, "status": "draft"}), "unknown status"),
        (_file({**SECTION, "parent_ref": "ch3"}), "parent_ref"),
    ],
)
def test_invalid_files_are_rejected(data, message):
    with pytest.raises(ValueError, match=message):
        _validate(data, "test.json")


@pytest.mark.parametrize("path", sorted(REQUIREMENTS_DIR.glob("*.json")), ids=lambda p: p.name)
def test_shipped_data_files_are_valid(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    _validate(data, path.name)
    assert data.get("attribution"), "every shipped file must carry a credit line"


def test_defaults_fill_missing_fields_per_instrument():
    data = _file(
        {**SECTION},
        {**SECTION, "ref": "s23", "number": "23", "source_url": "own"},
        {"ref": "r1", "instrument": "Regulations", "kind": "regulation", "number": "1"},
        defaults={"Act": {"source_url": "act-url", "effective_from": "2020-07-01"}},
    )
    items = _validate(data, "test.json")
    assert items[0]["source_url"] == "act-url" and items[0]["effective_from"] == "2020-07-01"
    assert items[1]["source_url"] == "own"
    assert "source_url" not in items[2]


def test_popia_file_has_every_section_and_regulation():
    data = json.loads((REQUIREMENTS_DIR / "popia.json").read_text(encoding="utf-8"))
    items = _validate(data, "popia.json")
    sections = {i["number"] for i in items if i["kind"] == "section"}
    regulations = {i["number"] for i in items if i["kind"] == "regulation"}
    assert sections == {str(n) for n in range(1, 116)}
    assert regulations == {str(n) for n in range(1, 14)}
    assert all(i.get("text") for i in items if i["kind"] in ("section", "regulation"))


def test_framework_page_renders_text_and_credits():
    from types import SimpleNamespace

    from app.ui import templates

    data = json.loads((REQUIREMENTS_DIR / "popia.json").read_text(encoding="utf-8"))
    reqs = [
        {"status": "in_force", "number": None, "title": None, "text": None, "status_note": None,
         "version_label": None, "source_url": None, "controls": [], **item}
        for item in _validate(data, "popia.json")
    ]
    reqs[[r["ref"] for r in reqs].index("s22")]["controls"] = [{"id": 1, "scf_id": "IRO-10", "title": "t"}]
    html = templates.get_template("framework_detail.html").render(
        request=SimpleNamespace(query_params={}, url=SimpleNamespace(path="/frameworks/1")),
        fw={"id": 1, "code": "EMEA-ZA", "name": "POPIA", "category": None, "description": None,
            "publisher": None, "source_url": None, "is_scf": False, "licence_name": data["licence_name"],
            "licence_url": None, "attribution": data["attribution"]},
        controls=[], versions=[], jurisdiction_codes=["ZA"], related=[], requirements=reqs,
        scf_credit={"name": "Secure Controls Framework", "licence_name": "CC BY-ND 4.0",
                    "licence_url": "https://creativecommons.org/licenses/by-nd/4.0/legalcode.en",
                    "attribution": "SCF credit"},
    )
    assert "Notification of security compromises" in html
    assert "Condition 7: Security Safeguards" in html
    assert "IRO-10" in html
    assert "Government Gazette No. 37067" in html
    assert "SCF credit" in html and "legalcode.en" in html
    assert "Part : " not in html


def test_reload_fails_loudly_when_data_folder_missing(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import app.importers.requirements as req_module
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "admin_api_key", "test-key")
    monkeypatch.setattr(req_module, "REQUIREMENTS_DIR", tmp_path / "missing")
    r = TestClient(app).post("/api/system/reload-requirements", headers={"X-API-Key": "test-key"})
    assert r.status_code == 500
    assert "No requirement files" in r.json()["detail"]


def test_schema_upgrade_postgres_statements_only_for_missing_columns():
    from app.schema_upgrade import add_column_statements

    statements = add_column_statements("postgresql", {"frameworks": {"licence_name"}})
    assert statements == [
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS licence_url VARCHAR(500)",
        "ALTER TABLE frameworks ADD COLUMN IF NOT EXISTS attribution TEXT",
    ]
    all_present = {"frameworks": {"licence_name", "licence_url", "attribution"}}
    assert add_column_statements("postgresql", all_present) == []


def test_schema_upgrade_adds_missing_columns_to_old_database():
    from sqlalchemy import create_engine, text

    from app.schema_upgrade import ensure_schema

    engine = create_engine("sqlite://")
    with engine.begin() as conn:  # frameworks as it was before migration 0004
        conn.execute(text(
            "CREATE TABLE frameworks (id INTEGER PRIMARY KEY, code VARCHAR(50) NOT NULL UNIQUE, "
            "name VARCHAR(255) NOT NULL, category VARCHAR(100), description TEXT, publisher VARCHAR(255), "
            "source_url VARCHAR(500), is_scf BOOLEAN, created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO frameworks (id, code, name) VALUES (1, 'EMEA-ZA', 'POPIA')"))

    ensure_schema(engine)
    ensure_schema(engine)  # second start: nothing to do, no error

    insp = inspect(engine)
    assert {"licence_name", "licence_url", "attribution"} <= {c["name"] for c in insp.get_columns("frameworks")}
    assert insp.has_table("framework_requirements")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM frameworks WHERE id = 1")).scalar() == "POPIA"


def test_bad_date_is_rejected():
    with pytest.raises(ValueError):
        _validate(_file({**SECTION, "effective_from": "1 July 2021"}), "test.json")


# ── database ───────────────────────────────────────────────────────────

def _schema_ready() -> bool:
    insp = inspect(engine)
    return insp.has_table("framework_requirements") and "attribution" in {
        c["name"] for c in insp.get_columns("frameworks")
    }


needs_db = pytest.mark.skipif(not _schema_ready(), reason="run `alembic upgrade head` first (migration 0004)")


@pytest.fixture
def session():
    connection = engine.connect()
    trans = connection.begin()
    s = SessionLocal(bind=connection)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def popia(session):
    fw = session.query(Framework).filter(Framework.code == "EMEA-ZA").first()
    if fw is None:
        pytest.skip("EMEA-ZA (POPIA) not loaded")
    return fw


@needs_db
def test_every_popia_mapping_names_a_section(session, popia):
    refs = {
        r for (r,) in session.query(ControlMapping.mapped_control_id)
        .filter(ControlMapping.framework_id == popia.id)
    }
    assert refs, "no SCF mappings for POPIA"
    unparsed = sorted(r for r in refs if not provision_number(r))
    assert not unparsed, f"SCF refs with no section number: {unparsed[:20]}"


@needs_db
def test_import_links_sections_to_scf_controls(session, popia):
    mapped = (
        session.query(ControlMapping.mapped_control_id)
        .filter(ControlMapping.framework_id == popia.id)
        .first()[0]
    )
    number = provision_number(mapped)
    data = _file(
        {"ref": "ch3", "instrument": "Act", "kind": "chapter", "number": "3", "title": "Conditions"},
        {"ref": f"s{number}", "instrument": "Act", "kind": "section", "number": number,
         "parent_ref": "ch3", "title": "Test", "text": "Text.", "effective_from": "2021-07-01"},
        {"ref": "r4", "instrument": "Regulations", "kind": "regulation", "number": number},
        licence_name="Test licence",
        attribution="Test credit",
    )
    assert import_requirements(session, data) == 3
    assert popia.attribution == "Test credit"

    items = FrameworkService(session).get_requirements(popia.id)
    assert [i["requirement"].ref for i in items] == ["ch3", f"s{number}", "r4"]
    assert items[1]["controls"], "section should pick up its SCF controls"
    assert not items[0]["controls"] and not items[2]["controls"], "only sections match SCF refs"

    # Re-loading replaces: s<number> dropped, ch3 updated.
    data["requirements"] = [{**data["requirements"][0], "title": "Renamed"}]
    import_requirements(session, data)
    items = FrameworkService(session).get_requirements(popia.id)
    assert [(i["requirement"].ref, i["requirement"].title) for i in items] == [("ch3", "Renamed")]


@needs_db
def test_unknown_framework_is_rejected(session):
    with pytest.raises(ValueError, match="not found"):
        import_requirements(session, {"framework_code": "NO-SUCH-FW", "requirements": []})
