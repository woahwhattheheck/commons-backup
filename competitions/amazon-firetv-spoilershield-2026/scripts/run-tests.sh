#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
node "$ROOT/tests/core.test.mjs"
PYTHONPATH="$ROOT/backend" python3 -m unittest -v "$ROOT/backend/test_lambda_function.py"
python3 "$ROOT/scripts/build_package.py"
python3 - <<'PY' "$ROOT"
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
z = root / "dist/spoilershield-firetv-webapp.zip"
with zipfile.ZipFile(z) as f:
    names = set(f.namelist())
required = {"index.html","styles.css","core.js","demo_episode.js","config.js","app.js","PACKAGE-MANIFEST.json"}
assert names == required, (names, required)
print("Package structure PASS")
PY
