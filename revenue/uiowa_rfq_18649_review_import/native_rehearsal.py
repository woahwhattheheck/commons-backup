"""Real parent compiler -> CSV import -> native disposition -> response bundle.

Every review and disposition below is a labelled synthetic test fixture, not a
human approval. Requires the actual workshare/review_cycle modules in this checkout.
No replacement verifier, stub, network, or silently skipped integration is used.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from comment_import import canonical
from native_bridge import NAMESPACE, load_native, prepare_cycle


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(out: Path) -> dict:
    native = load_native()
    from revenue.uiowa_rfq_18649_review_cycle.parent_adapter import compile_inspection
    root = Path(__file__).resolve().parents[2]
    fixtures = root / "revenue/uiowa_rfq_18649_workshare/fixtures"
    packet_path, authority_path = fixtures / "synthetic_packet.json", fixtures / "synthetic_authority.json"
    report = compile_inspection(native.load(packet_path), native.load(authority_path))
    native.verify_inspection(report)
    source = report["evidence_authority"]["sources"][0]
    document = {"schema": native.DOC_SCHEMA, "status": native.STATUS, "synthetic": True,
                "version": "CSV-SYN-DRAFT-1", "parent_version": None,
                "report_receipt_sha256": report["receipt_sha256"], "authority": deepcopy(native.AUTHORITY),
                "findings": [{"id": "FND-CSV-SYN-01", "group": source["group"], "dimension": source["dimension"],
                              "title": "Illustrative review target", "statement": "Synthetic fixture only; no University finding is asserted.",
                              "source_ids": [source["source_id"]]}],
                "recommendations": [], "applied_cycles": [], "unresolved": []}
    native.validate_document(document, report)
    rows = []
    for cid, kind, comment in (("CSV-SYN-C1", "wording", 'Please clarify this title.\nKeep the quoted word "illustrative".'),
                               ("CSV-SYN-C2", "interpretation", "Keep this disagreement explicitly unresolved.")):
        rows.append({"comment_id": cid, "reviewer_role": "Fictional practitioner role",
                     "comment_text": comment, "finding_id": "FND-CSV-SYN-01", "report_version": document["version"],
                     "finding_namespace": NAMESPACE, "comment_kind": kind,
                     "extra_context": "SYNTHETIC — NOT UNIVERSITY EVIDENCE", "supplied_decision": "ACCEPT"})
    rows += [dict(rows[0]), {**rows[0], "comment_id": "CSV-SYN-C3", "finding_id": "FND-MISSING"},
             {**rows[0], "comment_id": "CSV-SYN-C4", "report_version": "OLD-DRAFT"}]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\r\n")
    writer.writeheader(); writer.writerows(rows)
    raw = stream.getvalue().encode("utf-8")
    prepared = prepare_cycle(raw, "synthetic-native-review-round", "comments.csv", document, report,
                             "CSV-SYN-CYCLE-1", "CSV-SYN-DRAFT-2", validate_text=native.text)
    check(prepared["summary"]["native_open_comments"] == 2, "expected two real native OPEN comments")
    check(prepared["summary"]["unresolved"] == 2, "unknown/stale references must remain visible")
    check(all(c["decision"] == "OPEN" and not c["proposed_changes"] for c in prepared["cycle"]["comments"]),
          "importer inferred a review decision or patch")
    check(all(m["record"]["values"]["extra_context"].startswith("SYNTHETIC") for m in prepared["mapped"]),
          "source extension or fiction label was dropped")
    imported = {m["record"]["comment_id"]: m["native_comment_id"] for m in prepared["mapped"]}
    # Explicit fixture decisions are a separate, downstream review input. Nothing
    # in prepare_cycle reads supplied_decision or manufactures these dispositions.
    reviewed = deepcopy(prepared["cycle"])
    for c in reviewed["comments"]:
        if c["id"] == imported["CSV-SYN-C1"]:
            c.update(decision="ACCEPT", owner_role="Fictional review chair",
                     rationale="SYNTHETIC DISPOSITION FIXTURE: accept the title wording only.",
                     proposed_changes=[{"field": "title", "before": document["findings"][0]["title"],
                                        "after": "Clarified illustrative review target"}])
        else:
            c.update(decision="UNRESOLVED", owner_role="Fictional review chair",
                     rationale="SYNTHETIC DISPOSITION FIXTURE: retain the interpretive disagreement.")
    bundle = native.build_bundle(report, report, document, reviewed)
    check(bundle == native.build_bundle(report, report, document, reviewed), "native regeneration changed bytes")
    revised = json.loads(bundle["revised-draft.json"])
    audit = json.loads(bundle["audit.json"])
    check(len(audit["changes"]) == 1 and audit["changes"][0]["field"] == "title", "wrong native edit set")
    check(len(revised["unresolved"]) == 1 and revised["unresolved"][0]["decision"] == "UNRESOLVED",
          "native disagreement did not survive")
    check(all(v is False for v in revised["authority"].values()), "review changed authority flags")
    check(revised["findings"][0]["statement"] == document["findings"][0]["statement"], "wording changed conclusion")
    check(not audit["source_changes"] and not audit["compiler_status_changes"], "import changed evidence/status")
    for c in reviewed["comments"]:
        response = next(x for x in audit["responses"] if x["id"] == c["id"])
        check(response["comment"] == c["comment"], "native response lost original comment text")
    out.mkdir(parents=True, exist_ok=False)
    (out / "comments.csv").write_bytes(raw)
    (out / "preparation.json").write_bytes(canonical(prepared) + b"\n")
    (out / "reviewed-fixture-comments.json").write_bytes(native.canonical(reviewed))
    native.write_bundle(out / "native-bundle", bundle)
    native.verify_bundle(out / "native-bundle")
    dependencies = list((root / "revenue/uiowa_rfq_18649_workshare").glob("workshare_*.py"))
    dependencies += [packet_path, authority_path, Path(native.__file__),
                     Path(native.__file__).with_name("parent_adapter.py")]
    receipt = {"schema": "uiowa124-native-integration/v1", "synthetic": True,
               "summary": prepared["summary"], "native_changes": len(audit["changes"]),
               "native_unresolved": len(revised["unresolved"]), "native_bundle_verified": True,
               "authority_changed": False, "real_parent_compiler": True,
               "compiler_receipt_sha256": report["receipt_sha256"],
               "dependencies_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(dependencies)},
               "bundle_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(bundle.items())},
               "source_csv_sha256": hashlib.sha256(raw).hexdigest()}
    (out / "receipt.json").write_bytes(canonical(receipt) + b"\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out), indent=2))
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"native rehearsal error: {exc}", file=sys.stderr)
        raise SystemExit(2)
