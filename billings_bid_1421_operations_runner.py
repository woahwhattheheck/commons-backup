#!/usr/bin/env python3
"""Billings Bid 1421 operations runner.

Demand: billings-bid-1421-operations-runner-20260831-01

Working nonproduction RBAC runner. Executes the ten denial cases
described in the already-landed operations package. Cite, do not remint:
p/billings-bid-1421-operations-package-20260831-01.md blob 3952a794.

Synthetic directory and fixtures only. No City contact. No bid
submission. No live LIMS. Production-like verbs need a named human
and still fail closed because this runner has no production destination.

Official command:
    python3 billings_bid_1421_operations_runner.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEFTOVER_ID = "billings-bid-1421-operations-runner-20260831-01"
SCHEMA = "commons-billings-bid-1421-operations-runner/v1"
PACKAGE_ID = "billings-bid-1421-operations-package-20260831-01"
PACKAGE_RECEIPT_BLOB = "3952a794451222d2feb64a1a212efc16b8238930"
PACKAGE_SHA256 = "49d6d56a5726d598966e8185ec84f3401faf405a9f8a0ccb9804248ad13885bc"
COMMAND = "python3 billings_bid_1421_operations_runner.py"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
CASH_USD = 0

HERE = Path(__file__).resolve().parent
PACK = HERE / "revenue" / "billings_bid_1421" / "operations_runner"
DIRECTORY_PATH = PACK / "directory.json"
CASES_PATH = PACK / "cases.json"
SOURCE_PATH = PACK / "source.json"
PACKAGE_PATH = HERE / "revenue" / "billings_bid_1421" / "operations_package" / "billings-bid-1421-operations-package.md"
PACKAGE_RECEIPT_PATH = HERE / "p" / f"{PACKAGE_ID}.md"

CLOCK = "2026-08-31T12:00:00Z"
CASE_IDS = tuple(f"RBAC-{i:02d}" for i in range(1, 11))

ROLE_MATRIX = {
    "field_collector": frozenset({"create_sample", "transfer_sample"}),
    "analyst": frozenset({"enter_result", "import_result"}),
    "qa_reviewer": frozenset({"hold_result", "review_result"}),
    "reporting_approver": frozenset({"release_report"}),
    "integration": frozenset({"ingest_adapter"}),
    "support": frozenset({"read_ticket"}),
    "configurator": frozenset({"propose_change"}),
    "change_approver": frozenset({"approve_change"}),
    "administrator": frozenset({"administer_users"}),
}

PRODUCTION_LIKE_VERBS = frozenset(
    {"contact_city", "submit_bid", "connect_live_lims", "write_production"}
)
PRIVILEGED_VERBS = frozenset(
    {
        "create_sample",
        "transfer_sample",
        "enter_result",
        "import_result",
        "hold_result",
        "review_result",
        "release_result",
        "release_report",
        "ingest_adapter",
        "administer_users",
        "elevate_role",
        "erase_audit",
        "propose_change",
        "approve_change",
        "read_ticket",
    }
) | PRODUCTION_LIKE_VERBS

# Locked after the first measured battery. Fail-closed if the journal moves.
GOLDEN_AUDIT_SHA256 = "31e0fbd9981daa017a914900887335623f849ab12b624202a080946c91e9e3f1"
GOLDEN_EFFECT_COUNT = 1
GOLDEN_DENY_COUNT = 16
GOLDEN_ALLOW_COUNT = 1
GOLDEN_CASE_COUNT = 10


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


def parse_clock(stamp: str) -> datetime:
    raw = stamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_directory(path: Path = DIRECTORY_PATH) -> dict[str, Any]:
    return load_json(path)


def load_cases(path: Path = CASES_PATH) -> dict[str, Any]:
    return load_json(path)


class NonproductionRBACPlane:
    """Deny-by-default RBAC plane for the Bid 1421 operations battery."""

    def __init__(self, directory: dict[str, Any] | None = None) -> None:
        spec = deepcopy(directory if directory is not None else load_directory())
        self.environment = spec.get("environment", "NONPRODUCTION")
        self.clock = _text(spec.get("clock") or CLOCK)
        self.actors: dict[str, dict[str, Any]] = spec.get("actors") or {}
        self.resources: dict[str, dict[str, Any]] = spec.get("resources") or {}
        self.audit: list[dict[str, Any]] = []
        self.effects: dict[str, dict[str, Any]] = {}
        self.seq = 0

    def lookup_actor(self, actor_id: str) -> dict[str, Any] | None:
        name = _text(actor_id)
        if not name:
            return None
        row = self.actors.get(name)
        return deepcopy(row) if isinstance(row, dict) else None

    def lookup_resource(self, resource_id: str | None) -> dict[str, Any]:
        name = _text(resource_id)
        if not name:
            return {}
        row = self.resources.get(name)
        return deepcopy(row) if isinstance(row, dict) else {}

    def _stamp(self) -> str:
        return self.clock

    def _record(
        self,
        request: dict[str, Any],
        decision: str,
        reason: str,
        effect: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        event = {
            "seq": self.seq,
            "at": self._stamp(),
            "request_id": _text(request.get("request_id")),
            "actor": _text(request.get("actor")),
            "verb": _text(request.get("verb")),
            "resource_id": _text(request.get("resource_id")) or None,
            "decision": decision,
            "reason": reason,
            "environment": self.environment,
            "cash_usd": CASH_USD,
            "city_contact": False,
            "city_submission": False,
            "live_lims": False,
        }
        self.audit.append(event)
        return {
            **event,
            "effect": effect,
            "effect_count": len(self.effects),
            "ok": decision == "ALLOW",
        }

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = _text(request.get("request_id"))
        actor_id = _text(request.get("actor"))
        verb = _text(request.get("verb"))
        resource_id = _text(request.get("resource_id")) or None
        resource = self.lookup_resource(resource_id)

        if request_id and request_id in self.effects:
            return self._record(request, "DENY", "replay_suppressed")

        actor = self.lookup_actor(actor_id)
        if actor is None:
            return self._record(request, "DENY", "unknown_actor")
        if bool(actor.get("disabled")):
            return self._record(request, "DENY", "disabled_actor")

        if verb in PRODUCTION_LIKE_VERBS:
            named = _text(request.get("named_human"))
            if not named:
                return self._record(request, "DENY", "named_human_missing")
            return self._record(request, "DENY", "production_destination_absent")

        if self.environment != "NONPRODUCTION":
            return self._record(request, "DENY", "environment_not_nonproduction")

        if verb == "elevate_role":
            return self._record(request, "DENY", "silent_elevate_refused")
        if verb == "erase_audit":
            return self._record(request, "DENY", "erase_audit_refused")
        if verb == "release_result":
            return self._record(request, "DENY", "release_refused")

        if verb in {"approve_change", "approve_result"}:
            owner = _text(resource.get("proposer") or resource.get("entered_by"))
            if owner and owner == actor_id:
                return self._record(request, "DENY", "separation_of_duties")

        role = _text(actor.get("role"))
        verbs = ROLE_MATRIX.get(role, frozenset())
        if verbs.isdisjoint({verb}):
            return self._record(request, "DENY", "role_cannot_use_verb")

        if role == "support":
            start = parse_clock(_text(actor.get("window_start") or "1970-01-01T00:00:00Z"))
            end = parse_clock(_text(actor.get("window_end") or "1970-01-01T00:00:00Z"))
            now = parse_clock(self.clock)
            if not _text(actor.get("approved_by")):
                return self._record(request, "DENY", "support_not_endorsed")
            if not (start <= now <= end):
                return self._record(request, "DENY", "support_window_closed")

        if verb in {"create_sample", "transfer_sample"}:
            site = _text(request.get("site") or resource.get("site"))
            allowed_sites = {_text(item) for item in (actor.get("sites") or [])}
            if not site or site not in allowed_sites:
                return self._record(request, "DENY", "site_scope")

        if verb in {"enter_result", "import_result"}:
            method_id = _text(request.get("method_id") or resource.get("method_id"))
            grants = actor.get("methods") or []
            match = next(
                (
                    row
                    for row in grants
                    if isinstance(row, dict) and _text(row.get("method_id")) == method_id
                ),
                None,
            )
            if match is None:
                return self._record(request, "DENY", "method_not_current")
            expires = parse_clock(_text(match.get("expires_at") or "1970-01-01T00:00:00Z"))
            if expires < parse_clock(self.clock):
                return self._record(request, "DENY", "method_expired")

        if verb == "release_report":
            if not resource or resource.get("kind") != "report":
                return self._record(request, "DENY", "report_not_ready")
            if not bool(resource.get("reconciled")) or not bool(resource.get("approved")):
                return self._record(request, "DENY", "report_not_ready")

        if verb == "ingest_adapter":
            adapter_id = _text(request.get("adapter_id"))
            adapters = {_text(item) for item in (actor.get("adapters") or [])}
            if not adapter_id or adapter_id not in adapters:
                return self._record(request, "DENY", "adapter_scope")

        effect = {
            "request_id": request_id,
            "actor": actor_id,
            "verb": verb,
            "resource_id": resource_id,
            "at": self._stamp(),
        }
        if request_id:
            self.effects[request_id] = effect
        return self._record(request, "ALLOW", "applied", effect=effect)


def _attempt_matches(got: dict[str, Any], attempt: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if got.get("decision") != attempt.get("expect_decision"):
        failures.append(
            "decision %s != %s"
            % (got.get("decision"), attempt.get("expect_decision"))
        )
    if got.get("reason") != attempt.get("expect_reason"):
        failures.append(
            "reason %s != %s" % (got.get("reason"), attempt.get("expect_reason"))
        )
    expected_effects = attempt.get("expect_effects")
    if expected_effects is not None and got.get("effect_count") != expected_effects:
        failures.append(
            "effect_count %s != %s" % (got.get("effect_count"), expected_effects)
        )
    return failures


def _audit_gaps(plane: NonproductionRBACPlane, decisions: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    by_request: dict[str, list[dict[str, Any]]] = {}
    for event in plane.audit:
        by_request.setdefault(event["request_id"], []).append(event)
    for row in decisions:
        request_id = row["request_id"]
        events = by_request.get(request_id) or []
        if not events:
            gaps.append("missing audit for %s" % request_id)
            continue
        matched = next(
            (
                event
                for event in events
                if event["actor"] == row["actor"]
                and event["verb"] == row["verb"]
                and event["decision"] == row["decision"]
                and event["reason"] == row["reason"]
                and event.get("at")
            ),
            None,
        )
        if matched is None:
            gaps.append("audit mismatch for %s" % request_id)
    privileged = [
        event
        for event in plane.audit
        if event["verb"] in PRIVILEGED_VERBS
    ]
    if len(privileged) != len(plane.audit):
        gaps.append("audit row missing privileged verb coverage")
    return gaps


def run_battery(
    directory: dict[str, Any] | None = None,
    cases: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plane = NonproductionRBACPlane(directory)
    spec = deepcopy(cases if cases is not None else load_cases())
    rows = spec.get("cases") or []
    by_id = {row["id"]: row for row in rows if isinstance(row, dict) and row.get("id")}
    missing = [case_id for case_id in CASE_IDS if case_id not in by_id]
    case_results: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for case_id in CASE_IDS:
        case = by_id.get(case_id) or {}
        kind = _text(case.get("kind"))
        failures: list[str] = []
        attempt_results: list[dict[str, Any]] = []
        if kind == "audit_coverage":
            failures.extend(_audit_gaps(plane, decisions))
            if not decisions:
                failures.append("no prior decisions to attribute")
        else:
            for attempt in case.get("attempts") or []:
                got = plane.evaluate(attempt)
                attempt_failures = _attempt_matches(got, attempt)
                failures.extend(attempt_failures)
                attempt_results.append(
                    {
                        "request_id": got["request_id"],
                        "actor": got["actor"],
                        "verb": got["verb"],
                        "decision": got["decision"],
                        "reason": got["reason"],
                        "effect_count": got["effect_count"],
                        "failures": attempt_failures,
                    }
                )
                decisions.append(
                    {
                        "request_id": got["request_id"],
                        "actor": got["actor"],
                        "verb": got["verb"],
                        "decision": got["decision"],
                        "reason": got["reason"],
                    }
                )
        # Case 9 is checked again after later cases so coverage stays complete.
        if case_id == "RBAC-10":
            later_gaps = _audit_gaps(plane, decisions)
            rbac09 = next(
                (item for item in case_results if item["id"] == "RBAC-09"),
                None,
            )
            if rbac09 is not None and later_gaps:
                rbac09["failures"].extend(later_gaps)
                rbac09["ok"] = False
        case_results.append(
            {
                "id": case_id,
                "title": case.get("title"),
                "package_item": case.get("package_item"),
                "ok": not failures,
                "failures": failures,
                "attempts": attempt_results,
            }
        )

    deny_count = sum(1 for row in decisions if row["decision"] == "DENY")
    allow_count = sum(1 for row in decisions if row["decision"] == "ALLOW")
    audit_sha = sha256_hex(plane.audit)
    all_ok = not missing and all(item["ok"] for item in case_results)
    contract_failures: list[str] = []
    if missing:
        contract_failures.append("missing cases %s" % missing)
    if len(case_results) != GOLDEN_CASE_COUNT:
        contract_failures.append("case_count %s != %s" % (len(case_results), GOLDEN_CASE_COUNT))
    if deny_count != GOLDEN_DENY_COUNT:
        contract_failures.append("deny_count %s != %s" % (deny_count, GOLDEN_DENY_COUNT))
    if allow_count != GOLDEN_ALLOW_COUNT:
        contract_failures.append("allow_count %s != %s" % (allow_count, GOLDEN_ALLOW_COUNT))
    if len(plane.effects) != GOLDEN_EFFECT_COUNT:
        contract_failures.append(
            "effect_count %s != %s" % (len(plane.effects), GOLDEN_EFFECT_COUNT)
        )
    if audit_sha != GOLDEN_AUDIT_SHA256:
        contract_failures.append("audit_sha256 moved")
    ok = all_ok and not contract_failures
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": COMMAND,
        "truth_gate": TRUTH_GATE,
        "cash_usd": CASH_USD,
        "city_contact": False,
        "city_submission": False,
        "live_lims": False,
        "cites": {
            "operations_package_id": PACKAGE_ID,
            "operations_package_receipt_blob": PACKAGE_RECEIPT_BLOB,
            "operations_package_sha256": PACKAGE_SHA256,
        },
        "ok": ok,
        "case_count": len(case_results),
        "cases_ok": sum(1 for item in case_results if item["ok"]),
        "deny_count": deny_count,
        "allow_count": allow_count,
        "effect_count": len(plane.effects),
        "audit_count": len(plane.audit),
        "audit_sha256": audit_sha,
        "failures": contract_failures
        + [item["id"] for item in case_results if not item["ok"]],
        "cases": case_results,
        "audit": plane.audit,
        "effects": plane.effects,
    }


def prove_package_untouched() -> list[str]:
    failures: list[str] = []
    if not PACKAGE_PATH.is_file():
        return ["operations package missing"]
    digest = sha256_hex(PACKAGE_PATH)
    if digest != PACKAGE_SHA256:
        failures.append("operations package sha256 moved")
    if PACKAGE_RECEIPT_PATH.is_file():
        import subprocess

        blob = subprocess.check_output(
            ["git", "hash-object", str(PACKAGE_RECEIPT_PATH)],
            cwd=HERE,
            text=True,
        ).strip()
        if blob != PACKAGE_RECEIPT_BLOB:
            failures.append("operations package receipt blob moved")
    return failures


def production_like_probe(named_human: str = "") -> dict[str, Any]:
    plane = NonproductionRBACPlane()
    missing = plane.evaluate(
        {
            "request_id": "PROD-CITY",
            "actor": "SYN-ADMIN-1",
            "verb": "contact_city",
            "named_human": "",
        }
    )
    bid = plane.evaluate(
        {
            "request_id": "PROD-BID",
            "actor": "SYN-ADMIN-1",
            "verb": "submit_bid",
            "named_human": named_human or "SYN-NAMED-HUMAN",
        }
    )
    lims = plane.evaluate(
        {
            "request_id": "PROD-LIMS",
            "actor": "SYN-ADMIN-1",
            "verb": "connect_live_lims",
            "named_human": named_human or "SYN-NAMED-HUMAN",
        }
    )
    ok = (
        missing["decision"] == "DENY"
        and missing["reason"] == "named_human_missing"
        and bid["decision"] == "DENY"
        and bid["reason"] == "production_destination_absent"
        and lims["decision"] == "DENY"
        and lims["reason"] == "production_destination_absent"
        and len(plane.effects) == 0
    )
    return {
        "ok": ok,
        "named_human_missing": missing,
        "submit_bid": bid,
        "connect_live_lims": lims,
        "effect_count": len(plane.effects),
    }


def control_allows() -> dict[str, Any]:
    """Legitimate nonproduction work still goes through the same plane."""
    plane = NonproductionRBACPlane()
    rows = [
        plane.evaluate(
            {
                "request_id": "CTRL-FIELD",
                "actor": "SYN-FIELD-WEST",
                "verb": "create_sample",
                "site": "WEST",
            }
        ),
        plane.evaluate(
            {
                "request_id": "CTRL-ANALYST",
                "actor": "SYN-ANALYST-PH",
                "verb": "enter_result",
                "resource_id": "RESULT-PH-1",
                "method_id": "SM-4500-H+",
            }
        ),
        plane.evaluate(
            {
                "request_id": "CTRL-QA",
                "actor": "SYN-QA-1",
                "verb": "hold_result",
                "resource_id": "RESULT-PH-1",
            }
        ),
        plane.evaluate(
            {
                "request_id": "CTRL-INTEG",
                "actor": "SYN-INTEG-PH",
                "verb": "ingest_adapter",
                "adapter_id": "fixture-ph-meter-1",
            }
        ),
        plane.evaluate(
            {
                "request_id": "CTRL-SUPPORT",
                "actor": "SYN-SUPPORT-ACTIVE",
                "verb": "read_ticket",
                "resource_id": "TICKET-1",
            }
        ),
    ]
    return {
        "ok": all(row["ok"] for row in rows),
        "rows": rows,
        "effect_count": len(plane.effects),
    }


def summarize(result: dict[str, Any]) -> str:
    lines = [
        "%s cases=%s/%s deny=%s allow=%s effects=%s cash_usd=0"
        % (
            "PASS" if result["ok"] else "FAIL",
            result["cases_ok"],
            result["case_count"],
            result["deny_count"],
            result["allow_count"],
            result["effect_count"],
        ),
        "audit_sha256 %s" % result["audit_sha256"],
        "command %s" % COMMAND,
    ]
    if not result["ok"]:
        for case in result["cases"]:
            if case["ok"]:
                continue
            lines.append("%s FAIL" % case["id"])
            for item in case["failures"]:
                lines.append(" - %s" % item)
        for item in result["failures"]:
            if item not in {case["id"] for case in result["cases"]}:
                lines.append(" - %s" % item)
    return "\n".join(lines)


class OperationsRunnerSelfTest(unittest.TestCase):
    """Fail-closed unittest hosted by the product CLI."""

    def test_ten_denial_cases_pass(self) -> None:
        result = run_battery()
        self.assertTrue(result["ok"], summarize(result))
        self.assertEqual(result["case_count"], 10)
        self.assertEqual(result["cases_ok"], 10)
        self.assertEqual(result["deny_count"], GOLDEN_DENY_COUNT)
        self.assertEqual(result["allow_count"], GOLDEN_ALLOW_COUNT)
        self.assertEqual(result["effect_count"], GOLDEN_EFFECT_COUNT)
        self.assertEqual(result["audit_sha256"], GOLDEN_AUDIT_SHA256)

    def test_package_untouched(self) -> None:
        self.assertEqual(prove_package_untouched(), [])

    def test_production_like_stays_closed(self) -> None:
        probe = production_like_probe(named_human="SYN-NAMED-HUMAN")
        self.assertTrue(probe["ok"], probe)

    def test_control_allows_still_work(self) -> None:
        control = control_allows()
        self.assertTrue(control["ok"], control)
        self.assertEqual(control["effect_count"], 5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Bid 1421 nonproduction RBAC denial battery"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--named-human",
        default="",
        help="Name the human for a production-like probe; the probe still fail-closes",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(OperationsRunnerSelfTest)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    battery = run_battery()
    package_failures = prove_package_untouched()
    probe = production_like_probe(named_human=args.named_human)
    control = control_allows()
    battery["package_untouched"] = not package_failures
    battery["production_like_closed"] = probe["ok"]
    battery["control_allows_ok"] = control["ok"]
    if package_failures or not probe["ok"] or not control["ok"]:
        battery["ok"] = False
        battery["failures"] = list(battery["failures"]) + package_failures
        if not probe["ok"]:
            battery["failures"].append("production_like_not_closed")
        if not control["ok"]:
            battery["failures"].append("control_allows_failed")
    if args.json:
        printable = {
            key: value
            for key, value in battery.items()
            if key not in {"audit", "effects"}
        }
        print(json.dumps(printable, indent=2, sort_keys=True))
    else:
        print(summarize(battery))
        print(
            "package_untouched=%s production_like_closed=%s control_allows=%s"
            % (
                battery["package_untouched"],
                battery["production_like_closed"],
                battery["control_allows_ok"],
            )
        )
    return 0 if battery["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
