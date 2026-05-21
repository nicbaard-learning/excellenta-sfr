"""Quick integration test for SFR MCP tools.

Usage:
    python test_mcp_tools.py

Runs each MCP tool against the live database and prints results.
Requires the database to be running and populated.
"""

from app.mcp.resolver import resolve_framework_id, resolve_frameworks, search_frameworks
from app.database import SessionLocal

session = SessionLocal()

print("=" * 72)
print("SFR MCP TOOL TESTS")
print("=" * 72)

# --- Resolver Tests ---
print("\n--- Resolver Tests ---")

tests = [
    ("ISO 27001", "ISO27001"),
    ("PCI DSS", "PCI-DSS"),
    ("gdpr", "GDPR"),
    ("GDPR", "GDPR"),
    ("nist csf", "NIST-CSF"),
    ("NIST Cybersecurity Framework", "NIST-CSF"),
    ("hipaa", "HIPAA"),
    ("NIST SP 800-53", "NIST-800-53"),
]

for name, expected_code in tests:
    fid = resolve_framework_id(session, framework_name=name)
    if fid:
        from app.models.framework import Framework
        fw = session.query(Framework).filter(Framework.id == fid).first()
        status = "OK" if fw and fw.code == expected_code else "FAIL"
        print(f"  {status} '{name}' -> id={fid}, code={fw.code if fw else '?'} (expected {expected_code})")
    else:
        print(f"  FAIL '{name}' -> NOT FOUND (expected {expected_code})")

# --- Test search_frameworks ---
print("\n--- Test: search_frameworks ---")
results = search_frameworks(session, "nist", limit=5)
print(f"  Results for 'nist':")
for r in results:
    print(f"    - {r.get('code')}: {r.get('name')}")

# --- Test get_applicable_frameworks ---
print("\n--- Test: get_applicable_frameworks ---")
from app.mcp.server import get_applicable_frameworks

# Test 1: South African SaaS company
print("\n  Case 1: South African SaaS company")
result = get_applicable_frameworks(business_model="SAAS", jurisdiction="ZA")
print(f"    Total: {result.get('total', 0)}")
print(f"    Filters: {result.get('applied_filters', [])}")
for r in result.get("recommendations", [])[:5]:
    print(f"    - {r.get('code')}: {r.get('name')}")

# Test 2: Privacy frameworks in US
print("\n  Case 2: Privacy frameworks in US")
result = get_applicable_frameworks(privacy_context="privacy", jurisdiction="US")
print(f"    Total: {result.get('total', 0)}")
print(f"    Filters: {result.get('applied_filters', [])}")
for r in result.get("recommendations", [])[:5]:
    print(f"    - {r.get('code')}: {r.get('name')}")

# Test 3: All frameworks (no filters)
print("\n  Case 3: No filters (all frameworks)")
result = get_applicable_frameworks()
print(f"    Total: {result.get('total', 0)}")
for r in result.get("recommendations", [])[:5]:
    print(f"    - {r.get('code')}: {r.get('name')}")

# --- Test get_framework_details by name ---
print("\n--- Test: get_framework_details ---")
from app.mcp.server import get_framework_details

print("\n  Case 1: By name 'GDPR'")
result = get_framework_details(framework_name="GDPR")
if "error" in result:
    print(f"    ERROR: {result['error']}")
else:
    print(f"    Code: {result.get('code')}, Name: {result.get('name')}")
    print(f"    Publisher: {result.get('publisher')}")
    print(f"    Jurisdictions: {[j.get('code') for j in result.get('jurisdictions', [])]}")
    print(f"    Versions: {[v.get('version_label') for v in result.get('versions', [])]}")

print("\n  Case 2: By name 'ISO 27001'")
result = get_framework_details(framework_name="ISO 27001")
if "error" in result:
    print(f"    ERROR: {result['error']}")
