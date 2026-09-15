#!/usr/bin/env python3
"""Load Croatian INSPIRE address GML files into a SpatiaLite database."""

import os
import sys
import time
import xml.etree.ElementTree as ET

import spatialite

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data", "extracted")
DB_PATH = os.path.join(PROJECT_DIR, "data", "db", "addresses.sqlite")

NS = {
    "ad": "http://inspire.ec.europa.eu/schemas/ad/4.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "gn": "http://inspire.ec.europa.eu/schemas/gn/4.0",
    "base": "http://inspire.ec.europa.eu/schemas/base/3.3",
    "xlink": "http://www.w3.org/1999/xlink",
}
#referenca na koji nacin se parsiraju i sprema nova tablica

def iterparse_members(path, tag_localname):
    """Stream-parse GML, yielding one element per wfs:member child and freeing memory."""
    full_tag = f"{{{NS['ad']}}}{tag_localname}"
    context = ET.iterparse(path, events=("end",))
    for event, elem in context:
        if elem.tag == full_tag:
            yield elem
            elem.clear()


def parse_inspire_id(elem):
    node = elem.find(".//base:Identifier/base:localId", NS)
    return node.text if node is not None else None


def parse_name_text(elem, name_path):
    node = elem.find(f"{name_path}//gn:SpellingOfName/gn:text", NS)
    return node.text if node is not None else None


def progress(count, total, label, t0):
    elapsed = time.time() - t0
    pct = count / total * 100 if total else 0
    rate = count / elapsed if elapsed > 0 else 0
    print(f"\r  {label}: {count:,}/{total:,} ({pct:.1f}%) [{rate:,.0f}/s]", end="", flush=True)


def load_postal_descriptors(db, path, total=900):
    print(f"  PostalDescriptor ({total:,} expected)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS postal_descriptor (
            gml_id TEXT PRIMARY KEY,
            local_id TEXT,
            post_name TEXT,
            post_code TEXT,
            valid_from TEXT
        )
    """)
    rows = []
    t0 = time.time()
    for elem in iterparse_members(path, "PostalDescriptor"):
        gml_id = elem.get(f"{{{NS['gml']}}}id")
        local_id = parse_inspire_id(elem)
        post_name = parse_name_text(elem, ".//ad:postName")
        post_code_node = elem.find(".//ad:postCode", NS)
        post_code = post_code_node.text if post_code_node is not None else None
        valid_from_node = elem.find(".//ad:validFrom", NS)
        valid_from = valid_from_node.text if valid_from_node is not None else None
        rows.append((gml_id, local_id, post_name, post_code, valid_from))
        if len(rows) % 100 == 0:
            progress(len(rows), total, "PostalDescriptor", t0)

    db.executemany(
        "INSERT OR IGNORE INTO postal_descriptor VALUES (?,?,?,?,?)", rows
    )
    db.commit()
    print(f"\r  PostalDescriptor: {len(rows):,}/{total:,} (100.0%) done in {time.time()-t0:.1f}s")


def load_admin_unit_names(db, path, total=6760):
    print(f"  AdminUnitName ({total:,} expected)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS admin_unit_name (
            gml_id TEXT PRIMARY KEY,
            local_id TEXT,
            alt_id TEXT,
            name TEXT,
            level TEXT,
            valid_from TEXT
        )
    """)
    rows = []
    t0 = time.time()
    for elem in iterparse_members(path, "AdminUnitName"):
        gml_id = elem.get(f"{{{NS['gml']}}}id")
        local_id = parse_inspire_id(elem)
        alt_node = elem.find("ad:alternativeIdentifier", NS)
        alt_id = alt_node.text if alt_node is not None else None
        name = parse_name_text(elem, ".//ad:name")
        level_node = elem.find("ad:level", NS)
        level = level_node.get(f"{{{NS['xlink']}}}title") if level_node is not None else None
        valid_from_node = elem.find("ad:validFrom", NS)
        valid_from = valid_from_node.text if valid_from_node is not None else None
        rows.append((gml_id, local_id, alt_id, name, level, valid_from))
        if len(rows) % 500 == 0:
            progress(len(rows), total, "AdminUnitName", t0)

    db.executemany(
        "INSERT OR IGNORE INTO admin_unit_name VALUES (?,?,?,?,?,?)", rows
    )
    db.commit()
    print(f"\r  AdminUnitName: {len(rows):,}/{total:,} (100.0%) done in {time.time()-t0:.1f}s")


