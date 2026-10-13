# SPDX-License-Identifier: Apache-2.0
"""Run paired exact-engine P01 development cells and preserve raw evidence."""
from __future__ import annotations

import importlib.util
import json
import math
import os
import re
from pathlib import Path
import statistics
import sys
import time

ROOT = Path("/tmp/p01-runtime")
TRACE_DIR = Path(os.environ.get("P01_TRACE_DIR", "/tmp/p01-traces"))
MODE = os.environ.get("P01_MODE", "annual").strip().lower()
CANDIDATE_HEAD = os.environ.get("P01_CANDIDATE_HEAD", "").strip()
if re.fullmatch(r"[0-9a-f]{40}", CANDIDATE_HEAD) is None:
    raise ValueError("P01_CANDIDATE_HEAD must be the immutable lowercase event-head SHA")
DISPATCH = "50fc3978603da7a2f155168a0296877007b895ea"
ARCHIVE_SHA256 = "a055fd56ca5821208096f37787f77dbdddc2f65c14c24132d6e219a05e6f02ba"
SOURCE_SHA256 = "b96676977687ee8a92d7213380f96bf5774a5ec26925cb4f0d66bdd244eb44ba"
DEFAULT_SEEDS = tuple(range(2909010001, 2909010009))
HEX64 = re.compile(r"^[0-9a-f]{64}$")

EVALUATOR = ROOT / "checks/reference/evaluator/evaluate.py"
ENGINE = ROOT / "checks/reference/engine"
LOADER = ROOT / "checks/reference/evaluator/loader.py"
CONTROL = str(ROOT / "main.py") + "::agent"
CANDIDATE = str(ROOT / "p01_agent.py") + "::agent"
OPPONENT = str(ROOT / "reference/next-panel/vendor/arlene.py") + "::agent"


