"""MCP tool get_framework_text: provision lookup and the tool's reply."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from app.database import engine
from app.importers.requirements import REQUIREMENTS_DIR
from app.services.framework_service import match_provisions


@pytest.fixture(scope="module")
def popia_rows():
    data = json.loads((REQUIREMENTS_DIR / "popia.json").read_text(encoding="utf-8"))
    return [
        SimpleNamespace(ref=r["ref"], kind=r["kind"], number=r.get("number"), parent_ref=r.get("parent_ref"))
        for r in data["requirements"]
    ]


def _refs(rows, query):
    return [r.ref for r in match_provisions(rows, query)]


@pytest.mark.parametrize("query", ["s22", "S22", "22", "section 22", "Sec. 22", "22(1)(a)", "s 22"])
def test_section_queries(popia_rows, query):
    assert _refs(popia_rows, query) == ["s22"]


@pytest.mark.parametrize("query", ["r4", "reg 4", "Regulation 4"])
def test_regulation_queries(popia_rows, query):
    assert _refs(popia_rows, query) == ["r4"]


def test_bare_number_is_a_section_not_a_regulation(popia_rows):
    assert _refs(popia_rows, "4") == ["s4"]


def test_chapter_brings_its_parts_and_sections(popia_rows):
    refs = _refs(popia_rows, "ch3")
    assert refs[0] == "ch3"
    assert {"ch3-pA", "cond1", "s8", "s19", "s22"} <= set(refs)
    assert "s1" not in refs and "r1" not in refs


GDPR_ROWS = [
    SimpleNamespace(ref="recitals", kind="part", number=None, parent_ref=None),
    SimpleNamespace(ref="rec71", kind="recital", number="71", parent_ref="recitals"),
    SimpleNamespace(ref="ch4", kind="chapter", number="IV", parent_ref=None),
    SimpleNamespace(ref="art71", kind="article", number="71", parent_ref="ch4"),
]


@pytest.mark.parametrize("query,expected", [
    ("recital 71", ["rec71"]), ("Rec. 71", ["rec71"]), ("rec71", ["rec71"]),
    ("71", ["art71"]), ("Art 71(1)", ["art71"]), ("recitals", ["recitals", "rec71"]),
])
def test_gdpr_recital_and_article_queries(query, expected):
    assert _refs(GDPR_ROWS, query) == expected


@pytest.mark.parametrize("query", ["", "s999", "nonsense", "form99"])
def test_no_match(popia_rows, query):
    assert _refs(popia_rows, query) == []


# ── live database ──────────────────────────────────────────────────────

needs_db = pytest.mark.skipif(
    not inspect(engine).has_table("framework_requirements"), reason="framework_requirements table missing"
)


@needs_db
def test_tool_returns_popia_section_text():
    from app.mcp.server import get_framework_text

    result = get_framework_text(framework_name="POPIA", ref="section 22")
    if result.get("total_provisions") == 0:
        pytest.skip("POPIA text not loaded")
    assert result["framework_code"] == "EMEA-ZA"
    assert result["attribution"] and result["license"]
    [p] = result["provisions"]
    assert p["ref"] == "s22" and "compromise" in p["text"].lower()
    assert isinstance(p["scf_controls"], list)


@needs_db
def test_tool_contents_without_text_and_errors():
    from app.mcp.server import get_framework_text

    toc = get_framework_text(framework_name="POPIA")
    if toc.get("total_provisions") == 0:
        pytest.skip("POPIA text not loaded")
    assert toc["returned"] == toc["total_provisions"]
    assert all("text" not in p for p in toc["provisions"])

    assert "No provision matches" in get_framework_text(framework_name="POPIA", ref="s999")["error"]
    assert "not found" in get_framework_text(framework_name="no such framework xyz")["error"].lower()
    assert "error" in get_framework_text()
