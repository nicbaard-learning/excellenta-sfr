"""EUR-Lex page → framework text file (app/importers/eurlex.py).

The parsing tests use a small sample. The GDPR tests read the page saved
from EUR-Lex (data/sources/gdpr/gdpr.html, not in git) and skip without it.
"""

from __future__ import annotations

import json

import pytest

from app.importers.eurlex import ACTS, SOURCES_DIR, build_file, build_recitals, build_requirements, read_sources
from app.importers.requirements import REQUIREMENTS_DIR, _validate

SAMPLE = """
<div id="docHtml">
 <p class="arrow">▼B</p>
 <div id="cpt_II">
  <p class="title-division-1"><span class="italics">CHAPTER II</span></p>
  <p class="title-division-2"><span class="boldface"><span class="italics">Principles</span></span></p>
  <div class="eli-subdivision" id="art_5">
   <p class="title-article-norm">Article 5</p>
   <div class="eli-title" id="art_5.tit_1"><p class="stitle-article-norm">Principles relating to processing</p></div>
   <div class="norm">
    <span class="no-parag">1.&nbsp;&nbsp;</span>
    <div class="norm inline-element">
     <p class="norm inline-element">Personal data shall be:</p>
     <div class="grid-container grid-list">
      <div class="list grid-list-column-1"><span>(a)&nbsp;</span></div>
      <div class="grid-list-column-2"><p class="norm">processed lawfully;</p></div>
     </div>
     <p class="modref"><a title="32016R0679R(02)">▼C1</a><a class="anchorarrow" id="C1-1"><i class="fa"></i></a></p>
     <div class="grid-container grid-list">
      <div class="list grid-list-column-1"><span>(b)&nbsp;</span></div>
      <div class="grid-list-column-2">
       <p class="norm">collected for:</p>
       <div class="grid-container grid-list">
        <div class="list grid-list-column-1"><span>(i)&nbsp;</span></div>
        <div class="grid-list-column-2"><p class="norm">a service&nbsp;(<a id="src.E0001">
          <span class="superscript">1</span>
        </a>);</p></div>
       </div>
      </div>
     </div>
    </div>
   </div>
   <div class="norm">
    <span class="no-parag">2.&nbsp;&nbsp;</span>
    <div class="norm inline-element">The controller shall be responsible.</div>
   </div>
  </div>
  <div id="cpt_II.sct_1">
   <p class="title-division-1">Section 1</p>
   <p class="title-division-2"><span class="boldface">Transparency</span></p>
   <div class="eli-subdivision" id="art_12">
    <p class="title-article-norm">Article 12</p>
    <div class="eli-title" id="art_12.tit_1"><p class="stitle-article-norm">Transparent information</p></div>
    <p class="norm"><span><a title="32016R0679R(02): REPLACED"><span class="boldface">►C1</span></a><a class="anchorarrow"><i></i></a></span>&nbsp;Corrected words.<span class="boldface">&nbsp;◄ </span> Original words.</p>
   </div>
  </div>
 </div>
</div>
<p class="footnote">(<a id="E0001">
  <span class="superscript">1</span>
 </a>)&nbsp;Directive (EU) 2015/1535 (OJ L 241, 17.9.2015, p.&nbsp;1).</p>
"""


def test_sample_structure():
    items = build_requirements(SAMPLE, ACTS["gdpr"])
    assert [(i["ref"], i["kind"], i.get("parent_ref")) for i in items] == [
        ("ch2", "chapter", None),
        ("art5", "article", "ch2"),
        ("ch2-s1", "part", "ch2"),
        ("art12", "article", "ch2-s1"),
    ]
    assert items[0]["number"] == "II" and items[0]["title"] == "Principles"
    assert items[2]["title"] == "Section 1: Transparency"
    assert items[1]["title"] == "Principles relating to processing"
    assert items[1]["source_url"].endswith("#art_5")


