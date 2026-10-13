#!/usr/bin/env python3
"""Strict side-by-side experiment receipt validation.

Callers provide the literal requested panel and the live canonical SHA.  This
module validates that a receipt covers that exact cartesian panel once, with
strict integer seeds, finite scores, and current canonical provenance.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA = "commons-strict-receipt/v1"
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key before indexing: %s" % key)
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_strict_object,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("non-finite JSON value: %s" % value)
        ),
    )


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % field)
    return value.strip()


def _literal_nonempty(value: Any, field: str) -> str:
    """Validate an identifier without rewriting its literal identity."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % field)
    return value


def _strict_int(value: Any, field: str) -> int:
    if type(value) is not int:  # bool is intentionally rejected.
        raise ValueError("%s must be a strict non-bool integer" % field)
    return value


def _finite(value: Any, field: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("%s must be a finite numeric score" % field)
    return value


def normalize_sha(value: Any, field: str = "canonical_sha") -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise ValueError("%s must be exactly 40 hexadecimal characters" % field)
    return value.lower()


def normalize_panel(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("requested panel must be an object")
    if set(value) != {"seeds", "opponents"}:
        raise ValueError("requested panel must contain exactly seeds and opponents")
    seeds_in = value["seeds"]
    opponents_in = value["opponents"]
    if not isinstance(seeds_in, list) or not seeds_in:
        raise ValueError("requested panel seeds must be a non-empty list")
    if not isinstance(opponents_in, list) or not opponents_in:
        raise ValueError("requested panel opponents must be a non-empty list")
    seeds: List[int] = []
    seen_seeds = set()
    for index, item in enumerate(seeds_in):
        seed = _strict_int(item, "requested_panel.seeds[%d]" % index)
        if seed in seen_seeds:
            raise ValueError("duplicate requested seed: %s" % seed)
        seen_seeds.add(seed)
        seeds.append(seed)
    opponents: List[str] = []
    seen_opponents = set()
    for index, item in enumerate(opponents_in):
        opponent = _literal_nonempty(item, "requested_panel.opponents[%d]" % index)
        if opponent in seen_opponents:
            raise ValueError("duplicate requested opponent: %s" % opponent)
        seen_opponents.add(opponent)
        opponents.append(opponent)
    return {"seeds": seeds, "opponents": opponents}


def expected_pairs(panel: Mapping[str, Any]) -> List[Tuple[int, str]]:
    normalized = normalize_panel(panel)
    return [(seed, opponent) for seed in normalized["seeds"] for opponent in normalized["opponents"]]


def normalize_cell(value: Mapping[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("cells[%d] must be an object" % index)
    if set(value) != {"seed", "opponent", "score"}:
        raise ValueError("cells[%d] must contain exactly seed, opponent, score" % index)
    return {
        "seed": _strict_int(value["seed"], "cells[%d].seed" % index),
        "opponent": _literal_nonempty(value["opponent"], "cells[%d].opponent" % index),
        "score": _finite(value["score"], "cells[%d].score" % index),
    }


def validate_receipt(receipt: Mapping[str, Any], requested_panel: Mapping[str, Any],
                     live_canonical_sha: str) -> Dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise ValueError("receipt must be an object")
    allowed = {"schema", "hypothesis_id", "objective", "canonical_sha", "panel", "cells", "evidence"}
    required = {"schema", "hypothesis_id", "objective", "canonical_sha", "panel", "cells"}
    extra = set(receipt) - allowed
    missing = required - set(receipt)
    if missing:
        raise ValueError("missing receipt fields: %s" % ", ".join(sorted(missing)))
    if extra:
        raise ValueError("unexpected receipt fields: %s" % ", ".join(sorted(extra)))
    if receipt["schema"] != SCHEMA:
        raise ValueError("unsupported receipt schema")

    requested = normalize_panel(requested_panel)
    declared = normalize_panel(receipt["panel"])
    if declared != requested:
        raise ValueError("receipt panel does not equal the literal requested panel")

    canonical_sha = normalize_sha(receipt["canonical_sha"], "receipt.canonical_sha")
    live_sha = normalize_sha(live_canonical_sha, "live_canonical_sha")
    if canonical_sha != live_sha:
        raise ValueError("stale canonical: receipt %s != live %s" % (canonical_sha, live_sha))

    cells_in = receipt["cells"]
    if not isinstance(cells_in, list):
        raise ValueError("cells must be a list")

    # Reject duplicates while consuming the raw sequence, before any indexing or
    # dictionary construction can overwrite one observation with another.
    cells: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(cells_in):
        cell = normalize_cell(raw, index)
        key = (cell["seed"], cell["opponent"])
        if key in seen:
            raise ValueError("duplicate cell before indexing: seed=%s opponent=%s" % key)
        seen.add(key)
        cells.append(cell)

    expected = expected_pairs(requested)
    expected_set = set(expected)
    observed_set = set(seen)
    missing_pairs = [pair for pair in expected if pair not in observed_set]
    extra_pairs = sorted(observed_set - expected_set)
    if missing_pairs or extra_pairs or len(cells) != len(expected):
        raise ValueError(
            "cartesian membership mismatch: expected=%d observed=%d missing=%s extra=%s"
            % (len(expected), len(cells), missing_pairs, extra_pairs)
        )

    evidence_in = receipt.get("evidence", [])
    if not isinstance(evidence_in, list):
        raise ValueError("evidence must be a list")
    evidence = sorted(set(_nonempty(item, "evidence item") for item in evidence_in))

    normalized_cells = sorted(cells, key=lambda cell: (cell["seed"], cell["opponent"]))
    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "hypothesis_id": _nonempty(receipt["hypothesis_id"], "hypothesis_id"),
        "objective": _nonempty(receipt["objective"], "objective"),
        "canonical_sha": canonical_sha,
        "panel": requested,
        "cells": normalized_cells,
    }
    if evidence:
        out["evidence"] = evidence
    return out


def validate_text(receipt_text: str, requested_panel_text: str, live_canonical_sha: str) -> Dict[str, Any]:
    receipt = loads_strict(receipt_text)
    panel = loads_strict(requested_panel_text)
    if not isinstance(receipt, dict) or not isinstance(panel, dict):
        raise ValueError("receipt and requested panel must decode to objects")
    return validate_receipt(receipt, panel, live_canonical_sha)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Commons strict experiment receipt")
    parser.add_argument("receipt")
    parser.add_argument("--requested-panel", required=True, help="path to literal requested panel JSON")
    parser.add_argument("--live-canonical-sha", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.receipt, "r", encoding="utf-8") as fh:
            receipt_text = fh.read()
        with open(args.requested_panel, "r", encoding="utf-8") as fh:
            panel_text = fh.read()
        normalized = validate_text(receipt_text, panel_text, args.live_canonical_sha)
        print(json.dumps(normalized, sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
