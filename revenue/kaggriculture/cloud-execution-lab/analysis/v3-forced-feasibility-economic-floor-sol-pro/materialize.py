# SPDX-License-Identifier: Apache-2.0
"""Materialize the current TITAN forced-feasibility economic-floor repair.

The current scheduler lets physical infeasibility waive its modeled value floor:
a feasible replacement can be selected even when every scenario loses own cash
and relative value.  The caller then ranks the Boolean ``forced_feasibility``
flag before economic gain.

This source-bound carrier makes three narrow changes in a temporary scheduler:

* physical feasibility alone never admits a negative own/relative candidate;
* diagnostics distinguish a physical candidate from an economically admissible
  candidate; and
* cross-product selection ranks modeled gain first, using ``forced`` only as a
  tie-break annotation.

The canonical source, archive, config, and pointers are never mutated here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Sequence

OPERATION = "titan-v3-forced-feasibility-economic-floor-20260910-sol-pro-01"
EXPECTED_SOURCE_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"

INITIAL_STATE_OLD = """\
    found_feasible=reference_feasible
    candidates={tuple(reference)}
"""
INITIAL_STATE_NEW = """\
    found_feasible=reference_feasible
    physical_feasible_found=reference_feasible
    economic_floor_rejections=0
    candidates={tuple(reference)}
"""

INFEASIBLE_BRANCH_OLD = """\
        else:
            if capacity_ok and not capacity_ok(plan):continue
            scores=[model.score(plan,quantity,r,a,end==last) for _,r,a in scenarios]
"""
INFEASIBLE_BRANCH_NEW = """\
        else:
            if capacity_ok and not capacity_ok(plan):continue
            physical_feasible_found=True
            scores=[model.score(plan,quantity,r,a,end==last) for _,r,a in scenarios]
"""

ADMISSION_OLD = """\
        # Require improvement in every explicit scenario; ties preserve reference.
        if (key[0]>0 or not reference_feasible) and key>best_key:
            best_key,best_plan,best_scores=key,plan,scores
            found_feasible=True
"""
ADMISSION_NEW = """\
        own_deltas=[s[1]-b[1] for s,b in zip(scores,baseline)]
        worst_own_gain=round(min(own_deltas),8)
        # Physical infeasibility cannot waive modeled own or relative value.
        # A value-neutral feasible repair may survive, but a negative one stays
        # diagnostic-only until an exact avoided-loss certificate exists.
        economic_floor=(key[0]>0 if reference_feasible
                        else key[0]>=0 and worst_own_gain>=0)
        if economic_floor and key>best_key:
            best_key,best_plan,best_scores=key,plan,scores
            found_feasible=True
        elif not reference_feasible and not economic_floor:
            economic_floor_rejections+=1
"""

INFO_OLD = """\
        'worst_relative_gain':best_key[0] if found_feasible else 0.0,'forced_feasibility':not reference_feasible and found_feasible,
        'feasible':found_feasible,'plans_evaluated':len(candidates)}
"""
INFO_NEW = """\
        'worst_relative_gain':best_key[0] if found_feasible else 0.0,
        'worst_own_gain':(round(min(s[1]-b[1] for s,b in zip(best_scores,baseline)),8)
                          if found_feasible else 0.0),
        'reference_feasible':reference_feasible,
        'physical_feasible_found':physical_feasible_found,
        'economic_floor_rejections':economic_floor_rejections,
        'forced_feasibility':not reference_feasible and found_feasible,
        'feasible':found_feasible,'plans_evaluated':len(candidates)}
"""

CALLER_OLD = """\
            eligible=info['worst_relative_gain']>0 or info.get('forced_feasibility',False)
            rank=(info.get('forced_feasibility',False),info['worst_relative_gain'])
            if eligible and (best is None or rank>(best[2].get('forced_feasibility',False),best[2]['worst_relative_gain'])):best=(item,plan,info)
"""
CALLER_NEW = """\
            gain=info['worst_relative_gain']
            forced=bool(info.get('forced_feasibility',False))
            own_floor=info.get('worst_own_gain',0.0)
            eligible=((forced and gain>=0 and own_floor>=0)
                      or (not forced and gain>0))
            rank=(gain,forced)
            prior=(-float('inf'),False) if best is None else (
                best[2]['worst_relative_gain'],
                bool(best[2].get('forced_feasibility',False)),
            )
            if eligible and rank>prior:best=(item,plan,info)
