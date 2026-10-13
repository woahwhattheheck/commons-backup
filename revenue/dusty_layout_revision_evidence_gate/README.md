# Layout Revision-to-Print Evidence Gate

A deterministic, **read-only** evidence gate for joining layout-design provenance to a completed field-print job. It is intentionally narrower than robot control, survey/layout certification, or field release.

## Evidence joined

For every job, the gate binds:

- BIM/CAD SHA-256 and design revision;
- trade signoffs bound to that exact design hash/revision;
- unit and scale metadata;
- control-point survey version and SHA-256;
- station-verification result bound to those control points;
- Portal preview design binding and QR checksum;
- expected printer/app versions; and
- final job report evidence.

A clean packet is content-addressed with `packet_sha256`. The entire batch is content-addressed with `input_sha256` and `receipt_sha256`.

## Exact exception classes

The gate emits only these named evidence exceptions:

1. `DESIGN_HASH_MISMATCH`
2. `DESIGN_REVISION_MISMATCH`
3. `TRADE_SIGNOFF_STALE`
4. `UNIT_SCALE_MISMATCH`
5. `CONTROL_POINT_SURVEY_MISMATCH`
6. `STATION_VERIFICATION_FAILED`
7. `PORTAL_QR_MISMATCH`
8. `RUNTIME_REPORT_MISMATCH`

A job with independent defects may emit more than one exact reason. The acceptance corpus deliberately has one defect per bad job so its 24 bad jobs yield exactly 24 `job_id + reason` exceptions.

## Acceptance corpus

`acceptance_fixture.py` deterministically creates 120 synthetic jobs:

- 96 clean jobs;
- 24 unique bad jobs;
- exactly 3 bad jobs for each of the eight reason classes; and
- zero robot/control commands.

Run:

```bash
python revenue/dusty_layout_revision_evidence_gate/acceptance_fixture.py --output /tmp/dusty-120.json
python revenue/dusty_layout_revision_evidence_gate/gate.py /tmp/dusty-120.json --output /tmp/dusty-receipt.json
python -m unittest discover -s revenue/dusty_layout_revision_evidence_gate -p 'test_*.py' -v
python -O -m unittest discover -s revenue/dusty_layout_revision_evidence_gate -p 'test_*.py' -v
```

Expected acceptance receipt: `jobs_total=120`, `clean_count=96`, `exception_count=24`, every `reason_counts[...] == 3`, and `control_commands=[]`.

## Hash and custody rules

SHA-256 fields must be canonical lowercase 64-character hex. The gate rejects uppercase/noncanonical input instead of silently lowercasing or repairing evidence. Duplicate JSON keys, duplicate job IDs, unknown fields, malformed types, and ambiguous values fail closed.

CLI output is written atomically and refuses to overwrite its own input path. Identical valid input yields a byte-identical normalized receipt.

## Boundary

This module does **not** navigate or move a robot, initiate printing, configure trackers/stations, handle obstacles, delete files, approve models, certify survey/layout correctness, release field work, mutate project systems, or contact customers. It emits evidence packets and exact exception reasons only.
