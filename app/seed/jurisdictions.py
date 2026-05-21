"""Seed helper – populate common jurisdictions."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.jurisdiction import Jurisdiction

logger = logging.getLogger(__name__)

COMMON_JURISDICTIONS = [
    # EU / EEA
    ("EU", "European Union", "EU"),
    ("AT", "Austria", "EU"),
    ("BE", "Belgium", "EU"),
    ("BG", "Bulgaria", "EU"),
    ("HR", "Croatia", "EU"),
    ("CY", "Cyprus", "EU"),
    ("CZ", "Czech Republic", "EU"),
    ("DK", "Denmark", "EU"),
    ("EE", "Estonia", "EU"),
    ("FI", "Finland", "EU"),
    ("FR", "France", "EU"),
    ("DE", "Germany", "EU"),
    ("GR", "Greece", "EU"),
    ("HU", "Hungary", "EU"),
    ("IE", "Ireland", "EU"),
    ("IT", "Italy", "EU"),
    ("LV", "Latvia", "EU"),
    ("LT", "Lithuania", "EU"),
    ("LU", "Luxembourg", "EU"),
    ("MT", "Malta", "EU"),
    ("NL", "Netherlands", "EU"),
    ("PL", "Poland", "EU"),
    ("PT", "Portugal", "EU"),
    ("RO", "Romania", "EU"),
    ("SK", "Slovakia", "EU"),
    ("SI", "Slovenia", "EU"),
    ("ES", "Spain", "EU"),
    ("SE", "Sweden", "EU"),
    # EEA additional
    ("IS", "Iceland", "EEA"),
    ("LI", "Liechtenstein", "EEA"),
    ("NO", "Norway", "EEA"),
    ("CH", "Switzerland", "EEA"),
    # North America
    ("US", "United States", "NA"),
    ("CA", "Canada", "NA"),
    ("MX", "Mexico", "NA"),
    # APAC
    ("AU", "Australia", "APAC"),
    ("NZ", "New Zealand", "APAC"),
    ("JP", "Japan", "APAC"),
    ("SG", "Singapore", "APAC"),
    ("KR", "South Korea", "APAC"),
    ("CN", "China", "APAC"),
    ("IN", "India", "APAC"),
    ("HK", "Hong Kong", "APAC"),
    ("MY", "Malaysia", "APAC"),
    ("ID", "Indonesia", "APAC"),
    ("PH", "Philippines", "APAC"),
    ("TH", "Thailand", "APAC"),
    ("TW", "Taiwan", "APAC"),
    # LATAM
    ("BR", "Brazil", "LATAM"),
    ("AR", "Argentina", "LATAM"),
    ("CL", "Chile", "LATAM"),
    ("CO", "Colombia", "LATAM"),
    ("PE", "Peru", "LATAM"),
    ("UY", "Uruguay", "LATAM"),
    # Middle East / Africa
    ("AE", "United Arab Emirates", "MEA"),
    ("SA", "Saudi Arabia", "MEA"),
    ("ZA", "South Africa", "MEA"),
    ("NG", "Nigeria", "MEA"),
    ("KE", "Kenya", "MEA"),
    ("IL", "Israel", "MEA"),
    ("QA", "Qatar", "MEA"),
    ("TR", "Turkey", "MEA"),
    # Caribbean & Offshore
    ("BM", "Bermuda", "CAR"),
    ("BS", "Bahamas", "CAR"),
    # Eastern Europe / Eurasia
    ("RS", "Serbia", "EEA"),
    ("RU", "Russia", "EE"),  # Eastern Europe / Eurasia (not EEA)
    # UK post-Brexit
    ("GB", "United Kingdom", "EU"),  # Former EU
]


def seed_jurisdictions(session: Session) -> int:
    """Insert common jurisdictions if they don't already exist."""
    existing = {j.code for j in session.query(Jurisdiction).all()}
    count = 0
    for code, name, region in COMMON_JURISDICTIONS:
        if code not in existing:
            session.add(Jurisdiction(code=code, name=name, region=region))
            count += 1
    session.flush()
    if count:
        logger.info("Seeded %d jurisdictions", count)
    return count
