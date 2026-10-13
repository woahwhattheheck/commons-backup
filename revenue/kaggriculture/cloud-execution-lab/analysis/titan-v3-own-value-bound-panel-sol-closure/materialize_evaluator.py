# SPDX-License-Identifier: Apache-2.0
"""Materialize the pinned evaluator with candidate-only pre-interpreter evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


EXPECTED_EVALUATOR_BLOB = "077feb2208b6e0c1727835eb4f8089709bf67f3b"

NEEDLES: tuple[tuple[bytes, bytes, str], ...] = (
    (
        b"    actors, trace = [], hashlib.sha256()\n",
        b"    actors, trace, candidate_trace = [], hashlib.sha256(), hashlib.sha256()\n",
        "candidate digest initialization",
    ),
    (
        b"            for seat in range(2):\n"
        b"                state[seat].action = actions[seat]\n",
        b"            candidate_trace.update(encoded({\"step\": step, \"action\": actions[candidate_seat]}))\n"
        b"            for seat in range(2):\n"
        b"                state[seat].action = actions[seat]\n",
        "pre-interpreter candidate action capture",
    ),
    (
        b"        else:\n"
        b"            result[\"trace_sha256\"] = trace.hexdigest()\n"
        b"        if finalization_errors:\n",
        b"        else:\n"
        b"            result[\"trace_sha256\"] = trace.hexdigest()\n"
        b"        result[\"candidate_action_sha256\"] = candidate_trace.hexdigest()\n"
        b"        result[\"candidate_action_count\"] = result[\"steps\"]\n"
        b"        if finalization_errors:\n",
        "candidate digest publication",
    ),
)


class EvaluatorMaterializeError(ValueError):
    """The exact evaluator source or patch contract is invalid."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def materialize_evaluator(
    source: Path,
    output: Path,
    *,
    expected_blob: str = EXPECTED_EVALUATOR_BLOB,
) -> dict[str, Any]:
    source = source.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise EvaluatorMaterializeError(f"output already exists: {output}")
    original = source.read_bytes()
    actual_blob = git_blob_sha1(original)
    if actual_blob != expected_blob:
        raise EvaluatorMaterializeError(
            f"evaluator blob mismatch: expected {expected_blob}, got {actual_blob}"
        )

    patched = original
    patch_receipts: list[dict[str, Any]] = []
    for old, new, label in NEEDLES:
        before_count = patched.count(old)
        new_before = patched.count(new)
        if before_count != 1 or new_before != 0:
            raise EvaluatorMaterializeError(
                f"{label} cardinality mismatch: old={before_count}, new={new_before}"
            )
        patched = patched.replace(old, new, 1)

        old_after_raw = patched.count(old)
        old_embedded_in_replacement = new.count(old)
        old_after_unconsumed = old_after_raw - old_embedded_in_replacement
        if old_after_unconsumed != 0:
            raise EvaluatorMaterializeError(
                f"{label} left {old_after_unconsumed} unconsumed old patch sites"
            )

        patch_receipts.append(
            {
                "label": label,
                "old_sha256": sha256(old),
                "new_sha256": sha256(new),
                "old_occurrences_before": before_count,
                "old_occurrences_after": old_after_unconsumed,
                "old_occurrences_after_raw": old_after_raw,
                "old_occurrences_embedded_in_replacement": (
                    old_embedded_in_replacement
                ),
                "new_occurrences_after": patched.count(new),
            }
        )

    if patched == original:
        raise EvaluatorMaterializeError("evaluator patch changed no bytes")
    try:
        compile(patched.decode("utf-8"), str(output), "exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise EvaluatorMaterializeError(
            f"patched evaluator does not compile: {exc}"
        ) from exc

    atomic_write(output, patched)
    if source.read_bytes() != original:
        raise EvaluatorMaterializeError("source evaluator changed during patching")

    return {
        "schema_version": 1,
        "operation": "titan-v3-own-value-bound-gameplay-screen-20260910-01",
        "repair": "sol-candidate-action-evidence-v1",
        "source": {
            "path_name": source.name,
            "git_blob_sha1": actual_blob,
            "sha256": sha256(original),
            "bytes": len(original),
        },
        "patched": {
            "path_name": output.name,
            "git_blob_sha1": git_blob_sha1(patched),
            "sha256": sha256(patched),
            "bytes": len(patched),
            "patches": patch_receipts,
            "candidate_action_field": "candidate_action_sha256",
            "candidate_action_count_field": "candidate_action_count",
            "capture_phase": "after both returned actions, before interpreter",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    receipt = materialize_evaluator(args.source, args.output)
    atomic_write(
        args.receipt,
        (
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8"),
    )
    print(
        json.dumps(
            {
                "source_blob": receipt["source"]["git_blob_sha1"],
                "patched_blob": receipt["patched"]["git_blob_sha1"],
                "patched_sha256": receipt["patched"]["sha256"],
                "capture_phase": receipt["patched"]["capture_phase"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
