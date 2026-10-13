#!/usr/bin/env python3
"""Fail-closed dynamic import provenance auditor for TITAN candidate trees.

The parent launches an isolated, bytecode-disabled child, imports ``main.py`` by
absolute path, activates the frozen runtime constructor, and emits a deterministic
JSON receipt for the source modules Python actually resolved.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:  # Required because the worker itself runs under -I.
    sys.path.insert(0, str(TOOL_ROOT))

from _titan_custody_common import (  # noqa: E402
    ENTRY_MODULE_PREFIX,
    MODULE_RE,
    SCHEMA,
    canonical_bytes,
    load_manifest,
    local_top_levels,
    normalize_relative,
    sha256_bytes,
)


def assignment(raw: str, option: str) -> tuple[str, Path]:
    module, separator, path = raw.partition("=")
    if not separator or not MODULE_RE.fullmatch(module):
        raise ValueError(f"{option} must be MODULE=PATH, got {raw!r}")
    return module, Path(path)


def sanitized_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")
    }
    environment["PYTHONHASHSEED"] = "0"
    return environment


def protocol_failure(
    *,
    code: str,
    raw_hash: str,
    canonical_hash: str,
    entrypoint: str,
    callable_name: str,
    activation: str,
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int | None = None,
) -> dict:
    violation = {
        "code": code,
        "stdout_bytes": len(stdout),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": sha256_bytes(stderr),
    }
    if returncode is not None:
        violation["child_returncode"] = returncode
    return {
        "schema": SCHEMA,
        "verdict": "FAIL",
        "candidate": {
            "root": ".",
            "manifest_raw_sha256": raw_hash,
            "manifest_canonical_sha256": canonical_hash,
            "entrypoint": entrypoint,
            "callable": callable_name,
            "activation": activation,
        },
        "violations": [violation],
    }


def parent_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--entrypoint", default="main.py")
    parser.add_argument("--callable", dest="callable_name", default="agent")
    parser.add_argument(
        "--activate", choices=("none", "titan-new-instance"), default="titan-new-instance"
    )
    parser.add_argument("--preload-root", action="append", default=[], metavar="MODULE=ROOT")
    parser.add_argument("--preload-file", action="append", default=[], metavar="MODULE=FILE")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)

    try:
        root = args.candidate_root.resolve(strict=True)
        manifest_path = args.manifest.resolve(strict=True)
        entrypoint = normalize_relative(args.entrypoint)
        if not MODULE_RE.fullmatch(args.callable_name):
            raise ValueError("--callable must be a dotted Python identifier")
        if not 0 < args.timeout_seconds <= 300:
            raise ValueError("--timeout-seconds must be in (0, 300]")
        manifest, raw_hash, canonical_hash = load_manifest(manifest_path)
        preloads: list[dict[str, str]] = []
        for raw in args.preload_root:
            module, path = assignment(raw, "--preload-root")
            resolved = path.resolve(strict=True)
            if not resolved.is_dir():
                raise ValueError(f"preload root is not a directory: {path}")
            preloads.append({"kind": "root", "module": module, "path": str(resolved)})
        for raw in args.preload_file:
            module, path = assignment(raw, "--preload-file")
            resolved = path.resolve(strict=True)
            if not resolved.is_file():
                raise ValueError(f"preload file is not a file: {path}")
            preloads.append({"kind": "file", "module": module, "path": str(resolved)})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    request = {
        "candidate_root": str(root),
        "manifest": manifest,
        "manifest_raw_sha256": raw_hash,
        "manifest_canonical_sha256": canonical_hash,
        "local_top_levels": local_top_levels(manifest),
        "entrypoint": entrypoint,
        "callable": args.callable_name,
        "activate": args.activate,
        "entry_module_name": ENTRY_MODULE_PREFIX + canonical_hash[:16],
        "preloads": sorted(preloads, key=lambda item: (item["kind"], item["module"], item["path"])),
    }
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--_child"]
    try:
        completed = subprocess.run(
            command,
            input=canonical_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=args.timeout_seconds,
            env=sanitized_environment(),
            cwd=str(root.parent),
        )
        try:
            receipt = json.loads(completed.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            receipt = protocol_failure(
                code="AUDITOR_CHILD_PROTOCOL_ERROR",
                raw_hash=raw_hash,
                canonical_hash=canonical_hash,
                entrypoint=entrypoint,
                callable_name=args.callable_name,
                activation=args.activate,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
            )
        success = receipt.get("verdict") == "PASS" and completed.returncode == 0
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        receipt = protocol_failure(
            code="AUDITOR_CHILD_TIMEOUT",
            raw_hash=raw_hash,
            canonical_hash=canonical_hash,
            entrypoint=entrypoint,
            callable_name=args.callable_name,
            activation=args.activate,
            stdout=stdout if isinstance(stdout, bytes) else stdout.encode(),
            stderr=stderr if isinstance(stderr, bytes) else stderr.encode(),
        )
        success = False

    rendered = canonical_bytes(receipt) + b"\n"
    if args.receipt is not None:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_bytes(rendered)
    sys.stdout.buffer.write(rendered)
    return 0 if success else 1


def main() -> int:
    if sys.argv[1:] == ["--_child"]:
        from _titan_custody_worker import child_main

        return child_main()
    return parent_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
