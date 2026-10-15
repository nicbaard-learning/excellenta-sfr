"""Framework catalogue derived from the SCF workbook.

The SCF workbook describes every mapped framework twice:

* the ``SCF 2026.1`` sheet has one mapping column per framework, and
* the ``Authoritative Sources`` sheet has one row per mapping column (in the
  same order), giving its Focal Document Identifier (FDI), name, full title,
  source/publisher, URL and geography.

This module pairs the two so that each workbook column becomes exactly one
framework, with its metadata and jurisdiction taken from the workbook rather
than guessed from the framework code.

Usage (re-sync an existing database with the workbook):
    python -m app.importers.catalogue --file secure-controls-framework-scf-2026-1.xlsx
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.framework import Framework
from app.models.jurisdiction import FrameworkJurisdiction, Jurisdiction
from app.models.mapping import ControlMapping

logger = logging.getLogger(__name__)

SCF_SHEET = "SCF 2026.1"
SOURCES_SHEET = "Authoritative Sources"

# ── Stable codes for frameworks that existed before the catalogue ──────
# Keyed by FDI. Where the workbook has several columns for one family
# (baselines, levels, revisions) the existing code stays on:
#   1. the family's base document when there is one (e.g. "PCI DSS 4.0.1"),
#   2. otherwise the latest revision (NIST 800-53 R5, NIST 800-171 R3),
#   3. otherwise the first column in the workbook (FedRAMP Low, CMMC Level 1),
# and country-code frameworks (EMEA-xx, CA, NZ, ...) stay on the national
# data-protection law. Every other column gets a code derived from its header.
EXISTING_CODES: dict[str, str] = {
    # General
    "general-aicpa-pmf-2020": "AICPA-PMF",
    "general-aicpa-tsc-2017": "AICPA-TSC",
    "general-apec-privacy-framework-2015": "APEC-Privacy",
    "general-bsi-200-1-1-0": "BSI-200",
    "general-cis-csc-8-1": "CIS-CSC",
    "general-cobit-2019": "COBIT",
    "general-coso-2013": "COSO",
    "general-csa-cmm-4-1-0": "CSA-CCM",
    "general-csa-iot-2": "CSA-IoT",
    "general-cr-cmm-2026": "CR-CMM",
    "general-govramp": "GovRAMP",
    "general-iec-tr-60601-4-5-2021": "IEC-60601",
    "general-iec-62443-2-1-2024": "IEC-62443",
    "general-imo-maritime-cyber-risk-management-2025": "IMO-Maritime",
    "general-iso-21434-2021": "ISO-SAE-21434",
    "general-iso-22301-2019": "ISO22301",
    "general-iso-27001-2022": "ISO27001",
    "general-iso-27002-2022": "ISO27002",
    "general-iso-27017-2015": "ISO27017",
    "general-iso-27018-2025": "ISO27018",
    "general-iso-27701-2025": "ISO27701",
    "general-iso-29100-2024": "ISO29100",
    "general-iso-31000-2018": "ISO31000",
    "general-iso-31010-2009": "ISO31010",
    "general-iso-42001-2023": "ISO42001",
    "general-mitre-att&ck-16-1": "MITRE-ATTACK",
    "general-mpa-csbp-5-3-1": "MPA-CSP",
    "general-naic-insurance-data-security-model-law-668-2017": "NAIC-MDL668",
    "general-nist-100-1-ai-rmf": "NIST-AI-RMF",
    "general-nist-600-1-gen-ai-profile": "NIST-AI-600",
    "general-nist-privacy-framework-1-0": "NIST-Privacy",
    "general-nist-800-37-r2": "NIST-800-37",
    "general-nist-800-39": "NIST-800-39",
    "general-nist-800-53-r5-2": "NIST-800-53",
    "general-nist-800-66-r2": "NIST-SP-800-66",
    "general-nist-800-82-r3": "NIST-800-82",
    "general-nist-800-160-vol-2-r1": "NIST-800-160",
    "general-nist-800-161-r1": "NIST-800-161",
    "general-nist-800-171-r3": "NIST-800-171",
    "general-nist-800-171a-r3": "NIST-800-171A",
    "general-nist-800-172": "NIST-800-172",
    "general-nist-800-207": "NIST-800-207",
    "general-nist-800-218": "NIST-800-218",
    "general-nist-csf-2-0": "NIST-CSF",
    "general-oecd-privacy-principles-2010": "OECD-Privacy",
    "general-owasp-top-10-2025": "OWASP-Top10",
    "general-pci-dss-4-0-1": "PCI-DSS",
    "general-scf-dpmp-2025": "SCF-DPMP",
    "general-shared-assessments-sig-2025": "SIG",
    "general-sparta": "SPARTA",
    "general-swift-cscf-2025": "SWIFT-CSF",
    "general-tisax-6-0-3": "TISAX-ISA",
    "general-ul-2900-1-2017": "UL-2900",
    "general-un-155-2021": "UN-R155",
    "general-un-ece-wp-29-2020": "UN-WP29",
    # US federal
    "usa-federal-dow-cert-rmm-1-2": "US-CERT-RMM",
    "usa-federal-law-coppa-2024": "US-COPPA",
    "usa-federal-dhs-cisa-ssdaf-2024": "US-CISA-SSDAF",
    "usa-federal-dhs-cisa-tic-3-0": "US-CISA-TIC",
    "usa-federal-dhs-cisa-cpg-2-0": "US-CISA-CPG",
    "usa-federal-fbi-cjis-6-0": "US-CJIS",
    "usa-federal-doe-c2m2-2-1": "US-C2M2",
    "usa-federal-dow-cmmc-2-level-1": "US-CMMC",
    "usa-federal-doc-data-privacy-framework-2023": "US-DPF",
    "usa-federal-dow-zt-roadmap-1-1": "US-DoD-ZT",
    "usa-federal-dow-dfars-252-204-7012": "US-DFARS",
    "usa-federal-eo-14028": "US-EO14028",
    "usa-federal-law-facta-fcra-2023": "US-FACTA",
    "usa-federal-far-52-204-21": "US-FAR",
    "usa-federal-sro-fca-crm-2023": "US-FCA-CRM",
    "usa-federal-fda-21-cfr-part-11-2025": "US-FDA-21CFR",
    "usa-federal-gsa-fedramp-5-low": "US-FedRAMP",
    "usa-federal-law-ferpa-2010": "US-FERPA",
    "usa-federal-sro-finra": "US-FINRA",
    "usa-federal-omb-fipps-1973": "US-FIPPS",
    "usa-federal-law-ftc-act": "US-FTC",
    "usa-federal-law-glba-cfr-314-2023": "US-GLBA",
    "usa-federal-hhs-45-cfr-155-260-2016": "US-HHS-45CFR",
    "usa-federal-law-hipaa-simplification-2013": "US-HIPAA",
    "usa-federal-irs-1075-2021": "US-IRS-1075",
    "usa-federal-cms-marse-2-0": "US-MARS-E",
    "usa-federal-nerc-cip-2024": "US-NERC-CIP",
    "usa-federal-nispom-2020": "US-NISPOM",
    "usa-federal-dow-safeguarding-nnpi-2010": "US-NNPI",
    "usa-federal-sec-cybersecurity-rule-2023": "US-SEC-Cyber",
    "usa-federal-law-sox-2002": "US-SOX",
    "usa-federal-tsa-security-directive-1580-82-2022-01": "US-TSA",
    # US state
    "usa-state-ak-pipa-2009": "US-AK-PIPA",
    "usa-state-ca-sb327-2018": "US-CA-SB327",
    "usa-state-ca-ccpa-cpra-2026": "US-CA-CCPA",
    "usa-state-ca-sb1386-2002": "US-CA-SB1386",
    "usa-state-co-privacy-act-2021": "US-CO-CPA",
    "usa-state-il-bipa-2008": "US-IL-BIPA",
    "usa-state-il-ipa-2009": "US-IL-IPA",
    "usa-state-il-pipa-2006": "US-IL-PIPA",
    "usa-state-ma-201-cmr-17-2008": "US-MA-201CMR",
    "usa-state-nv-privacy-law-2023": "US-NV-Privacy",
    "usa-state-nv-regulation-5-2024": "US-NV-NOGE",
    "usa-state-nv-sb220-2019": "US-NV-SB220",
    "usa-state-ny-dfs-23-nycrr500-2023-amd2": "US-NY-DFS",
    "usa-state-ny-shield-act-2019": "US-NY-SHIELD",
    "usa-state-or-ors-646a-2025": "US-OR-646A",
    "usa-state-or-cpa-2023": "US-OR-CPA",
    "usa-state-tn-tipa-2025": "US-TN-TIPA",
    "usa-state-tx-bc521-2009": "US-TX-BC521",
    "usa-state-tx-cdpa-2025": "US-TX-CDPA",
    "usa-state-tx-dir-security-control-standards-catalog-2-2": "US-TX-DIR",
    "usa-state-tx-sb820-2019": "US-TX-SB820",
    "usa-state-tx-sb2610-2025": "US-TX-SB2610",
    "usa-state-tx-txramp-2-0-level-1": "US-TX-TXRAMP",
    "usa-state-va-cdpa-2023": "US-VA-CDPA",
    "usa-state-vt-act-171-2018": "US-VT-Act171",
    # EMEA
    "emea-eu-ai-act-2024": "EU-AI-Act",
    "emea-eu-cyber-resilience-act-2022": "EU-CRA",
    "emea-eu-eba-ict-srm-2025": "EU-EBA",
    "emea-eu-dora-2023": "EU-DORA",
    "emea-eu-gdpr-2016": "EU-GDPR",
    "emea-eu-nis2-2022": "EU-NIS2",
    "emea-us-psd2-2015": "EU-PSD2",
    "emea-aut-fappd-2000": "EMEA-AT",
    "emea-bel-act-8-1992": "EMEA-BE",
    "emea-deu-fdpa-2017": "EMEA-DE",
    "emea-grc-pirppd-1997": "EMEA-GR",
    "emea-hun-isdfi-2011": "EMEA-HU",
    "emea-irl-dpa-2003": "EMEA-IE",
    "emea-isr-ppl-5741-1981": "EMEA-IL",
    "emea-ita-pdpc-2003": "EMEA-IT",
    "emea-ken-pda-2019": "EMEA-KE",
    "emea-nga-dpr-2019": "EMEA-NG",
    "emea-nor-pda-2018": "EMEA-NO",
    "emea-pol-act-29-1997": "EMEA-PL",
    "emea-qat-pdppl-2020": "EMEA-QA",
    "emea-rus-federal-law-27-2006": "EMEA-RU",
    "emea-sau-pdpl-2023": "EMEA-SA",
    "emea-srb-act-9-2018": "EMEA-RS",
    "emea-zaf-popia-2013": "EMEA-ZA",
    "emea-esp-decree-1720-2007": "EMEA-ES",
    "emea-che-fadp-2025": "EMEA-CH",
    "emea-tur-lppd-2016": "EMEA-TR",
    "emea-uae-niaf-2023": "EMEA-AE",
    # APAC
    "apac-aus-essential-8-2024": "AU-Essential8",
    "apac-aus-privacy-act-1998": "AU-Privacy",
    "apac-aus-privacy-principles-2026": "AU-APP",
    "apac-aus-ism-2024-june": "AU-ISM",
    "apac-aus-cop-sitc-2020": "AU-IoT",
    "apac-aus-ps-cps-230-2023": "AU-CPS230",
    "apac-aus-ps-cps-234-2019": "AU-CPS234",
    "apac-chn-cybersecurity-law-2017": "CN-Cyber",
    "apac-chn-data-security-law-2021": "CN-DSL",
    "apac-chn-csnip-2012": "CN-DNSIP",
    "apac-chn-pipl-2021": "CN-Privacy",
    "apac-hkg-pdo-2022": "HK",
    "apac-ind-dpdpa-2023": "IN-DPDPA",
    "apac-ind-privacy-rules-2011": "IN-ITR",
    "apac-ind-sebi-2024": "IN-SEBI",
    "apac-jpn-ppi-2020": "JP-APPI",
    "apac-jpn-ismap": "JP-ISMAP",
    "apac-mys-pdpa-2010": "MY",
    "apac-nzl-privacy-act-2020": "NZ",
    "apac-phl-dpa-2012": "PH",
    "apac-sgp-pdpa-2012": "SG",
    "apac-kor-pipa-2011": "KR",
    "apac-twn-pdpa-2025": "TW",
    # Americas
    "americas-arg-ppd-2018": "AR",
    "americas-bhs-dpa-2003": "BS",
    "americas-bmu-mba-coc-2020": "BM",
    "americas-bra-lgpd-2018": "BR-LGPD",
    "americas-can-pipeda-2000": "CA",
    "americas-chl-act-19628-1999": "CL",
    "americas-col-law-1581-2012": "CO",
    "americas-mex-fdpa-2010": "MX",
}

# Workbook "Source" values (for non-US geographies) that differ from the
# seeded jurisdiction names.
_SOURCE_TO_JURISDICTION: dict[str, str] = {
    "EU": "EU",
    "UAE": "AE",
}


@dataclass
class CatalogueEntry:
    """One framework mapping column of the SCF sheet plus its source metadata."""

    column_index: int
    header: str            # exact SCF sheet header (used as ControlMapping.source_column)
    fdi: str | None        # Focal Document Identifier
    source: str | None     # e.g. "NIST", "PCI SSC", "Federal", "South Africa"
    name: str | None       # Focal Document Name
    title: str | None      # Focal Document Title
    url: str | None        # Focal Document Source
    geography: str | None  # General, US, EMEA, APAC, Americas
    code: str = ""

    @property
    def jurisdiction_key(self) -> str | None:
        """The jurisdiction code or name this framework applies to, or None if global."""
        geo = (self.geography or "").strip()
        if not geo or geo.lower() == "general":
            return None
        if geo.upper() == "US":
            return "US"
        src = (self.source or "").strip()
        return _SOURCE_TO_JURISDICTION.get(src, src) or None


def _norm(value: object) -> str:
    """Normalise a header for comparison: lowercase, no whitespace."""
    return re.sub(r"\s+", "", str(value or "")).lower()


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _code_from_header(header: str) -> str:
    """Derive a framework code from a workbook column header."""
    code = re.sub(r"[^A-Za-z0-9.]+", "-", header).strip("-").upper()
    return code[:50].rstrip("-.")


def load_catalogue(wb) -> list[CatalogueEntry]:
    """Pair the SCF sheet's framework columns with Authoritative Sources rows.

    ``wb`` is an openpyxl workbook. Rows are paired by position (the sheets
    list frameworks in the same order) and checked header-by-header; the
    import is aborted if the sheets have drifted apart.
    """
    scf_headers = list(next(wb[SCF_SHEET].iter_rows(min_row=1, max_row=1, values_only=True)))
    source_rows = [
        r for r in wb[SOURCES_SHEET].iter_rows(min_row=2, values_only=True)
        if r and len(r) > 2 and r[1] and r[2]
    ]
    if not source_rows:
        raise ValueError(f"No framework rows found in the {SOURCES_SHEET!r} sheet")

    norm_headers = [_norm(h) for h in scf_headers]
    first = _norm(source_rows[0][1])
    if first not in norm_headers:
        raise ValueError(f"First {SOURCES_SHEET!r} header {source_rows[0][1]!r} not found in {SCF_SHEET!r}")
    start = norm_headers.index(first)
    if start + len(source_rows) > len(scf_headers):
        raise ValueError(f"{SOURCES_SHEET!r} lists more frameworks than {SCF_SHEET!r} has columns")

    entries: list[CatalogueEntry] = []
    mismatches: list[str] = []
    for offset, row in enumerate(source_rows):
        col = start + offset
        header = str(scf_headers[col])
        if _norm(row[1]) != norm_headers[col]:
            mismatches.append(f"{header!r} ≠ {row[1]!r}")
        entries.append(CatalogueEntry(
            column_index=col,
            header=header,
            fdi=_clean(row[2]),
            source=_clean(row[3]),
            name=_clean(row[4]),
            title=_clean(row[5]),
            url=_clean(row[6]) if row[6] and str(row[6]).startswith("http") else None,
            geography=_clean(row[0]),
        ))

    # A couple of header spelling differences between the sheets are normal;
    # many means the sheets are no longer in step and pairing is unsafe.
    if len(mismatches) > 5:
        raise ValueError(f"{len(mismatches)} header mismatches between sheets, e.g. {mismatches[:3]}")
    for m in mismatches:
        logger.info("Header differs between sheets (paired by position): %s", m)

    # Assign codes: existing code by FDI, else derived from the header.
    used: set[str] = set()
    for e in entries:
        code = EXISTING_CODES.get(e.fdi or "") or _code_from_header(e.header)
        base, n = code, 2
        while code.upper() in used:
            code = f"{base[:46]}-{n}"
            n += 1
        e.code = code
        used.add(code.upper())

    return entries


def sync_frameworks(session: Session, entries: list[CatalogueEntry]) -> dict[str, int]:
    """Create/update one framework per catalogue entry and set its jurisdiction.

    Also removes non-SCF frameworks that are not in the catalogue (legacy
    duplicates such as "FedRAMP" next to "US-FedRAMP"), together with their
    mappings, jurisdiction links and applicability rules.

    Returns a dict of framework code -> framework id for the catalogue.
    """
    from app.seed.jurisdictions import seed_jurisdictions

    seed_jurisdictions(session)
    jurisdictions = session.query(Jurisdiction).all()
    jur_by_key: dict[str, Jurisdiction] = {}
    for j in jurisdictions:
        jur_by_key[j.code.upper()] = j
        jur_by_key[j.name.upper()] = j

    by_code = {fw.code: fw for fw in session.query(Framework).all()}
    framework_ids: dict[str, int] = {}

    for e in entries:
        fw = by_code.get(e.code)
        if fw is None:
            fw = Framework(code=e.code, name=e.name or e.code, category="framework")
            session.add(fw)
        fw.name = (e.name or e.code)[:255]
        fw.description = e.title
        fw.publisher = (e.source or None) and e.source[:255]
        fw.source_url = (e.url or None) and e.url[:500]
        fw.is_scf = False
        session.flush()
        framework_ids[e.code] = fw.id

        # Jurisdiction links mirror the workbook's geography exactly.
        wanted: set[int] = set()
        key = e.jurisdiction_key
        if key:
            jur = jur_by_key.get(key.upper())
            if jur is None:
                logger.warning("Jurisdiction %r for %s not found – left untagged", key, e.code)
            else:
                wanted.add(jur.id)
        links = session.query(FrameworkJurisdiction).filter_by(framework_id=fw.id).all()
        for link in links:
            if link.jurisdiction_id not in wanted:
                session.delete(link)
        have = {link.jurisdiction_id for link in links}
        for jid in wanted - have:
            session.add(FrameworkJurisdiction(framework_id=fw.id, jurisdiction_id=jid, is_primary=True))

    # Remove frameworks the workbook no longer describes.
    catalogue_codes = set(framework_ids)
    for code, fw in by_code.items():
        if not fw.is_scf and code not in catalogue_codes:
            logger.info("Removing framework %s (not a column in the SCF workbook)", code)
            session.delete(fw)

    session.flush()
    logger.info("Framework catalogue synced: %d frameworks", len(framework_ids))
    return framework_ids


def prune_stale_mappings(session: Session, entries: list[CatalogueEntry], framework_ids: dict[str, int]) -> int:
    """Delete mappings that were imported from a column other than the framework's own."""
    removed = 0
    for e in entries:
        fw_id = framework_ids.get(e.code)
        if fw_id is None:
            continue
        removed += (
            session.query(ControlMapping)
            .filter(
                ControlMapping.framework_id == fw_id,
                (ControlMapping.source_column != e.header[:100]) | ControlMapping.source_column.is_(None),
            )
            .delete(synchronize_session=False)
        )
    session.flush()
    if removed:
        logger.info("Removed %d mappings imported from the wrong workbook column", removed)
    return removed


