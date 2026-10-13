#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

SCHEMA: Final = "swarm-work-item/v1"
ROUTE_RECEIPT_SCHEMA: Final = "swarm-work-route-receipt/v1"
SCRATCH_RECEIPT_SCHEMA: Final = "swarm-work-scratch-receipt/v1"
MUSE_DM_ID: Final = "D0C1U7TUZEC"
TODO_CHANNEL: Final = {"id": "C0BU2V38CBC", "name": "todo"}
COORDINATION_CHANNEL: Final = {"id": "C0BU51F1PL3", "name": "coordination-channel-created-today-please-use"}

_CHANNELS: Final[dict[str, tuple[str, str]]] = {
    "awaiting-merge": ("C0BVDR70CE6", "awaiting-merge"),
    "bug-bounty": ("C0BVANHNB26", "bug-bounty"),
    "build-demand": ("C0BTRNE6Y58", "build-demand"),
    "business-packs": ("C0BU7JAPUH3", "business-packs"),
    "coordination": (COORDINATION_CHANNEL["id"], COORDINATION_CHANNEL["name"]),
    "data-science-bounties": ("C0BUY2GT8P9", "data-science-bounties"),
    "delegations": ("C0BTB4SUCP9", "delegations"),
    "email-actionables": ("C0BUYF8S3HV", "email-actionables"),
    "feature-bounties": ("C0C0TQ56F9N", "feature-bounties"),
    "github-inbox": ("C0BVBTVMJ94", "github-inbox"),
    "hive-commerce-builds": ("C0BV6G7Q3L7", "hive-commerce-builds"),
    "hive-media-builds": ("C0C05UU6WKG", "hive-media-builds"),
    "hive-original-builds": ("C0C05UVE0EA", "hive-original-builds"),
    "hive-saas-builds": ("C0C09QN8MQR", "hive-saas-builds"),
    "hot-leads": ("C0C2BE7K0KA", "hot-leads"),
    "integration-bounties": ("C0C01AXLCGZ", "integration-bounties"),
    "international-competitions": ("C0BVDDS04G2", "international-competitions"),
    "leads": ("C0BTURDA3PW", "leads"),
    "math-bounties": ("C0BV7KHRGF7", "math-bounties"),
    "products": ("C0BTA20SU95", "products"),
    "sales": ("C0BTTA66TK3", "sales"),
    "shipped-builds": ("C0BTVA3C0G3", "shipped-builds"),
    "todo": (TODO_CHANNEL["id"], TODO_CHANNEL["name"]),
}

# Central queues are coordination surfaces, not default work destinations.
_NON_DEFAULT_PRIMARY: Final = frozenset({"delegations", "awaiting-merge"})

# (primary, mirrors). awaiting-merge is primary only for exact merge-review work.
_ROUTES: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "build": ("build-demand", ("coordination",)),
    "bug_bounty": ("bug-bounty", ("coordination",)),
    "business_pack": ("business-packs", ("products",)),
    "competition": ("international-competitions", ("coordination",)),
    "coordination": ("coordination", ()),
    "data_science_bounty": ("data-science-bounties", ("international-competitions",)),
    "feature_bounty": ("feature-bounties", ("coordination",)),
    "github_inbox": ("github-inbox", ("coordination",)),
    "hive_commerce": ("hive-commerce-builds", ("products",)),
    "hive_media": ("hive-media-builds", ("products",)),
    "hive_original": ("hive-original-builds", ("products",)),
    "hive_saas": ("hive-saas-builds", ("products",)),
    "integration_bounty": ("integration-bounties", ("coordination",)),
    "lead": ("leads", ("hot-leads", "sales")),
    "math_bounty": ("math-bounties", ("coordination",)),
    "merge_review": ("awaiting-merge", ("github-inbox",)),
    "outbound": ("hot-leads", ("sales", "email-actionables")),
    "product": ("products", ("business-packs",)),
    "shipped": ("shipped-builds", ("github-inbox",)),
}

_ALLOWED_KEYS: Final = frozenset({
    "schema",
    "work_id",
    "kind",
    "target",
    "opportunity",
    "purpose",
    "value_usd",
    "external_publish",
    "route_family",
    "repository",
    "artifact_scope",
})
_REQUIRED_KEYS: Final = _ALLOWED_KEYS
_KIND_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ID_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,159}$")
_ROUTE_FAMILIES: Final = frozenset({
    "none",
    "email",
    "contact_form",
    "direct_message",
    "github_external",
    "provider_submission",
    "public_post",
})


