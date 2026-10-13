#!/usr/bin/env python3
"""Run actual native imports and changed-note replay through LODESTONE's mapper."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

if __package__:
    from . import adapter as a
else:
    _path = Path(__file__).resolve().with_name("adapter.py")
    _spec = importlib.util.spec_from_file_location("_uiowa_workshare_native_adapter", _path)
    if _spec is None or _spec.loader is None:
        raise RuntimeError("Cannot load sibling adapter")
    a = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(a)

HERE = Path(__file__).resolve().parent
PARENT_FIXTURE = HERE.parent / "uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json"
PARENT_LOCATOR = "revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json"
HANDOFF_LOCATOR = "contract-fixture://workbench-draft/v1"


def handoff_fixture() -> dict:
    """Contract-shaped synthetic data, explicitly not a captured browser export."""
    return {"schema": a.HANDOFF_SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
        "report_receipt_sha256": "d" * 64, "report_mode": "UNTRUSTED_INSPECTION",
        "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED", "synthetic_demo": True,
        "cell_notes": [{"group": group, "dimension": dimension,
                        "compiler_status": "HOLD_MISSING_EVIDENCE", "disposition": "UNREVIEWED",
                        "analyst_note": "Synthetic contract fixture; not compiler output or a University finding"}
                       for group in ("ESS", "RIS", "IAM")
                       for dimension in ("software_development", "security", "deployment", "ai_readiness")],
        "authority": {flag: False for flag in sorted(a.FLAGS)},
        "fixture_notice": "Contract-shaped synthetic handoff based on actual workbench app.js exportDraft; no browser execution asserted"}


def request(authority: dict, handoff: dict, rid: str) -> dict:
    return a.review_request(authority, handoff, source_id="ESS-SW-01", group="ESS", dimension="software_development",
        expected_receipt=handoff["adapter"]["original_document"]["report_receipt_sha256"],
        expected_generation=authority["adapter"]["original_document"]["generation"],
        expected_handoff_revision=handoff["adapter"]["revision"],
        expected_authority_revision=authority["adapter"]["revision"], request_id=rid,
        rationale="Synthetic analyst explicitly requests this source for review; native dimension spelling is retained, not equated")


def run(authority_document: dict, mapper) -> dict:
    authority = a.adapt_authority(authority_document, namespace="demo/workshare", locator=PARENT_LOCATOR, synthetic=True)
    original = handoff_fixture()
    revised = deepcopy(original)
    revised["cell_notes"][0]["analyst_note"] = "Please inspect the sampled promotion record; policy text alone does not describe all execution."
    first = a.adapt_handoff(original, namespace="demo/workbench", locator=HANDOFF_LOCATOR)
    second = a.adapt_handoff(revised, namespace="demo/workbench", locator=HANDOFF_LOCATOR)
    original_request, revised_request = request(authority, first, "request-original"), request(authority, second, "request-revised")
    baseline_input = a.combine([authority, first], [original_request])
    baseline = mapper.reconcile(baseline_input)
    # An intentionally unqualified selector proves retained version ambiguity.
    ambiguous_link = {"link_id": "unqualified-note-probe", "relation": "inspect_version_ambiguity",
        "from": revised_request["from"], "to": {"kind": "observation", "id": a.cell_id("ESS", "software_development")}}
    replay_input = a.combine([authority, first, second], [original_request, revised_request, ambiguous_link])
    replay = mapper.reconcile(replay_input)
    old = next(r for r in replay["records"] if all(r["original"].get(k) == v for k, v in original_request["from"].items()))
    new = next(r for r in replay["records"] if all(r["original"].get(k) == v for k, v in revised_request["from"].items()))
    probe = next(link for link in replay["links"] if link["link_id"] == "unqualified-note-probe")
    summary = {"schema": "uiowa.workshare-adapter-replay.v1", "synthetic": True,
        "scope": "actual checked-in authority fixture plus contract-shaped synthetic handoff; no compiler or browser execution",
        "assessment_authority": False, "baseline": baseline["summary"], "replay": replay["summary"],
        "compiler_receipt_unchanged": original["report_receipt_sha256"] == revised["report_receipt_sha256"],
        "handoff_revision_changed": first["adapter"]["revision"] != second["adapter"]["revision"],
        "changed_note_entity_id_stable": old["entity_id"] == new["entity_id"],
        "changed_note_occurrence_id_changed": old["occurrence_id"] != new["occurrence_id"],
        "unqualified_note_status": probe["to"]["status"], "unqualified_candidate_count": len(probe["to"]["candidate_ids"]),
        "native_authority_document_sha256": a.sha256(authority_document),
        "baseline_snapshot_sha256": baseline["snapshot_sha256"], "replay_snapshot_sha256": replay["snapshot_sha256"]}
    return {"baseline-input.json": baseline_input, "baseline-report.json": baseline,
            "replay-input.json": replay_input, "replay-report.json": replay, "summary.json": summary,
            "handoff-original.json": original, "handoff-revised.json": revised}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--authority-fixture", type=Path, default=PARENT_FIXTURE)
    parser.add_argument("--mapper-path", type=Path, default=a.DEFAULT_MAPPER)
    args = parser.parse_args(argv)
    try:
        native = a.load_json(args.authority_fixture.read_text(encoding="utf-8"))
        if native.get("generation") != "uiowa-synthetic-authority-20260913-01":
            raise a.AdapterError("Rehearsal requires the named checked-in synthetic fixture")
        mapper = a.load_mapper(args.mapper_path)
        outputs = run(native, mapper)
        summary = outputs["summary.json"]
        summary["mapper_file_sha256"] = hashlib.sha256(args.mapper_path.read_bytes()).hexdigest()
        summary["adapter_file_sha256"] = hashlib.sha256((HERE / "adapter.py").read_bytes()).hexdigest()
        summary["native_fixture_file_sha256"] = hashlib.sha256(args.authority_fixture.read_bytes()).hexdigest()
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in outputs.items():
            (args.output / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="")
        for prefix in ("baseline", "replay"):
            (args.output / (prefix + "-report.md")).write_text(mapper.render_markdown(outputs[prefix + "-report.json"]), encoding="utf-8", newline="")
        print(a.canonical(summary))
        return 0
    except (a.AdapterError, OSError, ValueError, UnicodeError) as exc:
        print(f"adapter-replay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
