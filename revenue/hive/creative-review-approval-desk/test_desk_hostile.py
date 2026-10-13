#!/usr/bin/env python3
from __future__ import annotations

from _test_support import *  # noqa: F401,F403


class CreativeReviewDeskHostileTests(CreativeReviewDeskTestCase):
    def test_resolved_annotation_from_reassigned_reviewer_remains_history_not_blocker(self) -> None:
        self.create()
        self.submit_hero()
        self.assign_hero()
        self.desk.add_annotation(
            "old-ann",
            "old-ann",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            {"kind": "GLOBAL"},
            "OTHER",
            "old reviewer note",
        )
        self.desk.resolve_annotation("old-resolve", "fall-launch", "old-ann", "designer-a")
        self.desk.assign_reviewer("reassign", "fall-launch", "hero-image", "brand", "reviewer-brand-two")
        self.desk.decide(
            "new-approve",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand-two",
            "APPROVE",
            "new reviewer",
        )
        self.desk.decide(
            "legal-approve",
            "fall-launch",
            "hero-image",
            "legal",
            "reviewer-legal",
            "APPROVE",
            "",
        )
        hero = next(
            item
            for item in self.desk.status("fall-launch")["derived"]["assets"]
            if item["asset_id"] == "hero-image"
        )
        self.assertEqual(hero["state"], "READY_FOR_OWNER_HANDOFF")
        self.assertFalse(hero["holds"])

    def test_audit_hash_tamper_forces_hold(self) -> None:
        self.make_ready()
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE events SET event_hash=? WHERE ordinal=1", ("f" * 64,))
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "HOLD")
        self.assertIn("AUDIT_EVENT_HASH_MISMATCH", status["campaign_holds"])

    def test_state_tamper_without_matching_audit_event_forces_hold(self) -> None:
        self.make_ready()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE dispositions SET decision='CHANGES_REQUESTED' WHERE campaign_id='fall-launch' AND asset_id='hero-image' AND role='brand'"
            )
        status = self.desk.status("fall-launch")["derived"]
        hero = next(item for item in status["assets"] if item["asset_id"] == "hero-image")
        self.assertEqual(hero["state"], "HOLD")
        self.assertIn("DISPOSITION_NOT_AUDIT_BOUND:brand", hero["holds"])

    def test_historical_asset_version_cannot_be_resurrected(self) -> None:
        self.make_ready()
        successor = self.root / "hero-generation-2.bin"
        successor.write_bytes(b"synthetic hero generation 2")
        self.submit_hero("submit-hero-generation-2", successor)
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "DELETE FROM asset_versions WHERE campaign_id='fall-launch' AND asset_id='hero-image' AND version=2"
            )
        status = self.desk.status("fall-launch")["derived"]
        hero = next(item for item in status["assets"] if item["asset_id"] == "hero-image")
        self.assertEqual(hero["state"], "HOLD")
        self.assertIn("ASSET_STATE_NOT_LATEST_AUDIT", hero["holds"])

    def test_historical_campaign_revision_cannot_be_resurrected(self) -> None:
        self.make_ready()
        with sqlite3.connect(self.db) as connection:
            original = connection.execute(
                "SELECT name,spec_json,spec_sha256,revision,updated_at FROM campaigns WHERE campaign_id='fall-launch'"
            ).fetchone()
        revised = json.loads(json.dumps(self.spec))
        revised["name"] = "Synthetic Fall Launch Revised"
        self.desk.revise_campaign("revise-campaign", 1, revised)
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE campaigns SET name=?,spec_json=?,spec_sha256=?,revision=?,updated_at=? WHERE campaign_id='fall-launch'",
                original,
            )
        status = self.desk.status("fall-launch")["derived"]
        self.assertEqual(status["campaign_state"], "HOLD")
        self.assertIn("CAMPAIGN_STATE_NOT_LATEST_AUDIT", status["campaign_holds"])

    def test_historical_assignment_and_approval_cannot_be_resurrected(self) -> None:
        self.make_ready()
        with sqlite3.connect(self.db) as connection:
            assignment = connection.execute(
                "SELECT reviewer_id,assigned_at FROM assignments WHERE campaign_id='fall-launch' AND asset_id='hero-image' AND campaign_revision=1 AND asset_version=1 AND role='brand'"
            ).fetchone()
            disposition = connection.execute(
                "SELECT campaign_id,asset_id,campaign_revision,asset_version,role,reviewer_id,decision,note,event_ordinal,decided_at FROM dispositions WHERE campaign_id='fall-launch' AND asset_id='hero-image' AND campaign_revision=1 AND asset_version=1 AND role='brand'"
            ).fetchone()
        self.desk.assign_reviewer(
            "reassign-brand",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand-two",
        )
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE assignments SET reviewer_id=?,assigned_at=? WHERE campaign_id='fall-launch' AND asset_id='hero-image' AND campaign_revision=1 AND asset_version=1 AND role='brand'",
                assignment,
            )
            connection.execute(
                "INSERT INTO dispositions(campaign_id,asset_id,campaign_revision,asset_version,role,reviewer_id,decision,note,event_ordinal,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                disposition,
            )
        status = self.desk.status("fall-launch")["derived"]
        hero = next(item for item in status["assets"] if item["asset_id"] == "hero-image")
        self.assertEqual(hero["state"], "HOLD")
        self.assertIn("ASSIGNMENT_NOT_LATEST_AUDIT:brand", hero["holds"])
        self.assertIn("DISPOSITION_NOT_LATEST_AUDIT:brand", hero["holds"])

    def test_export_is_deterministic_and_semantically_verifiable(self) -> None:
        self.make_ready()
        out_a = self.root / "out-a"
        out_b = self.root / "out-b"
        out_a.mkdir()
        out_b.mkdir()
        self.desk.export("fall-launch", out_a)
        self.desk.export("fall-launch", out_b)
        self.assertEqual(
            {path.name: path.read_bytes() for path in out_a.iterdir()},
            {path.name: path.read_bytes() for path in out_b.iterdir()},
        )
        verified = verify_bundle(out_a)
        self.assertTrue(verified["integrity_checked"])
        self.assertNotIn("valid", verified)
        self.assertEqual(verified["campaign_state"], "READY_FOR_OWNER_HANDOFF")

    def test_manifest_derived_tamper_is_rejected(self) -> None:
        self.make_ready()
        out = self.root / "out"
        out.mkdir()
        self.desk.export("fall-launch", out)
        manifest = json.loads((out / "manifest.json").read_text())
        manifest["derived"]["campaign_state"] = "HOLD"
        (out / "manifest.json").write_bytes(canonical_bytes(manifest))
        with self.assertRaises(InvalidState):
            verify_bundle(out)

    def test_receipt_or_member_tamper_is_rejected(self) -> None:
        self.make_ready()
        out = self.root / "out"
        out.mkdir()
        self.desk.export("fall-launch", out)
        (out / "review.md").write_text((out / "review.md").read_text() + "tamper\n")
        with self.assertRaises(InvalidState):
            verify_bundle(out)

    def test_csv_formula_prefix_is_neutralized(self) -> None:
        self.create()
        self.submit_hero()
        self.assign_hero()
        self.desk.add_annotation(
            "formula-note",
            "formula-note",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            {"kind": "GLOBAL"},
            "OTHER",
            "=HYPERLINK(example)",
        )
        out = self.root / "out"
        out.mkdir()
        self.desk.export("fall-launch", out)
        self.assertIn("'=HYPERLINK(example)", (out / "annotations.csv").read_text())

    @unittest.skipUnless(os.name == "posix", "descriptor-relative path checks require POSIX")
    def test_symlink_output_and_nonempty_output_fail_closed(self) -> None:
        self.make_ready()
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises((InvalidState, OSError)):
            self.desk.export("fall-launch", link)
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "sentinel").write_text("preserve")
        with self.assertRaises(InvalidState):
            self.desk.export("fall-launch", occupied)
        self.assertEqual((occupied / "sentinel").read_text(), "preserve")

    def test_extra_bundle_member_is_rejected(self) -> None:
        self.make_ready()
        out = self.root / "out"
        out.mkdir()
        self.desk.export("fall-launch", out)
        (out / "extra.txt").write_text("not admitted")
        with self.assertRaises(InvalidState):
            verify_bundle(out)

    def test_cli_create_status_export_verify_round_trip(self) -> None:
        spec_file = self.root / "spec.json"
        meta_file = self.root / "meta.json"
        spec_file.write_text(json.dumps(self.spec))
        meta_file.write_text(json.dumps(self.image_metadata()))
        cli_db = self.root / "cli.db"

        def run(*args: str) -> dict:
            process = subprocess.run(
                [sys.executable, str(HERE / "desk.py"), *args],
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(process.stdout)

        created = run("create", "--db", str(cli_db), "--spec", str(spec_file), "--request-id", "cli-create")
        self.assertEqual(created["revision"], 1)
        submitted = run(
            "submit",
            "--db",
            str(cli_db),
            "--campaign",
            "fall-launch",
            "--asset",
            "hero-image",
            "--author",
            "designer-a",
            "--file",
            str(self.hero),
            "--media-type",
            "image",
            "--metadata",
            str(meta_file),
            "--provenance-ref",
            "self-authored:cli-fixture",
            "--request-id",
            "cli-submit",
        )
        self.assertEqual(submitted["version"], 1)
        status = run("status", "--db", str(cli_db), "--campaign", "fall-launch")
        self.assertEqual(status["derived"]["campaign_state"], "HOLD")
        out = self.root / "cli-out"
        out.mkdir()
        run("export", "--db", str(cli_db), "--campaign", "fall-launch", "--output-dir", str(out))
        verified = run("verify", "--output-dir", str(out))
        self.assertTrue(verified["integrity_checked"])
        self.assertNotIn("valid", verified)

    def test_event_chain_ordinals_are_contiguous_and_bound(self) -> None:
        self.make_ready()
        manifest = self.desk.manifest("fall-launch")
        self.assertEqual([event["ordinal"] for event in manifest["events"]], list(range(1, len(manifest["events"]) + 1)))
        self.assertEqual(manifest["events"][0]["previous_hash"], "0" * 64)
        self.assertEqual(manifest["derived"]["campaign_holds"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
