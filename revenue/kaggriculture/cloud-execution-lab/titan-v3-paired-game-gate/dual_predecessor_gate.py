#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Atomic fail-closed promotion gate against two distinct predecessors.

The existing paired-game gate proves one candidate/baseline comparison. This
wrapper snapshots both comparison bundles, strict run-custody receipts, the
actual artifact bundles, and one shared candidate panel before running either
gate. It then rejects identity, grid, policy, panel, artifact, receipt, or
cache-binding drift.

Exit 0 = PROMOTE against both predecessors.
Exit 2 = INVALID evidence or cross-comparison binding.
Exit 3 = valid evidence, but at least one predecessor comparison was REJECTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

import gate as single_gate
from gate_common import (
    GateError,
    MAX_JSONL_BYTES,
    MAX_JSON_BYTES,
    SCHEMA_VERSION,
    atomic_write_json,
    is_int,
    read_json,
    sha256_file,
    snapshot_regular_file,
)

_SLOTS = ("predecessor_a", "predecessor_b")
_RECEIPT_TYPE = "titan-paired-run-custody/v1"
_SHARED_PROVENANCE = (
    "engine_commit",
    "engine_sha256",
    "runner_commit",
    "runner_sha256",
    "candidate_artifact_sha256",
)
_PROVENANCE_FIELDS = (
    "engine_commit",
    "engine_sha256",
    "runner_commit",
    "runner_sha256",
    "baseline_artifact_sha256",
    "candidate_artifact_sha256",
)
_RECEIPT_SHA_FIELDS = (
    "contract",
    "evidence",
    "engine_artifact",
    "runner_artifact",
    "baseline_artifact",
    "candidate_artifact",
    "baseline_games",
    "candidate_games",
)


