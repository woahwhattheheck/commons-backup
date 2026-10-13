#!/usr/bin/env python3
"""Deterministic fictional before/after reports, produced by the real parent compiler."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import review_diff as diff
from workshare_compile import compile_untrusted_inspection
from workshare_contract import AUTHORITY_SCHEMA, CANDIDATE_SCHEMA

BEFORE_AT = "2026-09-13T15:00:00Z"
AFTER_AT = "2026-09-19T15:00:00Z"


def make_inputs() -> tuple[dict, dict]:
    generation, prime = "synthetic-quartz-g1", "Fictional Assessment Prime"
    sources = []
    for group, dimension in diff.CELL_KEYS:
        source_id = f"fictional-{group.lower()}-{dimension}"
        sources.append({
            "source_id": source_id, "authority_generation": generation,
            "solicitation_id": "18649", "prime_candidate": prime,
            "group": group, "dimension": dimension, "evidence_kind": "artifact",
            "source_ref": f"synthetic://{source_id}/v1",
            "source_content_sha256": diff.digest({"fictional_document": source_id, "version": 1}),
            "observed_at": BEFORE_AT,
            "claim": "Fictional rehearsal record; not University evidence.",
            "maturity": 2, "confidence_bp": 7000,
        })
    candidate = {
        "schema": CANDIDATE_SCHEMA,
        "engagement": {"solicitation_id": "18649", "buyer": "University of Iowa",
                       "prime_candidate": prime, "subcontractor": "TJLabs",
                       "base_fee_usd": 24000, "optional_readout_usd": 4000},
        "authority_generation": generation, "source_ids": [s["source_id"] for s in sources],
    }
    authority = {"schema": AUTHORITY_SCHEMA, "generation": generation,
                 "solicitation_id": "18649", "prime_candidate": prime, "sources": sources}
    return candidate, authority


def compile_inputs(candidate: dict, authority: dict, evaluated_at: str = BEFORE_AT) -> dict:
    candidate = copy.deepcopy(candidate)
    candidate["source_ids"] = [s["source_id"] for s in authority["sources"]]
    return compile_untrusted_inspection(candidate, authority, now=evaluated_at)


def example_reports() -> tuple[dict, dict]:
    candidate, authority = make_inputs()
    # Deliberately absent evidence persists across both revisions.
    authority["sources"] = [s for s in authority["sources"]
                            if s["source_id"] != "fictional-iam-ai_readiness"]
    before = compile_inputs(candidate, authority)
    candidate["authority_generation"] = authority["generation"] = "synthetic-quartz-g2"
    for source in authority["sources"]:
        source["authority_generation"] = authority["generation"]
    rows = {s["source_id"]: s for s in authority["sources"]}
    rows["fictional-ess-software"]["source_content_sha256"] = diff.digest({"fictional_revision": 2})
    rows["fictional-ess-software"]["claim"] = "Fictional changed evidence; professional interpretation remains open."
    rows["fictional-ris-deployment"]["group"] = "IAM"  # Both old/new cells affected.
    rows["fictional-ris-security"]["source_ref"] = "synthetic://reorganized/reference"
    authority["sources"] = [s for s in authority["sources"]
                            if s["source_id"] != "fictional-ess-security"]
    extra = copy.deepcopy(rows["fictional-iam-software"])
    extra.update(source_id="fictional-iam-software-dissent", maturity=3,
                 claim="Fictional conflicting account retained for follow-up.")
    authority["sources"].append(extra)
    after = compile_inputs(candidate, authority, AFTER_AT)
    return before, after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path, help="new directory, must not already exist")
    args = parser.parse_args()
    before, after = example_reports()
    delta = diff.compare_reports(before, after)
    args.output_directory.mkdir(mode=0o700)
    files = {"before.json": diff.canonical_json_bytes(before),
             "after.json": diff.canonical_json_bytes(after),
             "delta.json": diff.canonical_json_bytes(delta),
             "review.md": diff.render_markdown(before, after).encode("utf-8")}
    for name, raw in files.items():
        diff.write_new(args.output_directory / name, raw)
    print("SYNTHETIC ONLY; not University findings")
    print(delta["summary"])
    print(delta["diff_receipt_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