def load_thoroughfare_names(db, path, total=54425):
    print(f"  ThoroughfareName ({total:,} expected)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS thoroughfare_name (
            gml_id TEXT PRIMARY KEY,
            local_id TEXT,
            alt_id TEXT,
            name TEXT,
            valid_from TEXT
        )
    """)
    rows = []
    t0 = time.time()
    for elem in iterparse_members(path, "ThoroughfareName"):
        gml_id = elem.get(f"{{{NS['gml']}}}id")
        local_id = parse_inspire_id(elem)
        alt_node = elem.find("ad:alternativeIdentifier", NS)
        alt_id = alt_node.text if alt_node is not None else None
        name = parse_name_text(elem, ".//ad:name//ad:ThoroughfareNameValue/ad:name")
        if name is None:
            name = parse_name_text(elem, ".//ad:name")
        valid_from_node = elem.find("ad:validFrom", NS)
        valid_from = valid_from_node.text if valid_from_node is not None else None
        rows.append((gml_id, local_id, alt_id, name, valid_from))
        if len(rows) % 5000 == 0:
            progress(len(rows), total, "ThoroughfareName", t0)

    db.executemany(
        "INSERT OR IGNORE INTO thoroughfare_name VALUES (?,?,?,?,?)", rows
    )
    db.commit()
    print(f"\r  ThoroughfareName: {len(rows):,}/{total:,} (100.0%) done in {time.time()-t0:.1f}s")


def load_addresses(db, path, total=1679882):
    print(f"  Address ({total:,} expected)")
    db.execute("SELECT InitSpatialMetaData(1)")
    db.execute("""
        CREATE TABLE IF NOT EXISTS address (
            gml_id TEXT PRIMARY KEY,
            local_id TEXT,
            alt_identifier TEXT,
            house_number TEXT,
            valid_from TEXT,
            thoroughfare_ref TEXT,
            postal_ref TEXT,
            admin_unit_ref1 TEXT,
            admin_unit_ref2 TEXT
        )
    """)
    db.execute("""
        SELECT AddGeometryColumn('address', 'geom', 3035, 'POINT', 'XY')
    """)

    BATCH = 10000
    batch = []
    count = 0
    t0 = time.time()

    for elem in iterparse_members(path, "Address"):
        gml_id = elem.get(f"{{{NS['gml']}}}id")
        local_id = parse_inspire_id(elem)

        alt_node = elem.find("ad:alternativeIdentifier", NS)
        alt_identifier = alt_node.text if alt_node is not None else None

        designator_node = elem.find(".//ad:LocatorDesignator/ad:designator", NS)
        house_number = designator_node.text if designator_node is not None else None

        valid_from_node = elem.find("ad:validFrom", NS)
        valid_from = valid_from_node.text if valid_from_node is not None else None

        pos_node = elem.find(".//gml:Point/gml:pos", NS)
        x, y = None, None
        if pos_node is not None and pos_node.text:
            parts = pos_node.text.strip().split()
            if len(parts) == 2:
                y, x = float(parts[0]), float(parts[1])

        components = elem.findall("ad:component", NS)
        thoroughfare_ref = None
        postal_ref = None
        admin_refs = []
        for comp in components:
            href = comp.get(f"{{{NS['xlink']}}}href", "")
            ref = href.lstrip("#")
            if ref.startswith("ThoroughfareName"):
                thoroughfare_ref = ref
            elif ref.startswith("PostalDescriptor"):
                postal_ref = ref
            elif ref.startswith("AdminUnitName"):
                admin_refs.append(ref)

        admin1 = admin_refs[0] if len(admin_refs) > 0 else None
        admin2 = admin_refs[1] if len(admin_refs) > 1 else None

        if x is not None and y is not None:
            geom_wkt = f"POINT({x} {y})"
        else:
            geom_wkt = None

        batch.append((
            gml_id, local_id, alt_identifier, house_number, valid_from,
            thoroughfare_ref, postal_ref, admin1, admin2, geom_wkt
        ))

        if len(batch) >= BATCH:
            _insert_address_batch(db, batch)
            count += len(batch)
            progress(count, total, "Address", t0)
            batch = []

    if batch:
        _insert_address_batch(db, batch)
        count += len(batch)

    db.commit()
    print(f"\r  Address: {count:,}/{total:,} (100.0%) done in {time.time()-t0:.1f}s")


def _insert_address_batch(db, batch):
    db.executemany("""
        INSERT OR IGNORE INTO address
        (gml_id, local_id, alt_identifier, house_number, valid_from,
         thoroughfare_ref, postal_ref, admin_unit_ref1, admin_unit_ref2, geom)
        VALUES (?,?,?,?,?,?,?,?,?, GeomFromText(?, 3035))
    """, batch)


def create_indexes(db):
    print("  Creating indexes...")
    db.execute("CREATE INDEX IF NOT EXISTS idx_address_thoroughfare ON address(thoroughfare_ref)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_address_postal ON address(postal_ref)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_address_admin1 ON address(admin_unit_ref1)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_address_admin2 ON address(admin_unit_ref2)")
    db.execute("SELECT CreateSpatialIndex('address', 'geom')")
    db.commit()


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing {DB_PATH}")

    print(f"Creating database: {DB_PATH}\n")

    with spatialite.connect(DB_PATH) as db:
        load_postal_descriptors(db, os.path.join(DATA_DIR, "PostalDescriptor.gml"))
        load_admin_unit_names(db, os.path.join(DATA_DIR, "AdminUnitName.gml"))
        load_thoroughfare_names(db, os.path.join(DATA_DIR, "ThoroughfareName.gml"))
        load_addresses(db, os.path.join(DATA_DIR, "Address.gml"))
        create_indexes(db)

    print(f"\nDone. Database: {DB_PATH}")


if __name__ == "__main__":
    main()
