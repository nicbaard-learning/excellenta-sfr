"""Acceptance tests from SFR_RECOMMEND_JURISDICTION_SPEC.md.

Run against a database loaded from the SCF workbook:
    python -m pytest tests/test_recommend_jurisdiction.py -v
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.recommendation_service import clear_recommendation_cache

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_recommendation_cache()


def _recommend(body: dict) -> dict:
    r = client.post("/api/recommend/frameworks", json={**body, "max_controls": 0})
    assert r.status_code == 200, r.text
    return r.json()


def _assert_scoped(result: dict, jurisdiction: str) -> None:
    allowed = {jurisdiction, "EU"} if jurisdiction != "GB" else {jurisdiction}
    for fw in result["recommendations"]:
        assert fw["scope"] in ("jurisdiction", "global"), fw
        codes = set(fw["jurisdiction_codes"])
        if fw["scope"] == "global":
            assert not codes, fw
        else:
            assert codes & allowed, fw


def test_1_za_saas_large_keeps_jurisdiction():
    result = _recommend({"jurisdiction": "ZA", "business_model": "SAAS", "category": "SaaS", "size": "large"})
    codes = {fw["code"] for fw in result["recommendations"]}
    assert "EMEA-ZA" in codes
    assert "jurisdiction=ZA" in result["applied_filters"]
    _assert_scoped(result, "ZA")
    assert not codes & {"US-FedRAMP", "US-CMMC", "FedRAMP", "CMMC"}


def test_2_us_request_has_no_za_frameworks():
    result = _recommend({"jurisdiction": "US", "business_model": "SAAS", "category": "SaaS", "size": "large"})
    assert "jurisdiction=US" in result["applied_filters"]
    assert not any("ZA" in fw["jurisdiction_codes"] for fw in result["recommendations"])
    _assert_scoped(result, "US")


def test_3_gb_returns_uk_and_global_never_us():
    result = _recommend({"jurisdiction": "GB"})
    scopes = {fw["scope"] for fw in result["recommendations"]}
    assert scopes == {"jurisdiction", "global"}
    assert not any("US" in fw["jurisdiction_codes"] for fw in result["recommendations"])
    _assert_scoped(result, "GB")


def test_4_unknown_jurisdiction_is_422_fast():
    start = time.monotonic()
    r = client.post("/api/recommend/frameworks", json={"jurisdiction": "XX"})
    assert r.status_code == 422
    assert time.monotonic() - start < 1
    assert "ZA" in r.json()["detail"]["valid_jurisdictions"]


def test_5_empty_body_is_422_fast():
    start = time.monotonic()
    r = client.post("/api/recommend/frameworks", json={})
    assert r.status_code == 422
    assert time.monotonic() - start < 1


def test_6_catalogue_has_jurisdiction_codes():
    r = client.get("/api/frameworks")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all("jurisdiction_codes" in i for i in items)
    za = client.get("/api/frameworks", params={"jurisdiction": "ZA"}).json()["items"]
    assert [i["code"] for i in za] == ["EMEA-ZA"]


def test_7_every_recommendation_has_scope():
    for body in ({"jurisdiction": "ZA"}, {"business_model": "SAAS"}, {"search": "privacy"}):
        result = _recommend(body)
        assert result["recommendations"]
        assert all(fw["scope"] in ("jurisdiction", "global") for fw in result["recommendations"])


def test_eu_member_gets_eu_frameworks():
    result = _recommend({"jurisdiction": "DE"})
    codes = {fw["code"] for fw in result["recommendations"]}
    assert {"EMEA-DE", "EU-GDPR"} <= codes
    _assert_scoped(result, "DE")


def test_names_come_from_workbook():
    fw = client.get("/api/frameworks", params={"jurisdiction": "ZA"}).json()["items"][0]
    assert fw["name"] == "South Africa - Protection of Personal Information Act (POPIA) (2013)"


def test_related_is_ranked_and_bounded():
    za_id = client.get("/api/frameworks", params={"jurisdiction": "ZA"}).json()["items"][0]["id"]
    related = client.get(f"/api/frameworks/{za_id}/related").json()
    assert 0 < len(related) <= 10
    overlaps = [r["overlap_percent"] for r in related]
    assert overlaps == sorted(overlaps, reverse=True)
