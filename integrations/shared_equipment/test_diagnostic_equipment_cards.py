#!/usr/bin/env python3
"""Hermetic: equipment diagnostic contract+receipt+fulfill cards."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from integrations.shared_equipment.peers import GrokBotEquipment

_FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "transferable_roles"
    / "fixtures"
)
_TR = Path(__file__).resolve().parents[1] / "transferable_roles"
if str(_TR) not in sys.path:
    sys.path.insert(0, str(_TR))
from roles import RoleStore  # noqa: E402

DIAG = _FIXTURES / "synthetic_diagnostic_fulfillment_role.json"
CRM = _FIXTURES / "synthetic_crm_followup_role.json"

_EVIDENCE = "2026-09-04T15:00:00-04:00"
_AS_OF_OPEN = "2026-09-04T16:00:00-04:00"
_AS_OF_MISSED = "2026-09-08T10:00:00-04:00"


class DiagnosticEquipmentCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.eq = GrokBotEquipment()
        self.diag = json.loads(DIAG.read_text(encoding="utf-8"))

    def test_contract_card_all_slugs(self) -> None:
        for slug in ("dealer", "referral", "repair", "plant"):
            with self.subTest(slug=slug):
                out = self.eq.call(
                    "diagnostic_contract_card",
                    {"role": self.diag, "slug": slug},
                )
                self.assertTrue(out.get("ok"), out)
                card = out["card"]
                self.assertEqual(card["slug"], slug)
                self.assertTrue(card.get("pointer"))
                # rivet-r4-equipment-contract-diagnostic-usd-all-slugs-20260905-01
                self.assertEqual(card.get("diagnostic_usd"), 199)

    def test_receipt_card_landed_slugs(self) -> None:
        for slug in ("dealer", "referral", "plant"):
            with self.subTest(slug=slug):
                out = self.eq.call(
                    "diagnostic_receipt_card",
                    {"role": self.diag, "slug": slug},
                )
                self.assertTrue(out.get("ok"), out)
                card = out["card"]
                self.assertEqual(card["slug"], slug)
                self.assertEqual(card.get("cash_usd"), 0)
                self.assertIs(card.get("payment_verified"), False)

    def test_receipt_repair_refuses(self) -> None:
        out = self.eq.call(
            "diagnostic_receipt_card",
            {"role": self.diag, "slug": "repair"},
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "role_refused")

    def test_diagnostic_fulfill_deadline_and_sla(self) -> None:
        due = self.eq.call(
            "diagnostic_fulfill_deadline_card",
            {
                "role": self.diag,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
            },
        )
        self.assertTrue(due.get("ok"), due)
        self.assertTrue(due["card"].get("delivery_due_at"))
        open_card = self.eq.call(
            "diagnostic_fulfill_sla_card",
            {
                "role": self.diag,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_OPEN,
            },
        )
        self.assertTrue(open_card.get("ok"), open_card)
        self.assertEqual(open_card["card"].get("sla_status"), "OPEN")
        missed = self.eq.call(
            "diagnostic_fulfill_sla_card",
            {
                "role": self.diag,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_MISSED,
            },
        )
        self.assertTrue(missed.get("ok"), missed)
        self.assertEqual(missed["card"].get("sla_status"), "MISSED")

    def test_open_obligations_cash_card(self) -> None:
        # wedge-r4-equipment-open-obligations-cash-card-20260905-01
        crm = json.loads(CRM.read_text(encoding="utf-8"))
        roles = [crm, self.diag]
        before = json.dumps(roles, sort_keys=True)
        out = self.eq.call(
            "open_obligations_cash_card",
            {"roles": roles},
        )
        self.assertTrue(out.get("ok"), out)
        rows = out["open_obligations"]
        self.assertEqual(json.dumps(roles, sort_keys=True), before)
        expected = {
            (role["role_id"], ob["id"])
            for role in (self.diag,)
            for ob in role["obligations"]
            if ob["status"] == "open"
        }
        self.assertEqual({(row["role_id"], row["obligation_id"]) for row in rows}, expected)
        self.assertTrue(rows)
        for row in rows:
            self.assertIs(row.get("payment_capability"), True)
            self.assertFalse(row["role_id"].startswith("role-synthetic-crm"))
        empty = self.eq.call("open_obligations_cash_card", {"roles": []})
        self.assertFalse(empty.get("ok"))
        self.assertEqual(empty.get("error"), "missing_argument")

    def test_crm_role_refuses(self) -> None:
        crm = json.loads(CRM.read_text(encoding="utf-8"))
        cases = [
            ("diagnostic_contract_card", {"role": crm, "slug": "dealer"}),
            ("diagnostic_receipt_card", {"role": crm, "slug": "dealer"}),
            (
                "diagnostic_fulfill_deadline_card",
                {
                    "role": crm,
                    "slug": "dealer",
                    "usable_evidence_at": _EVIDENCE,
                },
            ),
        ]
        for name, args in cases:
            with self.subTest(name=name):
                out = self.eq.call(name, args)
                self.assertFalse(out.get("ok"))
                self.assertEqual(out.get("error"), "role_refused")

    def test_tools_listed(self) -> None:
        names = {t["name"] for t in self.eq.tools()}
        for name in (
            "diagnostic_contract_card",
            "diagnostic_receipt_card",
            "diagnostic_fulfill_deadline_card",
            "diagnostic_fulfill_sla_card",
            "open_obligations_cash_card",
        ):
            self.assertIn(name, names)

    def _assert_diag_fulfill_cards(self, role: dict) -> None:
        # rivet-r4-equipment-diag-sla-diagnostic-usd-survive-handoff-20260905-01
        due = self.eq.call(
            "diagnostic_fulfill_deadline_card",
            {
                "role": role,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
            },
        )
        self.assertTrue(due.get("ok"), due)
        self.assertTrue(due["card"].get("delivery_due_at"))
        self.assertEqual(due["card"].get("diagnostic_usd"), 199)
        open_card = self.eq.call(
            "diagnostic_fulfill_sla_card",
            {
                "role": role,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_OPEN,
            },
        )
        self.assertTrue(open_card.get("ok"), open_card)
        self.assertEqual(open_card["card"].get("sla_status"), "OPEN")
        self.assertEqual(open_card["card"].get("diagnostic_usd"), 199)
        self.assertEqual(
            open_card["card"].get("refund"),
            "If the accepted diagnostic is not delivered inside the one-business-day window, "
            "the paid diagnostic amount is refunded unless the buyer elects in writing to "
            "receive one free next-business-day repair instead.",
        )
        missed = self.eq.call(
            "diagnostic_fulfill_sla_card",
            {
                "role": role,
                "slug": "dealer",
                "usable_evidence_at": _EVIDENCE,
                "as_of": _AS_OF_MISSED,
            },
        )
        self.assertTrue(missed.get("ok"), missed)
        self.assertEqual(missed["card"].get("sla_status"), "MISSED")
        self.assertEqual(missed["card"].get("diagnostic_usd"), 199)
        self.assertEqual(missed["card"].get("refund"), open_card["card"]["refund"])

    def _assert_diag_contract_receipt_cards(self, role: dict) -> None:
        # rivet-r4-equipment-contract-receipt-survive-handoff-20260905-01
        # rivet-r4-equipment-contract-diagnostic-usd-survive-handoff-20260905-01
        for slug in ("dealer", "referral", "plant"):
            with self.subTest(contract_slug=slug):
                out = self.eq.call(
                    "diagnostic_contract_card",
                    {"role": role, "slug": slug},
                )
                self.assertTrue(out.get("ok"), out)
                card = out["card"]
                self.assertEqual(card["slug"], slug)
                self.assertTrue(card.get("pointer"))
                self.assertEqual(card.get("diagnostic_usd"), 199)
            with self.subTest(receipt_slug=slug):
                out = self.eq.call(
                    "diagnostic_receipt_card",
                    {"role": role, "slug": slug},
                )
                self.assertTrue(out.get("ok"), out)
                card = out["card"]
                self.assertEqual(card["slug"], slug)
                self.assertEqual(card.get("cash_usd"), 0)
        repair = self.eq.call(
            "diagnostic_receipt_card",
            {"role": role, "slug": "repair"},
        )
        self.assertFalse(repair.get("ok"))
        self.assertEqual(repair.get("error"), "role_refused")

    def _assert_open_obligations_cash_card(self, roles: list) -> None:
        # wedge-r4-equipment-open-obligations-cash-survive-handoff-20260905-01
        out = self.eq.call("open_obligations_cash_card", {"roles": roles})
        self.assertTrue(out.get("ok"), out)
        rows = out["open_obligations"]
        paid = []
        for role in roles:
            names = {
                str(route.get("name") or "").strip()
                for route in (role.get("access_routes") or [])
                if isinstance(route, dict)
            }
            if "payment_capability" in names:
                paid.append(role)
        expected = {
            (role["role_id"], ob["id"])
            for role in paid
            for ob in role["obligations"]
            if ob["status"] == "open"
        }
        self.assertEqual(
            {(row["role_id"], row["obligation_id"]) for row in rows}, expected
        )
        self.assertTrue(rows)
        for row in rows:
            self.assertIs(row.get("payment_capability"), True)
            self.assertFalse(row["role_id"].startswith("role-synthetic-crm"))

    def test_diagnostic_cards_survive_transfer(self) -> None:
        # rivet-r4-equipment-cards-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="d-eq-A", harness="hinge")
            store.transfer(
                rid,
                from_session_id="d-eq-A",
                to_session_id="d-eq-B",
                to_harness="rivet",
            )
            self._assert_diag_fulfill_cards(store.get(rid))

    def test_diagnostic_cards_survive_release_equip(self) -> None:
        # rivet-r4-equipment-cards-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="rel-A", harness="hinge")
            store.release(rid, from_session_id="rel-A")
            store.equip(rid, session_id="rel-B", harness="rivet")
            self._assert_diag_fulfill_cards(store.get(rid))

    def test_diagnostic_fulfill_cards_survive_export_import_equip(self) -> None:
        # rivet-r4-equipment-fulfill-handoff-matrix-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="df-exp-A", harness="hinge")
            package = store.export_package(rid)
        with tempfile.TemporaryDirectory() as fresh_dir:
            fresh = RoleStore(fresh_dir)
            imported = fresh.import_package(package)
            fresh.equip(
                imported["role_id"],
                session_id="df-exp-B",
                harness="rivet",
                seat="RIVET",
            )
            self._assert_diag_fulfill_cards(fresh.get(imported["role_id"]))

    def test_diagnostic_contract_receipt_survive_transfer(self) -> None:
        # rivet-r4-equipment-contract-receipt-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="cr-A", harness="hinge")
            store.transfer(
                rid,
                from_session_id="cr-A",
                to_session_id="cr-B",
                to_harness="rivet",
            )
            self._assert_diag_contract_receipt_cards(store.get(rid))

    def test_diagnostic_contract_receipt_survive_export_import_equip(self) -> None:
        # rivet-r4-equipment-contract-receipt-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="cr-exp-A", harness="hinge")
            package = store.export_package(rid)
        with tempfile.TemporaryDirectory() as fresh_dir:
            fresh = RoleStore(fresh_dir)
            imported = fresh.import_package(package)
            fresh.equip(
                imported["role_id"],
                session_id="cr-exp-B",
                harness="rivet",
                seat="RIVET",
            )
            self._assert_diag_contract_receipt_cards(
                fresh.get(imported["role_id"])
            )

    def test_diagnostic_contract_receipt_survive_release_equip(self) -> None:
        # rivet-r4-equipment-contract-receipt-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            role = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            rid = role["role_id"]
            store.equip(rid, session_id="cr-rel-A", harness="hinge")
            store.release(rid, from_session_id="cr-rel-A")
            store.equip(rid, session_id="cr-rel-B", harness="rivet")
            self._assert_diag_contract_receipt_cards(store.get(rid))

    def test_open_obligations_cash_survive_transfer(self) -> None:
        # wedge-r4-equipment-open-obligations-cash-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            crm = store.create(json.loads(CRM.read_text(encoding="utf-8")))
            diag = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            store.equip(diag["role_id"], session_id="cash-d-A", harness="hinge")
            store.transfer(
                diag["role_id"],
                from_session_id="cash-d-A",
                to_session_id="cash-d-B",
                to_harness="rivet",
            )
            self._assert_open_obligations_cash_card(
                [
                    store.get(crm["role_id"]),
                    store.get(diag["role_id"]),
                ]
            )

    def test_open_obligations_cash_survive_export_import_equip(self) -> None:
        # wedge-r4-equipment-open-obligations-cash-survive-handoff-20260905-01
        packages = []
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            for path, sess in (
                (CRM, "cash-exp-crm"),
                (DIAG, "cash-exp-d"),
            ):
                role = store.create(json.loads(path.read_text(encoding="utf-8")))
                store.equip(role["role_id"], session_id=sess, harness="hinge")
                packages.append(store.export_package(role["role_id"]))
        with tempfile.TemporaryDirectory() as fresh_dir:
            fresh = RoleStore(fresh_dir)
            roles = []
            for i, package in enumerate(packages):
                imported = fresh.import_package(package)
                fresh.equip(
                    imported["role_id"],
                    session_id=f"cash-imp-{i}",
                    harness="rivet",
                    seat="RIVET",
                )
                roles.append(fresh.get(imported["role_id"]))
            self._assert_open_obligations_cash_card(roles)

    def test_open_obligations_cash_survive_release_equip(self) -> None:
        # wedge-r4-equipment-open-obligations-cash-survive-handoff-20260905-01
        with tempfile.TemporaryDirectory() as tmp:
            store = RoleStore(tmp)
            crm = store.create(json.loads(CRM.read_text(encoding="utf-8")))
            diag = store.create(json.loads(DIAG.read_text(encoding="utf-8")))
            store.equip(diag["role_id"], session_id="cash-rel-d-A", harness="hinge")
            store.release(diag["role_id"], from_session_id="cash-rel-d-A")
            store.equip(diag["role_id"], session_id="cash-rel-d-B", harness="rivet")
            self._assert_open_obligations_cash_card(
                [
                    store.get(crm["role_id"]),
                    store.get(diag["role_id"]),
                ]
            )


if __name__ == "__main__":
    unittest.main()
