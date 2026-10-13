#!/usr/bin/env python3
"""Public-safe submission edge helpers for HackerRank Orchestrate.

No challenge-specific logic lives here. The challenge prompt and official schema
remain authoritative.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any, Iterable

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {
    "authorization", "apikey", "api_key", "password", "passwd", "secret",
    "token", "access_token", "refresh_token", "cookie", "set_cookie",
}
PRIVATE_VISIBILITY = {"private", "internal", "secret"}
TOKEN_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)


class EdgeError(ValueError):
    pass


def _normalized_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def redact_string(value: str) -> str:
    out = value
    for pattern in TOKEN_PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _normalized_key(str(key)) in SENSITIVE_KEYS:
                cleaned[str(key)] = REDACTED
            else:
                cleaned[str(key)] = sanitize(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def sanitize_transcript(src: Path, dst: Path) -> dict[str, Any]:
    kept = dropped = 0
    with src.open("r", encoding="utf-8") as inp, dst.open("w", encoding="utf-8") as out:
        for lineno, raw in enumerate(inp, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise EdgeError(f"{src}:{lineno}: invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise EdgeError(f"{src}:{lineno}: each transcript line must be a JSON object")
            visibility = str(record.get("visibility", "")).strip().lower()
            if visibility in PRIVATE_VISIBILITY:
                dropped += 1
                continue
            out.write(json.dumps(sanitize(record), ensure_ascii=False, sort_keys=True) + "\n")
            kept += 1
    return {"kept": kept, "dropped_private": dropped, "output": str(dst)}


def _load_rows(path: Path, fmt: str) -> list[dict[str, Any]]:
    if fmt == "auto":
        suffix = path.suffix.lower()
        fmt = "jsonl" if suffix in {".jsonl", ".ndjson"} else "csv"
    if fmt == "csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if fmt == "jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise EdgeError(f"{path}:{lineno}: invalid JSON: {exc.msg}") from exc
                if not isinstance(row, dict):
                    raise EdgeError(f"{path}:{lineno}: each row must be a JSON object")
                rows.append(row)
        return rows
    raise EdgeError(f"unsupported format: {fmt}")


def _canonical_digest(rows: Iterable[dict[str, Any]], id_field: str | None) -> str:
    material = list(rows)
    if id_field:
        material.sort(key=lambda row: str(row.get(id_field, "")))
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_output(
    path: Path,
    fmt: str,
    required: list[str],
    id_field: str | None,
    expected_ids: Path | None,
    compare: Path | None,
    allow_extra: bool,
) -> dict[str, Any]:
    rows = _load_rows(path, fmt)
    errors: list[str] = []
    required_set = set(required)
    ids: list[str] = []

    for idx, row in enumerate(rows, 1):
        missing = sorted(key for key in required_set if key not in row or row[key] in (None, ""))
        if missing:
            errors.append(f"row {idx}: missing required fields {missing}")
        if id_field:
            if id_field not in row or row[id_field] in (None, ""):
                errors.append(f"row {idx}: missing id field {id_field!r}")
            else:
                ids.append(str(row[id_field]))

    if id_field:
        seen: set[str] = set()
        dupes: set[str] = set()
        for item in ids:
            if item in seen:
                dupes.add(item)
            seen.add(item)
        if dupes:
            errors.append(f"duplicate ids: {sorted(dupes)}")

    if expected_ids:
        expected = {
            line.strip()
            for line in expected_ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        actual = set(ids)
        missing_ids = sorted(expected - actual)
        extras = sorted(actual - expected)
        if missing_ids:
            errors.append(f"missing expected ids: {missing_ids}")
        if extras and not allow_extra:
            errors.append(f"unexpected ids: {extras}")

    digest = _canonical_digest(rows, id_field)
    compare_digest = None
    if compare:
        other = _load_rows(compare, fmt)
        compare_digest = _canonical_digest(other, id_field)
        if digest != compare_digest:
            errors.append("normalized output differs from comparison file")

    return {
        "ok": not errors,
        "rows": len(rows),
        "sha256_normalized": digest,
        "compare_sha256_normalized": compare_digest,
        "errors": errors,
    }


def _artifact_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EdgeError(f"artifact does not exist or is not a file: {path}")
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_receipt(
    artifacts: list[Path],
    metadata: list[str],
    commit: str | None,
    model: str | None,
    wall_seconds: float | None,
) -> dict[str, Any]:
    meta: dict[str, str] = {}
    for entry in metadata:
        if "=" not in entry:
            raise EdgeError(f"metadata must be KEY=VALUE: {entry!r}")
        key, value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise EdgeError("metadata key cannot be empty")
        if _normalized_key(key) in SENSITIVE_KEYS:
            raise EdgeError(f"refusing sensitive metadata key: {key}")
        meta[key] = redact_string(value.strip())

    return {
        "schema_version": 1,
        "commit": commit,
        "model": model,
        "wall_seconds": wall_seconds,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "metadata": meta,
        "artifacts": [_artifact_receipt(path) for path in artifacts],
    }


def write_defense(
    receipt: dict[str, Any],
    architecture: str,
    tradeoffs: list[str],
    failure_modes: list[str],
    output: Path,
) -> None:
    artifact_lines = "\n".join(
        f"- {item['path']} — {item['bytes']} bytes — {item['sha256']}"
        for item in receipt.get("artifacts", [])
    ) or "- No artifacts recorded."
    tradeoff_lines = "\n".join(f"- {item}" for item in tradeoffs) or "- Not recorded."
    failure_lines = "\n".join(f"- {item}" for item in failure_modes) or "- Not recorded."
    text = f"""# Orchestrate technical defense

