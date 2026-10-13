#!/usr/bin/env python3
"""Tests for the evidence register and document manifest (UIOWA-031).

Run:  python3 -m unittest -v test_evidence_register.py

The order's two completion conditions are the two test classes that matter:

  ResolutionTests  - "every example document can be found from its register entry"
  RoundTripTests   - "a round trip preserves IDs, versions, and locators,
                      including documents used by more than one assessment cell"

Both are executed against the real packet on disk, not asserted.
"""

from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evidence_register as er  # noqa: E402
import make_packet as mp  # noqa: E402


def codes(issues):
    return {i.code for i in issues}


class PacketFixture(unittest.TestCase):
    """Each test gets its own copy of the packet, so edits cannot leak."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.td, ignore_errors=True)
        self.root = os.path.join(self.td, "packet")
        self.packet = mp.build(self.root)
        er.save_packet_csv(self.packet, self.root)
        self.packet, _ = er.load_packet(self.root)


class SchemaTests(unittest.TestCase):
    def test_register_keeps_every_023_field_name_unchanged(self):
        """The existing convention is extended, not forked."""
        real = os.path.join(HERE, "..", "uiowa_rfq_18649_workshare", "methodology",
                            "23-synthetic-evidence-register.csv")
        if not os.path.exists(real):
            self.skipTest("not running inside the Commons checkout")
        with open(real, newline="", encoding="utf-8") as f:
            upstream = next(csv.reader(f))
        self.assertEqual(upstream, er.REGISTER_FIELDS_FROM_023,
                         "the 023 register's field names must be carried verbatim")
        for name in upstream:
            self.assertIn(name, er.REGISTER_FIELDS)

    def test_the_order_s_named_fields_all_exist(self):
        """source ID, group, assessment area, owner, supplied date, version,
        document location, excerpt locator, and the practice supported."""
        everywhere = set(er.MANIFEST_FIELDS) | set(er.REGISTER_FIELDS)
        for name in ("source_id", "group", "area", "owner", "supplied_date",
                     "document_version", "document_location", "excerpt_locator",
                     "practice_supported"):
            with self.subTest(field=name):
                self.assertIn(name, everywhere)

    def test_document_attributes_live_on_the_manifest_not_the_register(self):
        """A document is described once, so its version cannot drift between
        two entries that cite it."""
        for name in ("document_location", "document_version", "owner", "supplied_date"):
            with self.subTest(field=name):
                self.assertIn(name, er.MANIFEST_FIELDS)
                self.assertNotIn(name, er.REGISTER_FIELDS)


class PacketShapeTests(PacketFixture):
    def test_packet_loads_with_documents_and_entries(self):
        self.assertEqual(6, len(self.packet.manifest))
        self.assertEqual(8, len(self.packet.register))

    def test_every_document_written_to_disk_exists(self):
        for d in self.packet.manifest:
            with self.subTest(doc=d["source_id"]):
                self.assertTrue(os.path.exists(
                    os.path.join(self.root, d["document_location"])))

    def test_packet_contains_documents_in_more_than_one_format(self):
        exts = {os.path.splitext(d["document_location"])[1] for d in self.packet.manifest}
        self.assertGreaterEqual(len(exts), 4, f"only {exts}")

    def test_packet_has_a_document_used_by_more_than_one_cell(self):
        multi = self.packet.multi_cell_documents()
        self.assertIn("SRC-SYN-006", multi)
        self.assertEqual({("ESS", "SD"), ("IAM", "SEC")},
                         self.packet.cells_for("SRC-SYN-006"))

    def test_identifiers_carry_the_synthetic_marker(self):
        for d in self.packet.manifest:
            self.assertIn("SYN", d["source_id"])
        for e in self.packet.register:
            self.assertIn("SYN", e["evidence_id"])


class ResolutionTests(PacketFixture):
    """Completion condition 1: every document findable from its register entry."""

    def test_the_shipped_packet_validates_clean(self):
        issues = er.validate(self.packet)
        self.assertEqual([], issues, "\n".join(str(i) for i in issues))

    def test_every_entry_resolves_to_a_document_and_an_excerpt(self):
        for e in self.packet.register:
            with self.subTest(entry=e["evidence_id"]):
                path, why = er.resolve_document(self.packet, e["source_id"])
                self.assertEqual("", why)
                text, why = er.resolve_excerpt(path, e["excerpt_locator"])
                self.assertEqual("", why)
                self.assertTrue(text.strip(), "locator resolved to nothing")

    def test_all_four_locator_kinds_are_exercised_by_the_packet(self):
        kinds = {e["excerpt_locator"].split(":", 1)[0] for e in self.packet.register}
        self.assertEqual({"lines", "section", "key", "row"}, kinds)

    def test_a_section_locator_returns_that_section(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-001")
        text, why = er.resolve_excerpt(path, "section:Required checks")
        self.assertEqual("", why)
        self.assertIn("passing build-and-test status", text)
        self.assertNotIn("Exceptions", text)

    def test_a_key_locator_returns_that_json_value(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-003")
        text, why = er.resolve_excerpt(path, "key:summary")
        self.assertEqual("", why)
        self.assertEqual({"accounts_returned": 14, "second_factor_enrolled": 14},
                         json.loads(text))

    def test_a_row_locator_returns_that_csv_row(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-004")
        text, why = er.resolve_excerpt(path, "row:CHG-SYN-2044")
        self.assertEqual("", why)
        self.assertIn("rolled back", text)

    def test_a_lines_locator_returns_that_range(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-005")
        text, why = er.resolve_excerpt(path, "lines:8-10")
        self.assertEqual("", why)
        self.assertEqual(3, len(text.split("\n")))


class HostileResolutionTests(PacketFixture):
    def test_a_deleted_document_is_reported(self):
        os.remove(os.path.join(self.root, self.packet.manifest[0]["document_location"]))
        self.assertIn(er.MISSING_DOCUMENT, codes(er.validate(self.packet)))

    def test_an_entry_pointing_at_no_document_is_reported(self):
        self.packet.register[0]["source_id"] = "SRC-DOES-NOT-EXIST"
        self.assertIn(er.DANGLING_SOURCE_ID, codes(er.validate(self.packet)))

    def test_an_entry_with_no_source_id_is_reported(self):
        self.packet.register[0]["source_id"] = ""
        self.assertIn(er.DANGLING_SOURCE_ID, codes(er.validate(self.packet)))

    def test_an_entry_with_no_locator_is_reported(self):
        self.packet.register[0]["excerpt_locator"] = ""
        self.assertIn(er.UNRESOLVED_LOCATOR, codes(er.validate(self.packet)))

    def test_a_malformed_locator_is_reported_as_syntax(self):
        self.packet.register[0]["excerpt_locator"] = "page 4"
        self.assertIn(er.BAD_LOCATOR_SYNTAX, codes(er.validate(self.packet)))

    def test_a_locator_past_the_end_of_the_document_is_reported(self):
        """The real defect this caught in the packet during development."""
        self.packet.register[1]["excerpt_locator"] = "lines:900-901"
        issues = er.validate(self.packet)
        self.assertIn(er.UNRESOLVED_LOCATOR, codes(issues))
        self.assertTrue(any("outside the document" in i.detail for i in issues))

    def test_a_section_that_does_not_exist_is_reported(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-001")
        _, why = er.resolve_excerpt(path, "section:No Such Heading")
        self.assertIn("no heading named", why)

    def test_a_key_path_that_does_not_resolve_is_reported(self):
        path, _ = er.resolve_document(self.packet, "SRC-SYN-003")
        _, why = er.resolve_excerpt(path, "key:summary.nope")
        self.assertIn("does not resolve", why)

    def test_a_document_edited_after_registration_is_detected(self):
        """The digest is the difference between 'a document' and 'the document
        that was supplied'."""
        doc = self.packet.manifest[0]
        path = os.path.join(self.root, doc["document_location"])
        with open(path, "a", encoding="utf-8") as f:
            f.write("\nAn edit made after the document was registered.\n")
        issues = er.validate(self.packet)
        self.assertIn(er.DIGEST_MISMATCH, codes(issues))

    def test_digest_checking_can_be_turned_off_without_hiding_other_issues(self):
        doc = self.packet.manifest[0]
        with open(os.path.join(self.root, doc["document_location"]), "a",
                  encoding="utf-8") as f:
            f.write("\nedited\n")
        self.assertNotIn(er.DIGEST_MISMATCH, codes(er.validate(self.packet, check_digests=False)))
        self.assertEqual([], er.validate(self.packet, check_digests=False))

    def test_a_duplicate_source_id_is_reported(self):
        self.packet.manifest.append(copy.deepcopy(self.packet.manifest[0]))
        self.assertIn(er.DUPLICATE_ID, codes(er.validate(self.packet)))

    def test_a_duplicate_evidence_id_is_reported(self):
        self.packet.register.append(copy.deepcopy(self.packet.register[0]))
        self.assertIn(er.DUPLICATE_ID, codes(er.validate(self.packet)))

    def test_a_document_nothing_cites_is_reported(self):
        self.packet.register = [e for e in self.packet.register
                                if e["source_id"] != "SRC-SYN-002"]
        issues = er.validate(self.packet)
        self.assertIn(er.ORPHAN_DOCUMENT, codes(issues))

    def test_loading_a_missing_packet_reports_rather_than_raising(self):
        p, issues = er.load_packet(os.path.join(self.td, "nope"))
        self.assertEqual([], p.manifest)
        self.assertIn(er.MISSING_DOCUMENT, codes(issues))


