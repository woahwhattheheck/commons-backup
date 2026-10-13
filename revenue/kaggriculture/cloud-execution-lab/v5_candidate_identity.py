# SPDX-License-Identifier: Apache-2.0
"""Stable, fail-closed identity manifests for TITAN V5 experiment candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "titan-v5-candidate-identity/v1"
_SPEC_KEYS = {"base_id", "engine_id", "opponent_pack_id", "config", "components"}
_COMPONENT_KEYS = {"name", "source", "activation", "unconditional"}


class IdentityError(ValueError):
    """Candidate identity cannot be certified from the supplied evidence."""


def _typed(value: Any) -> Any:
    """Return a deterministic, type-preserving JSON representation."""
    if value is None:
        return {"t": "none"}
    if type(value) is bool:
        return {"t": "bool", "v": value}
    if type(value) is int:
        return {"t": "int", "v": str(value)}
    if type(value) is float:
        if not math.isfinite(value):
            raise IdentityError("non-finite float in identity input")
        return {"t": "float", "v": value.hex()}
    if type(value) is str:
        return {"t": "str", "v": value}
    if type(value) is list:
        return {"t": "list", "v": [_typed(item) for item in value]}
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise IdentityError("identity mappings require string keys")
        return {
            "t": "dict",
            "v": [[key, _typed(value[key])] for key in sorted(value)],
        }
    raise IdentityError(f"unsupported identity value type: {type(value).__name__}")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_equal(left: Any, right: Any) -> bool:
    return _typed(left) == _typed(right)


def _text_id(value: Any, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or not value.strip():
        raise IdentityError(f"{field} must be a non-empty string")
    return value


def _source_record(
    root: Path, component: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    if type(component) is not dict:
        raise IdentityError("each component must be an object")
    extra = set(component) - _COMPONENT_KEYS
    if extra:
        raise IdentityError(f"unknown component keys: {sorted(extra)}")

    name = _text_id(component.get("name"), "component name")
    source = _text_id(component.get("source"), f"{name}.source")
    if name is None or source is None:
        raise IdentityError("component name/source cannot be null")

    raw_source = Path(source)
    if raw_source.is_absolute():
        raise IdentityError(f"{name}: source must be relative to root")
    resolved_root = root.resolve()
    resolved_source = (resolved_root / raw_source).resolve()
    try:
        canonical_source = resolved_source.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise IdentityError(f"{name}: source escapes root") from exc
    if not resolved_source.is_file():
        raise IdentityError(f"{name}: source is not a file: {source}")

    unconditional = component.get("unconditional", False)
    if type(unconditional) is not bool:
        raise IdentityError(f"{name}: unconditional must be an exact bool")
    activation = component.get("activation")
    if unconditional:
        if activation not in (None, {}):
            raise IdentityError(
                f"{name}: unconditional and activation are mutually exclusive"
            )
        activation_record = {"mode": "unconditional"}
    else:
        if type(activation) is not dict or not activation:
            raise IdentityError(f"{name}: a non-empty activation mapping is required")
        if not all(type(key) is str for key in activation):
            raise IdentityError(f"{name}: activation keys must be strings")
        reserved = sorted(key for key in activation if key.startswith("_"))
        if reserved:
            raise IdentityError(
                f"{name}: activation cannot depend on reserved metadata keys: {reserved}"
            )
        for key, expected in activation.items():
            if key not in config:
                raise IdentityError(f"{name}: activation key missing from config: {key}")
            if not _exact_equal(config[key], expected):
                raise IdentityError(
                    f"{name}: activation mismatch for {key}: "
                    "actual type/value does not exactly match expected"
                )
        activation_record = {"mode": "config", "equals": _typed(activation)}

    digest = hashlib.sha256(resolved_source.read_bytes()).hexdigest()
    return {
        "name": name,
        "source": canonical_source,
        "source_sha256": digest,
        "activation": activation_record,
    }


def build_manifest(root: str | Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Build one stable candidate identity from source/config/runtime evidence."""
    if type(spec) is not dict:
        raise IdentityError("spec must be an object")
    extra = set(spec) - _SPEC_KEYS
    if extra:
        raise IdentityError(f"unknown spec keys: {sorted(extra)}")

    base_id = _text_id(spec.get("base_id"), "base_id")
    engine_id = _text_id(spec.get("engine_id"), "engine_id")
    opponent_pack_id = _text_id(
        spec.get("opponent_pack_id"), "opponent_pack_id", optional=True
    )
    config = spec.get("config")
    if type(config) is not dict:
        raise IdentityError("config must be an object")
    typed_config = _typed(config)

    components = spec.get("components")
    if type(components) is not list:
        raise IdentityError("components must be a list")
    root_path = Path(root)
    records = [_source_record(root_path, raw, config) for raw in components]
    names = [record["name"] for record in records]
    if len(names) != len(set(names)):
        raise IdentityError("component names must be unique")
    records.sort(key=lambda record: record["name"])

    body = {
        "schema": SCHEMA,
        "base_id": base_id,
        "engine_id": engine_id,
        "opponent_pack_id": opponent_pack_id,
        "config_sha256": _sha(typed_config),
        "components": records,
    }
    candidate_id = "v5c:" + _sha(body)
    return {**body, "candidate_id": candidate_id}


def validate_manifest(
    root: str | Path, spec: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Rebuild and compare every manifest field; fail on any drift."""
    if type(manifest) is not dict:
        raise IdentityError("manifest must be an object")
    expected = build_manifest(root, spec)
    if manifest != expected:
        raise IdentityError("candidate manifest does not match current evidence")
    return expected


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IdentityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise IdentityError(f"non-standard JSON number: {value}")


def _load_json(path: str | Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
        return json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except IdentityError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"cannot load JSON: {path}") from exc


def _emit(manifest: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    if output is None:
        print(text, end="")
        return
    destination = Path(output)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=".", help="root containing component source files"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a candidate identity manifest")
    build.add_argument("spec")
    build.add_argument("--output")

    check = sub.add_parser("validate", help="validate a candidate identity manifest")
    check.add_argument("spec")
    check.add_argument("manifest")

    args = parser.parse_args(argv)
    try:
        spec = _load_json(args.spec)
        if args.command == "build":
            manifest = build_manifest(args.root, spec)
            _emit(manifest, args.output)
        else:
            manifest = _load_json(args.manifest)
            validate_manifest(args.root, spec, manifest)
            print(manifest["candidate_id"])
    except IdentityError as exc:
        parser.exit(2, f"identity error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