def test_sample_text_layout():
    art5 = build_requirements(SAMPLE, ACTS["gdpr"])[1]
    assert art5["text"] == (
        "1. Personal data shall be:\n"
        "    (a) processed lawfully;\n"
        "    (b) collected for:\n"
        "        (i) a service (1);\n"
        "2. The controller shall be responsible.\n"
        "\n"
        "(1) Directive (EU) 2015/1535 (OJ L 241, 17.9.2015, p. 1)."
    )
    assert "▼" not in art5["text"] and "C1" not in art5["text"]


def test_sample_inline_change_markers_dropped():
    art12 = build_requirements(SAMPLE, ACTS["gdpr"])[3]
    assert art12["text"] == "Corrected words. Original words."


def test_sample_file_is_valid():
    data = build_file(SAMPLE, ACTS["gdpr"])
    assert data["framework_code"] == "EU-GDPR"
    items = _validate(data, "sample")
    assert all(i["effective_from"] == "2018-05-25" for i in items)


# ── the saved GDPR page ───────────────────────────────────────────────

OJ_SAMPLE = """
<div id="pbl_1">
 <div class="eli-subdivision" id="rct_70"><table><tbody><tr>
  <td><p class="oj-normal">(70)</p></td>
  <td><p class="oj-normal">Plain recital&nbsp;<a id="ntc4-X-E0004">(<span class="oj-super oj-note-tag">4</span>)</a>.</p></td>
 </tr></tbody></table></div>
 <div class="eli-subdivision" id="rct_71"><table><tbody><tr>
  <td><p class="oj-normal">(71)</p></td>
  <td><p class="oj-normal">First paragraph.</p>
   <p class="oj-normal">for the interests and rights of the data subject and that prevents, inter alia, effects
   or sexual orientation, or that result in measures having such an effect. End.</p></td>
 </tr></tbody></table></div>
</div>
<p class="oj-note"><a id="ntr4-X-E0004">(<span class="oj-super">4</span>)</a>&nbsp;&nbsp;<a>OJ C 229, 31.7.2012, p. 90</a>.</p>
"""


def test_sample_recitals_with_correction_and_note():
    items = build_recitals(OJ_SAMPLE, ACTS["gdpr"])
    assert [(i["ref"], i["kind"], i.get("parent_ref")) for i in items] == [
        ("recitals", "part", None), ("rec70", "recital", "recitals"), ("rec71", "recital", "recitals"),
    ]
    assert items[1]["text"] == "Plain recital (4).\n\n(4) OJ C 229, 31.7.2012, p. 90."
    assert items[1]["status_note"] is None
    assert items[2]["text"] == (
        "First paragraph.\n"
        "for the interests and rights of the data subject, and prevent, inter alia, effects "
        "or sexual orientation, or processing that results in measures having such an effect. End."
    )
    assert "23.5.2018" in items[2]["status_note"]
    assert items[2]["source_url"].endswith("32016R0679#rct_71")


def test_recital_with_nested_table_uses_its_own_text_cell():
    html = """
    <div class="eli-subdivision" id="rct_5"><table><tbody><tr>
     <td><p class="oj-normal">(5)</p></td>
     <td><p class="oj-normal">Recital text.</p>
      <table><tbody><tr><td><p>inner A</p></td><td><p>inner B</p></td></tr></tbody></table></td>
    </tr></tbody></table></div>
    """
    act = {**ACTS["gdpr"], "recital_corrections": {}}
    rec = build_recitals(html, act)[1]
    assert rec["number"] == "5"
    assert rec["text"].startswith("Recital text.")


def test_recital_correction_must_match_exactly():
    with pytest.raises(ValueError, match="recital 71"):
        build_recitals(OJ_SAMPLE.replace("and that prevents", "and which prevents"), ACTS["gdpr"])


GDPR_PAGES = [SOURCES_DIR / ACTS["gdpr"]["html"], SOURCES_DIR / ACTS["gdpr"]["recitals_html"]]


@pytest.fixture(scope="module")
def gdpr():
    missing = [str(p) for p in GDPR_PAGES if not p.exists()]
    if missing:
        pytest.skip(f"not saved: {missing}")
    html, recitals = read_sources(ACTS["gdpr"])
    return build_file(html, ACTS["gdpr"], recitals)


