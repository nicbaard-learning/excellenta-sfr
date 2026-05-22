"""Check business models and related data."""

from app.database import SessionLocal
from sqlalchemy import text

s = SessionLocal()
try:
    print("=== Business Models ===")
    r = s.execute(text("SELECT id, code, name, category FROM business_models ORDER BY id"))
    rows = r.fetchall()
    for row in rows:
        print(f"  {row.id}: [{row.code}] {row.name} | cat={row.category}")
    if not rows:
        print("  (EMPTY - no business models in DB)")

    print()
    print("=== FrameworkApplicabilityRule table exists? ===")
    r = s.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'framework_applicability_rules')"))
    exists = r.scalar()
    print(f"  Exists: {exists}")

    if exists:
        print()
        print("=== Applicability rules ===")
        r = s.execute(text("SELECT id, framework_id, attribute_name, attribute_value FROM framework_applicability_rules LIMIT 30"))
        for row in r:
            print(f"  id={row.id} fw={row.framework_id} {row.attribute_name}={row.attribute_value}")

    print()
    print("=== Domains (control families) ===")
    r = s.execute(text("SELECT id, code, name FROM domains ORDER BY id"))
    for row in r:
        print(f"  {row.id}: {row.code} - {row.name}")

    print()
    print("=== Sample control SCF IDs (first 30) ===")
    r = s.execute(text("SELECT scf_id FROM controls ORDER BY scf_id LIMIT 30"))
    for row in r:
        print(f"  {row.scf_id}")

    print()
    print("=== Distinct control 3-char prefixes ===")
    r = s.execute(text("SELECT DISTINCT LEFT(scf_id, 3) FROM controls ORDER BY 1"))
    for row in r:
        print(f"  {row[0]}")

    print()
    print("=== Distinct Domain codes from domains table ===")
    r = s.execute(text("SELECT DISTINCT code FROM domains ORDER BY code"))
    for row in r:
        print(f"  {row.code}")

finally:
    s.close()
