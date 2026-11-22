"""Turn an EUR-Lex HTML page into a framework text file (data/requirements/*.json).

EUR-Lex publishes EU regulations as HTML with stable element ids: ``cpt_III``
for a chapter, ``cpt_III.sct_2`` for a section inside it, ``art_13`` for an
article. This module reads a page saved from EUR-Lex (kept locally under
``data/sources/<name>/``, not in git) and writes the JSON file the
requirements importer loads. The wording is copied as is; only the layout
changes (one plain-text block per article, list points on their own lines,
footnotes added under the article that cites them, EUR-Lex's ▼B/▼C1 change
markers left out).

Consolidated texts have no recitals, so an act can name a second saved page,
the Official Journal text, to take them from. Corrigenda to the recitals are
listed per act and applied with an exact match.

Usage (from the repository root):
    python -m app.importers.eurlex gdpr
then load it:
    python -m app.importers.requirements --file data/requirements/gdpr.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from app.importers.requirements import REQUIREMENTS_DIR

SOURCES_DIR = REQUIREMENTS_DIR.parent / "sources"

INDENT = "    "

# Frameworks built from EUR-Lex. "html" is relative to data/sources/.
ACTS: dict[str, dict] = {
    "gdpr": {
        "html": "gdpr/gdpr.html",
        "out": "gdpr.json",
        "framework_code": "EU-GDPR",
        "instrument": "Regulation",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02016R0679-20160504",
        "version_label": "Consolidated text 02016R0679-20160504 (EN 000.002, incl. corrigendum OJ L 127, 23.5.2018)",
        # Art 99(2): applies from 25 May 2018.
        "effective_from": "2018-05-25",
        # The consolidated text has no recitals; they come from the Official Journal text.
        "recitals_html": "gdpr/gdpr-oj.html",
        "recitals_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679",
        "recitals_version_label": "Official Journal text, OJ L 119, 4.5.2016, p. 1",
        # Corrigenda to the recitals (the consolidated text already has the article corrections).
        # Recital number -> [(published wording, corrected wording), ...]
        "recital_corrections": {
            "71": {
                "note": "Corrected by corrigendum OJ L 127, 23.5.2018, p. 2.",
                "replace": [
                    ("for the interests and rights of the data subject and that prevents, inter alia,",
                     "for the interests and rights of the data subject, and prevent, inter alia,"),
                    ("or sexual orientation, or that result in measures having such an effect.",
                     "or sexual orientation, or processing that results in measures having such an effect."),
                ],
            },
        },
        "licence_name": "CC BY 4.0 (EUR-Lex reuse under Commission Decision 2011/833/EU)",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": (
            "© European Union, https://eur-lex.europa.eu, 1998–2026. Regulation (EU) 2016/679: "
            "articles from the consolidated version 02016R0679-20160504 (EN); recitals from the "
            "Official Journal text (OJ L 119, 4.5.2016), with the corrigendum of OJ L 127, 23.5.2018 "
            "applied to recital 71. Reused under Commission Decision 2011/833/EU and CC BY 4.0 "
            "(https://creativecommons.org/licenses/by/4.0/). Split into recitals, chapters and "
            "articles for display; wording otherwise unchanged. Only the Official Journal text is "
            "authentic."
        ),
    },
}

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {"p", "div", "table", "tbody", "tr", "td", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "template", "i"}
# EUR-Lex furniture that isn't part of the legal text.
_SKIP_CLASSES = {"modref", "arrow", "anchorarrow", "eli-title", "title-article-norm"}
# Inline change markers: ►B, ►C1, ►M2, ◄
_CHANGE_MARKER = re.compile(r"[►▼◄](?:\s*[A-Z]\d*)?")


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def iter(self):
        yield self
        for ch in self.children:
            if isinstance(ch, Node):
                yield from ch.iter()

    def child_with_class(self, cls: str) -> Node | None:
        return next((c for c in self.children if isinstance(c, Node) and cls in c.classes), None)


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag):
        # Close the nearest open element with this tag; ignore strays.
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _skipped(node: Node) -> bool:
    return node.tag in _SKIP_TAGS or bool(node.classes & _SKIP_CLASSES)


def inline_text(node: Node) -> str:
    """Text of a node with whitespace kept (cleaned by the caller)."""
    parts = []
    for ch in node.children:
        if isinstance(ch, str):
            parts.append(ch)
        elif not _skipped(ch):
            parts.append(_inline_child(ch))
    return "".join(parts)


def _inline_child(node: Node) -> str:
    if node.tag == "a" and re.fullmatch(r"(src\.)?E\d+", node.attrs.get("id", "")):
        return _clean(inline_text(node))  # footnote number: "(1)", not "( 1 )"
    text = inline_text(node)
    if _CHANGE_MARKER.fullmatch(_clean(text)):
        return " "  # EUR-Lex's ►C1 … ◄ around corrected wording
    return text


def _attach(label: str, lines: list[str], indent: str) -> list[str]:
    if not lines:
        return [indent + label]
    return [f"{indent}{label} {lines[0].lstrip()}", *lines[1:]]


def render(node: Node, indent: str = "") -> list[str]:
    """Plain-text lines for a block of EUR-Lex legal text."""
    lines: list[str] = []
    buf: list[str] = []
    label: str | None = None

    def flush():
        text = _clean("".join(buf))
        buf.clear()
        if text:
            lines.append(indent + text)

    for ch in node.children:
        if isinstance(ch, str):
            buf.append(ch)
            continue
        if _skipped(ch):
            continue
        if "grid-container" in ch.classes:
            # A list point: "(a)" in column 1, its text (maybe with sub-points) in column 2.
            flush()
            col1, col2 = ch.child_with_class("grid-list-column-1"), ch.child_with_class("grid-list-column-2")
            point = _clean(inline_text(col1)) if col1 else ""
            body = render(col2, indent + INDENT) if col2 else []
            lines.extend(_attach(point, body, indent) if point else body)
        elif ch.tag == "span" and "no-parag" in ch.classes:
            # Paragraph number ("1.") followed by the paragraph's block.
            flush()
            label = _clean(inline_text(ch))
        elif ch.tag in _BLOCK:
            flush()
            if label:
                lines.extend(_attach(label, render(ch, indent + INDENT), indent))
                label = None
            else:
                lines.extend(render(ch, indent))
        else:
            buf.append(_inline_child(ch))
    flush()
    if label:
        lines.append(indent + label)
    return lines


def _roman_to_int(roman: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for i, c in enumerate(roman):
        v = values[c]
        total += -v if i + 1 < len(roman) and values[roman[i + 1]] > v else v
    return total


def _heading(div: Node, cls: str) -> str:
    p = div.child_with_class(cls)
    return _clean(inline_text(p)) if p else ""


def _footnotes(root: Node) -> dict[str, str]:
    """Footnote id ("E0001") -> "(1) text"."""
    notes = {}
    for p in root.iter():
        if p.tag == "p" and "footnote" in p.classes:
            a = next((c for c in p.children if isinstance(c, Node) and c.tag == "a"), None)
            if a is not None and a.attrs.get("id"):
                notes[a.attrs["id"]] = _clean(inline_text(p))
    return notes


def build_requirements(html: str, act: dict) -> list[dict]:
    """Chapters, sections and articles in document order, as importer items."""
    root = parse_html(html)
    notes = _footnotes(root)
    instrument = act["instrument"]
    items: list[dict] = []

    def walk(node: Node, parent_ref: str | None):
        for ch in node.children:
            if not isinstance(ch, Node):
                continue
            el_id = ch.attrs.get("id", "")
            m_cpt = re.fullmatch(r"cpt_([IVXLC]+)", el_id)
            m_sct = re.fullmatch(r"cpt_([IVXLC]+)\.sct_(\d+)", el_id)
            m_art = re.fullmatch(r"art_(\d+)", el_id)
            if m_cpt:
                ref = f"ch{_roman_to_int(m_cpt.group(1))}"
                items.append({
                    "ref": ref, "instrument": instrument, "kind": "chapter",
                    "number": m_cpt.group(1), "title": _heading(ch, "title-division-2"),
                })
                walk(ch, ref)
            elif m_sct:
                ref = f"ch{_roman_to_int(m_sct.group(1))}-s{m_sct.group(2)}"
                title = _heading(ch, "title-division-2")
                items.append({
                    "ref": ref, "instrument": instrument, "kind": "part", "number": None,
                    "title": f"Section {m_sct.group(2)}: {title}" if title else f"Section {m_sct.group(2)}",
                    "parent_ref": parent_ref,
                })
                walk(ch, ref)
            elif m_art:
                number = m_art.group(1)
                title_div = next(
                    (c for c in ch.children if isinstance(c, Node) and c.attrs.get("id") == f"art_{number}.tit_1"),
                    None,
                )
                text = "\n".join(render(ch))
                cited = [
                    a.attrs["id"][len("src."):] for a in ch.iter()
                    if a.tag == "a" and a.attrs.get("id", "").startswith("src.")
                ]
                if cited:
                    text += "\n\n" + "\n".join(notes[c] for c in cited if c in notes)
                items.append({
                    "ref": f"art{number}", "instrument": instrument, "kind": "article",
                    "number": number, "parent_ref": parent_ref,
                    "title": _clean(inline_text(title_div)) if title_div else None,
                    "text": text,
                    "source_url": f"{act['source_url']}#art_{number}",
                })
            else:
                walk(ch, parent_ref)

    body = next((n for n in root.iter() if n.attrs.get("id") == "docHtml"), root)
    walk(body, None)
    return items


def _oj_notes(root: Node) -> dict[str, str]:
    """Official Journal footnotes: citing anchor id ("ntc4-…") -> "(4) text"."""
    notes = {}
    for p in root.iter():
        if p.tag == "p" and "oj-note" in p.classes:
            a = next((c for c in p.children if isinstance(c, Node) and c.tag == "a"), None)
            if a is not None and a.attrs.get("id", "").startswith("ntr"):
                notes["ntc" + a.attrs["id"][3:]] = _clean(inline_text(p))
    return notes


def build_recitals(html: str, act: dict) -> list[dict]:
    """The recitals from an Official Journal page, under a "Recitals" heading.

    Applies act["recital_corrections"]; raises if a correction's published
    wording isn't found exactly once (the source isn't the text we expect).
    """
    root = parse_html(html)
    notes = _oj_notes(root)
    corrections = act.get("recital_corrections", {})
    instrument = act["instrument"]
    items = [{"ref": "recitals", "instrument": instrument, "kind": "part", "number": None, "title": "Recitals"}]
    for div in root.iter():
        m = re.fullmatch(r"rct_(\d+)", div.attrs.get("id", ""))
        if not m:
            continue
        number = m.group(1)
        # Cells of the recital's own first row (not of any table nested inside the text).
        row = next((n for n in div.iter() if n.tag == "tr"), None)
        cells = [c for c in row.children if isinstance(c, Node) and c.tag == "td"] if row else []
        if len(cells) < 2:
            raise ValueError(f"recital {number}: unexpected layout")
        text = "\n".join(line.strip() for line in render(cells[1]))
        status_note = None
        fix = corrections.get(number)
        if fix:
            for old, new in fix["replace"]:
                if text.count(old) != 1:
                    raise ValueError(f"recital {number}: published wording not found once: {old!r}")
                text = text.replace(old, new)
            status_note = fix["note"]
        cited = [a.attrs["id"] for a in div.iter() if a.tag == "a" and a.attrs.get("id", "").startswith("ntc")]
        if cited:
            text += "\n\n" + "\n".join(notes[c] for c in cited if c in notes)
        items.append({
            "ref": f"rec{number}", "instrument": instrument, "kind": "recital", "number": number,
            "parent_ref": "recitals", "title": None, "text": text, "status_note": status_note,
            "version_label": act["recitals_version_label"],
            "source_url": f"{act['recitals_url']}#rct_{number}",
        })
    missing = set(corrections) - {i["number"] for i in items}
    if missing:
        raise ValueError(f"corrected recitals not in the page: {sorted(missing)}")
    return items


def build_file(html: str, act: dict, recitals_html: str | None = None) -> dict:
    requirements = build_requirements(html, act)
    if recitals_html is not None:
        requirements = build_recitals(recitals_html, act) + requirements
    return {
        "framework_code": act["framework_code"],
        "licence_name": act["licence_name"],
        "licence_url": act["licence_url"],
        "attribution": act["attribution"],
        "defaults": {
            act["instrument"]: {
                "source_url": act["source_url"],
                "version_label": act["version_label"],
                "effective_from": act["effective_from"],
            }
        },
        "requirements": requirements,
    }


def read_sources(act: dict) -> tuple[str, str | None]:
    """The saved page(s) for an act: (main page, recitals page or None)."""
    html = (SOURCES_DIR / act["html"]).read_text(encoding="utf-8")
    recitals = None
    if act.get("recitals_html"):
        recitals = (SOURCES_DIR / act["recitals_html"]).read_text(encoding="utf-8")
    return html, recitals


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a framework text file from a saved EUR-Lex page.")
    parser.add_argument("act", choices=sorted(ACTS))
    args = parser.parse_args()

    act = ACTS[args.act]
    html, recitals_html = read_sources(act)
    data = build_file(html, act, recitals_html)
    out = REQUIREMENTS_DIR / act["out"]
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for item in data["requirements"]:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    print(f"Wrote {out} ({', '.join(f'{n} {k}s' for k, n in kinds.items())})")


if __name__ == "__main__":
    main()