## Architecture
{architecture.strip() or "Not recorded."}

## Reproducibility receipt
- Commit: {receipt.get("commit") or "not recorded"}
- Model: {receipt.get("model") or "not recorded"}
- Wall time: {receipt.get("wall_seconds") if receipt.get("wall_seconds") is not None else "not recorded"}
{artifact_lines}

## Explicit tradeoffs
{tradeoff_lines}

## Known failure modes / limitations
{failure_lines}

## Judge checklist
- Which decisions are deterministic code vs model decisions?
- What evidence shows the output is structurally complete?
- Which failure modes were measured rather than assumed?
- What would be changed with another iteration?
"""
    output.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    tx = sub.add_parser("sanitize-transcript")
    tx.add_argument("input", type=Path)
    tx.add_argument("output", type=Path)

    val = sub.add_parser("validate-output")
    val.add_argument("input", type=Path)
    val.add_argument("--format", choices=("auto", "csv", "jsonl"), default="auto")
    val.add_argument("--required", action="append", default=[])
    val.add_argument("--id-field")
    val.add_argument("--expected-ids", type=Path)
    val.add_argument("--compare", type=Path)
    val.add_argument("--allow-extra", action="store_true")

    rec = sub.add_parser("receipt")
    rec.add_argument("--artifact", action="append", type=Path, default=[])
    rec.add_argument("--metadata", action="append", default=[])
    rec.add_argument("--commit")
    rec.add_argument("--model")
    rec.add_argument("--wall-seconds", type=float)
    rec.add_argument("--output", type=Path, required=True)

    defense = sub.add_parser("defense")
    defense.add_argument("receipt", type=Path)
    defense.add_argument("--architecture", default="")
    defense.add_argument("--tradeoff", action="append", default=[])
    defense.add_argument("--failure-mode", action="append", default=[])
    defense.add_argument("--output", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "sanitize-transcript":
            result = sanitize_transcript(args.input, args.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "validate-output":
            result = validate_output(
                args.input, args.format, args.required, args.id_field,
                args.expected_ids, args.compare, args.allow_extra,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result["ok"] else 2
        if args.command == "receipt":
            receipt = build_receipt(
                args.artifact, args.metadata, args.commit, args.model, args.wall_seconds
            )
            args.output.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps({"ok": True, "output": str(args.output)}, sort_keys=True))
            return 0
        if args.command == "defense":
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            write_defense(
                receipt, args.architecture, args.tradeoff, args.failure_mode, args.output
            )
            print(json.dumps({"ok": True, "output": str(args.output)}, sort_keys=True))
            return 0
    except (EdgeError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
