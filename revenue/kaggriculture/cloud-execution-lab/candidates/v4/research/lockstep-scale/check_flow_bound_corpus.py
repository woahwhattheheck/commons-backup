# SPDX-License-Identifier: MIT
"""Held-out acceptance of ESTUARY-0891's sole effective_flow_bounds helper.

This imports authenticated candidate source; it does not implement flow bounds.
The input adapter passes ONLY public inventory/town/clock/seat and final own action.
Ground truth remains outside the candidate arguments. Corpus truth comes from
flow_engine_corpus's full interpreter plus noninterference replay.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import flow_engine_corpus as corpus

TESTED_HELPER_BLOB = "e24dd03a88a71ba4cf6f8d5da1082b89490b5a94"


def load_helper(path: Path, expected_blob: str = TESTED_HELPER_BLOB):
    data = path.read_bytes()
    if corpus.git_blob(data) != expected_blob:
        raise ValueError("flow helper source pin mismatch")
    # Compile the authenticated bytes, never a possibly stale pycache or a second
    # unauthenticated read by a loader.
    import types
    module = types.ModuleType("flowproof_candidate")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def public_inputs(record):
    value = record["input"]
    def observation(obs):
        return {"step": obs["step"], "player": obs["player"],
                "market": {"inventory": copy.deepcopy(obs["market"]["inventory"])},
                "town": copy.deepcopy(obs["town"])}
    return (observation(value["previous"]), copy.deepcopy(value["submitted_action"]),
            observation(value["current"]), copy.deepcopy(value["configuration"]))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evaluate(helper, records):
    require(bool(records), "empty corpus")
    cells = signals = exact = 0
    outputs = []
    for record in records:
        args = public_inputs(record)
        untouched = copy.deepcopy(args)
        bounds = helper.effective_flow_bounds(*args)
        require(args == untouched, f"input mutation: {record['id']}")
        truth = record["oracle"]["opponent_admitted_net"]
        require(isinstance(bounds, dict) and set(bounds) == set(truth),
                f"missing product bounds: {record['id']}")
        for product, interval in bounds.items():
            prefix = f"{record['id']}:{product}"
            require(isinstance(interval, (list, tuple)) and len(interval) == 2,
                    f"bad interval shape: {prefix}")
            lo, hi = interval
            require(type(lo) is int and type(hi) is int and lo <= hi,
                    f"bad interval domain: {prefix}")
            require(lo <= truth[product] <= hi, f"unsound interval: {prefix}")
            cells += 1
            exact += lo == hi
        for threshold in (1, 50, 150):
            found = helper.confirmed_net_sells(bounds, threshold=threshold)
            expected = {p: b[0] for p, b in bounds.items() if b[0] >= threshold}
            require(found == expected, f"signal is not lower-bound-only: {record['id']}")
            for p, n in found.items():
                require(n <= truth[p], f"false-positive signal: {record['id']}:{p}")
            signals += len(found)
        # Repeated invocation, public inputs, and reverse-order replay all matter:
        # this is a stateless support API, not a cross-match cache.
        require(helper.effective_flow_bounds(*public_inputs(record)) == bounds,
                f"non-idempotent helper: {record['id']}")
        outputs.append(bounds)
    for record, expected in zip(reversed(records), reversed(outputs)):
        require(helper.effective_flow_bounds(*public_inputs(record)) == expected,
                f"order-dependent helper: {record['id']}")
    require(signals > 0, "vacuous panel: no certified positive flow")
    return {"cases": len(records), "product_containments": cells,
            "singleton_intervals": exact, "certified_signals_across_three_thresholds": signals,
            "false_positive_signals": 0, "source_calls": 3*len(records),
            "input_mutations": 0, "output_sha256": hashlib.sha256(corpus.encoded(outputs)).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", required=True, type=Path)
    parser.add_argument("--helper-blob", default=TESTED_HELPER_BLOB)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError("output already exists")
        helper = load_helper(args.helper, args.helper_blob)
        records = corpus.build_corpus(corpus.load_engine(args.engine))
        result = evaluate(helper, records)
        result.update(helper_blob=args.helper_blob, engine_pins=corpus.ENGINE_PINS,
                      corpus_sha256=hashlib.sha256(corpus.corpus_bytes(records)).hexdigest(),
                      scope="constructed full-engine transition soundness; not game EV or runtime wiring")
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, sort_keys=True)
            out.write("\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"flow-bound acceptance rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
