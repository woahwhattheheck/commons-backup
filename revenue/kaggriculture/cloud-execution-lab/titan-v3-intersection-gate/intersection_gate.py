# SPDX-License-Identifier: Apache-2.0
"""Fail-closed intersection and paired-margin gate for TITAN game reports.

This adapter consumes the exact JSON report emitted by the existing TITAN V3
paired-game gate.  It intentionally does not alter that historical gate's
schema or verdict.  Instead, a separate immutable contract binds the exact
parent-report bytes and adds checks that cannot be represented by opponent-only
or seat-only marginals:

* opponent × candidate-seat own-cash strata;
* opponent × candidate-seat margin strata; and
* two-seat pair margin distributions.

Exit codes are stable: 0 PROMOTE, 2 INVALID, 3 REJECT.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import statistics
import tempfile
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 64 * 1024 * 1024
HEX = frozenset("0123456789abcdef")

CONTRACT_FIELDS = {
    "schema_version",
    "panel_id",
    "parent_report_sha256",
    "opponents",
    "seeds",
    "seats",
    "expected_cells",
    "policy",
}
POLICY_FIELDS = {
    "require_parent_promote",
    "min_positive_margin_pair_fraction",
    "max_negative_opponent_seat_own_strata",
    "max_negative_opponent_seat_margin_strata",
    "min_worst_pair_margin_delta",
    "min_worst_opponent_seat_own_mean",
    "min_worst_opponent_seat_margin_mean",
}


class GateError(ValueError):
    """Evidence is malformed, incomplete, contradictory, or unbound."""


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON constant is forbidden: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _strict_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError(f"{label}: expected UTF-8 JSON") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except GateError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise GateError(f"{label}: invalid JSON: {exc}") from exc


def _read_regular_once(path: Path, *, label: str) -> tuple[bytes, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GateError(f"{label}: cannot open regular input: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise GateError(f"{label}: input is not a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise GateError(f"{label}: input exceeds {MAX_INPUT_BYTES} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise GateError(f"{label}: input exceeds {MAX_INPUT_BYTES} bytes")
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise GateError(f"{label}: input mutated during acquisition")
        data = b"".join(chunks)
        if len(data) != before.st_size:
            raise GateError(f"{label}: short or expanding read")
        return data, hashlib.sha256(data).hexdigest()
    finally:
        os.close(fd)


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateError(f"{label}: expected a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise GateError(f"{label}: expected a finite number") from exc
    if not math.isfinite(result):
        raise GateError(f"{label}: expected a finite number")
    return result


def _integer(value: Any, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateError(f"{label}: expected an integer")
    if minimum is not None and value < minimum:
        raise GateError(f"{label}: expected an integer >= {minimum}")
    return value


def _exact_keys(value: Any, expected: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{label}: expected an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise GateError(f"{label}: key mismatch; missing={missing}, extra={extra}")
    return value


def _unique_strings(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise GateError(f"{label}: expected a non-empty list")
    out: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise GateError(f"{label}[{index}]: expected a non-empty string")
        if item in seen:
            raise GateError(f"{label}: duplicate value {item!r}")
        seen.add(item)
        out.append(item)
    return out


def _unique_ints(value: Any, *, label: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise GateError(f"{label}: expected a non-empty list")
    out: list[int] = []
    seen: set[int] = set()
    for index, item in enumerate(value):
        parsed = _integer(item, label=f"{label}[{index}]")
        if parsed in seen:
            raise GateError(f"{label}: duplicate value {parsed}")
        seen.add(parsed)
        out.append(parsed)
    return out


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in HEX for char in value)
    ):
        raise GateError(f"{label}: expected 64 lowercase hexadecimal characters")
    return value


def _optional_finite(value: Any, *, label: str) -> float | None:
    return None if value is None else _finite(value, label=label)


def _load_contract(value: Any) -> dict[str, Any]:
    obj = _exact_keys(value, CONTRACT_FIELDS, label="contract")
    version = _integer(obj["schema_version"], label="contract.schema_version")
    if version != SCHEMA_VERSION:
        raise GateError(
            f"contract.schema_version: expected {SCHEMA_VERSION}, got {version}"
        )
    panel_id = obj["panel_id"]
    if not isinstance(panel_id, str) or not panel_id.strip():
        raise GateError("contract.panel_id: expected a non-empty string")
    opponents = _unique_strings(obj["opponents"], label="contract.opponents")
    seeds = _unique_ints(obj["seeds"], label="contract.seeds")
    seats = _unique_ints(obj["seats"], label="contract.seats")
    if seats != [0, 1]:
        raise GateError("contract.seats: expected exactly [0, 1]")
    expected_cells = _integer(
        obj["expected_cells"], label="contract.expected_cells", minimum=1
    )
    computed_cells = len(opponents) * len(seeds) * len(seats)
    if expected_cells != computed_cells:
        raise GateError(
            "contract.expected_cells: expected "
            f"len(opponents) * len(seeds) * 2 = {computed_cells}"
        )

    policy_obj = _exact_keys(obj["policy"], POLICY_FIELDS, label="contract.policy")
    require_parent_promote = policy_obj["require_parent_promote"]
    if require_parent_promote is not True:
        raise GateError(
            "contract.policy.require_parent_promote: expected literal true; "
            "a companion gate may not escalate a non-promoted parent"
        )
    fraction = _finite(
        policy_obj["min_positive_margin_pair_fraction"],
        label="contract.policy.min_positive_margin_pair_fraction",
    )
    if not 0.0 <= fraction <= 1.0:
        raise GateError(
            "contract.policy.min_positive_margin_pair_fraction: expected [0, 1]"
        )
    policy = {
        "require_parent_promote": require_parent_promote,
        "min_positive_margin_pair_fraction": fraction,
        "max_negative_opponent_seat_own_strata": _integer(
            policy_obj["max_negative_opponent_seat_own_strata"],
            label="contract.policy.max_negative_opponent_seat_own_strata",
            minimum=0,
        ),
        "max_negative_opponent_seat_margin_strata": _integer(
            policy_obj["max_negative_opponent_seat_margin_strata"],
            label="contract.policy.max_negative_opponent_seat_margin_strata",
            minimum=0,
        ),
        "min_worst_pair_margin_delta": _optional_finite(
            policy_obj["min_worst_pair_margin_delta"],
            label="contract.policy.min_worst_pair_margin_delta",
        ),
        "min_worst_opponent_seat_own_mean": _optional_finite(
            policy_obj["min_worst_opponent_seat_own_mean"],
            label="contract.policy.min_worst_opponent_seat_own_mean",
        ),
        "min_worst_opponent_seat_margin_mean": _optional_finite(
            policy_obj["min_worst_opponent_seat_margin_mean"],
            label="contract.policy.min_worst_opponent_seat_margin_mean",
        ),
    }
    return {
        "schema_version": version,
        "panel_id": panel_id,
        "parent_report_sha256": _sha256(
            obj["parent_report_sha256"], label="contract.parent_report_sha256"
        ),
        "opponents": opponents,
        "seeds": seeds,
        "seats": seats,
        "expected_cells": expected_cells,
        "policy": policy,
    }


def _result(margin: float) -> str:
    return "W" if margin > 0 else ("T" if margin == 0 else "L")


def _score_pair(value: Any, *, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise GateError(f"{label}: expected exactly two terminal scores")
    return (
        _finite(value[0], label=f"{label}[0]"),
        _finite(value[1], label=f"{label}[1]"),
    )


def _equal_number(actual: Any, expected: float, *, label: str) -> None:
    parsed = _finite(actual, label=label)
    if parsed != expected:
        raise GateError(f"{label}: reported {parsed}, recomputed {expected}")


def _mean(values: Sequence[float], *, label: str) -> float:
    if not values:
        raise GateError(f"{label}: cannot summarize an empty sequence")
    try:
        value = statistics.fmean(values)
    except (OverflowError, ValueError) as exc:
        raise GateError(f"{label}: derived mean is not finite") from exc
    return _finite(value, label=label)


def _summary(values: Sequence[float], *, label: str) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": _mean(values, label=f"{label}.mean"),
        "min": min(values),
        "max": max(values),
        "negative": sum(value < 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "positive": sum(value > 0 for value in values),
    }


def _parent_promote_is_coherent(report: Mapping[str, Any]) -> bool:
    if report.get("verdict") != "PROMOTE":
        return False
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise GateError("parent report: PROMOTE requires a non-empty checks list")
    for index, item in enumerate(checks):
        if not isinstance(item, dict) or item.get("pass") is not True:
            raise GateError(
                f"parent report.checks[{index}]: PROMOTE contains a failed/malformed check"
            )
    return True


def analyze_parent(report: Any, contract: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise GateError("parent report: expected an object")
    verdict = report.get("verdict")
    if verdict not in {"PROMOTE", "REJECT", "INVALID"}:
        raise GateError("parent report.verdict: expected PROMOTE, REJECT, or INVALID")
    if verdict == "INVALID":
        raise GateError(
            "parent report is INVALID; companion evaluation requires complete parent evidence"
        )
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise GateError("parent report.metrics: expected an object")
    raw_cells = metrics.get("cells")
    if not isinstance(raw_cells, list):
        raise GateError("parent report.metrics.cells: expected a list")

    expected_keys = {
        (opponent, seed, seat)
        for opponent in contract["opponents"]
        for seed in contract["seeds"]
        for seat in contract["seats"]
    }
    seen: set[tuple[str, int, int]] = set()
    cells: list[dict[str, Any]] = []
    pair_own: dict[tuple[str, int], dict[int, float]] = defaultdict(dict)
    pair_margin: dict[tuple[str, int], dict[int, float]] = defaultdict(dict)
    intersection_own: dict[tuple[str, int], list[float]] = defaultdict(list)
    intersection_margin: dict[tuple[str, int], list[float]] = defaultdict(list)

    for index, raw in enumerate(raw_cells):
        label = f"parent report.metrics.cells[{index}]"
        if not isinstance(raw, dict):
            raise GateError(f"{label}: expected an object")
        key_value = raw.get("key")
        if not isinstance(key_value, list) or len(key_value) != 3:
            raise GateError(f"{label}.key: expected [opponent, seed, seat]")
        opponent = key_value[0]
        if not isinstance(opponent, str) or not opponent:
            raise GateError(f"{label}.key[0]: expected a non-empty opponent string")
        seed = _integer(key_value[1], label=f"{label}.key[1]")
        seat = _integer(key_value[2], label=f"{label}.key[2]")
        key = (opponent, seed, seat)
        if key in seen:
            raise GateError(f"{label}.key: duplicate cell {list(key)!r}")
        seen.add(key)
        if key not in expected_keys:
            raise GateError(f"{label}.key: unexpected cell {list(key)!r}")

        baseline_scores = _score_pair(raw.get("baseline_scores"), label=f"{label}.baseline_scores")
        candidate_scores = _score_pair(
            raw.get("candidate_scores"), label=f"{label}.candidate_scores"
        )
        base_own = baseline_scores[seat]
        base_rival = baseline_scores[1 - seat]
        cand_own = candidate_scores[seat]
        cand_rival = candidate_scores[1 - seat]
        baseline_margin = _finite(
            base_own - base_rival, label=f"{label}.recomputed_baseline_margin"
        )
        candidate_margin = _finite(
            cand_own - cand_rival, label=f"{label}.recomputed_candidate_margin"
        )
        own_delta = _finite(cand_own - base_own, label=f"{label}.recomputed_own_delta")
        rival_delta = _finite(
            cand_rival - base_rival, label=f"{label}.recomputed_rival_delta"
        )
        margin_delta = _finite(
            candidate_margin - baseline_margin,
            label=f"{label}.recomputed_margin_delta",
        )
        _equal_number(raw.get("own_delta"), own_delta, label=f"{label}.own_delta")
        _equal_number(raw.get("rival_delta"), rival_delta, label=f"{label}.rival_delta")
        _equal_number(raw.get("margin_delta"), margin_delta, label=f"{label}.margin_delta")
        baseline_result = _result(baseline_margin)
        candidate_result = _result(candidate_margin)
        if raw.get("baseline_result") != baseline_result:
            raise GateError(
                f"{label}.baseline_result: reported {raw.get('baseline_result')!r}, "
                f"recomputed {baseline_result!r}"
            )
        if raw.get("candidate_result") != candidate_result:
            raise GateError(
                f"{label}.candidate_result: reported {raw.get('candidate_result')!r}, "
                f"recomputed {candidate_result!r}"
            )

        pair_own[(opponent, seed)][seat] = own_delta
        pair_margin[(opponent, seed)][seat] = margin_delta
        intersection_own[(opponent, seat)].append(own_delta)
        intersection_margin[(opponent, seat)].append(margin_delta)
        cells.append(
            {
                "key": [opponent, seed, seat],
                "own_delta": own_delta,
                "rival_delta": rival_delta,
                "margin_delta": margin_delta,
                "baseline_result": baseline_result,
                "candidate_result": candidate_result,
            }
        )

    missing = expected_keys - seen
    if missing:
        preview = [list(key) for key in sorted(missing)[:8]]
        raise GateError(
            f"parent report.metrics.cells: missing {len(missing)} cells; first={preview}"
        )
    if len(seen) != contract["expected_cells"]:
        raise GateError(
            "parent report.metrics.cells: observed cell count does not match contract"
        )

    pairs: list[dict[str, Any]] = []
    pair_margin_means: list[float] = []
    for key in sorted(pair_own):
        if set(pair_own[key]) != {0, 1} or set(pair_margin[key]) != {0, 1}:
            raise GateError(f"internal pair cardinality error for {list(key)!r}")
        own_by_seat = {str(seat): pair_own[key][seat] for seat in (0, 1)}
        margin_by_seat = {str(seat): pair_margin[key][seat] for seat in (0, 1)}
        own_mean = _mean(list(own_by_seat.values()), label=f"pair {list(key)!r} own_mean")
        margin_mean = _mean(
            list(margin_by_seat.values()), label=f"pair {list(key)!r} margin_mean"
        )
        pair_margin_means.append(margin_mean)
        pairs.append(
            {
                "opponent": key[0],
                "seed": key[1],
                "own_delta_by_seat": own_by_seat,
                "margin_delta_by_seat": margin_by_seat,
                "seat_mean_own_delta": own_mean,
                "seat_mean_margin_delta": margin_mean,
            }
        )

    intersections: list[dict[str, Any]] = []
    own_means: list[float] = []
    margin_means: list[float] = []
    for key in sorted(intersection_own):
        if len(intersection_own[key]) != len(contract["seeds"]):
            raise GateError(f"internal intersection cardinality error for {list(key)!r}")
        own_summary = _summary(
            intersection_own[key], label=f"intersection {list(key)!r} own_delta"
        )
        margin_summary = _summary(
            intersection_margin[key], label=f"intersection {list(key)!r} margin_delta"
        )
        own_means.append(float(own_summary["mean"]))
        margin_means.append(float(margin_summary["mean"]))
        intersections.append(
            {
                "opponent": key[0],
                "candidate_seat": key[1],
                "own_delta": own_summary,
                "margin_delta": margin_summary,
            }
        )

    return {
        "parent_verdict": verdict,
        "parent_promote_coherent": _parent_promote_is_coherent(report)
        if verdict == "PROMOTE"
        else False,
        "cells": sorted(cells, key=lambda item: tuple(item["key"])),
        "pairs": pairs,
        "opponent_seat_strata": intersections,
        "aggregate": {
            "cells": len(cells),
            "pairs": len(pairs),
            "opponent_seat_strata": len(intersections),
            "positive_margin_pair_fraction": (
                sum(value > 0 for value in pair_margin_means) / len(pair_margin_means)
            ),
            "negative_margin_pairs": sum(value < 0 for value in pair_margin_means),
            "worst_pair_margin_delta": min(pair_margin_means),
            "negative_opponent_seat_own_strata": sum(
                value < 0 for value in own_means
            ),
            "negative_opponent_seat_margin_strata": sum(
                value < 0 for value in margin_means
            ),
            "worst_opponent_seat_own_mean": min(own_means),
            "worst_opponent_seat_margin_mean": min(margin_means),
        },
    }


def evaluate_policy(metrics: Mapping[str, Any], policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    aggregate = metrics["aggregate"]
    checks: list[dict[str, Any]] = []

    def check(
        name: str,
        actual: float | int | bool,
        op: str,
        threshold: Any,
        passed: bool,
    ) -> None:
        checks.append(
            {
                "name": name,
                "actual": actual,
                "op": op,
                "threshold": threshold,
                "pass": passed,
            }
        )

    parent_actual = metrics["parent_promote_coherent"]
    check(
        "parent_promote_coherent",
        parent_actual,
        "is true",
        True,
        parent_actual,
    )
    actual_fraction = aggregate["positive_margin_pair_fraction"]
    threshold_fraction = policy["min_positive_margin_pair_fraction"]
    check(
        "positive_margin_pair_fraction",
        actual_fraction,
        ">=",
        threshold_fraction,
        actual_fraction >= threshold_fraction,
    )
    for name in (
        "negative_opponent_seat_own_strata",
        "negative_opponent_seat_margin_strata",
    ):
        threshold = policy[f"max_{name}"]
        actual = aggregate[name]
        check(name, actual, "<=", threshold, actual <= threshold)

    optional_checks = (
        ("worst_pair_margin_delta", "min_worst_pair_margin_delta"),
        (
            "worst_opponent_seat_own_mean",
            "min_worst_opponent_seat_own_mean",
        ),
        (
            "worst_opponent_seat_margin_mean",
            "min_worst_opponent_seat_margin_mean",
        ),
    )
    for actual_name, policy_name in optional_checks:
        threshold = policy[policy_name]
        actual = aggregate[actual_name]
        if threshold is not None:
            check(actual_name, actual, ">=", threshold, actual >= threshold)
    return checks


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise GateError(f"cannot establish input/output path identity: {exc}") from exc


def _reject_output_alias(
    contract_path: Path, parent_report_path: Path, output_path: Path
) -> None:
    for label, input_path in (
        ("contract", contract_path),
        ("parent report", parent_report_path),
    ):
        if _same_existing_file(input_path, output_path):
            raise GateError(
                f"output aliases {label}; refusing to overwrite immutable evidence"
            )


def run_gate(
    contract_path: Path, parent_report_path: Path, output_path: Path
) -> tuple[int, dict[str, Any]]:
    observed: dict[str, Any] = {
        "contract_sha256": None,
        "contract_bytes": None,
        "parent_report_sha256": None,
        "parent_report_bytes": None,
    }
    try:
        _reject_output_alias(contract_path, parent_report_path, output_path)
    except GateError as exc:
        # Deliberately do not write an INVALID report onto an evidence path.
        return 2, {
            "schema_version": SCHEMA_VERSION,
            "verdict": "INVALID",
            "error": str(exc),
            "inputs": observed,
        }

    try:
        contract_bytes, contract_sha = _read_regular_once(
            contract_path, label="contract"
        )
        observed["contract_sha256"] = contract_sha
        observed["contract_bytes"] = len(contract_bytes)
        report_bytes, report_sha = _read_regular_once(
            parent_report_path, label="parent report"
        )
        observed["parent_report_sha256"] = report_sha
        observed["parent_report_bytes"] = len(report_bytes)

        contract = _load_contract(
            _strict_json_bytes(contract_bytes, label="contract")
        )
        if report_sha != contract["parent_report_sha256"]:
            raise GateError(
                "parent report digest mismatch: "
                f"expected {contract['parent_report_sha256']}, observed {report_sha}"
            )
        parent = _strict_json_bytes(report_bytes, label="parent report")
        metrics = analyze_parent(parent, contract)
        checks = evaluate_policy(metrics, contract["policy"])
        verdict = "PROMOTE" if all(item["pass"] for item in checks) else "REJECT"
        code = 0 if verdict == "PROMOTE" else 3
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "verdict": verdict,
            "panel_id": contract["panel_id"],
            "inputs": observed,
            "grid": {
                "opponents": contract["opponents"],
                "seeds": contract["seeds"],
                "seats": contract["seats"],
                "expected_cells": contract["expected_cells"],
            },
            "metrics": metrics,
            "checks": checks,
        }
    except GateError as exc:
        code = 2
        result = {
            "schema_version": SCHEMA_VERSION,
            "verdict": "INVALID",
            "error": str(exc),
            "inputs": observed,
        }
    _atomic_write(output_path, _canonical_bytes(result))
    return code, result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--parent-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    code, result = run_gate(args.contract, args.parent_report, args.output)
    print(result["verdict"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
