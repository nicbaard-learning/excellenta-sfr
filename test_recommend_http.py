"""Verify the 7 BM filter recommendations work via HTTP against a live deployment.

Usage:
    python test_recommend_http.py https://your-app.onrender.com

Run this AFTER deploying to Render and before marking the deployment as complete.
Tests the /api/recommend/frameworks endpoint for each business model.
"""

import sys
import time
import urllib.request
import urllib.error
import json

EXPECTED_MIN = {
    "PAYMENT": 2,
    "HEALTHTECH": 5,
    "SAAS": 17,
    "AIMAACHINELEARNING": 4,
    "CONSULTING": 5,
    "EDTECH": 2,
    "FINTECH": 2,
}


def check(endpoint: str) -> tuple[int, list[dict]]:
    """Hit an endpoint and return (total, recommendations)."""
    try:
        with urllib.request.urlopen(endpoint, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data["total"], data["recommendations"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200] if e.fp else ""
        print(f"  HTTP {e.code}: {body}")
        return -1, []
    except Exception as e:
        print(f"  ERROR: {e}")
        return -1, []


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <base_url>")
        print(f"  e.g. {sys.argv[0]} https://sfr.onrender.com")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    print(f"Testing against: {base}")
    print()

    # --- Health check first ---
    print("=== Health Check ===")
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=10) as resp:
            print(f"  /health → {json.loads(resp.read().decode())}")
    except Exception as e:
        print(f"  /health FAILED: {e}")
        sys.exit(1)
    print()

    # --- 7 BM filter tests ---
    print("=== Business Model Filter Tests ===")
    all_ok = True
    for bm, expected_min in sorted(EXPECTED_MIN.items()):
        url = f"{base}/api/recommend/frameworks"
        body = json.dumps({"business_model": bm}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        total, recs = check(req)
        status = "OK" if total >= expected_min else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  {bm:<22}: {total:>2} results (expected >={expected_min}) [{status}]")

    # --- Combined filter ---
    print()
    print("=== Combined Filter ===")
    url = f"{base}/api/recommend/frameworks"
    body = json.dumps({"business_model": "SAAS", "jurisdiction": "US"}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    total, recs = check(req)
    print(f"  SAAS + US: {total} results")
    if recs:
        print(f"    First: {recs[0]['code']} – {recs[0]['name']}")

    print()
    if all_ok:
        print("ALL TESTS PASSED ✅")
    else:
        print("SOME TESTS FAILED ❌")
        sys.exit(1)


if __name__ == "__main__":
    main()
