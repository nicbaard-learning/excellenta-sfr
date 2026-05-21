"""Import frameworks and versions from the workbook."""

from __future__ import annotations

import logging
from typing import Any

import openpyxl
import pandas as pd

from app.importers.base import find_sheet, load_sheet_dataframe, normalize_headers, safe_str
from app.models.framework import Framework, FrameworkVersion

logger = logging.getLogger(__name__)


# Known framework mappings that appear as columns in the SCF sheet.
# The key is a substring to search for in the (normalized) column header.
# The value is the short framework code used internally.
KNOWN_FRAMEWORK_COLUMNS = {
    # AICPA
    "aicpa privacy management framework": "AICPA-PMF",
    "aicpa tsc": "AICPA-TSC",
    # APEC
    "apec privacy framework": "APEC-Privacy",
    # BSI
    "bsi standard 200": "BSI-200",
    # CIS
    "cis csc": "CIS-CSC",
    # COBIT
    "cobit": "COBIT",
    # COSO
    "coso": "COSO",
    # CSA
    "csa ccm": "CSA-CCM",
    "csa iot scf": "CSA-IoT",
    "cr cmm": "CR-CMM",
    # GovRAMP
    "govramp": "GovRAMP",
    # IEC
    "iec tr 60601": "IEC-60601",
    "iec 62443": "IEC-62443",
    # IMO
    "imo maritime": "IMO-Maritime",
    # ISO/SAE
    "iso/sae 21434": "ISO-SAE-21434",
    # ISO standards
    "iso 22301": "ISO22301",
    "iso 27001": "ISO27001",
    "iso 27002": "ISO27002",
    "iso 27017": "ISO27017",
    "iso 27018": "ISO27018",
    "iso 27701": "ISO27701",
    "iso 29100": "ISO29100",
    "iso 31000": "ISO31000",
    "iso 31010": "ISO31010",
    "iso 42001": "ISO42001",
    # MITRE
    "mitre att&ck": "MITRE-ATTACK",
    # MPA
    "mpa content security": "MPA-CSP",
    # NAIC
    "naic insurance": "NAIC-MDL668",
    # NIST
    "nist ai 100": "NIST-AI-RMF",
    "nist ai 600": "NIST-AI-600",
    "nist privacy framework": "NIST-Privacy",
    "nist 800-37": "NIST-800-37",
    "nist 800-39": "NIST-800-39",
    "nist 800-53": "NIST-800-53",
    "nist 800-66": "NIST-SP-800-66",
    "nist 800-82": "NIST-800-82",
    "nist 800-160": "NIST-800-160",
    "nist 800-161": "NIST-800-161",
    "nist 800-171": "NIST-800-171",
    "nist 800-171a": "NIST-800-171A",
    "nist 800-172": "NIST-800-172",
    "nist 800-207": "NIST-800-207",
    "nist 800-218": "NIST-800-218",
    "nist csf": "NIST-CSF",
    # OECD
    "oecd privacy principles": "OECD-Privacy",
    # OWASP
    "owasp top 10": "OWASP-Top10",
    # PCI DSS
    "pci dss": "PCI-DSS",
    # SCF
    "scf dpmp": "SCF-DPMP",
    # Shared Assessments
    "shared assessments sig": "SIG",
    # SWIFT
    "swift csf": "SWIFT-CSF",
    # TISAX
    "tisax isa": "TISAX-ISA",
    # UL
    "ul 2900": "UL-2900",
    # UN
    "un r155": "UN-R155",
    "un ece wp.29": "UN-WP29",
    # US frameworks
    "us cert rmm": "US-CERT-RMM",
    "us coppa": "US-COPPA",
    "us dhs cisa ssdaf": "US-CISA-SSDAF",
    "us dhs cisa tic": "US-CISA-TIC",
    "us cisa cpg": "US-CISA-CPG",
    "us cjis": "US-CJIS",
    "us c2m2": "US-C2M2",
    "us cmmc": "US-CMMC",
    "us data privacy framework": "US-DPF",
    "us dod zero trust": "US-DoD-ZT",
    "us dfars": "US-DFARS",
    "us eo 14028": "US-EO14028",
    "us facta": "US-FACTA",
    "us far ": "US-FAR",
    "us fca crm": "US-FCA-CRM",
    "us fda 21 cfr": "US-FDA-21CFR",
    "us fedramp": "US-FedRAMP",
    "us ferpa": "US-FERPA",
    "us finra": "US-FINRA",
    "us fipps": "US-FIPPS",
    "us ftc act": "US-FTC",
    "us glba": "US-GLBA",
    "us hhs 45 cfr": "US-HHS-45CFR",
    "us hipaa": "US-HIPAA",
    "us irs 1075": "US-IRS-1075",
    "us cms mars": "US-MARS-E",
    "us nerc cip": "US-NERC-CIP",
    "us nispom": "US-NISPOM",
    "us nnpi": "US-NNPI",
    "us sec cybersecurity": "US-SEC-Cyber",
    "us sox": "US-SOX",
    "us tsa": "US-TSA",
    # US state privacy laws
    "us - ak pipa": "US-AK-PIPA",
    "us - ca sb327": "US-CA-SB327",
    "us - ca ccpa": "US-CA-CCPA",
    "us - ca sb1386": "US-CA-SB1386",
    "us - co colorado privacy": "US-CO-CPA",
    "us - il bipa": "US-IL-BIPA",
    "us - il ipa": "US-IL-IPA",
    "us - il pipa": "US-IL-PIPA",
    "us - ma 201 cmr": "US-MA-201CMR",
    "us - nv privacy": "US-NV-Privacy",
    "us - nv noge": "US-NV-NOGE",
    "us - nv sb220": "US-NV-SB220",
    "us - ny dfs": "US-NY-DFS",
    "us - ny shield": "US-NY-SHIELD",
    "us - or 646a": "US-OR-646A",
    "us - or cpa": "US-OR-CPA",
    "us - tn tipa": "US-TN-TIPA",
    "us - tx bc521": "US-TX-BC521",
    "us - tx cdpa": "US-TX-CDPA",
    "us - tx dir": "US-TX-DIR",
    "us - tx sb 820": "US-TX-SB820",
    "us - tx sb 2610": "US-TX-SB2610",
    "us - tx tx-ramp": "US-TX-TXRAMP",
    "us - va cdpa": "US-VA-CDPA",
    "us - vt act 171": "US-VT-Act171",
    # EMEA
    "emea eu ai act": "EU-AI-Act",
    "emea eu cyber resiliency": "EU-CRA",
    "emea eu eba": "EU-EBA",
    "emea eu dora": "EU-DORA",
    "emea eu gdpr": "EU-GDPR",
    "emea eu nis2": "EU-NIS2",
    "emea eu psd2": "EU-PSD2",
    # EMEA countries
    "emea austria": "EMEA-AT",
    "emea belgium": "EMEA-BE",
    "emea germany": "EMEA-DE",
    "emea greece": "EMEA-GR",
    "emea hungary": "EMEA-HU",
    "emea ireland": "EMEA-IE",
    "emea israel": "EMEA-IL",
    "emea italy": "EMEA-IT",
    "emea kenya": "EMEA-KE",
    "emea nigeria": "EMEA-NG",
    "emea norway": "EMEA-NO",
    "emea poland": "EMEA-PL",
    "emea qatar": "EMEA-QA",
    "emea russia": "EMEA-RU",
    "emea saudi arabia": "EMEA-SA",
    "emea serbia": "EMEA-RS",
    "emea south africa": "EMEA-ZA",
    "emea spain": "EMEA-ES",
    "emea switzerland": "EMEA-CH",
    "emea turkey": "EMEA-TR",
    "emea uae": "EMEA-AE",
    "emea uk ": "UK-",
    # APAC
    "apac australia essential 8": "AU-Essential8",
    "apac australia privacy act": "AU-Privacy",
    "apac australian privacy principles": "AU-APP",
    "apac australia ism": "AU-ISM",
    "apac australia iot": "AU-IoT",
    "apac australia prudential standard cps230": "AU-CPS230",
    "apac australia prudential standard cps234": "AU-CPS234",
    "apac china cybersecurity": "CN-Cyber",
    "apac china data security": "CN-DSL",
    "apac china dnsip": "CN-DNSIP",
    "apac china privacy": "CN-Privacy",
    "apac hong kong": "HK",
    "apac india dpdpa": "IN-DPDPA",
    "apac india itr": "IN-ITR",
    "apac india sebi": "IN-SEBI",
    "apac japan appi": "JP-APPI",
    "apac japan ismap": "JP-ISMAP",
    "apac malaysia": "MY",
    "apac new zealand": "NZ",
    "apac philippines": "PH",
    "apac singapore": "SG",
    "apac south korea": "KR",
    "apac taiwan": "TW",
    # Americas
    "americas argentina": "AR",
    "americas bahamas": "BS",
    "americas bermuda": "BM",
    "americas brazil lgpd": "BR-LGPD",
    "americas canada": "CA",
    "americas chile": "CL",
    "americas colombia": "CO",
    "americas mexico": "MX",
    # Spar, etc.
    "sparta": "SPARTA",
}