"""

REPLACEMENTS = (
    ("optimizer diagnostic state", INITIAL_STATE_OLD, INITIAL_STATE_NEW),
    ("infeasible physical-candidate census", INFEASIBLE_BRANCH_OLD, INFEASIBLE_BRANCH_NEW),
    ("own-and-relative economic admission floor", ADMISSION_OLD, ADMISSION_NEW),
    ("diagnostic receipt fields", INFO_OLD, INFO_NEW),
    ("gain-first cross-product ranking", CALLER_OLD, CALLER_NEW),
)


class MaterializeError(ValueError):
    """The source identity or exact replacement contract is invalid."""


def git_blob_sha1(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lexists(path: Path) -> bool:
    """Return true for every existing operand, including dangling symlinks."""
    return os.path.lexists(os.fspath(path))


def _resolved(path: Path, *, strict: bool, label: str) -> Path:
    try:
        return Path(path).expanduser().resolve(strict=strict)
    except (OSError, RuntimeError) as exc:
        raise MaterializeError(f"cannot resolve {label}: {path}: {exc}") from exc


def _destination(path: Path, *, label: str) -> Path:
    """Resolve a new destination and reject pre-existing path or symlink aliases."""
    raw = Path(path).expanduser()
    if _lexists(raw):
        raise MaterializeError(f"{label} already exists: {raw}")
    resolved = _resolved(raw, strict=False, label=label)
    if _lexists(resolved):
        raise MaterializeError(f"{label} resolves to an existing path: {resolved}")
    return resolved


def resolve_cli_operands(
    source: Path,
    output: Path,
    receipt: Path,
) -> tuple[Path, Path, Path]:
    """Resolve all CLI operands before writes and reject canonical aliases."""
    resolved_source = _resolved(source, strict=True, label="source")
    resolved_output = _destination(output, label="output")
    resolved_receipt = _destination(receipt, label="receipt")
    operands = {
        "source": resolved_source,
        "output": resolved_output,
        "receipt": resolved_receipt,
    }
    seen: dict[str, str] = {}
    for label, path in operands.items():
        key = os.path.normcase(os.fspath(path))
        prior = seen.get(key)
        if prior is not None:
            raise MaterializeError(f"{label} aliases {prior}: {path}")
        seen[key] = label
    return resolved_source, resolved_output, resolved_receipt


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _apply_exact(
    text: str, replacements: Iterable[tuple[str, str, str]]
) -> tuple[str, list[dict[str, Any]]]:
    receipts: list[dict[str, Any]] = []
    patched = text
    for label, old, new in replacements:
        old_before = patched.count(old)
        new_before = patched.count(new)
        if old_before != 1 or new_before != 0:
            raise MaterializeError(
                f"{label} cardinality mismatch: old={old_before}, new={new_before}"
            )
        patched = patched.replace(old, new, 1)
        receipts.append(
            {
                "label": label,
                "old_sha256": sha256(old.encode("utf-8")),
                "new_sha256": sha256(new.encode("utf-8")),
                "old_occurrences_before": old_before,
                "old_occurrences_after": patched.count(old),
                "new_occurrences_before": new_before,
                "new_occurrences_after": patched.count(new),
            }
        )
    return patched, receipts


def materialize(
    source: Path,
    output: Path,
    *,
    expected_source_blob: str = EXPECTED_SOURCE_BLOB,
) -> dict[str, Any]:
    source = _resolved(source, strict=True, label="source")
    output = _destination(output, label="output")
    if source == output:
        raise MaterializeError("refusing to overwrite the source scheduler")
    before = source.read_bytes()
    actual_blob = git_blob_sha1(before)
    if actual_blob != expected_source_blob:
        raise MaterializeError(
            f"scheduler blob mismatch: expected {expected_source_blob}, got {actual_blob}"
        )
    try:
        text = before.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MaterializeError("scheduler is not UTF-8") from exc
    patched_text, replacements = _apply_exact(text, REPLACEMENTS)
    if patched_text == text:
        raise MaterializeError("repair changed no source bytes")
    try:
        compile(patched_text, str(output), "exec")
    except SyntaxError as exc:
        raise MaterializeError(f"patched scheduler does not compile: {exc}") from exc
    patched = patched_text.encode("utf-8")
    _atomic_write(output, patched)
    if source.read_bytes() != before:
        raise MaterializeError("source scheduler changed during materialization")
    if output.read_bytes() != patched:
        raise MaterializeError("materialized scheduler readback mismatch")
    return {
        "schema_version": 1,
        "operation": OPERATION,
        "source": {
            "path_name": source.name,
            "git_blob_sha1": actual_blob,
            "sha256": sha256(before),
            "bytes": len(before),
        },
        "repair": {
            "kind": "forced_feasibility_economic_floor",
            "changed_files": ["scheduler.py"],
            "git_blob_sha1": git_blob_sha1(patched),
            "sha256": sha256(patched),
            "bytes": len(patched),
            "replacements": replacements,
            "properties": {
                "negative_forced_plan_ineligible": True,
                "forced_zero_cannot_outrank_positive_gain": True,
                "own_floor_required_for_forced_plan": True,
                "physical_candidate_census_separate": True,
                "canonical_state_mutated": False,
            },
        },
    }


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    destination = _destination(path, label="receipt")
    data = (
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    _atomic_write(destination, data)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    source, output, receipt_path = resolve_cli_operands(
        args.source,
        args.output,
        args.receipt,
    )
    receipt = materialize(source, output)
    write_receipt(receipt_path, receipt)
    print(
        json.dumps(
            {
                "operation": OPERATION,
                "source_blob": receipt["source"]["git_blob_sha1"],
                "repair_blob": receipt["repair"]["git_blob_sha1"],
                "replacement_count": len(receipt["repair"]["replacements"]),
                "repair_sha256": receipt["repair"]["sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