else:
    print(f"    Code: {result.get('code')}, Name: {result.get('name')}")
    print(f"    Category: {result.get('category')}")
    print(f"    Description (first 200 chars): {result.get('description', '')[:200] if result.get('description') else 'N/A'}")

# --- Test get_framework_controls ---
print("\n--- Test: get_framework_controls ---")
from app.mcp.server import get_framework_controls

# Test by name
print("\n  Case 1: By name 'PCI-DSS', limit=5")
result = get_framework_controls(framework_name="PCI-DSS", limit=5)
if "error" in result:
    print(f"    ERROR: {result['error']}")
else:
    print(f"    Framework: {result.get('framework_code')} - {result.get('framework_name')}")
    print(f"    Total controls: {result.get('total_controls')}, Returned: {result.get('returned')}")
    for c in result.get("controls", [])[:5]:
        print(f"    - {c.get('scf_id')}: {c.get('title')} [{c.get('domain_code')}]")

# Test by ID
print("\n  Case 2: By ID (COBIT, id=98), limit=3")
result = get_framework_controls(framework_id=98, limit=3)
if "error" in result:
    print(f"    ERROR: {result['error']}")
else:
    print(f"    Framework: {result.get('framework_code')} - {result.get('framework_name')}")
    print(f"    Total controls: {result.get('total_controls')}, Returned: {result.get('returned')}")
    for c in result.get("controls", [])[:3]:
        print(f"    - {c.get('scf_id')}: {c.get('title')} [{c.get('domain_code')}]")

# --- Test compare_frameworks ---
print("\n--- Test: compare_frameworks ---")
from app.mcp.server import compare_frameworks

# Find framework IDs
iso_id = resolve_framework_id(session, framework_name="ISO 27001")
nist_id = resolve_framework_id(session, framework_name="NIST CSF")
print(f"  ISO 27001 id={iso_id}, NIST CSF id={nist_id}")

if iso_id and nist_id:
    # Intersection mode
    print("\n  Mode: intersection")
    result = compare_frameworks(framework_ids=[iso_id, nist_id], mode="intersection")
    print(f"    Common controls: {result.get('total_common_controls', result.get('overlap_count', 0))}")
    print(f"    Frameworks: {result.get('framework_names', {})}")
    common = result.get('common_controls', [])
    for c in common[:3]:
        print(f"    - {c.get('scf_id')}: {c.get('title')}")

    # Differences mode
    print("\n  Mode: differences")
    result = compare_frameworks(framework_ids=[iso_id, nist_id], mode="differences")
    print(f"    In ISO not NIST: {result.get('base_count', 0)}")
    print(f"    In NIST not ISO: {result.get('compare_count', 0)}")

# --- Test with natural names ---
print("\n--- Test: compare_frameworks with natural names ---")
result = compare_frameworks(framework_names=["ISO 27001", "NIST CSF"], mode="intersection")
if "error" in result:
    print(f"  ERROR: {result['error']}")
else:
    print(f"  Frameworks: {result.get('framework_names', {})}")
    print(f"  Common controls: {result.get('total_common_controls', result.get('overlap_count', 0))}")

# --- Test error handling ---
print("\n--- Test: Error handling ---")
print("  Case 1: No args to get_framework_details")
result = get_framework_details()
print(f"    Result: {result}")

print("  Case 2: No args to get_framework_controls")
result = get_framework_controls()
print(f"    Result: {result}")

print("  Case 3: Unknown framework name")
result = get_framework_details(framework_name="NonExistentFramework123")
print(f"    Result: {result}")

print("  Case 4: Invalid mode for compare_frameworks")
result = compare_frameworks(framework_ids=[1, 2], mode="invalid_mode")
print(f"    Result: {result}")

print("  Case 5: Single framework for comparison")
result = compare_frameworks(framework_ids=[1], mode="intersection")
print(f"    Result: {result}")

session.close()
print("\n" + "=" * 72)
print("TESTS COMPLETE")
print("=" * 72)
