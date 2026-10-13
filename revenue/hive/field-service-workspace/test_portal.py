from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from portal import make_server
from workspace import FieldServiceWorkspace, WorkspaceError

TOKEN = "portal-token-0123456789abcdef0123456789abcdef"


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = FieldServiceWorkspace(Path(self.tmp.name) / "portal.db")
        self.ws.create_quote(
            quote_id="portal-q",
            currency="USD",
            customer_token=TOKEN,
            items=[{"item_id": "scope", "description": "Repair <script>alert(1)</script>", "quantity": 1, "unit_cents": 12_345}],
            created_at="2026-09-13T10:00:00Z",
            request_key="create",
        )
        self.ws.publish_quote(quote_id="portal-q", published_at="2026-09-13T10:01:00Z", request_key="publish")
        self.server = make_server(self.ws, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.tmp.cleanup()

    def post(self, path, fields, headers=None):
        body = urlencode(fields).encode("utf-8")
        request = Request(self.base + path, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})})
        return urlopen(request, timeout=2)

    def test_health_truth_and_security_headers(self):
        with urlopen(self.base + "/health", timeout=2) as response:
            body = response.read().decode()
            self.assertIn('"payment_authorized": false', body)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_customer_view_escapes_scope_html(self):
        with self.post("/customer/view", {"quote_id": "portal-q", "token": TOKEN}) as response:
            body = response.read().decode()
        self.assertIn("Repair &lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertNotIn("Repair <script>alert(1)</script>", body)
        self.assertIn("USD 123.45", body)
        self.assertIn("Scope fingerprint", body)

    def test_wrong_and_missing_quote_have_same_public_error(self):
        bodies = []
        for quote_id, token in (("portal-q", "wrong-token-0123456789abcdef0123456789abcdef"), ("missing-q", TOKEN)):
            try:
                self.post("/customer/view", {"quote_id": quote_id, "token": token})
            except HTTPError as exc:
                self.assertEqual(exc.code, 409)
                bodies.append(exc.read().decode())
        self.assertEqual(bodies[0], bodies[1])

    def test_customer_can_approve_quote_through_portal(self):
        fields = {
            "quote_id": "portal-q",
            "token": TOKEN,
            "expected_quote_digest": self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)["quote_digest"],
            "decision": "APPROVE",
            "decided_at": "2026-09-13T10:02:00Z",
            "request_key": "portal-approve",
        }
        with self.post("/customer/quote-decision", fields) as response:
            body = response.read().decode()
        self.assertIn("APPROVED", body)
        snapshot = self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)
        self.assertEqual(snapshot["state"], "APPROVED")
        self.assertIsNotNone(snapshot["job"])

    def test_change_order_scope_is_visible_and_decidable_in_portal(self):
        snapshot = self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)
        approved = self.ws.customer_decide_quote(
            quote_id="portal-q", customer_token=TOKEN, expected_quote_digest=snapshot["quote_digest"],
            decision="APPROVE", decided_at="2026-09-13T10:02:00Z", request_key="api-approve"
        )
        change = self.ws.propose_change(
            job_id=approved["job_id"], change_id="portal-co",
            items=[{"item_id": "added", "description": "Customer-visible added scope", "quantity": 1, "unit_cents": 2_500}],
            proposed_at="2026-09-13T10:03:00Z", request_key="propose-portal-co"
        )
        with self.post("/customer/view", {"quote_id": "portal-q", "token": TOKEN}) as response:
            body = response.read().decode()
        self.assertIn("Customer-visible added scope", body)
        self.assertIn(change["change_digest"], body)
        fields = {
            "job_id": approved["job_id"],
            "change_id": "portal-co",
            "token": TOKEN,
            "expected_change_digest": change["change_digest"],
            "decision": "APPROVE",
            "decided_at": "2026-09-13T10:04:00Z",
            "request_key": "portal-co-approve",
        }
        with self.post("/customer/change-decision", fields) as response:
            decided_body = response.read().decode()
        self.assertIn("APPROVED", decided_body)
        self.assertEqual(self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)["changes"][0]["state"], "APPROVED")

    def test_cross_origin_form_rejected_before_mutation(self):
        fields = {
            "quote_id": "portal-q",
            "token": TOKEN,
            "expected_quote_digest": self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)["quote_digest"],
            "decision": "APPROVE",
            "decided_at": "2026-09-13T10:02:00Z",
            "request_key": "cross-origin",
        }
        try:
            self.post("/customer/quote-decision", fields, headers={"Origin": "https://evil.example"})
        except HTTPError as exc:
            self.assertEqual(exc.code, 403)
        self.assertEqual(self.ws.customer_quote(quote_id="portal-q", customer_token=TOKEN)["state"], "OPEN")

    def test_untrusted_host_header_rejected(self):
        request = Request(self.base + "/health", headers={"Host": "evil.example"})
        try:
            urlopen(request, timeout=2)
        except HTTPError as exc:
            self.assertEqual(exc.code, 403)

    def test_non_loopback_bind_refused(self):
        with self.assertRaises(WorkspaceError):
            make_server(self.ws, "0.0.0.0", 0)

    def test_get_query_does_not_accept_customer_token(self):
        try:
            urlopen(self.base + "/customer/view?quote_id=portal-q&token=" + TOKEN, timeout=2)
        except HTTPError as exc:
            self.assertEqual(exc.code, 404)


if __name__ == "__main__":
    unittest.main()