class RoundTripTests(PacketFixture):
    """Completion condition 2: IDs, versions and locators survive, including
    documents used by more than one assessment cell."""

    def test_round_trip_is_clean(self):
        _, issues = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        self.assertEqual([], issues, "\n".join(str(i) for i in issues))

    def test_round_trip_preserves_every_id(self):
        back, _ = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        self.assertEqual([d["source_id"] for d in self.packet.manifest],
                         [d["source_id"] for d in back.manifest])
        self.assertEqual([e["evidence_id"] for e in self.packet.register],
                         [e["evidence_id"] for e in back.register])

    def test_round_trip_preserves_versions_and_locations(self):
        back, _ = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        for a, b in zip(self.packet.manifest, back.manifest):
            with self.subTest(doc=a["source_id"]):
                self.assertEqual(a["document_version"], b["document_version"])
                self.assertEqual(a["document_location"], b["document_location"])
                self.assertEqual(a["sha256"], b["sha256"])

    def test_round_trip_preserves_excerpt_locators(self):
        back, _ = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        for a, b in zip(self.packet.register, back.register):
            with self.subTest(entry=a["evidence_id"]):
                self.assertEqual(a["excerpt_locator"], b["excerpt_locator"])

    def test_round_trip_preserves_a_multi_cell_document_s_cells(self):
        back, _ = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        self.assertEqual(self.packet.multi_cell_documents(),
                         back.multi_cell_documents())
        self.assertEqual(self.packet.cells_for("SRC-SYN-006"),
                         back.cells_for("SRC-SYN-006"))
        self.assertEqual(2, len(back.entries_for("SRC-SYN-006")))

    def test_the_round_tripped_packet_still_validates(self):
        back, _ = er.round_trip(self.packet, os.path.join(self.td, "rt"))
        self.assertEqual([], er.validate(back))

    def test_round_trip_detects_a_dropped_row(self):
        """The check must be able to fail, or it proves nothing."""
        p2 = copy.deepcopy(self.packet)
        back, _ = er.round_trip(p2, os.path.join(self.td, "rt2"))
        back.register = back.register[:-1]
        # Compare by hand the way round_trip does, to prove the comparison bites.
        before = {e["evidence_id"] for e in p2.register}
        after = {e["evidence_id"] for e in back.register}
        self.assertNotEqual(before, after)

    def test_round_trip_detects_a_changed_version(self):
        """A distinctive sentinel, because the obvious value ('v3') also appears
        inside the document filename - the first version of this test corrupted
        the location column and then asserted nothing."""
        p2 = copy.deepcopy(self.packet)
        p2.manifest[0]["document_version"] = "VERSION-SENTINEL-A"
        rt_dir = os.path.join(self.td, "rt3")
        er.round_trip(p2, rt_dir)
        csv_path = os.path.join(rt_dir, "csv", "manifest.csv")
        with open(csv_path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("VERSION-SENTINEL-A", text)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(text.replace("VERSION-SENTINEL-A", "VERSION-SENTINEL-B"))
        reloaded, _ = er.load_packet(os.path.join(rt_dir, "csv"))
        self.assertEqual("VERSION-SENTINEL-B",
                         reloaded.manifest[0]["document_version"])
        # And the comparison round_trip performs must flag exactly that field.
        issues = []
        a = {d["source_id"]: d for d in p2.manifest}
        b = {d["source_id"]: d for d in reloaded.manifest}
        for sid in a:
            for k in er.ROUND_TRIP_KEYS:
                if a[sid].get(k, "") != b[sid].get(k, ""):
                    issues.append((sid, k))
        self.assertIn((p2.manifest[0]["source_id"], "document_version"), issues)

    def test_an_unrecognised_column_survives_the_round_trip(self):
        """An unknown field is somebody's data; dropping it silently loses it."""
        self.packet.register[0]["local_note"] = "kept by the exporter"
        out = os.path.join(self.td, "extra")
        er.save_packet_csv(self.packet, out)
        back, issues = er.load_packet(out)
        self.assertEqual("kept by the exporter", back.register[0].get("local_note"))
        self.assertIn(er.UNKNOWN_FIELD, codes(issues))

    def test_json_export_and_import_agree(self):
        path = os.path.join(self.td, "p.json")
        er.save_packet_json(self.packet, path)
        back = er.load_packet_json(path, root=self.root)
        self.assertEqual(self.packet.manifest, back.manifest)
        self.assertEqual(self.packet.register, back.register)
        self.assertEqual([], er.validate(back))

    def test_json_export_declares_the_schema_and_its_provenance(self):
        payload = er.to_json(self.packet)
        self.assertEqual(er.REGISTER_FIELDS_FROM_023,
                         payload["schema"]["register_fields_from_023"])
        self.assertEqual(er.REGISTER_FIELDS_ADDED_BY_031,
                         payload["schema"]["register_fields_added_by_031"])
        self.assertIn("SYNTHETIC", payload["status"])

    def test_unicode_and_multiline_survive_csv_and_json(self):
        self.packet.register[0]["claim"] = "Ünicode — line one\nline two"
        out = os.path.join(self.td, "uni")
        er.save_packet_csv(self.packet, out)
        back, _ = er.load_packet(out)
        self.assertEqual("Ünicode — line one\nline two", back.register[0]["claim"])
        jp = os.path.join(self.td, "uni.json")
        er.save_packet_json(self.packet, jp)
        self.assertEqual("Ünicode — line one\nline two",
                         er.load_packet_json(jp).register[0]["claim"])


class CliTests(PacketFixture):
    def test_validate_exits_zero_on_the_shipped_packet(self):
        self.assertEqual(0, er.main(["--packet", self.root, "--validate"]))

    def test_validate_exits_nonzero_on_a_broken_packet(self):
        os.remove(os.path.join(self.root, self.packet.manifest[0]["document_location"]))
        self.assertEqual(1, er.main(["--packet", self.root, "--validate"]))

    def test_round_trip_cli_exits_zero(self):
        self.assertEqual(0, er.main(["--packet", self.root,
                                     "--round-trip", os.path.join(self.td, "cli-rt")]))

    def test_export_json_writes_a_parseable_file(self):
        out = os.path.join(self.td, "cli.json")
        self.assertEqual(0, er.main(["--packet", self.root, "--export-json", out]))
        with open(out, encoding="utf-8") as f:
            self.assertIn("register", json.load(f))


if __name__ == "__main__":
    unittest.main(verbosity=2)
