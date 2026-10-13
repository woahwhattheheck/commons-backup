from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JSON_FILES = [
    "opportunity.json",
    "budget.json",
    "project_spec.json",
    "protocol_v0.schema.json",
    "benchmark_seed.json",
]
TEXT_FILES = ["README.md", "proposal.md", "application_fields.md", "evaluation_plan.md"]


def load_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def validate() -> dict:
    errors: list[str] = []
    opp = load_json("opportunity.json")
    budget = load_json("budget.json")
    spec = load_json("project_spec.json")
    schema = load_json("protocol_v0.schema.json")
    seed = load_json("benchmark_seed.json")

    if opp["deadline"] != "2026-10-31T23:59:00-07:00":
        errors.append("deadline must remain the verified 2026-10-31 23:59 PDT value")
    if opp["submission_status"] != "NOT_SUBMITTED" or opp["award_status"] != "UNKNOWN":
        errors.append("carrier may not claim submission or award")
    if not all(str(url).startswith("https://") for url in opp["sources"]):
        errors.append("all opportunity sources must be HTTPS URLs")
    if not any("foresight.org" in url for url in opp["sources"]):
        errors.append("official Foresight source missing")

    direct = sum(int(row["amount"]) for row in budget["direct_costs"])
    if direct != budget["direct_total"]:
        errors.append("direct budget math mismatch")
    if budget["overhead"]["amount"] > round(direct * 0.10):
        errors.append("overhead exceeds RFP 10% ceiling")
    total = direct + int(budget["overhead"]["amount"])
    if total != budget["total_requested"] or total != opp["requested_usd_proposed"]:
        errors.append("requested total is inconsistent across budget/opportunity")
    if not (opp["typical_grant_usd"]["min"] <= total <= opp["typical_grant_usd"]["max"]):
        errors.append("proposed request falls outside sponsor's stated typical range")

    deliverables = spec["deliverables"]
    if len(deliverables) < 5 or max(int(row["month"]) for row in deliverables) != 12:
        errors.append("deliverable schedule must span the proposed 12 months")
    if not all(row.get("open_source") is True for row in deliverables):
        errors.append("every funded deliverable must be marked open source")
    if "OWNER_CONFIRM" not in spec["license_proposal"]:
        errors.append("license must remain owner-confirmed before submission")

    event_enum = schema["properties"]["event_type"]["enum"]
    if event_enum != spec["event_types"]:
        errors.append("protocol schema event enum drifted from project spec")

    scenarios = seed["scenarios"]
    ids = [row["id"] for row in scenarios]
    if len(scenarios) < 12 or len(ids) != len(set(ids)):
        errors.append("benchmark seed needs >=12 uniquely identified scenarios")
    if seed["status"] != "APPLICATION_PROTOTYPE_NOT_RESEARCH_RESULT":
        errors.append("benchmark seed must remain clearly non-result prototype material")

    corpus = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in TEXT_FILES)
    required_markers = [
        "not submitted",
        "OWNER_CONFIRM",
        "open source",
        "negative result",
        "Supercollaboration and decentralized alignment",
    ]
    lower = corpus.lower()
    for marker in required_markers:
        if marker.lower() not in lower:
            errors.append(f"truth/readiness marker missing: {marker}")

    files = sorted(JSON_FILES + TEXT_FILES + ["validate_pack.py", "test_pack.py"])
    digest = hashlib.sha256()
    for name in files:
        path = ROOT / name
        if not path.exists():
            errors.append(f"missing carrier file: {name}")
            continue
        digest.update(name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")

    return {
        "ok": not errors,
        "errors": errors,
        "status": "TECHNICAL_GO_SUBMISSION_HOLD" if not errors else "INVALID",
        "proposed_request_usd": total,
        "seed_scenarios": len(scenarios),
        "pack_sha256": digest.hexdigest(),
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if result["ok"] else 2)
