"""Frameworks page progress bar: target list and 'text loaded' status."""

from app.framework_targets import TARGET_FRAMEWORKS, build_progress


def test_build_progress_counts_only_frameworks_with_text():
    frameworks = [
        {"id": 1, "code": "EMEA-ZA", "name": "POPIA"},
        {"id": 2, "code": "EU-GDPR", "name": "GDPR"},
    ]
    p = build_progress(frameworks, {1: 176})
    assert p["total"] == len(TARGET_FRAMEWORKS)
    assert p["done"] == 1
    assert p["percent"] == round(100 / len(TARGET_FRAMEWORKS))
    by_code = {i["code"]: i for i in p["items"]}
    assert by_code["EMEA-ZA"]["done"] and by_code["EMEA-ZA"]["provisions"] == 176
    assert not by_code["EU-GDPR"]["done"] and by_code["EU-GDPR"]["id"] == 2
    assert by_code["COBIT"]["id"] is None  # not in the given list


def test_target_codes_are_unique():
    codes = [c for c, _ in TARGET_FRAMEWORKS]
    assert len(codes) == len(set(codes))


def test_target_codes_exist_in_database():
    from app.database import SessionLocal
    from app.models.framework import Framework

    s = SessionLocal()
    try:
        found = {c for (c,) in s.query(Framework.code).filter(
            Framework.code.in_([c for c, _ in TARGET_FRAMEWORKS])).all()}
    finally:
        s.close()
    missing = [c for c, _ in TARGET_FRAMEWORKS if c not in found]
    assert not missing, f"target codes not in frameworks table: {missing}"


def test_frameworks_page_shows_progress():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/frameworks")
    assert r.status_code == 200
    assert 'id="text-progress"' in r.text
    assert "POPIA" in r.text
    assert "of %d done" % len(TARGET_FRAMEWORKS) in r.text
