#!/usr/bin/env python3
"""Show a fictional requirement change without rewriting the prior evidence.

Uses secure_design's existing model. No live systems, network calls, scoring,
external publication, pricing, or independently verified security findings.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Sequence

import secure_design as sd

HERE = Path(__file__).resolve().parent
DEFAULT_REQUIREMENT = "SEC-REQ-SYN-02"
DEFAULT_DECISION = "DD-SYN-02"


def _selected(report: Dict[str, Any], requirement_id: str, decision_id: str) -> Dict[str, Any]:
    for row in report["links"]:
        if row["requirement_id"] == requirement_id and row["decision_id"] == decision_id:
            return row
    raise sd.SecureDesignError("the selected requirement-to-decision link does not exist")


def run_rehearsal(payload: Any, requirement_id: str = DEFAULT_REQUIREMENT,
                  decision_id: str = DEFAULT_DECISION) -> Dict[str, Any]:
    """Return three real-engine snapshots; do not modify the supplied records."""
    original = sd.assess(*sd.load_records(payload))
    selected = _selected(original, requirement_id, decision_id)
    if selected["state"] != sd.OBSERVED_PRACTICE:
        raise sd.SecureDesignError("choose a link with current observed-practice evidence")
    if selected["evidence_citing_a_future_version"]:
        raise sd.SecureDesignError("reconcile future-version citations before this rehearsal")

    records = copy.deepcopy(original)
    requirement = next(r for r in records["requirements"] if r["requirement_id"] == requirement_id)
    requirement["current_version"] += 1
    version = requirement["current_version"]
    change = "FICTIONAL REHEARSAL CHANGE: retain a decision-specific review reference."
    requirement["statement"] += " " + change
    requirement["change_history"].append(f"v{version}: {change}")
    revised = sd.assess(*sd.load_records(records))
    if _selected(revised, requirement_id, decision_id)["state"] != sd.TRACED_STALE:
        raise sd.SecureDesignError("revision did not produce the expected stale trace")

    used_ids = {e["evidence_id"] for e in records["evidence"]}
    suffix = 1
    evidence_id = f"EV-REHEARSAL-{suffix}"
    while evidence_id in used_ids:
        suffix += 1
        evidence_id = f"EV-REHEARSAL-{suffix}"
    records["evidence"].append({
        "evidence_id": evidence_id,
        "kind": "design_review_record",
        "requirement_id": requirement_id,
        "decision_id": decision_id,
        "flow_id": selected["flow_id"],
        "cites_requirement_version": version,
        "statement": "FICTIONAL rehearsal review records consideration of the revised requirement.",
        "locator": f"synthetic-rehearsal/{evidence_id}",
    })
    revisited = sd.assess(*sd.load_records(records))
    stages = []
    for name, assessment in (("baseline", original), ("requirement_changed", revised),
                             ("decision_revisited", revisited)):
        restored = sd.assess(*sd.load_records(json.loads(json.dumps(assessment))))
        if restored != assessment:
            raise sd.SecureDesignError(f"{name}: JSON re-import lost assessment information")
        row = _selected(assessment, requirement_id, decision_id)
        stages.append({
            "name": name,
            "state": row["state"],
            "requirement_version": row["requirement_current_version"],
            "stale_evidence_ids": [e["evidence_id"] for e in row["evidence_stale_trace"]],
            "current_evidence_ids": [e["evidence_id"] for e in row["evidence_observed_practice"]],
            "json_round_trip_equal": True,
            "assessment": assessment,
        })
    return {
        "content_class": sd.CONTENT_CLASS,
        "requirement_id": requirement_id,
        "decision_id": decision_id,
        "stages": stages,
        "limits": "Fictional evidence only. Artifact content and actual controls were not verified.",
    }


def summary(rehearsal: Dict[str, Any]) -> str:
    lines = ["SYNTHETIC SECURE-DESIGN CHANGE REHEARSAL",
             f"{rehearsal['decision_id']} <- {rehearsal['requirement_id']}"]
    for stage in rehearsal["stages"]:
        lines.append(f"{stage['name']}: v{stage['requirement_version']} {stage['state']}; "
                     f"current={len(stage['current_evidence_ids'])}, "
                     f"stale={len(stage['stale_evidence_ids'])}; JSON round-trip identical")
    lines.append(rehearsal["limits"])
    return "\n".join(lines) + "\n"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bundle(rehearsal: Dict[str, Any], output: Path) -> None:
    """Create a new directory only. A manifest is written last, not an atomic install."""
    files = {"REHEARSAL.txt": summary(rehearsal).encode("utf-8")}
    for stage in rehearsal["stages"]:
        report, name = stage["assessment"], stage["name"]
        csv_text = io.StringIO(newline="")
        csv.writer(csv_text).writerows(sd.to_csv_rows(report))
        files[f"{name}.json"] = _json_bytes(report)
        files[f"{name}.csv"] = csv_text.getvalue().encode("utf-8")
        files[f"{name}-worksheet.md"] = sd.render_worksheet(report).encode("utf-8")
        files[f"{name}-chain.md"] = sd.render_evidence_chain(report).encode("utf-8")
    manifest = {
        "content_class": sd.CONTENT_CLASS,
        "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())],
        "stages": [{key: value for key, value in stage.items() if key != "assessment"}
                   for stage in rehearsal["stages"]],
    }
    # mkdir refuses files, directories, and symlinks already occupying this name.
    # An I/O failure can leave an incomplete new directory; do not treat it as a
    # complete bundle without successful exit and all manifest hashes matching.
    output.mkdir()
    for name, data in files.items():
        with (output / name).open("xb") as handle:
            handle.write(data)
    with (output / "manifest.json").open("xb") as handle:
        handle.write(_json_bytes(manifest))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", default=str(HERE / "fixtures" / "secure_design_records.json"))
    parser.add_argument("--requirement", default=DEFAULT_REQUIREMENT)
    parser.add_argument("--decision", default=DEFAULT_DECISION)
    parser.add_argument("--out-dir", type=Path, help="new directory; parent must already exist")
    args = parser.parse_args(argv)
    try:
        rehearsal = run_rehearsal(sd.read_json(args.records), args.requirement, args.decision)
        if args.out_dir is not None:
            write_bundle(rehearsal, args.out_dir)
        print(summary(rehearsal), end="")
        return 0
    except (sd.SecureDesignError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
