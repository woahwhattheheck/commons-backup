#!/usr/bin/env python3
"""Strict normalization for retained terminality snapshots."""
from .schema import (
    SCHEMA, RegistryError, _arr, _enum, _git_sha, _https, _id, _index, _obj,
    _positive_int, _sha256, _text, _timestamp,
)

def _normalize(candidate):
    root = _obj(candidate, "snapshot", {
        "schema_version", "evaluated_at_utc", "max_provider_age_seconds",
        "max_heartbeat_age_seconds", "items", "provider_observations", "heartbeats", "successors",
    })
    if root["schema_version"] != SCHEMA:
        raise RegistryError(f"schema_version must be {SCHEMA}")
    now = _timestamp(root["evaluated_at_utc"], "evaluated_at_utc")
    provider_age = _positive_int(root["max_provider_age_seconds"], "max_provider_age_seconds")
    heartbeat_age = _positive_int(root["max_heartbeat_age_seconds"], "max_heartbeat_age_seconds")

    items = []
    for raw in _arr(root["items"], "items"):
        row = _obj(raw, "item", {"id", "kind", "locator", "provider_observation_id"})
        items.append({
            "id": _id(row["id"], "item.id"),
            "kind": _enum(row["kind"], "item.kind", {"ISSUE", "PR", "BRANCH", "OPERATION"}),
            "locator": _text(row["locator"], "item.locator", 512),
            "provider_observation_id": _id(row["provider_observation_id"], "item.provider_observation_id"),
        })
    items.sort(key=lambda x: x["id"])
    iidx = _index(items, "item")
    if not items:
        raise RegistryError("at least one item is required")

    observations = []
    for raw in _arr(root["provider_observations"], "provider_observations"):
        row = _obj(raw, "provider_observation", {
            "id", "item_id", "provider", "source_url", "source_sha256", "observed_at_utc",
            "provider_state", "head_sha", "merged_sha",
        })
        item_id = _id(row["item_id"], "provider_observation.item_id")
        if item_id not in iidx:
            raise RegistryError(f"provider observation references unknown item: {item_id}")
        state = _enum(row["provider_state"], "provider_observation.provider_state", {
            "OPEN", "CLOSED", "MERGED", "PRESENT", "ABSENT", "UNKNOWN",
        })
        kind = iidx[item_id]["kind"]
        allowed = {
            "ISSUE": {"OPEN", "CLOSED", "UNKNOWN"},
            "PR": {"OPEN", "CLOSED", "MERGED", "UNKNOWN"},
            "BRANCH": {"PRESENT", "ABSENT", "UNKNOWN"},
            "OPERATION": {"OPEN", "CLOSED", "UNKNOWN"},
        }[kind]
        if state not in allowed:
            raise RegistryError(f"impossible provider state {state} for {kind} {item_id}")
        head_sha = _git_sha(row["head_sha"], "provider_observation.head_sha")
        merged_sha = _git_sha(row["merged_sha"], "provider_observation.merged_sha")
        if state == "MERGED" and merged_sha is None:
            raise RegistryError(f"MERGED PR {item_id} requires merged_sha")
        if state != "MERGED" and merged_sha is not None:
            raise RegistryError(f"non-MERGED item {item_id} cannot carry merged_sha")
        if kind == "BRANCH" and state == "PRESENT" and head_sha is None:
            raise RegistryError(f"PRESENT branch {item_id} requires head_sha")
        observations.append({
            "id": _id(row["id"], "provider_observation.id"),
            "item_id": item_id,
            "provider": _enum(row["provider"], "provider_observation.provider", {"GITHUB", "SLACK", "OTHER_RETAINED"}),
            "source_url": _https(row["source_url"], "provider_observation.source_url"),
            "source_sha256": _sha256(row["source_sha256"], "provider_observation.source_sha256"),
            "observed_at_utc": _text(row["observed_at_utc"], "provider_observation.observed_at_utc", 64),
            "provider_state": state,
            "head_sha": head_sha,
            "merged_sha": merged_sha,
        })
        _timestamp(observations[-1]["observed_at_utc"], "provider_observation.observed_at_utc")
    observations.sort(key=lambda x: x["id"])
    oidx = _index(observations, "provider_observation")
    if not observations:
        raise RegistryError("at least one provider observation is required")
    for item in items:
        oid = item["provider_observation_id"]
        if oid not in oidx:
            raise RegistryError(f"item {item['id']} references unknown provider observation: {oid}")
        if oidx[oid]["item_id"] != item["id"]:
            raise RegistryError(f"cross-item provider observation transplant on {item['id']}")

    heartbeats = []
    for raw in _arr(root["heartbeats"], "heartbeats"):
        row = _obj(raw, "heartbeat", {"id", "item_id", "owner", "observed_at_utc", "expires_at_utc", "source_observation_id"})
        item_id = _id(row["item_id"], "heartbeat.item_id")
        if item_id not in iidx:
            raise RegistryError(f"heartbeat references unknown item: {item_id}")
        source_id = _id(row["source_observation_id"], "heartbeat.source_observation_id")
        if source_id not in oidx or oidx[source_id]["item_id"] != item_id:
            raise RegistryError(f"heartbeat source observation is not bound to item {item_id}")
        observed = _timestamp(row["observed_at_utc"], "heartbeat.observed_at_utc")
        expires = _timestamp(row["expires_at_utc"], "heartbeat.expires_at_utc")
        if expires <= observed:
            raise RegistryError(f"heartbeat {row['id']} expires before/at observation")
        heartbeats.append({
            "id": _id(row["id"], "heartbeat.id"),
            "item_id": item_id,
            "owner": _text(row["owner"], "heartbeat.owner", 192),
            "observed_at_utc": _text(row["observed_at_utc"], "heartbeat.observed_at_utc", 64),
            "expires_at_utc": _text(row["expires_at_utc"], "heartbeat.expires_at_utc", 64),
            "source_observation_id": source_id,
        })
    heartbeats.sort(key=lambda x: x["id"])
    _index(heartbeats, "heartbeat")

    successors = []
    for raw in _arr(root["successors"], "successors"):
        row = _obj(raw, "successor", {"id", "predecessor_item_id", "successor_item_id", "relationship", "source_observation_ids"})
        pred = _id(row["predecessor_item_id"], "successor.predecessor_item_id")
        succ = _id(row["successor_item_id"], "successor.successor_item_id")
        if pred not in iidx or succ not in iidx:
            raise RegistryError("successor edge references unknown item")
        if pred == succ:
            raise RegistryError("self-successor edge is invalid")
        relationship = _enum(row["relationship"], "successor.relationship", {"CANONICAL_SUCCESSOR"})
        refs = sorted(_id(x, "successor.source_observation_ids[]") for x in _arr(row["source_observation_ids"], "successor.source_observation_ids"))
        if len(refs) != len(set(refs)):
            raise RegistryError("successor.source_observation_ids contains duplicates")
        if not refs:
            raise RegistryError("successor edge requires provider evidence")
        for oid in refs:
            if oid not in oidx:
                raise RegistryError(f"successor edge references unknown observation: {oid}")
        bound_items = {oidx[oid]["item_id"] for oid in refs}
        if not {pred, succ}.issubset(bound_items):
            raise RegistryError(f"successor edge {row['id']} lacks predecessor+successor-bound observations")
        successors.append({
            "id": _id(row["id"], "successor.id"),
            "predecessor_item_id": pred,
            "successor_item_id": succ,
            "relationship": relationship,
            "source_observation_ids": refs,
        })
    successors.sort(key=lambda x: x["id"])
    _index(successors, "successor")

    outgoing = {}
    for edge in successors:
        outgoing.setdefault(edge["predecessor_item_id"], []).append(edge["successor_item_id"])
    for pred, targets in outgoing.items():
        if len(targets) > 1:
            raise RegistryError(f"conflicting canonical successors for {pred}: {sorted(targets)!r}")

    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise RegistryError(f"canonical-successor cycle detected at {node}")
        if node in visited:
            return
        visiting.add(node)
        for nxt in outgoing.get(node, []):
            visit(nxt)
        visiting.remove(node)
        visited.add(node)
    for item_id in iidx:
        visit(item_id)

    return {
        "schema_version": SCHEMA,
        "evaluated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "max_provider_age_seconds": provider_age,
        "max_heartbeat_age_seconds": heartbeat_age,
        "items": items,
        "provider_observations": observations,
        "heartbeats": heartbeats,
        "successors": successors,
    }