def identify_framework_columns(headers: list[str]) -> dict[int, str]:
    """Scan normalized headers for known framework columns.

    Returns a dict mapping column index -> framework code.
    """
    framework_columns: dict[int, str] = {}
    for idx, header in enumerate(headers):
        header_lower = header.lower().strip()
        for key, code in KNOWN_FRAMEWORK_COLUMNS.items():
            if key in header_lower:
                framework_columns[idx] = code
                break
    return framework_columns


def import_frameworks(session, wb) -> dict[str, int]:
    """Import framework definitions from the workbook.

    First checks the SCF sheet headers for mapped framework columns,
    then seeds any known frameworks that aren't yet in the database.

    Returns a dict mapping framework code -> framework id.
    """
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        # Try alternative sheet names
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is None:
            logger.warning("No SCF main sheet found – skipping framework import")
            return {}
        df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")

    headers = normalize_headers(df)
    fw_columns = identify_framework_columns(headers)

    # Also load Authoritative Sources sheet for additional frameworks
    _import_authoritative_frameworks(session, wb)

    # Ensure known frameworks exist
    framework_ids: dict[str, int] = {}
    seen = {fw.code: fw.id for fw in session.query(Framework).all()}

    # Add mapped frameworks
    for code in fw_columns.values():
        if code not in seen:
            name = _framework_name(code)
            fw = Framework(code=code, name=name, category=_framework_category(code))
            session.add(fw)
            session.flush()
            seen[code] = fw.id
        framework_ids[code] = seen[code]

    # Always ensure SCF exists
    if "SCF" not in seen:
        scf = Framework(
            code="SCF",
            name="Secure Controls Framework",
            category="canonical",
            is_scf=True,
            description="The Secure Controls Framework (SCF) – a canonical control library.",
        )
        session.add(scf)
        session.flush()
        framework_ids["SCF"] = scf.id
    else:
        framework_ids["SCF"] = seen["SCF"]

    # Import SCF version
    _import_scf_version(session, wb, framework_ids["SCF"])

    session.flush()
    logger.info("Imported %d frameworks", len(framework_ids))
    return framework_ids