def _strict_keys(
    value: Any,
    expected: set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{label}: expected an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise GateError(
            f"{label}: keys mismatch; missing={missing}, extra={extra}"
        )
    return value


def _hex_value(
    value: Any,
    *,
    lengths: tuple[int, ...],
    label: str,
) -> str:
    if not isinstance(value, str) or len(value) not in lengths:
        choices = " or ".join(str(length) for length in lengths)
        raise GateError(f"{label}: expected {choices} hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise GateError(f"{label}: expected hexadecimal characters") from exc
    return value.lower()


def _normalized_provenance(
    value: Any,
    *,
    label: str,
) -> dict[str, str]:
    obj = _strict_keys(value, set(_PROVENANCE_FIELDS), label=label)
    return {
        "engine_commit": _hex_value(
            obj["engine_commit"],
            lengths=(40, 64),
            label=f"{label}.engine_commit",
        ),
        "engine_sha256": _hex_value(
            obj["engine_sha256"],
            lengths=(64,),
            label=f"{label}.engine_sha256",
        ),
        "runner_commit": _hex_value(
            obj["runner_commit"],
            lengths=(40, 64),
            label=f"{label}.runner_commit",
        ),
        "runner_sha256": _hex_value(
            obj["runner_sha256"],
            lengths=(64,),
            label=f"{label}.runner_sha256",
        ),
        "baseline_artifact_sha256": _hex_value(
            obj["baseline_artifact_sha256"],
            lengths=(64,),
            label=f"{label}.baseline_artifact_sha256",
        ),
        "candidate_artifact_sha256": _hex_value(
            obj["candidate_artifact_sha256"],
            lengths=(64,),
            label=f"{label}.candidate_artifact_sha256",
        ),
    }


def _normalized_grid(report: Mapping[str, Any]) -> dict[str, Any]:
    grid = report["grid"]
    return {
        "seeds": sorted(grid["seeds"]),
        "opponents": sorted(grid["opponents"]),
        "seats": sorted(grid["seats"]),
        "expected_cells": grid["expected_cells"],
    }


def _baseline_semantic_sha256(report: Mapping[str, Any]) -> str:
    normalized = [
        {
            "key": cell["key"],
            "scores": [
                0.0 if score == 0.0 else score
                for score in cell["baseline_scores"]
            ],
        }
        for cell in report["metrics"]["cells"]
    ]
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bind_inner_inputs(
    *,
    report: Mapping[str, Any],
    outer_hashes: Mapping[str, str],
    slot: str,
) -> None:
    expected = {
        "contract": outer_hashes[f"{slot}_contract"],
        "evidence": outer_hashes[f"{slot}_evidence"],
        "baseline_games": outer_hashes[f"{slot}_games"],
        "candidate_games": outer_hashes["candidate_games"],
    }
    observed = report.get("input_sha256")
    if observed != expected:
        raise GateError(
            f"{slot}: single-gate input binding drift; "
            f"expected={json.dumps(expected, sort_keys=True)}, "
            f"observed={json.dumps(observed, sort_keys=True)}"
        )


def _validate_custody_receipt(
    *,
    receipt_path: Path,
    report: Mapping[str, Any],
    outer_hashes: Mapping[str, str],
    slot: str,
) -> dict[str, Any]:
    label = f"{slot} custody receipt"
    receipt = _strict_keys(
        read_json(receipt_path, label=label),
        {
            "schema_version",
            "receipt_type",
            "panel_id",
            "baseline_name",
            "candidate_name",
            "exact_command",
            "provenance",
            "grid",
            "sha256",
        },
        label=label,
    )
    if not is_int(receipt["schema_version"]) or receipt["schema_version"] != SCHEMA_VERSION:
        raise GateError(
            f"{label}.schema_version must equal integer {SCHEMA_VERSION}"
        )
    if receipt["receipt_type"] != _RECEIPT_TYPE:
        raise GateError(
            f"{label}.receipt_type must equal {_RECEIPT_TYPE!r}"
        )

    expected_identity = {
        "panel_id": report["panel_id"],
        "baseline_name": report["baseline_name"],
        "candidate_name": report["candidate_name"],
        "exact_command": report["exact_command"],
    }
    identity_drift = {
        key: {
            "expected": expected,
            "observed": receipt[key],
        }
        for key, expected in expected_identity.items()
        if receipt[key] != expected
    }
    if identity_drift:
        raise GateError(
            f"{label}: run identity drift: "
            + json.dumps(identity_drift, sort_keys=True, allow_nan=False)
        )

    receipt_provenance = _normalized_provenance(
        receipt["provenance"],
        label=f"{label}.provenance",
    )
    if receipt_provenance != report["provenance"]:
        drift = {
            key: {
                "expected": report["provenance"][key],
                "observed": receipt_provenance[key],
            }
            for key in _PROVENANCE_FIELDS
            if receipt_provenance[key] != report["provenance"][key]
        }
        raise GateError(
            f"{label}: provenance drift: "
            + json.dumps(drift, sort_keys=True)
        )

    expected_grid = _normalized_grid(report)
    if receipt["grid"] != expected_grid:
        raise GateError(
            f"{label}: normalized grid drift; "
            f"expected={json.dumps(expected_grid, sort_keys=True)}, "
            f"observed={json.dumps(receipt['grid'], sort_keys=True)}"
        )

    receipt_sha_obj = _strict_keys(
        receipt["sha256"],
        set(_RECEIPT_SHA_FIELDS),
        label=f"{label}.sha256",
    )
    receipt_sha = {
        key: _hex_value(
            receipt_sha_obj[key],
            lengths=(64,),
            label=f"{label}.sha256.{key}",
        )
        for key in _RECEIPT_SHA_FIELDS
    }
    expected_sha = {
        "contract": outer_hashes[f"{slot}_contract"],
        "evidence": outer_hashes[f"{slot}_evidence"],
        "engine_artifact": outer_hashes["engine_artifact"],
        "runner_artifact": outer_hashes["runner_artifact"],
        "baseline_artifact": outer_hashes[f"{slot}_artifact"],
        "candidate_artifact": outer_hashes["candidate_artifact"],
        "baseline_games": outer_hashes[f"{slot}_games"],
        "candidate_games": outer_hashes["candidate_games"],
    }
    sha_drift = {
        key: {
            "expected": expected_sha[key],
            "observed": receipt_sha[key],
        }
        for key in _RECEIPT_SHA_FIELDS
        if receipt_sha[key] != expected_sha[key]
    }
    if sha_drift:
        raise GateError(
            f"{label}: exact file SHA-256 binding drift: "
            + json.dumps(sha_drift, sort_keys=True)
        )

    declared_artifacts = {
        "engine_artifact": report["provenance"]["engine_sha256"],
        "runner_artifact": report["provenance"]["runner_sha256"],
        "baseline_artifact": report["provenance"]["baseline_artifact_sha256"],
        "candidate_artifact": report["provenance"]["candidate_artifact_sha256"],
    }
    observed_artifacts = {
        "engine_artifact": outer_hashes["engine_artifact"],
        "runner_artifact": outer_hashes["runner_artifact"],
        "baseline_artifact": outer_hashes[f"{slot}_artifact"],
        "candidate_artifact": outer_hashes["candidate_artifact"],
    }
    artifact_drift = {
        key: {
            "declared": declared_artifacts[key],
            "observed": observed_artifacts[key],
        }
        for key in declared_artifacts
        if declared_artifacts[key] != observed_artifacts[key]
    }
    if artifact_drift:
        raise GateError(
            f"{label}: declared artifact digest does not match observed bytes: "
            + json.dumps(artifact_drift, sort_keys=True)
        )

    return {
        "receipt_type": _RECEIPT_TYPE,
        "receipt_sha256": outer_hashes[f"{slot}_receipt"],
        "panel_id": report["panel_id"],
        "baseline_name": report["baseline_name"],
        "candidate_name": report["candidate_name"],
        "exact_command": report["exact_command"],
        "declared_provenance": receipt_provenance,
        "observed_artifact_sha256": observed_artifacts,
        "bound_file_sha256": receipt_sha,
        "grid": expected_grid,
    }


def _validate_cross_comparison(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    outer_hashes: Mapping[str, str],
) -> dict[str, Any]:
    drift: dict[str, Any] = {}

    if first["candidate_name"] != second["candidate_name"]:
        drift["candidate_name"] = {
            "predecessor_a": first["candidate_name"],
            "predecessor_b": second["candidate_name"],
        }

    first_shared = {
        key: first["provenance"][key]
        for key in _SHARED_PROVENANCE
    }
    second_shared = {
        key: second["provenance"][key]
        for key in _SHARED_PROVENANCE
    }
    if first_shared != second_shared:
        drift["shared_provenance"] = {
            key: {
                "predecessor_a": first_shared[key],
                "predecessor_b": second_shared[key],
            }
            for key in _SHARED_PROVENANCE
            if first_shared[key] != second_shared[key]
        }

    first_grid = _normalized_grid(first)
    second_grid = _normalized_grid(second)
    if first_grid != second_grid:
        drift["grid"] = {
            "predecessor_a": first_grid,
            "predecessor_b": second_grid,
        }

    if first["policy"] != second["policy"]:
        drift["policy"] = {
            "predecessor_a": first["policy"],
            "predecessor_b": second["policy"],
        }

    first_candidate_games = first["input_sha256"]["candidate_games"]
    second_candidate_games = second["input_sha256"]["candidate_games"]
    candidate_games_sha256 = outer_hashes["candidate_games"]
    if (
        first_candidate_games != candidate_games_sha256
        or second_candidate_games != candidate_games_sha256
    ):
        drift["candidate_games_sha256"] = {
            "outer_snapshot": candidate_games_sha256,
            "predecessor_a": first_candidate_games,
            "predecessor_b": second_candidate_games,
        }

    first_baseline_name = first["baseline_name"]
    second_baseline_name = second["baseline_name"]
    if first_baseline_name == second_baseline_name:
        drift["baseline_name"] = {
            "error": "predecessor names must be distinct",
            "value": first_baseline_name,
        }

    first_declared_baseline = first["provenance"]["baseline_artifact_sha256"]
    second_declared_baseline = second["provenance"]["baseline_artifact_sha256"]
    if first_declared_baseline == second_declared_baseline:
        drift["baseline_artifact_sha256"] = {
            "error": "declared predecessor artifacts must be distinct",
            "value": first_declared_baseline,
        }

    first_observed_baseline = outer_hashes["predecessor_a_artifact"]
    second_observed_baseline = outer_hashes["predecessor_b_artifact"]
    if first_observed_baseline == second_observed_baseline:
        drift["observed_baseline_artifact_sha256"] = {
            "error": "observed predecessor artifact bytes must be distinct",
            "value": first_observed_baseline,
        }

    first_baseline_games = outer_hashes["predecessor_a_games"]
    second_baseline_games = outer_hashes["predecessor_b_games"]
    first_baseline_semantic = _baseline_semantic_sha256(first)
    second_baseline_semantic = _baseline_semantic_sha256(second)
    if (
        first_baseline_semantic == second_baseline_semantic
        and first_baseline_games != second_baseline_games
    ):
        drift["baseline_semantic_sha256"] = {
            "error": (
                "predecessor game panels are semantically identical; "
                "reserialization is not evidence of a second execution"
            ),
            "value": first_baseline_semantic,
        }

    declared_candidate = first_shared["candidate_artifact_sha256"]
    observed_candidate = outer_hashes["candidate_artifact"]
    declared_aliases = []
    if declared_candidate == first_declared_baseline:
        declared_aliases.append("predecessor_a")
    if declared_candidate == second_declared_baseline:
        declared_aliases.append("predecessor_b")
    if declared_aliases:
        drift["declared_candidate_artifact_alias"] = {
            "candidate_artifact_sha256": declared_candidate,
            "aliases": declared_aliases,
        }

    observed_aliases = []
    if observed_candidate == first_observed_baseline:
        observed_aliases.append("predecessor_a")
    if observed_candidate == second_observed_baseline:
        observed_aliases.append("predecessor_b")
    if observed_aliases:
        drift["observed_candidate_artifact_alias"] = {
            "candidate_artifact_sha256": observed_candidate,
            "aliases": observed_aliases,
        }

    if drift:
        raise GateError(
            "dual-predecessor comparison drift: "
            + json.dumps(drift, sort_keys=True, allow_nan=False)
        )

    return {
        "candidate_name": first["candidate_name"],
        "declared_provenance": first_shared,
        "observed_artifact_sha256": {
            "engine_artifact": outer_hashes["engine_artifact"],
            "runner_artifact": outer_hashes["runner_artifact"],
            "candidate_artifact": outer_hashes["candidate_artifact"],
        },
        "candidate_games_sha256": candidate_games_sha256,
        "predecessor_baseline_semantic_sha256": {
            "predecessor_a": first_baseline_semantic,
            "predecessor_b": second_baseline_semantic,
        },
        "grid": first_grid,
        "policy": first["policy"],
    }


def run_dual_gate(
    *,
    predecessor_a_contract_path: Path,
    predecessor_a_evidence_path: Path,
    predecessor_a_games_path: Path,
    predecessor_a_receipt_path: Path,
    predecessor_a_artifact_path: Path,
    predecessor_b_contract_path: Path,
    predecessor_b_evidence_path: Path,
    predecessor_b_games_path: Path,
    predecessor_b_receipt_path: Path,
    predecessor_b_artifact_path: Path,
    candidate_games_path: Path,
    candidate_artifact_path: Path,
    engine_artifact_path: Path,
    runner_artifact_path: Path,
) -> tuple[dict[str, Any], int]:
    sources = {
        "predecessor_a_contract": (
            predecessor_a_contract_path,
            MAX_JSON_BYTES,
            "predecessor A contract",
        ),
        "predecessor_a_evidence": (
            predecessor_a_evidence_path,
            MAX_JSON_BYTES,
            "predecessor A evidence",
        ),
        "predecessor_a_games": (
            predecessor_a_games_path,
            MAX_JSONL_BYTES,
            "predecessor A games",
        ),
        "predecessor_a_receipt": (
            predecessor_a_receipt_path,
            MAX_JSON_BYTES,
            "predecessor A custody receipt",
        ),
        "predecessor_a_artifact": (
            predecessor_a_artifact_path,
            MAX_JSONL_BYTES,
            "predecessor A artifact bundle",
        ),
        "predecessor_b_contract": (
            predecessor_b_contract_path,
            MAX_JSON_BYTES,
            "predecessor B contract",
        ),
        "predecessor_b_evidence": (
            predecessor_b_evidence_path,
            MAX_JSON_BYTES,
            "predecessor B evidence",
        ),
        "predecessor_b_games": (
            predecessor_b_games_path,
            MAX_JSONL_BYTES,
            "predecessor B games",
        ),
        "predecessor_b_receipt": (
            predecessor_b_receipt_path,
            MAX_JSON_BYTES,
            "predecessor B custody receipt",
        ),
        "predecessor_b_artifact": (
            predecessor_b_artifact_path,
            MAX_JSONL_BYTES,
            "predecessor B artifact bundle",
        ),
        "candidate_games": (
            candidate_games_path,
            MAX_JSONL_BYTES,
            "shared candidate games",
        ),
        "candidate_artifact": (
            candidate_artifact_path,
            MAX_JSONL_BYTES,
            "candidate artifact bundle",
        ),
        "engine_artifact": (
            engine_artifact_path,
            MAX_JSONL_BYTES,
            "engine artifact bundle",
        ),
        "runner_artifact": (
            runner_artifact_path,
            MAX_JSONL_BYTES,
            "runner artifact bundle",
        ),
    }

    with TemporaryDirectory(
        prefix="titan-v3-dual-predecessor-gate-"
    ) as directory:
        snapshot_root = Path(directory)
        snapshots = {
            name: snapshot_regular_file(
                path,
                directory=snapshot_root,
                max_bytes=max_bytes,
                label=label,
            )
            for name, (path, max_bytes, label) in sources.items()
        }
        paths = {
            name: snapshot.path
            for name, snapshot in snapshots.items()
        }
        hashes = {
            name: snapshot.sha256
            for name, snapshot in snapshots.items()
        }
        sizes = {
            name: snapshot.bytes
            for name, snapshot in snapshots.items()
        }

        reports: dict[str, dict[str, Any]] = {}
        codes: dict[str, int] = {}
        custody: dict[str, dict[str, Any]] = {}
        for slot in _SLOTS:
            report, code = single_gate.run_gate(
                contract_path=paths[f"{slot}_contract"],
                evidence_path=paths[f"{slot}_evidence"],
                baseline_path=paths[f"{slot}_games"],
                candidate_path=paths["candidate_games"],
            )
            _bind_inner_inputs(
                report=report,
                outer_hashes=hashes,
                slot=slot,
            )
            custody[slot] = _validate_custody_receipt(
                receipt_path=paths[f"{slot}_receipt"],
                report=report,
                outer_hashes=hashes,
                slot=slot,
            )
            reports[slot] = report
            codes[slot] = code

        shared = _validate_cross_comparison(
            reports["predecessor_a"],
            reports["predecessor_b"],
            outer_hashes=hashes,
        )

        changed_snapshots = {}
        for name, snapshot in snapshots.items():
            observed = sha256_file(snapshot.path)
            if observed != snapshot.sha256:
                changed_snapshots[name] = {
                    "expected": snapshot.sha256,
                    "observed": observed,
                }
        if changed_snapshots:
            raise GateError(
                "private dual-gate input snapshot changed during evaluation: "
                + json.dumps(changed_snapshots, sort_keys=True)
            )

        promote = all(codes[slot] == 0 for slot in _SLOTS)
        report = {
            "schema_version": SCHEMA_VERSION,
            "verdict": "PROMOTE" if promote else "REJECT",
            "valid": True,
            "mode": "dual-predecessor-custody-bound",
            "input_sha256": hashes,
            "input_bytes": sizes,
            "input_binding": (
                "all fourteen inputs snapshotted before either comparison; "
                "one candidate snapshot is parsed by both single gates; "
                "strict receipts bind every compared panel to observed "
                "artifact bytes"
            ),
            "shared": shared,
            "custody": custody,
            "comparison_exit_codes": codes,
            "comparisons": reports,
        }
        return report, 0 if promote else 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for slot in _SLOTS:
        prefix = slot.replace("_", "-")
        parser.add_argument(
            f"--{prefix}-contract",
            required=True,
            type=Path,
        )
        parser.add_argument(
            f"--{prefix}-evidence",
            required=True,
            type=Path,
        )
        parser.add_argument(
            f"--{prefix}-games",
            required=True,
            type=Path,
        )
        parser.add_argument(
            f"--{prefix}-receipt",
            required=True,
            type=Path,
        )
        parser.add_argument(
            f"--{prefix}-artifact",
            required=True,
            type=Path,
        )
    parser.add_argument(
        "--candidate-games",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--candidate-artifact",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--engine-artifact",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--runner-artifact",
        required=True,
        type=Path,
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        report, code = run_dual_gate(
            predecessor_a_contract_path=args.predecessor_a_contract,
            predecessor_a_evidence_path=args.predecessor_a_evidence,
            predecessor_a_games_path=args.predecessor_a_games,
            predecessor_a_receipt_path=args.predecessor_a_receipt,
            predecessor_a_artifact_path=args.predecessor_a_artifact,
            predecessor_b_contract_path=args.predecessor_b_contract,
            predecessor_b_evidence_path=args.predecessor_b_evidence,
            predecessor_b_games_path=args.predecessor_b_games,
            predecessor_b_receipt_path=args.predecessor_b_receipt,
            predecessor_b_artifact_path=args.predecessor_b_artifact,
            candidate_games_path=args.candidate_games,
            candidate_artifact_path=args.candidate_artifact,
            engine_artifact_path=args.engine_artifact,
            runner_artifact_path=args.runner_artifact,
        )
    except (GateError, OSError, UnicodeError) as exc:
        report, code = {
            "schema_version": SCHEMA_VERSION,
            "verdict": "INVALID",
            "valid": False,
            "error": str(exc),
        }, 2

    atomic_write_json(args.report, report)
    if not args.quiet:
        print(
            json.dumps(
                report,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
