#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose scheduler calendar + executable-market custody after V4 prefix repair.

Input is the exact output of ``materialize_scheduler_prefix.py``. This stage
closes the remaining hard-coded day-boundary assumptions and binds every
scheduler market-capacity consumer to the engine's same minimum-one limit.
It is a source-only scratch materializer: production files are never edited
in place.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Final

RAW_SCHEDULER_GIT_BLOB: Final = "a483b24dd72b580d7d8811636b54d2d44f391575"
PREFIX_MATERIALIZER_GIT_BLOB: Final = "f36e9120ea07c861a7eca5821a5306c6dbfa4613"
PREFIXED_SCHEDULER_GIT_BLOB: Final = "1da9934ec45f485a16244bcbc78af26d9109b97e"
ENGINE_GIT_BLOB: Final = "3c202c7ee921da239356789e266b694635103fc4"

CLASS_ANCHOR: Final = "\n\nclass SellScheduler:\n"
CALENDAR_HELPER: Final = """\
def _strict_scheduler_turns_per_day(config):
    # Projection calendar must not broaden Python coercion semantics.  A
    # malformed day length cannot authenticate represented future state.
    raw=config.get('turnsPerDay',24) if isinstance(config,dict) else None
    if type(raw) is not int or raw<=0:
        raise ValueError('scheduler turnsPerDay must be a positive plain int')
    return raw


class SellScheduler:
"""

MARKET_PREFIX_DEF_OLD: Final = "def _engine_market_prefix(action, config):\n"
MARKET_PREFIX_DEF_NEW: Final = """\
def _engine_market_limit(config):
    # Match the official interpreter and the canonical prefix projection:
    # at least row zero executes for any int-coercible configured cap.
    return max(1,int(config.get('maxMarketOrdersPerTurn',10)))


def _engine_market_prefix(action, config):
"""
MARKET_PREFIX_RETURN_OLD: Final = "    return q[:max(1,int(config.get('maxMarketOrdersPerTurn',10)))]\n"
MARKET_PREFIX_RETURN_NEW: Final = "    return q[:_engine_market_limit(config)]\n"

CASH_START_OLD: Final = "        now=int(obs['step']);farm=dict(obs['farms'][obs['player']])\n"
CASH_START_NEW: Final = (
    "        now=int(obs['step']);farm=dict(obs['farms'][obs['player']])\n"
    "        turns_per_day=_strict_scheduler_turns_per_day(config)\n"
)
CASH_RESET_OLD: Final = "            if t>now and t%24==0:hires=0\n"
CASH_RESET_NEW: Final = "            if t>now and t%turns_per_day==0:hires=0\n"

RECEIPT_START_OLD: Final = "        now=int(obs['step']);cap=int(config.get('shedCapacity',100))\n"
RECEIPT_START_NEW: Final = (
    "        now=int(obs['step']);cap=int(config.get('shedCapacity',100))\n"
    "        turns_per_day=_strict_scheduler_turns_per_day(config)\n"
)
UNIT_STAGE_OLD: Final = (
    "                    m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)\n"
)
UNIT_STAGE_NEW: Final = (
    "                    m._apply_unit_action(f,p,i,a,len(f['tiles']),"
    "t//turns_per_day,turns_per_day,10**6)\n"
)
EOD_OLD: Final = "            if t%24==23:\n"
EOD_NEW: Final = "            if t%turns_per_day==turns_per_day-1:\n"

ACT_START_OLD: Final = "        config=dict(config or {});now=int(obs['step']);last=int(config.get('episodeSteps',720))-2\n"
ACT_START_NEW: Final = (
    "        config=dict(config or {});now=int(obs['step']);last=int(config.get('episodeSteps',720))-2\n"
    "        turns_per_day=_strict_scheduler_turns_per_day(config)\n"
    "        market_limit=_engine_market_limit(config)\n"
)
ACT_END_OLD: Final = "        end=min(now+HORIZON,last,(now//24+1)*24-1)\n"
ACT_END_NEW: Final = (
    "        end=min(now+HORIZON,last,(now//turns_per_day+1)*turns_per_day-1)\n"
)
ACT_NAIVE_EOD_OLD: Final = "                if farm['money']<budget or now%24==23:take=max(take,current[item])\n"
ACT_NAIVE_EOD_NEW: Final = (
    "                if farm['money']<budget or now%turns_per_day==turns_per_day-1:"
    "take=max(take,current[item])\n"
)

