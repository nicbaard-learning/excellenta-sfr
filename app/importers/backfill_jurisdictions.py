"""Backfill framework–jurisdiction links from framework code patterns.

The SCF workbook has no dedicated "Jurisdiction" sheet. Jurisdiction info is
embedded in framework codes (e.g. "EMEA-ZA" → South Africa, "US-HIPAA" → US).
This module extracts those links and populates the framework_jurisdictions table.

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.framework import Framework
from app.models.jurisdiction import Jurisdiction, FrameworkJurisdiction

logger = logging.getLogger(__name__)

# ── Prefix-based mappings: framework code STARTS WITH the prefix ──
# Format: (prefix, jurisdiction_code, description)
PREFIX_MAP: list[tuple[str, str, str]] = [
    # EMEA countries — use FULL code as prefix to avoid "EMEA-ZA" matching "EMEA-" before "EMEA-ZA"
    ("EMEA-AE", "AE", "UAE"),
    ("EMEA-AT", "AT", "Austria"),
    ("EMEA-BE", "BE", "Belgium"),
    ("EMEA-CH", "CH", "Switzerland"),
    ("EMEA-DE", "DE", "Germany"),
    ("EMEA-ES", "ES", "Spain"),
    ("EMEA-GR", "GR", "Greece"),
    ("EMEA-HU", "HU", "Hungary"),
    ("EMEA-IE", "IE", "Ireland"),
    ("EMEA-IL", "IL", "Israel"),
    ("EMEA-IT", "IT", "Italy"),
    ("EMEA-KE", "KE", "Kenya"),
    ("EMEA-NG", "NG", "Nigeria"),
    ("EMEA-NO", "NO", "Norway"),
    ("EMEA-PL", "PL", "Poland"),
    ("EMEA-QA", "QA", "Qatar"),
    ("EMEA-RS", "RS", "Serbia"),
    ("EMEA-RU", "RU", "Russia"),
    ("EMEA-SA", "SA", "Saudi Arabia"),
    ("EMEA-TR", "TR", "Turkey"),
    ("EMEA-ZA", "ZA", "South Africa"),
    # Country-prefixed frameworks (safe — no overlapping prefixes like "EMEA-")
    ("AU-", "AU", "Australia"),
    ("BR-", "BR", "Brazil"),
    ("CN-", "CN", "China"),
    ("EU-", "EU", "European Union"),
    ("IN-", "IN", "India"),
    ("JP-", "JP", "Japan"),
    ("UK-", "GB", "United Kingdom"),
    ("US-", "US", "United States"),
]

# ── Framework-code-prefix mappings for well-known org-based frameworks ──
# These encode jurisdiction in the publishing organization, not in the code itself.
ORG_PREFIX_MAP: list[tuple[str, str, str]] = [
    ("NIST-", "US", "NIST is a US federal agency"),
    ("MITRE-", "US", "MITRE is US federally funded"),
    ("NAIC-", "US", "National Association of Insurance Commissioners (US)"),
    ("UL-", "US", "UL is a US safety organization"),
    ("BSI-", "DE", "BSI is the German Federal Office for Information Security"),
    ("TISAX-", "DE", "TISAX is a German automotive standard"),
]

# ── Exact framework-code → jurisdiction mappings ──
# These are frameworks whose code IS a country/region code.
EXACT_CODE_MAP: list[tuple[str, str, str]] = [
    ("AR", "AR", "Argentina"),
    ("BM", "BM", "Bermuda"),
    ("BS", "BS", "Bahamas"),
    ("CA", "CA", "Canada"),
    ("CL", "CL", "Chile"),
    ("CO", "CO", "Colombia"),
    ("HK", "HK", "Hong Kong"),
    ("KR", "KR", "South Korea"),
    ("MX", "MX", "Mexico"),
    ("MY", "MY", "Malaysia"),
    ("NZ", "NZ", "New Zealand"),
    ("PH", "PH", "Philippines"),
    ("SG", "SG", "Singapore"),
    ("TW", "TW", "Taiwan"),
]

# ── Standalone framework codes → jurisdiction (old/alternate codes) ──
STANDALONE_MAP: list[tuple[str, str, str]] = [
    ("GDPR", "EU", "General Data Protection Regulation"),
    ("CCPA", "US", "California Consumer Privacy Act"),
    ("PIPEDA", "CA", "Canada PIPEDA"),
    ("LGPA", "BR", "Brazil LGPD"),
    ("FedRAMP", "US", "US Federal Risk Authorization Program"),
    ("GovRAMP", "US", "US Government Risk Authorization Program"),
    ("HIPAA", "US", "US HIPAA"),
    ("SOX", "US", "US Sarbanes-Oxley Act"),
    ("CMMC", "US", "US Cybersecurity Maturity Model Certification"),
    ("COPPA", "US", "US Children's Online Privacy Protection Act"),
]


def backfill_framework_jurisdictions(session: Session) -> int:
    """Create framework–jurisdiction links based on framework code patterns.

    Returns the number of new links created.
    """
    # Pre-fetch all frameworks and jurisdictions for fast lookups
    frameworks_by_code: dict[str, Framework] = {
        fw.code: fw for fw in session.query(Framework).all()
    }
    jurisdictions_by_code: dict[str, Jurisdiction] = {
        j.code: j for j in session.query(Jurisdiction).all()
    }

    # Pre-fetch existing links to avoid duplicates
    existing_links: set[tuple[int, int]] = {
        (fl.framework_id, fl.jurisdiction_id)
        for fl in session.query(FrameworkJurisdiction).all()
    }

    created = 0
    matched_framework_codes: set[str] = set()

    def _link(fw_code: str, fw: Framework, jur_code: str, label: str = "") -> bool:
        """Create a single framework-jurisdiction link if it doesn't exist."""
        nonlocal created
        jur = jurisdictions_by_code.get(jur_code)
        if jur is None:
            logger.warning("Jurisdiction %r not found in DB — skipping link for %s", jur_code, fw_code)
            return False
        key = (fw.id, jur.id)
        if key not in existing_links:
            session.add(FrameworkJurisdiction(
                framework_id=fw.id, jurisdiction_id=jur.id, is_primary=True,
            ))
            existing_links.add(key)
            created += 1
            if created <= 5 or created % 25 == 0:
                detail = f" ({label})" if label else ""
                logger.info("  Linked %s → %s%s", fw_code, jur_code, detail)
        return True

    # --- Phase 1: Exact code matches ---
    # Only match if the framework code EXACTLY matches the jurisdiction code.
    # This avoids "CO" matching "COBIT" or "CA" matching "CA-" prefixed codes.
    for fw_code, jur_code, label in EXACT_CODE_MAP:
        if fw_code not in matched_framework_codes and fw_code in frameworks_by_code:
            if _link(fw_code, frameworks_by_code[fw_code], jur_code, label):
                matched_framework_codes.add(fw_code)

    # --- Phase 2: Prefix matches (EMEA-*, US-*, AU-*, etc.) ---
    for prefix, jur_code, label in PREFIX_MAP:
        for fw_code, fw in frameworks_by_code.items():
            if fw_code in matched_framework_codes:
                continue
            if fw_code.startswith(prefix):
                if _link(fw_code, fw, jur_code, label):
                    matched_framework_codes.add(fw_code)

    # --- Phase 3: Organization-based prefix matches (NIST-*, MITRE-*, etc.) ---
    for prefix, jur_code, label in ORG_PREFIX_MAP:
        for fw_code, fw in frameworks_by_code.items():
            if fw_code in matched_framework_codes:
                continue
            if fw_code.startswith(prefix):
                if _link(fw_code, fw, jur_code, label):
                    matched_framework_codes.add(fw_code)

    # --- Phase 4: Standalone codes ---
    for fw_code, jur_code, label in STANDALONE_MAP:
        if fw_code not in matched_framework_codes and fw_code in frameworks_by_code:
            if _link(fw_code, frameworks_by_code[fw_code], jur_code, label):
                matched_framework_codes.add(fw_code)

    session.flush()
    logger.info("Created %d new framework–jurisdiction links", created)

    # Report unlinked frameworks
    unlinked = [
        fw.code for fw in frameworks_by_code.values()
        if not fw.is_scf and fw.code not in matched_framework_codes
    ]
    if unlinked:
        logger.info(
            "Frameworks without jurisdiction (global / no mapping): %d — %s",
            len(unlinked), ", ".join(sorted(unlinked)),
        )

    return created


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        count = backfill_framework_jurisdictions(session)
        session.commit()
        print(f"Done — created {count} new framework–jurisdiction links.")
    except Exception:
        session.rollback()
        logger.exception("Backfill failed")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
