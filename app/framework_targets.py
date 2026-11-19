"""Frameworks we plan to load full provision text for.

The frameworks page shows a progress bar of how many of these have their
text loaded (rows in framework_requirements). Edit this list to change the
target; codes must match frameworks.code.
"""

from __future__ import annotations

# (code, short label shown on the progress card)
TARGET_FRAMEWORKS: list[tuple[str, str]] = [
    ("EMEA-ZA", "POPIA"),
    ("EU-GDPR", "GDPR"),
    ("ISO27001", "ISO 27001"),
    ("NIST-CSF", "NIST CSF"),
    # From SCF 2026.3 this framework is the UK DPA 2018 (FDI emea-gbr-dpa-2018).
    ("EMEA-UK-DPA", "UK DPA (2018)"),
    ("COBIT", "COBIT"),
    ("EU-DORA", "DORA"),
    ("EMEA-UK-CYBER-ESSENTIALS", "Cyber Essentials"),
    ("OWASP-Top10", "OWASP Top 10"),
]


def build_progress(frameworks: list[dict], requirement_counts: dict[int, int]) -> dict:
    """Progress of the target list.

    `frameworks` are dicts with at least id, code and name. Returns
    {"items": [...], "done": n, "total": n, "percent": int}; each item has
    code, label, id (None if the code isn't in the database), name,
    provisions and done.
    """
    by_code = {fw["code"]: fw for fw in frameworks}
    items = []
    for code, label in TARGET_FRAMEWORKS:
        fw = by_code.get(code)
        provisions = requirement_counts.get(fw["id"], 0) if fw else 0
        items.append({
            "code": code,
            "label": label,
            "id": fw["id"] if fw else None,
            "name": fw["name"] if fw else None,
            "provisions": provisions,
            "done": provisions > 0,
        })
    done = sum(1 for i in items if i["done"])
    total = len(items)
    return {
        "items": items,
        "done": done,
        "total": total,
        "percent": round(100 * done / total) if total else 0,
    }
