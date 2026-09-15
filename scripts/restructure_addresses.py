#!/usr/bin/env python3
"""Restructure addresses by splitting alt_identifier into separate columns.

Reads from data/db/addresses.sqlite (address table) and creates a new
data/db/restructured_addresses.sqlite with the alt_identifier parsed into:

    street_name, house_number_full, house_number, settlement, zip_code, city

Parsing uses INSTR/SUBSTR with the designator (house_number) as the pivot point
to split the combined address string.
"""

import os
import time
import spatialite

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SRC_DB = os.path.join(PROJECT_DIR, "data", "db", "addresses.sqlite")
DST_DB = os.path.join(PROJECT_DIR, "data", "db", "restructured_addresses.sqlite")
#Lociranje i kreiranje putanje do baze podataka, addressess.sqlite
#Tako da skripta uvijek zna tocno odakle citati i gdje pisati
#Stvara funkciju koja ispisuje liniju koja se uživo ažurira i prikazuje napredak (obrađeni redci / ukupno, %) te koliko brzo napreduje.
def progress(count, total, t0):
    elapsed = time.time() - t0
    pct = count / total * 100 if total else 0
    rate = count / elapsed if elapsed > 0 else 0
    print(f"\r  {count:,}/{total:,} ({pct:.1f}%) [{rate:,.0f}/s]", end="", flush=True)

#čita svaku adresu iz stare baze podataka, rastavlja tekst adrese svake od njih u zasebne stupce, 
#upisuje rezultate u novu prostornu (spatial) bazu podataka u serijama (batchevima), zatim je indeksira i ispisuje uzorke redaka radi provjere."

