from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from datetime import datetime, timezone

from revenue.delivery_capacity_allocator.cli import main as cli_main
from revenue.delivery_capacity_allocator.engine import (
    DIAGNOSTIC_CAPACITY_CANDIDATE,
    HISTORICAL_REPLAY_ONLY,
    INDEPENDENT_ROOT_AUTHORITY_REQUIRED,
    CapacityError,
    canonical_json,
    compile_bytes,
    compile_historical_bytes,
    sha256_hex,
    strict_json_loads,
    verify_current_bytes,
    verify_historical_bytes,
    write_exclusive,
)

NOW = datetime(2026, 9, 14, 1, 20, 0, tzinfo=timezone.utc)
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def j(obj):
    return canonical_json(obj)


def policy(*, cap=1, age=3600, snapshot="2026-09-14T01:15:00Z"):
    return {
        "schema": "tjlabs.delivery-capacity-policy/v1",
        "policy_id": "tjlabs-main",
        "generation": 7,
        "snapshot_at": snapshot,
        "max_age_seconds": age,
        "slots": [
            {
                "slot_id": "slot-a",
                "service_class": "evidence-pilot",
                "starts_at": "2026-09-14T02:00:00Z",
                "ends_at": "2026-09-14T04:00:00Z",
                "capacity_units": cap,
            },
            {
                "slot_id": "slot-b",
                "service_class": "evidence-pilot",
                "starts_at": "2026-09-14T05:00:00Z",
                "ends_at": "2026-09-14T07:00:00Z",
                "capacity_units": 1,
            },
        ],
    }


def deal(
    deal_id,
    *,
    stage="BUYER_ACCEPTED",
    units=1,
    deadline="2026-09-14T04:30:00Z",
    service="evidence-pilot",
    accepted="2026-09-14T01:00:00Z",
    not_before="2026-09-14T01:30:00Z",
):
    return {
        "deal_id": deal_id,
        "buyer_id": f"buyer-{deal_id}",
        "opportunity_id": f"opp-{deal_id}",
        "service_class": service,
        "requested_units": units,
        "stage": stage,
        "accepted_at": accepted
        if stage in {"BUYER_ACCEPTED", "FUNDED_TO_START", "FULFILLMENT_READY", "CLOSED_SETTLED"}
        else None,
        "not_before": not_before,
        "deadline": deadline,
        "source_receipt_sha256": HEX_A,
    }


def demands(rows, snapshot="2026-09-14T01:16:00Z"):
    return {
        "schema": "tjlabs.delivery-capacity-demand/v1",
        "policy_id": "tjlabs-main",
        "generation": 4,
        "snapshot_at": snapshot,
        "deals": rows,
    }


def reservations(rows=(), snapshot="2026-09-14T01:17:00Z"):
    return {
        "schema": "tjlabs.delivery-capacity-reservations/v1",
        "policy_id": "tjlabs-main",
        "generation": 9,
        "snapshot_at": snapshot,
        "reservations": list(rows),
    }


def active(deal_id, slot="slot-a", units=1, *, buyer=None, opp=None, service="evidence-pilot"):
    return {
        "reservation_id": f"r-{deal_id}",
        "deal_id": deal_id,
        "buyer_id": buyer or f"buyer-{deal_id}",
        "opportunity_id": opp or f"opp-{deal_id}",
        "slot_id": slot,
        "service_class": service,
        "units": units,
        "state": "ACTIVE",
        "source_receipt_sha256": HEX_A,
    }


def compile_obj(p, d, r, when=NOW):
    pb, db, rb = j(p), j(d), j(r)
    return compile_historical_bytes(
        pb,
        db,
        rb,
        expected_policy_sha256=sha256_hex(pb),
        expected_demand_sha256=sha256_hex(db),
        expected_reservations_sha256=sha256_hex(rb),
        evaluated_at=when,
    )


