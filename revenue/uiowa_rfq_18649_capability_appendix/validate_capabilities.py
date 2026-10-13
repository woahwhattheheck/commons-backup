#!/usr/bin/env python3
"""Validate UIOWA-137 capability evidence against the checked-out source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "capabilities.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_COMMAND_FRAGMENTS = (
    "curl ",
    "wget ",
    "ssh ",
    "scp ",
    "slack",
    "gmail",
    "calendar",
    "submit",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def load(path: Path = DEFAULT_DATA) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("capability file root must be an object")
    return value


def validate(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    errors: list[str] = []
    snapshot = str(payload.get("snapshot_main_sha", ""))
    if payload.get("schema") != "uiowa.technical-capability-appendix.v1":
        errors.append("unexpected schema")
    if not SHA40.fullmatch(snapshot):
        errors.append("snapshot_main_sha must be 40 lowercase hexadecimal characters")

    classification = payload.get("evidence_classification")
    if not isinstance(classification, dict):
        errors.append("evidence_classification must be an object")
    else:
        for key in ("synthetic_demonstrations", "original_engineering", "client_validation"):
            if not str(classification.get(key, "")).strip():
                errors.append(f"missing evidence classification: {key}")

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        errors.append("capabilities must be a non-empty array")
        capabilities = []

    seen_ids: set[str] = set()
    source_count = 0
    verified_blobs = 0
    root = root.resolve()

    for index, capability in enumerate(capabilities):
        if not isinstance(capability, dict):
            errors.append(f"capability[{index}] must be an object")
            continue
        cap_id = str(capability.get("capability_id", "")).strip()
        if not cap_id:
            errors.append(f"capability[{index}] missing capability_id")
        elif cap_id in seen_ids:
            errors.append(f"duplicate capability_id: {cap_id}")
        else:
            seen_ids.add(cap_id)

        for field in ("title", "business_use", "reproduction_command"):
            if not str(capability.get(field, "")).strip():
                errors.append(f"{cap_id or index}: missing {field}")

        command = str(capability.get("reproduction_command", "")).lower()
        for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
            if fragment in command:
                errors.append(f"{cap_id}: forbidden reproduction command fragment {fragment!r}")

        observation = capability.get("provider_observation")
        if not isinstance(observation, dict) or not str(observation.get("method", "")).strip():
            errors.append(f"{cap_id}: missing provider observation")

        sources = capability.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{cap_id}: sources must be non-empty")
            continue

        for source in sources:
            source_count += 1
            rel = str(source.get("path", "")).strip()
            expected_sha = str(source.get("blob_sha", "")).strip()
            url = str(source.get("url", "")).strip()
            if not rel or not SHA40.fullmatch(expected_sha):
                errors.append(f"{cap_id}: malformed source record {rel!r}")
                continue

            candidate = (root / rel).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"{cap_id}: source escapes repository root: {rel}")
                continue
            if not candidate.is_file():
                errors.append(f"{cap_id}: source missing: {rel}")
                continue

            actual_sha = git_blob_sha(candidate)
            if actual_sha != expected_sha:
                errors.append(
                    f"{cap_id}: source byte drift for {rel}: expected {expected_sha}, got {actual_sha}"
                )
            else:
                verified_blobs += 1

            expected_url = (
                f"https://github.com/woahwhattheheck/commons/blob/{snapshot}/{rel}"
            )
            if url != expected_url:
                errors.append(f"{cap_id}: pinned URL mismatch for {rel}")

    return {
        "ok": not errors,
        "snapshot_main_sha": snapshot,
        "capabilities": len(capabilities),
        "sources": source_count,
        "verified_blobs": verified_blobs,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate(load(args.data), (args.root or repo_root()).resolve())
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"UIOWA-137 validation: {'PASS' if result['ok'] else 'FAIL'} "
            f"capabilities={result['capabilities']} "
            f"verified_blobs={result['verified_blobs']}/{result['sources']}"
        )
        for error in result["errors"]:
            print(f"ERROR: {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