def main():
    if not os.path.exists(SRC_DB):
        print(f"Source database not found: {SRC_DB}")
        return

    if os.path.exists(DST_DB):
        os.remove(DST_DB)
        print(f"Removed existing {DST_DB}")

    print(f"Source: {SRC_DB}")
    print(f"Target: {DST_DB}\n")

    with spatialite.connect(DST_DB) as dst:
        dst.execute("SELECT InitSpatialMetaData(1)")

        dst.execute(f"ATTACH DATABASE '{SRC_DB}' AS src")

        total = dst.execute("SELECT COUNT(*) FROM src.address").fetchone()[0]
        print(f"Total source addresses: {total:,}\n")

        dst.execute("""
            CREATE TABLE address (
                gml_id TEXT PRIMARY KEY,
                street_name TEXT,
                house_number_full TEXT,
                house_number TEXT,
                settlement TEXT,
                zip_code TEXT,
                city TEXT
            )
        """)
        dst.execute("SELECT AddGeometryColumn('address', 'geom', 3035, 'POINT', 'XY')")

        # alt_identifier ima obrazac:
        #   <ulica> <HN_full> <naselje> <ZIP> <grad>
        #
        # Strategija:
        #   pos       = pozicija znaka ' ' || house_number unutar alt_identifier
        #   street    = sve prije pos
        #   remainder = sve nakon ulice + razmak -> "HN_full naselje ZIP grad"
        #   hn_full   = prvi token iz remainder (do sljedećeg razmaka)
        #   rest      = ono nakon hn_full -> "naselje ZIP grad"
        #   zip_pos   = pronađi obrazac petoznamenkastog poštanskog broja skenirajući od kraja
        #               poštanski broj uvijek je prije njega razmak, a poslije njega razmak
        #   settlement = sve prije zip unutar rest
        #   city       = sve nakon zip unutar rest

        print("Parsing and inserting addresses...")
        t0 = time.time()

        BATCH = 50000
        offset = 0
        inserted = 0

        while offset < total:
            rows = dst.execute(f"""
                SELECT gml_id, alt_identifier, house_number, geom
                FROM src.address
                LIMIT {BATCH} OFFSET {offset}
            """).fetchall()

            if not rows:
                break

            parsed = []
            for gml_id, alt, hn, geom in rows:
                street, hn_full, settlement, zip_code, city = parse_address(alt, hn)
                parsed.append((gml_id, street, hn_full, hn, settlement, zip_code, city, geom))

            dst.executemany("""
                INSERT OR IGNORE INTO address
                (gml_id, street_name, house_number_full, house_number, settlement, zip_code, city, geom)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, parsed)
            dst.commit()

            inserted += len(rows)
            offset += BATCH
            progress(inserted, total, t0)

        elapsed = time.time() - t0
        print(f"\r  {inserted:,}/{total:,} (100.0%) done in {elapsed:.1f}s")

        print("\nCreating indexes...")
        dst.execute("CREATE INDEX idx_street ON address(street_name)")
        dst.execute("CREATE INDEX idx_settlement ON address(settlement)")
        dst.execute("CREATE INDEX idx_zip ON address(zip_code)")
        dst.execute("CREATE INDEX idx_city ON address(city)")
        dst.execute("SELECT CreateSpatialIndex('address', 'geom')")
        dst.commit()

        print("\nSample results:")
        sample = dst.execute("""
            SELECT street_name, house_number_full, house_number, settlement, zip_code, city
            FROM address ORDER BY RANDOM() LIMIT 10
        """).fetchall()
        print(f"  {'street_name':<35s} {'hn_full':>8s} {'hn':>5s} {'settlement':<25s} {'zip':>5s} {'city'}")
        print(f"  {'-'*35} {'-'*8} {'-'*5} {'-'*25} {'-'*5} {'-'*20}")
        for street, hn_full, hn, sett, zc, city in sample:
            print(f"  {street or '':<35s} {hn_full or '':>8s} {hn or '':>5s} {sett or '':<25s} {zc or '':>5s} {city or ''}")

        dst.execute("DETACH DATABASE src")

    size_mb = os.path.getsize(DST_DB) / 1024 / 1024
    print(f"\nDone. Output: {DST_DB} ({size_mb:.0f} MB)")


def parse_address(alt, house_number):
    """Split 'street HN_full settlement ZIP city' using house_number as pivot."""
    if not alt or not house_number:
        return (alt, house_number, None, None, None)

    marker = f" {house_number}"
    pos = alt.find(marker)

    if pos == -1:
        return (alt, house_number, None, None, None)

    street_name = alt[:pos]

    remainder = alt[pos + 1:]  # "HN_full settlement ZIP city"

    space_after_hn = remainder.find(" ")
    if space_after_hn == -1:
        return (street_name, remainder, None, None, None)

    hn_full = remainder[:space_after_hn]
    rest = remainder[space_after_hn + 1:]  # "settlement ZIP city"

    # Find the 5-digit zip code — scan for a sequence of 5 digits preceded by space
    zip_code = None
    settlement = None
    city = None

    parts = rest.split(" ")
    zip_idx = None
    for i, p in enumerate(parts):
        if len(p) == 5 and p.isdigit():
            zip_idx = i
            break

    if zip_idx is not None:
        settlement = " ".join(parts[:zip_idx])
        zip_code = parts[zip_idx]
        city = " ".join(parts[zip_idx + 1:])
    else:
        settlement = rest

    return (street_name, hn_full, settlement, zip_code, city)


if __name__ == "__main__":
    main()
#Funkcija uzima jedan dugačak string adrese i poznati kućni broj, 
#te koristi kućni broj kao orijentir (landmark) da bi rastavila string na dijelove — prvo odvaja naziv ulice (dio prije kućnog broja), zatim sam kućni broj, 
#a onda traži petoznamenkasti poštanski broj u preostalom tekstu kako bi razdvojila naselje (dio prije poštanskog broja) od grada (dio poslije poštanskog broja). 
#Ako se neki od očekivanih dijelova ne može pronaći tijekom postupka, funkcija se elegantno predaje (ne baca grešku) i vraća None za dijelove koje nije uspjela odrediti.