ACT_FEASIBLE_CAP_OLD: Final = "                    if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):\n"
ACT_FEASIBLE_CAP_NEW: Final = "                    if len(orders)>=market_limit:\n"
ACT_APPEND_CAP_OLD: Final = "            if q>0 and len(market)<int(config.get('maxMarketOrdersPerTurn',10)):\n"
ACT_APPEND_CAP_NEW: Final = "            if q>0 and len(market)<market_limit:\n"

ENGINE_ANCHORS: Final = (
    'turns_per_day = max(1, int(get(cfg, "turnsPerDay", 24)))',
    'max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))',
    'queues.append(q[:max_orders])',
    'day = step // turns_per_day',
    'if (step + 1) % turns_per_day == 0:',
    '_apply_unit_action(obs0.farms[i], s.observation.private, 0, _allowed(farmer_action),',
    'board_size, day, turns_per_day, shed_capacity)',
)
PREFIX_ANCHORS: Final = (
    "def _engine_market_prefix(action, config):",
    "orders=_engine_market_prefix(market_action,config)",
)


class CalendarMaterializationError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise CalendarMaterializationError(
            f"{label}: expected exactly one anchor, found {count}"
        )
    return text.replace(old, new, 1)


def verify_engine(engine_text: str) -> None:
    missing = [anchor for anchor in ENGINE_ANCHORS if engine_text.count(anchor) < 1]
    if missing:
        raise CalendarMaterializationError(
            f"official engine calendar anchors missing: {missing!r}"
        )


def transform_prefixed(source: str) -> str:
    if source.count("def _strict_scheduler_turns_per_day("):
        raise CalendarMaterializationError("calendar helper already present")
    if source.count(CLASS_ANCHOR) != 1:
        raise CalendarMaterializationError("SellScheduler insertion anchor missing or ambiguous")
    if source.count(PREFIX_ANCHORS[0]) != 1:
        raise CalendarMaterializationError("canonical scheduler-prefix helper missing")
    if source.count(PREFIX_ANCHORS[1]) != 2:
        raise CalendarMaterializationError("canonical scheduler-prefix consumers missing")
    if source.count(MARKET_PREFIX_RETURN_OLD) != 1:
        raise CalendarMaterializationError("canonical minimum-one prefix return missing")

    out = source.replace(CLASS_ANCHOR, "\n\n" + CALENDAR_HELPER, 1)
    out = _replace_once(out, MARKET_PREFIX_DEF_OLD, MARKET_PREFIX_DEF_NEW, "market limit helper bind")
    out = _replace_once(out, MARKET_PREFIX_RETURN_OLD, MARKET_PREFIX_RETURN_NEW, "prefix market limit bind")
    out = _replace_once(out, CASH_START_OLD, CASH_START_NEW, "cash_reserve calendar bind")
    out = _replace_once(out, CASH_RESET_OLD, CASH_RESET_NEW, "cash_reserve hire reset")
    out = _replace_once(out, RECEIPT_START_OLD, RECEIPT_START_NEW, "receipt calendar bind")
    out = _replace_once(out, UNIT_STAGE_OLD, UNIT_STAGE_NEW, "receipt future unit stage")
    out = _replace_once(out, EOD_OLD, EOD_NEW, "receipt end-of-day boundary")
    out = _replace_once(out, ACT_START_OLD, ACT_START_NEW, "act calendar bind")
    out = _replace_once(out, ACT_END_OLD, ACT_END_NEW, "act horizon day boundary")
    out = _replace_once(out, ACT_NAIVE_EOD_OLD, ACT_NAIVE_EOD_NEW, "act naive EOD guard")
    out = _replace_once(out, ACT_FEASIBLE_CAP_OLD, ACT_FEASIBLE_CAP_NEW, "act feasibility market limit")
    out = _replace_once(out, ACT_APPEND_CAP_OLD, ACT_APPEND_CAP_NEW, "act append market limit")

    for predecessor in (
        CASH_RESET_OLD,
        UNIT_STAGE_OLD,
        EOD_OLD,
        ACT_END_OLD,
        ACT_NAIVE_EOD_OLD,
        MARKET_PREFIX_RETURN_OLD,
        ACT_FEASIBLE_CAP_OLD,
        ACT_APPEND_CAP_OLD,
    ):
        if predecessor in out:
            raise CalendarMaterializationError("hard-coded calendar predecessor survived")
    if out.count("turns_per_day=_strict_scheduler_turns_per_day(config)") != 3:
        raise CalendarMaterializationError("calendar binding cardinality drift")
    if out.count("def _strict_scheduler_turns_per_day(") != 1:
        raise CalendarMaterializationError("calendar helper cardinality drift")
    if out.count("def _engine_market_limit(") != 1:
        raise CalendarMaterializationError("market limit helper cardinality drift")
    if out.count("market_limit=_engine_market_limit(config)") != 1:
        raise CalendarMaterializationError("act market limit binding cardinality drift")
    if out.count("_engine_market_limit(config)") != 3:
        raise CalendarMaterializationError("market limit consumer cardinality drift")
    if out.count(PREFIX_ANCHORS[1]) != 2:
        raise CalendarMaterializationError("prefix consumers changed unexpectedly")
    ast.parse(out, filename="<v4-scheduler-calendar-custody>")
    return out


