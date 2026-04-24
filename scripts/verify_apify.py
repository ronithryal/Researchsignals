"""
Confirms APIFY_API_TOKEN in .env is valid.
Run: python scripts/verify_apify.py
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("APIFY_API_TOKEN", "")
if not token:
    print("FAIL — APIFY_API_TOKEN is empty in .env")
    raise SystemExit(1)

resp = httpx.get(
    "https://api.apify.com/v2/users/me",
    params={"token": token},
    timeout=10,
)
if resp.status_code == 200:
    data = resp.json().get("data", {})
    print(f"OK — Apify account: {data.get('username')} / plan: {data.get('plan', {}).get('id')}")
else:
    print(f"FAIL — Apify returned {resp.status_code}: {resp.text[:200]}")
    raise SystemExit(1)
