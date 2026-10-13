"""Independent integration tests for portable Civic handoffs; synthetic records.

These check emitted artifacts against source bytes and the retained compiler.
They are not browser execution, accessibility certification, or a core re-audit.
"""
import base64
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from civic_ledger import core
from civic_ledger import handoff


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-01-04T12:00:00Z"
CANONICAL_FILES = ("ledger.json", "ledger.csv", "ledger.md", "manifest.json")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ReaderMarkup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def evidence_values(value):
    if isinstance(value, dict):
        if {"doc_id", "line", "line_sha256", "source_sha256"} <= set(value):
            yield value
        for child in value.values():
            yield from evidence_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_values(child)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="civic-handoff-review-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ledger = core.Ledger("fictional-access-meeting")
        self.source_inputs = [
            ("agenda", "agenda", "2026-01-01T12:00:00Z",
             "[ITEM U] Library — café <em>proposal</em>\r\nOwner: Team <research> & neighbors\r\n"
             "Action: Literal <script>source note</script>\r\n\r\n[ITEM C] Bus route\r\n"),
            ("minutes-one", "minutes", "2026-01-02T12:00:00Z",
             "[ITEM U] Library — café <em>proposal</em>\rAction: Discussed, no decision recorded.\r"
             "[ITEM C] Bus route\rDecision: APPROVED\rOwner: Mobility & access\r"),
            ("minutes-two", "minutes", "2026-01-03T12:00:00Z",
             "[ITEM C] Bus route\nDecision: DENIED\n[ITEM D] Ramp improvements\n"
             "Decision: APPROVED\nDeadline: 2026-02-01\n"),
        ]
        for doc_id, kind, observed, text in self.source_inputs:
            self.ledger.add(core.DocumentSnapshot.create(
                meeting_id=self.ledger.meeting_id, doc_id=doc_id, kind=kind,
                source_url=f"https://example.invalid/{doc_id}?source=declared&version=1",
                observed_at=observed, text=text))
        self.workspace = self.root / "original-workspace.json"
        # Non-canonical whitespace is intentional: retain these exact bytes.
        self.workspace_bytes = (json.dumps(self.ledger.to_dict(), ensure_ascii=False, indent=3) + "\n\n").encode()
        self.workspace.write_bytes(self.workspace_bytes)

    def export(self, name="handoff", **kwargs):
        folder = self.root / name
        handoff.export_handoff(self.workspace, folder, as_of=kwargs.pop("as_of", AS_OF), **kwargs)
        return folder

    def compiled(self, folder):
        return json.loads((folder / "ledger.json").read_bytes())

    def reseal_file_inventory(self, folder, name):
        path = folder / "handoff-manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["files"][name] = sha((folder / name).read_bytes())
        path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    def run_cli(self, *args, cwd=ROOT):
        env = dict(os.environ); env.pop("PYTHONPATH", None)
        flags = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
        return subprocess.run([sys.executable, "-B", *flags, "-m", "civic_ledger.handoff", *map(str, args)],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=20)

    def test_canonical_four_files_remain_byte_identical_to_retained_core(self):
        folder = self.export()
        expected = self.root / "core-output"
        core.write_bundle(core.compile_ledger(self.ledger, as_of=AS_OF), expected)
        for name in CANONICAL_FILES:
            self.assertEqual((folder / name).read_bytes(), (expected / name).read_bytes(), name)
        self.assertTrue(handoff.verify_handoff(folder)["ok"])

    def test_exact_workspace_bytes_and_all_payload_hashes_are_bound(self):
        folder = self.export(classification="synthetic")
        self.assertEqual((folder / "workspace.json").read_bytes(), self.workspace_bytes)
        self.assertEqual(self.workspace.read_bytes(), self.workspace_bytes)
        manifest = json.loads((folder / "handoff-manifest.json").read_bytes())
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
        self.assertEqual(set(manifest["files"]), actual - {"handoff-manifest.json"})
        for name, digest in manifest["files"].items():
            self.assertEqual(digest, sha((folder / name).read_bytes()), name)
        self.assertEqual(manifest["as_of"], AS_OF)
        self.assertEqual(manifest["max_source_age_days"], 90)
        self.assertEqual(manifest["classification"], "synthetic")
        self.assertEqual(manifest["compile_sha256"], self.compiled(folder)["compile_sha256"])

    def test_normalized_sources_downloads_and_line_hashes_agree(self):
        folder = self.export()
        reader = (folder / "reader.html").read_text(encoding="utf-8")
        markup = ReaderMarkup(reader)
        downloads = {attrs["download"]: attrs["href"] for tag, attrs in markup.tags
                     if tag == "a" and "download" in attrs}
        expected_downloads = set(CANONICAL_FILES) | {"workspace.json", "0001.txt", "0002.txt", "0003.txt"}
        self.assertEqual(set(downloads), expected_downloads)
        decoded = {}
        for name, href in downloads.items():
            prefix, encoded = href.split(",", 1)
            self.assertEqual(prefix, "data:application/octet-stream;base64")
            decoded[name] = base64.b64decode(encoded, validate=True)
        for name in (*CANONICAL_FILES, "workspace.json"):
            self.assertEqual(decoded[name], (folder / name).read_bytes(), name)
        ids = {attrs["id"] for _, attrs in markup.tags if "id" in attrs}
        by_id = {}
        for number, (doc_id, _, _, original) in enumerate(self.source_inputs, 1):
            expected = original.replace("\r\n", "\n").replace("\r", "\n").encode()
            relative = f"sources/{number:04d}.txt"
            self.assertEqual((folder / relative).read_bytes(), expected)
            self.assertEqual(decoded[Path(relative).name], expected)
            self.assertIn(f"source-{number:04d}", ids)
            by_id[doc_id] = (number, expected)
        for anchor in evidence_values(self.compiled(folder)):
            number, raw = by_id[anchor["doc_id"]]
            line = raw.decode().splitlines()[anchor["line"] - 1]
            self.assertEqual(anchor["source_sha256"], sha(raw))
            self.assertEqual(anchor["line_sha256"], sha(line.encode()))
            self.assertIn(f"source-{number:04d}-line-{anchor['line']}", ids)

    def test_conflict_unknown_and_decided_states_survive_handoff(self):
        folder = self.export(); compiled = self.compiled(folder)
        items = {row["item_id"]: row for row in compiled["items"]}
        self.assertEqual(items["C"]["state"], "HOLD_CONFLICT")
        self.assertIsNone(items["C"]["decision"])
        self.assertEqual(len(items["C"]["decision_evidence"]), 2)
        self.assertEqual(items["U"]["state"], "UNKNOWN_DECISION")
        self.assertIsNone(items["U"]["decision"])
        self.assertIsNone(items["U"]["deadline"])
        self.assertEqual(items["D"]["state"], "DECIDED_APPROVED")
        for key in ("external_actions_authorized", "legal_or_policy_judgment", "unsupported_inference_allowed"):
            self.assertIs(compiled["authority"][key], False)
        reader = (folder / "reader.html").read_text()
        for state in ("HOLD_CONFLICT", "UNKNOWN_DECISION", "DECIDED_APPROVED"):
            self.assertIn(state, reader)

    def test_stale_status_uses_explicit_as_of_and_threshold(self):
        folder = self.export(as_of="2026-05-04T12:00:00Z", max_source_age_days=30)
        compiled = self.compiled(folder)
        self.assertEqual(compiled["freshness"], "STALE_SOURCE")
        self.assertEqual(compiled["as_of"], "2026-05-04T12:00:00Z")
        self.assertEqual(compiled["max_source_age_days"], 30)
        self.assertIn("STALE_SOURCE", (folder / "reader.html").read_text())
        self.assertTrue(handoff.verify_handoff(folder)["ok"])

    def test_markup_is_displayed_as_text_and_unicode_is_retained(self):
        reader = (self.export() / "reader.html").read_text(encoding="utf-8")
        self.assertIn("café", reader)
        self.assertIn("&lt;em&gt;proposal&lt;/em&gt;", reader)
        self.assertIn("&lt;script&gt;source note&lt;/script&gt;", reader)
        self.assertNotIn("<em>proposal</em>", reader)
        self.assertNotIn("<script>source note</script>", reader)
        self.assertIn("&amp; neighbors", reader)

    def test_static_reader_contains_filter_controls_without_external_assets(self):
        reader = (self.export() / "reader.html").read_text()
        markup = ReaderMarkup(reader)
        by_id = {attrs["id"]: (tag, attrs) for tag, attrs in markup.tags if "id" in attrs}
        self.assertEqual(by_id["search-input"][0], "input")
        self.assertEqual(by_id["state-filter"][0], "select")
        self.assertIn("results-count", by_id)
        cards = [attrs for _, attrs in markup.tags if "item-card" in attrs.get("class", "").split()]
        self.assertEqual(len(cards), 3)
        for tag, attrs in markup.tags:
            if tag in ("script", "img", "iframe", "link"):
                self.assertFalse(attrs.get("src", "").startswith(("http:", "https:", "//")))
                self.assertFalse(attrs.get("href", "").startswith(("http:", "https:", "//")))
        # Markup checks establish controls/assets only, not browser interaction.

    def test_real_cli_exports_and_verifies_and_default_classification_is_unspecified(self):
        output = self.root / "cli"
        result = self.run_cli("export", "--workspace", self.workspace, "--output-dir", output, "--as-of", AS_OF)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_cli("verify", "--output-dir", output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(handoff.verify_handoff(output)["classification"], "unspecified")
        # The documented -B invocation must work with only the copied package.
        before = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        result = self.run_cli("verify", "--output-dir", ".", cwd=output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(before, {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()})

    def test_source_snapshot_tampering_is_rejected(self):
        folder = self.export()
        source = folder / "sources/0001.txt"
        source.write_bytes(source.read_bytes() + b"Altered supplied text\n")
        with self.assertRaises(core.ContractError):
            handoff.verify_handoff(folder)

    def test_resealed_reader_cannot_replace_recomputed_artifact(self):
        folder = self.export()
        reader = folder / "reader.html"; reader.write_bytes(reader.read_bytes() + b"\n<p>Changed reader</p>\n")
        self.reseal_file_inventory(folder, "reader.html")
        with self.assertRaises(core.ContractError):
            handoff.verify_handoff(folder)

    def test_source_package_tamper_rejected_even_with_updated_inventory(self):
        folder = self.export()
        source = folder / "civic_ledger/core.py"; source.write_bytes(source.read_bytes() + b"\n# changed packaged source\n")
        self.reseal_file_inventory(folder, "civic_ledger/core.py")
        with self.assertRaises(core.ContractError):
            handoff.verify_handoff(folder)

    def test_manifest_assessment_change_is_not_silently_adopted(self):
        folder = self.export()
        path = folder / "handoff-manifest.json"; manifest = json.loads(path.read_bytes())
        manifest["as_of"] = "2026-05-04T12:00:00Z"
        path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n")
        with self.assertRaises(core.ContractError):
            handoff.verify_handoff(folder)

    def test_existing_output_directory_or_file_is_preserved(self):
        folder = self.root / "existing"; folder.mkdir(); marker = folder / "owner.txt"; marker.write_bytes(b"retained")
        with self.assertRaises(core.ContractError):
            handoff.export_handoff(self.workspace, folder, as_of=AS_OF)
        self.assertEqual(list(folder.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b"retained")
        with self.assertRaises(core.ContractError):
            handoff.export_handoff(self.workspace, self.workspace, as_of=AS_OF)
        self.assertEqual(self.workspace.read_bytes(), self.workspace_bytes)

    def test_existing_directory_symlink_and_dangling_symlink_are_refused(self):
        owner = self.root / "owner"; owner.mkdir(); (owner / "keep.txt").write_text("retain")
        target = self.root / "alias"; target.symlink_to(owner, target_is_directory=True)
        with self.assertRaises(core.ContractError):
            handoff.export_handoff(self.workspace, target, as_of=AS_OF)
        self.assertEqual(list(owner.iterdir()), [owner / "keep.txt"])
        absent = self.root / "absent-target"; dangling = self.root / "dangling"; dangling.symlink_to(absent)
        with self.assertRaises(core.ContractError):
            handoff.export_handoff(self.workspace, dangling, as_of=AS_OF)
        self.assertFalse(absent.exists())

    def test_same_declared_inputs_produce_identical_payloads_without_mutation(self):
        first = self.export("one", classification="synthetic")
        second = self.export("two", classification="synthetic")
        snapshots = lambda folder: {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        self.assertEqual(snapshots(first), snapshots(second))
        self.assertEqual(self.workspace.read_bytes(), self.workspace_bytes)


if __name__ == "__main__":
    unittest.main()
