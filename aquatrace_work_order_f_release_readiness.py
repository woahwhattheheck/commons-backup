#!/usr/bin/env python3
"""AquaTrace work-order F — customer release-readiness runner.

Demand: aquatrace-work-order-f-release-readiness-20260831-01

Independently checks demo, training, deployment, support, security,
disaster recovery, interfaces, and buyer-acceptance against durable
evidence pointers. Unresolved gates stay NOT_READY. This runner never
invents certification, production-ready, deployed, submitted, or
buyer-accepted.

Cite, do not remint, private AquaTrace local SHA
1e6cdbeddf308cd1415fbe3b8e70e564c569daa4 path
docs/acceptance/customer-release-gates.md. Citation without local bytes
does not promote a gate. Do not clone the private repo.

Named-human release only. SYSTEM / unnamed / HELD are denied. Replay is
idempotent. Synthetic / read-only fixtures only.

Official command:
    python3 aquatrace_work_order_f_release_readiness.py

HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.
No City contact. No bid submission. No live LIMS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

LEFTOVER_ID = "aquatrace-work-order-f-release-readiness-20260831-01"
SCHEMA = "commons-aquatrace-work-order-f-release-readiness/v1"
COMMAND = "python3 aquatrace_work_order_f_release_readiness.py"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
CASH_USD = 0
CLOCK = "2026-08-31T12:00:00Z"
HUMAN_APPROVER = "SYN-F-RELEASER"

PRIVATE_CITE_SHA = "1e6cdbeddf308cd1415fbe3b8e70e564c569daa4"
PRIVATE_CITE_PATH = "docs/acceptance/customer-release-gates.md"

GATE_IDS = (
    "demo",
    "training",
    "deployment",
    "support",
    "security",
    "disaster_recovery",
    "interfaces",
    "buyer_acceptance",
)

AUTONOMOUS_NAMES = frozenset(
    {"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE", "UNNAMED", "UNKNOWN", "HELD"}
)
FORBIDDEN_LABELS = frozenset(
    {
        "CERTIFIED",
        "CERTIFICATION",
        "PRODUCTION_READY",
        "PRODUCTION-READY",
        "DEPLOYED",
        "SUBMITTED",
        "BUYER_ACCEPTED",
        "BUYER-ACCEPTED",
    }
)
PRODUCTION_LIKE_VERBS = frozenset(
    {
        "contact_city",
        "submit_bid",
        "connect_live_lims",
        "write_production",
        "claim_production_ready",
        "claim_deployed",
        "claim_buyer_accepted",
    }
)
READY_KINDS = frozenset({"LOCAL_SHA256"})
NOT_READY_KINDS = frozenset(
    {"CITE_ONLY", "PRIVATE_UNVERIFIED", "CLAIM_ONLY", "FORBIDDEN_LABEL"}
)

HERE = Path(__file__).resolve().parent
PACK = HERE / "revenue" / "aquatrace_work_order_f_release_readiness"
GATES_PATH = PACK / "gates.json"
DEFAULT_POINTERS_PATH = PACK / "default_pointers.json"
EVIDENCE_DIR = PACK / "evidence"

# Locked after the first measured battery. Fail-closed if the journal moves.
GOLDEN_AUDIT_SHA256 = "fcdc5783b724d1a864b45319156167a49e2283673f8c3144d632f6f417bd2d9f"
GOLDEN_DEFAULT_READY = 0
GOLDEN_DEFAULT_NOT_READY = 8
GOLDEN_COMPLETE_READY = 8
GOLDEN_RELEASE_COUNT = 1
GOLDEN_DENY_COUNT = 7
GOLDEN_CASE_COUNT = 11


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, Path):
        return hashlib.sha256(value.read_bytes()).hexdigest()
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gates(path: Path = GATES_PATH) -> list[dict[str, Any]]:
    spec = load_json(path)
    rows = spec.get("gates") or []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def load_default_pointers(path: Path = DEFAULT_POINTERS_PATH) -> list[dict[str, Any]]:
    spec = load_json(path)
    return [deepcopy(row) for row in (spec.get("pointers") or []) if isinstance(row, dict)]


def evidence_relpath(gate_id: str) -> str:
    return "revenue/aquatrace_work_order_f_release_readiness/evidence/%s.json" % gate_id


def build_complete_pointers() -> list[dict[str, Any]]:
    pointers: list[dict[str, Any]] = []
    for gate_id in GATE_IDS:
        rel = evidence_relpath(gate_id)
        path = HERE / rel
        pointers.append(
            {
                "gate": gate_id,
                "kind": "LOCAL_SHA256",
                "label": "MEASURED",
                "path": rel,
                "recorded_by": HUMAN_APPROVER,
                "sha": sha256_hex(path) if path.is_file() else "",
                "source": "commons-synthetic",
            }
        )
    return pointers


class ReleaseReadinessPlane:
    """Fail-closed evaluator for Lane F customer-release gates."""

    def __init__(self) -> None:
        self.clock = CLOCK
        self.audit: list[dict[str, Any]] = []
        self.records: dict[str, dict[str, Any]] = {}
        self.seq = 0

    def _record(
        self,
        kind: str,
        request: dict[str, Any],
        decision: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        event = {
            "seq": self.seq,
            "at": self.clock,
            "kind": kind,
            "request_id": _text(request.get("request_id")),
            "actor": _text(request.get("named_human") or request.get("actor")),
            "verb": _text(request.get("verb") or kind),
            "decision": decision,
            "reason": reason,
            "cash_usd": CASH_USD,
            "city_contact": False,
            "city_submission": False,
            "live_lims": False,
            "private_repo_cloned": False,
        }
        if extra:
            event.update(extra)
        self.audit.append(event)
        return event

    def evaluate_pointer(self, pointer: dict[str, Any]) -> dict[str, Any]:
        gate = _text(pointer.get("gate"))
        kind = _text(pointer.get("kind")).upper()
        label = _text(pointer.get("label")).upper().replace(" ", "_")
        path = _text(pointer.get("path"))
        sha = _text(pointer.get("sha")).lower()
        recorded_by = _text(pointer.get("recorded_by"))
        source = _text(pointer.get("source"))

        if not gate:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "gate_missing",
                "kind": kind,
            }
        if label in FORBIDDEN_LABELS:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "forbidden_label",
                "kind": kind,
                "label": label,
            }
        if kind in NOT_READY_KINDS or kind == "CITE_ONLY":
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "cite_only_not_local_bytes"
                if kind == "CITE_ONLY"
                else "pointer_kind_not_durable",
                "kind": kind,
                "cited_sha": sha,
                "cited_path": path,
            }
        if kind not in READY_KINDS:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "unknown_pointer_kind",
                "kind": kind,
            }
        if not path or not sha:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "pointer_incomplete",
                "kind": kind,
            }
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "sha_not_sha256",
                "kind": kind,
            }
        if recorded_by.upper() in AUTONOMOUS_NAMES or not recorded_by:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "named_human_missing",
                "kind": kind,
            }
        if source == "private-aquatrace-local":
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "private_cite_unverified",
                "kind": kind,
            }
        local = HERE / path
        if not local.is_file():
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "local_evidence_missing",
                "kind": kind,
                "path": path,
            }
        digest = sha256_hex(local)
        if digest != sha:
            return {
                "gate": gate,
                "state": "NOT_READY",
                "reason": "local_hash_mismatch",
                "kind": kind,
                "path": path,
            }
        return {
            "gate": gate,
            "state": "READY",
            "reason": "durable_local_pointer",
            "kind": kind,
            "path": path,
            "sha": sha,
            "recorded_by": recorded_by,
        }

    def evaluate_gates(
        self,
        pointers: list[dict[str, Any]],
        request_id: str = "GATES",
    ) -> dict[str, Any]:
        by_gate = {
            _text(row.get("gate")): row
            for row in pointers
            if isinstance(row, dict) and _text(row.get("gate"))
        }
        rows: list[dict[str, Any]] = []
        for gate_id in GATE_IDS:
            pointer = by_gate.get(gate_id)
            if pointer is None:
                row = {
                    "gate": gate_id,
                    "state": "NOT_READY",
                    "reason": "pointer_missing",
                }
            else:
                row = self.evaluate_pointer(pointer)
            rows.append(row)
        ready = [row["gate"] for row in rows if row["state"] == "READY"]
        not_ready = [row["gate"] for row in rows if row["state"] != "READY"]
        product_state = "GATES_SATISFIED" if not not_ready else "NOT_READY"
        event = self._record(
            "EVALUATE_GATES",
            {"request_id": request_id, "verb": "evaluate_gates"},
            "ALLOW" if product_state == "GATES_SATISFIED" else "HOLD",
            "all_gates_ready" if product_state == "GATES_SATISFIED" else "unresolved_gates",
            {
                "product_state": product_state,
                "ready_count": len(ready),
                "not_ready_count": len(not_ready),
            },
        )
        return {
            "ok": True,
            "product_state": product_state,
            "truth_gate": TRUTH_GATE,
            "ready": ready,
            "not_ready": not_ready,
            "ready_count": len(ready),
            "not_ready_count": len(not_ready),
            "gates": rows,
            "event": event,
            "invented_certification": False,
            "production_ready": False,
            "deployed": False,
            "submitted": False,
            "buyer_accepted": False,
        }

    def evaluate_release(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = _text(request.get("request_id"))
        named = _text(request.get("named_human"))
        verb = _text(request.get("verb") or "release")
        pointers = request.get("pointers") or []
        if not isinstance(pointers, list):
            pointers = []

        if request_id and request_id in self.records:
            event = self._record(verb, request, "DENY", "replay_suppressed")
            return {
                **event,
                "ok": False,
                "effect_count": len(self.records),
            }

        if verb in PRODUCTION_LIKE_VERBS:
            if not named:
                event = self._record(verb, request, "DENY", "named_human_missing")
                return {**event, "ok": False, "effect_count": len(self.records)}
            event = self._record(verb, request, "DENY", "production_destination_absent")
            return {**event, "ok": False, "effect_count": len(self.records)}

        if not named:
            event = self._record(verb, request, "DENY", "named_human_missing")
            return {**event, "ok": False, "effect_count": len(self.records)}
        if named.upper() in AUTONOMOUS_NAMES:
            reason = (
                "held_release_denied"
                if named.upper() == "HELD"
                else "autonomous_release_denied"
            )
            event = self._record(verb, request, "DENY", reason)
            return {**event, "ok": False, "effect_count": len(self.records)}

        snapshot = self.evaluate_gates(pointers, request_id="REL-%s" % (request_id or "anon"))
        if snapshot["product_state"] != "GATES_SATISFIED":
            event = self._record(verb, request, "DENY", "gates_not_ready")
            return {
                **event,
                "ok": False,
                "effect_count": len(self.records),
                "not_ready": snapshot["not_ready"],
            }

        record = {
            "request_id": request_id,
            "released_by": named,
            "at": self.clock,
            "state": "RELEASE_RECORDED",
            "product_state": "GATES_SATISFIED",
            "cash_usd": CASH_USD,
            "production_ready": False,
            "deployed": False,
            "submitted": False,
            "buyer_accepted": False,
        }
        if request_id:
            self.records[request_id] = record
        event = self._record(verb, request, "ALLOW", "named_human_release", {"state": "RELEASE_RECORDED"})
        return {
            **event,
            "ok": True,
            "effect": record,
            "effect_count": len(self.records),
        }


def run_default() -> dict[str, Any]:
    plane = ReleaseReadinessPlane()
    snapshot = plane.evaluate_gates(load_default_pointers(), request_id="DEFAULT")
    snapshot["audit_sha256"] = sha256_hex(plane.audit)
    snapshot["command"] = COMMAND
    snapshot["id"] = LEFTOVER_ID
    snapshot["cash_usd"] = CASH_USD
    snapshot["cites"] = {
        "private_sha": PRIVATE_CITE_SHA,
        "private_path": PRIVATE_CITE_PATH,
        "cloned": False,
    }
    return snapshot


def run_battery() -> dict[str, Any]:
    plane = ReleaseReadinessPlane()
    default = plane.evaluate_gates(load_default_pointers(), request_id="DEFAULT")
    complete_pointers = build_complete_pointers()
    complete = plane.evaluate_gates(complete_pointers, request_id="COMPLETE")

    cases: list[dict[str, Any]] = []

    def _case(case_id: str, title: str, ok: bool, detail: Any) -> None:
        cases.append({"id": case_id, "title": title, "ok": ok, "detail": detail})

    _case(
        "F-01",
        "default cite-only fixture stays NOT_READY on every gate",
        default["product_state"] == "NOT_READY"
        and default["ready_count"] == 0
        and default["not_ready_count"] == 8
        and default["not_ready"] == list(GATE_IDS),
        {"ready": default["ready"], "not_ready": default["not_ready"]},
    )
    _case(
        "F-02",
        "complete synthetic pointers mark every named gate READY",
        complete["product_state"] == "GATES_SATISFIED"
        and complete["ready_count"] == 8
        and complete["not_ready_count"] == 0,
        {"ready": complete["ready"]},
    )

    system = plane.evaluate_release(
        {
            "request_id": "REL-SYSTEM",
            "named_human": "SYSTEM",
            "verb": "release",
            "pointers": complete_pointers,
        }
    )
    _case(
        "F-03",
        "SYSTEM release is denied",
        system["decision"] == "DENY" and system["reason"] == "autonomous_release_denied",
        system,
    )

    unnamed = plane.evaluate_release(
        {
            "request_id": "REL-UNNAMED",
            "named_human": "",
            "verb": "release",
            "pointers": complete_pointers,
        }
    )
    _case(
        "F-04",
        "unnamed release is denied",
        unnamed["decision"] == "DENY" and unnamed["reason"] == "named_human_missing",
        unnamed,
    )

    held = plane.evaluate_release(
        {
            "request_id": "REL-HELD",
            "named_human": "HELD",
            "verb": "release",
            "pointers": complete_pointers,
        }
    )
    _case(
        "F-05",
        "HELD release is denied",
        held["decision"] == "DENY" and held["reason"] == "held_release_denied",
        held,
    )

    early = plane.evaluate_release(
        {
            "request_id": "REL-EARLY",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
            "pointers": load_default_pointers(),
        }
    )
    _case(
        "F-06",
        "named human cannot release while gates are NOT_READY",
        early["decision"] == "DENY" and early["reason"] == "gates_not_ready",
        early,
    )

    first = plane.evaluate_release(
        {
            "request_id": "REL-OK",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
            "pointers": complete_pointers,
        }
    )
    replay = plane.evaluate_release(
        {
            "request_id": "REL-OK",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
            "pointers": complete_pointers,
        }
    )
    _case(
        "F-07",
        "named-human release records once when every gate is READY",
        first["decision"] == "ALLOW"
        and first["reason"] == "named_human_release"
        and first.get("effect", {}).get("state") == "RELEASE_RECORDED"
        and first.get("effect", {}).get("production_ready") is False
        and first.get("effect", {}).get("buyer_accepted") is False,
        first,
    )
    _case(
        "F-08",
        "replay is idempotent — zero duplicate records",
        replay["decision"] == "DENY"
        and replay["reason"] == "replay_suppressed"
        and replay["effect_count"] == 1
        and first["effect_count"] == 1
        and len(plane.records) == 1,
        {"first": first["effect_count"], "replay": replay["effect_count"]},
    )

    forbidden = plane.evaluate_pointer(
        {
            "gate": "demo",
            "kind": "LOCAL_SHA256",
            "label": "PRODUCTION_READY",
            "path": evidence_relpath("demo"),
            "recorded_by": HUMAN_APPROVER,
            "sha": sha256_hex(HERE / evidence_relpath("demo")),
            "source": "commons-synthetic",
        }
    )
    _case(
        "F-09",
        "forbidden certification labels never promote a gate",
        forbidden["state"] == "NOT_READY" and forbidden["reason"] == "forbidden_label",
        forbidden,
    )

    incomplete = plane.evaluate_pointer(
        {
            "gate": "training",
            "kind": "LOCAL_SHA256",
            "label": "MEASURED",
            "path": "",
            "recorded_by": HUMAN_APPROVER,
            "sha": "",
            "source": "commons-synthetic",
        }
    )
    _case(
        "F-10",
        "incomplete pointer stays NOT_READY",
        incomplete["state"] == "NOT_READY" and incomplete["reason"] == "pointer_incomplete",
        incomplete,
    )

    city = plane.evaluate_release(
        {
            "request_id": "REL-CITY",
            "named_human": HUMAN_APPROVER,
            "verb": "contact_city",
            "pointers": complete_pointers,
        }
    )
    bid = plane.evaluate_release(
        {
            "request_id": "REL-BID",
            "named_human": HUMAN_APPROVER,
            "verb": "submit_bid",
            "pointers": complete_pointers,
        }
    )
    _case(
        "F-11",
        "City contact and bid submission stay closed",
        city["decision"] == "DENY"
        and city["reason"] == "production_destination_absent"
        and bid["decision"] == "DENY"
        and bid["reason"] == "production_destination_absent"
        and len(plane.records) == 1,
        {"city": city["reason"], "bid": bid["reason"]},
    )

    deny_count = sum(1 for event in plane.audit if event["decision"] == "DENY")
    audit_sha = sha256_hex(plane.audit)
    contract_failures: list[str] = []
    if default["ready_count"] != GOLDEN_DEFAULT_READY:
        contract_failures.append("default_ready moved")
    if default["not_ready_count"] != GOLDEN_DEFAULT_NOT_READY:
        contract_failures.append("default_not_ready moved")
    if complete["ready_count"] != GOLDEN_COMPLETE_READY:
        contract_failures.append("complete_ready moved")
    if len(plane.records) != GOLDEN_RELEASE_COUNT:
        contract_failures.append("release_count moved")
    if deny_count != GOLDEN_DENY_COUNT:
        contract_failures.append("deny_count %s != %s" % (deny_count, GOLDEN_DENY_COUNT))
    if len(cases) != GOLDEN_CASE_COUNT:
        contract_failures.append("case_count moved")
    if audit_sha != GOLDEN_AUDIT_SHA256:
        contract_failures.append("audit_sha256 moved:%s" % audit_sha)
    ok = all(item["ok"] for item in cases) and not contract_failures
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": COMMAND,
        "truth_gate": TRUTH_GATE,
        "cash_usd": CASH_USD,
        "city_contact": False,
        "city_submission": False,
        "live_lims": False,
        "private_repo_cloned": False,
        "cites": {
            "private_sha": PRIVATE_CITE_SHA,
            "private_path": PRIVATE_CITE_PATH,
        },
        "ok": ok,
        "product_state": default["product_state"],
        "default_ready_count": default["ready_count"],
        "default_not_ready_count": default["not_ready_count"],
        "complete_ready_count": complete["ready_count"],
        "release_count": len(plane.records),
        "deny_count": deny_count,
        "case_count": len(cases),
        "cases_ok": sum(1 for item in cases if item["ok"]),
        "audit_count": len(plane.audit),
        "audit_sha256": audit_sha,
        "failures": contract_failures + [item["id"] for item in cases if not item["ok"]],
        "cases": cases,
        "default": default,
        "complete": complete,
        "invented_certification": False,
        "production_ready": False,
        "deployed": False,
        "submitted": False,
        "buyer_accepted": False,
    }


def summarize(result: dict[str, Any]) -> str:
    lines = [
        "%s cases=%s/%s default=%s/%s-ready complete=%s/8-ready releases=%s cash_usd=0"
        % (
            "PASS" if result["ok"] else "FAIL",
            result["cases_ok"],
            result["case_count"],
            result["default_ready_count"],
            result["default_not_ready_count"],
            result["complete_ready_count"],
            result["release_count"],
        ),
        "product_state %s" % result["product_state"],
        "truth_gate %s" % TRUTH_GATE,
        "audit_sha256 %s" % result["audit_sha256"],
        "cite %s %s" % (PRIVATE_CITE_SHA, PRIVATE_CITE_PATH),
        "command %s" % COMMAND,
    ]
    if not result["ok"]:
        for case in result["cases"]:
            if case["ok"]:
                continue
            lines.append("%s FAIL" % case["id"])
        for item in result["failures"]:
            lines.append(" - %s" % item)
    return "\n".join(lines)


class ReleaseReadinessSelfTest(unittest.TestCase):
    """Fail-closed unittest hosted by the product CLI."""

    def test_battery_holds(self) -> None:
        result = run_battery()
        self.assertTrue(result["ok"], summarize(result))
        self.assertEqual(result["case_count"], GOLDEN_CASE_COUNT)
        self.assertEqual(result["cases_ok"], GOLDEN_CASE_COUNT)
        self.assertEqual(result["product_state"], "NOT_READY")
        self.assertEqual(result["audit_sha256"], GOLDEN_AUDIT_SHA256)

    def test_default_fixture_is_hold(self) -> None:
        snapshot = run_default()
        self.assertEqual(snapshot["product_state"], "NOT_READY")
        self.assertEqual(snapshot["ready_count"], 0)
        self.assertEqual(snapshot["not_ready_count"], 8)

    def test_held_and_system_stay_closed(self) -> None:
        plane = ReleaseReadinessPlane()
        pointers = build_complete_pointers()
        system = plane.evaluate_release(
            {"request_id": "T-SYS", "named_human": "SYSTEM", "pointers": pointers}
        )
        held = plane.evaluate_release(
            {"request_id": "T-HOLD", "named_human": "HELD", "pointers": pointers}
        )
        self.assertEqual(system["reason"], "autonomous_release_denied")
        self.assertEqual(held["reason"], "held_release_denied")
        self.assertEqual(len(plane.records), 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the AquaTrace Lane F release-readiness battery"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--named-human",
        default="",
        help="Name the human for a release probe; default fixture still stays NOT_READY",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseReadinessSelfTest)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    battery = run_battery()
    default = run_default()
    if args.named_human:
        plane = ReleaseReadinessPlane()
        probe = plane.evaluate_release(
            {
                "request_id": "CLI-REL",
                "named_human": args.named_human,
                "verb": "release",
                "pointers": load_default_pointers(),
            }
        )
        battery["named_human_probe"] = {
            "decision": probe["decision"],
            "reason": probe["reason"],
        }
    if args.json:
        printable = {
            key: value
            for key, value in battery.items()
            if key not in {"default", "complete", "cases"}
        }
        printable["default_product_state"] = default["product_state"]
        print(json.dumps(printable, indent=2, sort_keys=True))
    else:
        print(summarize(battery))
        print(
            "default_product_state=%s invented_certification=false production_ready=false"
            % default["product_state"]
        )
    return 0 if battery["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
