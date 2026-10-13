#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-source repair for scheduler executable-market-prefix accounting.

This source-only transformer does not import the scheduler, change production,
execute a legacy materializer, or enable a feature. Its command line writes the
postimage to stdout; the input is always read-only. See README.md for scope.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path
import sys

SOURCE_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
UPSTREAM_PREFIX_DONOR = "5e8f54ca20fa755bc6ced55decdcdf0193cda812"

# Preserve the upstream donor's one shared helper and two forecast consumers.
HELPER = '''def _engine_market_prefix(action, config):
    # Official interpreter: normalize only list-valued market queues, then
    # execute q[:max(1, maxMarketOrdersPerTurn)] without compaction.
    market=action.get('market',[]) if isinstance(action,dict) else []
    q=list(market) if isinstance(market,list) else []
    return q[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]


'''
FORECAST_OLD = """            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            for {name} in orders:
"""
FORECAST_NEW = """            market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)
            orders=_engine_market_prefix(market_action,config)
            for {name} in orders:
"""


class SourceMismatch(ValueError):
    """The source is not the reviewed predecessor or an anchor drifted."""


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SourceMismatch(f"{label}: expected one occurrence, got {count}")
    return source.replace(old, new, 1)


def transform(source: bytes) -> bytes:
    """Return the reviewed postimage, rejecting drift and repeated application."""
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    if git_blob_sha(source) != SOURCE_GIT_BLOB:
        raise SourceMismatch("scheduler predecessor Git blob does not match")
    text = source.decode("utf-8")
    text = _once(text, "\n\nclass SellScheduler:\n",
                 "\n\n" + HELPER + "class SellScheduler:\n", "shared prefix helper")
    for name in ("order", "o"):
        text = _once(text, FORECAST_OLD.format(name=name),
                     FORECAST_NEW.format(name=name), f"forecast {name}")
    text = _once(text,
                 "        for o in base['market']:\n",
                 "        for o in _engine_market_prefix(base,config):\n",
                 "current baseline quantities")
    text = _once(text,
                 "                for order in route[t].get('market',[]) if t<len(route) else []:\n",
                 "                for order in _engine_market_prefix(route[t] if t<len(route) else parent.PASS,config):\n",
                 "future reference quantities")
    text = _once(text,
                 "                    orders=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
                 "                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n",
                 "                    market_action=base if t==now else (route[t] if t<len(route) else parent.PASS)\n"
                 "                    orders=_engine_market_prefix(market_action,config)\n"
                 "                    if len(orders)>=max(1,int(config.get('maxMarketOrdersPerTurn',10))):\n",
                 "executable offered capacity")
    text = _once(text,
                 "        for raw in out['market']:\n            o=list(raw)\n",
                 "        max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n"
                 "        for index,raw in enumerate(out['market']):\n"
                 "            # The engine never parses capped suffix rows. Preserve them\n"
                 "            # verbatim; they cannot consume executable stock or plans.\n"
                 "            if index>=max_orders:\n"
                 "                market.append(raw)\n"
                 "                continue\n"
                 "            o=list(raw)\n",
                 "suffix preservation")
    text = _once(text,
                 "            if q>0 and len(market)<int(config.get('maxMarketOrdersPerTurn',10)):\n",
                 "            if q>0 and len(market)<max_orders:\n",
                 "append cap clamp")
    text = _once(text,
                 "            sold=sum(o[2] for o in out['market'] if o and o[0]=='SELL' and o[1]==item)\n",
                 "            sold=sum(o[2] for o in _engine_market_prefix(out,config) if o and o[0]=='SELL' and o[1]==item)\n",
                 "pending and planned retirement")
    tree = ast.parse(text, filename="<scheduler-action-prefix>")
    helpers = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "_engine_market_prefix"]
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "_engine_market_prefix"]
    if len(helpers) != 1 or len(calls) != 6:
        raise SourceMismatch("expected one shared helper and six prefix consumers")
    compile(tree, "<scheduler-action-prefix>", "exec")
    return text.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact predecessor scheduler; read only")
    args = parser.parse_args(argv)
    try:
        candidate = transform(args.source.read_bytes())
    except (OSError, UnicodeError, SourceMismatch) as exc:
        print(f"scheduler-action-prefix: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
