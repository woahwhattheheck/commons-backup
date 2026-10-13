"""Platform-neutral delta protocol used by TITAN Hands adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


PROTOCOL_VERSION = "titan-hands-deltaui/0.1"


class ProtocolError(ValueError):
    """A request or backend observation does not satisfy the wire contract."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def normalize_node(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ProtocolError("every node must be an object")
    node_id = str(raw.get("id") or "").strip()
    if not node_id:
        raise ProtocolError("every node requires a stable id")
    node = dict(raw)
    node["id"] = node_id
    node["parent"] = str(node.get("parent") or "")
    node["role"] = str(node.get("role") or "unknown")
    actions = node.get("actions") or []
    if not isinstance(actions, list):
        raise ProtocolError("node actions must be a list")
    node["actions"] = sorted({str(action) for action in actions if str(action)})
    states = node.get("states") or []
    if not isinstance(states, list):
        raise ProtocolError("node states must be a list")
    node["states"] = sorted({str(state) for state in states if str(state)})
    return node


def normalize_nodes(raw_nodes: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for raw in raw_nodes:
        node = normalize_node(raw)
        if node["id"] in nodes:
            raise ProtocolError(f"duplicate node id: {node['id']}")
        nodes[node["id"]] = node
    return nodes


@dataclass
class DeltaTracker:
    """Turns full adapter snapshots into deterministic, replayable deltas."""

    sequence: int = 0
    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _meta: dict[str, Any] = field(default_factory=dict)

    def reset(self) -> None:
        self.sequence = 0
        self._nodes.clear()
        self._meta.clear()

    def current_nodes(self) -> dict[str, dict[str, Any]]:
        return self._nodes

    def current_meta(self) -> dict[str, Any]:
        return self._meta

    def current_nodes(self) -> dict[str, dict[str, Any]]:
        return self._nodes

    def current_meta(self) -> dict[str, Any]:
        return self._meta

    def observe(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, Mapping):
            raise ProtocolError("snapshot must be an object")
        raw_nodes = snapshot.get("nodes") or []
        if not isinstance(raw_nodes, list):
            raise ProtocolError("snapshot.nodes must be a list")
        current = normalize_nodes(raw_nodes)
        previous = self._nodes
        base_sequence = self.sequence
        self.sequence += 1

        added = [current[key] for key in sorted(current.keys() - previous.keys())]
        removed = sorted(previous.keys() - current.keys())
        updated = [
            current[key]
            for key in sorted(current.keys() & previous.keys())
            if current[key] != previous[key]
        ]
        unchanged = len(current) - len(added) - len(updated)

        meta = {
            key: value
            for key, value in snapshot.items()
            if key not in {"nodes", "ok"}
        }
        meta_changed = meta != self._meta
        self._nodes = current
        self._meta = meta
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "observation_delta",
            "sequence": self.sequence,
            "base_sequence": base_sequence,
            "full": base_sequence == 0,
            "added": added,
            "updated": updated,
            "removed": removed,
            "unchanged": unchanged,
            "node_count": len(current),
            "meta_changed": meta_changed,
            "meta": meta if meta_changed or base_sequence == 0 else {},
            "state_digest": digest({"nodes": current, "meta": meta}),
        }


def failure(reason: str, message: str, **evidence: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "protocol": PROTOCOL_VERSION,
        "kind": "failure",
        "failure_reason": str(reason or "BACKEND_ERROR"),
        "message": str(message or ""),
    }
    if evidence:
        result["evidence"] = evidence
    return result


