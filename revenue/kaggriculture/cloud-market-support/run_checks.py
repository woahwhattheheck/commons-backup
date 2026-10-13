# SPDX-License-Identifier: Apache-2.0
"""Execute independent certificate-consumer witnesses against supplied POLY source."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from certificate_consumer import check_certificate

HERE = Path(__file__).resolve().parent
REFERENCE_COMMIT = "3457d8f149b2bb07de6d9993a41ae0e0f19eb57f"
REFERENCE_BLOB = "b04f7bc4ff2137dee4b70ec6f10e7f02ccaebd06"
DEFAULT_CORE = HERE.parent / "cloud-full-support/full_support.py"


def load_core(path: Path):
    source = path.read_bytes()
    blob = hashlib.sha1(f"blob {len(source)}\0".encode()+source).hexdigest()
    spec = importlib.util.spec_from_file_location("triad_consumed_poly", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load supplied core file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, {"path": str(path), "git_blob": blob,
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "reference_commit": REFERENCE_COMMIT if blob == REFERENCE_BLOB else None}


def build_receipt(core_path: Path = DEFAULT_CORE) -> dict:
    core, source = load_core(core_path)
    triangle = [[0,0,0],[-1,1,1],[1,-1,1],[1,1,-1]]
    bit_case = [[0,0,0],[-101,103,107],[109,-113,127],[131,137,-139]]
    cases = [
        ("three_support", triangle, {}, "optimal", True),
        ("zero_pivots", triangle, {"max_pivots": 0}, "pivot_limit", False),
        ("one_pivot", triangle, {"max_pivots": 1}, "pivot_limit", False),
        ("bit_limit", bit_case, {"max_bits": 16}, "bit_limit", False),
        ("closed_bounds_unfinished", [[0],[0]], {"max_pivots": 0}, "pivot_limit", False),
        ("completed_zero", [[0],[0]], {}, "optimal", False),
        ("negative_alternative", [[0,0],[-2,3]], {}, "optimal", False),
        ("published_strawberry", [[0,0],[1,-1],[-1,2]], {}, "optimal", True),
        ("published_negative_column", [[0,0,0],[1,-1,-1],[-1,2,-1]], {}, "optimal", False),
    ]
    records, durations = [], []
    for name, deltas, limits, status, positive in cases:
        solution = core.solve_full_table(deltas, **limits)
        started = time.perf_counter()
        check = check_certificate(deltas, solution)
        durations.append(time.perf_counter()-started)
        assert check["valid"] and check["status"] == status and check["positive_optimum"] == positive
        records.append({"id": name, "deltas": deltas, "limits": limits,
                        "solution": solution, "independent_check": check})
    changed = copy.deepcopy(records[0]["solution"])
    changed["support"] = [0]
    metadata_witness = {"changed_field": "support", "changed_value": [0],
                        "provider_math_check": core.verify_certificate(triangle, changed),
                        "independent_consumer": check_certificate(triangle, changed)}
    assert not metadata_witness["independent_consumer"]["valid"]
    source["path"] = "revenue/kaggriculture/cloud-full-support/full_support.py"
    return {"schema": "triad-certificate-consumer-v1", "core_source": source,
            "consumer_sha256": hashlib.sha256((HERE/"certificate_consumer.py").read_bytes()).hexdigest(),
            "cases": records, "metadata_witness": metadata_witness,
            "max_consumer_seconds": max(durations),
            "timing_scope": "Nine warm certificate checks only; not solver or whole-agent time",
            "published_matrix_provenance": {
                "commit": "4d97474b0188b0373be1b52b610c0114ceb033c8",
                "readme_blob": "5fb510deeef0136c7143327514a7601d6fac896f",
                "method": "Two exact matrices transcribed from README; no archive or engine replay"},
            "new_lp_comparisons": 0, "new_engine_transitions": 0, "new_full_games": 0,
            "policy_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_receipt(args.core)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"core": report["core_source"], "cases": len(report["cases"]),
                      "max_consumer_seconds": report["max_consumer_seconds"]}))