def _seeds() -> tuple[int, ...]:
    raw = os.environ.get("P01_SEEDS", "").strip()
    if not raw:
        return DEFAULT_SEEDS
    values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not values or len(values) > 64 or len(set(values)) != len(values):
        raise ValueError("P01_SEEDS must contain 1..64 distinct integers")
    return values


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("p01_host_eval", EVALUATOR)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load evaluator from {EVALUATOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _outcome(own: float, rival: float) -> str:
    return "W" if own > rival else "L" if own < rival else "T"


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _finite_number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("score is not a finite number")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError("score is not finite")
    return out


def _validate_complete_row(row: dict, *, expected_label: str, seed: int, seat: int) -> None:
    """Fail-closed completion gate before any aggregate."""
    if row.get("label") != expected_label:
        raise ValueError(f"label mismatch: {row.get('label')!r} != {expected_label!r}")
    if row.get("seed") != seed or row.get("candidate_seat") != seat:
        raise ValueError("seed/seat identity mismatch")
    if row.get("status") != "complete":
        raise ValueError(f"status is not complete: {row.get('status')!r}")
    if row.get("failure") is not None:
        raise ValueError(f"failure is not None: {row.get('failure')!r}")
    scores = row.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        raise ValueError("scores must be a two-element list")
    for item in scores:
        _finite_number(item)
    steps = row.get("steps")
    episode_steps = row.get("episode_steps")
    if steps is not None and episode_steps is not None:
        if not isinstance(steps, int) or isinstance(steps, bool):
            raise ValueError("steps must be int")
        if not isinstance(episode_steps, int) or isinstance(episode_steps, bool):
            raise ValueError("episode_steps must be int")
        if steps != episode_steps - 1:
            raise ValueError(f"terminal steps {steps} != episode_steps-1 {episode_steps - 1}")
    digest = row.get("trace_sha256")
    if digest is not None:
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise ValueError(f"trace_sha256 is not a valid 64-hex digest: {digest!r}")


def _set_cell_env(seed: int, seat: int, label: str) -> None:
    os.environ["P01_CELL_SEED"] = str(seed)
    os.environ["P01_CELL_SEAT"] = str(seat)
    os.environ["P01_CELL_LABEL"] = label


def _clear_cell_env() -> None:
    for key in ("P01_CELL_SEED", "P01_CELL_SEAT", "P01_CELL_LABEL"):
        os.environ.pop(key, None)


def _read_traces_for_cell(seed: int, seat: int, label: str) -> list[dict]:
    rows: list[dict] = []
    pattern = f"p01-{MODE}-s{seed}-seat{seat}-{label}-*.jsonl"
    for path in sorted(TRACE_DIR.glob(pattern)):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["trace_file"] = path.name
            row["trace_line"] = number
            rows.append(row)
    rows.sort(key=lambda row: (int(row.get("step", 10**9)), row["trace_file"], row["trace_line"]))
    return rows


def _read_all_traces() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(TRACE_DIR.glob(f"p01-{MODE}-*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["trace_file"] = path.name
            row["trace_line"] = number
            rows.append(row)
    rows.sort(key=lambda row: (int(row.get("step", 10**9)), row["trace_file"], row["trace_line"]))
    return rows


def main() -> None:
    seeds = _seeds()
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = _load_evaluator()
    engine, _ = evaluator.get_engine(ENGINE, LOADER)
    started = time.time()
    games: list[dict] = []
    paired: list[dict] = []
    for seed in seeds:
        for seat in (0, 1):
            cell: dict = {}
            cell_traces: dict[str, list[dict]] = {}
            for label, entrypoint in (("control", CONTROL), (MODE, CANDIDATE)):
                _set_cell_env(seed, seat, label)
                try:
                    agents = [entrypoint, OPPONENT] if seat == 0 else [OPPONENT, entrypoint]
                    result = evaluator.play(
                        engine, agents, ENGINE, LOADER, seed, seat, 20260909,
                        1.0, 10.0, 120.0, None,
                    )
                finally:
                    _clear_cell_env()
                row = {"label": label, "seed": seed, "candidate_seat": seat, **result}
                try:
                    _validate_complete_row(row, expected_label=label, seed=seed, seat=seat)
                    row["_validated"] = True
                except ValueError as err:
                    row["_validated"] = False
                    row["_validation_error"] = str(err)
                games.append(row)
                cell[label] = row
                # Collect candidate traces immediately under the unique cell path.
                cell_traces[label] = _read_traces_for_cell(seed, seat, label)
                print(json.dumps({
                    "mode": MODE, "label": label, "seed": seed, "seat": seat,
                    "status": result.get("status"), "scores": result.get("scores"),
                    "validated": row["_validated"],
                }, sort_keys=True, allow_nan=False), flush=True)

            control = cell["control"]
            candidate = cell[MODE]
            pair: dict = {
                "seed": seed,
                "candidate_seat": seat,
                "control_status": control.get("status"),
                "candidate_status": candidate.get("status"),
                "control_validated": bool(control.get("_validated")),
                "candidate_validated": bool(candidate.get("_validated")),
            }
            both_ok = (
                control.get("_validated") is True
                and candidate.get("_validated") is True
            )
            if both_ok:
                c_own = _finite_number(control["scores"][seat])
                c_rival = _finite_number(control["scores"][1 - seat])
                p_own = _finite_number(candidate["scores"][seat])
                p_rival = _finite_number(candidate["scores"][1 - seat])
                control_digest = control.get("trace_sha256")
                candidate_digest = candidate.get("trace_sha256")
                trace_identical = (
                    isinstance(control_digest, str)
                    and isinstance(candidate_digest, str)
                    and control_digest == candidate_digest
                )
                activations = [
                    t for t in cell_traces.get(MODE, [])
                    if bool(t.get("report", {}).get("changed"))
                ]
                pair.update(
                    complete=True,
                    control_own=c_own,
                    control_rival=c_rival,
                    candidate_own=p_own,
                    candidate_rival=p_rival,
                    control_outcome=_outcome(c_own, c_rival),
                    candidate_outcome=_outcome(p_own, p_rival),
                    own_cash_delta=p_own - c_own,
                    rival_cash_delta=p_rival - c_rival,
                    margin_delta=(p_own - p_rival) - (c_own - c_rival),
                    control_trace_sha256=control_digest,
                    candidate_trace_sha256=candidate_digest,
                    trace_identical=trace_identical,
                    activation_count=len(activations),
                    activations=activations[:3],  # bounded evidence sample
                    cell_trace_files=sorted({
                        t.get("trace_file") for t in cell_traces.get(MODE, []) if t.get("trace_file")
                    }),
                )
                # Activation requires corresponding trace divergence when digests exist.
                if activations and control_digest is not None and candidate_digest is not None:
                    if control_digest == candidate_digest:
                        pair["activation_trace_bound"] = False
                        pair["activation_bind_error"] = (
                            "claimed activation but control/candidate trace_sha256 identical"
                        )
                    else:
                        pair["activation_trace_bound"] = True
                elif activations:
                    # Digests unavailable: still bind via action hashes in the emission.
                    pair["activation_trace_bound"] = all(
                        t.get("before_action_sha256") != t.get("after_action_sha256")
                        for t in activations
                    )
                else:
                    pair["activation_trace_bound"] = True  # no claim to bind
            else:
                pair["complete"] = False
                pair["control_validation_error"] = control.get("_validation_error")
                pair["candidate_validation_error"] = candidate.get("_validation_error")
            paired.append(pair)

    traces = _read_all_traces()
    activations = [row for row in traces if bool(row.get("report", {}).get("changed"))]
    reason_counts: dict[str, int] = {}
    for row in traces:
        reason = str(row.get("report", {}).get("reason", "missing_reason"))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    complete = [row for row in paired if row.get("complete")]
    changed_cells = [row for row in complete if int(row.get("activation_count", 0)) > 0]
    unchanged_cells = [row for row in complete if int(row.get("activation_count", 0)) == 0]
    own_deltas = [float(row["own_cash_delta"]) for row in complete]
    margin_deltas = [float(row["margin_delta"]) for row in complete]
    changed_own = [float(row["own_cash_delta"]) for row in changed_cells]
    changed_margin = [float(row["margin_delta"]) for row in changed_cells]
    control_wtl = {key: sum(row["control_outcome"] == key for row in complete) for key in "WTL"}
    candidate_wtl = {key: sum(row["candidate_outcome"] == key for row in complete) for key in "WTL"}
    changed_wtl = {key: sum(row["candidate_outcome"] == key for row in changed_cells) for key in "WTL"}
    regressive_flips = sum(
        row["control_outcome"] in ("W", "T") and row["candidate_outcome"] == "L"
        for row in complete
    )
    positive_flips = sum(
        row["control_outcome"] in ("L", "T") and row["candidate_outcome"] == "W"
        for row in complete
    )
    unbound_activations = sum(
        1 for row in complete
        if int(row.get("activation_count", 0)) > 0 and not row.get("activation_trace_bound", False)
    )
    unchanged_not_identical = sum(
        1 for row in unchanged_cells
        if row.get("control_trace_sha256") is not None
        and row.get("candidate_trace_sha256") is not None
        and not row.get("trace_identical", False)
    )
    summary = {
        "scheduled_pairs": len(paired),
        "complete_pairs": len(complete),
        "failed_pairs": len(paired) - len(complete),
        "control_wtl": control_wtl,
        "candidate_wtl": candidate_wtl,
        "changed_cell_count": len(changed_cells),
        "unchanged_cell_count": len(unchanged_cells),
        "changed_cell_wtl": changed_wtl,
        "mean_own_cash_delta": _mean(own_deltas),
        "mean_margin_delta": _mean(margin_deltas),
        "changed_cell_mean_own_cash_delta": _mean(changed_own),
        "changed_cell_mean_margin_delta": _mean(changed_margin),
        "worst_own_cash_delta": min(own_deltas) if own_deltas else None,
        "best_own_cash_delta": max(own_deltas) if own_deltas else None,
        "nonzero_own_delta_pairs": sum(delta != 0 for delta in own_deltas),
        "regressive_flips": regressive_flips,
        "positive_flips": positive_flips,
        "frontier_rows": len(traces),
        "frontier_reason_counts": dict(sorted(reason_counts.items())),
        "activation_rows": len(activations),
        "activation_processes": len({row.get("trace_file") for row in activations}),
        "unbound_activation_cells": unbound_activations,
        "unchanged_cells_not_trace_identical": unchanged_not_identical,
        "first_frontier": traces[0] if traces else None,
        "first_activation": activations[0] if activations else None,
    }
    # Causal development signal: every activation bound, unchanged cells identical
    # when digests exist, and positive aggregate only after binding.
    summary["development_signal"] = bool(
        len(complete) == len(paired)
        and activations
        and unbound_activations == 0
        and unchanged_not_identical == 0
        and positive_flips >= regressive_flips
        and summary["mean_own_cash_delta"] > 0
        and summary["mean_margin_delta"] >= 0
        and (not changed_cells or summary["changed_cell_mean_own_cash_delta"] is not None)
    )
    payload = {
        "schema": 2,
        "operation": "op:titan-v25-orders-20260909-P01-sol-forge-01",
        "mode": MODE,
        "candidate_head": CANDIDATE_HEAD,
        "dispatch": DISPATCH,
        "archive_sha256": ARCHIVE_SHA256,
        "source_manifest_sha256": SOURCE_SHA256,
        "engine": "kaggle-environments==1.32.7 / commit 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
        "opponent": "intact Arlene from exact archive",
        "seeds": list(seeds),
        "both_seats": True,
        "summary": summary,
        "paired": paired,
        "games": games,
        "traces": traces,
        "wall_seconds": time.time() - started,
        "scope": "development screen only; no canonical enablement or Kaggle submission",
    }
    output = Path(f"/tmp/P01-{MODE}-SCREEN.json")
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"mode": MODE, **summary}, sort_keys=True, allow_nan=False), flush=True)
    if len(complete) != len(paired):
        raise SystemExit("incomplete P01 paired screen")
    if unbound_activations:
        raise SystemExit("unbound activation cells present")


if __name__ == "__main__":
    main()
