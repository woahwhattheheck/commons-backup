"""Actual local command and synthetic rehearsal contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATE))

import packet_rehearsal as rehearsal
from packet_quality import canonical_bytes


class PacketCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet_path = self.root / "packet.json"
        self.map_path = self.root / "image-map.json"
        _, packet, payloads, _ = next(rehearsal.cases())
        self.packet_path.write_bytes(canonical_bytes(packet))
        image_map = {}
        for slot, payload in payloads.items():
            name = "img-" + slot + ".png"
            (self.root / name).write_bytes(payload)
            image_map["img-" + slot] = name
        self.map_path.write_bytes(canonical_bytes(image_map))

    def run_command(self, *args, script="packet_cli.py"):
        optimize = ["-O"] if sys.flags.optimize else []
        return subprocess.run(
            [sys.executable, *optimize, str(GATE / script), *map(str, args)],
            cwd=self.root, capture_output=True, timeout=30,
        )

    def inspect(self, *args):
        return self.run_command("inspect", "--packet", self.packet_path, "--image-map", self.map_path, *args)

    def test_actual_inspect_from_other_directory_and_verify(self):
        receipt_path = self.root / "receipt.json"
        run = self.inspect("--output", receipt_path)
        self.assertEqual(run.returncode, 0, run.stderr)
        receipt = json.loads(receipt_path.read_bytes())
        self.assertEqual(receipt["decision"]["trace"]["action"], "ACCEPT_FOR_HUMAN_REVIEW")
        verify = self.run_command("verify", "--packet", self.packet_path, "--image-map", self.map_path, "--receipt", receipt_path)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertTrue(json.loads(verify.stdout)["verified"])

    def test_stdout_receipt_is_deterministic(self):
        first, second = self.inspect(), self.inspect()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(all(v is False for v in json.loads(first.stdout)["decision"]["authority"].values()))

    def test_existing_output_is_preserved(self):
        output = self.root / "existing.json"
        output.write_bytes(b"existing operator work")
        run = self.inspect("--output", output)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(output.read_bytes(), b"existing operator work")
        self.assertEqual(run.stdout, b"")

    def test_malformed_packet_creates_no_output(self):
        self.packet_path.write_bytes(b'{"packet_id":"first","packet_id":"second"}')
        output = self.root / "refused.json"
        run = self.inspect("--output", output)
        self.assertEqual(run.returncode, 2)
        self.assertFalse(output.exists())
        self.assertEqual(run.stdout, b"")

    def test_missing_extra_and_invalid_image_map_are_rejected(self):
        good = json.loads(self.map_path.read_bytes())
        for bad in ({}, {**good, "unused": "unused.png"}, {"img-front": True}, []):
            with self.subTest(bad=bad):
                self.map_path.write_bytes(canonical_bytes(bad))
                run = self.inspect()
                self.assertEqual(run.returncode, 2)
                self.assertEqual(run.stdout, b"")

    def test_changed_image_and_changed_receipt_do_not_verify(self):
        run = self.inspect()
        self.assertEqual(run.returncode, 0, run.stderr)
        receipt = json.loads(run.stdout)
        receipt["decision"]["authority"]["payment_authorized"] = True
        receipt_path = self.root / "changed.json"
        receipt_path.write_bytes(canonical_bytes(receipt))
        verify = self.run_command("verify", "--packet", self.packet_path, "--image-map", self.map_path, "--receipt", receipt_path)
        self.assertEqual(verify.returncode, 2)
        (self.root / "img-front.png").write_bytes(b"changed bytes")
        self.assertEqual(self.inspect().returncode, 2)

    def test_rehearsal_has_all_actions_and_exact_inventory(self):
        first, second = self.root / "first", self.root / "second"
        for dest in (first, second):
            run = self.run_command(dest, script="packet_rehearsal.py")
            self.assertEqual(run.returncode, 0, run.stderr)
        files_a = {p.relative_to(first).as_posix(): p.read_bytes() for p in first.rglob("*") if p.is_file()}
        files_b = {p.relative_to(second).as_posix(): p.read_bytes() for p in second.rglob("*") if p.is_file()}
        self.assertEqual(files_a, files_b)
        summary = json.loads(files_a["summary.json"])
        self.assertEqual(len(summary["cases"]), 9)
        self.assertEqual({r["action"] for r in summary["cases"]}, {
            "ACCEPT_FOR_HUMAN_REVIEW", "REQUEST_MISSING_VIEW", "HOLD_DUPLICATE_EVIDENCE",
            "REQUEST_RECAPTURE", "HOLD_UNSAFE_OR_UNREADABLE", "INPUT_REJECTED",
        })
        self.assertTrue(summary["s3_fixture"]["outer_mutation_rejected"])
        self.assertIs(summary["s3_fixture"]["aws_execution_proven"], False)
        self.assertNotIn("digest-mismatch/receipt.json", files_a)
        inventory = json.loads(files_a["INVENTORY.json"])["files"]
        self.assertEqual(set(inventory), set(files_a) - {"INVENTORY.json"})
        for name, item in inventory.items():
            self.assertEqual(item, {"bytes": len(files_a[name]), "sha256": hashlib.sha256(files_a[name]).hexdigest()})

    def test_rehearsal_refuses_existing_directory(self):
        destination = self.root / "operator"
        destination.mkdir()
        marker = destination / "notes.txt"
        marker.write_bytes(b"retain these notes")
        run = self.run_command(destination, script="packet_rehearsal.py")
        self.assertEqual(run.returncode, 2)
        self.assertEqual(marker.read_bytes(), b"retain these notes")
        self.assertEqual(list(destination.iterdir()), [marker])


if __name__ == "__main__":
    unittest.main()
