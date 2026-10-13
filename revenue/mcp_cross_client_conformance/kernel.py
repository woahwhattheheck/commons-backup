"""Deterministic, buyer-neutral cross-client MCP conformance evidence kernel.

This module does not connect to MCP servers or clients. It evaluates frozen,
externally-produced observations against an explicit conformance manifest.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

SCHEMA = "mcp-cross-client-conformance/v1"
REPORT_SCHEMA = "mcp-cross-client-conformance-report/v1"
HEX64 = set("0123456789abcdef")
ALLOWED_DISPOSITIONS = {"PASS", "HOLD", "REJECT", "UNVERIFIED"}
EVIDENCE_BINDING_FAILURES = {
    "SERVER_BUILD_MISMATCH",
    "FIXTURE_MISMATCH",
    "UNKNOWN_CLIENT",
}


class ConformanceError(ValueError):
    """Raised when evidence cannot be interpreted safely."""


def _reject_float(_: str) -> None:
    raise ConformanceError("FLOATS_NOT_ALLOWED")


def _reject_constant(_: str) -> None:
    raise ConformanceError("NONFINITE_NUMBER")


def _pairs_no_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ConformanceError(f"DUPLICATE_KEY:{key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    """Load JSON while refusing duplicate keys, floats, and non-finite numbers."""
    if not isinstance(text, str):
        raise ConformanceError("JSON_TEXT_REQUIRED")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except ConformanceError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConformanceError(f"INVALID_JSON:{exc.__class__.__name__}") from exc


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ConformanceError(f"FLOAT_NOT_ALLOWED:{path}")
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ConformanceError(f"NON_STRING_KEY:{path}")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ConformanceError(f"NON_JSON_TYPE:{path}:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConformanceError("CANONICALIZATION_FAILED") from exc
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def _require_exact_keys(obj: Mapping[str, Any], required: Iterable[str], optional: Iterable[str] = ()) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(obj))
    extra = sorted(set(obj) - allowed)
    if missing:
        raise ConformanceError("MISSING_KEYS:" + ",".join(missing))
    if extra:
        raise ConformanceError("UNKNOWN_KEYS:" + ",".join(extra))


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConformanceError(f"INVALID_STRING:{field}")
    return value


def _require_sha(value: Any, field: str) -> str:
    value = _require_nonempty_string(value, field)
    if len(value) != 64 or any(ch not in HEX64 for ch in value):
        raise ConformanceError(f"INVALID_SHA256:{field}")
    return value


def _require_unique_string_list(value: Any, field: str, *, nonempty: bool = True) -> List[str]:
    if not isinstance(value, list):
        raise ConformanceError(f"INVALID_LIST:{field}")
    if nonempty and not value:
        raise ConformanceError(f"EMPTY_LIST:{field}")
    out: List[str] = []
    seen = set()
    for i, item in enumerate(value):
        item = _require_nonempty_string(item, f"{field}[{i}]")
        if item in seen:
            raise ConformanceError(f"DUPLICATE_LIST_VALUE:{field}:{item}")
        seen.add(item)
        out.append(item)
    return out


def validate_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ConformanceError("MANIFEST_OBJECT_REQUIRED")
    _require_exact_keys(
        manifest,
        required={
            "schema", "server_build", "fixture", "supported_protocol_versions", "clients",
            "expected_tools", "resources", "hostile_expectations", "clean_runs_per_client",
            "production_action_limit",
        },
    )
    if manifest["schema"] != SCHEMA:
        raise ConformanceError("UNSUPPORTED_MANIFEST_SCHEMA")
    _require_nonempty_string(manifest["server_build"], "server_build")

    fixture = manifest["fixture"]
    if not isinstance(fixture, dict):
        raise ConformanceError("FIXTURE_OBJECT_REQUIRED")
    _require_exact_keys(fixture, {"id", "sha256"})
    _require_nonempty_string(fixture["id"], "fixture.id")
    _require_sha(fixture["sha256"], "fixture.sha256")

    protocols = _require_unique_string_list(manifest["supported_protocol_versions"], "supported_protocol_versions")
    clients = _require_unique_string_list(manifest["clients"], "clients")
    tools = _require_unique_string_list(manifest["expected_tools"], "expected_tools")

    resources = manifest["resources"]
    if not isinstance(resources, list) or not resources:
        raise ConformanceError("INVALID_RESOURCES")
    resource_ids = set()
    for i, resource in enumerate(resources):
        if not isinstance(resource, dict):
            raise ConformanceError(f"RESOURCE_OBJECT_REQUIRED:{i}")
        _require_exact_keys(resource, {"id", "kind", "sha256"})
        resource_id = _require_nonempty_string(resource["id"], f"resources[{i}].id")
        if resource_id in resource_ids:
            raise ConformanceError(f"DUPLICATE_RESOURCE:{resource_id}")
        resource_ids.add(resource_id)
        if resource["kind"] not in {"json", "raw"}:
            raise ConformanceError(f"INVALID_RESOURCE_KIND:{resource_id}")
        _require_sha(resource["sha256"], f"resources[{i}].sha256")

    hostile = manifest["hostile_expectations"]
    if not isinstance(hostile, dict) or not hostile:
        raise ConformanceError("HOSTILE_EXPECTATIONS_REQUIRED")
    for name, disposition in hostile.items():
        _require_nonempty_string(name, "hostile_expectations.key")
        if disposition not in {"HOLD", "REJECT", "UNVERIFIED"}:
            raise ConformanceError(f"INVALID_HOSTILE_DISPOSITION:{name}")

    clean_runs = manifest["clean_runs_per_client"]
    if not isinstance(clean_runs, int) or isinstance(clean_runs, bool) or clean_runs < 2:
        raise ConformanceError("CLEAN_RUNS_PER_CLIENT_MIN_2")
    action_limit = manifest["production_action_limit"]
    if not isinstance(action_limit, int) or isinstance(action_limit, bool) or action_limit != 0:
        raise ConformanceError("PRODUCTION_ACTION_LIMIT_MUST_BE_ZERO")

    normalized = deepcopy(manifest)
    normalized["supported_protocol_versions"] = protocols
    normalized["clients"] = clients
    normalized["expected_tools"] = tools
    return normalized


OBS_REQUIRED = {
    "observation_id", "client_id", "run_id", "case", "server_build", "fixture_sha256",
    "requested_protocol_version", "negotiated_protocol_version", "negotiation_status",
    "listing_status", "listed_tools", "resource_hashes", "production_action_count",
}


def _validate_observation_shape(observation: Mapping[str, Any]) -> None:
    if not isinstance(observation, dict):
        raise ConformanceError("OBSERVATION_OBJECT_REQUIRED")
    _require_exact_keys(observation, OBS_REQUIRED)
    for field in (
        "observation_id", "client_id", "run_id", "case", "server_build", "fixture_sha256",
        "requested_protocol_version", "negotiation_status", "listing_status",
    ):
        _require_nonempty_string(observation[field], field)
    negotiated = observation["negotiated_protocol_version"]
    if negotiated is not None:
        _require_nonempty_string(negotiated, "negotiated_protocol_version")
    if observation["negotiation_status"] not in {"OK", "REJECTED", "DOWNGRADED", "FAILED"}:
        raise ConformanceError("INVALID_NEGOTIATION_STATUS")
    if observation["listing_status"] not in {"OK", "UNREACHABLE", "REJECTED"}:
        raise ConformanceError("INVALID_LISTING_STATUS")
    _require_unique_string_list(observation["listed_tools"], "listed_tools", nonempty=False)
    hashes = observation["resource_hashes"]
    if not isinstance(hashes, dict):
        raise ConformanceError("RESOURCE_HASHES_OBJECT_REQUIRED")
    for key, value in hashes.items():
        _require_nonempty_string(key, "resource_hashes.key")
        _require_sha(value, f"resource_hashes.{key}")
    count = observation["production_action_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ConformanceError("INVALID_PRODUCTION_ACTION_COUNT")


def _manifest_resource_hashes(manifest: Mapping[str, Any]) -> Dict[str, str]:
    return {r["id"]: r["sha256"] for r in manifest["resources"]}


def assess_observation(manifest: Mapping[str, Any], observation: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-evaluate one observation from facts; never trust a caller's disposition."""
    _validate_observation_shape(observation)
    reasons: List[str] = []

    if observation["production_action_count"] != 0:
        reasons.append("PRODUCTION_ACTION_OBSERVED")
    if observation["server_build"] != manifest["server_build"]:
        reasons.append("SERVER_BUILD_MISMATCH")
    if observation["fixture_sha256"] != manifest["fixture"]["sha256"]:
        reasons.append("FIXTURE_MISMATCH")
    if observation["client_id"] not in set(manifest["clients"]):
        reasons.append("UNKNOWN_CLIENT")

    requested = observation["requested_protocol_version"]
    negotiated = observation["negotiated_protocol_version"]
    status = observation["negotiation_status"]

    if status == "DOWNGRADED":
        reasons.append("SILENT_OR_UNAPPROVED_DOWNGRADE")
        disposition = "REJECT"
    elif status in {"REJECTED", "FAILED"}:
        if requested not in manifest["supported_protocol_versions"]:
            reasons.append("UNSUPPORTED_PROTOCOL_REJECTED")
            disposition = "REJECT"
        else:
            reasons.append("SUPPORTED_PROTOCOL_NEGOTIATION_FAILED")
            disposition = "HOLD"
    elif requested not in manifest["supported_protocol_versions"]:
        reasons.append("UNSUPPORTED_PROTOCOL_ACCEPTED")
        disposition = "HOLD"
    elif negotiated != requested:
        reasons.append("NEGOTIATED_PROTOCOL_MISMATCH")
        disposition = "HOLD"
    elif observation["listing_status"] == "UNREACHABLE":
        reasons.append("LISTING_UNREACHABLE")
        disposition = "UNVERIFIED"
    elif observation["listing_status"] == "REJECTED":
        reasons.append("LISTING_REJECTED")
        disposition = "HOLD"
    else:
        expected_tools = sorted(manifest["expected_tools"])
        listed_tools = sorted(observation["listed_tools"])
        expected_resources = _manifest_resource_hashes(manifest)
        observed_resources = observation["resource_hashes"]
        if listed_tools != expected_tools:
            missing = sorted(set(expected_tools) - set(listed_tools))
            extra = sorted(set(listed_tools) - set(expected_tools))
            if missing:
                reasons.append("MISSING_TOOLS:" + ",".join(missing))
            if extra:
                reasons.append("UNEXPECTED_TOOLS:" + ",".join(extra))
        if set(observed_resources) != set(expected_resources):
            missing = sorted(set(expected_resources) - set(observed_resources))
            extra = sorted(set(observed_resources) - set(expected_resources))
            if missing:
                reasons.append("MISSING_RESOURCES:" + ",".join(missing))
            if extra:
                reasons.append("UNEXPECTED_RESOURCES:" + ",".join(extra))
        for resource_id in sorted(set(expected_resources) & set(observed_resources)):
            if observed_resources[resource_id] != expected_resources[resource_id]:
                reasons.append(f"RESOURCE_HASH_MISMATCH:{resource_id}")
        disposition = "PASS" if not reasons else "HOLD"

    if reasons and disposition == "PASS":
        disposition = "HOLD"
    if disposition not in ALLOWED_DISPOSITIONS:
        raise ConformanceError("INTERNAL_INVALID_DISPOSITION")
    return {
        "observation_id": observation["observation_id"],
        "client_id": observation["client_id"],
        "run_id": observation["run_id"],
        "case": observation["case"],
        "disposition": disposition,
        "reasons": reasons,
        "evidence_sha256": canonical_sha256(observation),
    }


