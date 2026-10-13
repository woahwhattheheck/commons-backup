"""Focused store, export, concurrency and real-HTTP product workflow tests."""
import base64
from concurrent.futures import ThreadPoolExecutor
import csv
from email import message_from_bytes
from email.policy import default
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import app

EVENT = dict(name="SAMPLE Makers Expo", venue="Example Hall", starts_at="2026-10-15T09:00:00-04:00",
             deadline_at="2026-10-01T17:00:00-04:00", brief="Logo and loading notes due.\nUse the north loading bay.")
EX = dict(company="Sample Ceramics", contact_name="Example Contact", email="desk@example.invalid", booth_code="A01",
          width_m="3", depth_m="3", power_w=500, notes="One table; step-free loading requested.")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "desk.sqlite3"
        self.store = app.Store(self.path)
        self.event = self.store.save_event(EVENT)
        self.ex = self.store.save_exhibitor(self.event["id"], EX)

    def detail(self):
        return self.store.detail(self.event["id"], self.ex["id"])

    def change(self, **fields):
        return self.store.request_change(self.event["id"], self.ex["id"],
            {"expected_revision": self.ex["revision"], "proposed": dict(EX, **fields), "reason": "Larger demo area needed"})

    def resolve(self, change, decision="apply"):
        return self.store.resolve_change(self.event["id"], self.ex["id"], change["id"],
            {"decision": decision, "resolution": "Organizer recorded the request"})

    def upload(self, data=b"\x00original\xff\x01", filename="logo.bin", **kwargs):
        return self.store.add_asset(self.event["id"], self.ex["id"],
            dict(filename=filename, kind="Original logo", base64=base64.b64encode(data).decode(), **kwargs))

    def test_restart_preserves_records(self):
        before = self.detail()
        self.assertEqual(app.Store(self.path).detail(self.event["id"], self.ex["id"]), before)

    def test_event_time_normalizes_offset(self):
        self.assertEqual(self.event["deadline_at"], "2026-10-01T21:00:00+00:00")

    def test_naive_and_reversed_event_dates_rejected(self):
        for changes in ({"starts_at": "2026-10-15T09:00:00"}, {"deadline_at": "2026-10-16T10:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(app.DeskError):
                self.store.save_event(dict(EVENT, **changes))

    def test_header_newlines_rejected(self):
        with self.assertRaises(app.DeskError):
            self.store.save_event(dict(EVENT, name="Expo\r\nBcc: other@example.invalid"))
        with self.assertRaises(app.DeskError):
            self.store.save_exhibitor(self.event["id"], dict(EX, email="desk@example.invalid\r\nBcc:x@y.invalid"))

    def test_nonfinite_and_invalid_dimensions_rejected(self):
        for value in ("NaN", "Infinity", "-1", "0", "1e100", "3.001", None, True):
            with self.subTest(value=value), self.assertRaises(app.DeskError):
                self.store.save_exhibitor(self.event["id"], dict(EX, width_m=value))

    def test_invalid_power_rejected(self):
        for value in (True, -1, 0.5, "9" * 5000, "NaN"):
            with self.subTest(value=str(value)[:20]), self.assertRaises(app.DeskError):
                self.store.save_exhibitor(self.event["id"], dict(EX, power_w=value))

    def test_duplicate_booth_is_case_insensitive_and_atomic(self):
        with self.assertRaises(app.Conflict):
            self.store.save_exhibitor(self.event["id"], dict(EX, company="Other", booth_code="a01"))
        self.assertEqual(len(self.store.detail(self.event["id"])["exhibitors"]), 1)

    def test_booths_are_separate_between_events(self):
        event2 = self.store.save_event(dict(EVENT, name="Second event"))
        self.store.save_exhibitor(event2["id"], EX)
        self.assertEqual(len(self.store.detail(event2["id"])["exhibitors"]), 1)

    def test_multiple_unassigned_booths(self):
        for n in range(2):
            self.store.save_exhibitor(self.event["id"], dict(EX, company=f"Unassigned {n}", booth_code=""))
        self.assertEqual(len(self.store.detail(self.event["id"])["exhibitors"]), 3)

    def test_exhibitor_scope_does_not_mix_events(self):
        event2 = self.store.save_event(dict(EVENT, name="Other"))
        with self.assertRaises(app.Missing):
            self.store.detail(event2["id"], self.ex["id"])

    def test_scoped_portal_contains_one_exhibitor(self):
        self.store.save_exhibitor(self.event["id"], dict(EX, company="Other exhibitor", booth_code="B02"))
        self.assertEqual([ex["company"] for ex in self.detail()["exhibitors"]], [EX["company"]])

    def test_event_stale_revision_preserves_latest(self):
        saved = self.store.save_event(dict(EVENT, name="New name", expected_revision=1), self.event["id"])
        with self.assertRaises(app.Conflict):
            self.store.save_event(dict(EVENT, expected_revision=1), self.event["id"])
        self.assertEqual(self.detail()["event"], saved)

    def test_concurrent_saves_have_one_winner(self):
        def attempt(name):
            try:
                return self.store.save_event(dict(EVENT, name=name, expected_revision=1), self.event["id"])["revision"]
            except app.Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(attempt, ("Version one", "Version two")))
        self.assertCountEqual(result, [2, "conflict"])

    def test_requested_change_does_not_mutate_current_until_apply(self):
        change = self.change(width_m="4", power_w=1000)
        self.assertEqual(self.detail()["exhibitors"][0]["width_m"], "3")
        self.resolve(change)
        ex = self.detail()["exhibitors"][0]
        self.assertEqual((ex["width_m"], ex["power_w"], ex["revision"]), ("4", 1000, 2))
        self.assertEqual(ex["changes"][0]["before"]["width_m"], "3")
        self.assertEqual(ex["changes"][0]["status"], "applied")

    def test_dismiss_preserves_requirements(self):
        self.resolve(self.change(width_m="4"), "dismiss")
        self.assertEqual(self.detail()["exhibitors"][0]["revision"], 1)

    def test_stale_request_cannot_overwrite_later_edit(self):
        change = self.change(width_m="4")
        self.store.save_exhibitor(self.event["id"], dict(EX, notes="New note", expected_revision=1), self.ex["id"])
        with self.assertRaises(app.Conflict):
            self.resolve(change)
        ex = self.detail()["exhibitors"][0]
        self.assertEqual((ex["width_m"], ex["notes"], ex["changes"][0]["status"]), ("3", "New note", "pending"))

    def test_booth_collision_rolls_back_change_resolution(self):
        self.store.save_exhibitor(self.event["id"], dict(EX, company="Other", booth_code="B02"))
        change = self.change(booth_code="B02")
        with self.assertRaises(app.Conflict):
            self.resolve(change)
        self.assertEqual(self.detail()["exhibitors"][0]["changes"][0]["status"], "pending")

    def test_change_cannot_be_resolved_twice(self):
        change = self.change(width_m="4")
        self.resolve(change)
        with self.assertRaises(app.Conflict):
            self.resolve(change)
        self.assertEqual(self.detail()["exhibitors"][0]["revision"], 2)

    def test_unchanged_proposal_rejected(self):
        with self.assertRaises(app.DeskError):
            self.change()

    def test_binary_asset_exact_round_trip_and_metadata(self):
        payload = bytes(range(256)) * 20
        asset = self.upload(payload, "logo-日本語.bin")
        out = self.store.asset(self.event["id"], self.ex["id"], asset["id"])
        self.assertEqual(out["data"], payload)
        self.assertEqual(asset["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(asset["size"], len(payload))
        self.assertEqual(len(self.detail()["exhibitors"][0]["assets"]), 1)

    def test_asset_filename_preserves_original_spaces(self):
        asset = self.upload(filename=" original file.bin ")
        self.assertEqual(asset["filename"], " original file.bin ")

    def test_asset_retry_coalesces_without_rewriting_original(self):
        first, second = self.upload(), self.upload()
        self.assertEqual(first, second)
        self.assertEqual(len(self.detail()["exhibitors"][0]["assets"]), 1)

    def test_same_filename_changed_content_keeps_both_versions(self):
        self.assertNotEqual(self.upload(b"one")["id"], self.upload(b"two")["id"])
        self.assertEqual(len(self.detail()["exhibitors"][0]["assets"]), 2)

    def test_asset_input_and_scope_errors(self):
        for filename in ("../file", "a/b", "a\\b", "\nfilename", "."):
            with self.subTest(filename=filename), self.assertRaises(app.DeskError):
                self.upload(filename=filename)
        for value in ("%%%", "", "abcdé"):
            with self.subTest(value=value), self.assertRaises(app.DeskError):
                self.store.add_asset(self.event["id"], self.ex["id"], dict(filename="a.bin", base64=value))
        with self.assertRaises(app.Missing):
            self.store.asset(self.event["id"], "missing", "missing")

    def test_size_limit_rejected_without_partial_asset(self):
        with self.assertRaises(app.DeskError):
            self.upload(b"x" * (app.MAX_ASSET + 1))
        self.assertEqual(self.detail()["exhibitors"][0]["assets"], [])

    def test_floor_export_changes_after_resolved_request(self):
        self.resolve(self.change(width_m="4"))
        rows = list(csv.DictReader(io.StringIO(app.floor_csv(self.detail()["exhibitors"]).decode("utf-8-sig"))))
        self.assertEqual((rows[0]["width_m"], rows[0]["area_m2"], rows[0]["revision"]), ("4", "12", "2"))

    def test_csv_text_formula_and_multiline_handling(self):
        self.store.save_exhibitor(self.event["id"], dict(EX, company="=1+1", notes='Text, with "quotes"\nand newline', expected_revision=1), self.ex["id"])
        rows = list(csv.DictReader(io.StringIO(app.floor_csv(self.detail()["exhibitors"]).decode("utf-8-sig"))))
        self.assertEqual(rows[0]["company"], "'=1+1")
        self.assertEqual(rows[0]["requirements"], 'Text, with "quotes"\nand newline')

    def test_latest_deadline_drives_reminder_and_calendar(self):
        event = self.store.save_event(dict(EVENT, deadline_at="2026-10-05T12:00:00Z", expected_revision=1), self.event["id"])
        msg = message_from_bytes(app.reminder(event, self.ex), policy=default)
        self.assertEqual(msg["To"], EX["email"])
        self.assertEqual(msg["X-Unsent"], "1")
        self.assertIn("2026-10-05T12:00:00+00:00", msg.get_content())
        ics = app.calendar(event)
        self.assertIn(b"DTSTART:20261005T120000Z", ics)
        self.assertIn(b"SEQUENCE:2", ics)
        self.assertNotIn(b"20261001T210000Z", ics)

    def test_calendar_utf8_folding_and_escaping(self):
        event = dict(self.event, name="東京" * 80 + ", test; slash\\", brief="Line one\nLine two")
        result = app.calendar(event)
        result.decode("utf-8")
        self.assertTrue(all(len(line) <= 75 for line in result.split(b"\r\n")))
        unfolded = result.replace(b"\r\n ", b"").decode()
        self.assertIn("\\, test\\; slash\\\\", unfolded)
        self.assertIn("Line one\\nLine two", unfolded)

    def test_packet_contains_original_assets_and_exact_manifest(self):
        asset = self.upload()
        self.resolve(self.change(width_m="4"))
        with zipfile.ZipFile(io.BytesIO(self.store.packet(self.event["id"]))) as z:
            manifest = json.loads(z.read("MANIFEST.json"))
            self.assertEqual(set(manifest), set(z.namelist()) - {"MANIFEST.json"})
            for path, entry in manifest.items():
                data = z.read(path)
                self.assertEqual((entry["bytes"], entry["sha256"]), (len(data), hashlib.sha256(data).hexdigest()))
            names = [n for n in z.namelist() if n.startswith("assets/")]
            self.assertEqual(z.read(names[0]), b"\x00original\xff\x01")
            self.assertEqual(json.loads(z.read("assets.json"))[0]["id"], asset["id"])
            self.assertEqual(json.loads(z.read("changes.json"))[0]["status"], "applied")


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = app.Store(Path(self.temp.name) / "http.sqlite3")
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.handler_for(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path, data=None, raw=None, content_type="application/json"):
        body = json.dumps(data).encode() if data is not None else raw
        req = Request(self.base + path, data=body, headers={"Content-Type": content_type})
        try:
            with urlopen(req, timeout=10) as response:
                return response.status, response.read(), response.headers
        except HTTPError as error:
            with error:
                return error.code, error.read(), error.headers

    def json(self, path, data=None):
        status, body, _ = self.request(path, data)
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_real_http_end_to_end(self):
        event = self.json("/api/events", EVENT)
        ep = "/api/events/" + event["id"]
        ex = self.json(ep + "/exhibitors", EX)
        xp = ep + "/exhibitors/" + ex["id"]
        asset = self.json(xp + "/assets", {"filename": "logo.bin", "base64": "AG9yaWdpbmFs/w==", "kind": "Logo"})
        status, data, headers = self.request(xp + "/assets/" + asset["id"])
        self.assertEqual((status, data), (200, b"\x00original\xff"))
        self.assertEqual(headers.get_content_type(), "application/octet-stream")
        change = self.json(xp + "/changes", {"expected_revision": 1, "proposed": dict(EX, width_m="4"), "reason": "Demonstration space"})
        self.assertEqual(self.json(xp)["exhibitors"][0]["width_m"], "3")
        self.json(xp + "/changes/" + change["id"], {"decision": "apply", "resolution": "New floor plan recorded"})
        self.assertEqual(self.json(xp)["exhibitors"][0]["width_m"], "4")
        self.json(ep, dict(EVENT, expected_revision=1, deadline_at="2026-10-04T12:00:00Z"))
        self.assertIn(b"20261004T120000Z", self.request(ep + "/deadlines.ics")[1])
        self.assertIn("2026-10-04T12:00:00+00:00", message_from_bytes(self.request(xp + "/reminder.eml")[1], policy=default).get_content())
        self.assertIn(b",4,3,12,", self.request(ep + "/floor-plan.csv")[1])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(self.request(ep + "/packet.zip")[1])))

    def test_real_static_assets_and_scoped_missing(self):
        for path, kind in (("/", "text/html"), ("/desk.js", "text/javascript")):
            status, data, headers = self.request(path)
            self.assertEqual(status, 200)
            self.assertTrue(data)
            self.assertEqual(headers.get_content_type(), kind)
        self.assertEqual(self.request("/api/events/missing")[0], 404)
        self.assertEqual(self.request("/app.py")[0], 404)

    def test_real_bad_requests_have_structured_errors(self):
        for raw, kind in ((b"{", "application/json"), (b"[]", "application/json"), (b"{}", "text/plain"), (b"", "application/json")):
            status, data, _ = self.request("/api/events", raw=raw, content_type=kind)
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(data))

    def test_real_stale_save_is_409(self):
        event = self.json("/api/events", EVENT)
        path = "/api/events/" + event["id"]
        self.json(path, dict(EVENT, expected_revision=1, name="Saved"))
        status, body, _ = self.request(path, dict(EVENT, expected_revision=1, name="Stale"))
        self.assertEqual(status, 409)
        self.assertIn("error", json.loads(body))
        self.assertEqual(self.json(path)["event"]["name"], "Saved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
