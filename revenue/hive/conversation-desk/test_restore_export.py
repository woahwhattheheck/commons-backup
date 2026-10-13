"""Restore-only acceptance for Conversation Desk exports; synthetic data only."""
from __future__ import annotations

import base64
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import app
import restore_export

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=")
PNG64 = base64.b64encode(PNG).decode("ascii")


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_db = self.root / "source.sqlite3"
        store = app.Store(self.source_db)
        first = store.create({
            "title": "Fictional weekend",
            "transcript": "Alex: Easy walk or long hike?",
            "context": "Fictional demo only",
            "intent": "respond",
            "reply": "I prefer an easy walk",
            "question": "Which trail do you like",
            "draft": "I prefer an easy walk. Which trail do you like?",
        })
        first = store.add_image(first["id"], {"name": "fictional.png", "data_base64": PNG64}, first["revision"])
        store.update(first["id"], {"draft": "Edited fictional draft"}, first["revision"])
        store.create({
            "title": "Second synthetic conversation",
            "transcript": "No screenshot here",
            "context": "",
            "intent": "boundary",
            "reply": "I need to stop here",
            "question": "",
            "draft": "I need to stop here.",
        })
        self.export = store.export()
        self.export_path = self.root / "export.json"
        self.write_export(self.export)

    def write_export(self, value=None, path=None):
        path = path or self.export_path
        path.write_text(json.dumps(self.export if value is None else value), encoding="utf-8")
        return path

    def target(self, name="restored.sqlite3"):
        return self.root / name

    def assert_semantics(self, receipt, destination):
        restored = app.Store(destination).export()
        source_convs = {row["id"]: row for row in self.export["conversations"]}
        target_convs = {row["id"]: row for row in restored["conversations"]}
        source_images = {row["id"]: row for row in self.export["images"]}
        target_images = {row["id"]: row for row in restored["images"]}
        self.assertEqual(len(source_convs), len(target_convs))
        self.assertEqual(len(source_images), len(target_images))
        for old_id, source in source_convs.items():
            target = target_convs[receipt["conversation_id_map"][old_id]]
            self.assertEqual({key: target[key] for key in app.FIELDS}, {key: source[key] for key in app.FIELDS})
            self.assertEqual(
                [meta["id"] for meta in target["images"]],
                [receipt["image_id_map"][meta["id"]] for meta in source["images"]],
            )
        for old_id, source in source_images.items():
            target = target_images[receipt["image_id_map"][old_id]]
            self.assertEqual(target["conversation_id"], receipt["conversation_id_map"][source["conversation_id"]])
            self.assertEqual((target["name"], target["mime"], target["sha256"]), (source["name"], source["mime"], source["sha256"]))
            self.assertEqual(base64.b64decode(target["data_base64"]), base64.b64decode(source["data_base64"]))

    def test_export_restore_reexport_preserves_saved_fields_and_original_image_bytes(self):
        destination = self.target()
        receipt = restore_export.restore_export(self.export_path, destination)
        self.assertTrue(receipt["restored"])
        self.assertEqual((receipt["conversations"], receipt["images"]), (2, 1))
        self.assertEqual(receipt["regenerated"], ["ids", "revisions", "timestamps"])
        self.assertTrue(destination.is_file())
        self.assert_semantics(receipt, destination)

    def test_empty_export_restores_to_usable_empty_workspace(self):
        value = {"format": restore_export.FORMAT, "exported": self.export["exported"], "conversations": [], "images": []}
        self.write_export(value)
        destination = self.target()
        receipt = restore_export.restore_export(self.export_path, destination)
        self.assertEqual((receipt["conversations"], receipt["images"]), (0, 0))
        self.assertEqual(app.Store(destination).export()["conversations"], [])

    def test_existing_destination_or_dangling_link_is_never_overwritten(self):
        destination = self.target()
        destination.write_bytes(b"sentinel-existing-database")
        with self.assertRaisesRegex(restore_export.RestoreError, "Refusing to overwrite"):
            restore_export.restore_export(self.export_path, destination)
        self.assertEqual(destination.read_bytes(), b"sentinel-existing-database")
        destination.unlink()
        destination.symlink_to(self.root / "missing-target")
        with self.assertRaisesRegex(restore_export.RestoreError, "Refusing to overwrite"):
            restore_export.restore_export(self.export_path, destination)
        self.assertTrue(destination.is_symlink())

    def test_tampered_image_integrity_and_association_fail_before_destination(self):
        image_id = self.export["images"][0]["id"]
        cases = []
        changed = copy.deepcopy(self.export); changed["images"][0]["sha256"] = "0" * 64; cases.append(("sha", changed))
        changed = copy.deepcopy(self.export); changed["images"][0]["mime"] = "image/jpeg"; cases.append(("mime", changed))
        changed = copy.deepcopy(self.export); changed["images"][0]["data_base64"] = "AAAA"; cases.append(("bytes", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["images"][0]["size"] += 1; cases.append(("size", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["images"][0]["name"] = "other.png"; cases.append(("meta", changed))
        changed = copy.deepcopy(self.export); changed["images"][0]["conversation_id"] = "unknown"; cases.append(("owner", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["images"] = []; cases.append(("nested", changed))
        for index, (name, value) in enumerate(cases):
            with self.subTest(case=name):
                path = self.write_export(value, self.root / f"tamper-{index}.json")
                destination = self.target(f"tamper-{index}.sqlite3")
                with self.assertRaises(restore_export.RestoreError):
                    restore_export.restore_export(path, destination)
                self.assertFalse(destination.exists())
        self.assertIn(image_id, {row["id"] for row in self.export["images"]})

    def test_duplicate_ids_and_invalid_saved_fields_fail_closed(self):
        cases = []
        changed = copy.deepcopy(self.export); changed["conversations"].append(copy.deepcopy(changed["conversations"][0])); cases.append(("duplicate conversation", changed))
        changed = copy.deepcopy(self.export); changed["images"].append(copy.deepcopy(changed["images"][0])); cases.append(("duplicate image", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["title"] = " "; cases.append(("blank title", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["intent"] = "invented"; cases.append(("bad intent", changed))
        changed = copy.deepcopy(self.export); changed["conversations"][0]["revision"] = True; cases.append(("bool revision", changed))
        for index, (name, value) in enumerate(cases):
            with self.subTest(case=name):
                path = self.write_export(value, self.root / f"bad-{index}.json")
                destination = self.target(f"bad-{index}.sqlite3")
                with self.assertRaises(restore_export.RestoreError):
                    restore_export.restore_export(path, destination)
                self.assertFalse(destination.exists())

    def test_wrong_shape_format_and_nonfinite_json_are_rejected(self):
        cases = [
            ("wrong format", {**self.export, "format": "conversation-desk-export-v2"}),
            ("extra field", {**self.export, "unexpected": 1}),
            ("not object", []),
        ]
        for index, (name, value) in enumerate(cases):
            with self.subTest(case=name):
                path = self.write_export(value, self.root / f"shape-{index}.json")
                with self.assertRaises(restore_export.RestoreError):
                    restore_export.restore_export(path, self.target(f"shape-{index}.sqlite3"))
        nan_path = self.root / "nan.json"
        nan_path.write_text('{"format":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(restore_export.RestoreError, "finite JSON"):
            restore_export.restore_export(nan_path, self.target("nan.sqlite3"))

    def test_destination_parent_must_already_exist(self):
        destination = self.root / "absent" / "restored.sqlite3"
        with self.assertRaisesRegex(restore_export.RestoreError, "parent directory"):
            restore_export.restore_export(self.export_path, destination)
        self.assertFalse(destination.exists())

    def test_concurrent_restores_to_same_path_have_exactly_one_winner(self):
        destination = self.target("race.sqlite3")
        def attempt(_):
            try:
                return restore_export.restore_export(self.export_path, destination)
            except restore_export.RestoreError as exc:
                return str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        winners = [value for value in outcomes if isinstance(value, dict)]
        losers = [value for value in outcomes if isinstance(value, str)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 7)
        self.assertTrue(all("Destination appeared" in value or "Refusing to overwrite" in value for value in losers))
        self.assert_semantics(winners[0], destination)

    def test_cli_roundtrip_and_failure_diagnostic(self):
        destination = self.target("cli.sqlite3")
        command = [sys.executable, "-B", "restore_export.py", str(self.export_path), str(destination)]
        success = subprocess.run(command, cwd=Path(__file__).parent, capture_output=True, text=True, check=False)
        self.assertEqual(success.returncode, 0, success.stderr)
        receipt = json.loads(success.stdout)
        self.assertTrue(receipt["restored"])
        self.assertEqual(success.stderr, "")
        failure = subprocess.run(command, cwd=Path(__file__).parent, capture_output=True, text=True, check=False)
        self.assertEqual(failure.returncode, 2)
        self.assertFalse(json.loads(failure.stdout)["restored"])
        self.assertEqual(failure.stderr, "")

    def test_source_screenshot_hash_is_known_and_preserved(self):
        source = self.export["images"][0]
        self.assertEqual(source["sha256"], hashlib.sha256(PNG).hexdigest())
        destination = self.target("hash.sqlite3")
        receipt = restore_export.restore_export(self.export_path, destination)
        restored = {row["id"]: row for row in app.Store(destination).export()["images"]}
        self.assertEqual(restored[receipt["image_id_map"][source["id"]]]["sha256"], source["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