def resync_from_workbook(session: Session, wb) -> dict[str, int]:
    """Bring an existing database's frameworks and mappings in line with the workbook."""
    from app.importers.backfill_applicability import backfill_applicability_rules
    from app.importers.mappings import import_mappings
    from app.services.recommendation_service import clear_recommendation_cache

    entries = load_catalogue(wb)
    framework_ids = sync_frameworks(session, entries)
    pruned = prune_stale_mappings(session, entries, framework_ids)
    added = import_mappings(session, wb, framework_ids, entries)
    rules = backfill_applicability_rules(session)
    clear_recommendation_cache()
    return {
        "frameworks": len(framework_ids),
        "mappings_removed": pruned,
        "mappings_added": added,
        "applicability_rules_added": sum(rules.values()),
    }


def main() -> None:
    """CLI entry point."""
    import openpyxl

    from app.database import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Re-sync frameworks and mappings with the SCF workbook.")
    parser.add_argument("--file", default="secure-controls-framework-scf-2026-1.xlsx")
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.file, data_only=True, read_only=True)
    session = SessionLocal()
    try:
        result = resync_from_workbook(session, wb)
        session.commit()
        print("Done:", result)
    except Exception:
        session.rollback()
        logger.exception("Catalogue sync failed")
        raise
    finally:
        session.close()
        wb.close()


if __name__ == "__main__":
    main()
