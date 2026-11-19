"""SCF CC BY-ND 4.0 attribution: shared text, scf.json in step, exports and pages."""

import json
import re
from pathlib import Path

import pytest

from app import scf_attribution
from app.database import SessionLocal
from app.models.framework import Framework
from app.services.oscal_service import OscalService

ROOT = Path(__file__).resolve().parent.parent


def test_scf_json_matches_shared_attribution():
    data = json.loads((ROOT / "data" / "requirements" / "scf.json").read_text(encoding="utf-8"))
    assert data["attribution"] == scf_attribution.ATTRIBUTION
    assert data["licence_url"] == scf_attribution.LICENCE_URL
    assert "No changes have been made" in data["attribution"]
    assert "by-nd/4.0" in data["licence_url"]


def test_oscal_link_and_remarks():
    link = scf_attribution.oscal_licence_link()
    assert link["rel"] == "license" and "by-nd/4.0" in link["href"]
    assert scf_attribution.NO_CHANGES in scf_attribution.oscal_remarks()


def _check_metadata(meta):
    links = meta["links"]
    assert any(l["rel"] == "license" and "by-nd/4.0" in l["href"] for l in links)
    assert scf_attribution.NO_CHANGES in meta["remarks"]


def test_all_three_oscal_exports_carry_the_licence():
    session = SessionLocal()
    try:
        scf = session.query(Framework).filter(Framework.is_scf.is_(True)).first()
        if scf is None:
            pytest.skip("no SCF framework in the database")
        svc = OscalService(session)
        _check_metadata(svc.export_catalog(domain_code="GOV")["catalog"]["metadata"])
        _check_metadata(svc.export_profile(framework_id=scf.id)["profile"]["metadata"])
        _check_metadata(
            svc.export_assessment_results(framework_id=scf.id)["assessment-results"]["metadata"]
        )
    finally:
        session.close()


def test_scf_text_is_not_shortened_in_outputs():
    """SCF text must be passed through whole, or 'no changes' would be untrue."""
    pat = re.compile(
        r"\b(description|control_question|solution|val|value|objectives_text)\[:\d+\]"
    )
    files = [
        "app/mcp/server.py",
        "app/services/oscal_service.py",
        "app/services/evidence_service.py",
        "app/services/maturity_service.py",
        "app/services/recommendation_service.py",
        "app/services/risk_intelligence_service.py",
        "app/services/translation_service.py",
        "app/templates/control_detail.html",
    ]
    for f in files:
        text = (ROOT / f).read_text(encoding="utf-8")
        assert not pat.search(text), f


def test_about_page_shows_licence_and_no_changes():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/about")
    assert r.status_code == 200
    assert scf_attribution.LICENCE_URL in r.text
    assert "CC BY-ND 4.0" in r.text
    assert scf_attribution.NO_CHANGES in r.text


def test_mcp_tool_results_carry_the_licence():
    from app.mcp.server import compare_frameworks

    res = compare_frameworks()  # no ids: returns an error dict without touching the DB
    assert "error" in res
    assert res["license"]["url"] == scf_attribution.LICENCE_URL
    assert scf_attribution.NO_CHANGES in res["license"]["attribution"]


def test_api_json_objects_get_licence_body_and_headers_lists_get_headers_only():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.scf_license_middleware import SCFLicenseMiddleware

    app = FastAPI()
    app.add_middleware(SCFLicenseMiddleware)

    @app.get("/api/obj")
    def obj():
        return {"a": 1}

    @app.get("/api/list")
    def lst():
        return [1, 2]

    @app.get("/api/oscal/x")
    def oscal():
        return {"catalog": {}}

    @app.get("/other")
    def other():
        return {"a": 1}

    c = TestClient(app)
    r = c.get("/api/obj")
    assert r.json()["a"] == 1 and r.json()["license"]["url"] == scf_attribution.LICENCE_URL
    assert 'rel="license"' in r.headers["link"]
    assert scf_attribution.NO_CHANGES in r.headers["x-scf-attribution"]
    assert int(r.headers["content-length"]) == len(r.content)
    r = c.get("/api/list")
    assert r.json() == [1, 2] and 'rel="license"' in r.headers["link"]
    assert "license" not in c.get("/api/oscal/x").json()
    r = c.get("/other")
    assert "license" not in r.json() and "link" not in r.headers


def test_print_roadmap_template_has_credit_slot():
    html = (ROOT / "app" / "templates" / "roadmap_print.html").read_text(encoding="utf-8")
    assert "{{ scf_attribution }}" in html