class RouterError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RouterError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> dict[str, Any]:
    try:
        obj = json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    except (json.JSONDecodeError, RouterError) as exc:
        raise RouterError(f"invalid JSON: {exc}") from exc
    if type(obj) is not dict:
        raise RouterError("top-level JSON must be an object")
    return obj


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_obj(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _normalize_identity(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _validate_text(name: str, value: Any, *, max_len: int = 500) -> str:
    if type(value) is not str:
        raise RouterError(f"{name} must be a string")
    value = value.strip()
    if not value or len(value) > max_len or "\x00" in value:
        raise RouterError(f"{name} must be non-empty, <= {max_len} chars, and contain no NUL")
    return value


def validate_work_item(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != _REQUIRED_KEYS:
        missing = sorted(_REQUIRED_KEYS - set(raw))
        unknown = sorted(set(raw) - _ALLOWED_KEYS)
        raise RouterError(f"work-item keys mismatch; missing={missing} unknown={unknown}")
    if raw["schema"] != SCHEMA:
        raise RouterError(f"schema must be {SCHEMA}")
    work_id = _validate_text("work_id", raw["work_id"], max_len=160)
    if not _ID_RE.fullmatch(work_id):
        raise RouterError("work_id contains unsupported characters")
    kind = _validate_text("kind", raw["kind"], max_len=64)
    if not _KIND_RE.fullmatch(kind):
        raise RouterError("kind must be lowercase snake_case")
    target = _validate_text("target", raw["target"])
    opportunity = _validate_text("opportunity", raw["opportunity"])
    purpose = _validate_text("purpose", raw["purpose"])
    repository = _validate_text("repository", raw["repository"], max_len=200)
    artifact_scope = _validate_text("artifact_scope", raw["artifact_scope"], max_len=500)
    if type(raw["value_usd"]) is not int or raw["value_usd"] < 0 or raw["value_usd"] > 10**12:
        raise RouterError("value_usd must be an integer in [0, 1e12]")
    if type(raw["external_publish"]) is not bool:
        raise RouterError("external_publish must be boolean")
    route_family = _validate_text("route_family", raw["route_family"], max_len=32)
    if route_family not in _ROUTE_FAMILIES:
        raise RouterError(f"unsupported route_family: {route_family}")
    if raw["external_publish"] and route_family == "none":
        raise RouterError("external_publish=true requires a non-none route_family")
    if not raw["external_publish"] and route_family != "none":
        raise RouterError("non-none route_family requires external_publish=true")
    return {
        "schema": SCHEMA,
        "work_id": work_id,
        "kind": kind,
        "target": target,
        "opportunity": opportunity,
        "purpose": purpose,
        "value_usd": raw["value_usd"],
        "external_publish": raw["external_publish"],
        "route_family": route_family,
        "repository": repository,
        "artifact_scope": artifact_scope,
    }


def publication_key(item: dict[str, Any]) -> str:
    # Transport is deliberately excluded: same target/opportunity/purpose collides
    # across email, form, DM, or other publication routes.
    identity = {
        "target": _normalize_identity(item["target"]),
        "opportunity": _normalize_identity(item["opportunity"]),
        "purpose": _normalize_identity(item["purpose"]),
    }
    return _sha256_obj(identity)


def _channel(name: str) -> dict[str, str]:
    channel_id, channel_name = _CHANNELS[name]
    return {"id": channel_id, "name": channel_name}


def compile_route(raw: dict[str, Any]) -> dict[str, Any]:
    item = validate_work_item(raw)
    known = item["kind"] in _ROUTES
    if known:
        primary_name, mirror_names = _ROUTES[item["kind"]]
    else:
        primary_name, mirror_names = "coordination", ()
    if primary_name in _NON_DEFAULT_PRIMARY and item["kind"] != "merge_review":
        raise RouterError("central queue selected outside its dedicated work kind")

    external = item["external_publish"]
    decision = {
        "schema": ROUTE_RECEIPT_SCHEMA,
        "work_id": item["work_id"],
        "kind": item["kind"],
        "publication_key": publication_key(item),
        "primary_channel": _channel(primary_name),
        "mirror_channels": [_channel(name) for name in mirror_names],
        "scratch_channel": _channel("todo"),
        "classification": "ROUTED" if known else "HOLD_CLASSIFICATION_UNKNOWN",
        "requires_collision_search": True,
        "requires_muse_arbitration": external,
        "muse_dm_id": MUSE_DM_ID if external else None,
        "external_publish_requested": external,
        "external_publish_authorized": False,
        "side_effects_authorized": False,
        "anti_dogpile": {
            "delegations_default_primary": False,
            "awaiting_merge_default_primary": False,
            "transport_excluded_from_publication_key": True,
        },
        "input_sha256": _sha256_obj(item),
    }
    decision["receipt_sha256"] = _sha256_obj(decision)
    return decision


def _verify_digest(receipt: dict[str, Any]) -> bool:
    digest = receipt.get("receipt_sha256")
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    return _sha256_obj(body) == digest


def verify_receipt(receipt: dict[str, Any]) -> bool:
    if type(receipt) is not dict or not _verify_digest(receipt):
        return False
    schema = receipt.get("schema")
    if schema == ROUTE_RECEIPT_SCHEMA:
        return receipt.get("external_publish_authorized") is False and receipt.get("side_effects_authorized") is False
    if schema == SCRATCH_RECEIPT_SCHEMA:
        return receipt.get("side_effects_authorized") is False and receipt.get("state") in {"OPEN", "CLEARED"}
    return False


def compile_scratch(raw: dict[str, Any], action: str, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    item = validate_work_item(raw)
    if action not in {"OPEN", "CLEAR"}:
        raise RouterError("scratch action must be OPEN or CLEAR")
    prior_digest: str | None = None
    if action == "OPEN":
        if prior is not None:
            if not verify_receipt(prior) or prior.get("schema") != SCRATCH_RECEIPT_SCHEMA:
                raise RouterError("prior scratch receipt is invalid")
            if prior.get("work_id") != item["work_id"] or prior.get("publication_key") != publication_key(item):
                raise RouterError("prior scratch receipt is for a different work item")
            if prior.get("state") != "CLEARED":
                raise RouterError("cannot OPEN over a non-cleared scratch record")
            prior_digest = prior["receipt_sha256"]
    else:
        if prior is None or not verify_receipt(prior) or prior.get("schema") != SCRATCH_RECEIPT_SCHEMA:
            raise RouterError("CLEAR requires a valid prior scratch receipt")
        if prior.get("work_id") != item["work_id"] or prior.get("publication_key") != publication_key(item):
            raise RouterError("prior scratch receipt is for a different work item")
        if prior.get("state") != "OPEN":
            raise RouterError("CLEAR requires prior OPEN state")
        prior_digest = prior["receipt_sha256"]

    receipt = {
        "schema": SCRATCH_RECEIPT_SCHEMA,
        "work_id": item["work_id"],
        "publication_key": publication_key(item),
        "state": "CLEARED" if action == "CLEAR" else "OPEN",
        "todo_channel": _channel("todo"),
        "previous_receipt_sha256": prior_digest,
        "side_effects_authorized": False,
    }
    receipt["receipt_sha256"] = _sha256_obj(receipt)
    return receipt


def channel_registry() -> dict[str, Any]:
    entries = []
    for key in sorted(_CHANNELS):
        entries.append({
            "key": key,
            "id": _CHANNELS[key][0],
            "name": _CHANNELS[key][1],
            "default_primary_allowed": key not in _NON_DEFAULT_PRIMARY,
        })
    return {"schema": "swarm-work-channel-registry/v1", "channels": entries, "muse_dm_id": MUSE_DM_ID}


def _read_json(path: str) -> dict[str, Any]:
    return loads_strict(Path(path).read_text(encoding="utf-8"))


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Swarm-Z specialist work router")
    sub = parser.add_subparsers(dest="command", required=True)
    p_route = sub.add_parser("route")
    p_route.add_argument("work_item")
    p_open = sub.add_parser("scratch-open")
    p_open.add_argument("work_item")
    p_open.add_argument("--prior")
    p_clear = sub.add_parser("scratch-clear")
    p_clear.add_argument("work_item")
    p_clear.add_argument("prior")
    sub.add_parser("channels")
    args = parser.parse_args(argv)
    try:
        if args.command == "route":
            _emit(compile_route(_read_json(args.work_item)))
        elif args.command == "scratch-open":
            prior = _read_json(args.prior) if args.prior else None
            _emit(compile_scratch(_read_json(args.work_item), "OPEN", prior))
        elif args.command == "scratch-clear":
            _emit(compile_scratch(_read_json(args.work_item), "CLEAR", _read_json(args.prior)))
        else:
            _emit(channel_registry())
    except (OSError, RouterError) as exc:
        sys.stderr.write(f"swarm-work-router: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
