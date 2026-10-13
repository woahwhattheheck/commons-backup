#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

from .router import (
    MUSE_DM_ID,
    RouterError,
    _CHANNELS,
    _NON_DEFAULT_PRIMARY,
    _ROUTES,
    channel_registry,
    loads_strict,
)

CENSUS_SCHEMA: Final = "swarm-slack-channel-census/v1"
AUDIT_SCHEMA: Final = "swarm-work-channel-drift-audit/v1"
EXPECTATION_SCHEMA: Final = "swarm-work-channel-expectation/v1"
_MAX_CHANNELS: Final = 1000
_CENSUS_KEYS: Final = frozenset({"schema", "generation", "source", "channels"})
_ROW_KEYS: Final = frozenset({"id", "name", "archived", "is_member", "conversation_type"})
_CONVERSATION_TYPES: Final = frozenset({"public_channel", "private_channel", "im", "mpim"})
_CHANNEL_ID_RE: Final = re.compile(r"^[CDG][A-Z0-9]+$")
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class DriftError(ValueError):
    pass


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_obj(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _text(name: str, value: Any, max_len: int) -> str:
    if type(value) is not str:
        raise DriftError(f"{name} must be a string")
    value = value.strip()
    if not value or len(value) > max_len or "\x00" in value:
        raise DriftError(f"{name} must be non-empty, <= {max_len} chars, and contain no NUL")
    return value


def validate_census(raw: dict[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict:
        raise DriftError("census must be an object")
    if set(raw) != _CENSUS_KEYS:
        raise DriftError(
            f"census keys mismatch; missing={sorted(_CENSUS_KEYS - set(raw))} "
            f"unknown={sorted(set(raw) - _CENSUS_KEYS)}"
        )
    if raw["schema"] != CENSUS_SCHEMA:
        raise DriftError(f"schema must be {CENSUS_SCHEMA}")
    generation = _text("generation", raw["generation"], 160)
    source = _text("source", raw["source"], 200)
    rows = raw["channels"]
    if type(rows) is not list or len(rows) > _MAX_CHANNELS:
        raise DriftError(f"channels must be a list of at most {_MAX_CHANNELS} rows")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if type(row) is not dict or set(row) != _ROW_KEYS:
            raise DriftError(f"channels[{index}] must contain exactly {sorted(_ROW_KEYS)}")
        channel_id = _text(f"channels[{index}].id", row["id"], 32)
        if not _CHANNEL_ID_RE.fullmatch(channel_id):
            raise DriftError(f"channels[{index}].id is not a supported Slack conversation ID")
        name = _text(f"channels[{index}].name", row["name"], 120)
        if type(row["archived"]) is not bool or type(row["is_member"]) is not bool:
            raise DriftError(f"channels[{index}] archived/is_member must be boolean")
        conversation_type = _text(f"channels[{index}].conversation_type", row["conversation_type"], 32)
        if conversation_type not in _CONVERSATION_TYPES:
            raise DriftError(f"channels[{index}].conversation_type is unsupported")
        normalized.append({
            "id": channel_id,
            "name": name,
            "archived": row["archived"],
            "is_member": row["is_member"],
            "conversation_type": conversation_type,
        })
    normalized.sort(key=lambda row: (row["id"], row["name"].casefold(), row["archived"], row["is_member"], row["conversation_type"]))
    return {"schema": CENSUS_SCHEMA, "generation": generation, "source": source, "channels": normalized}


def loads_census_strict(text: str) -> dict[str, Any]:
    try:
        raw = loads_strict(text)
    except RouterError as exc:
        raise DriftError(str(exc)) from exc
    return validate_census(raw)


def expected_snapshot() -> dict[str, Any]:
    registry = channel_registry()
    routes = []
    for kind in sorted(_ROUTES):
        primary, mirrors = _ROUTES[kind]
        routes.append({"kind": kind, "primary": primary, "mirrors": list(mirrors)})
    return {
        "schema": EXPECTATION_SCHEMA,
        "channels": registry["channels"],
        "routes": routes,
        "scratch_channel_key": "todo",
        "coordination_channel_key": "coordination",
        "muse_dm_id": MUSE_DM_ID,
        "non_default_primary": sorted(_NON_DEFAULT_PRIMARY),
    }


def _finding(severity: str, code: str, subject: str, detail: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "subject": subject, "detail": detail}


def _live_unique(rows_by_id: dict[str, list[dict[str, Any]]], channel_id: str) -> bool:
    rows = rows_by_id.get(channel_id, [])
    return len(rows) == 1 and not rows[0]["archived"] and rows[0]["is_member"]


def compile_audit(raw_census: dict[str, Any]) -> dict[str, Any]:
    census = validate_census(raw_census)
    findings: list[dict[str, str]] = []
    rows_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in census["channels"]:
        rows_by_id[row["id"]].append(row)
        rows_by_name[row["name"].casefold()].append(row)

    for channel_id, rows in sorted(rows_by_id.items()):
        if len(rows) > 1:
            findings.append(_finding("HOLD", "DUPLICATE_OBSERVED_ID", channel_id, f"census contains {len(rows)} rows for one conversation ID"))
    for folded_name, rows in sorted(rows_by_name.items()):
        unique_ids = sorted({row["id"] for row in rows})
        if len(unique_ids) > 1:
            findings.append(_finding("REVIEW", "DUPLICATE_OBSERVED_NAME", folded_name, f"name resolves to {len(unique_ids)} conversation IDs: {','.join(unique_ids)}"))

    expected_id_owner: dict[str, str] = {}
    expected_name_owner: dict[str, str] = {}
    for key, (channel_id, name) in sorted(_CHANNELS.items()):
        if channel_id in expected_id_owner:
            findings.append(_finding("HOLD", "DUPLICATE_EXPECTED_ID", channel_id, f"registry keys {expected_id_owner[channel_id]} and {key} share one ID"))
        else:
            expected_id_owner[channel_id] = key
        folded = name.casefold()
        if folded in expected_name_owner:
            findings.append(_finding("HOLD", "DUPLICATE_EXPECTED_NAME", name, f"registry keys {expected_name_owner[folded]} and {key} share one name"))
        else:
            expected_name_owner[folded] = key

        observed = rows_by_id.get(channel_id, [])
        if not observed:
            findings.append(_finding("HOLD", "MISSING_EXPECTED_CHANNEL", key, f"expected {channel_id} #{name} is absent from census"))
            continue
        if len(observed) != 1:
            continue
        row = observed[0]
        if row["archived"]:
            findings.append(_finding("HOLD", "ARCHIVED_EXPECTED_CHANNEL", key, f"{channel_id} #{name} is archived"))
        if not row["is_member"]:
            findings.append(_finding("HOLD", "INACCESSIBLE_EXPECTED_CHANNEL", key, f"census marks {channel_id} #{name} is_member=false"))
        if row["name"] != name:
            findings.append(_finding("REVIEW", "RENAMED_EXPECTED_CHANNEL", key, f"expected #{name}; observed #{row['name']} for {channel_id}"))

    muse_rows = rows_by_id.get(MUSE_DM_ID, [])
    if not muse_rows:
        findings.append(_finding("HOLD", "MISSING_MUSE_DM", "muse", f"required Muse DM {MUSE_DM_ID} is absent from census"))
    elif len(muse_rows) == 1:
        muse = muse_rows[0]
        if muse["archived"] or not muse["is_member"] or muse["conversation_type"] != "im":
            findings.append(_finding("HOLD", "MUSE_DM_UNAVAILABLE", "muse", f"{MUSE_DM_ID} must be an active member-visible im conversation"))

    required_non_default = {"delegations", "awaiting-merge"}
    if set(_NON_DEFAULT_PRIMARY) != required_non_default:
        findings.append(_finding("HOLD", "NON_DEFAULT_PRIMARY_POLICY_DRIFT", "router-policy", f"expected {sorted(required_non_default)}; configured {sorted(_NON_DEFAULT_PRIMARY)}"))

    coverage: list[dict[str, Any]] = []
    for kind in sorted(_ROUTES):
        primary, mirrors = _ROUTES[kind]
        targets = [("primary", primary)] + [("mirror", name) for name in mirrors]
        if primary in _NON_DEFAULT_PRIMARY and not (kind == "merge_review" and primary == "awaiting-merge"):
            findings.append(_finding("HOLD", "CENTRAL_QUEUE_PRIMARY_VIOLATION", kind, f"{primary} is configured as a primary outside merge_review"))
        if kind == "merge_review" and primary != "awaiting-merge":
            findings.append(_finding("HOLD", "MERGE_REVIEW_PRIMARY_DRIFT", kind, f"merge_review primary is {primary}, expected awaiting-merge"))
        for role, key in targets:
            if key not in _CHANNELS:
                findings.append(_finding("HOLD", "UNKNOWN_ROUTE_TARGET", f"{kind}:{role}", f"route target key {key} is absent from registry"))
                coverage.append({"kind": kind, "role": role, "key": key, "id": None, "resolved": False})
                continue
            channel_id = _CHANNELS[key][0]
            resolved = _live_unique(rows_by_id, channel_id)
            coverage.append({"kind": kind, "role": role, "key": key, "id": channel_id, "resolved": resolved})

    scratch_id = _CHANNELS.get("todo", (None, None))[0]
    if scratch_id is None:
        findings.append(_finding("HOLD", "MISSING_SCRATCH_REGISTRY_KEY", "todo", "todo scratch key is absent from registry"))
        coverage.append({"kind": "__scratch__", "role": "scratch", "key": "todo", "id": None, "resolved": False})
    else:
        coverage.append({"kind": "__scratch__", "role": "scratch", "key": "todo", "id": scratch_id, "resolved": _live_unique(rows_by_id, scratch_id)})

    findings.sort(key=lambda row: (row["severity"], row["code"], row["subject"], row["detail"]))
    if any(row["severity"] == "HOLD" for row in findings):
        state = "HOLD"
    elif any(row["severity"] == "REVIEW" for row in findings):
        state = "REVIEW"
    else:
        state = "PASS"
    coverage.sort(key=lambda row: (row["kind"], row["role"], row["key"], row["id"] or ""))
    expected = expected_snapshot()
    receipt: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "generation": census["generation"],
        "source": census["source"],
        "state": state,
        "findings": findings,
        "route_coverage": coverage,
        "counts": {
            "observed_channels": len(census["channels"]),
            "expected_channels": len(_CHANNELS),
            "resolved_route_targets": sum(1 for row in coverage if row["resolved"]),
            "route_targets": len(coverage),
            "holds": sum(1 for row in findings if row["severity"] == "HOLD"),
            "reviews": sum(1 for row in findings if row["severity"] == "REVIEW"),
        },
        "census_sha256": _sha256_obj(census),
        "expected_sha256": _sha256_obj(expected),
        "side_effects_authorized": False,
    }
    receipt["receipt_sha256"] = _sha256_obj(receipt)
    return receipt


def verify_audit_receipt(receipt: dict[str, Any]) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != AUDIT_SCHEMA:
        return False
    digest = receipt.get("receipt_sha256")
    if type(digest) is not str or not _DIGEST_RE.fullmatch(digest):
        return False
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if _sha256_obj(body) != digest or receipt.get("side_effects_authorized") is not False:
        return False
    findings = receipt.get("findings")
    if type(findings) is not list or any(type(row) is not dict for row in findings):
        return False
    if any(set(row) != {"severity", "code", "subject", "detail"} for row in findings):
        return False
    if any(row["severity"] not in {"HOLD", "REVIEW"} for row in findings):
        return False
    expected_state = "HOLD" if any(row["severity"] == "HOLD" for row in findings) else ("REVIEW" if findings else "PASS")
    if receipt.get("state") != expected_state:
        return False
    expected_sort = sorted(findings, key=lambda row: (row["severity"], row["code"], row["subject"], row["detail"]))
    if findings != expected_sort:
        return False
    counts = receipt.get("counts")
    if type(counts) is not dict:
        return False
    if counts.get("holds") != sum(1 for row in findings if row["severity"] == "HOLD"):
        return False
    if counts.get("reviews") != sum(1 for row in findings if row["severity"] == "REVIEW"):
        return False
    coverage = receipt.get("route_coverage")
    if type(coverage) is not list:
        return False
    if counts.get("route_targets") != len(coverage):
        return False
    if counts.get("resolved_route_targets") != sum(1 for row in coverage if type(row) is dict and row.get("resolved") is True):
        return False
    for key in ("census_sha256", "expected_sha256"):
        value = receipt.get(key)
        if type(value) is not str or not _DIGEST_RE.fullmatch(value):
            return False
    return True


def render_markdown(receipt: dict[str, Any]) -> str:
    if not verify_audit_receipt(receipt):
        raise DriftError("cannot render invalid audit receipt")
    counts = receipt["counts"]
    lines = [
        "# Swarm channel registry drift audit",
        "",
        f"- State: **{receipt['state']}**",
        f"- Generation: `{receipt['generation']}`",
        f"- Source: `{receipt['source']}`",
        f"- Observed/expected channels: {counts['observed_channels']}/{counts['expected_channels']}",
        f"- Route targets resolved: {counts['resolved_route_targets']}/{counts['route_targets']}",
        f"- Findings: {counts['holds']} HOLD, {counts['reviews']} REVIEW",
        f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
        "- Side effects authorized: **false**",
        "",
        "## Findings",
        "",
    ]
    if not receipt["findings"]:
        lines.append("No drift findings.")
    else:
        lines.extend(["|Severity|Code|Subject|Detail|", "|---|---|---|---|"])
        for row in receipt["findings"]:
            values = [row["severity"], row["code"], row["subject"], row["detail"]]
            escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("|" + "|".join(escaped) + "|")
    lines.append("")
    return "\n".join(lines)


def _read(path: str) -> dict[str, Any]:
    return loads_census_strict(Path(path).read_text(encoding="utf-8"))


def _emit_json(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Swarm specialist-channel registry drift")
    sub = parser.add_subparsers(dest="command", required=True)
    p_audit = sub.add_parser("audit")
    p_audit.add_argument("census")
    p_audit.add_argument("--format", choices=("json", "markdown"), default="json")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("receipt")
    sub.add_parser("expected")
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            receipt = compile_audit(_read(args.census))
            if args.format == "markdown":
                sys.stdout.write(render_markdown(receipt))
            else:
                _emit_json(receipt)
        elif args.command == "verify":
            raw = loads_strict(Path(args.receipt).read_text(encoding="utf-8"))
            if not verify_audit_receipt(raw):
                raise DriftError("audit receipt verification failed")
            _emit_json({"schema": "swarm-work-channel-drift-verification/v1", "valid": True, "receipt_sha256": raw["receipt_sha256"]})
        else:
            _emit_json(expected_snapshot())
    except (OSError, RouterError, DriftError) as exc:
        sys.stderr.write(f"swarm-channel-drift: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
