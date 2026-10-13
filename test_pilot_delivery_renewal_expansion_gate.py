import builtins
import copy
import unittest
from datetime import datetime, timedelta, timezone

from revenue.pilot_delivery_renewal_expansion_gate.test_gate import *  # noqa: F401,F403
from revenue.pilot_delivery_renewal_expansion_gate import common as common_module
from revenue.pilot_delivery_renewal_expansion_gate import engine
from revenue.pilot_delivery_renewal_expansion_gate import model as model_module


class SplitViewDict(dict):
    """Adversarial mapping with distinct lookup and iteration views."""

    def __init__(self, lookup_view, items_view):
        super().__init__(lookup_view)
        self._lookup_view = lookup_view
        self._items_view = items_view

    def keys(self):
        return self._lookup_view.keys()

    def __getitem__(self, key):
        return self._lookup_view[key]

    def items(self):
        return self._items_view.items()


class SplitViewList(list):
    """Non-exact list container; current trusted ingress must reject it."""


class CurrentSemanticGenerationTests(unittest.TestCase):
    def test_current_generation_ignores_ordinary_semantic_global_rebinding(self):
        dnr_packet = current_packet()
        dnr_packet["route_control"]["state"] = "DNR"
        before = engine.compile_current(dnr_packet)
        self.assertEqual(before["state"], "DNR")

        sentinel = object()
        mutations = [
            (engine, "DNR", "READY_FOR_RENEWAL_REVIEW"),
            (engine, "READY", "DNR"),
            (engine, "HOLD_ACCEPTANCE", "READY_FOR_RENEWAL_REVIEW"),
            (engine, "HOLD_PAYMENT", "READY_FOR_RENEWAL_REVIEW"),
            (engine, "HOLD_WINDOW", "READY_FOR_RENEWAL_REVIEW"),
            (engine, "HOLD_EVIDENCE", "READY_FOR_RENEWAL_REVIEW"),
            (engine, "_decision", lambda *_args, **_kwargs: ("READY_FOR_RENEWAL_REVIEW", [])),
            (engine, "_normalize", lambda value, _now: value),
            (engine, "_compile", lambda *_args, **_kwargs: {"state": "READY_FOR_RENEWAL_REVIEW"}),
            (engine, "_commercial_generation", lambda _normalized: 999),
            (engine, "_expected_total", lambda _normalized: 0),
            (engine, "authority_flags", lambda: {"external_send_authorized": True}),
            (engine, "max", lambda *_args, **_kwargs: 999),
            (engine, "dict", lambda *_args, **_kwargs: {"external_send_authorized": True}),
            (engine, "str", bytes),
            (engine, "enumerate", lambda *_args, **_kwargs: ()),
            (engine, "type", lambda _value: SplitViewDict),
            (model_module, "_age", lambda *_args, **_kwargs: 0),
            (model_module, "_source", lambda value, *_args, **_kwargs: value),
            (model_module, "PAYMENT_MAX_AGE_SECONDS", 10**18),
            (model_module, "ROUTE_MAX_AGE_SECONDS", 10**18),
            (model_module, "ROUTE_STATES", {"CLEAR", "UNASSESSED", "ACTIVE_OTHER_OWNER", "DNR", "READY_FOR_RENEWAL_REVIEW"}),
            (common_module, "_age", lambda *_args, **_kwargs: 0),
            (common_module, "_dt", lambda _value: datetime(2000, 1, 1, tzinfo=timezone.utc)),
            (common_module, "_source", lambda value, *_args, **_kwargs: value),
            (common_module, "canonical_json", lambda _value: b"{}\n"),
            (common_module, "digest", lambda _value: "0" * 64),
        ]
        previous = []
        try:
            for owner, name, replacement in mutations:
                previous.append((owner, name, getattr(owner, name, sentinel)))
                setattr(owner, name, replacement)
            after = engine.compile_current(dnr_packet)
            checked = engine.verify_receipt(dnr_packet, before)
        finally:
            for owner, name, old in reversed(previous):
                if old is sentinel:
                    delattr(owner, name)
                else:
                    setattr(owner, name, old)

        self.assertEqual(after["state"], "DNR")
        self.assertEqual(after["reasons"], ["ROUTE_DNR"])
        self.assertTrue(all(value is False for value in after["authority"].values()))
        self.assertNotEqual(after["receipt_digest"], "0" * 64)
        self.assertTrue(checked["integrity_valid"])
        self.assertEqual(checked["prior_state"], "DNR")
        self.assertEqual(checked["current_state"], "DNR")
        self.assertTrue(checked["still_current"])

    def test_rebinding_freshness_helpers_cannot_revive_stale_payment(self):
        stale = current_packet()
        old = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=200)
        old_text = old.strftime("%Y-%m-%dT%H:%M:%SZ")
        stale["payment"]["observed_at"] = old_text
        stale["payment"]["source"]["observed_at"] = old_text
        error_type = engine.GateError

        previous = [
            (model_module, "_age", model_module._age),
            (model_module, "PAYMENT_MAX_AGE_SECONDS", model_module.PAYMENT_MAX_AGE_SECONDS),
            (common_module, "_age", common_module._age),
        ]
        try:
            model_module._age = lambda *_args, **_kwargs: 0
            model_module.PAYMENT_MAX_AGE_SECONDS = 10**18
            common_module._age = lambda *_args, **_kwargs: 0
            with self.assertRaisesRegex(error_type, "stale evidence"):
                engine.compile_current(stale)
        finally:
            for owner, name, old_value in reversed(previous):
                setattr(owner, name, old_value)

    def test_process_builtin_max_rebinding_cannot_rewrite_commercial_generation(self):
        p = current_packet()
        for row in p["milestones"]:
            row["commercial_generation"] = 1
        p["payment"]["commercial_generation"] = 1

        control = engine.compile_current(p)
        self.assertEqual(control["state"], engine.HOLD_ACCEPTANCE)
        self.assertEqual(control["commercial_generation"], 2)

        real_max = builtins.max

        def forged_max(*args, **kwargs):
            if len(args) == 1 and not kwargs and type(args[0]) is list and args[0] == [1, 2]:
                return 1
            return real_max(*args, **kwargs)

        try:
            builtins.max = forged_max
            mutated = engine.compile_current(p)
        finally:
            builtins.max = real_max

        self.assertEqual(mutated["state"], engine.HOLD_ACCEPTANCE)
        self.assertEqual(mutated["commercial_generation"], 2)
        self.assertTrue(all(value is False for value in mutated["authority"].values()))

    def test_process_builtin_isinstance_rebinding_cannot_admit_bool_as_integer(self):
        p = current_packet()
        p["baseline"]["generation"] = True
        with self.assertRaisesRegex(engine.GateError, "integer required"):
            engine.compile_current(p)

        real_isinstance = builtins.isinstance
        captured = None

        def forged_isinstance(value, kind):
            if value is True and kind is bool:
                return False
            return real_isinstance(value, kind)

        try:
            builtins.isinstance = forged_isinstance
            try:
                engine.compile_current(p)
            except engine.GateError as exc:
                captured = str(exc)
        finally:
            builtins.isinstance = real_isinstance

        self.assertIsNotNone(captured)
        self.assertIn("integer required", captured)

    def test_split_view_receipt_cannot_cross_authentication_phases(self):
        p = current_packet()
        honest = engine.compile_current(p)
        forged = copy.deepcopy(honest)
        forged["authority"]["external_send_authorized"] = True
        unsigned = dict(forged)
        unsigned.pop("receipt_digest")
        forged["receipt_digest"] = engine.digest(unsigned)

        split = SplitViewDict(forged, honest)
        self.assertTrue(split["authority"]["external_send_authorized"])
        with self.assertRaisesRegex(engine.GateError, "exact built-in plain-JSON"):
            engine.verify_receipt(p, split)

    def test_split_view_packet_is_rejected_recursively_before_semantics(self):
        p = current_packet()
        receipt = engine.compile_current(p)
        honest_route = copy.deepcopy(p["route_control"])
        forged_route = copy.deepcopy(honest_route)
        forged_route["state"] = "DNR"
        p["route_control"] = SplitViewDict(forged_route, honest_route)

        with self.assertRaisesRegex(engine.GateError, "exact built-in plain-JSON"):
            engine.compile_current(p)
        with self.assertRaisesRegex(engine.GateError, "exact built-in plain-JSON"):
            engine.verify_receipt(p, receipt)

    def test_nonexact_list_container_is_rejected_recursively(self):
        p = current_packet()
        p["milestones"] = SplitViewList(p["milestones"])
        with self.assertRaisesRegex(engine.GateError, "exact built-in plain-JSON"):
            engine.compile_current(p)

    def test_lone_surrogate_packet_and_receipt_text_fail_as_gate_errors(self):
        p = current_packet()
        receipt = engine.compile_current(p)
        p["baseline"]["source"]["source_id"] = "bad\ud800text"
        with self.assertRaisesRegex(engine.GateError, "valid UTF-8 text required"):
            engine.compile_current(p)

        bad_receipt = copy.deepcopy(receipt)
        bad_receipt["truth"]["ready_means"] = "bad\ud800text"
        with self.assertRaisesRegex(engine.GateError, "valid UTF-8 text required"):
            engine.verify_receipt(current_packet(), bad_receipt)

    def test_lone_surrogate_object_key_fails_without_echoing_key(self):
        p = current_packet()
        p["baseline"]["bad\ud800key"] = None
        try:
            engine.compile_current(p)
        except engine.GateError as exc:
            message = str(exc)
            self.assertIn("valid UTF-8 text required", message)
            self.assertNotIn("\ud800", message)
        else:
            self.fail("expected GateError")

    def test_pathological_integers_fail_before_canonical_serialization(self):
        huge = 10**5000
        p = current_packet()
        p["baseline"]["generation"] = huge
        with self.assertRaisesRegex(engine.GateError, "integer outside supported range"):
            engine.compile_current(p)

        p = current_packet()
        receipt = engine.compile_current(p)
        receipt["effective_total_cents"] = huge
        with self.assertRaisesRegex(engine.GateError, "integer outside supported range"):
            engine.verify_receipt(p, receipt)

    def test_oversized_packet_list_fails_before_child_traversal(self):
        bomb = [object()] + [None] * 12_000
        p = {"bomb": bomb, **current_packet()}
        with self.assertRaisesRegex(engine.GateError, "node budget exceeded"):
            engine.compile_current(p)

    def test_oversized_receipt_list_fails_before_child_traversal(self):
        p = current_packet()
        receipt = engine.compile_current(p)
        bomb = [object()] + [None] * 12_000
        oversized = {"bomb": bomb, **receipt}
        with self.assertRaisesRegex(engine.GateError, "node budget exceeded"):
            engine.verify_receipt(p, oversized)


if __name__ == "__main__":
    unittest.main()
