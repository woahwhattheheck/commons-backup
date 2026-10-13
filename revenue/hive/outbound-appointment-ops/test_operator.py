#!/usr/bin/env python3
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import app


class OperatorAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.operator = app.OperatorApp(Path(self.tmp.name) / "desk.sqlite3")
        self.addCleanup(self.operator.close)
        self.operator.action({
            "action": "campaign",
            "operation_id": "op-campaign",
            "campaign_id": "campaign",
            "customer_name": "Synthetic Seller",
            "offer": "a bounded appointment workflow",
            "source_policy": "customer-provided lawful source only",
        })

    def prospect(self, pid="p1", route="route-1"):
        return self.operator.action({
            "action": "prospect",
            "operation_id": f"op-prospect-{pid}",
            "campaign_id": "campaign",
            "prospect_id": pid,
            "organization": "Synthetic Buyer",
            "contact_name": "Sample Contact",
            "route_ref": route,
            "source_ref": "example://authorized-source/1",
            "lawful_source_note": "synthetic fixture standing in for customer-provided lawful source",
            "relevance_note": "the synthetic organization manually coordinates appointments",
        })

    def reply(self, kind="interested", pid="p1", suffix="1"):
        return self.operator.action({
            "action": "reply",
            "operation_id": f"op-reply-{pid}-{suffix}",
            "prospect_id": pid,
            "reply_id": f"reply-{pid}-{suffix}",
            "kind": kind,
            "note": f"Synthetic {kind} reply",
            "received_at": "2026-09-09T17:00:00Z",
        })

    def slot(self, slot="slot-1"):
        return self.operator.action({
            "action": "slot",
            "operation_id": f"op-{slot}",
            "slot_id": slot,
            "starts_at": "2026-09-10T15:00:00Z",
            "ends_at": "2026-09-10T15:30:00Z",
        })

    def test_state_projects_landed_desk_without_transport_claim(self):
        self.prospect()
        draft = self.operator.action({"action": "draft", "operation_id": "op-draft", "prospect_id": "p1"})
        state = self.operator.state()
        self.assertEqual(state["transport"], "NONE")
        self.assertFalse(state["provider_mutation"])
        self.assertEqual(len(state["campaigns"]), 1)
        self.assertEqual(len(state["prospects"]), 1)
        row = state["prospects"][0]
        self.assertEqual(row["draft_state"], "UNSENT")
        self.assertEqual(row["draft_subject"], draft["subject"])
        self.assertEqual(row["suppressed"], 0)

    def test_opt_out_is_visible_and_blocks_future_draft(self):
        self.prospect()
        self.reply("opt_out")
        state = self.operator.state()
        self.assertEqual(state["prospects"][0]["status"], "SUPPRESSED")
        self.assertEqual(state["prospects"][0]["latest_reply"], "opt_out")
        self.assertEqual(state["prospects"][0]["suppressed"], 1)
        self.assertEqual(state["suppressions"][0]["route_ref"], "route-1")
        with self.assertRaisesRegex(Exception, "suppressed"):
            self.operator.action({"action": "draft", "operation_id": "op-draft-after", "prospect_id": "p1"})

    def test_interested_reply_to_local_booking_and_exports(self):
        self.prospect()
        self.reply("interested")
        self.slot()
        booking = self.operator.action({
            "action": "book",
            "operation_id": "op-book",
            "prospect_id": "p1",
            "slot_id": "slot-1",
        })
        self.assertEqual(booking["transport"], "LOCAL_HANDOFF_ONLY")
        state = self.operator.state()
        self.assertEqual(state["prospects"][0]["status"], "BOOKED")
        self.assertEqual(state["slots"][0]["state"], "BOOKED")
        self.assertEqual(state["bookings"][0]["booking_id"], booking["booking_id"])
        crm = self.operator.crm_csv("campaign")
        self.assertIn("BOOKED", crm)
        ics = self.operator.booking_ics(booking["booking_id"])
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("Local handoff only", ics)

    def test_operation_key_retry_and_conflicting_reuse_are_preserved(self):
        payload = {
            "action": "prospect",
            "operation_id": "same-op",
            "campaign_id": "campaign",
            "prospect_id": "p1",
            "organization": "Synthetic Buyer",
            "contact_name": "Sample Contact",
            "route_ref": "route-1",
            "source_ref": "example://authorized-source/1",
            "lawful_source_note": "synthetic authorized-source stand-in",
            "relevance_note": "manual scheduling",
        }
        first = self.operator.action(payload)
        second = self.operator.action(payload)
        self.assertEqual(first, second)
        changed = dict(payload, relevance_note="changed input")
        with self.assertRaisesRegex(Exception, "different input"):
            self.operator.action(changed)
        self.assertEqual(self.operator.state()["status"]["counts"]["prospects"], 1)

    def test_send_name_reaches_dispatch_without_transport(self):
        result = self.operator.action({"action": "send", "operation_id": "op-send"})
        self.assertEqual(result["kind"], "OPERATOR_INPUT")
        self.assertEqual(result["action"], "send")
        self.assertEqual(result["transport"], "NONE")
        self.assertFalse(result["provider_mutation"])
        self.assertFalse(result["applied"])
        state = self.operator.state()
        self.assertEqual(state["transport"], "NONE")
        self.assertEqual(state["status"]["counts"].get("transport_actions", 0), 0)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.operator = app.OperatorApp(Path(self.tmp.name) / "desk.sqlite3")
        self.server = app.Server(("127.0.0.1", 0), self.operator)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.addCleanup(self._close)

    def _close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.operator.close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.headers.get_content_type(), response.read()

    def post(self, payload):
        req = urllib.request.Request(
            self.base + "/api",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_real_http_serves_operator_and_state(self):
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html")
        text = body.decode()
        self.assertIn("Outbound Appointment Operations", text)
        self.assertIn("does not send email", text)
        status, content_type, body = self.get("/state")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        state = json.loads(body)
        self.assertEqual(state["transport"], "NONE")
        self.assertFalse(state["provider_mutation"])

    def test_real_http_action_round_trip(self):
        status, result = self.post({
            "action": "campaign",
            "operation_id": "http-op-campaign",
            "campaign_id": "http-campaign",
            "customer_name": "Synthetic HTTP Seller",
            "offer": "local appointment operations",
            "source_policy": "customer-provided lawful source only",
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["kind"], "CAMPAIGN")
        _, _, body = self.get("/state")
        state = json.loads(body)
        self.assertEqual(state["campaigns"][0]["campaign_id"], "http-campaign")

    def test_send_name_http_has_no_transport(self):
        status, result = self.post({"action": "send", "operation_id": "op-send"})
        self.assertEqual(status, 200)
        self.assertEqual(result["transport"], "NONE")
        self.assertFalse(result["provider_mutation"])
        self.assertFalse(result["applied"])
        _, _, body = self.get("/state")
        state = json.loads(body)
        self.assertEqual(state["transport"], "NONE")

    def test_http_state_survives_concurrent_worker_threads(self):
        def once():
            status, content_type, body = self.get("/state")
            self.assertEqual(status, 200)
            self.assertEqual(content_type, "application/json")
            return json.loads(body)["transport"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: once(), range(16)))
        self.assertEqual(results, ["NONE"] * 16)


if __name__ == "__main__":
    unittest.main()
