"""Calendar integration checks against the real Lantern Store and HTTP handler."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

from app import Store
import calendar_feed as calendar

HERE = Path(__file__).resolve().parent
NOW = 1_788_860_000


def unfold(body):
    """Independent physical-line checks and RFC continuation decoding."""
    if not body.endswith(b"\r\n"):
        raise AssertionError("Calendar must end with CRLF")
    physical = body[:-2].split(b"\r\n")
    logical = []
    for line in physical:
        if len(line) > 75 or b"\r" in line or b"\n" in line:
            raise AssertionError("Invalid physical content line")
        line.decode("utf-8")  # A fold may not split a UTF-8 character.
        if line.startswith((b" ", b"\t")):
            if not logical:
                raise AssertionError("Continuation without content line")
            logical[-1] += line[1:]
        else:
            logical.append(line)
    return [line.decode("utf-8") for line in logical]


def properties(body, name):
    return [line.split(":", 1)[1] for line in unfold(body) if line.startswith(name + ":")]


class FormattingTests(unittest.TestCase):
    def event(self, **changes):
        return dict(id="synthetic-event", title="Friday round", room="Common room",
                    opens=NOW, ends=NOW + 60, created=NOW - 600, **changes)

    def test_complete_components_and_required_fields(self):
        lines = unfold(calendar.render_calendar([self.event()]))
        self.assertEqual(lines[:2], ["BEGIN:VCALENDAR", "VERSION:2.0"])
        self.assertEqual(lines[-2:], ["END:VEVENT", "END:VCALENDAR"])
        for key in ("UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "LOCATION"):
            self.assertEqual(sum(line.startswith(key + ":") for line in lines), 1)
        self.assertNotIn("METHOD:PUBLISH", lines)

    def test_text_escape_is_reversible_and_not_an_extra_property(self):
        event = self.event()
        event["title"] = "Tea, coffee; notes\\file\r\nLOCATION:still title"
        result = calendar.render_calendar([event])
        self.assertEqual(properties(result, "SUMMARY"),
                         [r"Tea\, coffee\; notes\\file\nLOCATION:still title"])
        self.assertEqual(properties(result, "LOCATION"), ["Common room"])

    def test_long_unicode_lines_fold_by_bytes_without_character_loss(self):
        for character in ("x", "é", "棋", "🧩"):
            for count in (0, 1, 66, 67, 74, 75, 76, 160):
                with self.subTest(character=character, count=count):
                    value = "SUMMARY:" + character * count
                    self.assertEqual(unfold(calendar.fold_line(value)), [value])

    def test_text_controls_and_surrogates_report_calendar_error(self):
        for value in (None, 3, True, "a\x00b", "\x7f", "\ud800"):
            with self.subTest(value=repr(value)), self.assertRaises(calendar.CalendarError):
                calendar.text_value(value)
        self.assertEqual(calendar.text_value("a\rb\r\nc\nd\te"), r"a\nb\nc\nd" + "\te")

    def test_raw_content_newline_is_rejected(self):
        for line in ("A\nB", "A\rB"):
            with self.assertRaises(calendar.CalendarError):
                calendar.fold_line(line)

    def test_utc_stamp_known_epoch_and_leap_day(self):
        self.assertEqual(calendar.utc_stamp(0), "19700101T000000Z")
        leap = datetime(2024, 2, 29, 23, 59, 59, tzinfo=timezone.utc).timestamp()
        self.assertEqual(calendar.utc_stamp(leap), "20240229T235959Z")

    def test_fractional_interval_is_not_shortened(self):
        event = self.event()
        event.update(opens=NOW + .25, ends=NOW + .5)
        result = calendar.render_calendar([event])
        start = datetime.strptime(properties(result, "DTSTART")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
        end = datetime.strptime(properties(result, "DTEND")[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
        self.assertEqual((start, end), (NOW, NOW + 1))

    def test_page_times_match_calendar_outward_rounding(self):
        event = self.event()
        event.update(opens=NOW + .25, ends=NOW + .5)
        page = calendar.calendar_page([event]).decode()
        for second in (NOW, NOW + 1):
            timestamp = datetime.fromtimestamp(second, timezone.utc).isoformat(timespec="seconds")
            self.assertIn(f"<time>{timestamp}</time>", page)

    def test_invalid_timestamp_values(self):
        for value in (-1, True, None, "0", float("inf"), float("nan"), 10**500, 253402300800):
            with self.subTest(value=repr(value)), self.assertRaises(calendar.CalendarError):
                calendar.utc_stamp(value)

    def test_equal_and_reversed_intervals_rejected(self):
        for end in (NOW, NOW - 1):
            event = self.event()
            event["ends"] = end
            with self.assertRaises(calendar.CalendarError):
                calendar.render_calendar([event])

    def test_stable_uid_independent_of_advertised_host(self):
        event = self.event()
        one = calendar.render_calendar([event], app_url="https://one.example")
        two = calendar.render_calendar([event], app_url="https://two.example:9443/")
        self.assertEqual(properties(one, "UID"), properties(two, "UID"))
        self.assertEqual(properties(one, "URL"), ["https://one.example/?event=synthetic-event"])
        self.assertEqual(properties(one, "DTSTAMP"), properties(two, "DTSTAMP"))

    def test_event_link_encodes_id_and_no_url_is_invented(self):
        event = self.event()
        event["id"] = "demo /?&棋"
        plain = calendar.render_calendar([event])
        self.assertEqual(properties(plain, "URL"), [])
        result = calendar.render_calendar([event], app_url="https://example.test")
        self.assertEqual(properties(result, "URL"), ["https://example.test/?event=demo%20%2F%3F%26%E6%A3%8B"])

    def test_empty_calendar_is_valid_and_deterministic(self):
        one = calendar.render_calendar([])
        self.assertEqual(one, calendar.render_calendar([]))
        self.assertEqual(unfold(one)[-1], "END:VCALENDAR")
        self.assertNotIn(b"BEGIN:VEVENT", one)

    def test_duplicate_or_missing_identity_fails_before_output(self):
        event = self.event()
        with self.assertRaises(calendar.CalendarError):
            calendar.render_calendar([event, event])
        for value in ("", None, 3):
            with self.subTest(value=value), self.assertRaises(calendar.CalendarError):
                calendar.render_calendar([{**event, "id": value}])
        del event["created"]
        with self.assertRaisesRegex(calendar.CalendarError, "created"):
            calendar.render_calendar([event])

    def test_public_url_normalizes_hosts_without_fetching(self):
        self.assertEqual(calendar.public_url("https://münich.example"), "https://xn--mnich-kva.example/")
        self.assertEqual(calendar.public_url("http://[::1]:8765/"), "http://[::1]:8765/")
        self.assertIsNone(calendar.public_url(None))

    def test_invalid_public_url_cannot_enter_calendar(self):
        for url in ("", "/", "file:///tmp/events", "https://name:secret@example.test", "https://example.test/app",
                    "https://example.test/?x=1", "https://example.test/#x", "https://example.test:0",
                    "https://example.test:99999", "https://a\nb", "https://a\\b", "https://a\x7fb"):
            with self.subTest(url=url), self.assertRaises(calendar.CalendarError):
                calendar.public_url(url)


class StoreCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.database = self.directory / "events # ? 棋.sqlite3"
        self.store = Store(self.database, clock=lambda: NOW)

    def payload(self, **changes):
        result = dict(title="Friday round", room="Room A", opens=NOW - 60, ends=NOW + 3600,
                      questions=[dict(prompt="Hidden synthetic question", choices=["answer one", "answer two"], correct=1, points=100)])
        result.update(changes)
        return result

    def create(self, **changes):
        return self.store.create(self.payload(**changes))["id"]

    def dump(self):
        with self.store.connect() as db:
            return "\n".join(db.iterdump())

    def feed(self, **selection):
        return calendar.render_calendar(calendar.read_events(self.database, **selection))


class StoreTests(StoreCase):
    def test_source_snapshot_contains_exactly_six_metadata_fields(self):
        identifier = self.create()
        row, = calendar.read_events(self.database)
        self.assertEqual(set(row), {"id", "title", "room", "opens", "ends", "created"})
        self.assertEqual(row["id"], identifier)

    def test_export_and_html_do_not_include_questions_answers_or_members(self):
        identifier = self.create()
        member = self.store.join(identifier, {"name": "Synthetic participant private label"})["id"]
        self.store.answer(identifier, dict(member_id=member, question=0, choice=1))
        rows = calendar.read_events(self.database)
        for result in (self.feed(), calendar.calendar_page(rows)):
            for value in (member, "Hidden synthetic question", "answer one", "answer two", "Synthetic participant private label"):
                self.assertNotIn(value.encode(), result)

    def test_export_does_not_modify_source_records(self):
        self.create()
        before = self.dump()
        for _ in range(3):
            self.feed()
        self.assertEqual(before, self.dump())

    def test_missing_db_remains_missing(self):
        absent = self.directory / "absent.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            calendar.read_events(absent)
        self.assertFalse(absent.exists())

    def test_metadata_reader_does_not_require_game_tables(self):
        only_metadata = self.directory / "metadata.sqlite3"
        with contextlib.closing(sqlite3.connect(only_metadata)) as db, db:
            db.execute("CREATE TABLE events(id,title,room,opens,ends,created)")
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", ("demo", "Metadata", "Room", NOW, NOW+1, NOW))
        self.assertEqual(properties(calendar.render_calendar(calendar.read_events(only_metadata)), "SUMMARY"), ["Metadata"])

    def test_room_filter_is_exact_and_parameterized(self):
        a = self.create(room="Chess, 棋 & friends")
        self.create(room="chess, 棋 & friends")
        self.assertEqual([e["id"] for e in calendar.read_events(self.database, room="Chess, 棋 & friends")], [a])
        self.assertEqual(calendar.read_events(self.database, room="Room' OR 1=1 --"), [])

    def test_one_event_and_unknown_event(self):
        a = self.create()
        self.create(title="Second")
        self.assertEqual(len(calendar.read_events(self.database, event_id=a)), 1)
        with self.assertRaises(calendar.CalendarError) as caught:
            calendar.read_events(self.database, event_id="not-present")
        self.assertEqual(caught.exception.status, 404)

    def test_order_is_start_then_id(self):
        self.create(opens=NOW+120)
        self.create(opens=NOW+60)
        self.create(opens=NOW+60)
        rows = calendar.read_events(self.database)
        self.assertEqual([(e["opens"], e["id"]) for e in rows], sorted((e["opens"], e["id"]) for e in rows))
        self.assertEqual(self.feed(), self.feed())

    def test_gameplay_finish_and_database_reopen_keep_schedule_bytes(self):
        a = self.create()
        before = self.feed()
        member = self.store.join(a, {"name": "Player"})["id"]
        answer = dict(member_id=member, question=0, choice=1)
        self.store.answer(a, answer)
        self.assertTrue(self.store.answer(a, answer)["replayed"])
        self.store.finish(a)
        self.store = Store(self.database, clock=lambda: NOW + 10000)
        self.assertEqual(before, self.feed())
        self.assertEqual(self.store.join(a, {"member_id": member})["id"], member)
        self.assertEqual(self.store.state(a, member)["leaderboard"][0]["points"], 100)
        self.assertNotIn(b"CANCELLED", before)

    def test_uncommitted_schedule_does_not_leak_into_feed(self):
        self.create(title="Published")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE events SET title='Not committed'")
            self.assertEqual(properties(self.feed(), "SUMMARY"), ["Published"])
            db.rollback()
        self.assertEqual(properties(self.feed(), "SUMMARY"), ["Published"])

    def test_concurrent_game_writes_leave_feed_deterministic(self):
        event = self.create()
        before = self.feed()
        def play(index):
            member = self.store.join(event, {"name": f"Player {index}"})["id"]
            self.store.answer(event, dict(member_id=member, question=0, choice=index % 2))
            return self.feed()
        with ThreadPoolExecutor(max_workers=4) as workers:
            self.assertTrue(all(value == before for value in workers.map(play, range(12))))
        self.assertEqual(self.store.state(event)["players"], 12)


class HttpTests(StoreCase):
    def setUp(self):
        super().setUp()
        handler = calendar.make_calendar_handler(self.store, app_url="https://events.example.test")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.worker.start()
        def stop():
            self.server.shutdown()
            self.server.server_close()
            self.worker.join(timeout=5)
        self.addCleanup(stop)

    def request(self, path, method="GET", data=None, headers=None):
        headers = dict(headers or {})
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_inherited_ui_is_exact_owner_asset(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(body, (HERE / "index.html").read_bytes())
        self.assertTrue(headers["Content-Type"].startswith("text/html"))

    def test_real_game_flow_through_wrapper_and_reconnect(self):
        self.assertEqual(json.loads(self.request("/health")[2]), {"ok": True})
        status, _, raw = self.request("/api/events", "POST", self.payload())
        self.assertEqual(status, 201)
        created = json.loads(raw)
        event = created["id"]
        path = f"/api/events/{event}"
        member = json.loads(self.request(path + "/join", "POST", {"name": "Player"})[2])["id"]
        before = self.request("/calendar.ics")[2]
        answer = dict(member_id=member, question=0, choice=1)
        self.assertEqual(self.request(path + "/answers", "POST", answer)[0], 200)
        self.assertTrue(json.loads(self.request(path + "/answers", "POST", answer)[2])["replayed"])
        self.assertEqual(self.request(path + "/finish", "POST", {"host_key": created["host_key"]})[0], 200)
        self.assertEqual(json.loads(self.request(path + "/join", "POST", {"member_id": member})[2])["id"], member)
        state = json.loads(self.request(path + "?member=" + member)[2])
        self.assertEqual(state["leaderboard"][0]["points"], 100)
        self.assertEqual(self.request("/calendar.ics")[2], before)
        self.assertEqual(properties(before, "URL"), ["https://events.example.test/?event=" + event])

    def test_feed_headers_exact_length_and_format(self):
        self.create(title="棋 " * 50)
        status, headers, body = self.request("/calendar.ics")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(headers["ETag"], '"' + hashlib.sha256(body).hexdigest() + '"')
        unfold(body)

    def test_head_preserves_get_headers_without_body(self):
        self.create()
        for path in ("/calendar", "/calendar.ics"):
            with self.subTest(path=path):
                _, get_headers, get_body = self.request(path)
                status, headers, body = self.request(path, "HEAD")
                self.assertEqual(status, 200)
                self.assertEqual(body, b"")
                self.assertEqual(headers["ETag"], get_headers["ETag"])
                self.assertEqual(int(headers["Content-Length"]), len(get_body))

    def test_conditional_get_and_head_support_weak_list_and_wildcard(self):
        self.create()
        etag = self.request("/calendar.ics")[1]["ETag"]
        for match in (etag, "W/" + etag, '"other", ' + etag, "*"):
            for method in ("GET", "HEAD"):
                with self.subTest(match=match, method=method):
                    status, _, body = self.request("/calendar.ics", method, headers={"If-None-Match": match})
                    self.assertEqual((status, body), (304, b""))

    def test_new_event_changes_etag_and_retains_old_uid(self):
        self.create()
        _, headers, before = self.request("/calendar.ics")
        self.create(title="Another round")
        status, new_headers, after = self.request("/calendar.ics", headers={"If-None-Match": headers["ETag"]})
        self.assertEqual(status, 200)
        self.assertNotEqual(headers["ETag"], new_headers["ETag"])
        self.assertIn(properties(before, "UID")[0], properties(after, "UID"))

    def test_room_and_single_event_downloads(self):
        identifier = self.create(room="Chess & 棋")
        self.create(title="Other", room="Other")
        for path in ("/calendar.ics?room=" + quote("Chess & 棋", safe=""), f"/calendar/{identifier}.ics"):
            status, _, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(properties(body, "SUMMARY"), ["Friday round"])

    def test_missing_event_is_json_404_not_empty_success(self):
        for method in ("GET", "HEAD"):
            status, headers, body = self.request("/calendar/not-present.ics", method)
            self.assertEqual(status, 404)
            self.assertTrue(headers["Content-Type"].startswith("application/json"))
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(body, b"" if method == "HEAD" else b'{"error": "Event not found"}')

    def test_bad_utf8_or_duplicate_room_has_error_without_mutation(self):
        self.create()
        before = self.dump()
        for path, expected in (("/calendar.ics?room=A&room=B", 422),
                               ("/calendar/%FF.ics", 400), ("/calendar.ics?room=%FF", 400)):
            self.assertEqual(self.request(path)[0], expected)
        self.assertEqual(self.dump(), before)

    def test_html_escapes_metadata_and_links_to_existing_event_view(self):
        identifier = self.create(title='<b>Tea & cake</b>', room='Room "A"')
        status, _, body = self.request("/calendar")
        self.assertEqual(status, 200)
        self.assertIn(b"&lt;b&gt;Tea &amp; cake&lt;/b&gt;", body)
        self.assertNotIn(b"<b>Tea", body)
        self.assertIn(f'href="/?event={identifier}"'.encode(), body)
        self.assertIn(f'href="/calendar/{identifier}.ics"'.encode(), body)
        self.assertIn(b'name="viewport"', body)

    def test_missing_database_returns_503_without_recreating_it(self):
        self.database.unlink()
        self.assertEqual(self.request("/calendar.ics")[0], 503)
        self.assertFalse(self.database.exists())

    def test_invalid_source_row_never_emits_partial_calendar(self):
        self.create()
        with self.store.connect() as db:
            db.execute("UPDATE events SET ends=opens")
        status, headers, body = self.request("/calendar.ics")
        self.assertEqual(status, 422)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertNotIn(b"BEGIN:VCALENDAR", body)

    def test_unknown_get_still_uses_owner_error_contract(self):
        status, _, body = self.request("/not-a-route")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "Route not found"})


class CliTests(StoreCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(HERE / "calendar_feed.py"), *arguments],
                              capture_output=True, timeout=10)

    def test_stdout_is_exact_calendar_and_database_unchanged(self):
        self.create()
        before = self.dump()
        result = self.run_cli("export", "--db", str(self.database))
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertEqual(result.stdout, self.feed())
        self.assertEqual(before, self.dump())

    def test_event_and_room_selection(self):
        event = self.create(room="棋 club")
        self.create(title="Other")
        for selection in (("--event", event), ("--room", "棋 club")):
            result = self.run_cli("export", "--db", str(self.database), *selection)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(properties(result.stdout, "SUMMARY"), ["Friday round"])

    def test_public_url_produces_actual_ui_event_link(self):
        event = self.create()
        result = self.run_cli("export", "--db", str(self.database), "--public-url", "https://example.test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(properties(result.stdout, "URL"), ["https://example.test/?event=" + event])

    def test_missing_database_and_event_fail_without_stdout(self):
        absent = self.directory / "missing.sqlite3"
        for arguments in (("--db", str(absent)), ("--db", str(self.database), "--event", "missing")):
            result = self.run_cli("export", *arguments)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"Calendar error:", result.stderr)
        self.assertFalse(absent.exists())

    def test_invalid_url_does_not_create_database(self):
        absent = self.directory / "missing.sqlite3"
        result = self.run_cli("serve", "--db", str(absent), "--public-url", "not-a-url")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertFalse(absent.exists())

    def test_selection_flags_are_mutually_exclusive(self):
        result = self.run_cli("export", "--db", str(self.database), "--event", "x", "--room", "y")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")

    def test_real_serve_process_returns_same_calendar(self):
        self.create()
        process = subprocess.Popen([sys.executable, "-B", str(HERE / "calendar_feed.py"), "serve",
                                    "--db", str(self.database), "--port", "0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # Read readiness with a bounded future, not a fixed startup delay.
            with ThreadPoolExecutor(max_workers=1) as reader:
                ready = reader.submit(process.stdout.readline)
                try:
                    line = ready.result(timeout=8).decode()
                except TimeoutError:
                    process.terminate()
                    raise
            self.assertIn("Lantern calendar: http://127.0.0.1:", line)
            port = int(line.rsplit(":", 1)[1].split("/", 1)[0])
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("GET", "/calendar.ics")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), self.feed())
            finally:
                connection.close()
        finally:
            process.terminate()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