def test_gdpr_has_every_recital(gdpr):
    recitals = [r for r in gdpr["requirements"] if r["kind"] == "recital"]
    assert [r["number"] for r in recitals] == [str(n) for n in range(1, 174)]
    assert gdpr["requirements"][0]["ref"] == "recitals"
    by_ref = {r["ref"]: r for r in recitals}
    assert by_ref["rec1"]["text"].startswith("The protection of natural persons in relation to the processing")
    assert "data subject, and prevent, inter alia," in by_ref["rec71"]["text"]
    assert "or processing that results in measures having such an effect." in by_ref["rec71"]["text"]
    assert by_ref["rec71"]["status_note"]
    assert sum(1 for r in recitals if r["status_note"]) == 1


def test_gdpr_has_every_chapter_section_and_article(gdpr):
    reqs = gdpr["requirements"]
    articles = [r for r in reqs if r["kind"] == "article"]
    assert [a["number"] for a in articles] == [str(n) for n in range(1, 100)]
    assert [r["number"] for r in reqs if r["kind"] == "chapter"] == [
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"
    ]
    assert sum(r["kind"] == "part" for r in reqs) == 16  # 15 sections + the Recitals heading
    assert all(a["title"] and a["text"] for a in articles)
    _validate(gdpr, "gdpr")


def test_gdpr_text_is_clean(gdpr):
    by_ref = {r["ref"]: r for r in gdpr["requirements"]}
    assert by_ref["art1"]["text"].startswith("1. This Regulation lays down rules relating to the protection")
    assert by_ref["art32"]["title"] == "Security of processing"
    assert by_ref["art99"]["text"].endswith("2. It shall apply from 25 May 2018.")
    # Art 37(1)(c) sits after a ▼C1 marker: the point stays, the marker goes.
    assert "    (c) the core activities of the controller" in by_ref["art37"]["text"]
    # Art 4(25) cites footnote 1, which is added under the article.
    assert "(1) Directive (EU) 2015/1535" in by_ref["art4"]["text"]
    for r in gdpr["requirements"]:
        for marker in ("▼", "►", "◄", "  )", "( "):
            assert marker not in (r.get("text") or "") + (r.get("title") or ""), (r["ref"], marker)


def test_gdpr_article_32_layout(gdpr):
    text = next(r for r in gdpr["requirements"] if r["ref"] == "art32")["text"]
    lines = text.split("\n")
    assert lines[0].startswith("1. Taking into account the state of the art")
    assert [l.strip()[:3] for l in lines[1:5]] == ["(a)", "(b)", "(c)", "(d)"]
    assert all(l.startswith("    (") for l in lines[1:5])
    assert [l[:2] for l in lines[5:]] == ["2.", "3.", "4."]


def test_every_scf_gdpr_ref_names_an_article(gdpr):
    from app.database import SessionLocal
    from app.models.framework import Framework
    from app.models.mapping import ControlMapping
    from app.services.framework_service import provision_number

    session = SessionLocal()
    try:
        fw = session.query(Framework).filter(Framework.code == "EU-GDPR").first()
        if fw is None:
            pytest.skip("EU-GDPR not in the database")
        refs = {r for (r,) in session.query(ControlMapping.mapped_control_id).filter(
            ControlMapping.framework_id == fw.id)}
    finally:
        session.close()
    assert refs, "no SCF mappings for EU-GDPR"
    articles = {r["number"] for r in gdpr["requirements"] if r["kind"] == "article"}
    unmatched = sorted(r for r in refs if provision_number(r) not in articles)
    assert not unmatched, f"SCF refs that don't point at a GDPR article: {unmatched[:20]}"


def test_shipped_gdpr_file_matches_source(gdpr):
    path = REQUIREMENTS_DIR / ACTS["gdpr"]["out"]
    if not path.exists():
        pytest.skip("data/requirements/gdpr.json not built yet (python -m app.importers.eurlex gdpr)")
    # Fails until the file is rebuilt after a parser or source change: re-run the command above.
    assert json.loads(path.read_text(encoding="utf-8")) == gdpr
