#!/usr/bin/env python3
"""Validate the restructured addresses database for missing/empty fields."""

import os
import spatialite

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_DIR, "data", "db", "restructured_addresses.sqlite")


def check_field(db, field, total):
    null_count = db.execute(
        f"SELECT COUNT(*) FROM address WHERE [{field}] IS NULL OR TRIM([{field}]) = ''"
    ).fetchone()[0]
    pct = null_count / total * 100 if total else 0
    status = "OK" if null_count == 0 else "MISSING"
    print(f"  {field:<25s} {null_count:>10,} empty/null ({pct:5.2f}%)  [{status}]")

    if null_count > 0 and null_count <= 20:
        rows = db.execute(
            f"SELECT gml_id, street_name, house_number_full, settlement, zip_code, city "
            f"FROM address WHERE [{field}] IS NULL OR TRIM([{field}]) = '' "
            f"LIMIT 10"
        ).fetchall()
        for r in rows:
            print(f"    {r}")
    elif null_count > 20:
        rows = db.execute(
            f"SELECT gml_id, street_name, house_number_full, settlement, zip_code, city "
            f"FROM address WHERE [{field}] IS NULL OR TRIM([{field}]) = '' "
            f"LIMIT 10"
        ).fetchall()
        for r in rows:
            print(f"    {r}")
        print(f"    ... and {null_count - 10:,} more")

    return null_count


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        return

    with spatialite.connect(DB_PATH) as db:
        total = db.execute("SELECT COUNT(*) FROM address").fetchone()[0]
        print(f"Database: {DB_PATH}")
        print(f"Total records: {total:,}\n")

        print("=== Field completeness ===")
        fields = ["street_name", "house_number_full", "house_number", "settlement", "zip_code", "city"]
        issues = {}
        for f in fields:
            count = check_field(db, f, total)
            if count > 0:
                issues[f] = count

        null_geom = db.execute("SELECT COUNT(*) FROM address WHERE geom IS NULL").fetchone()[0]
        pct = null_geom / total * 100 if total else 0
        status = "OK" if null_geom == 0 else "MISSING"
        print(f"  {'geom':<25s} {null_geom:>10,} empty/null ({pct:5.2f}%)  [{status}]")

        print(f"\n=== Summary ===")
        if not issues:
            print("  All fields are fully populated.")
        else:
            print(f"  {len(issues)} field(s) with missing values:")
            for f, c in issues.items():
                print(f"    {f}: {c:,} missing")

        print(f"\n=== Distinct value counts ===")
        for f in fields:
            distinct = db.execute(f"SELECT COUNT(DISTINCT [{f}]) FROM address WHERE [{f}] IS NOT NULL AND TRIM([{f}]) != ''").fetchone()[0]
            print(f"  {f:<25s} {distinct:>10,} distinct values")


if __name__ == "__main__":
    main()
