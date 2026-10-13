from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from http.server import ThreadingHTTPServer

from app import StudioHandler, loopback_browser_authorities, serve
from studio import StudioError, StudioStore, load_config


class BrowserProductTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        fixture = Path(__file__).with_name("example_creator.json")
        self.config_path = self.root / "creator.json"
        self.config_path.write_bytes(fixture.read_bytes())
        cfg, cfg_sha = load_config(self.config_path)
        self.store = StudioStore(self.root / "studio.sqlite3", cfg, cfg_sha)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
        self.server.store = self.store
        self.server.csrf = "fixed-test-token"
        self.port = self.server.server_address[1]
        self.server.allowed_hosts, self.server.allowed_origins = loopback_browser_authorities("127.0.0.1", self.port)
        self.origin = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.store.close()
        self.tmp.cleanup()

    def request(self, method: str, path: str, fields: dict[str, str] | None = None, *, headers: dict[str, str] | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = None
        req_headers = dict(headers or {})
        if fields is not None:
            body = urllib.parse.urlencode(fields)
            req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        conn.request(method, path, body=body, headers=req_headers)
        res = conn.getresponse()
        data = res.read()
        out_headers = dict(res.getheaders())
        status = res.status
        conn.close()
        return status, out_headers, data

    def post(self, path: str, fields: dict[str, str]):
        return self.request(
            "POST",
            path,
            {"csrf": "fixed-test-token", **fields},
            headers={"Origin": self.origin},
        )

    def seed_workflow(self) -> None:
        status, _, _ = self.post(
            "/class/save",
            {"class_id": "ceramics-a", "label": "Ceramics A", "rostered": "35", "expected": "28", "notes": ""},
        )
        self.assertEqual(status, 303)
        for fields in [
            {"item_id": "clay", "label": "Clay bags", "mode": "per_attendee_consumable", "units_per_attendee": "1", "units_per_class": "0", "program_units": "0", "package_size": "1", "notes": ""},
            {"item_id": "wheel", "label": "Banding wheels", "mode": "per_class_shared", "units_per_attendee": "0", "units_per_class": "2", "program_units": "0", "package_size": "1", "notes": ""},
            {"item_id": "rollers", "label": "Texture rollers", "mode": "program_shared", "units_per_attendee": "0", "units_per_class": "0", "program_units": "6", "package_size": "3", "notes": ""},
        ]:
            status, _, _ = self.post("/item/save", fields)
            self.assertEqual(status, 303)

    def test_customer_completes_core_workflow_and_receives_exports(self) -> None:
        self.seed_workflow()
        status, headers, raw = self.request("GET", "/export.json")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        packet = json.loads(raw)
        by_id = {row["item_id"]: row for row in packet["supply_plan"]}
        self.assertEqual(packet["summary"]["rostered_total"], 35)
        self.assertEqual(packet["summary"]["expected_total"], 28)
        self.assertEqual(by_id["clay"]["needed_units"], 28)
        self.assertEqual(by_id["wheel"]["needed_units"], 2)
        self.assertEqual(by_id["rollers"]["needed_units"], 6)

        status, headers, csv_bytes = self.request("GET", "/export.csv")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"per_attendee_consumable", csv_bytes)

    def test_changing_expected_attendance_changes_only_attendee_consumable(self) -> None:
        self.seed_workflow()
        _, _, first_raw = self.request("GET", "/export.json")
        first = json.loads(first_raw)
        status, _, _ = self.post(
            "/class/save",
            {"class_id": "ceramics-a", "label": "Ceramics A", "rostered": "35", "expected": "20", "notes": ""},
        )
        self.assertEqual(status, 303)
        _, _, second_raw = self.request("GET", "/export.json")
        second = json.loads(second_raw)
        a = {r["item_id"]: r["needed_units"] for r in first["supply_plan"]}
        b = {r["item_id"]: r["needed_units"] for r in second["supply_plan"]}
        self.assertEqual((a["clay"], b["clay"]), (28, 20))
        self.assertEqual((a["wheel"], b["wheel"]), (2, 2))
        self.assertEqual((a["rollers"], b["rollers"]), (6, 6))

    def test_onboarding_and_pricing_are_customer_visible_without_payment_authority(self) -> None:
        status, _, onboarding = self.request("GET", "/onboarding")
        self.assertEqual(status, 200)
        self.assertIn(b"rostered", onboarding)
        self.assertIn(b"shared per class", onboarding)
        status, _, pricing = self.request("GET", "/pricing")
        self.assertEqual(status, 200)
        self.assertIn(b"$3,000.00 fixed scoped MVP sprint", pricing)
        self.assertIn(b"does not process payment or imply a sale", pricing)

    def test_support_packet_is_local_artifact_not_send(self) -> None:
        status, _, raw = self.post("/support/packet", {"topic": "Need help", "details": "Please review shared tool assumptions."})
        self.assertEqual(status, 200)
        packet = json.loads(raw)
        self.assertFalse(packet["send_authority"])
        self.assertEqual(packet["support_route"], self.store.config.support_route)

    def test_bad_csrf_fails_closed(self) -> None:
        status, _, raw = self.request(
            "POST",
            "/class/save",
            {"csrf": "wrong", "class_id": "x", "label": "X", "rostered": "1", "expected": "1", "notes": ""},
            headers={"Origin": self.origin},
        )
        self.assertEqual(status, 400)
        self.assertIn(b"invalid form token", raw)
        self.assertEqual(self.store.snapshot()["classes"], [])

    def test_transfer_encoding_is_rejected_before_mutation(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        body = "csrf=fixed-test-token&class_id=x&label=X&rostered=1&expected=1&notes="
        conn.putrequest("POST", "/class/save")
        conn.putheader("Origin", self.origin)
        conn.putheader("Transfer-Encoding", "chunked")
        conn.endheaders()
        conn.send(f"{len(body):X}\r\n{body}\r\n0\r\n\r\n".encode())
        res = conn.getresponse()
        raw = res.read()
        status = res.status
        conn.close()
        self.assertEqual(status, 400)
        self.assertIn(b"Transfer-Encoding is not supported", raw)
        self.assertEqual(self.store.snapshot()["classes"], [])

    def test_untrusted_host_cannot_read_csrf_page_or_export(self) -> None:
        status, _, raw = self.request("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)
        self.assertIn(b"untrusted browser host", raw)
        self.assertNotIn(b"fixed-test-token", raw)

        self.seed_workflow()
        status, _, raw = self.request("GET", "/export.json", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)
        self.assertNotIn(b"ceramics-a", raw)
        self.assertNotIn(b"fixed-test-token", raw)

    def test_cross_site_origin_cannot_mutate_even_with_valid_csrf(self) -> None:
        status, _, raw = self.request(
            "POST",
            "/class/save",
            {"csrf": "fixed-test-token", "class_id": "x", "label": "X", "rostered": "1", "expected": "1", "notes": ""},
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(status, 403)
        self.assertIn(b"untrusted browser origin", raw)
        self.assertNotIn(b"fixed-test-token", raw)
        self.assertEqual(self.store.snapshot()["classes"], [])

    def test_missing_origin_cannot_mutate_even_with_valid_csrf(self) -> None:
        status, _, raw = self.request(
            "POST",
            "/class/save",
            {"csrf": "fixed-test-token", "class_id": "x", "label": "X", "rostered": "1", "expected": "1", "notes": ""},
        )
        self.assertEqual(status, 403)
        self.assertIn(b"untrusted browser origin", raw)
        self.assertEqual(self.store.snapshot()["classes"], [])

    def test_canonical_localhost_host_and_origin_are_accepted(self) -> None:
        authority = f"localhost:{self.port}"
        status, _, _ = self.request(
            "POST",
            "/class/save",
            {"csrf": "fixed-test-token", "class_id": "x", "label": "X", "rostered": "1", "expected": "1", "notes": ""},
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        self.assertEqual(status, 303)
        self.assertEqual(self.store.snapshot()["classes"][0]["class_id"], "x")

    def test_loopback_authority_builder_is_ipv4_exact_and_fail_closed(self) -> None:
        hosts, origins = loopback_browser_authorities("127.0.0.1", 8765)
        self.assertEqual(hosts, frozenset({"127.0.0.1:8765", "localhost:8765"}))
        self.assertEqual(origins, frozenset({"http://127.0.0.1:8765", "http://localhost:8765"}))
        with self.assertRaisesRegex(StudioError, "IPv4 loopback"):
            loopback_browser_authorities("::1", 8765)
        with self.assertRaises(StudioError):
            loopback_browser_authorities("0.0.0.0", 8765)
        with self.assertRaises(StudioError):
            loopback_browser_authorities("127.0.0.1", 0)

    def test_public_serve_rejects_ipv6_before_socket_bind(self) -> None:
        with mock.patch("app.ThreadingHTTPServer", side_effect=AssertionError("socket bind must not be attempted")) as server_factory:
            with self.assertRaisesRegex(StudioError, "IPv4 loopback"):
                serve(str(self.config_path), str(self.root / "ipv6-rejected.sqlite3"), "::1", 0)
            server_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
