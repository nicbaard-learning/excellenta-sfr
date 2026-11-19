"""Find the versioned sheets of an SCF workbook.

SCF names its main sheets after the release ("SCF 2026.3",
"Evidence Request List 2026.3", ...) and renames others between releases.
Importers ask here instead of hard-coding a release, so a new workbook only
needs the new file.
"""

from __future__ import annotations

import re

_SCF_SHEET_RE = re.compile(r"^SCF (\d{4}\.\d+)$")

# The framework metadata sheet, newest name first.
SOURCES_SHEET_NAMES = ("Focal Documents (FD)", "Authoritative Sources")


def scf_sheet_name(wb) -> str:
    """Name of the main control sheet, e.g. "SCF 2026.3"."""
    for name in wb.sheetnames:
        if _SCF_SHEET_RE.match(name.strip()):
            return name
    raise ValueError(f"No 'SCF <version>' sheet in workbook (sheets: {wb.sheetnames})")


def scf_version(wb) -> str:
    """The SCF release of the workbook, e.g. "2026.3"."""
    return _SCF_SHEET_RE.match(scf_sheet_name(wb).strip()).group(1)


def versioned_sheet_name(wb, base: str) -> str | None:
    """Sheet called "<base> <version>", else any sheet starting with ``base``."""
    exact = f"{base} {scf_version(wb)}"
    if exact in wb.sheetnames:
        return exact
    for name in wb.sheetnames:
        if name.lower().startswith(base.lower()):
            return name
    return None


def sources_sheet_name(wb) -> str:
    """Name of the sheet that describes each framework column."""
    for name in SOURCES_SHEET_NAMES:
        if name in wb.sheetnames:
            return name
    raise ValueError(f"No framework sources sheet ({' / '.join(SOURCES_SHEET_NAMES)}) in workbook")


def norm_header(value: object) -> str:
    """Lower-case header with all whitespace collapsed to single spaces."""
    return " ".join(str(value or "").split()).lower()


def parse_scf_ids(raw: object) -> list[str]:
    """Split a cell listing SCF #s (newlines, commas, semicolons) into IDs.

    "NONE" and "N/A ..." mean no ID.
    """
    text = str(raw or "").strip()
    if not text or text.upper() == "NONE" or text.upper().startswith("N/A"):
        return []
    return [p for p in re.split(r"[\s,;]+", text) if p and p.upper() != "NONE"]
