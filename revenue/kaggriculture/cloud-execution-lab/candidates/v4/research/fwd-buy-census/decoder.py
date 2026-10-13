#!/usr/bin/env python3
"""Read-only structural decoder for TITAN V4 FWD-BUY engagement census.

No economics are inferred here.  This script only identifies exact positive
WHEAT/FERTILIZER BUY_PRODUCT rows in frozen R01 tapes and a conservative nearest
earlier structural slot that does not cross market/economy barriers.
Only the standard engine's first ten raw market slots are executable evidence.
A source-step economic companion vetoes relocation; this does not prove cash,
shared shed capacity, unit-service dependencies, or opponent-market benefit.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
PREDECESSOR_DECODER_BLOB = "83942caaf64e8a4e205d48ac26e734bdb8554bbe"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PRODUCTS = {"WHEAT", "FERTILIZER"}
BARRIER_HEADS = {"HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL"}
MAX_MARKET_ROWS = 10
TURNS_PER_DAY = 24


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def market_rows(action: Any) -> list:
    if not isinstance(action, dict):
        return []
    rows = action.get("market")
    return rows if isinstance(rows, list) else []


def executable_rows(action: Any) -> list:
    # Do not compact placeholders: the engine caps RAW row positions.
    return market_rows(action)[:MAX_MARKET_ROWS]


def head(row: Any):
    return row[0] if isinstance(row, list) and row and isinstance(row[0], str) else None


def exact_buy(row: Any):
    if not isinstance(row, list) or len(row) != 3:
        return None
    if row[0] != "BUY_PRODUCT" or type(row[1]) is not str or row[1] not in PRODUCTS:
        return None
    q = row[2]
    if type(q) is not int or q <= 0:  # bool intentionally rejected
        return None
    return row[1], q


def step_has_barrier(action: Any, product: str, skip_row=None) -> bool:
    for index, row in enumerate(executable_rows(action)):
        if index == skip_row:
            continue
        h = head(row)
        if h in BARRIER_HEADS:
            return True
        if h in {"BUY_PRODUCT", "SELL"} and len(row) >= 2 and row[1] == product:
            return True
    return False


def structural_candidate(action: Any, product: str) -> bool:
    rows = market_rows(action)
    if len(rows) >= MAX_MARKET_ROWS:
        return False
    # Conservative: do not add into a step that itself carries a hard barrier or
    # same-product transfer; this prevents same-step reordering assumptions.
    return not step_has_barrier(action, product)


def nearest_candidate(tape: list, later_step: int, product: str):
    # Walk backward. A hard barrier encountered between source and candidate ends
    # the search: moving the buy earlier would cross a state-changing dependency.
    for s in range(later_step - 1, -1, -1):
        action = tape[s]
        if step_has_barrier(action, product):
            return None
        if structural_candidate(action, product):
            return s
    return None


def row_heads(action: Any) -> list[str]:
    return [h for h in (head(r) for r in market_rows(action)) if h is not None]


def analyze(tapes: list, require_shape: bool = True) -> dict:
    if require_shape and (len(tapes) != 13 or any(not isinstance(t, list) or len(t) != 719 for t in tapes)):
        raise ValueError("expected exactly 13 tapes x 719 steps")

    records = []
    buys = Counter()
    with_candidate = Counter()
    gap_hist = Counter()
    same_day = 0
    prior_day = 0

    for ti, tape in enumerate(tapes):
        for step, action in enumerate(tape):
            for ri, row in enumerate(executable_rows(action)):
                parsed = exact_buy(row)
                if parsed is None:
                    continue
                product, qty = parsed
                buys[product] += 1
                source_barrier = step_has_barrier(action, product, skip_row=ri)
                c = None if source_barrier else nearest_candidate(tape, step, product)
                rec = {
                    "tape": ti,
                    "later_step": step,
                    "later_day": step // TURNS_PER_DAY,
                    "later_hour": step % TURNS_PER_DAY,
                    "later_market_row": ri,
                    "product": product,
                    "qty": qty,
                    "source_companion_barrier": source_barrier,
                    "candidate_step": c,
                    "candidate_day": None if c is None else c // TURNS_PER_DAY,
                    "candidate_hour": None if c is None else c % TURNS_PER_DAY,
                    "gap": None if c is None else step - c,
                    "candidate_market_row_count": None if c is None else len(market_rows(tape[c])),
                    "candidate_market_heads": None if c is None else row_heads(tape[c]),
                    "cash_affordability": "NEEDS_RUNTIME_PROOF",
                    "shed_capacity": "NEEDS_RUNTIME_PROOF",
                    "opponent_market_effect": "NEEDS_RUNTIME_PROOF",
                }
                if c is not None:
                    with_candidate[product] += 1
                    gap_hist[step - c] += 1
                    if c // TURNS_PER_DAY == step // TURNS_PER_DAY:
                        same_day += 1
                    else:
                        prior_day += 1
                records.append(rec)

    witnesses = sorted(
        (r for r in records if r["candidate_step"] is not None),
        key=lambda r: (-r["gap"], r["tape"], r["later_step"], r["later_market_row"]),
    )[:10]
    return {
        "source_blob": EXPECTED_BLOB,
        "predecessor_decoder_blob": PREDECESSOR_DECODER_BLOB,
        "engine_blob": ENGINE_BLOB,
        "market_scope": "standard-first-10-raw-slots",
        "theorem": "naive own-price self-impact alone has zero intrinsic edge",
        "records": records,
        "summary": {
            "tape_count": len(tapes),
            "steps_per_tape": sorted({len(t) for t in tapes}),
            "positive_exact_buys_by_product": dict(sorted(buys.items())),
            "with_structural_candidate_by_product": dict(sorted(with_candidate.items())),
            "total_positive_exact_buys": sum(buys.values()),
            "total_with_structural_candidate": sum(with_candidate.values()),
            "same_day_candidates": same_day,
            "prior_day_candidates": prior_day,
            "gap_histogram": {str(k): gap_hist[k] for k in sorted(gap_hist)},
            "max_gap": max(gap_hist, default=None),
            "largest_gap_witnesses": witnesses,
        },
    }


def load_exact(path: Path):
    raw = path.read_bytes()
    got = git_blob_sha(raw)
    if got != EXPECTED_BLOB:
        raise SystemExit(f"SOURCE_MISMATCH expected={EXPECTED_BLOB} got={got}")
    spec = importlib.util.spec_from_file_location("_frozen_r01_tapes", path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot import source module")
    mod = importlib.util.module_from_spec(spec)
    # Execute the bytes authenticated above, not a second source read or a
    # timestamp-valid cached bytecode file selected by the import loader.
    exec(compile(raw, str(path), "exec"), mod.__dict__)
    tapes = mod.load_tapes()
    return tapes, hashlib.sha256(raw).hexdigest()


def self_test() -> None:
    # Explicit checks survive python -O; never use assert for this receipt.
    def require(condition, label):
        if not condition:
            raise RuntimeError("SELF_TEST_FAIL: " + label)

    t = [{"market": []} for _ in range(8)]
    t[1] = {"market": [["BUY_PRODUCT", "FERTILIZER", True]]}
    t[2] = {"market": [["BUY_PRODUCT", "WHEAT", 2]]}
    t[3] = {"market": [["BUY_ANIMAL", "COW", 1]]}
    t[5] = {"market": [["BUY_PRODUCT", "WHEAT", 3]]}
    t[6] = {"market": [["SELL", "FERTILIZER", 1]]}
    t[7] = {"market": [["BUY_PRODUCT", "FERTILIZER", 4]]}
    out = analyze([t], require_shape=False)
    require(out["summary"]["total_positive_exact_buys"] == 3, "positive buys")
    rec = {(r["later_step"], r["product"]): r for r in out["records"]}
    require(rec[(2, "WHEAT")]["candidate_step"] == 1, "WHEAT candidate")
    require(rec[(5, "WHEAT")]["candidate_step"] == 4, "second candidate")
    require(rec[(7, "FERTILIZER")]["candidate_step"] is None, "official SELL barrier")
    require(out["summary"]["max_gap"] == 1, "gap")
    t = [{"market": []}, {"market": [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 1]]}]
    require(analyze([t], False)["summary"]["total_positive_exact_buys"] == 0, "dead suffix")
    t = [{"market": []}, {"market": [["HIRE"], ["BUY_PRODUCT", "FERTILIZER", 1]]}]
    require(analyze([t], False)["records"][0]["candidate_step"] is None, "source HIRE bundle")
    print("SELF_TEST_PASS checks=7")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("module", nargs="?", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ns = ap.parse_args()
    if ns.self_test:
        self_test()
        return 0
    if ns.module is None:
        ap.error("module path is required unless --self-test")
    tapes, source_sha256 = load_exact(ns.module)
    result = analyze(tapes, require_shape=True)
    result["source_sha256"] = source_sha256
    payload = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if ns.output:
        ns.output.write_text(payload, encoding="utf-8", newline="")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
