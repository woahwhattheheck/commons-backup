"""Real CSV, canonical-loader, CLI and create-only output coverage for onboarding."""
import copy
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import import_mapper as mapper
import reorder_assistant as engine


class ImportMapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "retailer.csv"
        self.profile_path = self.root / "stock-profile.json"
        self.output = self.root / "stock.csv"
        self.profile = {
            "schema": mapper.SCHEMA, "kind": "stock", "delimiter": ";",
            "columns": {"sku": "Item", "name": "Label", "on_hand": "Qty", "unit": "Unit"},
            "constants": {"on_order": "0", "allocated": "2"},
        }
        self.source.write_bytes(b'Item;Label;Qty;Unit;Internal\r\n0007;Filter;3;each;private-note\r\n')
        self.save_profile()

    def save_profile(self):
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(Path(mapper.__file__)), *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def convert(self):
        return mapper.convert(self.source, self.profile_path, self.output)

    def test_maps_exact_headers_constants_and_leading_zero_id(self):
        report = self.convert()
        stock = engine.load_stock(self.output)
        self.assertEqual(["0007"], list(stock))
        self.assertEqual((3, 0, 2, 1), (stock["0007"].on_hand, stock["0007"].on_order,
                                     stock["0007"].allocated, stock["0007"].position))
        self.assertTrue(report["output_created"])
        self.assertEqual(["Internal"], report["ignored_source_columns"])
        self.assertEqual({"constant": "0"}, report["field_sources"]["on_order"])
        self.assertEqual(0, report["orders_sent"])

    def test_preview_does_not_create_output_and_hashes_actual_bytes(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        report = mapper.convert(self.source, self.profile_path)
        self.assertFalse(report["output_created"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), report["source_sha256"])
        written = self.convert()
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), written["output_sha256"])
        self.assertEqual(report["output_sha256"], written["output_sha256"])

    def test_unicode_multiline_bom_and_physical_source_locations(self):
        self.source.write_bytes(('\ufeffItem;Label;Qty;Unit;Internal\r\n\r\n'
                                 '0007;"Café filter\r\n東京";3;each;note\r\n').encode())
        report = self.convert()
        self.assertEqual("Café filter\r\n東京", engine.load_stock(self.output)["0007"].name)
        self.assertEqual([{"output_record": 1, "source_start_line": 3, "source_end_line": 4}],
                         report["source_locations"])

    def test_whitespace_is_trimmed_as_in_canonical_loaders(self):
        self.source.write_text('Item;Label;Qty;Unit;Internal\n 0007 ; Filter ; 3 ; each ;note\n')
        self.convert()
        row = next(csv.DictReader(io.StringIO(self.output.read_text())))
        self.assertEqual(("0007", "Filter", "3", "each"), tuple(row[k] for k in ("sku", "name", "on_hand", "unit")))

    def test_missing_destination_fields_are_never_inferred(self):
        del self.profile["constants"]["on_order"]
        self.save_profile()
        with self.assertRaisesRegex(mapper.MappingError, "missing=.*on_order"):
            self.convert()
        self.assertFalse(self.output.exists())

    def test_missing_source_column_is_not_fuzzy_matched(self):
        self.profile["columns"]["sku"] = "item"
        self.save_profile()
        with self.assertRaisesRegex(mapper.MappingError, "source columns are absent"):
            self.convert()

    def test_incomplete_profiles_are_rejected_even_for_empty_source(self):
        self.source.write_text('Item;Label;Qty;Unit;Internal\n')
        del self.profile["constants"]["allocated"]
        self.save_profile()
        with self.assertRaises(mapper.MappingError):
            self.convert()

    def test_unknown_profile_fields_and_duplicate_destinations_rejected(self):
        variants = [dict(self.profile, guess_headers=True),
                    {**self.profile, "constants": {**self.profile["constants"], "sku": "other"}},
                    {**self.profile, "constants": {**self.profile["constants"], "on_hnad": "0"}}]
        for bad in variants:
            with self.subTest(profile=bad), self.assertRaises(mapper.MappingError):
                mapper.map_bytes(self.source.read_bytes(), bad)

    def test_profile_types_fail_with_mapping_error(self):
        variants = [None, [], True, {}, dict(self.profile, kind=[]), dict(self.profile, columns=[]),
                    dict(self.profile, constants=None), dict(self.profile, delimiter=False),
                    dict(self.profile, constants={"allocated": 2, "on_order": "0"})]
        for bad in variants:
            with self.subTest(profile=bad), self.assertRaises(mapper.MappingError):
                mapper.map_bytes(self.source.read_bytes(), bad)

    def test_duplicate_json_keys_rejected_at_root_and_nested_fields(self):
        variants = [json.dumps(self.profile)[:-1] + ', "kind":"stock"}',
                    json.dumps(self.profile).replace('"allocated": "2"', '"allocated":"2","allocated":"3"')]
        for text in variants:
            self.profile_path.write_text(text)
            with self.subTest(text=text), self.assertRaisesRegex(mapper.MappingError, "duplicate JSON key"):
                self.convert()

    def test_invalid_json_encoding_constants_and_lone_surrogate_rejected(self):
        variants = [b'{', b'\xff', b'{"kind": NaN}',
                    json.dumps({**self.profile, "constants": {"allocated": "2", "on_order": "\ud800"}}).encode()]
        for data in variants:
            self.profile_path.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(mapper.MappingError):
                self.convert()
        self.assertFalse(self.output.exists())

    def test_invalid_source_csv_fails_without_output(self):
        variants = [b'', b'Item;Item;Qty;Unit;Internal\na;b;3;each;x\n',
                    b'Item;;Qty;Unit;Internal\na;b;3;each;x\n',
                    b'Item;Label;Qty;Unit;Internal\na;b;3;each;x;extra\n',
                    b'Item;Label;Qty;Unit;Internal\na;b;3;each\n',
                    b'Item;Label;Qty;Unit;Internal\na;"unterminated;3;each;x\n', b'\xff']
        for data in variants:
            with self.subTest(data=data), self.assertRaises(mapper.MappingError):
                mapper.map_bytes(data, self.profile)
        self.assertFalse(self.output.exists())

    def test_canonical_stock_numbers_and_duplicate_skus_are_validated(self):
        for quantity in ("-1", "1.5", "NaN", "Infinity", "", "1,000"):
            data = f'Item;Label;Qty;Unit;Internal\n0007;Filter;{quantity};each;x\n'.encode()
            with self.subTest(quantity=quantity), self.assertRaisesRegex(mapper.MappingError, "canonical stock validation"):
                mapper.map_bytes(data, self.profile)
        with self.assertRaisesRegex(mapper.MappingError, "duplicate sku"):
            mapper.map_bytes(self.source.read_bytes() + b'0007;Filter;3;each;dup\n', self.profile)

    def test_empty_explicit_cells_are_distinct_from_short_rows(self):
        self.source.write_text('Item;Label;Qty;Unit;Internal\n0007;;3;each;\n')
        self.convert()
        self.assertEqual("", engine.load_stock(self.output)["0007"].name)

    def test_supported_delimiters_and_quoted_separator_preserve_values(self):
        for delimiter in mapper.DELIMITERS:
            profile = dict(self.profile, delimiter=delimiter)
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, delimiter=delimiter)
            writer.writerow(["Item", "Label", "Qty", "Unit", "Internal"])
            writer.writerow(["0007", f'Filter{delimiter} "large"', "3", "each", ""])
            output, _ = mapper.map_bytes(stream.getvalue().encode(), profile)
            row = next(csv.DictReader(io.StringIO(output.decode())))
            self.assertEqual(f'Filter{delimiter} "large"', row["name"])

    def test_constants_are_explicit_text_and_not_profile_mutations(self):
        original = copy.deepcopy(self.profile)
        mapper.map_bytes(self.source.read_bytes(), self.profile)
        self.assertEqual(original, self.profile)
        self.profile["constants"]["on_order"] = " 0 "
        _, report = mapper.map_bytes(self.source.read_bytes(), self.profile)
        self.assertEqual("0", report["preview_rows"][0]["on_order"])
        self.assertEqual(" 0 ", report["field_sources"]["on_order"]["constant"])

    def test_existing_outputs_are_never_replaced(self):
        self.output.write_bytes(b'previous valid output\n')
        with self.assertRaises(FileExistsError):
            self.convert()
        self.assertEqual(b'previous valid output\n', self.output.read_bytes())
        self.assertFalse(list(self.root.glob('.reorder-map-*')))

    def test_source_and_profile_output_aliases_preserve_inputs(self):
        for output in (self.source, self.profile_path):
            previous = output.read_bytes()
            with self.subTest(output=output), self.assertRaises(FileExistsError):
                mapper.convert(self.source, self.profile_path, output)
            self.assertEqual(previous, output.read_bytes())

    def test_symlink_hardlink_and_dangling_symlink_are_not_followed(self):
        original = self.source.read_bytes()
        for kind in ("symlink", "hardlink", "dangling"):
            destination = self.root / kind
            if kind == "hardlink":
                os.link(self.source, destination)
            else:
                destination.symlink_to(self.source if kind == "symlink" else self.root / "absent")
            with self.subTest(kind=kind), self.assertRaises(FileExistsError):
                mapper.convert(self.source, self.profile_path, destination)
        self.assertEqual(original, self.source.read_bytes())
        self.assertFalse((self.root / "absent").exists())

    def test_concurrent_export_to_same_path_has_one_complete_winner(self):
        def writer():
            try:
                self.convert()
                return "created"
            except FileExistsError:
                return "exists"
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: writer(), range(6)))
        self.assertEqual(1, results.count("created"))
        self.assertEqual(5, results.count("exists"))
        self.assertEqual(3, engine.load_stock(self.output)["0007"].on_hand)
        self.assertFalse(list(self.root.glob('.reorder-map-*')))

    def test_failed_create_does_not_leave_partial_output_or_staging_file(self):
        with mock.patch.object(mapper.os, "link", side_effect=OSError("unsupported filesystem")):
            with self.assertRaises(OSError):
                self.convert()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.reorder-map-*')))

    def test_source_profile_row_and_output_limits(self):
        with mock.patch.object(mapper, "MAX_SOURCE", 10), self.assertRaises(mapper.MappingError):
            self.convert()
        with mock.patch.object(mapper, "MAX_PROFILE", 10), self.assertRaises(mapper.MappingError):
            self.convert()
        with mock.patch.object(mapper, "MAX_ROWS", 0), self.assertRaises(mapper.MappingError):
            self.convert()
        with mock.patch.object(mapper, "MAX_OUTPUT", 10), self.assertRaises(mapper.MappingError):
            self.convert()
        self.assertFalse(self.output.exists())

    def test_rules_and_catalog_use_their_real_loaders(self):
        cases = [("rules", b'Code,Trigger,Target,Supplier\n0007,2,10,SUP-1\n',
                  dict(zip(mapper.FIELDS["rules"], ("Code", "Trigger", "Target", "Supplier")))),
                 ("catalog", b'Vendor,Part,Code,Label,Price,Available,Lead,Instead\nSUP-1,FA-100,0007,Filter,4.25,20,2,\n',
                  dict(zip(mapper.FIELDS["catalog"], ("Vendor", "Part", "Code", "Label", "Price", "Available", "Lead", "Instead"))))]
        for kind, data, columns in cases:
            with self.subTest(kind=kind):
                profile = {"schema": mapper.SCHEMA, "kind": kind, "columns": columns}
                output, report = mapper.map_bytes(data, profile)
                self.assertEqual(f"load_{kind} passed", report["validation"])
                self.assertIn(b"0007", output)
                bad = data.replace(b',10,', b',1,') if kind == "rules" else data.replace(b'4.25', b'NaN')
                with self.assertRaisesRegex(mapper.MappingError, f"canonical {kind} validation"):
                    mapper.map_bytes(bad, profile)

    def test_real_cli_inspect_preview_and_create(self):
        result = self.cli("inspect", "--source", self.source, "--delimiter", ";")
        self.assertEqual(0, result.returncode, result.stderr)
        inspected = json.loads(result.stdout)
        self.assertEqual("0007", inspected["preview_rows"][0]["Item"])
        result = self.cli("map", "--source", self.source, "--profile", self.profile_path)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["output_created"])
        result = self.cli("map", "--source", self.source, "--profile", self.profile_path, "--out", self.output)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, json.loads(result.stdout)["row_count"])
        self.assertEqual(3, engine.load_stock(self.output)["0007"].on_hand)

    def test_real_cli_invalid_mapping_preserves_existing_output(self):
        self.source.write_bytes(self.source.read_bytes().replace(b';3;', b';1.5;'))
        self.output.write_bytes(b'keep this exact file\n')
        result = self.cli("map", "--source", self.source, "--profile", self.profile_path, "--out", self.output)
        self.assertEqual(2, result.returncode)
        self.assertIn("canonical stock validation failed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(b'keep this exact file\n', self.output.read_bytes())

    def test_real_cli_missing_file_and_invalid_profile_have_clean_errors(self):
        result = self.cli("inspect", "--source", self.root / "absent.csv")
        self.assertEqual(2, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.profile_path.write_bytes(b'\xff')
        result = self.cli("map", "--source", self.source, "--profile", self.profile_path)
        self.assertEqual(2, result.returncode)
        self.assertNotIn("Traceback", result.stderr)

    def test_preview_is_capped_but_every_record_is_validated(self):
        data = b'Item;Label;Qty;Unit;Internal\n' + b''.join(f'{i:04d};Filter;3;each;note\n'.encode() for i in range(8))
        _, report = mapper.map_bytes(data, self.profile)
        self.assertEqual(8, report["row_count"])
        self.assertEqual(5, len(report["preview_rows"]))
        self.assertEqual(8, len(report["source_locations"]))
        with self.assertRaisesRegex(mapper.MappingError, "duplicate sku"):
            mapper.map_bytes(data + b'0000;Filter;3;each;duplicate-beyond-preview\n', self.profile)

    def test_documented_example_maps_existing_example_stock_exactly(self):
        product = Path(mapper.__file__).parent
        report = mapper.convert(product / "mapping_examples/stock-export.csv",
                                product / "mapping_examples/stock-profile.json", self.output)
        stock = engine.load_stock(self.output)
        self.assertEqual(engine.load_stock(product / "examples/stock.csv"), stock)
        plan = engine.build_plan(stock, engine.load_rules(product / "examples/rules.csv"),
                                 engine.load_catalog(product / "examples/catalog.csv"), "2026-09-08")
        self.assertEqual("38.25", plan["purchase_orders"][0]["total"])
        self.assertEqual(9, plan["purchase_orders"][0]["lines"][0]["quantity"])
        self.assertEqual(3, plan["exceptions"][0]["unfilled_qty"])
        self.assertTrue(plan["exceptions"][0]["alternative_suggestions"][0]["requires_approval"])
        self.assertEqual(["Internal note"], report["ignored_source_columns"])

    def test_real_mapped_inputs_reach_planning_receiving_and_replay(self):
        self.convert()
        rules = self.root / "rules.csv"
        catalog = self.root / "catalog.csv"
        for kind, path, source, columns in (
            ("rules", rules, b'Code,Trigger,Target,Vendor\n0007,2,10,SUP-1\n',
             dict(zip(mapper.FIELDS["rules"], ("Code", "Trigger", "Target", "Vendor")))),
            ("catalog", catalog, b'Vendor,Part,Code,Name,Price,Supply,Days,Alt\nSUP-1,FA-100,0007,Filter,4.25,20,2,\n',
             dict(zip(mapper.FIELDS["catalog"], ("Vendor", "Part", "Code", "Name", "Price", "Supply", "Days", "Alt"))))):
            profile = {"schema": mapper.SCHEMA, "kind": kind, "columns": columns}
            encoded, _ = mapper.map_bytes(source, profile)
            mapper.create_output(path, encoded)
        plan_path = self.root / "plan.json"
        command = [sys.executable, "-B", str(Path(engine.__file__)), "plan", "--stock", str(self.output),
                   "--rules", str(rules), "--catalog", str(catalog), "--as-of", "2026-09-08", "--out", str(plan_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        plan = json.loads(plan_path.read_text())
        self.assertEqual(9, plan["purchase_orders"][0]["lines"][0]["quantity"])
        self.assertEqual("38.25", plan["purchase_orders"][0]["total"])
        self.assertEqual(0, plan["summary"]["orders_sent"])
        receipt = [{"receipt_id": "R1", "received_at": "2026-09-09", "supplier_id": "SUP-1",
                    "supplier_sku": "FA-100", "sku": "0007", "quantity": "4"}]
        stock = engine.load_stock(self.output)
        updated, history = engine.apply_receipts(stock, plan, receipt)
        replayed, log = engine.apply_receipts(updated, plan, receipt, prior_log=history)
        self.assertEqual(7, updated["0007"].on_hand)
        self.assertEqual(updated, replayed)
        self.assertEqual(0, log["new_count"])


if __name__ == "__main__":
    unittest.main()
