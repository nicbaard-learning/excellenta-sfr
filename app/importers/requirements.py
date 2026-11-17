"""Load a framework's own provisions (sections, regulations, articles) from JSON.

The SCF workbook only names the provisions it maps to. The provision text
comes from the official source and is kept in ``data/requirements/*.json``,
one file per framework::

    {
      "framework_code": "EMEA-ZA",
      "licence_name": "...", "licence_url": "...", "attribution": "...",
      "defaults": {"Act": {"source_url": "...", "version_label": "...",
                           "effective_from": "2020-07-01"}},
      "requirements": [
        {"ref": "ch3", "instrument": "Act", "kind": "chapter", "number": "3",
         "title": "Conditions for lawful processing"},
        {"ref": "s22", "instrument": "Act", "kind": "section", "number": "22",
         "parent_ref": "ch3", "title": "...", "text": "...",
         "version_label": "...", "effective_from": "2021-07-01",
         "status": "in_force", "status_note": null, "source_url": "..."}
      ]
    }

The file is the source of truth: re-loading it updates every provision,
adds new ones and removes provisions no longer in the file. List order is
display order.

Usage:
    python -m app.importers.requirements --file data/requirements/popia.json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.framework import Framework
from app.models.requirement import FrameworkRequirement

logger = logging.getLogger(__name__)

REQUIREMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "requirements"

KINDS = {
    "chapter", "part", "condition", "section", "regulation", "article", "recital", "schedule", "form",
}
# Kinds shown as headings on the framework page rather than as provisions.
HEADING_KINDS = {"chapter", "part", "condition"}
STATUSES = {"in_force", "not_in_force", "pending_amendment", "repealed"}
FIELDS = (
    "instrument", "kind", "number", "parent_ref", "title", "text",
    "version_label", "status", "status_note", "source_url",
)


def _validate(data: dict, source: str) -> list[dict]:
    if not isinstance(data, dict) or not str(data.get("framework_code") or "").strip():
        raise ValueError(f"{source}: missing framework_code")
    items = data.get("requirements")
    if not isinstance(items, list):
        raise ValueError(f"{source}: 'requirements' must be a list")
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError(f"{source}: 'defaults' must be an object")
    # Per-instrument defaults ({"Act": {...}, "Regulations": {...}}) fill fields an item leaves out.
    items = [{**defaults.get(item.get("instrument"), {}), **item} for item in items]

    seen: set[str] = set()
    for i, item in enumerate(items):
        where = f"{source}: requirements[{i}]"
        for key in ("ref", "instrument", "kind"):
            if not str(item.get(key) or "").strip():
                raise ValueError(f"{where}: missing {key}")
        ref = item["ref"].strip()
        if ref in seen:
            raise ValueError(f"{where}: duplicate ref {ref!r}")
        seen.add(ref)
        if item["kind"] not in KINDS:
            raise ValueError(f"{where}: unknown kind {item['kind']!r}")
        if item.get("status", "in_force") not in STATUSES:
            raise ValueError(f"{where}: unknown status {item['status']!r}")
        if item.get("effective_from"):
            date.fromisoformat(item["effective_from"])

    for i, item in enumerate(items):
        parent = item.get("parent_ref")
        if parent and parent not in seen:
            raise ValueError(f"{source}: requirements[{i}]: parent_ref {parent!r} not in file")
    return items


def import_requirements(session: Session, data: dict, source: str = "<data>") -> int:
    """Apply one framework's provisions and licence fields. Returns the number of provisions.

    Raises ValueError for an invalid file or an unknown framework code. The
    caller commits.
    """
    items = _validate(data, source)
    code = data["framework_code"].strip()
    framework = session.query(Framework).filter(Framework.code == code).first()
    if framework is None:
        raise ValueError(f"{source}: framework {code!r} not found")

    for key in ("licence_name", "licence_url", "attribution"):
        if key in data:
            setattr(framework, key, data[key])

    existing = {
        r.ref: r
        for r in session.query(FrameworkRequirement).filter(
            FrameworkRequirement.framework_id == framework.id
        )
    }
    for order, item in enumerate(items):
        ref = item["ref"].strip()
        row = existing.pop(ref, None)
        if row is None:
            row = FrameworkRequirement(framework_id=framework.id, ref=ref)
            session.add(row)
        for key in FIELDS:
            setattr(row, key, item.get(key))
        row.status = item.get("status") or "in_force"
        row.effective_from = (
            date.fromisoformat(item["effective_from"]) if item.get("effective_from") else None
        )
        row.display_order = order

    for stale in existing.values():
        session.delete(stale)
    session.flush()
    logger.info("%s: %d provisions loaded, %d removed", code, len(items), len(existing))
    return len(items)


def import_requirement_file(session: Session, path: Path | str) -> int:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        return import_requirements(session, json.load(fh), source=path.name)


def import_requirement_files(session: Session, directory: Path | str = REQUIREMENTS_DIR) -> int:
    """Load every ``*.json`` file in ``directory``. Returns the total number of provisions."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    return sum(import_requirement_file(session, p) for p in sorted(directory.glob("*.json")))


def main() -> None:
    from app.database import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Load framework provisions from a JSON file.")
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        import_requirement_file(session, args.file)
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
