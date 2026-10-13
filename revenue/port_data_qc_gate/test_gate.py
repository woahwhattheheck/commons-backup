from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

import revenue.port_data_qc_gate.gate as gate
from revenue.port_data_qc_gate.gate import (
    CURRENT_TEMPORAL_AUTHORITY,
    HISTORICAL_TEMPORAL_AUTHORITY,
    GateInputError,
    _evaluate_historical_at,
    _verify_historical,
    evaluate,
    verify,
)


def policy(max_age: int = 600):
    return {
        "schema": "port-data-qc-policy/v1",
        "max_snapshot_age_seconds": max_age,
        "sources": {
            "edi": {
                "schema_version": "v1",
                "allowed_fields": ["container", "status"],
                "required_fields": ["container", "status"],
            }
        },
    }


def event(*, observed: str, effective: str | None = None):
    return {
        "source_id": "edi",
        "event_id": "e1",
        "record_id": "r1",
        "business_key": "CONT-1",
        "schema_version": "v1",
        "previous_event_id": None,
        "effective_at": effective or observed,
        "observed_at": observed,
        "values": {"container": "CONT-1", "status": "ARRIVED"},
    }


def snapshot(captured: str, *, observed: str | None = None):
    observed = observed or captured
    return {
        "schema": "port-data-qc-snapshot/v1",
        "capture_complete": True,
        "captured_at": captured,
        "events": [event(observed=observed)],
    }


def rehash(receipt):
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    raw = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    receipt["receipt_sha256"] = hashlib.sha256(raw).hexdigest()


class HistoricalBoundaryTests(unittest.TestCase):
    def test_historical_replay_is_explicitly_non_current(self):
        s = snapshot("2026-09-14T12:00:00Z")
        result = _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:01Z")
        self.assertEqual("PASS", result["receipt"]["decision"])
        self.assertEqual(HISTORICAL_TEMPORAL_AUTHORITY, result["receipt"]["temporal_authority"])
        self.assertTrue(_verify_historical(result, policy=policy(), snapshot=s))
        self.assertFalse(verify(result, policy=policy(), snapshot=s))

    def test_fractional_expiry_is_not_truncated(self):
        s = snapshot("2026-09-14T12:00:00Z")
        result = _evaluate_historical_at(policy(60), s, evaluated_at="2026-09-14T12:01:00.500000Z")
        self.assertEqual(60, result["receipt"]["snapshot_age_seconds"])
        self.assertEqual("HOLD", result["receipt"]["decision"])
        self.assertIn("SNAPSHOT_STALE", result["receipt"]["holds"])

    def test_historical_label_cannot_be_readdressed_to_current(self):
        s = snapshot("2026-09-14T12:00:00Z")
        result = _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:01Z")
        result["receipt"]["temporal_authority"] = CURRENT_TEMPORAL_AUTHORITY
        rehash(result["receipt"])
        self.assertFalse(verify(result, policy=policy(), snapshot=s))

    def test_future_observation_is_rejected_by_wrapper_contract(self):
        s = snapshot("2026-09-14T12:00:00Z", observed="2026-09-14T12:00:01Z")
        with self.assertRaises(GateInputError):
            _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:02Z")


class CurrentAuthorityTests(unittest.TestCase):
    def fresh(self):
        now = datetime.now(timezone.utc)
        captured = (now - timedelta(seconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        return snapshot(captured), policy(60)

    def test_public_evaluate_has_no_caller_clock(self):
        s, p = self.fresh()
        with self.assertRaises(TypeError):
            evaluate(p, s, evaluated_at="2000-01-01T00:00:00Z")

    def test_current_api_owns_time_and_verifies(self):
        s, p = self.fresh()
        result = evaluate(p, s)
        self.assertEqual("PASS", result["receipt"]["decision"])
        self.assertEqual(CURRENT_TEMPORAL_AUTHORITY, result["receipt"]["temporal_authority"])
        self.assertTrue(verify(result, policy=p, snapshot=s))

    def test_old_snapshot_cannot_mint_current_pass(self):
        s = snapshot("2026-01-01T00:00:00Z")
        result = evaluate(policy(60), s)
        self.assertEqual("HOLD", result["receipt"]["decision"])
        self.assertIn("SNAPSHOT_STALE", result["receipt"]["holds"])

    def test_current_verifier_rejects_self_consistent_report_forgery(self):
        s, p = self.fresh()
        result = evaluate(p, s)
        result["report"]["rows"][0]["values"]["status"] = "FORGED"
        result["receipt"]["report_sha256"] = hashlib.sha256(
            json.dumps(result["report"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        rehash(result["receipt"])
        self.assertFalse(verify(result, policy=p, snapshot=s))

    def test_current_verifier_rejects_wrong_bound_inputs(self):
        s, p = self.fresh()
        result = evaluate(p, s)
        other = copy.deepcopy(s)
        other["events"][0]["values"]["status"] = "OTHER"
        self.assertFalse(verify(result, policy=p, snapshot=other))

    def test_current_verifier_rejects_extra_receipt_authority(self):
        s, p = self.fresh()
        result = evaluate(p, s)
        result["receipt"]["release_authorized"] = True
        rehash(result["receipt"])
        self.assertFalse(verify(result, policy=p, snapshot=s))

    def test_rebinding_public_datetime_global_cannot_select_clock(self):
        class FakeDateTime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2000, 1, 1, tzinfo=timezone.utc)

        original = gate.datetime
        gate.datetime = FakeDateTime
        try:
            s, p = self.fresh()
            result = gate.evaluate(p, s)
        finally:
            gate.datetime = original
        parsed = gate._parse_utc(result["receipt"]["evaluated_at"], name="receipt time")
        self.assertGreater(parsed.year, 2025)


class FrozenEngineRegressionTests(unittest.TestCase):
    def test_duplicate_event_identity_still_collapses(self):
        s = snapshot("2026-09-14T12:00:00Z")
        s["events"].append(copy.deepcopy(s["events"][0]))
        result = _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:01Z")
        self.assertEqual(1, result["receipt"]["duplicate_event_count"])
        self.assertEqual("PASS", result["receipt"]["decision"])

    def test_conflicting_duplicate_identity_still_holds(self):
        s = snapshot("2026-09-14T12:00:00Z")
        conflict = copy.deepcopy(s["events"][0])
        conflict["values"]["status"] = "HELD"
        s["events"].append(conflict)
        result = _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:01Z")
        self.assertEqual("HOLD", result["receipt"]["decision"])
        self.assertIn("EVENT_ID_CONFLICT", result["receipt"]["holds"])

    def test_unknown_field_is_still_rejected(self):
        s = snapshot("2026-09-14T12:00:00Z")
        s["events"][0]["values"]["surprise"] = "x"
        with self.assertRaises(GateInputError):
            _evaluate_historical_at(policy(), s, evaluated_at="2026-09-14T12:00:01Z")

    def test_bool_policy_age_is_still_rejected(self):
        p = policy()
        p["max_snapshot_age_seconds"] = True
        with self.assertRaises(GateInputError):
            _evaluate_historical_at(p, snapshot("2026-09-14T12:00:00Z"), evaluated_at="2026-09-14T12:00:01Z")


if __name__ == "__main__":
    unittest.main()
