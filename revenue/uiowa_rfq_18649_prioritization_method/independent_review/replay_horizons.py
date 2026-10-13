#!/usr/bin/env python3
"""Independent UIOWA-029 semantic replay; not a horizon planner.

Loads an explicitly selected, already trusted local method.py, exercises its
Backlog API and writes deterministic source-bound observations. Exit codes:
0 = every contract case passes; 1 = demonstrated contract failure; 2 = unable
to execute. Policy observations are separate and never counted as passes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys
import types

HORIZONS = ("0-90", "90-180", "180+")
EFFORTS = ((None, None), (None, 5), (2, None), (0, 0), (2, 5), (15, 30), (60, 90))


def canonical(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def record(rid, effort=(2, 5), horizon=None, prerequisites=()):
    return {"recommendation_id": rid, "title": "Fictional rehearsal " + rid,
            "group": "SYN", "area": "SD", "effects": {"quality": 1, "security": None, "delivery": 0},
            "complexity": 2, "effort_days_low": effort[0], "effort_days_high": effort[1],
            "prerequisites": list(prerequisites), "declared_horizon": horizon,
            "declared_horizon_reason": "Fictional declared exception for review."}


def cases():
    """224 distinct inputs; no random values or external fixtures."""
    for e, h, deps, reverse in itertools.product(
            range(len(EFFORTS)), (None,) + HORIZONS,
            ((), ("MISSING",), ("P",), ("P", "MISSING")), (False, True)):
        rows = [record("P", (15, 30), "180+"), record("A", EFFORTS[e], h, deps)]
        if reverse:
            rows.reverse()
        yield {"backlog_id": f"SYN-{e}-{h}-{','.join(deps)}-{int(reverse)}",
               "synthetic": True, "recommendations": rows}


def inspect(doc, payload, after):
    """Check observable contracts, not the planner's implementation or policy."""
    source = doc["recommendations"]
    rows = payload["recommendations"]
    by_id = {r["recommendation_id"]: r for r in rows}
    buckets = payload["by_horizon"]
    violations = {(v["recommendation_id"], v["code"]) for v in payload["violations"]}
    ids = {r["recommendation_id"] for r in source}
    expected = Counter(r["recommendation_id"] for r in source)
    sized = {r["recommendation_id"] for r in source
             if r["effort_days_low"] is not None and r["effort_days_high"] is not None}
    missing = {r["recommendation_id"] for r in source
               if any(p not in ids for p in r["prerequisites"])}
    misplaced = set()
    source_by_id = {r["recommendation_id"]: r for r in source}
    for r in source:
        h = r["declared_horizon"]
        if h not in HORIZONS:
            continue
        for p in r["prerequisites"]:
            ph = source_by_id.get(p, {}).get("declared_horizon")
            if ph in HORIZONS and HORIZONS.index(ph) > HORIZONS.index(h):
                misplaced.add(r["recommendation_id"])
    checks = {
        "input_unchanged": doc == after,
        "records_conserved": Counter(r["recommendation_id"] for r in rows) == expected,
        "bucket_membership_conserved": Counter(x for group in buckets.values() for x in group) == expected,
        "declarations_preserved": all(by_id[r["recommendation_id"]]["declared_horizon"] == r["declared_horizon"]
                                      for r in source if r["declared_horizon"] in HORIZONS),
        "missing_prerequisites_diagnosed": all((rid, "DANGLING_PREREQUISITE") in violations for rid in missing),
        "sized_items_not_mislabeled_needs_estimate": not sized.intersection(buckets.get("NEEDS_ESTIMATE", [])),
        "declared_dependency_order_diagnosed": all((rid, "PREREQUISITE_AFTER_DEPENDENT") in violations for rid in misplaced),
        "fictional_authority_preserved": payload["meta"].get("synthetic") is True
                                        and payload["meta"].get("authority") == "FICTIONAL_REHEARSAL_ONLY",
    }
    return {"case_id": doc["backlog_id"], "status": "PASS" if all(checks.values()) else "FAIL",
            "failed_checks": sorted(k for k, value in checks.items() if not value),
            "checks": checks,
            "observed": {"proposals": {r["recommendation_id"]: r["proposed_horizon"] for r in rows},
                         "by_horizon": buckets,
                         "violations": sorted([list(v) for v in violations])}}


def execute(module):
    results = []
    for doc in cases():
        working = copy.deepcopy(doc)
        try:
            payload = module.Backlog(working).as_dict()
            result = inspect(doc, payload, working)
        except Exception as exc:
            result = {"case_id": doc["backlog_id"], "status": "FAIL",
                      "failed_checks": ["execution"],
                      "error": {"type": type(exc).__name__, "message": str(exc)}}
        results.append(result)
    # A policy observation, not a test requiring a new dependency policy.
    chain = [record("A", (70, 90)), record("B", prerequisites=("A",)), record("C", prerequisites=("B",))]
    observations = []
    for rows in itertools.permutations(chain):
        try:
            payload = module.Backlog({"recommendations": copy.deepcopy(list(rows))}).as_dict()
            observations.append({"order": [r["recommendation_id"] for r in rows],
                                 "proposals": {r["recommendation_id"]: r["proposed_horizon"] for r in payload["recommendations"]},
                                 "violations": payload["violations"]})
        except Exception as exc:
            observations.append({"order": [r["recommendation_id"] for r in rows],
                                 "error": {"type": type(exc).__name__, "message": str(exc)}})
    counts = Counter(r["status"] for r in results)
    failures = Counter(k for r in results for k in r["failed_checks"])
    return {"status": "PASS" if results and counts["FAIL"] == 0 else "FAIL",
            "contract_cases": len(results), "passed": counts["PASS"], "failed": counts["FAIL"],
            "failure_counts": dict(sorted(failures.items())),
            "case_results_sha256": hashlib.sha256(canonical(results).encode()).hexdigest(),
            "contract_results": results,
            "policy_observations": {"interpretation": "Declarations and proposals are different views; these six observations do not assert a required propagation policy.",
                                    "cases": observations}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Already trusted local method.py; no download or remote execution")
    parser.add_argument("--expected-blob", help="Optional exact Git blob expected before execution")
    parser.add_argument("--out", type=Path, help="New output file; refuses overwrite")
    args = parser.parse_args(argv)
    try:
        data = args.source.read_bytes()
        digest = blob_sha(data)
        if args.expected_blob is not None and digest != args.expected_blob:
            raise ValueError("source Git blob differs from --expected-blob")
        module = types.ModuleType("uiowa029_review_target")
        module.__file__ = str(args.source.resolve())
        sys.modules[module.__name__] = module
        exec(compile(data, module.__file__, "exec"), module.__dict__)
        if not callable(getattr(module, "Backlog", None)):
            raise ValueError("source has no callable Backlog")
        report = execute(module)
        report["source"] = {"git_blob": digest, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        report["scope"] = "Synthetic UIOWA-029 Backlog API replay only; not hosted CI, capacity analysis, University findings or a delivery commitment."
        text = canonical(report)
        if args.out is None:
            sys.stdout.write(text)
        else:
            with args.out.open("x", encoding="utf-8") as fh:
                fh.write(text)
        return 0 if report["status"] == "PASS" else 1
    except Exception as exc:
        sys.stderr.write(canonical({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
