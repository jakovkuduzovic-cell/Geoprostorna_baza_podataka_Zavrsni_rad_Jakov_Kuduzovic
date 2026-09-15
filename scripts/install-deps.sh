#!/usr/bin/env bash
set -euo pipefail

echo "Installing GDAL and libspatialite via Homebrew..."
brew install gdal libspatialite

echo ""
echo "Verifying installation..."
ogr2ogr --version
python3 -c "
import sqlite3
conn = sqlite3.connect(':memory:')
conn.enable_load_extension(True)
conn.load_extension('mod_spatialite')
print('SpatiaLite extension loads OK')
"

echo "Done."
