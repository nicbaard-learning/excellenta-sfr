"""Framework name resolver – maps natural-language names to internal framework IDs.

Supports:
- Exact code matches (e.g. "ISO27001", "PCI-DSS")
- Common aliases / display names (e.g. "ISO 27001", "PCI DSS", "NIST CSF")
- Case-insensitive fuzzy code/name lookups
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.framework import Framework

logger = logging.getLogger(__name__)

# ── Common known aliases ───────────────────────────────────────────────
# These map display names / common variants to internal framework codes.
KNOWN_ALIASES: dict[str, str] = {
    # ISO
    "iso 27001": "ISO27001",
    "iso27001": "ISO27001",
    "iso/iec 27001": "ISO27001",
    "iso 27002": "ISO27002",
    "iso27002": "ISO27002",
    "iso/iec 27002": "ISO27002",
    "iso 27701": "ISO27701",
    "iso27701": "ISO27701",
    "iso 22301": "ISO22301",
    "iso22301": "ISO22301",
    "iso 9001": "ISO9001",
    "iso9001": "ISO9001",
    "iso 14001": "ISO14001",
    "iso14001": "ISO14001",
    "iso 31000": "ISO31000",
    "iso31000": "ISO31000",
    # PCI
    "pci dss": "PCI-DSS",
    "pci-dss": "PCI-DSS",
    "pci_dss": "PCI-DSS",
    "pci": "PCI-DSS",
    "pci dss v4": "PCI-DSS",
    "payment card industry": "PCI-DSS",
    "pci data security standard": "PCI-DSS",
    # NIST
    "nist csf": "NIST-CSF",
    "nist-csf": "NIST-CSF",
    "nist_csf": "NIST-CSF",
    "nist cybersecurity framework": "NIST-CSF",
    "nist sp 800-53": "NIST-800-53",
    "nist 800-53": "NIST-800-53",
    "nist-sp-800-53": "NIST-800-53",
    "nist 800-53 rev 5": "NIST-800-53",
    "nist 800-171": "NIST-800-171",
    "nist-sp-800-171": "NIST-800-171",
    "nist-sp-800-171": "NIST-800-171",
    "nist 800-171a": "NIST-800-171A",
    # Privacy
    "gdpr": "GDPR",
    "popia": "EMEA-ZA",
    "popi": "EMEA-ZA",
    "ccpa": "CCPA",
    "lgpd": "LGPD",
    "hipaa": "HIPAA",
    "hi trust": "HITRUST",
    "hitrust": "HITRUST",
    # Other common
    "cobit": "COBIT",
    "coso": "COSO",
    "soc 2": "AICPA-TSC",
    "soc2": "AICPA-TSC",
    "aicpa tsc": "AICPA-TSC",
    "aicpa-tsc": "AICPA-TSC",
    "aicpa_tsc": "AICPA-TSC",
    "soc 1": "SOC1",
    "soc1": "SOC1",
    "sox": "SOX",
    "sarbanes-oxley": "SOX",
    "fedramp": "FedRAMP",
    "fed ramp": "FedRAMP",
    "cis controls": "CIS-CSC",
    "cis": "CIS-CSC",
    "cis critical security controls": "CIS-CSC",
    "bcm": "BCM",
    "business continuity": "BCM",
    "iso 27001:2022": "ISO27001",
    "iso 27001:2013": "ISO27001",
    "cis top 18": "CIS-CSC",
    "ffiec": "FFIEC",
    "apra cps 234": "APRA-CPS-234",
    "apra cps 230": "APRA-CPS-230",
    "nist privacy framework": "NIST-Privacy",
    "nist privacy": "NIST-Privacy",
}


def _normalize(name: str) -> str:
    """Normalize a framework name for lookup: lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def resolve_framework_id(
    session: Session,
    framework_name: str | None = None,
    framework_id: int | None = None,
    *,
    strict: bool = True,
) -> int | None:
    """Resolve a framework to its internal ID.

    Priority:
    1. If *framework_id* is provided, return it directly.
    2. If *framework_name* is provided, try known aliases, then DB lookup.

    Returns *None* if no match found.
    If *strict* is *True* (default), logs a warning on no match.
    """
    if framework_id is not None:
        return framework_id

    if not framework_name:
        return None

    normalized = _normalize(framework_name)

    # 1. Check known aliases
    if normalized in KNOWN_ALIASES:
        code = KNOWN_ALIASES[normalized]
        fw = session.query(Framework).filter(Framework.code == code).first()
        if fw:
            return fw.id
        logger.warning("Alias '%s' resolved to code '%s' but no DB match found", framework_name, code)
        # Fall through to DB lookup in case the code doesn't exist

    # 2. Try exact code match (case-insensitive)
    fw = (
        session.query(Framework)
        .filter(Framework.code.ilike(normalized))
        .first()
    )
    if fw:
        return fw.id

    # 3. Try name match (case-insensitive)
    fw = (
        session.query(Framework)
        .filter(Framework.name.ilike(normalized))
        .first()
    )
    if fw:
        return fw.id

    # 4. Try substring search on code
    fw = (
        session.query(Framework)
        .filter(Framework.code.ilike(f"%{normalized}%"))
        .first()
    )
    if fw:
        return fw.id

    # 5. Try substring search on name
    fw = (
        session.query(Framework)
        .filter(Framework.name.ilike(f"%{normalized}%"))
        .first()
    )
    if fw:
        return fw.id

    if strict:
        logger.warning("Could not resolve framework name '%s' to any known framework", framework_name)
    return None


def resolve_frameworks(
    session: Session,
    framework_names: list[str] | None = None,
    framework_ids: list[int] | None = None,
    *,
    strict: bool = True,
) -> list[int] | None:
    """Resolve a list of framework inputs to a list of integer IDs.

    If *framework_ids* is provided, uses those directly.
    If *framework_names* is provided, resolves each name.
    Returns *None* if any name fails to resolve (in strict mode).
    """
    if framework_ids is not None:
        return framework_ids

    if not framework_names:
        return None

    ids: list[int] = []
    for name in framework_names:
        fid = resolve_framework_id(session, framework_name=name, strict=strict)
        if fid is None:
            return None
        ids.append(fid)
    return ids


def search_frameworks(session: Session, query: str, limit: int = 10) -> list[dict]:
    """Search frameworks by code or name substring (case-insensitive)."""
    pattern = f"%{_normalize(query)}%"
    results = (
        session.query(Framework)
        .filter(
            Framework.code.ilike(pattern) | Framework.name.ilike(pattern)
        )
        .order_by(Framework.code)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": fw.id,
            "code": fw.code,
            "name": fw.name,
            "category": fw.category,
            "description": fw.description[:200] if fw.description else None,
        }
        for fw in results
    ]