def _clean_signature(observation: Mapping[str, Any]) -> str:
    stable = {
        "server_build": observation["server_build"],
        "fixture_sha256": observation["fixture_sha256"],
        "requested_protocol_version": observation["requested_protocol_version"],
        "negotiated_protocol_version": observation["negotiated_protocol_version"],
        "negotiation_status": observation["negotiation_status"],
        "listing_status": observation["listing_status"],
        "listed_tools": sorted(observation["listed_tools"]),
        "resource_hashes": {k: observation["resource_hashes"][k] for k in sorted(observation["resource_hashes"])},
        "production_action_count": observation["production_action_count"],
    }
    return canonical_sha256(stable)


def evaluate(manifest: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    manifest = validate_manifest(manifest)
    if not isinstance(observations, list):
        raise ConformanceError("OBSERVATIONS_LIST_REQUIRED")

    unique: Dict[str, Tuple[str, Mapping[str, Any]]] = {}
    duplicate_collapses = 0
    for observation in observations:
        _validate_observation_shape(observation)
        observation_id = observation["observation_id"]
        digest = canonical_sha256(observation)
        prior = unique.get(observation_id)
        if prior:
            if prior[0] != digest:
                raise ConformanceError(f"OBSERVATION_ID_CONFLICT:{observation_id}")
            duplicate_collapses += 1
            continue
        unique[observation_id] = (digest, observation)

    assessments: List[Dict[str, Any]] = []
    clean_by_client: Dict[str, List[Mapping[str, Any]]] = {c: [] for c in manifest["clients"]}
    hostile_seen: Dict[str, List[Dict[str, Any]]] = {name: [] for name in manifest["hostile_expectations"]}
    global_reasons: List[str] = []

    for _, observation in [unique[k] for k in sorted(unique)]:
        assessment = assess_observation(manifest, observation)
        assessments.append(assessment)
        for reason in assessment["reasons"]:
            if reason in EVIDENCE_BINDING_FAILURES:
                global_reasons.append(
                    f"EVIDENCE_BINDING_FAILURE:{assessment['observation_id']}:{reason}"
                )
        if observation["case"] == "clean" and observation["client_id"] in clean_by_client:
            clean_by_client[observation["client_id"]].append(observation)
        elif observation["case"] in hostile_seen:
            hostile_seen[observation["case"]].append(assessment)
        elif observation["case"] != "clean":
            global_reasons.append(f"UNKNOWN_CASE:{observation['case']}")

    for client in manifest["clients"]:
        rows = clean_by_client[client]
        if len(rows) != manifest["clean_runs_per_client"]:
            global_reasons.append(f"CLEAN_RUN_COUNT:{client}:{len(rows)}!={manifest['clean_runs_per_client']}")
            continue
        row_assessments = {a["observation_id"]: a for a in assessments}
        if any(row_assessments[row["observation_id"]]["disposition"] != "PASS" for row in rows):
            global_reasons.append(f"CLEAN_RUN_NOT_PASS:{client}")
        signatures = {_clean_signature(row) for row in rows}
        if len(signatures) != 1:
            global_reasons.append(f"CLEAN_REPLAY_DRIFT:{client}")

    for case, expected in sorted(manifest["hostile_expectations"].items()):
        rows = hostile_seen[case]
        if not rows:
            global_reasons.append(f"MISSING_HOSTILE_CASE:{case}")
            continue
        if any(row["disposition"] != expected for row in rows):
            got = ",".join(sorted({row["disposition"] for row in rows}))
            global_reasons.append(f"HOSTILE_DISPOSITION:{case}:{got}!={expected}")

    if any(a["disposition"] != "PASS" for a in assessments if a["case"] == "clean"):
        global_reasons.append("CLEAN_ASSESSMENT_FAILURE")
    if any("PRODUCTION_ACTION_OBSERVED" in a["reasons"] for a in assessments):
        global_reasons.append("PRODUCTION_ACTION_BOUNDARY_VIOLATED")

    report_core = {
        "schema": REPORT_SCHEMA,
        "manifest_sha256": canonical_sha256(manifest),
        "server_build": manifest["server_build"],
        "fixture_id": manifest["fixture"]["id"],
        "client_count": len(manifest["clients"]),
        "unique_observation_count": len(unique),
        "duplicate_collapses": duplicate_collapses,
        "assessments": sorted(assessments, key=lambda a: (a["client_id"], a["case"], a["run_id"], a["observation_id"])),
        "global_reasons": sorted(set(global_reasons)),
    }
    report_core["overall"] = "PASS" if not report_core["global_reasons"] else "HOLD"
    receipt = canonical_sha256(report_core)
    report = dict(report_core)
    report["receipt_sha256"] = receipt
    return report


def verify_report(report: Mapping[str, Any]) -> bool:
    if not isinstance(report, dict):
        return False
    receipt = report.get("receipt_sha256")
    if not isinstance(receipt, str):
        return False
    core = dict(report)
    core.pop("receipt_sha256", None)
    try:
        return canonical_sha256(core) == receipt
    except ConformanceError:
        return False


def evaluate_text(manifest_text: str, observations_text: str) -> Dict[str, Any]:
    return evaluate(loads_strict(manifest_text), loads_strict(observations_text))
