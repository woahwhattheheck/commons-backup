"""Executed tests for commercial semantics, portable assembly and source integrity."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import packets as p

HERE = Path(__file__).resolve().parent


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(HERE / "fixtures", self.root / "fixtures")
        self.plan = p.load(HERE / "example.json")
        self.plan_path = self.root / "plan.json"
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.plan_path.write_bytes(p.canonical(self.plan))

    def reject(self):
        with self.assertRaises(p.PacketError):
            p.validate(self.plan)

    def build(self):
        self.save()
        return p.assemble(self.plan_path, self.root, self.root / "out")

    def test_real_upstream_bytes(self):
        pins = {
            "COMMERCIAL.md": "b6e9ca58984c15d96b497f3bb51000992fdb9b5f",
            "evidence.csv": "fe11729edc5ec8c0c6e6adbd6238777118acc16d",
            "findings.csv": "f3dfb204685e72510a4c1bf591e72529702020e9",
            "recommendations.csv": "e81ad1fe6cc691ae8b00d47ab3052fca13e4b047",
        }
        for name, sha in pins.items():
            self.assertEqual(p.git_blob((self.root / "fixtures" / name).read_bytes()), sha)

    def test_all_three_packages_and_separate_commercial_states(self):
        report = self.build()
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["milestone_sum_cents"], 2400000)
        self.assertEqual(report["separate_option_cents"], 400000)
        self.assertEqual(report["bound_source_artifacts"], 6)
        for packet in report["packets"]:
            self.assertEqual(packet["artifact_conformance"], "NOT_ASSESSED")
            self.assertEqual(packet["real_commercial_event"], "NOT_ESTABLISHED")

    def test_sources_unchanged_across_delivery_stages(self):
        self.build()
        for name in ("evidence", "findings", "recommendations"):
            original = (self.root / "fixtures" / (name + ".csv")).read_bytes()
            for stage in ("draft", "final"):
                self.assertEqual((self.root / "out" / stage / "artifacts" / (name + ".csv")).read_bytes(), original)

    def test_all_local_links_open_and_every_artifact_is_indexed(self):
        self.build()
        for doc in (self.root / "out").rglob("README.md"):
            for link in re.findall(r"\]\(([^)]+)\)", doc.read_text()):
                if link.startswith("https://"):
                    continue
                self.assertGreater(len((doc.parent / link).read_bytes()), 0)
        for stage in p.MILESTONES:
            packet = p.load(self.root / "out" / stage / "packet.json")
            for item in packet["artifacts"]:
                data = (self.root / "out" / stage / item["packet_path"]).read_bytes()
                self.assertEqual(p.git_blob(data), item["git_blob"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])

    def test_twelve_unknown_cells_preserved(self):
        rows = list(csv.DictReader((self.root / "fixtures/scope.csv").read_text().splitlines()))
        self.assertEqual(len(rows), 12)
        self.assertEqual({(r["group"], r["dimension"]) for r in rows}, {(g, d) for g in ("ESS", "RIS", "IAM") for d in ("SD", "SEC", "DEP", "AI")})
        self.assertEqual({r["assessment_state"] for r in rows}, {"UNKNOWN"})

    def test_real_record_chain_ids_resolve_without_reinterpretation(self):
        evidence = list(csv.DictReader((self.root / "fixtures/evidence.csv").read_text().splitlines()))
        findings = list(csv.DictReader((self.root / "fixtures/findings.csv").read_text().splitlines()))
        recommendations = list(csv.DictReader((self.root / "fixtures/recommendations.csv").read_text().splitlines()))
        self.assertEqual((len(evidence), len(findings), len(recommendations)), (8, 3, 2))
        self.assertEqual(evidence[2]["source_type"], "acceptance_record")
        self.assertIn("enrollment", evidence[2]["observation"])
        for row in findings:
            self.assertLessEqual(set(row["evidence_ids"].split(";")), {e["evidence_id"] for e in evidence})
        for row in recommendations:
            self.assertIn(row["linked_findings"], {f["finding_id"] for f in findings})
        self.build()
        final = p.load(self.root / "out/final/packet.json")
        self.assertEqual(final["scenario_receipt"]["artifact_id"], "notes")
        self.assertIn("not subcontract acceptance", final["scenario_receipt"]["note"])
        self.assertEqual(final["real_commercial_event"], "NOT_ESTABLISHED")

    def test_byte_deterministic_replay(self):
        self.build()
        p.assemble(self.plan_path, self.root, self.root / "again")
        one = {f.relative_to(self.root / "out").as_posix(): f.read_bytes() for f in (self.root / "out").rglob("*") if f.is_file()}
        two = {f.relative_to(self.root / "again").as_posix(): f.read_bytes() for f in (self.root / "again").rglob("*") if f.is_file()}
        self.assertEqual(one, two)

    def test_reordered_milestones_keep_canonical_stage_order(self):
        original, _ = p.construct(self.plan, self.root)
        self.plan["milestones"].reverse()
        reordered, _ = p.construct(self.plan, self.root)
        for stage in p.MILESTONES:
            self.assertEqual(original[f"{stage}/packet.json"], reordered[f"{stage}/packet.json"])

    def test_missing_source_is_incomplete_not_omitted_or_zero(self):
        (self.root / "fixtures/findings.csv").unlink()
        report = self.build()
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["diagnostics"][0]["status"], "MISSING")
        self.assertEqual(report["packets"][0]["packaging_status"], "COMPLETE")
        self.assertEqual(report["packets"][1]["amount_cents"], 960000)
        self.assertEqual(report["packets"][1]["trigger"], "DRAFT_DELIVERY")
        packet = p.load(self.root / "out/draft/packet.json")
        self.assertIn("findings", [a["id"] for a in packet["artifacts"]])
        self.assertEqual(p.verify(self.root / "out")["status"], "PASS")

    def test_changed_source_not_copied_as_verified(self):
        with (self.root / "fixtures/evidence.csv").open("a") as handle:
            handle.write("changed\n")
        report = self.build()
        self.assertEqual(report["diagnostics"][0]["status"], "CHANGED")
        self.assertFalse((self.root / "out/draft/artifacts/evidence.csv").exists())

    def test_modified_bundle_detected(self):
        self.build()
        (self.root / "out/final/artifacts/evidence.csv").write_text("changed")
        result = p.verify(self.root / "out")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["errors"][0]["status"], "CHANGED")

    def test_missing_bundle_file_detected(self):
        self.build()
        (self.root / "out/final/README.md").unlink()
        self.assertEqual(p.verify(self.root / "out")["errors"][0]["status"], "MISSING")

    def test_unindexed_file_detected(self):
        self.build()
        (self.root / "out/unlisted.txt").write_text("unexpected")
        self.assertEqual(p.verify(self.root / "out")["errors"][0]["status"], "UNINDEXED")

    def test_existing_output_preserved(self):
        self.build()
        sentinel = self.root / "out/sentinel.txt"
        sentinel.write_text("retained")
        with self.assertRaises(p.PacketError):
            self.build()
        self.assertEqual(sentinel.read_text(), "retained")

    def test_single_packet_portable_without_source_checkout(self):
        self.build()
        target = self.root / "portable"
        shutil.copytree(self.root / "out/final", target)
        shutil.rmtree(self.root / "fixtures")
        packet = p.load(target / "packet.json")
        for item in packet["artifacts"]:
            self.assertEqual(p.git_blob((target / item["packet_path"]).read_bytes()), item["git_blob"])

    def test_unknown_data_is_not_condition_of_kickoff(self):
        self.plan["milestones"][0]["dependencies"].append({"owner_role": "UNIVERSITY", "input": "Still unknown", "effect": "Only dependent analysis is affected."})
        _, report = p.construct(self.plan, self.root)
        self.assertEqual(report["packets"][0]["trigger"], "WRITTEN_AUTHORIZATION")
        self.assertEqual(report["packets"][0]["amount_cents"], 960000)

    def test_draft_acceptance_trigger_rejected(self):
        self.plan["milestones"][1]["trigger"] = "FINAL_ACCEPTANCE"
        self.reject()

    def test_final_delivery_trigger_rejected(self):
        self.plan["milestones"][2]["trigger"] = "DRAFT_DELIVERY"
        self.reject()

    def test_receipt_kind_not_interchangeable(self):
        self.plan["milestones"][2]["scenario_receipt"]["kind"] = "DRAFT_DELIVERY"
        self.reject()

    def test_live_acceptance_state_rejected(self):
        self.plan["milestones"][2]["scenario_receipt"]["state"] = "ACCEPTED"
        self.reject()

    def test_missing_receipt_kept_missing(self):
        self.plan["milestones"][2]["scenario_receipt"].update(state="NOT_SUPPLIED", artifact_id=None)
        self.build()
        data = p.load(self.root / "out/final/packet.json")
        self.assertEqual(data["scenario_receipt"]["state"], "NOT_SUPPLIED")
        self.assertEqual(data["real_commercial_event"], "NOT_ESTABLISHED")

    def test_money_bool_and_mismatch_and_option_mixing_rejected(self):
        for key, bad in [("base_cents", True), ("base_cents", 2800000), ("option_cents", 0), ("currency", "EUR")]:
            with self.subTest(key=key, bad=bad):
                plan = copy.deepcopy(self.plan)
                plan[key] = bad
                with self.assertRaises(p.PacketError):
                    p.validate(plan)
        self.plan["milestones"][1]["amount_cents"] = 950000
        self.reject()

    def test_duplicate_artifact_and_milestone_rejected(self):
        self.plan["artifacts"].append(copy.deepcopy(self.plan["artifacts"][0]))
        self.reject()
        self.plan["artifacts"].pop()
        self.plan["milestones"][2] = copy.deepcopy(self.plan["milestones"][0])
        self.reject()

    def test_dangling_or_outside_packet_reference_rejected(self):
        self.plan["milestones"][0]["artifact_ids"].append("absent")
        self.reject()
        self.plan["milestones"][0]["artifact_ids"].pop()
        self.plan["milestones"][0]["criteria"][0]["artifact_ids"] = ["evidence"]
        self.reject()

    def test_missing_criterion_rejected(self):
        self.plan["milestones"][0]["criteria"].pop()
        self.reject()

    def test_empty_unresolved_not_assumed_pass(self):
        self.plan["milestones"][0]["criteria"][0]["unresolved"] = ""
        self.reject()

    def test_generation_mismatch_rejected(self):
        self.plan["artifacts"][0]["generation"] = "another-version"
        self.reject()

    def test_unpinned_upstream_rejected(self):
        self.plan["artifacts"][0]["origin"]["commit"] = "main"
        self.reject()

    def test_source_blob_disagreement_rejected(self):
        self.plan["artifacts"][0]["origin"]["git_blob"] = "0" * 40
        self.reject()

    def test_traversal_and_absolute_paths_rejected(self):
        for path in ("../private", "/absolute", "fixtures/../secret", "C:\\file", "fixtures//a", "./x"):
            with self.subTest(path=path):
                self.plan["artifacts"][0]["path"] = path
                self.reject()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_input_and_output_symlinks_rejected(self):
        file = self.root / "fixtures/COMMERCIAL.md"
        file.unlink()
        file.symlink_to(HERE / "fixtures/COMMERCIAL.md")
        with self.assertRaises(p.PacketError):
            p.construct(self.plan, self.root)
        file.unlink()
        shutil.copyfile(HERE / "fixtures/COMMERCIAL.md", file)
        self.build()
        (self.root / "out/link").symlink_to(self.root / "fixtures")
        with self.assertRaises(p.PacketError):
            p.verify(self.root / "out")

    def test_duplicate_json_and_nan_rejected(self):
        for value in ('{"a":1,"a":2}', '{"a":NaN}'):
            self.plan_path.write_text(value)
            with self.assertRaises(p.PacketError):
                p.load(self.plan_path)

    def test_live_or_unknown_top_level_claim_rejected(self):
        self.plan["invoice_issued"] = True
        self.reject()
        self.plan.pop("invoice_issued")
        self.plan["mode"] = "LIVE"
        self.reject()

    def test_markdown_user_text_cannot_create_extra_link(self):
        escaped = p.cell("[click](file:///private)|<script>\nline")
        self.assertNotIn("[click]", escaped)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("|", escaped)

    def test_cli_success_incomplete_and_preserve_exit_codes(self):
        command = [sys.executable, str(HERE / "packets.py"), "assemble", str(self.plan_path), "--root", str(self.root), "--output", str(self.root / "out")]
        first = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=15).returncode, 2)
        (self.root / "fixtures/evidence.csv").unlink()
        command[-1] = str(self.root / "incomplete")
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=15).returncode, 1)
        result = subprocess.run([sys.executable, str(HERE / "packets.py"), "verify", str(self.root / "out")], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["files_checked"], 23)


if __name__ == "__main__":
    unittest.main()
