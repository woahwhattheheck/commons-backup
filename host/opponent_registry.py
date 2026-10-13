#!/usr/bin/env python3
"""Digest-keyed opponent and causal-witness registry (visibility D6)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPPONENT_KEYS = frozenset({"name", "source"})
_WITNESS_KEYS = frozenset(
    {
        "id",
        "opponent_digest",
        "canonical_parent",
        "intervention",
        "observable",
        "outcome",
        "evidence",
    }
)


class OpponentRegistryError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


def _text(value: Any, field: str, witness: str | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise OpponentRegistryError("INVALID_FIELD", f"{field} must be a non-empty string", field=field, witness=witness)
    return value.strip()


def _digest(value: Any, field: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise OpponentRegistryError("INVALID_DIGEST", f"{field} must be an exact lowercase 64-hex SHA-256 digest", field=field)
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise OpponentRegistryError(
                "DUPLICATE_JSON_KEY",
                "JSON object contains a duplicate member",
                key=key,
            )
        out[key] = value
    return out


def load_registry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"version", "opponents", "witnesses"}:
        raise OpponentRegistryError("INVALID_REGISTRY", "registry must contain exactly version, opponents, witnesses")
    if type(payload["version"]) is not int or payload["version"] != VERSION:
        raise OpponentRegistryError("UNSUPPORTED_VERSION", "registry version must be exact integer 1")
    if type(payload["opponents"]) is not dict:
        raise OpponentRegistryError("INVALID_OPPONENTS", "opponents must be an object keyed by digest")
    if type(payload["witnesses"]) is not list:
        raise OpponentRegistryError("INVALID_WITNESSES", "witnesses must be a list")

    opponents: dict[str, dict[str, str]] = {}
    for digest, raw in payload["opponents"].items():
        digest = _digest(digest, "opponents key")
        if not isinstance(raw, dict) or set(raw) != _OPPONENT_KEYS:
            raise OpponentRegistryError(
                "INVALID_OPPONENT",
                "opponent metadata must contain exactly name and source",
                digest=digest,
            )
        opponents[digest] = {
            "name": _text(raw["name"], "opponent.name"),
            "source": _text(raw["source"], "opponent.source"),
        }

    witnesses: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in payload["witnesses"]:
        if not isinstance(raw, dict) or set(raw) != _WITNESS_KEYS:
            keys = sorted(raw) if isinstance(raw, dict) else None
            raise OpponentRegistryError(
                "INVALID_WITNESS",
                "witness must contain exactly id, opponent_digest, canonical_parent, intervention, observable, outcome, evidence",
                keys=keys,
            )
        witness_id = _text(raw["id"], "id")
        if witness_id in seen:
            raise OpponentRegistryError("DUPLICATE_WITNESS", "witness id appears more than once", witness=witness_id)
        seen.add(witness_id)
        opponent_digest = _digest(raw["opponent_digest"], "opponent_digest")
        if opponent_digest not in opponents:
            raise OpponentRegistryError(
                "UNKNOWN_OPPONENT",
                "witness references an opponent digest absent from this registry",
                witness=witness_id,
                opponent_digest=opponent_digest,
            )
        witnesses.append(
            {
                "id": witness_id,
                "opponent_digest": opponent_digest,
                "canonical_parent": _text(raw["canonical_parent"], "canonical_parent", witness_id),
                "intervention": _text(raw["intervention"], "intervention", witness_id),
                "observable": _text(raw["observable"], "observable", witness_id),
                "outcome": _text(raw["outcome"], "outcome", witness_id),
                "evidence": _text(raw["evidence"], "evidence", witness_id),
            }
        )

    return {
        "version": VERSION,
        "opponents": {digest: opponents[digest] for digest in sorted(opponents)},
        "witnesses": sorted(witnesses, key=lambda item: item["id"]),
    }


def summarize(registry: dict[str, Any]) -> dict[str, Any]:
    counts_by_opponent = {digest: 0 for digest in registry["opponents"]}
    for witness in registry["witnesses"]:
        counts_by_opponent[witness["opponent_digest"]] += 1
    return {
        **registry,
        "counts": {
            "opponents": len(registry["opponents"]),
            "witnesses": len(registry["witnesses"]),
            "witnesses_by_opponent": counts_by_opponent,
        },
    }


def read_registry(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text, object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise OpponentRegistryError("INVALID_JSON", "registry is not strict JSON", line=exc.lineno, column=exc.colno) from exc
    return load_registry(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", help="registry JSON path, or - for stdin")
    parser.add_argument("--opponent", help="emit one exact SHA-256 opponent digest")
    parser.add_argument("--witness", help="emit one exact witness id")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = summarize(read_registry(args.registry))
        if args.opponent and args.witness:
            raise OpponentRegistryError("INVALID_QUERY", "choose at most one of --opponent and --witness")
        if args.opponent:
            digest = _digest(args.opponent, "--opponent")
            metadata = output["opponents"].get(digest)
            if metadata is None:
                raise OpponentRegistryError("OPPONENT_NOT_FOUND", "opponent digest is not registered", opponent_digest=digest)
            witnesses = [row for row in output["witnesses"] if row["opponent_digest"] == digest]
            output = {"version": VERSION, "opponent_digest": digest, "opponent": metadata, "witnesses": witnesses}
        elif args.witness:
            witness = next((row for row in output["witnesses"] if row["id"] == args.witness), None)
            if witness is None:
                raise OpponentRegistryError("WITNESS_NOT_FOUND", "witness id is not registered", witness=args.witness)
            output = {"version": VERSION, "witness": witness}
    except (OpponentRegistryError, OSError) as exc:
        result = exc.as_dict() if isinstance(exc, OpponentRegistryError) else {"ok": False, "error": "IO_ERROR", "message": str(exc)}
        json.dump(result, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 2
    output["ok"] = True
    json.dump(output, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
