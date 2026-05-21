"""Seed helper – populate common business models / TPRM vendor categories."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.business_model import BusinessModel

logger = logging.getLogger(__name__)

COMMON_BUSINESS_MODELS = [
    # Cloud / SaaS categories
    ("SAAS", "Software as a Service", "cloud", "Vendor provides cloud-hosted software applications"),
    ("PAAS", "Platform as a Service", "cloud", "Vendor provides cloud-hosted application platforms"),
    ("IAAS", "Infrastructure as a Service", "cloud", "Vendor provides cloud compute, storage, and networking"),
    ("IDaaS", "Identity as a Service", "cloud", "Cloud-based identity and access management"),
    ("DRaaS", "Disaster Recovery as a Service", "cloud", "Cloud-based disaster recovery and business continuity"),
    ("SECaaS", "Security as a Service", "cloud", "Cloud-delivered security services"),
    # Managed services
    ("MSP", "Managed Service Provider", "managed-services", "Vendor manages IT infrastructure for clients"),
    ("MSSP", "Managed Security Service Provider", "managed-services", "Vendor manages security operations for clients"),
    # Professional services
    ("CONSULTING", "Consulting Services", "professional-services", "Strategic advisory, risk, and compliance consulting"),
    ("AUDITOR", "Audit & Assurance", "professional-services", "External audit, assessment, and certification services"),
    ("TRAINING", "Training & Awareness", "professional-services", "Security and compliance training services"),
    # Financial / Payment
    ("PAYMENT", "Payment Processor", "financial", "Payment card processing and financial transaction services"),
    ("FINTECH", "Financial Technology", "financial", "Financial software and technology services"),
    ("INSURANCE", "Insurance Provider", "financial", "Insurance underwriting and brokerage services"),
    # HR / Payroll
    ("HRPAYROLL", "HR & Payroll", "hr", "Human resources and payroll processing services"),
    ("BENEFITS", "Benefits Administration", "hr", "Employee benefits and retirement plan administration"),
    ("PEO", "Professional Employer Organization", "hr", "Co-employment and HR outsourcing services"),
    # Telecom
    ("TELECOM", "Telecommunications", "telecom", "Voice, data, and telecommunications services"),
    ("ISP", "Internet Service Provider", "telecom", "Internet connectivity and bandwidth services"),
    # Data / Analytics
    ("DATAANALYTICS", "Data Analytics", "data", "Data processing, analytics, and business intelligence"),
    ("DATABROKER", "Data Broker", "data", "Data aggregation, enrichment, and brokerage services"),
    ("AIMAACHINELEARNING", "AI/ML Platform", "data", "Artificial intelligence and machine learning platform services"),
    # IAM / Security
    ("IAM", "Identity & Access Management", "security", "Identity governance, SSO, and access management solutions"),
    ("SIEM", "Security Information & Event Management", "security", "Security monitoring, SIEM, and SOAR solutions"),
    ("PENTEST", "Penetration Testing", "security", "Vulnerability assessment and penetration testing services"),
    ("DLP", "Data Loss Prevention", "security", "Data protection and DLP solutions"),
    ("ENCRYPTION", "Encryption & PKI", "security", "Encryption, key management, and PKI services"),
    # Hardware / Infrastructure
    ("HARDWARE", "Hardware Vendor", "hardware", "Hardware manufacturing and supply"),
    ("DATACENTER", "Data Center Provider", "hardware", "Colocation and data center services"),
    ("NETWORK", "Network Equipment Provider", "hardware", "Network infrastructure and equipment"),
    # Other
    ("SOFTWARE", "Software Vendor", "software", "On-premise software licensing and support"),
    ("CUSTOMDEV", "Custom Software Development", "professional-services", "Custom application development and integration"),
    ("SUPPLYCHAIN", "Supply Chain / Logistics", "logistics", "Logistics, shipping, and supply chain management"),
    ("HEALTHTECH", "Healthcare Technology", "healthcare", "Healthcare IT systems and medical device software"),
    ("EDTECH", "Education Technology", "education", "Educational software and learning management systems"),
    ("MARKETING", "Marketing & Ad Tech", "media", "Marketing automation, advertising, and analytics platforms"),
    ("COLLECTIONS", "Debt Collection Agency", "financial", "Debt collection and receivables management"),
    ("BGMANUFACTURING", "Background Check/MVR Provider", "professional-services", "Background screening and MVR services"),
]


def seed_business_models(session: Session) -> int:
    """Insert common business models if they don't already exist."""
    existing = {m.code for m in session.query(BusinessModel).all()}
    count = 0
    for code, name, category, description in COMMON_BUSINESS_MODELS:
        if code not in existing:
            session.add(BusinessModel(code=code, name=name, category=category, description=description))
            count += 1
    session.flush()
    if count:
        logger.info("Seeded %d business models", count)
    return count
