# SPDX-License-Identifier: Apache-2.0
"""Materialize the pinned tournament evaluator with action/evidence capture.

The patch is exact-cardinality and fail-closed. It does not change actions
passed to the official interpreter. For each tested actor it records the
SHA-256 of every returned action immediately before interpretation, a rolling
ordered action digest, and an optional bounded module evidence hook.
"""
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
        b'''            except TypeError:
                inspect.signature(function).bind({})
                takes_config = False
            send({"kind": "ready", **usage()})
''',
        b'''            except TypeError:
                inspect.signature(function).bind({})
                takes_config = False
            module = sys.modules.get(getattr(function, "__module__", ""))
            evidence_hook = getattr(module, "route_reference_echo_evidence", None)
            if evidence_hook is not None and not callable(evidence_hook):
                raise TypeError("route_reference_echo_evidence must be callable")
            send({"kind": "ready", **usage()})
''',
        "worker evidence-hook binding",
    ),
    (
        b'''                action = function(obs, cfg) if takes_config else function(obs)
                seconds, cpu_seconds = time.perf_counter() - start, time.process_time() - cpu
''',
        b'''                action = function(obs, cfg) if takes_config else function(obs)
                agent_evidence = evidence_hook() if evidence_hook is not None else None
                seconds, cpu_seconds = time.perf_counter() - start, time.process_time() - cpu
''',
        "post-action evidence-hook call",
    ),
    (
        b'''                send({"kind": "action", "action": action, "call_seconds": seconds,
                      "call_cpu_seconds": cpu_seconds, **usage()})
''',
        b'''                send({"kind": "action", "action": action, "agent_evidence": agent_evidence,
                      "call_seconds": seconds, "call_cpu_seconds": cpu_seconds, **usage()})
''',
        "worker evidence publication",
    ),
    (
        b'''    actors, trace = [], hashlib.sha256()
''',
        b'''    actors, trace, candidate_trace = [], hashlib.sha256(), hashlib.sha256()
    candidate_action_steps, candidate_evidence = [], []
''',
        "candidate evidence accumulators",
    ),
    (
        b'''        for step in range(cfg.episodeSteps):
            actions = []
''',
        b'''        for step in range(cfg.episodeSteps):
            actions, responses = [], []
''',
        "retain actor responses",
    ),
    (
        b'''                actions.append(response["action"])
            for seat in range(2):
''',
        b'''                responses.append(response)
                actions.append(response["action"])
            candidate_action = actions[candidate_seat]
            candidate_payload = encoded(candidate_action)
            candidate_trace.update(encoded({"step": step, "action": candidate_action}))
            candidate_action_steps.append(hashlib.sha256(candidate_payload).hexdigest())
            evidence = responses[candidate_seat].get("agent_evidence")
            if evidence is not None:
                candidate_evidence.append({"step": step, "evidence": evidence})
            for seat in range(2):
''',
        "pre-interpreter ordered action/evidence capture",
    ),
    (
        b'''        else:
            result["trace_sha256"] = trace.hexdigest()
        if finalization_errors:
''',
        b'''        else:
            result["trace_sha256"] = trace.hexdigest()
        result["candidate_action_sha256"] = candidate_trace.hexdigest()
        result["candidate_action_count"] = len(candidate_action_steps)
        result["candidate_action_step_sha256"] = candidate_action_steps
        result["candidate_agent_evidence"] = candidate_evidence
        if finalization_errors:
''',
        "action/evidence publication",
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
    receipts: list[dict[str, Any]] = []
    for old, new, label in NEEDLES:
        old_before = patched.count(old)
        new_before = patched.count(new)
        if old_before != 1 or new_before != 0:
            raise EvaluatorMaterializeError(
                f"{label} cardinality mismatch: old={old_before}, new={new_before}"
            )
        patched = patched.replace(old, new, 1)
        embedded = new.count(old)
        old_after_raw = patched.count(old)
        if old_after_raw - embedded != 0:
            raise EvaluatorMaterializeError(
                f"{label} left an unconsumed patch site"
            )
        receipts.append(
            {
                "label": label,
                "old_sha256": sha256(old),
                "new_sha256": sha256(new),
                "old_occurrences_before": old_before,
                "old_occurrences_after_unconsumed": old_after_raw - embedded,
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
        "operation": "titan-v3-route-reference-echo-current-activation-20260910-01",
        "repair": "candidate-ordered-action-and-module-evidence-v1",
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
            "patches": receipts,
            "action_digest_field": "candidate_action_sha256",
            "action_step_field": "candidate_action_step_sha256",
            "evidence_field": "candidate_agent_evidence",
            "capture_phase": "after actor return, before official interpreter",
            "action_mutation": False,
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
                "capture_phase": receipt["patched"]["capture_phase"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
