#!/usr/bin/env python3
"""Observe duplicate-import queue behavior with explicit synthetic unit stubs.

Use with either a predecessor or repaired source directory. This does not run
or replace the real parent compiler, and never establishes integration evidence.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    args = parser.parse_args()
    source = args.source_directory.resolve()
    if not (source / "handoff_review.py").is_file():
        parser.error("source directory must contain handoff_review.py")
    sys.path.insert(0, str(source))
    hr = importlib.import_module("handoff_review")
    fixtures = importlib.import_module("test_handoff_review")
    report = fixtures.report_fixture()
    handoff = hr._blank_handoff(report)
    for row in handoff["cell_notes"]:
        row.update(disposition="NEEDS_EVIDENCE", analyst_note="FICTIONAL: supporting record still requested.")
    observations = []
    with patch.object(hr, "_parent_integrity", side_effect=fixtures.integrity_fixture):
        for count in (1, 2, 20):
            result = hr.reconcile(report, [(f"label-{i}", copy.deepcopy(handoff)) for i in range(count)])
            observations.append({"input_count":result["input_count"],
                "distinct_handoff_content_count":result["distinct_handoff_content_count"],
                "review_queue_cells":len(result["review_queue"]), "reason_counts":result["reason_counts"],
                "preserved_entries_in_each_cell":len(result["assessment_cells"][0]["entries"]),
                "authority":result["authority"], "reconciliation_sha256":result["reconciliation_sha256"]})
    raw = (source / "handoff_review.py").read_bytes()
    print(json.dumps({"scope":"SYNTHETIC UNIT REPRODUCTION; parent integrity explicitly mocked, not real integration",
        "source_git_blob":hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "source_sha256":hashlib.sha256(raw).hexdigest(), "observations":observations}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
