#!/usr/bin/env bash
set -e
echo "Reviewing and moving files..."
mkdir -p src/api src/core src/data_layer src/optimization/legacy
mkdir -p "src/api"
git mv -k "src/api/app/main.py" "src/api/main.py"
echo "# SKIP (exists): src/optimization/legacy/config.py -> src/core/config.py"
echo "# SKIP (exists): src/optimization/legacy/database.py -> src/data_layer/database.py"
mkdir -p "src/core"
git mv -k "src/optimization/legacy/geo_utils.py" "src/core/geo_utils.py"
mkdir -p "src/core"
git mv -k "src/optimization/legacy/models.py" "src/core/models.py"