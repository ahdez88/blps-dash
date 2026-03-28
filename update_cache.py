"""
BLPS Data Cache Updater
Fetches campaign insights from Meta API and saves to data_cache.json.
Run locally to update the historical data cache.

Usage:
  python update_cache.py          # Update last 14 days only (fast)
  python update_cache.py --full   # Full rebuild from Jan 2025 (slow, first time only)
"""

import requests
import json
import time
import sys
import os
from datetime import datetime, timedelta

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = ""
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("META_ACCESS_TOKEN="):
                TOKEN = line.strip().split("=", 1)[1]

AD_ACCOUNTS = {
    "act_5302103159848505": "BL AC 01",
    "act_234789602496820": "BL AC 2",
    "act_1542649216514133": "BL AC 3",
    "act_836269185004901": "BL AC 2b",
    "act_938706057445508": "BL-plastic",
    "act_811057274877067": "BLPS-LIDERIFY",
}

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache.json")
HISTORICAL_CUTOFF_DAYS = 14  # Only refresh this many days on incremental update


def fetch_all_pages(url, params, max_retries=3):
    all_data = []
    while url:
        for attempt in range(max_retries):
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                break
            if resp.status_code == 403 and "request limit" in resp.text.lower():
                wait = 15 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    Error {resp.status_code}: {resp.text[:200]}")
                return all_data
        else:
            print(f"    Rate limit persisted after {max_retries} retries, skipping...")
            return all_data

        data = resp.json()
        all_data.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}
        time.sleep(0.5)
    return all_data


def fetch_insights(date_start, date_end):
    """Fetch campaign insights for all accounts in the given date range."""
    all_insights = []

    for account_id, account_name in AD_ACCOUNTS.items():
        print(f"  {account_name} ({account_id})...")

        insights = fetch_all_pages(
            f"{BASE_URL}/{account_id}/insights",
            {
                "fields": "campaign_id,campaign_name,objective,spend,impressions,reach,clicks,actions",
                "level": "campaign",
                "time_range": json.dumps({"since": date_start, "until": date_end}),
                "time_increment": 1,
                "limit": 500,
                "access_token": TOKEN,
            }
        )
        for row in insights:
            row["_account"] = account_name
        all_insights.extend(insights)
        print(f"    {len(insights)} rows")

        time.sleep(3)

    return all_insights


def load_cache():
    """Load existing cache if available."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"insights": [], "last_updated": None}


def save_cache(data):
    """Save cache to disk."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size_mb = os.path.getsize(CACHE_FILE) / (1024 * 1024)
    print(f"\nCache saved: {CACHE_FILE} ({size_mb:.1f} MB)")


def main():
    if not TOKEN:
        print("ERROR: No META_ACCESS_TOKEN found in .env")
        return

    full_rebuild = "--full" in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")

    if full_rebuild:
        print(f"=== FULL REBUILD: 2025-01-01 -> {today} ===")
        date_start = "2025-01-01"
        insights = fetch_insights(date_start, today)
        cache = {
            "insights": insights,
            "last_updated": today,
            "date_start": date_start,
            "date_end": today,
        }
    else:
        cache = load_cache()
        if not cache.get("insights"):
            print("No existing cache found. Run with --full first.")
            print("  python update_cache.py --full")
            return

        cutoff = (datetime.now() - timedelta(days=HISTORICAL_CUTOFF_DAYS)).strftime("%Y-%m-%d")
        print(f"=== INCREMENTAL UPDATE: {cutoff} -> {today} ===")
        print(f"  Existing cache: {len(cache['insights'])} rows, last updated {cache.get('last_updated', 'unknown')}")

        # Remove old rows within the refresh window
        old_insights = [r for r in cache["insights"] if r.get("date_start", "") < cutoff]
        print(f"  Keeping {len(old_insights)} historical rows (before {cutoff})")

        # Fetch fresh data for recent period
        new_insights = fetch_insights(cutoff, today)
        print(f"  Fetched {len(new_insights)} fresh rows")

        cache = {
            "insights": old_insights + new_insights,
            "last_updated": today,
            "date_start": cache.get("date_start", "2025-01-01"),
            "date_end": today,
        }

    print(f"\nTotal rows in cache: {len(cache['insights'])}")
    save_cache(cache)
    print("Done!")


if __name__ == "__main__":
    main()
