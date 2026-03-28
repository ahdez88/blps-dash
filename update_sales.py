"""
Update sales data cache from CRM export CSV.

Usage:
    python update_sales.py <csv_path>           # Merge new data with existing cache
    python update_sales.py <csv_path> --full     # Full rebuild (replace all data)

The cache file (sales_cache.json) is committed to the repo so the Streamlit
app loads it automatically without needing a file upload every session.
"""
import json
import sys
import os
import hashlib
import pandas as pd
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales_cache.json")


def record_key(r):
    """Generate unique key for a sales record (Invoice + Procedure + Date)."""
    parts = f"{r.get('Invoice', '')}|{r.get('Sales W Payments', '')}|{r.get('Sales Dates', '')}"
    return hashlib.md5(parts.encode()).hexdigest()


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"records": [], "last_updated": "", "total_records": 0}


def save_cache(records):
    data = {
        "records": records,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_records": len(records),
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    size_mb = os.path.getsize(CACHE_FILE) / 1024 / 1024
    print(f"Cache saved: {len(records):,} records ({size_mb:.1f} MB) -> {CACHE_FILE}")


def csv_to_records(csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    records = []
    for _, row in df.iterrows():
        r = {}
        for col in df.columns:
            val = row[col]
            r[col] = None if pd.isna(val) else val
        records.append(r)
    return records


def merge_records(existing, new):
    existing_keys = {record_key(r) for r in existing}
    added = 0
    for r in new:
        k = record_key(r)
        if k not in existing_keys:
            existing.append(r)
            existing_keys.add(k)
            added += 1
    return existing, added


def main():
    if len(sys.argv) < 2:
        print("Update sales data cache from CRM export CSV.")
        print()
        print("Usage:")
        print("  python update_sales.py <csv_path>          # Merge new data")
        print("  python update_sales.py <csv_path> --full    # Full rebuild")
        sys.exit(1)

    csv_path = sys.argv[1]
    full_mode = "--full" in sys.argv

    if not os.path.exists(csv_path):
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    new_records = csv_to_records(csv_path)
    print(f"CSV loaded: {len(new_records):,} records from {os.path.basename(csv_path)}")

    if full_mode:
        save_cache(new_records)
        print("Full rebuild complete.")
    else:
        cache = load_cache()
        existing = cache.get("records", [])
        print(f"Existing cache: {len(existing):,} records")
        merged, added = merge_records(existing, new_records)
        save_cache(merged)
        print(f"Merge complete: +{added:,} new records added")


if __name__ == "__main__":
    main()
