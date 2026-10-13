#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -B -m py_compile audit_transport.py audit_successor.py test_audit_transport.py test_audit_successor.py
python -B -m unittest -v test_audit_transport.py test_audit_successor.py
python -B audit_transport.py --verify-finding FINDING.json
if [[ -n "${TITAN_V3_PACKET:-}" ]]; then
  set +e
  python -B audit_transport.py --packet "$TITAN_V3_PACKET" --output RAW-REPORT.json
  status=$?
  set -e
  [[ $status -eq 3 ]] || exit "$status"
  echo "RAW PACKET HOLD REPRODUCED"
fi
