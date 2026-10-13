import csv
import json
import tempfile
import unittest
from pathlib import Path

import trade_quote as app


class TradeQuoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.photo = self.root / "room.jpg"; self.photo.write_bytes(b"fixture-photo-bytes")
        self.rules = self.root / "rules.json"
        self.rules.write_text(json.dumps({"currency": "USD", "setup_flat": "150", "wall_sqft_per_coat": "1.25", "ceiling_sqft_per_coat": "1.00", "tax_rate": "0.07", "schedule_duration_hours": "8"}))

    def tearDown(self): self.tmp.cleanup()

    def request(self, **room_changes):
        room = {"name": "Living Room", "length_ft": "10", "width_ft": "8", "height_ft": "9", "coats": "2", "openings_sq_ft": "30", "paint_ceiling": True}
        room.update(room_changes)
        path = self.root / "request.json"
        path.write_text(json.dumps({"request_id": "REQ-1", "customer": "Demo Customer", "service": "interior_painting", "photo_paths": ["room.jpg"], "rooms": [room]}))
        return path

    def quote(self, **changes): return app.build_quote(self.request(**changes), self.rules, "2026-09-08", 14, "http://localhost:8080")

    def test_complete_measurements_create_exact_editable_quote(self):
        quote = self.quote()
        self.assertEqual("DRAFT_NOT_SENT", quote["status"])
        self.assertEqual("1118.15", quote["total"])
        self.assertTrue(quote["acceptance_url"].startswith("http://localhost:8080/accept?"))
        self.assertEqual([], quote["measurement_requests"])

    def test_missing_measurement_is_requested_not_guessed(self):
        request = self.request(); data = json.loads(request.read_text()); del data["rooms"][0]["height_ft"]; request.write_text(json.dumps(data))
        quote = app.build_quote(request, self.rules, "2026-09-08", 14, "http://localhost:8080")
        self.assertEqual("NEEDS_MEASUREMENTS", quote["status"])
        self.assertFalse(quote["amounts_calculated"])
        self.assertEqual("rooms[1].height_ft", quote["measurement_requests"][0]["field"])
        self.assertIsNone(quote["acceptance_url"])

    def test_photo_and_input_sources_are_hash_linked(self):
        quote = self.quote()
        self.assertEqual(64, len(quote["sources"]["request"]["sha256"]))
        self.assertEqual(app._source(self.photo)["sha256"], quote["sources"]["photos"][0]["sha256"])

    def test_editing_rules_changes_quote_without_guessing(self):
        first = self.quote()
        rules = json.loads(self.rules.read_text()); rules["wall_sqft_per_coat"] = "1.50"; self.rules.write_text(json.dumps(rules))
        second = self.quote()
        self.assertNotEqual(first["total"], second["total"])
        self.assertNotEqual(first["quote_id"], second["quote_id"])

    def test_bundle_contains_valid_pdf_shape(self):
        paths = app.write_quote_bundle(self.quote(), self.root / "out")
        pdf = paths["pdf"].read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF-1.4")); self.assertTrue(pdf.endswith(b"%%EOF\n")); self.assertIn(b"xref", pdf)
        self.assertEqual("DRAFT_NOT_SENT", json.loads(paths["quote"].read_text())["status"])

    def test_acceptance_adds_local_job_and_receipt(self):
        paths = app.write_quote_bundle(self.quote(), self.root / "quotes"); quote = json.loads(paths["quote"].read_text())
        receipt = app.accept_quote(paths["quote"], quote["acceptance_token"], "2026-09-15", "09:00", self.root / "schedule.csv")
        self.assertEqual("ACCEPTED_SCHEDULED_LOCAL", receipt["status"])
        self.assertEqual(0, receipt["external_calendar_writes"]); self.assertEqual(0, receipt["messages_sent"])
        with (self.root / "schedule.csv").open(newline="") as handle: self.assertEqual("Q-", next(csv.DictReader(handle))["quote_id"][:2])

    def test_invalid_token_does_not_schedule(self):
        paths = app.write_quote_bundle(self.quote(), self.root / "quotes")
        with self.assertRaisesRegex(app.QuoteError, "token"):
            app.accept_quote(paths["quote"], "wrong", "2026-09-15", "09:00", self.root / "schedule.csv")
        self.assertFalse((self.root / "schedule.csv").exists())

    def test_schedule_collision_is_held(self):
        paths = app.write_quote_bundle(self.quote(), self.root / "quotes"); quote = json.loads(paths["quote"].read_text()); schedule = self.root / "schedule.csv"
        app.accept_quote(paths["quote"], quote["acceptance_token"], "2026-09-15", "09:00", schedule)
        with self.assertRaisesRegex(app.QuoteError, "collision"):
            app.accept_quote(paths["quote"], quote["acceptance_token"], "2026-09-15", "12:00", schedule)

    def test_expired_quote_is_held(self):
        paths = app.write_quote_bundle(self.quote(), self.root / "quotes"); quote = json.loads(paths["quote"].read_text())
        with self.assertRaisesRegex(app.QuoteError, "expired"):
            app.accept_quote(paths["quote"], quote["acceptance_token"], "2026-09-30", "09:00", self.root / "schedule.csv")

    def test_openings_cannot_exceed_wall_area(self):
        with self.assertRaisesRegex(app.QuoteError, "openings"):
            self.quote(openings_sq_ft="1000")


if __name__ == "__main__": unittest.main()
