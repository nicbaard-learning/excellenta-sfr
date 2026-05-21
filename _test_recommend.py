"""End-to-end test for the recommendation flow."""
import sys
sys.path.insert(0, '.')

from app.database import SessionLocal
from app.services.recommendation_service import RecommendationService
from app.services.comparison_service import ComparisonService

s = SessionLocal()
svc = RecommendationService(s)

print('=== RECOMMENDATION FLOW TEST ===')
print()

# 1. List jurisdictions
jurs = svc.list_jurisdictions()
print(f'1. Jurisdictions: {len(jurs)}')
for j in jurs[:4]:
    print(f'   {j["code"]}: {j["name"]} ({j["region"]})')

# 2. List business models
models = svc.list_business_models()
print(f'\n2. Business models: {len(models)}')
for m in models[:4]:
    print(f'   {m["code"]}: {m["name"]} ({m["category"]})')

# 3. Recommend (no filters)
result = svc.recommend_by_context()
print(f'\n3. Recommend (no filters): {result["total"]} frameworks')
if result["recommendations"]:
    fw = result["recommendations"][0]
    print(f'   First: id={fw["id"]} code={fw["code"]} name={fw["name"]}')
    codes = [fw["code"] for fw in result["recommendations"][:8]]
    print(f'   Codes: {codes}...')

# 4. Recommend with jurisdiction=US
result = svc.recommend_by_context(jurisdiction='US')
print(f'\n4. Recommend (US): {result["total"]} frameworks')
print(f'   Filters: {result["applied_filters"]}')
for fw in result["recommendations"]:
    print(f'   {fw["code"]}: {fw["name"][:60]}')

# 5. Recommend with business_model=cloud
result = svc.recommend_by_context(business_model='cloud')
print(f'\n5. Recommend (cloud): {result["total"]} frameworks')
print(f'   Filters: {result["applied_filters"]}')
for fw in result["recommendations"]:
    print(f'   {fw["code"]}: {fw["name"][:60]}')

# 6. Recommend with both
result = svc.recommend_by_context(jurisdiction='US', business_model='cloud')
print(f'\n6. Recommend (US + cloud): {result["total"]} frameworks')
print(f'   Filters: {result["applied_filters"]}')
for fw in result["recommendations"]:
    print(f'   {fw["code"]}: {fw["name"][:60]}')

# 7. Compare handoff with recommended IDs
if result["recommendations"] and len(result["recommendations"]) >= 2:
    ids = [fw["id"] for fw in result["recommendations"][:2]]
    print(f'\n7. Compare handoff: /compare?fw1={ids[0]}&fw2={ids[1]}')
    
    comp = ComparisonService(s)
    compare_result = comp.compare(ids)
    print(f'   Overlap: {compare_result["overlap_count"]} controls')
    print(f'   Unique to {result["recommendations"][0]["code"]}: {compare_result["unique_control_count"][ids[0]]}')
    print(f'   Unique to {result["recommendations"][1]["code"]}: {compare_result["unique_control_count"][ids[1]]}')

print()
print('ALL TESTS PASSED')
s.close()
