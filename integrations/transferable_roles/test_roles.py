#!/usr/bin/env python3
"""Hermetic tests: create → equip A → transfer B; secrets never exported."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from roles import RoleError, RoleStore, SECRET_FIELD_NAMES
import cli as roles_cli

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_crm_followup_role.json"
DIAGNOSTIC_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic_diagnostic_fulfillment_role.json"
)


class TransferableRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RoleStore(self._tmp.name)
        self.raw = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_equip_transfer_preserves_purpose_and_next_action(self) -> None:
        role = self.store.create(self.raw)
        role_id = role["role_id"]
        purpose = role["purpose"]
        next_actions = [o["next_action"] for o in role["obligations"]]

        equipped = self.store.equip(
            role_id, session_id="session-A", harness="cursor-hinge", seat="HINGE"
        )
        self.assertEqual(equipped["occupant"]["session_id"], "session-A")
        self.assertEqual(equipped["occupant"]["seat"], "HINGE")
        self.assertEqual(equipped["role_id"], role_id)

        handed = self.store.transfer(
            role_id,
            from_session_id="session-A",
            to_session_id="session-B",
            to_harness="claude-tenon",
            seat="TENON",
        )
        self.assertEqual(handed["role_id"], role_id)
        self.assertEqual(handed["purpose"], purpose)
        self.assertEqual(
            [o["next_action"] for o in handed["obligations"]], next_actions
        )
        self.assertEqual(handed["occupant"]["session_id"], "session-B")
        self.assertEqual(handed["occupant"]["prior_session_id"], "session-A")
        self.assertEqual(handed["occupant"]["seat"], "TENON")
        self.assertEqual(handed["transfer_count"], 1)
        loaded = self.store.get(role_id)
        self.assertEqual(loaded["occupant"]["prior_session_id"], "session-A")
        self.assertEqual(loaded["occupant"]["prior_harness"], "cursor-hinge")
        self.assertEqual(loaded["occupant"]["seat"], "TENON")

    def test_export_strips_secrets_and_clears_occupant(self) -> None:
        poisoned = dict(self.raw)
        poisoned["api_key"] = "SHOULD_NEVER_PERSIST"
        poisoned["access_routes"] = list(poisoned.get("access_routes") or []) + [
            {
                "name": "bad",
                "kind": "test",
                "token": "leak-me",
                "base_url": "http://127.0.0.1:9",
            }
        ]
        role = self.store.create(poisoned, role_id="role-scrub-test")
        self.assertNotIn("api_key", role)
        for route in role["access_routes"]:
            self.assertNotIn("token", route)

        self.store.equip(role["role_id"], session_id="A", harness="h1")
        package = self.store.export_package(role["role_id"])
        blob = json.dumps(package)
        self.assertNotIn("SHOULD_NEVER_PERSIST", blob)
        self.assertNotIn("leak-me", blob)
        self.assertIsNone(package.get("occupant"))
        self.assertEqual(package["role_id"], role["role_id"])
        self.assertFalse(package["export_meta"]["includes_secrets"])
        for key in SECRET_FIELD_NAMES:
            self.assertNotIn(key, package)

    def test_equip_while_occupied_fails(self) -> None:
        role = self.store.create(self.raw, role_id="role-busy")
        self.store.equip(role["role_id"], session_id="A", harness="h1")
        with self.assertRaises(RoleError):
            self.store.equip(role["role_id"], session_id="B", harness="h2")

    def test_access_routes_include_peer_gateway_shape(self) -> None:
        role = self.store.create(self.raw)
        names = {r["name"] for r in role["access_routes"]}
        self.assertIn("gemini_peer_tool_gateway", names)
        gateway = next(
            r for r in role["access_routes"] if r["name"] == "gemini_peer_tool_gateway"
        )
        for field in ("submit", "status", "events", "recover"):
            self.assertIn(field, gateway)

    def test_access_routes_include_grokbot_control_g2_shape(self) -> None:
        role = self.store.create(self.raw)
        g2 = next(
            r for r in role["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertEqual(g2["kind"], "grokbot_control")
        self.assertEqual(g2["base_url"], "http://127.0.0.1:8881")
        self.assertEqual(g2["pool_id"], "grokbot")
        self.assertEqual(g2["client"], "integrations/grokbot_control/client.py")
        for field in ("submit", "status", "follow_up", "cancel", "recover", "events"):
            self.assertIn(field, g2)
        # Role must not invent a second pool or bind a live chat window.
        self.assertNotIn("session_id", g2)

    def test_cli_equip_and_transfer_pass_seat(self) -> None:
        """CLI --seat must reach RoleStore (G2 occupant seat ≠ role_id)."""
        store_dir = self._tmp.name
        fixture = str(FIXTURE)
        role_id = "role-cli-seat-test"

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    fixture,
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "equip",
                    role_id,
                    "--session",
                    "session-A",
                    "--harness",
                    "cursor-hinge",
                    "--seat",
                    "HINGE",
                ]
            )
        self.assertEqual(rc, 0)
        equipped = json.loads(buf.getvalue())
        self.assertEqual(equipped["occupant"]["seat"], "HINGE")

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "transfer",
                    role_id,
                    "--from-session",
                    "session-A",
                    "--to-session",
                    "session-B",
                    "--to-harness",
                    "claude-tenon",
                    "--seat",
                    "TENON",
                ]
            )
        self.assertEqual(rc, 0)
        handed = json.loads(buf.getvalue())
        self.assertEqual(handed["occupant"]["seat"], "TENON")
        self.assertEqual(handed["occupant"]["session_id"], "session-B")
        self.assertEqual(handed["role_id"], role_id)

    def test_bind_access_route_stamps_g2_session_and_survives_export(self) -> None:
        role = self.store.create(self.raw, role_id="role-bind-g2")
        purpose = role["purpose"]
        bound = self.store.bind_access_route(
            role["role_id"],
            route_name="grokbot_control_g2",
            session_id="g2-sess-durable-1",
            last_run_id="g2-run-42",
        )
        self.assertEqual(bound["purpose"], purpose)
        g2 = next(
            r for r in bound["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertEqual(g2["session_id"], "g2-sess-durable-1")
        self.assertEqual(g2["last_run_id"], "g2-run-42")
        self.assertEqual(g2["pool_id"], "grokbot")

        self.store.equip(role["role_id"], session_id="occ-A", harness="hinge")
        package = self.store.export_package(role["role_id"])
        self.assertIsNone(package.get("occupant"))
        g2_ex = next(
            r for r in package["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertEqual(g2_ex["session_id"], "g2-sess-durable-1")
        self.assertEqual(g2_ex["last_run_id"], "g2-run-42")

    def test_bind_access_route_unknown_name_fails(self) -> None:
        role = self.store.create(self.raw, role_id="role-bind-miss")
        with self.assertRaises(RoleError):
            self.store.bind_access_route(
                role["role_id"],
                route_name="no-such-route",
                session_id="x",
            )

    def test_cli_bind_route(self) -> None:
        store_dir = self._tmp.name
        role_id = "role-cli-bind"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(FIXTURE),
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "bind-route",
                    role_id,
                    "--route",
                    "grokbot_control_g2",
                    "--session-id",
                    "sess-cli-9",
                    "--last-run-id",
                    "run-cli-9",
                ]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        g2 = next(
            r for r in out["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertEqual(g2["session_id"], "sess-cli-9")
        self.assertEqual(g2["last_run_id"], "run-cli-9")

    def test_unbind_access_route_clears_session_keeps_pool(self) -> None:
        role = self.store.create(self.raw, role_id="role-unbind-g2")
        purpose = role["purpose"]
        self.store.bind_access_route(
            role["role_id"],
            route_name="grokbot_control_g2",
            session_id="g2-sess-unbind-1",
            last_run_id="g2-run-unbind-9",
        )
        unbound = self.store.unbind_access_route(
            role["role_id"],
            route_name="grokbot_control_g2",
        )
        self.assertEqual(unbound["purpose"], purpose)
        g2 = next(
            r for r in unbound["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertNotIn("session_id", g2)
        self.assertNotIn("last_run_id", g2)
        self.assertEqual(g2["pool_id"], "grokbot")
        self.assertEqual(g2["kind"], "grokbot_control")
        self.assertEqual(g2["base_url"], "http://127.0.0.1:8881")

    def test_unbind_access_route_unknown_name_fails(self) -> None:
        role = self.store.create(self.raw, role_id="role-unbind-miss")
        with self.assertRaises(RoleError):
            self.store.unbind_access_route(
                role["role_id"],
                route_name="no-such-route",
            )

    def test_cli_unbind_route(self) -> None:
        store_dir = self._tmp.name
        role_id = "role-cli-unbind"
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(FIXTURE),
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "bind-route",
                    role_id,
                    "--route",
                    "grokbot_control_g2",
                    "--session-id",
                    "sess-cli-unbind",
                    "--last-run-id",
                    "run-cli-unbind",
                ]
            )
        self.assertEqual(rc, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "unbind-route",
                    role_id,
                    "--route",
                    "grokbot_control_g2",
                ]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        g2 = next(
            r for r in out["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertNotIn("session_id", g2)
        self.assertNotIn("last_run_id", g2)
        self.assertEqual(g2["pool_id"], "grokbot")

    def test_release_clears_occupant_keeps_bound_routes(self) -> None:
        role = self.store.create(self.raw, role_id="role-release")
        purpose = role["purpose"]
        self.store.bind_access_route(
            role["role_id"],
            route_name="grokbot_control_g2",
            session_id="g2-keep-me",
            last_run_id="run-keep",
        )
        self.store.equip(
            role["role_id"], session_id="session-A", harness="hinge", seat="HINGE"
        )
        released = self.store.release(role["role_id"], from_session_id="session-A")
        self.assertIsNone(released.get("occupant"))
        self.assertEqual(released["purpose"], purpose)
        self.assertEqual(released["last_released"]["session_id"], "session-A")
        self.assertEqual(released["last_released"]["seat"], "HINGE")
        inspected = self.store.inspect(role["role_id"])
        self.assertEqual(inspected["last_released"]["session_id"], "session-A")
        self.assertEqual(inspected["last_released"]["seat"], "HINGE")
        g2 = next(
            r for r in released["access_routes"] if r["name"] == "grokbot_control_g2"
        )
        self.assertEqual(g2["session_id"], "g2-keep-me")
        self.assertEqual(g2["last_run_id"], "run-keep")

        # Re-equip after release must succeed.
        again = self.store.equip(
            role["role_id"], session_id="session-C", harness="cursor", seat="QUILL"
        )
        self.assertEqual(again["occupant"]["session_id"], "session-C")

    def test_release_wrong_session_fails(self) -> None:
        role = self.store.create(self.raw, role_id="role-release-miss")
        self.store.equip(role["role_id"], session_id="A", harness="h1")
        with self.assertRaises(RoleError):
            self.store.release(role["role_id"], from_session_id="wrong")

    def test_cli_release(self) -> None:
        store_dir = self._tmp.name
        role_id = "role-cli-release"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(FIXTURE),
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "equip",
                    role_id,
                    "--session",
                    "session-A",
                    "--harness",
                    "hinge",
                ]
            )
        self.assertEqual(rc, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "release",
                    role_id,
                    "--from-session",
                    "session-A",
                ]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertIsNone(out.get("occupant"))
        self.assertEqual(out["last_released"]["session_id"], "session-A")

    def test_advance_obligation_updates_one_row(self) -> None:
        role = self.store.create(self.raw, role_id="role-adv")
        purpose = role["purpose"]
        advanced = self.store.advance_obligation(
            role["role_id"],
            "ob-1",
            status="done",
            next_action="Recorded next CRM action from private evidence",
            evidence_pointer="p/hinge-r4-obligation-advance-20260905-01.md",
        )
        self.assertEqual(advanced["purpose"], purpose)
        self.assertEqual(len(advanced["obligations"]), 1)
        ob = advanced["obligations"][0]
        self.assertEqual(ob["id"], "ob-1")
        self.assertEqual(ob["status"], "done")
        self.assertEqual(
            ob["next_action"], "Recorded next CRM action from private evidence"
        )
        self.assertEqual(
            ob["evidence_pointer"], "p/hinge-r4-obligation-advance-20260905-01.md"
        )

    def test_equip_seat_survives_get_round_trip(self) -> None:
        role = self.store.create(self.raw, role_id="role-seat-roundtrip")
        self.store.equip(
            role["role_id"], session_id="session-A", harness="hinge", seat="HINGE"
        )
        loaded = self.store.get(role["role_id"])
        self.assertEqual(loaded["occupant"]["seat"], "HINGE")
        self.assertEqual(loaded["occupant"]["session_id"], "session-A")

    def test_advance_obligation_unknown_id_fails(self) -> None:
        role = self.store.create(self.raw, role_id="role-adv-miss")
        with self.assertRaises(RoleError):
            self.store.advance_obligation(
                role["role_id"], "no-such", status="done"
            )

    def test_advance_obligation_rejects_unknown_status(self) -> None:
        role = self.store.create(self.raw, role_id="role-adv-bad-status")
        with self.assertRaises(RoleError):
            self.store.advance_obligation(
                role["role_id"], "ob-1", status="closed"
            )

    def test_advance_obligation_leaves_siblings(self) -> None:
        raw = deepcopy(self.raw)
        raw["obligations"].append(
            {
                "id": "ob-2",
                "summary": "Keep this sibling untouched",
                "next_action": "Do not rewrite sibling next_action",
                "status": "open",
            }
        )
        role = self.store.create(raw, role_id="role-adv-sib")
        sibling = deepcopy(role["obligations"][1])
        purpose = role["purpose"]
        advanced = self.store.advance_obligation(
            role["role_id"], "ob-1", status="done"
        )
        self.assertEqual(advanced["purpose"], purpose)
        self.assertEqual(advanced["obligations"][0]["status"], "done")
        self.assertEqual(advanced["obligations"][1], sibling)

    def test_cli_advance_obligation(self) -> None:
        store_dir = self._tmp.name
        role_id = "role-cli-adv"
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(FIXTURE),
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "advance-obligation",
                    role_id,
                    "--id",
                    "ob-1",
                    "--status",
                    "blocked",
                    "--next-action",
                    "Wait on LEDGER CRM pointer",
                ]
            )
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["obligations"][0]["status"], "blocked")
        self.assertEqual(
            out["obligations"][0]["next_action"], "Wait on LEDGER CRM pointer"
        )

    def test_import_package_round_trip(self) -> None:
        role = self.store.create(self.raw, role_id="role-import-round")
        purpose = role["purpose"]
        self.store.bind_access_route(
            role["role_id"],
            route_name="grokbot_control_g2",
            session_id="g2-import-sess",
            last_run_id="g2-import-run",
        )
        self.store.equip(
            role["role_id"], session_id="occ-export", harness="hinge", seat="HINGE"
        )
        package = self.store.export_package(role["role_id"])

        with tempfile.TemporaryDirectory() as fresh_dir:
            fresh = RoleStore(fresh_dir)
            imported = fresh.import_package(package)
            self.assertEqual(imported["role_id"], "role-import-round")
            self.assertEqual(imported["purpose"], purpose)
            self.assertIsNone(imported.get("occupant"))
            self.assertNotIn("export_meta", imported)
            g2 = next(
                r
                for r in imported["access_routes"]
                if r["name"] == "grokbot_control_g2"
            )
            self.assertEqual(g2["session_id"], "g2-import-sess")
            self.assertEqual(g2["last_run_id"], "g2-import-run")
            # Importer can equip after adopt.
            equipped = fresh.equip(
                imported["role_id"],
                session_id="occ-import",
                harness="cursor",
                seat="QUILL",
            )
            self.assertEqual(equipped["occupant"]["session_id"], "occ-import")
            self.assertEqual(equipped["role_id"], "role-import-round")

    def test_import_package_refuses_existing_role_id(self) -> None:
        role = self.store.create(self.raw, role_id="role-import-conflict")
        package = self.store.export_package(role["role_id"])
        with self.assertRaises(RoleError):
            self.store.import_package(package)

    def test_cli_import(self) -> None:
        store_dir = self._tmp.name
        role_id = "role-cli-import"
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(FIXTURE),
                    "--role-id",
                    role_id,
                ]
            )
        self.assertEqual(rc, 0)
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "bind-route",
                    role_id,
                    "--route",
                    "grokbot_control_g2",
                    "--session-id",
                    "cli-import-sess",
                ]
            )
        self.assertEqual(rc, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(["--store", store_dir, "export", role_id])
        self.assertEqual(rc, 0)
        package_path = Path(store_dir) / "export-pkg.json"
        package_path.write_text(buf.getvalue(), encoding="utf-8")

        with tempfile.TemporaryDirectory() as fresh_dir:
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc = roles_cli.main(
                    [
                        "--store",
                        fresh_dir,
                        "import",
                        "--file",
                        str(package_path),
                    ]
                )
            self.assertEqual(rc, 0)
            out = json.loads(buf2.getvalue())
            self.assertEqual(out["role_id"], role_id)
            self.assertIsNone(out.get("occupant"))
            g2 = next(
                r for r in out["access_routes"] if r["name"] == "grokbot_control_g2"
            )
            self.assertEqual(g2["session_id"], "cli-import-sess")

    def test_list_open_obligations_rows_then_advance_drops(self) -> None:
        raw = json.loads(DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        role = self.store.create(raw)
        rows = self.store.list_open_obligations()
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [r["obligation_id"] for r in rows],
            ["ob-deadline", "ob-diagnose", "ob-intake", "ob-settle", "ob-sla"],
        )
        for row in rows:
            self.assertEqual(row["role_id"], role["role_id"])
            self.assertEqual(row["purpose"], role["purpose"])
            self.assertTrue(row.get("synthetic"))
            self.assertIn("label", row)
            self.assertIn("summary", row)
            self.assertIn("next_action", row)
        settle = next(r for r in rows if r["obligation_id"] == "ob-settle")
        self.assertIn("evidence_pointer", settle)

        self.store.advance_obligation(role["role_id"], "ob-intake", status="done")
        after = self.store.list_open_obligations()
        self.assertEqual(len(after), 4)
        self.assertNotIn("ob-intake", [r["obligation_id"] for r in after])

    def test_cli_open_obligations(self) -> None:
        store_dir = self._tmp.name
        with redirect_stdout(io.StringIO()):
            rc = roles_cli.main(
                [
                    "--store",
                    store_dir,
                    "create",
                    "--file",
                    str(DIAGNOSTIC_FIXTURE),
                ]
            )
        self.assertEqual(rc, 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = roles_cli.main(["--store", store_dir, "open-obligations"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertIn("open_obligations", out)
        self.assertEqual(len(out["open_obligations"]), 5)
        self.assertEqual(
            out["open_obligations"][0]["role_id"],
            "role-synthetic-diagnostic-fulfillment-20260905",
        )

    def test_diagnostic_fixture_create_open_obligations_and_live_checkouts(self) -> None:
        raw = json.loads(DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        role = self.store.create(raw)
        self.assertTrue(role.get("synthetic"))
        self.assertEqual(
            role["role_id"], "role-synthetic-diagnostic-fulfillment-20260905"
        )
        self.assertEqual(role["credential_custodian"], "existing_secure_stores")
        ids = [o["id"] for o in role["obligations"]]
        self.assertEqual(ids, [o["id"] for o in raw["obligations"]])
        self.assertTrue({"ob-intake", "ob-diagnose", "ob-settle"}.issubset(ids))
        self.assertTrue(all(o["status"] == "open" for o in role["obligations"]))
        names = {r["name"] for r in role["access_routes"]}
        self.assertEqual(
            names,
            {"grokbot_control_g2", "gemini_peer_tool_gateway", "payment_capability"},
        )
        blob = json.dumps(role)
        self.assertIn("buy.stripe.com/3cIdR8gBf6379uF1Oy43S0b", blob)
        self.assertIn("buy.stripe.com/9B600i98N77b9uFeBk43S0c", blob)
        self.assertIn("buy.stripe.com/9B66oGacR2QVdKVeBk43S0d", blob)
        self.assertIn("buy.stripe.com/14AfZgckZ0IN0Y99h043S0e", blob)
        pointers = {k["pointer"] for k in role["knowledge"]}
        self.assertIn("dealer-service-lead-rescue.html", pointers)
        self.assertIn("referral-intake-completeness.html", pointers)
        self.assertIn("repair-booking-preflight.html", pointers)
        self.assertIn("plant-downtime-handoff.html", pointers)


if __name__ == "__main__":
    unittest.main()