class CapacityTests(unittest.TestCase):
    def test_historical_allocates_diagnostic_only(self):
        out = compile_obj(policy(), demands([deal("a"), deal("b")]), reservations())
        by = {row["deal_id"]: row for row in out["decisions"]}
        self.assertEqual(by["a"]["decision"], DIAGNOSTIC_CAPACITY_CANDIDATE)
        self.assertEqual(by["b"]["decision"], "CAPACITY_HOLD")
        self.assertEqual(out["current_state"], HISTORICAL_REPLAY_ONLY)
        self.assertIn(INDEPENDENT_ROOT_AUTHORITY_REQUIRED, out["global_blockers"])
        self.assertEqual(out["schema"], "tjlabs.delivery-capacity-allocation/v2")
        self.assertNotIn("ALLOCATED_FOR_OWNER_REVIEW", canonical_json(out).decode("utf-8"))

    def test_funded_beats_accepted_diagnostic(self):
        out = compile_obj(
            policy(),
            demands(
                [
                    deal("a", stage="BUYER_ACCEPTED", accepted="2026-09-14T00:00:00Z"),
                    deal("b", stage="FUNDED_TO_START", accepted="2026-09-14T01:10:00Z"),
                ]
            ),
            reservations(),
        )
        by = {row["deal_id"]: row for row in out["decisions"]}
        self.assertEqual(by["b"]["decision"], DIAGNOSTIC_CAPACITY_CANDIDATE)
        self.assertEqual(by["a"]["decision"], "CAPACITY_HOLD")

    def test_earlier_deadline_breaks_same_stage(self):
        p = policy()
        p["slots"] = [p["slots"][0]]
        out = compile_obj(
            p,
            demands(
                [
                    deal("late", deadline="2026-09-14T06:00:00Z"),
                    deal("early", deadline="2026-09-14T04:00:00Z"),
                ]
            ),
            reservations(),
        )
        by = {row["deal_id"]: row for row in out["decisions"]}
        self.assertEqual(by["early"]["decision"], DIAGNOSTIC_CAPACITY_CANDIDATE)
        self.assertEqual(by["late"]["decision"], "CAPACITY_HOLD")

    def test_active_reservation_consumes_capacity(self):
        out = compile_obj(
            policy(), demands([deal("old"), deal("new")]), reservations([active("old")])
        )
        by = {row["deal_id"]: row for row in out["decisions"]}
        self.assertTrue(by["old"]["existing_reservation"])
        self.assertEqual(by["new"]["decision"], "CAPACITY_HOLD")

    def test_active_reservation_overdraw_holds_globally(self):
        out = compile_obj(policy(), demands([deal("old")]), reservations([active("old", units=2)]))
        self.assertIn("ACTIVE_RESERVATION_OVERDRAW", out["diagnostic_blockers"])
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")

    def test_reservation_rebinding_holds_globally(self):
        out = compile_obj(
            policy(), demands([deal("old")]), reservations([active("old", buyer="buyer-evil")])
        )
        self.assertIn("ACTIVE_RESERVATION_DEAL_REBINDING", out["diagnostic_blockers"])

    def test_changed_reserved_units_are_rebinding(self):
        out = compile_obj(
            policy(cap=4),
            demands([deal("a", units=2)]),
            reservations([active("a", units=1)]),
        )
        self.assertIn("ACTIVE_RESERVATION_DEAL_REBINDING", out["diagnostic_blockers"])

    def test_orphan_active_reservation_consumes_and_holds(self):
        out = compile_obj(
            policy(cap=2),
            demands([deal("new")]),
            reservations([active("gone", units=1)]),
        )
        self.assertIn("ACTIVE_RESERVATION_DEAL_MISSING", out["diagnostic_blockers"])
        balances = {row["slot_id"]: row for row in out["slot_balances"]}
        self.assertEqual(balances["slot-a"]["remaining_units"], 1)
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")

    def test_service_mismatch_still_conserves_known_slot_units(self):
        r = active("a", service="wrong-service")
        out = compile_obj(policy(cap=2), demands([deal("a")]), reservations([r]))
        self.assertIn("ACTIVE_RESERVATION_SERVICE_MISMATCH", out["diagnostic_blockers"])
        balances = {row["slot_id"]: row for row in out["slot_balances"]}
        self.assertEqual(balances["slot-a"]["remaining_units"], 1)

    def test_future_acceptance_holds_generation(self):
        out = compile_obj(
            policy(),
            demands([deal("a", accepted="2026-09-14T01:21:00Z")]),
            reservations(),
        )
        self.assertIn("DEAL_ACCEPTED_AT_FUTURE", out["diagnostic_blockers"])
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")

    def test_future_acceptance_on_later_stage_holds_generation(self):
        out = compile_obj(
            policy(),
            demands(
                [
                    deal(
                        "a",
                        stage="FULFILLMENT_READY",
                        accepted="2026-09-14T01:21:00Z",
                    )
                ]
            ),
            reservations([active("a")]),
        )
        self.assertIn("DEAL_ACCEPTED_AT_FUTURE", out["diagnostic_blockers"])
        self.assertNotEqual(out["decisions"][0]["decision"], DIAGNOSTIC_CAPACITY_CANDIDATE)

    def test_past_slot_is_not_new_capacity(self):
        p = policy(snapshot="2026-09-14T01:15:00Z")
        p["slots"] = [
            {
                "slot_id": "past",
                "service_class": "evidence-pilot",
                "starts_at": "2026-09-13T02:00:00Z",
                "ends_at": "2026-09-13T04:00:00Z",
                "capacity_units": 5,
            }
        ]
        d = demands(
            [
                deal(
                    "a",
                    not_before="2026-09-13T01:00:00Z",
                    deadline="2026-09-15T00:00:00Z",
                )
            ]
        )
        out = compile_obj(p, d, reservations())
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")
        self.assertEqual(out["decisions"][0]["reasons"], ["NO_FUTURE_SERVICE_CLASS_SLOT"])

    def test_started_slot_is_not_new_capacity(self):
        p = policy()
        p["slots"] = [
            {
                "slot_id": "started",
                "service_class": "evidence-pilot",
                "starts_at": "2026-09-14T01:10:00Z",
                "ends_at": "2026-09-14T03:00:00Z",
                "capacity_units": 5,
            }
        ]
        out = compile_obj(
            p,
            demands([deal("a", not_before="2026-09-14T01:00:00Z")]),
            reservations(),
        )
        self.assertEqual(out["decisions"][0]["reasons"], ["NO_FUTURE_SERVICE_CLASS_SLOT"])

    def test_exact_start_slot_is_not_new_capacity(self):
        p = policy()
        p["slots"] = [
            {
                "slot_id": "exact-start",
                "service_class": "evidence-pilot",
                "starts_at": "2026-09-14T01:20:00Z",
                "ends_at": "2026-09-14T03:00:00Z",
                "capacity_units": 5,
            }
        ]
        out = compile_obj(
            p,
            demands([deal("a", not_before="2026-09-14T01:00:00Z")]),
            reservations(),
        )
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")
        self.assertEqual(out["decisions"][0]["reasons"], ["NO_FUTURE_SERVICE_CLASS_SLOT"])

    def test_ended_active_reservation_holds(self):
        p = policy()
        p["slots"][0]["starts_at"] = "2026-09-13T02:00:00Z"
        p["slots"][0]["ends_at"] = "2026-09-13T04:00:00Z"
        d = demands(
            [
                deal(
                    "a",
                    not_before="2026-09-13T01:00:00Z",
                    deadline="2026-09-15T00:00:00Z",
                )
            ]
        )
        out = compile_obj(p, d, reservations([active("a")]))
        self.assertIn("ACTIVE_RESERVATION_SLOT_ENDED", out["diagnostic_blockers"])

    def test_duplicate_active_reservations_for_one_deal_hold(self):
        r1 = active("old")
        r2 = active("old", slot="slot-b")
        r2["reservation_id"] = "r-old-2"
        out = compile_obj(
            policy(),
            demands([deal("old", deadline="2026-09-14T08:00:00Z")]),
            reservations([r1, r2]),
        )
        self.assertIn("DEAL_RESERVATION_COLLISION", out["diagnostic_blockers"])

    def test_changed_reserved_source_receipt_is_rebinding(self):
        r = active("a")
        r["source_receipt_sha256"] = HEX_B
        out = compile_obj(policy(), demands([deal("a")]), reservations([r]))
        self.assertIn("ACTIVE_RESERVATION_DEAL_REBINDING", out["diagnostic_blockers"])

    def test_wrong_service_holds_deal(self):
        out = compile_obj(
            policy(), demands([deal("a", service="security-review")]), reservations()
        )
        self.assertEqual(out["decisions"][0]["reasons"], ["NO_SERVICE_CLASS_SLOT"])

    def test_window_mismatch_holds_deal(self):
        out = compile_obj(
            policy(),
            demands([deal("a", deadline="2026-09-14T03:00:00Z")]),
            reservations(),
        )
        self.assertEqual(out["decisions"][0]["reasons"], ["NO_SLOT_WITHIN_DEAL_WINDOW"])

    def test_no_partial_allocation(self):
        out = compile_obj(
            policy(cap=2),
            demands([deal("a", units=3, deadline="2026-09-14T08:00:00Z")]),
            reservations(),
        )
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")
        self.assertEqual(out["decisions"][0]["units"], 0)

    def test_nonaccepted_is_ineligible(self):
        out = compile_obj(
            policy(), demands([deal("a", stage="BUYER_INTEREST")]), reservations()
        )
        self.assertEqual(out["decisions"][0]["decision"], "INELIGIBLE")

    def test_permutation_invariant_diagnostic_allocation(self):
        o1 = compile_obj(policy(), demands([deal("b"), deal("a")]), reservations())
        o2 = compile_obj(policy(), demands([deal("a"), deal("b")]), reservations())
        self.assertEqual(o1["allocation_sha256"], o2["allocation_sha256"])
        self.assertEqual(o1["decisions"], o2["decisions"])
        self.assertNotEqual(o1["receipt_sha256"], o2["receipt_sha256"])

    def test_stale_snapshot_is_diagnostic_blocker(self):
        out = compile_obj(
            policy(age=30, snapshot="2026-09-14T01:00:00Z"),
            demands([deal("a")], snapshot="2026-09-14T01:00:00Z"),
            reservations(snapshot="2026-09-14T01:00:00Z"),
        )
        self.assertIn("POLICY_SNAPSHOT_STALE", out["diagnostic_blockers"])
        self.assertEqual(out["decisions"][0]["decision"], "CAPACITY_HOLD")

    def test_future_snapshot_holds(self):
        out = compile_obj(
            policy(snapshot="2026-09-14T01:30:00Z"),
            demands([deal("a")]),
            reservations(),
        )
        self.assertIn("POLICY_SNAPSHOT_FUTURE", out["diagnostic_blockers"])

    def test_expected_digest_mismatch_rejects(self):
        pb, db, rb = j(policy()), j(demands([deal("a")])), j(reservations())
        with self.assertRaises(CapacityError):
            compile_historical_bytes(
                pb,
                db,
                rb,
                expected_policy_sha256=HEX_C,
                expected_demand_sha256=sha256_hex(db),
                expected_reservations_sha256=sha256_hex(rb),
                evaluated_at=NOW,
            )

    def test_current_api_has_no_caller_clock(self):
        self.assertNotIn("now", inspect.signature(compile_bytes).parameters)
        self.assertNotIn("now", inspect.signature(verify_current_bytes).parameters)
        pb, db, rb = j(policy()), j(demands([deal("a")])), j(reservations())
        kws = dict(
            expected_policy_sha256=sha256_hex(pb),
            expected_demand_sha256=sha256_hex(db),
            expected_reservations_sha256=sha256_hex(rb),
        )
        with self.assertRaises(TypeError):
            compile_bytes(pb, db, rb, now=NOW, **kws)
        receipt = compile_obj(policy(), demands([deal("a")]), reservations())
        with self.assertRaises(TypeError):
            verify_current_bytes(pb, db, rb, canonical_json(receipt), now=NOW, **kws)

    def test_historical_replay_verifies_but_never_current(self):
        p, d, r = policy(), demands([deal("a")]), reservations()
        pb, db, rb = j(p), j(d), j(r)
        kws = dict(
            expected_policy_sha256=sha256_hex(pb),
            expected_demand_sha256=sha256_hex(db),
            expected_reservations_sha256=sha256_hex(rb),
        )
        receipt = compile_historical_bytes(pb, db, rb, evaluated_at=NOW, **kws)
        self.assertTrue(verify_historical_bytes(pb, db, rb, canonical_json(receipt), **kws))
        self.assertFalse(verify_current_bytes(pb, db, rb, canonical_json(receipt), **kws))

    def test_v1_receipt_is_not_accepted_as_v2(self):
        p, d, r = policy(), demands([deal("a")]), reservations()
        pb, db, rb = j(p), j(d), j(r)
        kws = dict(
            expected_policy_sha256=sha256_hex(pb),
            expected_demand_sha256=sha256_hex(db),
            expected_reservations_sha256=sha256_hex(rb),
        )
        receipt = compile_historical_bytes(pb, db, rb, evaluated_at=NOW, **kws)
        receipt["schema"] = "tjlabs.delivery-capacity-allocation/v1"
        self.assertFalse(verify_historical_bytes(pb, db, rb, canonical_json(receipt), **kws))
        self.assertFalse(verify_current_bytes(pb, db, rb, canonical_json(receipt), **kws))

    def test_current_compile_is_fail_closed_on_self_derived_roots(self):
        p, d, r = policy(), demands([deal("a")]), reservations()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        p["snapshot_at"] = d["snapshot_at"] = r["snapshot_at"] = stamp
        from datetime import timedelta
        p["slots"][0]["starts_at"] = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        p["slots"][0]["ends_at"] = (now + timedelta(minutes=70)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d["deals"][0]["accepted_at"] = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d["deals"][0]["not_before"] = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d["deals"][0]["deadline"] = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pb, db, rb = j(p), j(d), j(r)
        receipt = compile_bytes(
            pb,
            db,
            rb,
            expected_policy_sha256=sha256_hex(pb),
            expected_demand_sha256=sha256_hex(db),
            expected_reservations_sha256=sha256_hex(rb),
        )
        self.assertEqual(receipt["current_state"], "HOLD_EXTERNAL_AUTHORITY")
        self.assertIn(INDEPENDENT_ROOT_AUTHORITY_REQUIRED, receipt["global_blockers"])
        self.assertFalse(receipt["source_root_authority"]["operational_authority"])
        self.assertEqual(receipt["decisions"][0]["decision"], DIAGNOSTIC_CAPACITY_CANDIDATE)

    def test_receipt_tamper_rejects_historical(self):
        p, d, r = policy(), demands([deal("a")]), reservations()
        pb, db, rb = j(p), j(d), j(r)
        kws = dict(
            expected_policy_sha256=sha256_hex(pb),
            expected_demand_sha256=sha256_hex(db),
            expected_reservations_sha256=sha256_hex(rb),
        )
        receipt = compile_historical_bytes(pb, db, rb, evaluated_at=NOW, **kws)
        receipt["decisions"][0]["decision"] = "CAPACITY_HOLD"
        self.assertFalse(verify_historical_bytes(pb, db, rb, canonical_json(receipt), **kws))

    def test_bool_is_not_integer(self):
        p = policy()
        p["slots"][0]["capacity_units"] = True
        with self.assertRaises(CapacityError):
            compile_obj(p, demands([deal("a")]), reservations())

    def test_duplicate_json_key_rejects(self):
        with self.assertRaises(CapacityError):
            strict_json_loads(b'{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejects(self):
        with self.assertRaises(CapacityError):
            strict_json_loads(b'{"x": NaN}')

    def test_duplicate_deal_id_rejects(self):
        with self.assertRaises(CapacityError):
            compile_obj(policy(), demands([deal("a"), deal("a")]), reservations())

    def test_duplicate_reservation_id_rejects(self):
        a = active("a")
        b = dict(a)
        with self.assertRaises(CapacityError):
            compile_obj(policy(), demands([deal("a")]), reservations([a, b]))

    def test_all_external_authority_false(self):
        out = compile_obj(policy(), demands([deal("a")]), reservations())
        self.assertTrue(out["authority"])
        self.assertFalse(any(out["authority"].values()))

    def test_write_exclusive_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.json")
            write_exclusive(path, b"one")
            with self.assertRaises(CapacityError):
                write_exclusive(path, b"two")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"one")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_write_exclusive_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            target = os.path.join(td, "target")
            link = os.path.join(td, "link")
            with open(target, "wb") as fh:
                fh.write(b"safe")
            os.symlink(target, link)
            with self.assertRaises(CapacityError):
                write_exclusive(link, b"evil")
            with open(target, "rb") as fh:
                self.assertEqual(fh.read(), b"safe")

    def test_cli_current_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p, d, r = j(policy()), j(demands([deal("a")])), j(reservations())
            paths = {}
            for name, data in (("p", p), ("d", d), ("r", r)):
                path = os.path.join(td, name + ".json")
                with open(path, "wb") as fh:
                    fh.write(data)
                paths[name] = path
            out = os.path.join(td, "receipt.json")
            rc = cli_main(
                [
                    "compile",
                    "--policy",
                    paths["p"],
                    "--demands",
                    paths["d"],
                    "--reservations",
                    paths["r"],
                    "--policy-sha",
                    sha256_hex(p),
                    "--demand-sha",
                    sha256_hex(d),
                    "--reservations-sha",
                    sha256_hex(r),
                    "--out",
                    out,
                ]
            )
            self.assertEqual(rc, 3)
            self.assertTrue(os.path.exists(out))
            verify_rc = cli_main(
                [
                    "verify",
                    "--policy",
                    paths["p"],
                    "--demands",
                    paths["d"],
                    "--reservations",
                    paths["r"],
                    "--policy-sha",
                    sha256_hex(p),
                    "--demand-sha",
                    sha256_hex(d),
                    "--reservations-sha",
                    sha256_hex(r),
                    "--receipt",
                    out,
                ]
            )
            self.assertEqual(verify_rc, 3)


if __name__ == "__main__":
    unittest.main()
