"""Append-only ESS/IAM enrollment-period timeline and conclusions."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os

try:
    from .canonical import (
        AUTHORITY,
        CELLS,
        MANIFEST_FIELDS,
        REGISTER_FIELDS,
        SCHEMA,
    )
except ImportError:
    from canonical import (
        AUTHORITY,
        CELLS,
        MANIFEST_FIELDS,
        REGISTER_FIELDS,
        SCHEMA,
    )

class DemoError(Exception):
    """Timeline cannot be advanced without inventing or rewriting history."""


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def empty_register_row():
    return {k: "" for k in REGISTER_FIELDS}


def write_csv(fields, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue()


def read_csv(text, fields):
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != fields:
        raise DemoError("CSV fields %r do not match published contract %r" % (reader.fieldnames, fields))
    for row in reader:
        rows.append({k: row.get(k, "") for k in fields})
    return rows


def conclude(register_rows):
    """Derive cell states from the current snapshot. Does not edit rows."""
    by_cell = {(g, a): [] for g, a in CELLS}
    for row in register_rows:
        key = (row["group"], row["area"])
        if key in by_cell:
            by_cell[key].append(row)
    out = []
    for cell in CELLS:
        rows = by_cell[cell]
        states = [r["evidence_state"] for r in rows]
        if any(s == "SUPPORTING" for s in states):
            status = "supported"
        elif any(s == "HOLD" for s in states) or not rows:
            status = "HOLD"
        else:
            status = "HOLD"
        out.append(
            {
                "group": cell[0],
                "area": cell[1],
                "status": status,
                "evidence_ids": [r["evidence_id"] for r in rows],
                "row_states": states,
            }
        )
    return out


def assert_history_preserved(earlier_rows, later_rows):
    if len(later_rows) < len(earlier_rows):
        raise DemoError("later stage dropped earlier evidence rows")
    for i, row in enumerate(earlier_rows):
        if later_rows[i] != row:
            raise DemoError("stage history rewritten at row %d (%s)" % (i, row.get("evidence_id")))


def load_stage(path):
    with open(os.path.join(path, "manifest.csv"), encoding="utf-8") as fh:
        manifest = read_csv(fh.read(), MANIFEST_FIELDS)
    with open(os.path.join(path, "register.csv"), encoding="utf-8") as fh:
        register = read_csv(fh.read(), REGISTER_FIELDS)
    with open(os.path.join(path, "events.jsonl"), encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh if line.strip()]
    conclusions = conclude(register)
    return {
        "schema": SCHEMA,
        "manifest": manifest,
        "register": register,
        "events": events,
        "conclusions": conclusions,
        "authority": dict(AUTHORITY),
    }


def compare_stages(stage1, stage2):
    assert_history_preserved(stage1["register"], stage2["register"])
    assert_history_preserved(stage1["manifest"], stage2["manifest"])
    assert_history_preserved(stage1["events"], stage2["events"])
    c1 = { (c["group"], c["area"]): c for c in stage1["conclusions"] }
    c2 = { (c["group"], c["area"]): c for c in stage2["conclusions"] }
    changed = []
    for cell in CELLS:
        if c1[cell]["status"] != c2[cell]["status"]:
            changed.append(
                {
                    "cell": "%s/%s" % cell,
                    "from": c1[cell]["status"],
                    "to": c2[cell]["status"],
                    "new_evidence": [
                        eid
                        for eid in c2[cell]["evidence_ids"]
                        if eid not in c1[cell]["evidence_ids"]
                    ],
                }
            )
    return {"history_preserved": True, "conclusion_changes": changed}
