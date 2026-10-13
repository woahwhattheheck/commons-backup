from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acceptance import build_cutover_gate, build_uat_packet, evaluate_interface_replay, reconcile_migration

fixture = json.loads((ROOT / "fixtures" / "synthetic.json").read_text())
migration = reconcile_migration(fixture["source"], fixture["target"])
replay = evaluate_interface_replay(fixture["events"])
uat = build_uat_packet(fixture["uat"])
gate = build_cutover_gate(fixture["source"], fixture["target"], fixture["events"], fixture["uat"])
assert migration["status"] == replay["status"] == uat["status"] == "pass"
assert gate["ready_for_owner_review"] is True
assert gate["input_authority"] == "caller_supplied_evidence_only"
assert gate["production_cutover_authority"] is False
assert gate["county_submission_authority"] is False
print(json.dumps({"migration": migration, "replay": replay, "uat": uat, "gate": gate, "fixture_only": True}, indent=2, sort_keys=True))
