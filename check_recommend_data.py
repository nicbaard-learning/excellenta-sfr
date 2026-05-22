"""Check recommendation data - what frameworks, jurisdictions, and links exist."""

from app.database import SessionLocal
from sqlalchemy import text

s = SessionLocal()
try:
    print("=== Frameworks (non-SCF) ===")
    r = s.execute(text("SELECT id, code, name, category, is_scf FROM frameworks ORDER BY id"))
    for row in r:
        print(f"  {row.id}: [{row.code}] {row.name} | cat={row.category} | scf={row.is_scf}")

    print("\n=== FrameworkJurisdictions ===")
    r = s.execute(text("SELECT * FROM framework_jurisdictions ORDER BY jurisdiction_id, framework_id"))
    for row in r:
        print(f"  framework_id={row[0]} jurisdiction_id={row[1]}")

    print("\n=== Jurisdiction Counts per Framework ===")
    r = s.execute(text("""
        SELECT fj.framework_id, f.code, f.name, COUNT(fj.jurisdiction_id)
        FROM framework_jurisdictions fj
        JOIN frameworks f ON f.id = fj.framework_id
        GROUP BY fj.framework_id, f.code, f.name
        ORDER BY fj.framework_id
    """))
    for row in r:
        print(f"  fw {row[0]} ({row[1]}): {row[3]} jurisdictions")

    print("\n=== US Jurisdiction ID ===")
    r = s.execute(text("SELECT id, code, name FROM jurisdictions WHERE code = 'US'"))
    for row in r:
        print(f"  id={row.id} code={row.code} name={row.name}")

    print("\n=== Frameworks linked to US ===")
    r = s.execute(text("""
        SELECT f.id, f.code, f.name, f.is_scf
        FROM frameworks f
        JOIN framework_jurisdictions fj ON fj.framework_id = f.id
        JOIN jurisdictions j ON j.id = fj.jurisdiction_id
        WHERE j.code = 'US'
    """))
    rows = r.fetchall()
    if rows:
        for row in rows:
            print(f"  {row.id}: [{row.code}] {row.name} | scf={row.is_scf}")
    else:
        print("  (none - no frameworks linked to US)")

    print("\n=== Applicability rules ===")
    r = s.execute(text("""
        SELECT f.id, f.code, ar.attribute_name, ar.attribute_value
        FROM applicability_rules ar
        JOIN frameworks f ON f.id = ar.framework_id
        LIMIT 40
    """))
    for row in r:
        print(f"  fw {row.id} ({row.code}): {row.attribute_name}={row.attribute_value}")

    print("\n=== Framework categories ===")
    r = s.execute(text("SELECT DISTINCT category FROM frameworks WHERE category IS NOT NULL ORDER BY category"))
    for row in r:
        print(f"  {row.category}")

    print("\n=== Framework count by is_scf ===")
    r = s.execute(text("SELECT is_scf, COUNT(*) FROM frameworks GROUP BY is_scf"))
    for row in r:
        print(f"  is_scf={row.is_scf}: {row.count}")

finally:
    s.close()
