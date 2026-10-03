#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m compileall -q voice_harness tests run_validation.py verify_artifacts.py serve_viewer.py
python3 -I -S run_validation.py --out results/clean_reproduction
python3 -I -S verify_artifacts.py results/clean_reproduction
if command -v node >/dev/null 2>&1; then
  node --check viewer/app.js
  python3 -c 'import json; from pathlib import Path; from serve_viewer import bundle; Path("results/clean_reproduction/viewer_bundle.json").write_text(json.dumps(bundle(Path("results/clean_reproduction"))))'
  node tests/test_viewer_controls.js results/clean_reproduction/viewer_bundle.json > results/clean_reproduction/viewer_control_tests.json
  cat results/clean_reproduction/viewer_control_tests.json
else
  printf '%s\n' 'NOT RUN: optional Node.js viewer-control test (Node unavailable). Python evidence checks completed.'
fi
