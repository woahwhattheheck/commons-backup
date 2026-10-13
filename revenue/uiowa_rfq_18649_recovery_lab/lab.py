#!/usr/bin/env python3
"""Deterministic, fictional stateful-recovery tabletop. No deployment operations."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

VERSIONS = {"v1", "bridge", "v2"}
MAX_BYTES = 2_000_000
ACTION_FIELDS = {
    "runtime": ({"at", "op"}, {"reader", "writer", "worker"}),
    "submit": ({"at", "op", "event_id", "resource", "delta"}, set()),
    "deliver": ({"at", "op", "event_id"}, {"idempotent"}),
    "replay": ({"at", "op"}, {"idempotent"}),
    "snapshot": ({"at", "op", "name"}, set()),
    "restore": ({"at", "op", "name"}, set()),
    "expand": ({"at", "op"}, set()),
    "contract": ({"at", "op"}, set()),
    "incident": ({"at", "op", "note"}, set()),
    "verify": ({"at", "op", "label"}, set()),
}
DISCLAIMER = (
    "Fictional deterministic model, not University evidence, a production recovery "
    "procedure, a benchmark, or an authorization to change any system. The accepted "
    "event log is assumed complete, durable, ordered, and outside the restored snapshot."
)


class InputError(ValueError):
    """Invalid input, distinct from an intentionally failing simulated recovery."""


class Incompatible(ValueError):
    """A modeled reader or worker cannot interpret a particular representation."""


def fields(value: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected an object")
    missing, extra = required - value.keys(), value.keys() - required - optional
    if missing or extra:
        raise InputError(f"{where}: missing={sorted(missing)}, unknown={sorted(extra)}")


def text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise InputError(f"{where}: expected 1..500 nonblank characters")
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise InputError(f"{where}: control characters or unpaired surrogates are not allowed")
    return value


def integer(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 1_000_000:
        raise InputError(f"{where}: expected integer in [{minimum}, 1000000]")
    return value


def loads_strict(raw: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InputError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise InputError(f"non-finite JSON number: {value}")

    def bounded_int(value: str) -> int:
        if len(value.lstrip("-")) > 7:
            raise InputError("JSON integer exceeds the model numeric range")
        return int(value)

    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise InputError(f"input exceeds {MAX_BYTES} bytes")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_int=bounded_int)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc


def validate_scenario(s: Any, where: str) -> None:
    fields(s, {"id", "title", "resources", "actions"}, set(), where)
    text(s["id"], where + ".id")
    text(s["title"], where + ".title")
    if not isinstance(s["resources"], list) or not 1 <= len(s["resources"]) <= 100:
        raise InputError(f"{where}.resources: expected 1..100 records")
    seen: set[str] = set()
    for r in s["resources"]:
        fields(r, {"id", "capacity", "initial"}, set(), where + ".resource")
        rid = text(r["id"], "resource.id")
        if rid in seen:
            raise InputError(f"duplicate resource: {rid}")
        seen.add(rid)
        if integer(r["initial"], "initial") > integer(r["capacity"], "capacity"):
            raise InputError(f"initial allocation exceeds capacity: {rid}")
    if not isinstance(s["actions"], list) or not 1 <= len(s["actions"]) <= 1000:
        raise InputError(f"{where}.actions: expected 1..1000 actions")
    previous = -1
    labels: set[str] = set()
    for i, a in enumerate(s["actions"]):
        p = f"{where}.actions[{i}]"
        if not isinstance(a, dict) or not isinstance(a.get("op"), str) or a["op"] not in ACTION_FIELDS:
            raise InputError(f"{p}: unknown action")
        required, optional = ACTION_FIELDS[a["op"]]
        fields(a, required, optional, p)
        at = integer(a["at"], p + ".at")
        if at < previous:
            raise InputError(f"{p}: time goes backwards")
        previous = at
        for key in ("event_id", "resource", "name", "note", "label"):
            if key in a:
                text(a[key], p + "." + key)
        if "delta" in a:
            integer(a["delta"], p + ".delta", -1_000_000)
            if a["delta"] == 0:
                raise InputError(f"{p}.delta: must not be zero")
        if "idempotent" in a and type(a["idempotent"]) is not bool:
            raise InputError(f"{p}.idempotent: expected boolean")
        if a["op"] == "runtime":
            if not any(k in a for k in ("reader", "writer", "worker")):
                raise InputError(f"{p}: empty runtime change")
            for k in ("reader", "writer", "worker"):
                if k in a and (not isinstance(a[k], str) or a[k] not in VERSIONS):
                    raise InputError(f"{p}.{k}: expected v1, bridge, or v2")
        if a["op"] == "verify":
            if a["label"] in labels:
                raise InputError(f"{p}: duplicate checkpoint label")
            labels.add(a["label"])
    if s["actions"][-1]["op"] != "verify":
        raise InputError(f"{where}: final action must verify the resulting state")


def decode(row: dict[str, int], version: str) -> int:
    if version == "bridge":
        if "units" in row and "quantity" in row and row["units"] != row["quantity"]:
            raise Incompatible("legacy and new fields disagree; no automatic winner")
        key = "quantity" if "quantity" in row else "units"
    else:
        key = "units" if version == "v1" else "quantity"
    if key not in row:
        raise Incompatible(f"{version} cannot read fields {sorted(row)}")
    return row[key]


def encoded(value: int, layout: str) -> dict[str, int]:
    if layout == "v1":
        return {"units": value}
    if layout == "v2":
        return {"quantity": value}
    return {"units": value, "quantity": value}


class Model:
    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.capacities = {r["id"]: r["capacity"] for r in scenario["resources"]}
        self.expected = {r["id"]: r["initial"] for r in scenario["resources"]}
        self.rows = {r: encoded(n, "v1") for r, n in self.expected.items()}
        self.layout = "v1"
        self.runtime = dict.fromkeys(("reader", "writer", "worker"), "v1")
        self.events: dict[str, dict[str, Any]] = {}
        self.applications: dict[str, int] = {}
        self.snapshots: dict[str, tuple[Any, ...]] = {}
        self.incident_at: int | None = None
        self.history: list[dict[str, Any]] = []
        self.checkpoints: list[dict[str, Any]] = []

    def deliver(self, eid: str, idempotent: bool) -> dict[str, str]:
        if eid not in self.events:
            raise InputError(f"delivery references unknown event: {eid}")
        if idempotent and self.applications.get(eid, 0):
            return {"event_id": eid, "outcome": "duplicate_skipped"}
        e = self.events[eid]
        worker = self.runtime["worker"]
        row = self.rows[e["resource"]]
        try:
            delta, previous = decode(e["payload"], worker), decode(row, worker)
        except Incompatible as exc:
            return {"event_id": eid, "outcome": "blocked", "reason": str(exc)}
        # Deliberately model legacy-only/new-only writers: a mixed fleet can split
        # a dual representation. The bridge updates both in one modeled step.
        if worker == "bridge":
            replacement = encoded(previous + delta, self.layout)
        else:
            replacement = dict(row)
            replacement["units" if worker == "v1" else "quantity"] = previous + delta
        self.rows[e["resource"]] = replacement
        self.applications[eid] = self.applications.get(eid, 0) + 1
        return {"event_id": eid, "outcome": "applied"}

    def verify(self, label: str, at: int) -> dict[str, Any]:
        observed: dict[str, int | None] = {}
        unreadable: dict[str, str] = {}
        for rid, row in sorted(self.rows.items()):
            try:
                observed[rid] = decode(row, self.runtime["reader"])
            except Incompatible as exc:
                observed[rid] = None
                unreadable[rid] = str(exc)
        pending = sorted(set(self.events) - self.applications.keys())
        duplicate = sorted(e for e, n in self.applications.items() if n > 1)
        disagreement = sorted(r for r, row in self.rows.items()
                              if "units" in row and "quantity" in row
                              and row["units"] != row["quantity"])
        invariants = {
            "service_readable": not unreadable,
            "balances_match_accepted_log": observed == self.expected,
            "accepted_events_accounted_for": not pending,
            "applied_at_most_once": not duplicate,
            "legacy_and_new_views_agree": not disagreement,
            "capacity_valid": all(n is not None and 0 <= n <= self.capacities[r]
                                  for r, n in observed.items()),
        }
        all_hold = all(invariants.values())
        return {
            "label": label, "at_minute": at, "layout": self.layout,
            "runtime": dict(self.runtime), "invariants": invariants,
            "all_model_invariants_hold": all_hold,
            "elapsed_since_incident_minutes": None if self.incident_at is None else at - self.incident_at,
            "verified_recovery_minutes": at - self.incident_at if all_hold and self.incident_at is not None else None,
            "observed": observed, "expected_from_accepted_log": dict(sorted(self.expected.items())),
            "stored_rows": deepcopy(self.rows), "unreadable": unreadable,
            "unapplied_event_ids": pending, "multiply_applied_event_ids": duplicate,
            "disagreeing_resource_ids": disagreement,
            "accepted_event_count": len(self.events),
            "application_counts": dict(sorted(self.applications.items())),
        }

    def step(self, a: dict[str, Any]) -> dict[str, Any]:
        op = a["op"]
        result: dict[str, Any] = {"outcome": "modeled"}
        if op == "runtime":
            self.runtime.update({k: a[k] for k in self.runtime if k in a})
        elif op == "submit":
            eid, rid = a["event_id"], a["resource"]
            if eid in self.events:
                raise InputError(f"duplicate accepted event ID: {eid}")
            if rid not in self.rows:
                raise InputError(f"unknown resource: {rid}")
            total = self.expected[rid] + a["delta"]
            if not 0 <= total <= self.capacities[rid]:
                raise InputError(f"accepted event violates fictional capacity: {eid}")
            # Bridge producers keep old-compatible messages until contraction.
            fmt = "v2" if self.runtime["writer"] == "v2" else "v1"
            self.events[eid] = {"resource": rid, "delta": a["delta"],
                                "payload": encoded(a["delta"], fmt), "accepted_at": a["at"]}
            self.expected[rid] = total
            result["event_id"] = eid
        elif op in {"deliver", "replay"}:
            ids = [a["event_id"]] if op == "deliver" else list(self.events)
            result["deliveries"] = [self.deliver(e, a.get("idempotent", True)) for e in ids]
        elif op == "snapshot":
            if a["name"] in self.snapshots:
                raise InputError(f"snapshot name reused: {a['name']}")
            self.snapshots[a["name"]] = deepcopy((self.rows, self.applications, self.layout))
        elif op == "restore":
            if a["name"] not in self.snapshots:
                raise InputError(f"unknown snapshot: {a['name']}")
            self.rows, self.applications, self.layout = deepcopy(self.snapshots[a["name"]])
            # External accepted log, runtime, and incident clock are NOT rewound.
        elif op == "expand":
            if self.layout != "v1":
                raise InputError("expand requires v1 storage")
            self.rows = {r: encoded(decode(row, "v1"), "dual") for r, row in self.rows.items()}
            self.layout = "dual"
        elif op == "contract":
            if self.layout != "dual":
                raise InputError("contract requires dual storage")
            self.rows = {r: {"quantity": row["quantity"]} for r, row in self.rows.items()}
            self.layout = "v2"
        elif op == "incident":
            if self.incident_at is not None:
                raise InputError("one incident clock per scenario; split separate incidents")
            self.incident_at = a["at"]
        elif op == "verify":
            checkpoint = self.verify(a["label"], a["at"])
            self.checkpoints.append(checkpoint)
            result["checkpoint"] = a["label"]
            result["all_model_invariants_hold"] = checkpoint["all_model_invariants_hold"]
        return result

    def run(self) -> dict[str, Any]:
        for index, action in enumerate(self.scenario["actions"]):
            try:
                outcome = self.step(action)
            except InputError as exc:
                raise InputError(f"{self.scenario['id']}.actions[{index}]: {exc}") from exc
            self.history.append({"index": index, **action, **outcome})
        return {"id": self.scenario["id"], "title": self.scenario["title"],
                "history": self.history, "checkpoints": self.checkpoints,
                "final": self.checkpoints[-1], "accepted_log": deepcopy(self.events)}


def run_packet(packet: Any) -> dict[str, Any]:
    fields(packet, {"schema_version", "synthetic", "scenarios"}, set(), "packet")
    if type(packet["schema_version"]) is not int or packet["schema_version"] != 1:
        raise InputError("schema_version must be integer 1")
    if packet["synthetic"] is not True:
        raise InputError("synthetic must be true; this lab is not a live evidence assessor")
    if not isinstance(packet["scenarios"], list) or not 1 <= len(packet["scenarios"]) <= 100:
        raise InputError("scenarios must contain 1..100 entries")
    seen: set[str] = set()
    for i, scenario in enumerate(packet["scenarios"]):
        validate_scenario(scenario, f"scenarios[{i}]")
        if scenario["id"] in seen:
            raise InputError(f"duplicate scenario ID: {scenario['id']}")
        seen.add(scenario["id"])
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema_version": 1, "synthetic": True, "notice": DISCLAIMER,
            "input_sha256": hashlib.sha256(canonical).hexdigest(),
            "results": [Model(s).run() for s in packet["scenarios"]]}


def md(value: Any) -> str:
    """Render user-controlled labels as inert table text, not HTML or links."""
    value = str(value)
    special = set("&<>|`*_[]()#!\\")
    return "".join(f"&#{ord(c)};" if c in special else c for c in value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Stateful recovery rehearsal", "", report["notice"], "",
             f"Canonical input SHA-256: `{report['input_sha256']}`", ""]
    for result in report["results"]:
        lines.extend([f"## {md(result['id'])}: {md(result['title'])}", "",
                      "| Checkpoint | Minute | Readable | All model invariants | Verified recovery minutes |",
                      "|---|---:|---|---|---:|"])
        for c in result["checkpoints"]:
            elapsed = c["verified_recovery_minutes"]
            lines.append(f"| {md(c['label'])} | {c['at_minute']} | {c['invariants']['service_readable']} | "
                         f"{c['all_model_invariants_hold']} | {elapsed if elapsed is not None else 'not established'} |")
        for c in result["checkpoints"]:
            lines.extend(["", f"### {md(c['label'])}", "",
                          f"Runtime: {md(c['runtime'])}; storage: {c['layout']}.",
                          f"Expected allocations: {md(c['expected_from_accepted_log'])}.",
                          f"Observed allocations: {md(c['observed'])}.",
                          f"Unapplied events: {md(c['unapplied_event_ids'])}.",
                          f"Repeated applications: {md(c['multiply_applied_event_ids'])}.",
                          f"Split representations: {md(c['disagreeing_resource_ids'])}.",
                          f"Failed invariants: {md([k for k, v in c['invariants'].items() if not v])}.",
                          f"Unreadable records: {md(c['unreadable'])}."])
        lines.extend(["", "### Action transcript", "", "| Minute | Action | Outcome |", "|---:|---|---|"])
        for event in result["history"]:
            detail = event.get("deliveries", event.get("checkpoint", event["outcome"]))
            lines.append(f"| {event['at']} | {md(event['op'])} | {md(detail)} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="fictional JSON scenario packet")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        with args.packet.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError(f"input exceeds {MAX_BYTES} bytes")
        report = run_packet(loads_strict(raw.decode("utf-8")))
    except (InputError, OSError, UnicodeError, RecursionError) as exc:
        print(f"recovery-lab input error: {exc}", file=sys.stderr)
        return 2
    print(render_markdown(report) if args.format == "markdown"
          else json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), end="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
