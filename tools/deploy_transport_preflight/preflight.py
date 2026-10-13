#!/usr/bin/env python3
"""Deterministic source-binding preflight for deployment transport actions.

This module is intentionally planning-only.  It can prove that a declared action
surface has a machine-readable path capable of carrying the requested immutable
source identity, but it cannot authenticate a provider, authorize a deployment,
or prove that a deployment actually happened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

REQUEST_SCHEMA = "deploy-transport-request.v1"
MANIFEST_SCHEMA = "deploy-transport-capability-manifest.v1"
BINDING_SCHEMA = "deploy-project-binding.v1"
REPORT_SCHEMA = "deploy-transport-preflight-report.v1"

READY = "READY_SOURCE_BOUND_PATH"
HOLD_UNBOUND = "HOLD_SOURCE_UNBOUND"
HOLD_AMBIGUOUS = "HOLD_AMBIGUOUS_CAPABILITY"

MAX_INPUT_BYTES = 256_000
MAX_ACTIONS = 64
MAX_STRING = 2048
MAX_INT_ABS = 9_007_199_254_740_991
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 50_000

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ACTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")

KNOWN_KINDS = {
    "CREATE_PROJECT",
    "DEPLOY_EXISTING_PROJECT",
    "DEPLOY_CURRENT_PROJECT",
    "DEPLOY_REPO",
    "DEPLOY_REPO_SUBDIR",
    "DEPLOY_ARTIFACT",
    "DEPLOY_FILE_BUNDLE",
    "DEPLOY_SOURCE_GENERATION",
}
KNOWN_BINDINGS = {
    "none",
    "existing_project_binding",
    "repo_commit",
    "repo_commit_subdir",
    "artifact_sha256",
    "file_bundle_sha256",
    "source_generation_id",
}
EXPECTED_BINDING_BY_KIND = {
    "CREATE_PROJECT": "none",
    "DEPLOY_EXISTING_PROJECT": "existing_project_binding",
    "DEPLOY_CURRENT_PROJECT": "existing_project_binding",
    "DEPLOY_REPO": "repo_commit",
    "DEPLOY_REPO_SUBDIR": "repo_commit_subdir",
    "DEPLOY_ARTIFACT": "artifact_sha256",
    "DEPLOY_FILE_BUNDLE": "file_bundle_sha256",
    "DEPLOY_SOURCE_GENERATION": "source_generation_id",
}

EXTERNAL_AUTHORITY_FALSE = {
    "provider_authenticated": False,
    "project_create_authorized": False,
    "deploy_authorized": False,
    "public_url_proven": False,
    "competition_submission_authorized": False,
    "payment_or_revenue_proven": False,
}


class DomainError(ValueError):
    """Stable, user-facing domain error without traceback semantics."""


def _reject_constant(value: str) -> None:
    raise DomainError(f"nonfinite JSON constant rejected: {value}")


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 16:
        raise DomainError("integer token exceeds safe bound")
    value = int(token)
    if abs(value) > MAX_INT_ABS:
        raise DomainError("integer exceeds safe bound")
    return value


def _reject_float(token: str) -> None:
    raise DomainError(f"floating-point JSON rejected: {token}")


def _object_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DomainError(f"duplicate JSON key rejected: {key}")
        out[key] = value
    return out


def _preflight_json_depth(text: str) -> None:
    """Reject excessive raw structural depth before CPython's recursive decoder."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise DomainError("JSON depth limit exceeded")
        elif ch in "]}":
            depth -= 1
            if depth < 0:
                # Let the decoder provide the ordinary syntax failure.
                return


def _validate_json_structure(value: Any) -> None:
    """Iteratively bound direct-object depth/work before recursive serialization."""
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise DomainError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise DomainError("JSON depth limit exceeded")

        item_type = type(item)
        if item_type is float:
            raise DomainError("floating-point JSON rejected")
        if item is None or item_type in {bool, int, str}:
            if item_type is int and abs(item) > MAX_INT_ABS:
                raise DomainError("integer exceeds safe bound")
            if item_type is str:
                try:
                    item.encode("utf-8", "strict")
                except UnicodeEncodeError as exc:
                    raise DomainError("value is not strict UTF-8") from exc
            continue
        if item_type is list:
            remaining = MAX_JSON_NODES - nodes
            if len(item) > remaining:
                raise DomainError("JSON node limit exceeded")
            for child in reversed(item):
                stack.append((child, depth + 1))
            continue
        if item_type is dict:
            remaining = MAX_JSON_NODES - nodes
            if len(item) > remaining // 2:
                raise DomainError("JSON node limit exceeded")
            for key in reversed(item):
                if type(key) is not str:
                    raise DomainError("JSON object keys must be exact strings")
                stack.append((item[key], depth + 1))
                stack.append((key, depth + 1))
            continue
        raise DomainError("value contains non-JSON type")


