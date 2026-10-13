# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from typing import Any, Mapping

from weed_model import Semantics

class DuplicateKeyError(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _find_key(value: Any, key: str, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    found: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, dict):
        for name, child in value.items():
            path = (*prefix, name)
            if name == key:
                found.append((path, child))
            found.extend(_find_key(child, key, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_key(child, key, (*prefix, str(index))))
    return found


def analyze_config(source: bytes) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "parse_ok": False,
        "weed_key_count": 0,
        "weed_key_paths": [],
        "weed_key_present": False,
        "weed_value_is_boolean": False,
        "weed_value": None,
        "errors": [],
    }
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        facts["errors"].append(f"config is not UTF-8: {exc}")
        return facts
    try:
        data = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant
        )
    except (json.JSONDecodeError, DuplicateKeyError, ValueError) as exc:
        facts["errors"].append(f"config parse failure: {exc}")
        return facts
    facts["parse_ok"] = True
    found = _find_key(data, "weed_continuation")
    facts["weed_key_count"] = len(found)
    facts["weed_key_paths"] = [".".join(path) for path, _ in found]
    facts["weed_key_present"] = len(found) == 1
    if len(found) == 1:
        value = found[0][1]
        facts["weed_value_is_boolean"] = isinstance(value, bool)
        facts["weed_value"] = value if isinstance(value, bool) else None
        if not isinstance(value, bool):
            facts["errors"].append("weed_continuation must be a JSON boolean")
    elif len(found) > 1:
        facts["errors"].append("weed_continuation appears at multiple paths")
    else:
        facts["errors"].append("weed_continuation key missing")
    return facts


def classify(
    spatial: Mapping[str, Any],
    runtime: Mapping[str, Any],
    entrypoint: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[Semantics, list[str]]:
    reasons: list[str] = []
    if not spatial.get("parse_ok"):
        return Semantics.AMBIGUOUS, ["SPATIAL_PARSE_FAILED"]
    if not runtime.get("parse_ok"):
        return Semantics.AMBIGUOUS, ["RUNTIME_PARSE_FAILED"]
    if not entrypoint.get("parse_ok"):
        return Semantics.AMBIGUOUS, ["ENTRYPOINT_PARSE_FAILED"]
    if not config.get("parse_ok"):
        return Semantics.AMBIGUOUS, ["CONFIG_PARSE_FAILED"]

    calls = int(spatial.get("weed_call_count", 0))
    constructor_ready = (
        bool(spatial.get("constructor_declares_weed_bit"))
        and bool(spatial.get("constructor_stores_weed_bit"))
        and bool(spatial.get("constructor_symbolically_wires_weed_bit"))
    )
    source_guard_ready = bool(spatial.get("all_weed_calls_independently_guarded"))
    runtime_ready = bool(runtime.get("features_declares_weed_bit")) and bool(
        runtime.get("all_spatialtempo_calls_wire_weed_bit")
    )
    entrypoint_ready = bool(entrypoint.get("end_to_end_config_to_features"))
    config_ready = bool(config.get("weed_key_present")) and bool(
        config.get("weed_value_is_boolean")
    )

    if calls == 0:
        # Absence of the capability is safe W0 only when the entire source was
        # parsed and runtime construction remains visible.  This is explicit in
        # the receipt even though no flag is needed to disable removed code.
        if int(runtime.get("spatialtempo_call_count", 0)) > 0:
            return Semantics.EXPLICIT_W0, ["WEED_CAPABILITY_ABSENT"]
        return Semantics.AMBIGUOUS, ["WEED_AND_SPATIAL_CONSTRUCTION_ABSENT"]

    if (
        constructor_ready
        and source_guard_ready
        and runtime_ready
        and entrypoint_ready
        and config_ready
    ):
        value = bool(config.get("weed_value"))
        return (
            Semantics.EXPLICIT_W1 if value else Semantics.EXPLICIT_W0,
            ["INDEPENDENT_WEED_CAPABILITY_END_TO_END", "CONFIG_W1" if value else "CONFIG_W0"],
        )

    no_independent_path = not (
        spatial.get("constructor_declares_weed_bit")
        or spatial.get("constructor_stores_weed_bit")
        or runtime.get("features_declares_weed_bit")
        or runtime.get("weed_keyword_call_count")
        or config.get("weed_key_present")
    )
    if no_independent_path and spatial.get("all_weed_calls_path_or_tempo_guarded"):
        return Semantics.COUPLED_WEED, ["WEED_COUPLED_TO_PATH_OR_TEMPO", "NO_INDEPENDENT_W_BIT"]
    if (
        no_independent_path
        and spatial.get("weed_call_precedes_spatial_disable_return")
        and int(spatial.get("unguarded_call_count", 0)) > 0
    ):
        return Semantics.LEGACY_PRE_GATE_W1, [
            "WEED_EXECUTES_BEFORE_SPATIAL_DISABLE_RETURN",
            "NO_INDEPENDENT_W_BIT",
            "P0_T0_DOES_NOT_IMPLY_W0",
        ]

    if not constructor_ready:
        reasons.append("SPATIAL_CONSTRUCTOR_W_BIT_INCOMPLETE")
    if not source_guard_ready:
        reasons.append("WEED_CALL_NOT_INDEPENDENTLY_GUARDED")
    if not runtime.get("features_declares_weed_bit"):
        reasons.append("RUNTIME_FEATURE_W_BIT_MISSING")
    if not runtime.get("all_spatialtempo_calls_wire_weed_bit"):
        reasons.append("RUNTIME_W_BIT_NOT_SYMBOLICALLY_WIRED")
    if not entrypoint_ready:
        reasons.append("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED")
    if not config.get("weed_key_present"):
        reasons.append("CONFIG_W_BIT_MISSING_OR_DUPLICATE")
    elif not config.get("weed_value_is_boolean"):
        reasons.append("CONFIG_W_BIT_NOT_BOOLEAN")
    return Semantics.AMBIGUOUS, reasons or ["UNCLASSIFIED_WEED_SEMANTICS"]
