#!/usr/bin/env python3
"""Exact-source carrier for the TITAN executable spend-reserve repair.

This module does not mutate the repository.  It binds the audited scheduler and
engine blobs, applies one exact textual replacement in memory, validates the
candidate with the Python parser, and emits a deterministic receipt or patch.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

BASE_COMMIT = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"
SCHEDULER_REL = Path("revenue/kaggriculture/cloud-execution-lab/scheduler.py")
ENGINE_REL = Path("revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py")
EXPECTED_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

OLD = """    def cash_reserve(self, obs, config, base, end):
        now=int(obs['step']);farm=dict(obs['farms'][obs['player']])
        farm['unlocked_quadrants']=list(farm['unlocked_quadrants'])
        hires=int(farm['hires_today']);cost=0
        route=self.controller.R[self.controller.cur]
        for t in range(now,end+1):
            if t>now and t%24==0:hires=0
            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            for order in orders:
                n,hires=_order_spend(order,farm,obs['market']['inventory'],obs['market'].get('params'),hires,config);cost+=n
                if order and order[0]=='BUY_LAND' and len(farm['unlocked_quadrants'])<=len(m.LAND_ORDER):
                    farm['unlocked_quadrants'].append(m.LAND_ORDER[len(farm['unlocked_quadrants'])-1])
        return cost
"""

NEW = """    def cash_reserve(self, obs, config, base, end):
        now=int(obs['step']);farm=dict(obs['farms'][obs['player']])
        farm['unlocked_quadrants']=list(farm['unlocked_quadrants'])
        hires=int(farm['hires_today']);cost=0
        max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))
        route=self.controller.R[self.controller.cur]
        for t in range(now,end+1):
            if t>now and t%24==0:hires=0
            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            # The engine truncates each raw queue before parsing.  Capped suffix
            # rows cannot spend cash or advance HIRE/land cursors.
            active=orders[:max_orders] if isinstance(orders,list) else ()
            for order in active:
                n,hires=_order_spend(order,farm,obs['market']['inventory'],obs['market'].get('params'),hires,config);cost+=n
                if order and order[0]=='BUY_LAND' and len(farm['unlocked_quadrants'])<=len(m.LAND_ORDER):
                    farm['unlocked_quadrants'].append(m.LAND_ORDER[len(farm['unlocked_quadrants'])-1])
        return cost
"""

ENGINE_ANCHORS = (
    'max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))',
    'q = list(m) if isinstance(m, list) else []',
    'queues.append(q[:max_orders])',
)
ACT_CAUSAL_ANCHOR = "minimum=current[item] if farm['money']<budget else 0"


class IntegrityError(RuntimeError):
    """Raised when an exact source or replacement boundary is not satisfied."""


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bound_read(repo: Path, relative: Path, expected_blob: str) -> bytes:
    root = repo.resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise IntegrityError(f"path escapes repository: {relative}")
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != expected_blob:
        raise IntegrityError(
            f"{relative}: expected Git blob {expected_blob}, observed {actual}"
        )
    return data


def apply_patch(source: str) -> str:
    count = source.count(OLD)
    if count != 1:
        raise IntegrityError(f"cash_reserve preimage count must be 1, observed {count}")
    candidate = source.replace(OLD, NEW, 1)
    ast.parse(candidate, filename=str(SCHEDULER_REL))
    if candidate.replace(NEW, OLD, 1) != source:
        raise IntegrityError("candidate changes escape the exact replacement hunk")
    return candidate


def build(repo: Path) -> tuple[bytes, bytes, bytes, str]:
    scheduler = _bound_read(repo, SCHEDULER_REL, EXPECTED_SCHEDULER_GIT_BLOB)
    engine = _bound_read(repo, ENGINE_REL, EXPECTED_ENGINE_GIT_BLOB)
    scheduler_text = scheduler.decode("utf-8")
    engine_text = engine.decode("utf-8")
    missing = [anchor for anchor in ENGINE_ANCHORS if engine_text.count(anchor) != 1]
    if missing:
        raise IntegrityError(f"engine prefix anchors missing or duplicated: {missing!r}")
    if scheduler_text.count(ACT_CAUSAL_ANCHOR) != 1:
        raise IntegrityError("budget-to-minimum causal anchor missing or duplicated")
    candidate_text = apply_patch(scheduler_text)
    patch = "".join(
        difflib.unified_diff(
            scheduler_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=f"a/{SCHEDULER_REL.as_posix()}",
            tofile=f"b/{SCHEDULER_REL.as_posix()}",
        )
    )
    if patch.count("@@") != 2:
        raise IntegrityError("repair must remain exactly one unified-diff hunk")
    return scheduler, engine, candidate_text.encode("utf-8"), patch


def receipt(repo: Path) -> dict[str, Any]:
    scheduler, engine, candidate, patch = build(repo)
    return {
        "schema": "titan-v3-executable-spend-reserve-closure/v1",
        "base_commit": BASE_COMMIT,
        "scheduler": {
            "path": SCHEDULER_REL.as_posix(),
            "git_blob": git_blob_sha(scheduler),
            "sha256": sha256(scheduler),
            "bytes": len(scheduler),
        },
        "engine": {
            "path": ENGINE_REL.as_posix(),
            "git_blob": git_blob_sha(engine),
            "sha256": sha256(engine),
            "bytes": len(engine),
            "raw_prefix_contract": True,
        },
        "candidate": {
            "git_blob": git_blob_sha(candidate),
            "sha256": sha256(candidate),
            "bytes": len(candidate),
            "replacement_count": 1,
            "unified_diff_hunks": 1,
        },
        "causal_boundary": "cash_reserve -> farm.money<budget -> minimum_now",
        "canonical_mutated": False,
        "patch_sha256": sha256(patch.encode("utf-8")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json", "patch"), default="json")
    args = parser.parse_args()
    if args.format == "patch":
        print(build(args.repo)[3], end="")
    else:
        print(json.dumps(receipt(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