def strict_loads(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise DomainError("input must be exact bytes")
    if len(raw) > MAX_INPUT_BYTES:
        raise DomainError("input exceeds byte bound")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise DomainError("input is not strict UTF-8") from exc
    _preflight_json_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except DomainError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise DomainError("invalid JSON") from exc
    _validate_json_structure(value)
    # Canonical encoding is also our lone-surrogate / unsafe-string fence.
    canonical_bytes(value)
    return value


def canonical_bytes(value: Any) -> bytes:
    _validate_json_structure(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise DomainError("value is not canonical strict JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact_keys(obj: Any, allowed: set[str], required: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise DomainError(f"{where} must be an object")
    keys = set(obj)
    unknown = keys - allowed
    missing = required - keys
    if unknown:
        raise DomainError(f"{where} has unknown keys: {','.join(sorted(unknown))}")
    if missing:
        raise DomainError(f"{where} missing keys: {','.join(sorted(missing))}")
    return obj


def _string(value: Any, where: str, *, max_len: int = MAX_STRING) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise DomainError(f"{where} must be a nonempty bounded string")
    # Strict UTF-8 and surrogate check.
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise DomainError(f"{where} is not strict UTF-8") from exc
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DomainError(f"{where} contains control characters")
    return value


def _optional_string(value: Any, where: str, *, max_len: int = MAX_STRING) -> str | None:
    if value is None:
        return None
    return _string(value, where, max_len=max_len)


def _bounded_int(value: Any, where: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or abs(value) > MAX_INT_ABS:
        raise DomainError(f"{where} must be a bounded integer >= {minimum}")
    return value


def _provider(value: Any, where: str = "provider") -> str:
    value = _string(value, where, max_len=64)
    if not _PROVIDER_RE.fullmatch(value):
        raise DomainError(f"{where} has invalid provider identifier")
    return value


def _opaque_id(value: Any, where: str) -> str:
    value = _string(value, where, max_len=256)
    if not _ID_RE.fullmatch(value):
        raise DomainError(f"{where} has invalid identifier")
    return value


def _safe_subdir(value: Any, where: str) -> str:
    value = _string(value, where, max_len=512)
    if value.startswith(("/", "\\")) or "\\" in value:
        raise DomainError(f"{where} must be a relative forward-slash path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DomainError(f"{where} contains unsafe path segments")
    return value


def _canonical_repo_url(value: Any, where: str) -> str:
    value = _string(value, where, max_len=1024)
    try:
        split = urlsplit(value)
        # URL parsing defers malformed/out-of-range port errors to this property.
        port = split.port
    except ValueError as exc:
        raise DomainError(f"{where} contains invalid URL components") from exc
    if split.scheme != "https" or not split.hostname:
        raise DomainError(f"{where} must be canonical https URL")
    if split.username is not None or split.password is not None or port is not None:
        raise DomainError(f"{where} cannot contain userinfo or explicit port")
    if split.query or split.fragment:
        raise DomainError(f"{where} cannot contain query or fragment")
    if split.path in {"", "/"} or split.path.endswith("/") or "//" in split.path:
        raise DomainError(f"{where} has noncanonical path")
    parts = split.path.split("/")[1:]
    if any(part in {"", ".", ".."} for part in parts):
        raise DomainError(f"{where} has unsafe path segments")
    host = split.hostname.lower()
    canonical = f"https://{host}{split.path}"
    if canonical != value:
        raise DomainError(f"{where} must already be canonical")
    return value


def _source(value: Any, where: str) -> dict[str, Any]:
    obj = _exact_keys(
        value,
        {
            "repo",
            "commit_sha",
            "branch",
            "artifact_sha256",
            "file_bundle_sha256",
            "source_generation_id",
            "subdir",
        },
        set(),
        where,
    )
    out: dict[str, Any] = {}
    if "repo" in obj:
        out["repo"] = _canonical_repo_url(obj["repo"], f"{where}.repo")
    if "commit_sha" in obj:
        sha = _string(obj["commit_sha"], f"{where}.commit_sha", max_len=40)
        if not _SHA40_RE.fullmatch(sha):
            raise DomainError(f"{where}.commit_sha must be lowercase 40-hex")
        if "repo" not in out:
            raise DomainError(f"{where}.commit_sha requires repo")
        out["commit_sha"] = sha
    if "branch" in obj:
        out["branch"] = _opaque_id(obj["branch"], f"{where}.branch")
    if "artifact_sha256" in obj:
        sha = _string(obj["artifact_sha256"], f"{where}.artifact_sha256", max_len=64)
        if not _SHA64_RE.fullmatch(sha):
            raise DomainError(f"{where}.artifact_sha256 must be lowercase 64-hex")
        out["artifact_sha256"] = sha
    if "file_bundle_sha256" in obj:
        sha = _string(obj["file_bundle_sha256"], f"{where}.file_bundle_sha256", max_len=64)
        if not _SHA64_RE.fullmatch(sha):
            raise DomainError(f"{where}.file_bundle_sha256 must be lowercase 64-hex")
        out["file_bundle_sha256"] = sha
    if "source_generation_id" in obj:
        out["source_generation_id"] = _opaque_id(
            obj["source_generation_id"], f"{where}.source_generation_id"
        )
    if "subdir" in obj:
        out["subdir"] = _safe_subdir(obj["subdir"], f"{where}.subdir")
    if not out:
        raise DomainError(f"{where} must contain at least one source locator")
    families = _immutable_families(out)
    if len(families) > 1:
        raise DomainError(f"{where} contains multiple independent immutable source identities")
    if "subdir" in out and families and families != ["repo_commit"]:
        raise DomainError(f"{where}.subdir is only valid with repo+commit source identity")
    return out


def _immutable_families(source: dict[str, Any]) -> list[str]:
    families: list[str] = []
    if "repo" in source and "commit_sha" in source:
        families.append("repo_commit")
    for key in ("artifact_sha256", "file_bundle_sha256", "source_generation_id"):
        if key in source:
            families.append(key)
    return families


def _immutable_identity(source: dict[str, Any]) -> dict[str, Any]:
    families = _immutable_families(source)
    if len(families) != 1:
        return {}
    family = families[0]
    if family == "repo_commit":
        identity = {"repo": source["repo"], "commit_sha": source["commit_sha"]}
        if "subdir" in source:
            identity["subdir"] = source["subdir"]
        return identity
    return {family: source[family]}


def _request(value: Any) -> dict[str, Any]:
    obj = _exact_keys(
        value,
        {"schema", "provider", "source", "target", "manifest_policy"},
        {"schema", "provider", "source", "target"},
        "request",
    )
    if obj["schema"] != REQUEST_SCHEMA:
        raise DomainError("request schema mismatch")
    target = _exact_keys(obj["target"], {"project_id"}, {"project_id"}, "request.target")
    project_id = _optional_string(target["project_id"], "request.target.project_id", max_len=256)
    if project_id is not None:
        project_id = _opaque_id(project_id, "request.target.project_id")
    result = {
        "schema": REQUEST_SCHEMA,
        "provider": _provider(obj["provider"], "request.provider"),
        "source": _source(obj["source"], "request.source"),
        "target": {"project_id": project_id},
    }
    if "manifest_policy" in obj:
        policy = _exact_keys(
            obj["manifest_policy"],
            {"evaluation_epoch", "max_age_seconds"},
            {"evaluation_epoch", "max_age_seconds"},
            "request.manifest_policy",
        )
        result["manifest_policy"] = {
            "evaluation_epoch": _bounded_int(policy["evaluation_epoch"], "request.manifest_policy.evaluation_epoch"),
            "max_age_seconds": _bounded_int(policy["max_age_seconds"], "request.manifest_policy.max_age_seconds"),
        }
    return result


def _manifest(value: Any) -> dict[str, Any]:
    obj = _exact_keys(
        value,
        {"schema", "provider", "actions", "captured_at_epoch"},
        {"schema", "provider", "actions"},
        "manifest",
    )
    if obj["schema"] != MANIFEST_SCHEMA:
        raise DomainError("manifest schema mismatch")
    actions = obj["actions"]
    if type(actions) is not list or not actions or len(actions) > MAX_ACTIONS:
        raise DomainError("manifest.actions must be a nonempty bounded array")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for idx, raw in enumerate(actions):
        item = _exact_keys(raw, {"name", "kind", "source_binding"}, {"name", "kind", "source_binding"}, f"manifest.actions[{idx}]")
        name = _string(item["name"], f"manifest.actions[{idx}].name", max_len=128)
        if not _ACTION_RE.fullmatch(name):
            raise DomainError(f"manifest.actions[{idx}].name invalid")
        if name in seen:
            raise DomainError("manifest action names must be unique")
        seen.add(name)
        kind = _string(item["kind"], f"manifest.actions[{idx}].kind", max_len=64)
        binding = _string(item["source_binding"], f"manifest.actions[{idx}].source_binding", max_len=64)
        normalized.append({"name": name, "kind": kind, "source_binding": binding})
    result = {
        "schema": MANIFEST_SCHEMA,
        "provider": _provider(obj["provider"], "manifest.provider"),
        "actions": normalized,
    }
    if "captured_at_epoch" in obj:
        result["captured_at_epoch"] = _bounded_int(obj["captured_at_epoch"], "manifest.captured_at_epoch")
    return result


def _binding(value: Any) -> dict[str, Any]:
    obj = _exact_keys(value, {"schema", "provider", "project_id", "source"}, {"schema", "provider", "project_id", "source"}, "binding")
    if obj["schema"] != BINDING_SCHEMA:
        raise DomainError("binding schema mismatch")
    source = _source(obj["source"], "binding.source")
    if not _immutable_identity(source):
        raise DomainError("binding.source must contain an immutable source identity")
    return {
        "schema": BINDING_SCHEMA,
        "provider": _provider(obj["provider"], "binding.provider"),
        "project_id": _opaque_id(obj["project_id"], "binding.project_id"),
        "source": source,
    }


def _action_semantics(action: dict[str, str]) -> tuple[bool, str | None]:
    kind = action["kind"]
    binding = action["source_binding"]
    if kind not in KNOWN_KINDS:
        return False, "UNKNOWN_ACTION_KIND"
    if binding not in KNOWN_BINDINGS:
        return False, "UNKNOWN_SOURCE_BINDING"
    if EXPECTED_BINDING_BY_KIND[kind] != binding:
        return False, "CONTRADICTORY_ACTION_BINDING"
    return True, None


def _binding_matches(
    request: dict[str, Any], project_binding: dict[str, Any] | None
) -> tuple[bool, list[str]]:
    if project_binding is None:
        return False, ["PROJECT_BINDING_MISSING"]
    reasons: list[str] = []
    if project_binding["provider"] != request["provider"]:
        reasons.append("PROJECT_BINDING_PROVIDER_MISMATCH")
    project_id = request["target"]["project_id"]
    if project_id is None:
        reasons.append("REQUEST_PROJECT_ID_MISSING")
    elif project_binding["project_id"] != project_id:
        reasons.append("PROJECT_BINDING_PROJECT_MISMATCH")
    req_identity = _immutable_identity(request["source"])
    binding_identity = _immutable_identity(project_binding["source"])
    if req_identity != binding_identity:
        reasons.append("PROJECT_BINDING_SOURCE_MISMATCH")
    return not reasons, reasons


def _action_viable(
    action: dict[str, str], request: dict[str, Any], project_binding: dict[str, Any] | None
) -> tuple[bool, list[str]]:
    binding = action["source_binding"]
    source = request["source"]
    if binding == "none":
        return False, ["ACTION_HAS_NO_SOURCE_BINDING"]
    if binding == "repo_commit":
        if "repo" not in source or "commit_sha" not in source:
            return False, ["REQUEST_REPO_COMMIT_MISSING"]
        if "subdir" in source:
            return False, ["REQUEST_SUBDIR_UNBOUND"]
        return True, []
    if binding == "repo_commit_subdir":
        if "repo" not in source or "commit_sha" not in source:
            return False, ["REQUEST_REPO_COMMIT_MISSING"]
        if "subdir" not in source:
            return False, ["REQUEST_SUBDIR_MISSING"]
        return True, []
    if binding == "artifact_sha256":
        if "artifact_sha256" in source:
            return True, []
        return False, ["REQUEST_ARTIFACT_DIGEST_MISSING"]
    if binding == "file_bundle_sha256":
        if "file_bundle_sha256" in source:
            return True, []
        return False, ["REQUEST_FILE_BUNDLE_DIGEST_MISSING"]
    if binding == "source_generation_id":
        if "source_generation_id" in source:
            return True, []
        return False, ["REQUEST_SOURCE_GENERATION_MISSING"]
    if binding == "existing_project_binding":
        return _binding_matches(request, project_binding)
    return False, ["UNKNOWN_SOURCE_BINDING"]


def compile_values(
    request_value: Any,
    manifest_value: Any,
    binding_value: Any | None = None,
) -> dict[str, Any]:
    _validate_json_structure(request_value)
    _validate_json_structure(manifest_value)
    if binding_value is not None:
        _validate_json_structure(binding_value)
    request = _request(request_value)
    manifest = _manifest(manifest_value)
    project_binding = _binding(binding_value) if binding_value is not None else None

    blockers: set[str] = set()
    viable_paths: list[str] = []
    semantic_ambiguity = False

    if manifest["provider"] != request["provider"]:
        blockers.add("MANIFEST_PROVIDER_MISMATCH")
        semantic_ambiguity = True

    policy = request.get("manifest_policy")
    if policy is not None:
        captured = manifest.get("captured_at_epoch")
        if captured is None:
            blockers.add("MANIFEST_FRESHNESS_UNKNOWN")
            semantic_ambiguity = True
        elif captured > policy["evaluation_epoch"]:
            blockers.add("MANIFEST_CAPTURED_IN_FUTURE")
            semantic_ambiguity = True
        elif policy["evaluation_epoch"] - captured > policy["max_age_seconds"]:
            blockers.add("MANIFEST_STALE")
            semantic_ambiguity = True

    if not _immutable_identity(request["source"]):
        blockers.add("REQUEST_SOURCE_NOT_IMMUTABLE")

    for action in manifest["actions"]:
        valid_semantics, semantic_blocker = _action_semantics(action)
        if not valid_semantics:
            semantic_ambiguity = True
            blockers.add(f"{action['name']}:{semantic_blocker}")
            continue
        viable, reasons = _action_viable(action, request, project_binding)
        if viable:
            viable_paths.append(action["name"])
        else:
            for reason in reasons:
                blockers.add(f"{action['name']}:{reason}")

    viable_paths.sort()
    if semantic_ambiguity:
        status = HOLD_AMBIGUOUS
    elif viable_paths:
        status = READY
    else:
        status = HOLD_UNBOUND

    report_without_receipt: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": status,
        "provider": request["provider"],
        "request_sha256": digest(request),
        "manifest_sha256": digest(manifest),
        "binding_sha256": digest(project_binding) if project_binding is not None else None,
        "source_identity": _immutable_identity(request["source"]),
        "viable_paths": viable_paths,
        "blockers": sorted(blockers),
        "external_authority": {
            "provider_authenticated": False,
            "project_create_authorized": False,
            "deploy_authorized": False,
            "public_url_proven": False,
            "competition_submission_authorized": False,
            "payment_or_revenue_proven": False,
        },
    }
    report = dict(report_without_receipt)
    report["receipt_sha256"] = digest(report_without_receipt)
    return report


def compile_bytes(
    request_raw: bytes,
    manifest_raw: bytes,
    binding_raw: bytes | None = None,
) -> dict[str, Any]:
    request_value = strict_loads(request_raw)
    manifest_value = strict_loads(manifest_raw)
    binding_value = strict_loads(binding_raw) if binding_raw is not None else None
    return compile_values(request_value, manifest_value, binding_value)


def verify_bytes(
    request_raw: bytes,
    manifest_raw: bytes,
    report_raw: bytes,
    binding_raw: bytes | None = None,
) -> dict[str, Any]:
    supplied = strict_loads(report_raw)
    expected = compile_bytes(request_raw, manifest_raw, binding_raw)
    # Canonical byte identity is type-sensitive: JSON false is not integer 0.
    if canonical_bytes(supplied) != canonical_bytes(expected):
        raise DomainError("report does not exactly recompile")
    return expected


def _read(path: str) -> bytes:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise DomainError(f"cannot read input: {path}") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise DomainError("input exceeds byte bound")
    return raw


def _write_exclusive(path: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except (OSError, ValueError) as exc:
        raise DomainError(f"refusing to overwrite output: {path}") from exc
    try:
        with os.fdopen(fd, "wb", closefd=True) as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception as exc:
        try:
            os.unlink(path)
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise DomainError(f"cannot persist output: {path}") from exc
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--request", required=True)
        p.add_argument("--manifest", required=True)
        p.add_argument("--binding")
        if name == "compile":
            p.add_argument("--out", required=True)
        else:
            p.add_argument("--report", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        request_raw = _read(args.request)
        manifest_raw = _read(args.manifest)
        binding_raw = _read(args.binding) if args.binding else None
        if args.command == "compile":
            report = compile_bytes(request_raw, manifest_raw, binding_raw)
            _write_exclusive(args.out, canonical_bytes(report) + b"\n")
            print(f"{report['status']} {report['receipt_sha256']}")
        else:
            report_raw = _read(args.report)
            report = verify_bytes(request_raw, manifest_raw, report_raw, binding_raw)
            print(f"VERIFIED {report['status']} {report['receipt_sha256']}")
        return 0
    except DomainError as exc:
        print(f"deploy-transport-preflight: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