def materialize(prefixed_source_bytes: bytes, engine_bytes: bytes) -> bytes:
    observed_source = git_blob_sha(prefixed_source_bytes)
    if observed_source != PREFIXED_SCHEDULER_GIT_BLOB:
        raise CalendarMaterializationError(
            f"prefixed scheduler Git blob mismatch: {observed_source}"
        )
    observed_engine = git_blob_sha(engine_bytes)
    if observed_engine != ENGINE_GIT_BLOB:
        raise CalendarMaterializationError(
            f"engine Git blob mismatch: {observed_engine}"
        )
    try:
        engine_text = engine_bytes.decode("utf-8")
        source_text = prefixed_source_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise CalendarMaterializationError("bound input is not UTF-8") from exc
    verify_engine(engine_text)
    return transform_prefixed(source_text).encode("utf-8")


def _receipt(prefixed: bytes, engine: bytes, candidate: bytes) -> dict[str, object]:
    return {
        "operation": "SOL-SCHEDULER-CUSTODY-WIDE",
        "admission": "SOURCE_ONLY_MERGEABLE_ACTIVATION_STILL_GATED",
        "raw_scheduler_git_blob": RAW_SCHEDULER_GIT_BLOB,
        "prefix_materializer_git_blob": PREFIX_MATERIALIZER_GIT_BLOB,
        "prefixed_scheduler_git_blob": git_blob_sha(prefixed),
        "engine_git_blob": git_blob_sha(engine),
        "candidate_scheduler_git_blob": git_blob_sha(candidate),
        "mutations": [
            "cash_reserve hire-day reset uses strict configured turnsPerDay",
            "receipt_profile future unit day/turn arguments use strict configured turnsPerDay",
            "receipt_profile EOD/drop boundary uses strict configured turnsPerDay",
            "act horizon clipping uses strict configured turnsPerDay",
            "act naive EOD guard uses strict configured turnsPerDay",
            "canonical prefix and both act market-cap guards share official minimum-one limit",
        ],
        "production_activation": False,
        "default_changed": False,
        "runtime_file_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact scheduler-prefix scratch output")
    parser.add_argument("output", type=Path, help="new scratch scheduler postimage")
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    engine_bytes = args.engine.read_bytes()
    candidate = materialize(source_bytes, engine_bytes)

    resolved_inputs = {
        args.source.resolve(strict=False),
        args.engine.resolve(strict=False),
    }
    if args.output.resolve(strict=False) in resolved_inputs:
        raise CalendarMaterializationError("output must not alias a bound input")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(candidate)
    if args.source.read_bytes() != source_bytes or args.engine.read_bytes() != engine_bytes:
        raise CalendarMaterializationError("bound input changed during materialization")
    if args.output.read_bytes() != candidate:
        raise CalendarMaterializationError("output readback mismatch")

    receipt = _receipt(source_bytes, engine_bytes, candidate)
    if args.receipt is not None:
        if args.receipt.resolve(strict=False) in resolved_inputs | {args.output.resolve(strict=False)}:
            raise CalendarMaterializationError("receipt must not alias source/engine/output")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
