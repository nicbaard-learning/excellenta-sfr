"""Check what control and domain data exists related to IAM."""

from app.database import SessionLocal
from sqlalchemy import text

s = SessionLocal()
try:
    print("=== Controls in IA domain (Identification & Authentication) ===")
    r = s.execute(text("""
        SELECT c.scf_id, c.title, d.code as domain_code, d.name as domain_name
        FROM controls c
        JOIN domains d ON c.domain_id = d.id
        WHERE d.code LIKE 'IA%'
        ORDER BY c.scf_id
        LIMIT 30
    """))
    for row in r:
        print(f"  {row.scf_id} | {row.domain_code} | {row.title[:100]}")

    print()
    print("=== Controls with 'identity' in title (first 20) ===")
    r = s.execute(text("""
        SELECT c.scf_id, c.title, d.code as domain_code
        FROM controls c
        JOIN domains d ON c.domain_id = d.id
        WHERE LOWER(c.title) LIKE '%identity%'
        ORDER BY c.scf_id
        LIMIT 20
    """))
    for row in r:
        print(f"  {row.scf_id} | {row.domain_code} | {row.title[:100]}")

    print()
    print("=== Controls with 'access' in title (first 20) ===")
    r = s.execute(text("""
        SELECT c.scf_id, c.title, d.code as domain_code
        FROM controls c
        JOIN domains d ON c.domain_id = d.id
        WHERE LOWER(c.title) LIKE '%access%'
        ORDER BY c.scf_id
        LIMIT 20
    """))
    for row in r:
        print(f"  {row.scf_id} | {row.domain_code} | {row.title[:100]}")

    print()
    print("=== Controls with 'authentication' in title (first 20) ===")
    r = s.execute(text("""
        SELECT c.scf_id, c.title, d.code as domain_code
        FROM controls c
        JOIN domains d ON c.domain_id = d.id
        WHERE LOWER(c.title) LIKE '%authentic%'
        ORDER BY c.scf_id
        LIMIT 20
    """))
    for row in r:
        print(f"  {row.scf_id} | {row.domain_code} | {row.title[:100]}")

    print()
    print("=== Check if 'identity' keyword matches any domain name ===")
    r = s.execute(text("""
        SELECT code, name FROM domains
        WHERE LOWER(name) LIKE '%identity%'
           OR LOWER(name) LIKE '%access%'
           OR LOWER(code) LIKE '%iam%'
    """))
    for row in r:
        print(f"  {row.code}: {row.name}")

    print()
    print("=== Frameworks with most IA-domain controls ===")
    r = s.execute(text("""
        SELECT f.id, f.code, f.name, COUNT(*) as cnt
        FROM control_mappings cm
        JOIN controls c ON cm.control_id = c.id
        JOIN domains d ON c.domain_id = d.id
        JOIN frameworks f ON cm.framework_id = f.id
        WHERE d.code LIKE 'IA%'
        GROUP BY f.id, f.code, f.name
        ORDER BY cnt DESC
        LIMIT 15
    """))
    for row in r:
        print(f"  fw {row.id} [{row.code}] {row.name}: {row.cnt} IA controls")

finally:
    s.close()
