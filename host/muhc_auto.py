#!/usr/bin/env python3
"""Deterministic, source-bound selector for complete verified MUHC containers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evolve
import muhc


SCHEMA = "muhc-auto-organ/v1"
MAX_DEPTH_LIMIT = 6
MAX_BEAM_LIMIT = 64
ENTROPIES = ("zlib", "bz2", "lzma")


class AutoOrganError(ValueError):
    """Invalid selector input or an impossible verified search."""


def _clean_opts(opts):
    return {key: opts[key] for key in sorted(opts)}


def _candidate_id(codec, opts):
    suffix = json.dumps(_clean_opts(opts), sort_keys=True, separators=(",", ":"))
    return "%s:%s" % (codec, suffix)


def _validate(data, width, max_depth, beam_width, entropies):
    if not isinstance(data, (bytes, bytearray)):
        raise AutoOrganError("data must be bytes")
    if not data:
        raise AutoOrganError("data must not be empty")
    if not isinstance(width, int) or width < 1:
        raise AutoOrganError("width must be a positive integer")
    if not isinstance(max_depth, int) or not 0 <= max_depth <= MAX_DEPTH_LIMIT:
        raise AutoOrganError("max_depth must be between 0 and %d" % MAX_DEPTH_LIMIT)
    if not isinstance(beam_width, int) or not 1 <= beam_width <= MAX_BEAM_LIMIT:
        raise AutoOrganError("beam_width must be between 1 and %d" % MAX_BEAM_LIMIT)
    if not entropies:
        raise AutoOrganError("at least one entropy codec is required")
    unknown = sorted(set(entropies) - set(ENTROPIES))
    if unknown:
        raise AutoOrganError("unknown entropy codecs: %s" % ", ".join(unknown))


def _evaluate(data, width, codec, opts, source_sha, seen, candidates, failures):
    cid = _candidate_id(codec, opts)
    if cid in seen:
        return None
    seen.add(cid)
    try:
        blob = muhc.encode_bytes(data, width, codec=codec, **opts)
        restored, header = muhc.decode_bytes(blob)
        if restored != data:
            raise muhc.MuhcCorrupt("decoded bytes differ from source")
        if header["sha256"] != source_sha:
            raise muhc.MuhcCorrupt("decoded SHA differs from source SHA")
        parsed, _payload = muhc.parse_header(blob)
        if parsed["total"] != len(blob):
            raise muhc.MuhcCorrupt("container accounting differs from artifact length")
    except Exception as exc:
        failures.append({
            "id": cid,
            "error_type": type(exc).__name__,
            "error": str(exc)[:200],
        })
        return None
    row = {
        "id": cid,
        "codec": parsed["codec_name"],
        "opts": _clean_opts(opts),
        "container_b": len(blob),
        "payload_b": parsed["payload_len"],
        "overhead_b": parsed["overhead"],
        "source_sha256": source_sha,
        "container_sha256": hashlib.sha256(blob).hexdigest(),
        "_blob": blob,
    }
    candidates.append(row)
    return row


def _stack_specs(width, height):
    tile_widths = {width, max(1, width // 2), max(1, width // 4)}
    for exact in (25, 50):
        if exact <= width:
            tile_widths.add(exact)
    tile_heights = {1}
    for tile_h in (2, 4, 8, 16, 32, 64):
        if tile_h <= height:
            tile_heights.add(tile_h)
    for tile_w in sorted(tile_widths):
        for tile_h in sorted(tile_heights):
            yield {"tile_w": tile_w, "tile_h": tile_h}


def _fold_specs(height):
    levels = {1}
    for folds in (2, 4, 8):
        if folds <= max(1, height.bit_length()):
            levels.add(folds)
    for mode in ("adjacent", "mirror", "translate"):
        for folds in sorted(levels):
            yield {"folds": folds, "mode": mode}


def select_bytes(data, width=200, max_depth=2, beam_width=4, entropies=ENTROPIES):
    """Return (winning_container, report) after exact verification of every accepted candidate."""
    data = bytes(data)
    entropies = tuple(entropies)
    _validate(data, width, max_depth, beam_width, entropies)
    source_sha = hashlib.sha256(data).hexdigest()
    height = (len(data) * 8 + width - 1) // width
    candidates = []
    failures = []
    seen = set()

    raw = _evaluate(data, width, "raw", {}, source_sha, seen, candidates, failures)
    if raw is None:
        raise AutoOrganError("raw MUHC baseline failed exact verification")

    for opts in _stack_specs(width, height):
        _evaluate(data, width, "stack", opts, source_sha, seen, candidates, failures)
    for opts in _fold_specs(height):
        _evaluate(data, width, "fold", opts, source_sha, seen, candidates, failures)

    parents = [()]
    for _depth in range(1, max_depth + 1):
        programs = sorted({parent + (op,) for parent in parents for op in evolve.NAMES})
        ranked = []
        for program in programs:
            rows = []
            for entropy in entropies:
                row = _evaluate(
                    data,
                    width,
                    "evolve",
                    {"entropy": entropy, "program": list(program)},
                    source_sha,
                    seen,
                    candidates,
                    failures,
                )
                if row is not None:
                    rows.append(row)
            if rows:
                best = min(rows, key=lambda item: (item["container_b"], item["id"]))
                ranked.append((best["container_b"], best["id"], program))
        parents = [item[2] for item in sorted(ranked)[:beam_width]]
        if not parents:
            break

    winner = min(candidates, key=lambda item: (item["container_b"], item["id"]))
    public_candidates = [
        {key: value for key, value in row.items() if key != "_blob"}
        for row in sorted(candidates, key=lambda item: item["id"])
    ]
    chosen = {key: value for key, value in winner.items() if key != "_blob"}
    report = {
        "schema": SCHEMA,
        "state": "VERIFIED",
        "source": {
            "bytes": len(data),
            "sha256": source_sha,
            "width": width,
            "height": height,
        },
        "search": {
            "max_depth": max_depth,
            "beam_width": beam_width,
            "entropies": list(entropies),
            "persistent_ledger": False,
            "tie_break": "container_b_then_candidate_id",
        },
        "candidate_count": len(public_candidates),
        "failure_count": len(failures),
        "failures": failures,
        "raw_container_b": raw["container_b"],
        "chosen": chosen,
        "saved_vs_raw_container_b": raw["container_b"] - winner["container_b"],
        "candidates": public_candidates,
        "guarantees": {
            "complete_container_bytes_counted": True,
            "every_accepted_candidate_decoded": True,
            "every_accepted_candidate_source_sha_matched": True,
            "source_bound_search": True,
        },
    }
    return winner["_blob"], report


def _cmd_select(args):
    data = Path(args.src).read_bytes()
    blob, report = select_bytes(
        data,
        width=args.width,
        max_depth=args.max_depth,
        beam_width=args.beam_width,
        entropies=tuple(args.entropies),
    )
    Path(args.dst).write_bytes(blob)
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Choose the smallest fully framed, exactly verified MUHC container"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    select = sub.add_parser("select")
    select.add_argument("src")
    select.add_argument("dst")
    select.add_argument("--report")
    select.add_argument("--width", type=int, default=200)
    select.add_argument("--max-depth", type=int, default=2)
    select.add_argument("--beam-width", type=int, default=4)
    select.add_argument("--entropies", nargs="+", choices=ENTROPIES, default=list(ENTROPIES))
    args = parser.parse_args(argv)
    if args.cmd == "select":
        return _cmd_select(args)
    raise AutoOrganError("unknown command")


if __name__ == "__main__":
    sys.exit(main() or 0)