def _framework_name(code: str) -> str:
    """Return a human-readable framework name for a code."""
    names = {
        "ISO27001": "ISO/IEC 27001",
        "ISO27002": "ISO/IEC 27002",
        "NIST-CSF": "NIST Cybersecurity Framework",
        "NIST-800-53": "NIST SP 800-53",
        "PCI-DSS": "PCI Data Security Standard",
        "GDPR": "General Data Protection Regulation",
        "HIPAA": "Health Insurance Portability and Accountability Act",
        "SOX": "Sarbanes-Oxley Act",
        "COBIT": "COBIT",
        "CIS-CONTROLS": "CIS Critical Security Controls",
        "CMMC": "Cybersecurity Maturity Model Certification",
        "FedRAMP": "Federal Risk and Authorization Management Program",
        "POPIA": "Protection of Personal Information Act",
        "CCPA": "California Consumer Privacy Act",
        "LGPA": "Lei Geral de Proteção de Dados",
        "PIPEDA": "Personal Information Protection and Electronic Documents Act",
        "APRA-CPS234": "APRA Prudential Standard CPS 234",
        "NIST-Privacy": "NIST Privacy Framework",
        "BCR": "Binding Corporate Rules",
    }
    return names.get(code, code)


def _framework_category(code: str) -> str:
    """Return a category for the framework."""
    regulatory = {"GDPR", "HIPAA", "SOX", "CCPA", "LGPA", "POPIA", "PIPEDA", "APRA-CPS234"}
    industry = {"PCI-DSS", "FedRAMP"}
    international = {"ISO27001", "ISO27002", "BCR"}
    us_government = {"NIST-CSF", "NIST-800-53", "NIST-Privacy", "CMMC"}
    if code in regulatory:
        return "regulatory"
    if code in industry:
        return "industry"
    if code in international:
        return "international"
    if code in us_government:
        return "government"
    return "framework"


def _import_scf_version(session, wb, scf_framework_id: int) -> None:
    """Create or update the SCF version record."""
    df = load_sheet_dataframe(wb, "SCF 2026.1")
    if df is None:
        sheet = find_sheet(wb, "SCF 2026")
        if sheet is not None:
            df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")
        else:
            return
    version = session.query(FrameworkVersion).filter_by(
        framework_id=scf_framework_id, version_label="2026.1"
    ).first()
    if not version:
        version = FrameworkVersion(
            framework_id=scf_framework_id,
            version_label="2026.1",
            status="active",
            source_sheet="SCF 2026.1",
        )
        session.add(version)


def _import_authoritative_frameworks(session, wb) -> None:
    """Scan the Authoritative Sources sheet for any additional frameworks to seed."""
    sheet = find_sheet(wb, "Authoritative Sources")
    if sheet is None:
        return
    df = pd.read_excel(wb, sheet_name=sheet.title, engine="openpyxl")
    seen = {fw.code: fw.id for fw in session.query(Framework).all()}
    for _, row in df.iterrows():
        org = safe_str(row.get("Source Organization") or row.get("source_organization"))
        if org and org.upper() not in seen:
            code = org.upper().replace(" ", "_")[:50]
            fw = Framework(code=code, name=org, category="reference", is_scf=False)
            session.add(fw)
            session.flush()
            seen[code] = fw.id
