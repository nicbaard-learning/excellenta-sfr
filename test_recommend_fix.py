"""Test that US + IAM business model returns results."""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.database import SessionLocal
from app.services.recommendation_service import RecommendationService

s = SessionLocal()
try:
    svc = RecommendationService(s)

    print("=== TEST 1: US only ===")
    result = svc.recommend_by_context(jurisdiction="US")
    print(f"  Results: {result['total']}")
    for r in result["recommendations"][:5]:
        print(f"    {r['code']}: {r['name']}")
    print()

    print("=== TEST 2: IAM only ===")
    result = svc.recommend_by_context(business_model="IAM")
    print(f"  Results: {result['total']}")
    for r in result["recommendations"][:10]:
        print(f"    {r['code']}: {r['name']}")
    print()

    print("=== TEST 3: US + IAM (THE KEY TEST) ===")
    result = svc.recommend_by_context(jurisdiction="US", business_model="IAM")
    print(f"  Results: {result['total']}")
    for r in result["recommendations"][:15]:
        print(f"    {r['code']}: {r['name']}")
    print()

    print("=== Filters applied ===")
    print(f"  {result['applied_filters']}")

finally:
    s.close()
