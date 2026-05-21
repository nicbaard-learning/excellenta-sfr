"""Seed runner – populates reference data (jurisdictions, business models, etc.)."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.seed.business_models import seed_business_models
from app.seed.jurisdictions import seed_jurisdictions

logger = logging.getLogger(__name__)


def seed_all(session: Session | None = None) -> dict[str, int]:
    """Run all seed operations and return counts."""
    own_session = session is None
    if own_session:
        session = SessionLocal()

    try:
        counts: dict[str, int] = {}
        counts["jurisdictions"] = seed_jurisdictions(session)
        counts["business_models"] = seed_business_models(session)

        if own_session:
            session.commit()
        else:
            session.flush()

        logger.info("Seeding complete: %s", counts)
        return counts
    finally:
        if own_session:
            session.close()


def main() -> None:
    """CLI entry point for seeding reference data."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    counts = seed_all()
    print("Seeded counts:", counts)
