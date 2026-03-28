"""
Update leads distribution cache from CRM export CSV.

Usage:
    python update_leads.py <csv_path>

Unlike sales (which merges incrementally), leads data is a summary report
so each update fully replaces the cache with the new export.
"""
import json
import sys
import os
import pandas as pd
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads_cache.json")


def main():
    if len(sys.argv) < 2:
        print("Update leads distribution cache from CRM export CSV.")
        print()
        print("Usage: python update_leads.py <csv_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    print(f"CSV loaded: {len(df):,} sources from {os.path.basename(csv_path)}")

    records = []
    for _, row in df.iterrows():
        r = {}
        for col in df.columns:
            val = row[col]
            r[col] = None if pd.isna(val) else val
        records.append(r)

    data = {
        "records": records,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_sources": len(records),
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = os.path.getsize(CACHE_FILE) / 1024
    print(f"Cache saved: {len(records):,} sources ({size_kb:.1f} KB) -> {CACHE_FILE}")


if __name__ == "__main__":
    main()
