#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""V4 donor: bind SELL scheduler projections to the engine-executable raw market prefix.

This is a source-only materializer. It authenticates the exact current V4
scheduler, applies one shared prefix helper to exactly cash_reserve() and
receipt_profile(), compiles the postimage, and never mutates the input.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_GIT_BLOB = "da1b6fb571e79ba7dab54c8d816e45afb934e4d2"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

HELPER_ANCHOR = "\n\nclass SellScheduler:\n"
HELPER = """\
def _engine_market_prefix(action, config):
    # Official interpreter: normalize only list-valued market queues, then
    # execute q[:max(1, maxMarketOrdersPerTurn)] without compaction.
    market=action.get('market',[]) if isinstance(action,dict) else []
    q=list(market) if isinstance(market,list) else []
    return q[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]


class SellScheduler:
"""

CALLSITE = """\
            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            for {name} in orders:
"""
REPLACEMENT = """\
            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
            orders=_engine_market_prefix(market_action,config)
            for {name} in orders:
"""

ENGINE_ANCHORS = (
    'max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))',
    'q = list(m) if isinstance(m, list) else []',
    'queues.append(q[:max_orders])',
)

class MaterializationError(RuntimeError):
    pass

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

def _replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise MaterializationError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)

def transform(source: str) -> str:
    if "def _engine_market_prefix(" in source:
        raise MaterializationError("prefix helper already present")
    if source.count(HELPER_ANCHOR) != 1:
        raise MaterializationError("SellScheduler insertion anchor missing or ambiguous")

    cash_old = CALLSITE.format(name="order")
    cash_new = REPLACEMENT.format(name="order")
    receipt_old = CALLSITE.format(name="o")
    receipt_new = REPLACEMENT.format(name="o")

    if source.count(cash_old) != 1:
        raise MaterializationError("cash_reserve queue anchor missing or ambiguous")
    if source.count(receipt_old) != 1:
        raise MaterializationError("receipt_profile queue anchor missing or ambiguous")

    out = source.replace(HELPER_ANCHOR, "\n\n" + HELPER, 1)
    out = _replace_exact(out, cash_old, cash_new, "cash_reserve")
    out = _replace_exact(out, receipt_old, receipt_new, "receipt_profile")

    if out.count("def _engine_market_prefix(") != 1:
        raise MaterializationError("helper cardinality drift")
    if out.count("orders=_engine_market_prefix(market_action,config)") != 2:
        raise MaterializationError("prefix consumer cardinality drift")
    if cash_old in out or receipt_old in out:
        raise MaterializationError("raw full-queue consumer survived")
    ast.parse(out, filename="<v4-scheduler-executable-prefix>")
    return out

def self_test() -> None:
    fixture = """\
class Prefix:
    pass


class SellScheduler:
    def cash_reserve(self, obs, config, base, end):
        now=0
        route=[]
        for t in range(now,end+1):
""" + CALLSITE.format(name="order") + """\
                pass

    def receipt_profile(self, obs, base, farm, private, end, item, config):
        now=0
        route=[]
        for t in range(now,end+1):
""" + CALLSITE.format(name="o") + """\
                pass
"""
    got = transform(fixture)
    if got.count("orders=_engine_market_prefix(market_action,config)") != 2:
        raise AssertionError("self-test: both consumers not routed through helper")
    if "_engine_market_prefix" not in got:
        raise AssertionError("self-test: helper missing")
    try:
        transform(got)
    except MaterializationError:
        pass
    else:
        raise AssertionError("self-test: double apply must fail closed")

    # Pure semantic vectors mirrored from the official raw-prefix contract.
    def prefix(action, config):
        market=action.get("market",[]) if isinstance(action,dict) else []
        q=list(market) if isinstance(market,list) else []
        return q[:max(1,int(config.get("maxMarketOrdersPerTurn",10)))]
    if prefix({"market":[[],["HIRE"],["BUY_LAND"]]}, {"maxMarketOrdersPerTurn":1}) != [[]]:
        raise AssertionError("self-test: capped suffix must be inert")
    if prefix({"market":[["SELL","MILK",1],["HIRE"]]}, {"maxMarketOrdersPerTurn":0}) != [["SELL","MILK",1]]:
        raise AssertionError("self-test: nonpositive cap must clamp to one")
    if prefix({"market":"not-a-list"}, {"maxMarketOrdersPerTurn":10}) != []:
        raise AssertionError("self-test: non-list queue must normalize empty")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", type=Path)
    ap.add_argument("output", nargs="?", type=Path)
    ap.add_argument("--engine", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ns = ap.parse_args()
    if ns.self_test:
        self_test()
        return 0
    if ns.source is None or ns.output is None or ns.engine is None:
        ap.error("source, output, and --engine are required unless --self-test is used")
    source_bytes = ns.source.read_bytes()
    if git_blob_sha(source_bytes) != SOURCE_GIT_BLOB:
        raise MaterializationError("scheduler Git blob mismatch")
    engine_bytes = ns.engine.read_bytes()
    if git_blob_sha(engine_bytes) != ENGINE_GIT_BLOB:
        raise MaterializationError("engine Git blob mismatch")
    engine_text = engine_bytes.decode("utf-8")
    missing = [x for x in ENGINE_ANCHORS if engine_text.count(x) != 1]
    if missing:
        raise MaterializationError(f"engine raw-prefix anchors missing/ambiguous: {missing!r}")
    source_text = source_bytes.decode("utf-8")
    candidate = transform(source_text).encode("utf-8")
    if ns.source.resolve(strict=False) == ns.output.resolve(strict=False):
        raise MaterializationError("output must not alias source")
    ns.output.write_bytes(candidate)
    if ns.source.read_bytes() != source_bytes:
        ns.output.unlink(missing_ok=True)
        raise MaterializationError("source mutated during materialization")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
