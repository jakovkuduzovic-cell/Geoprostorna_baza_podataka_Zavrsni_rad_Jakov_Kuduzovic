#!/usr/bin/env python3
"""Describe the addresses database structure and the alt_identifier parsing strategy.

The alt_identifier column in the address table contains the full address as a single
string with the pattern:

    <street_name> <house_number_full> <settlement> <zip_code> <city>

Examples:
    "Brežna ulica 33 Andraševec 49243 Oroslavje"
    "Ulica hrvatskih branitelja 45A Bartolovci 35252 Sibinj"
    "Bana Jelačića 64 Bakić 33520 Slatina"

The house_number column from the GML (designator) contains only the numeric part
(e.g. "45" for "45A"). We can use it as a pivot to split the string:

    1. Find the position of ' <house_number>' in alt_identifier
    2. Everything BEFORE that position = street_name
    3. From that position to the next space = house_number_full (may include letter suffix)
    4. The REMAINDER after house_number_full = '<settlement> <zip> <city>'
    5. The zip code is always 5 digits — we can find it to separate settlement from zip+city

The restructured_addresses.sqlite database will have a single table with columns:
    - street_name       (e.g. "Brežna ulica")
    - house_number_full (e.g. "45A")
    - house_number      (e.g. "45", numeric only from original designator)
    - settlement        (e.g. "Andraševec")
    - zip_code          (e.g. "49243")
    - city              (e.g. "Oroslavje")
    - geom              (original point geometry, EPSG:3035)
    - gml_id            (original ID for traceability)
"""
#skripta koja pise smjernice kako pristupiti rjesenju problema, kako je strukturirana baza podataka i na koji nacin ce se parsirato podaci
import os
import spatialite
#lociranje direktorija di je skripta
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_DIR, "data", "db", "addresses.sqlite")


def main():
    with spatialite.connect(DB_PATH) as db:
        total = db.execute("SELECT COUNT(*) FROM address").fetchone()[0]
        print(f"Database: {DB_PATH}")
        print(f"Total addresses: {total:,}\n")

        print("=== Tables ===")
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'idx_%' "
            "AND name NOT LIKE 'geometry_columns%' AND name NOT LIKE 'spatial_ref_sys%' "
            "AND name NOT LIKE 'views_%' AND name NOT LIKE 'virts_%' "
            "AND name NOT LIKE 'spatialite_%' AND name NOT LIKE 'data_%' "
            "AND name NOT LIKE 'sql_%' AND name NOT LIKE 'Spatial%' "
            "AND name NOT LIKE 'Elementary%' AND name NOT LIKE 'KNN%'"
        ).fetchall()
        for (t,) in tables:
            count = db.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            cols = db.execute(f"PRAGMA table_info([{t}])").fetchall()
            col_names = [c[1] for c in cols]
            print(f"\n  {t} ({count:,} rows)")
            print(f"    columns: {', '.join(col_names)}")

        print("\n\n=== alt_identifier structure ===")
        print("Pattern: <street_name> <house_number_full> <settlement> <zip_code> <city>\n")

        print("Sample addresses:")
        rows = db.execute("""
            SELECT alt_identifier, house_number FROM address
            WHERE alt_identifier IS NOT NULL
            ORDER BY RANDOM() LIMIT 10
        """).fetchall()
        for alt, hn in rows:
            print(f"  {alt!r}  (designator={hn!r})")

        print("\n\n=== Parsing strategy ===")
        print("Using INSTR + SUBSTR in SQLite:")#INSTR trazi poziciju cega se trazi, 
        print("  1. pos = INSTR(alt_identifier, ' ' || house_number)")
        print("  2. street_name = SUBSTR(alt_identifier, 1, pos - 1)")
        print("  3. remainder = SUBSTR(alt_identifier, pos + 1)  -> 'HN_full settlement ZIP city'")
        print("  4. house_number_full = first token of remainder (up to next space)")
        print("  5. rest = after house_number_full  -> 'settlement ZIP city'")
        print("  6. Find 5-digit zip in rest to split settlement from zip+city")

        # Stats on suffix letters
        with_suffix = db.execute("""
            SELECT COUNT(*) FROM address
            WHERE alt_identifier NOT LIKE '%' || ' ' || house_number || ' ' || '%'
              AND alt_identifier IS NOT NULL
        """).fetchone()[0]
        print(f"\n  Addresses with letter suffix (e.g. 45A): {with_suffix:,} / {total:,} ({with_suffix/total*100:.1f}%)")

        no_hn = db.execute("SELECT COUNT(*) FROM address WHERE house_number IS NULL OR house_number = ''").fetchone()[0]
        print(f"  Addresses with no house_number: {no_hn:,}")


if __name__ == "__main__":
    main()
