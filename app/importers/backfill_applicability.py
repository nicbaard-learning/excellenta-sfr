"""Backfill framework applicability rules from known framework attributes.

The SCF workbook has no dedicated sheet for business models, privacy context,
or organizational size. Instead we derive reasonable heuristics from:

1.  **Framework category** — frameworks in the 'government' category are likely
    relevant to US government contractors (business model: CONSULTING).
2.  **Framework code/name keywords** — a framework named "HIPAA" or whose code
    contains "HIPAA" is relevant to healthcare technology companies.
3.  **Explicit mapping** — well-known frameworks like PCI-DSS are explicitly
    mapped to payment-industry business models.

Every rule includes a `rationale` field explaining *why* it was created so
consumers can judge its reliability.  This is deliberately *not* authoritative
— treat it as a starting point that domain experts should refine.

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.applicability import FrameworkApplicabilityRule
from app.models.framework import Framework

# Short (2-letter) codes that should use exact matching, not startswith,
# to avoid false positives like "CO" matching "COBIT".
_EXACT_PRIVACY_CODES: set[str] = {
    "CO", "CA", "KR", "SG", "MY", "PH", "TW", "HK", "NZ", "MX", "AR", "CL",
    "GDPR", "CCPA", "PIPEDA", "LGPA", "HIPAA", "SOX", "COPPA", "FERPA", "GLBA",
}

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  BUSINESS-MODEL RULES
#  Format: (framework_code, business_model_code, rationale)
# ──────────────────────────────────────────────────────────────

EXPLICIT_BM_RULES: list[tuple[str, str, str]] = [
    # Payment / Financial
    ("PCI-DSS",       "PAYMENT",      "Payment card industry data standard — required for payment processors"),
    ("SWIFT-CSF",     "PAYMENT",      "SWIFT Customer Security Programme — financial messaging"),
    ("SWIFT-CSF",     "FINTECH",      "SWIFT CSF applies to financial technology firms using SWIFT"),
    ("US-NY-DFS",     "FINTECH",      "NY DFS cybersecurity regulation covers financial services"),
    ("US-NY-DFS",     "INSURANCE",    "NY DFS also regulates insurance companies"),
    ("US-SOX",        "SAAS",         "SOX ITGC applies to any public company's SaaS platforms"),
    ("SOX",           "SAAS",         "SOX ITGC applies to any public company's SaaS platforms"),
    ("US-FINRA",      "FINTECH",      "FINRA rules govern securities brokers and fintech platforms"),

    # Healthcare
    ("HIPAA",         "HEALTHTECH",   "HIPAA Privacy & Security Rules govern healthcare providers and tech"),
    ("US-HIPAA",      "HEALTHTECH",   "US HIPAA replication in the SCF mapping"),
    ("US-HHS-45CFR",  "HEALTHTECH",   "HHS 45 CFR (HIPAA administrative simplification)"),
    ("US-FDA-21CFR",  "HEALTHTECH",   "FDA 21 CFR Part 11 — electronic records for medical devices"),
    ("IEC-60601",     "HEALTHTECH",   "IEC 60601 — medical electrical equipment security"),

    # Cloud / SaaS
    ("FedRAMP",       "IAAS",         "FedRAMP authorisation required for IaaS federal cloud services"),
    ("FedRAMP",       "PAAS",         "FedRAMP authorisation required for PaaS federal cloud services"),
    ("FedRAMP",       "SAAS",         "FedRAMP authorisation required for SaaS federal cloud services"),
    ("US-FedRAMP",    "IAAS",         "US FedRAMP SCF mapping — IaaS"),
    ("US-FedRAMP",    "PAAS",         "US FedRAMP SCF mapping — PaaS"),
    ("US-FedRAMP",    "SAAS",         "US FedRAMP SCF mapping — SaaS"),
    ("CSA-CCM",       "IAAS",         "Cloud Security Alliance CCM covers IaaS"),
    ("CSA-CCM",       "PAAS",         "Cloud Security Alliance CCM covers PaaS"),
    ("CSA-CCM",       "SAAS",         "Cloud Security Alliance CCM covers SaaS"),
    ("ISO27017",      "IAAS",         "ISO 27017 cloud security — IaaS"),
    ("ISO27017",      "PAAS",         "ISO 27017 cloud security — PaaS"),
    ("ISO27017",      "SAAS",         "ISO 27017 cloud security — SaaS"),
    ("ISO27018",      "SAAS",         "ISO 27018 cloud privacy — SaaS providers processing PII"),

    # Managed Services
    ("CIS-CSC",       "MSP",          "CIS Critical Security Controls are a baseline for MSPs"),
    ("CIS-CSC",       "MSSP",         "CIS controls are the foundation for MSSP security monitoring"),
    ("SIG",           "MSP",          "Shared Assessments SIG — standard vendor assessment for MSPs"),
    ("SIG",           "MSSP",         "Shared Assessments SIG — used by MSSPs for client reporting"),

    # Professional Services / Consulting
    ("ISO27001",      "CONSULTING",   "ISO 27001 certification consulting — core offering"),
    ("ISO27001",      "MSP",          "ISO 27001 is the ISMS backbone for managed service providers"),
    ("ISO27001",      "SAAS",         "ISO 27001 certification is a common SaaS requirement"),
    ("ISO27001",      "IAAS",         "ISO 27001 applies to IaaS infrastructure providers"),
    ("ISO27001",      "PAAS",         "ISO 27001 applies to PaaS platform providers"),
    ("COBIT",         "CONSULTING",   "COBIT is an IT governance framework used by consultants"),
    ("COBIT",         "IAAS",         "COBIT governance applies to IT service providers"),
    ("NIST-CSF",      "CONSULTING",   "NIST CSF assessments are a standard consulting offering"),
    ("NIST-CSF",      "IAAS",         "NIST CSF applies to critical infrastructure IaaS"),
    ("NIST-CSF",      "SAAS",         "NIST CSF applies to SaaS providers in critical infrastructure"),
    ("AICPA-TSC",     "SAAS",         "SOC 2 (AICPA TSC) is the most common SaaS attestation"),
    ("AICPA-TSC",     "IAAS",         "SOC 2 applies to IaaS data centers and cloud providers"),
    ("AICPA-TSC",     "MSP",          "SOC 2 is used by MSPs for client assurance"),
    ("AICPA-TSC",     "CONSULTING",   "SOC 2 readiness assessments are a consulting service"),
    ("AICPA-PMF",     "SAAS",         "AICPA Privacy Management Framework — relevant to privacy-forward SaaS"),
    ("AICPA-PMF",     "CONSULTING",   "Privacy management consulting engagements"),

    # Security specialists
    ("MITRE-ATTACK",  "MSSP",         "MITRE ATT&CK is the primary threat framework for MSSPs"),
    ("MITRE-ATTACK",  "SIEM",         "SIEM vendors build detection rules around MITRE ATT&CK"),
    ("MITRE-ATTACK",  "CONSULTING",   "Threat modelling and red-team consulting"),

    # IAM / Identity
    ("NIST-800-63",   "IAM",          "NIST SP 800-63 digital identity guidelines"),
    ("ISO29100",      "IAM",          "ISO 29100 privacy framework — identity and privacy"),

    # Training
    ("ISO27001",      "TRAINING",     "ISO 27001 lead auditor / implementer training"),

    # HR / Payroll
    ("US-IRS-1075",   "HRPAYROLL",    "IRS 1075 — tax information safeguarding for payroll/HCM"),
    ("US-IRS-1075",   "PEO",          "PEOs handling tax data must comply with IRS 1075"),
    ("US-FERPA",      "EDTECH",       "FERPA — student privacy for edtech and HR systems"),

    # Data / Analytics
    ("CCPA",          "DATABROKER",   "CCPA explicitly targets data brokers in California"),
    ("CCPA",          "MARKETING",    "CCPA applies to marketing tech collecting CA consumer data"),
    ("US-CA-CCPA",    "DATABROKER",   "California Consumer Privacy Act — data broker regulation"),
    ("US-CA-CCPA",    "MARKETING",    "CCPA compliance for ad tech and marketing platforms"),
    ("GDPR",          "DATABROKER",   "GDPR — data broker obligations under Art 22"),
    ("GDPR",          "MARKETING",    "GDPR consent rules govern marketing automation"),
    ("GDPR",          "SAAS",         "GDPR applies to any SaaS processing EU personal data"),
    ("EU-GDPR",       "SAAS",         "EU GDPR SCF mapping — SaaS providers"),
    ("EU-GDPR",       "MARKETING",    "EU GDPR marketing consent requirements"),

    # AI / ML
    ("EU-AI-Act",     "AIMAACHINELEARNING", "EU AI Act regulates high-risk AI systems"),
    ("NIST-AI-RMF",   "AIMAACHINELEARNING", "NIST AI Risk Management Framework"),
    ("NIST-AI-600",   "AIMAACHINELEARNING", "NIST AI 600 — AI standards profile"),
    ("ISO42001",      "AIMAACHINELEARNING", "ISO 42001 AI management system standard"),

    # Telecom / Infrastructure
    ("US-NERC-CIP",   "TELECOM",      "NERC CIP — bulk electric system cybersecurity"),
    ("US-NERC-CIP",   "DATACENTER",   "Data centres serving the power grid"),
    ("IEC-62443",     "HARDWARE",     "IEC 62443 — industrial automation and control systems"),
    ("IEC-62443",     "NETWORK",      "IEC 62443 — network security for OT environments"),

    # Automotive
    ("TISAX-ISA",     "HARDWARE",     "TISAX — automotive information security for suppliers"),
    ("TISAX-ISA",     "CUSTOMDEV",    "Automotive software development requires TISAX"),
    ("UN-R155",       "HARDWARE",     "UN R155 — cybersecurity for automotive ECUs"),
    ("UN-WP29",       "HARDWARE",     "UN WP.29 — automotive cybersecurity framework"),
    ("ISO-SAE-21434", "HARDWARE",     "ISO/SAE 21434 — automotive cybersecurity engineering"),

    # Supply Chain / Logistics
    ("US-TSA",        "SUPPLYCHAIN",  "TSA security directives for pipeline and transport"),
    ("IMO-Maritime",  "SUPPLYCHAIN",  "IMO maritime cybersecurity — shipping and logistics"),

    # Government / Defense
    ("CMMC",          "HARDWARE",     "CMMC — defense contractor hardware security"),
    ("US-CMMC",       "HARDWARE",     "CMMC (US replication) — defense contractor"),
    ("NIST-800-171",  "IAAS",         "NIST 800-171 — CUI protection for cloud services"),
    ("NIST-800-171",  "SAAS",         "NIST 800-171 — CUI protection for SaaS"),
    ("NIST-800-171",  "CONSULTING",   "DFARS/NIST 800-171 consulting engagements"),
    ("NIST-800-53",   "IAAS",         "NIST 800-53 — FedRAMP baseline for IaaS"),
    ("NIST-800-53",   "SAAS",         "NIST 800-53 — FedRAMP baseline for SaaS"),
    ("NIST-800-53",   "PAAS",         "NIST 800-53 — FedRAMP baseline for PaaS"),
    ("NIST-800-53",   "CONSULTING",   "NIST 800-53 assessment and ATO consulting"),
    ("NIST-800-53",   "HARDWARE",     "FedRAMP baseline for hardware/device vendors"),

    # Education
    ("US-COPPA",      "EDTECH",       "COPPA — children's online privacy for edtech"),
    ("US-FERPA",      "EDTECH",       "FERPA — student records privacy for edtech"),

    # Insurance
    ("NAIC-MDL668",   "INSURANCE",    "NAIC MDL-668 — insurance data security model law"),
    ("US-GLBA",       "INSURANCE",    "GLBA — financial privacy for insurers"),

    # Collections
    ("US-FACTA",      "COLLECTIONS",  "FACTA — identity theft / credit reporting for debt collection"),
    ("US-FCA-CRM",    "COLLECTIONS",  "FCA Credit Reporting — debt collection agencies"),

    # Background checks
    ("US-FACTA",      "BGMANUFACTURING", "FACTA — background check and MVR services"),
]

# ──────────────────────────────────────────────────────────────
#  PRIVACY-CONTEXT RULES
#  attribute_name='privacy_context', attribute_value='privacy'
# ──────────────────────────────────────────────────────────────

PRIVACY_FRAMEWORK_PREFIXES: list[tuple[str, str]] = [
    # Code prefix → rationale
    # Exact codes
    ("GDPR",        "General Data Protection Regulation (EU)"),
    ("CCPA",        "California Consumer Privacy Act"),
    ("PIPEDA",      "Personal Information Protection and Electronic Documents Act (CA)"),
    ("LGPA",        "Lei Geral de Proteção de Dados (BR)"),
    ("HIPAA",       "Health Insurance Portability and Accountability Act (US)"),
    ("SOX",         "Sarbanes-Oxley Act — financial privacy / record retention"),
    ("COPPA",       "Children's Online Privacy Protection Act (US)"),
    ("FERPA",       "Family Educational Rights and Privacy Act (US)"),
    ("GLBA",        "Gramm-Leach-Bliley Act — financial privacy (US)"),
    # Prefixes
    ("EU-GDPR",     "EU General Data Protection Regulation (SCF mapped)"),
    ("US-HIPAA",    "HIPAA (SCF mapped)"),
    ("US-GLBA",     "GLBA (SCF mapped)"),
    ("US-COPPA",    "COPPA (SCF mapped)"),
    ("US-FERPA",    "FERPA (SCF mapped)"),
    ("US-CA-CCPA",  "California Consumer Privacy Act (state law)"),
    ("BR-LGPD",     "Brazil LGPD (SCF mapped)"),
    ("IN-DPDPA",    "India Digital Personal Data Protection Act"),
    ("JP-APPI",     "Japan Act on Protection of Personal Information"),
    ("KR",          "South Korea Personal Information Protection Act"),
    ("SG",          "Singapore Personal Data Protection Act"),
    ("MY",          "Malaysia Personal Data Protection Act"),
    ("PH",          "Philippines Data Privacy Act"),
    ("TW",          "Taiwan Personal Data Protection Act"),
    ("HK",          "Hong Kong Personal Data (Privacy) Ordinance"),
    ("NZ",          "New Zealand Privacy Act"),
    ("MX",          "Mexico Ley Federal de Protección de Datos Personales"),
    ("AR",          "Argentina Personal Data Protection Act"),
    ("CO",          "Colombia Ley Estatutaria 1581"),
    ("CL",          "Chile Ley 19.628"),
    ("CA",          "Canada PIPEDA (SCF mapped)"),
    ("AU-Privacy",  "Australian Privacy Act"),
    ("AU-APP",      "Australian Privacy Principles"),
    ("CN-Privacy",  "China Personal Information Protection Law"),
    ("NIST-Privacy","NIST Privacy Framework"),
    ("ISO29100",    "ISO 29100 Privacy framework"),
    ("ISO27701",    "ISO 27701 Privacy Information Management"),
    ("ISO27018",    "ISO 27018 Cloud privacy"),
    ("OECD-Privacy","OECD Privacy Principles"),
    ("APEC-Privacy","APEC Privacy Framework"),
    ("AICPA-PMF",   "AICPA Privacy Management Framework"),
    ("US-NV-Privacy","Nevada Privacy Law"),
    ("US-VA-CDPA",  "Virginia Consumer Data Protection Act"),
    ("US-CO-CPA",   "Colorado Privacy Act"),
    ("US-TX-CDPA",  "Texas Consumer Data Privacy Act"),
    ("US-CT-CPA",   "Connecticut Data Privacy Act"),
    ("US-IL-BIPA",  "Illinois Biometric Information Privacy Act"),
    ("US-IL-PIPA",  "Illinois Personal Information Protection Act"),
    ("US-MA-201CMR","Massachusetts 201 CMR 17.00"),
    ("US-NY-SHIELD","New York SHIELD Act"),
    ("US-OR-646A",  "Oregon Consumer Privacy Act"),
    ("US-TX-BC521", "Texas Business and Commerce Code 521"),
    ("US-DPF",      "US Data Privacy Framework"),
    ("US-FIPPS",    "Fair Information Practice Principles"),
]

# ──────────────────────────────────────────────────────────────
#  SIZE RULES
#  attribute_name='size', attribute_value='small'|'medium'|'large'
#  Only added where the framework has a clear size relevance.
# ──────────────────────────────────────────────────────────────

SIZE_RULES: list[tuple[str, str, str]] = [
    ("NIST-800-171",  "small",  "NIST 800-171 is the standard for small/medium defense contractors (DFARS)"),
    ("NIST-800-171",  "medium", "NIST 800-171 applies to medium-sized defense contractors"),
    ("CMMC",          "small",  "CMMC Level 1 is designed for small contractors (self-assessment)"),
    ("CMMC",          "medium", "CMMC Level 2-3 targets medium defense contractors"),
    ("FedRAMP",       "large",  "FedRAMP JAB authorisation is typically pursued by large cloud providers"),
    ("US-FedRAMP",    "large",  "FedRAMP (mapped) — large enterprise cloud"),
    ("PCI-DSS",       "medium", "PCI DSS SAQ available for small/medium payment processors"),
    ("PCI-DSS",       "large",  "PCI DSS full assessment for large enterprises (Level 1)"),
]


def backfill_applicability_rules(session: Session) -> dict[str, int]:
    """Populate framework_applicability_rules from heuristics.

    Returns counts by attribute_name: {'business_model': N, 'privacy_context': N, 'size': N}
    """
    frameworks_by_code: dict[str, Framework] = {
        fw.code: fw for fw in session.query(Framework).all()
    }

    # Pre-fetch existing rules to avoid duplicates
    existing: set[tuple[int, str, str]] = set()
    for rule in session.query(FrameworkApplicabilityRule).all():
        existing.add((rule.framework_id, rule.attribute_name, rule.attribute_value))

    counts: dict[str, int] = {"business_model": 0, "privacy_context": 0, "size": 0}

    # ── Helper ──────────────────────────────────────────────
    def _add(
        fw_id: int,
        attr_name: str,
        attr_value: str,
        rationale: str,
    ) -> bool:
        key = (fw_id, attr_name, attr_value)
        if key in existing:
            return False
        session.add(FrameworkApplicabilityRule(
            framework_id=fw_id,
            attribute_name=attr_name,
            attribute_value=attr_value,
            is_recommended=True,
            rationale=rationale,
            source_sheet="internal-heuristic",
        ))
        existing.add(key)
        counts[attr_name] = counts.get(attr_name, 0) + 1
        return True

    # ── Phase 1: Explicit business-model rules ──────────────
    for fw_code, bm_code, rationale in EXPLICIT_BM_RULES:
        fw = frameworks_by_code.get(fw_code)
        if fw is None:
            logger.debug("Framework %r not found — skipping BM rule", fw_code)
            continue
        _add(fw.id, "business_model", bm_code, rationale)

    # ── Phase 2: Category-based BM heuristics ───────────────
    # Government frameworks → relevant to consulting & fed contractors
    gov_codes = [
        c for c, f in frameworks_by_code.items()
        if f.category == "government" and not f.is_scf
    ]
    for fw_code in gov_codes:
        fw = frameworks_by_code[fw_code]
        # Skip if already explicitly mapped
        if (fw.id, "business_model", "CONSULTING") in existing:
            continue
        # Skip larger government-only frameworks that aren't consulting-relevant
        if fw_code in ("CMMC", "FedRAMP", "GovRAMP"):
            continue  # these are explicitly mapped in Phase 1 or above
        _add(fw.id, "business_model", "CONSULTING",
             f"Category=government — relevant to government advisory/consulting engagements")
        _add(fw.id, "business_model", "SAAS",
             f"Category=government — government-adjacent SaaS compliance")
        # For NIST frameworks specifically, also suggest IAAS/PAAS
        if fw_code.startswith("NIST-"):
            _add(fw.id, "business_model", "IAAS",
                 f"NIST framework — applicable to IaaS federal cloud providers")
            _add(fw.id, "business_model", "PAAS",
                 f"NIST framework — applicable to PaaS federal cloud providers")

    # International/industry frameworks → broad SaaS applicability
    explicitly_mapped = {r[0] for r in EXPLICIT_BM_RULES}
    broad_codes = [
        c for c, f in frameworks_by_code.items()
        if f.category in ("international", "industry", "framework")
        and not f.is_scf
        and c not in explicitly_mapped
    ]
    for fw_code in broad_codes:
        fw = frameworks_by_code[fw_code]
        # Only add broad rules for ISO-level frameworks (international/well-known)
        if fw.category == "international" and (fw.id, "business_model", "SAAS") not in existing:
            _add(fw.id, "business_model", "SAAS",
                 f"Category=international — broadly applicable to SaaS providers")
            _add(fw.id, "business_model", "CONSULTING",
                 f"Category=international — relevant to compliance consulting")
            _add(fw.id, "business_model", "IAAS",
                 f"Category=international — applicable to IaaS providers")
            _add(fw.id, "business_model", "PAAS",
                 f"Category=international — applicable to PaaS providers")
        elif fw.category == "industry" and (fw.id, "business_model", "SAAS") not in existing:
            _add(fw.id, "business_model", "SAAS",
                 f"Category=industry — sector-specific SaaS compliance")

    # ── Phase 3: Privacy-context rules ──────────────────────
    for code_or_prefix, rationale in PRIVACY_FRAMEWORK_PREFIXES:
        matched = False
        for fw_code, fw in frameworks_by_code.items():
            if fw.is_scf:
                continue
            # Short codes (2-letter country codes) use exact match to avoid
            # false positives like "CO" matching "COBIT" or "COSO".
            # Longer prefixes can safely use startswith.
            if code_or_prefix in _EXACT_PRIVACY_CODES:
                matches = (fw_code == code_or_prefix)
            else:
                matches = fw_code.startswith(code_or_prefix)
            if matches:
                if _add(fw.id, "privacy_context", "privacy", rationale):
                    matched = True
        if not matched:
            logger.debug("No framework matched privacy prefix %r", code_or_prefix)

    # ── Phase 4: Size rules ─────────────────────────────────
    for fw_code, size_val, rationale in SIZE_RULES:
        fw = frameworks_by_code.get(fw_code)
        if fw is None:
            continue
        _add(fw.id, "size", size_val, rationale)

    session.flush()

    total = sum(counts.values())
    logger.info(
        "Applicability backfill: %d business-model, %d privacy-context, %d size rules (%d total)",
        counts["business_model"], counts["privacy_context"], counts["size"], total,
    )

    return counts


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        counts = backfill_applicability_rules(session)
        session.commit()
        print(f"Done — {sum(counts.values())} applicability rules created.")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    except Exception:
        session.rollback()
        logger.exception("Backfill failed")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
