#!/usr/bin/env python3
"""resources.html last-reviewed stamp + regenerate-or-alarm canaries."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "host"))

import resources_tab as tab  # noqa: E402


FIXED_SHA = "4168d76c4d12633fa2ac2e7b3946ec3ad60f77b9"
FIXED_TIME = "2026-08-31T00:00:00Z"
def _absent_constructions(blob: str) -> None:
    lowered = blob.lower()
    assert "must authenticate" not in lowered
    assert "seat is required" not in lowered
    assert "required reviewers" not in lowered
    assert ("protected" + "_files").lower() not in lowered
    assert ("allowed" + "_verbs").lower() not in lowered
    assert ("tos" + "_gate").lower() not in lowered


def copy_live_tree(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    rels = list(tab.FIXED_SOURCES) + [tab.DEFAULT_PAGE, "host/resources_tab.py"]
    for rel in rels:
        src = ROOT / rel
        if not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    records = ROOT / tab.INVENTORY_RECORDS
    if records.is_dir():
        target_records = dest / tab.INVENTORY_RECORDS
        target_records.mkdir(parents=True, exist_ok=True)
        for path in records.glob("*.json"):
            shutil.copy2(path, target_records / path.name)


class ResourcesTabTests(unittest.TestCase):
    def test_self_test(self) -> None:
        self.assertEqual(tab.self_test(), 0)

    def test_live_page_has_generated_stamp_after_regenerate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="resources-tab-live-") as tmp:
            root = Path(tmp)
            copy_live_tree(root)
            row = tab.regenerate(
                str(root),
                sha=FIXED_SHA,
                reviewed_at=FIXED_TIME,
            )
            page = (root / "resources.html").read_text(encoding="utf-8")
            self.assertEqual(row["state"], "FRESH")
            self.assertTrue(row["present"])
            self.assertIn('id="resources-last-reviewed"', page)
            self.assertIn("LAST REVIEWED 2026-08-31T00:00:00Z", page)
            self.assertIn(FIXED_SHA, page)
            self.assertIn('data-resources-freshness="FRESH"', page)
            self.assertIn("Action Pad", page)
            self.assertIn("does not move money", page)
            self.assertIn("measured host-zero operation was already achieved", page)
            self.assertIn('href="./ledger.html"', page)
            self.assertIn("Larger fixed engagements", page)

    def test_checked_in_resources_html_stamp_matches_current_inputs(self) -> None:
        row = tab.measure(str(ROOT))
        self.assertEqual(row["state"], "FRESH", row["reason"])
        self.assertEqual(row["digest"], row["page_digest"])
        page = (ROOT / "resources.html").read_text(encoding="utf-8")
        self.assertIn("Larger fixed engagements", page)
        self.assertIn('data-resources-freshness="FRESH"', page)
        self.assertNotIn("Do not treat this tab as current", page)

    def test_body_edit_without_regenerate_is_stale(self) -> None:
        with tempfile.TemporaryDirectory(prefix="resources-tab-body-") as tmp:
            root = Path(tmp)
            copy_live_tree(root)
            tab.regenerate(str(root), sha=FIXED_SHA, reviewed_at=FIXED_TIME)
            self.assertEqual(tab.measure(str(root))["state"], "FRESH")
            page = root / "resources.html"
            html = page.read_text(encoding="utf-8")
            page.write_text(
                html.replace(
                    "<h1>Common Resources</h1>",
                    "<h1>Common Resources</h1><p id=\"body-canary\">body drift</p>",
                    1,
                ),
                encoding="utf-8",
            )
            measured = tab.measure(str(root))
            self.assertEqual(measured["state"], "STALE")
            self.assertIn("source digest does not match current inputs", measured["reason"])
            check = subprocess.run(
                [sys.executable, str(ROOT / "host" / "resources_tab.py"), "--root", str(root), "--check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check.returncode, 0)
            self.assertIn("STALE", check.stdout)
            row = tab.regenerate_or_alarm(
                str(root),
                sha=FIXED_SHA,
                reviewed_at=FIXED_TIME,
            )
            restored = (root / "resources.html").read_text(encoding="utf-8")
            self.assertEqual(row["state"], "FRESH")
            self.assertIn("body drift", restored)
            self.assertIn("Larger fixed engagements", restored)

    def test_stale_sources_fail_and_alarm_writes_visible_mark(self) -> None:
        with tempfile.TemporaryDirectory(prefix="resources-tab-stale-") as tmp:
            root = Path(tmp)
            copy_live_tree(root)
            tab.regenerate(str(root), sha=FIXED_SHA, reviewed_at=FIXED_TIME)
            ledger = root / "ground" / "RESOURCE_LEDGER.json"
            data = json.loads(ledger.read_text(encoding="utf-8"))
            data["_freshness_canary"] = "drift"
            ledger.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            measured = tab.measure(str(root))
            self.assertEqual(measured["state"], "STALE")
            check = subprocess.run(
                [sys.executable, str(ROOT / "host" / "resources_tab.py"), "--root", str(root), "--check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check.returncode, 0)
            self.assertIn("STALE", check.stdout)
            alarmed = tab.alarm(str(root), sha=FIXED_SHA, reviewed_at=FIXED_TIME)
            page = (root / "resources.html").read_text(encoding="utf-8")
            self.assertEqual(alarmed["state"], "STALE")
            self.assertIn('data-resources-freshness="STALE"', page)
            self.assertIn("STALE", page)
            self.assertIn("Do not treat this tab as current", page)
            self.assertIn("Action Pad", page)

    def test_ledger_md_and_catalog_drift_fail_check(self) -> None:
        """RESOURCE_LEDGER.md / catalog.json drift must fail --check (PR 11280 class)."""
        with tempfile.TemporaryDirectory(prefix="resources-tab-md-") as tmp:
            root = Path(tmp)
            copy_live_tree(root)
            tab.regenerate(str(root), sha=FIXED_SHA, reviewed_at=FIXED_TIME)
            self.assertEqual(tab.measure(str(root))["state"], "FRESH")
            ledger_md = root / "ground" / "RESOURCE_LEDGER.md"
            ledger_md.write_text(
                ledger_md.read_text(encoding="utf-8") + "\n<!-- freshness-canary-md -->\n",
                encoding="utf-8",
            )
            measured = tab.measure(str(root))
            self.assertEqual(measured["state"], "STALE")
            self.assertIn("source digest does not match current inputs", measured["reason"])
            check = subprocess.run(
                [sys.executable, str(ROOT / "host" / "resources_tab.py"), "--root", str(root), "--check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check.returncode, 0)
            self.assertIn("STALE", check.stdout)
            restored = tab.regenerate_or_alarm(
                str(root),
                sha=FIXED_SHA,
                reviewed_at=FIXED_TIME,
            )
            self.assertEqual(restored["state"], "FRESH")
            catalog = root / "revenue" / "outcome_commerce" / "catalog.json"
            payload = json.loads(catalog.read_text(encoding="utf-8") or "{}")
            if not isinstance(payload, dict):
                payload = {}
            payload["_freshness_canary"] = "catalog-drift"
            catalog.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            catalog_stale = tab.measure(str(root))
            self.assertEqual(catalog_stale["state"], "STALE")
            check2 = subprocess.run(
                [sys.executable, str(ROOT / "host" / "resources_tab.py"), "--root", str(root), "--check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(check2.returncode, 0)
            self.assertIn("STALE", check2.stdout)

    def test_regenerate_or_alarm_produces_matching_page(self) -> None:
        with tempfile.TemporaryDirectory(prefix="resources-tab-regen-") as tmp:
            root = Path(tmp)
            copy_live_tree(root)
            tab.regenerate(str(root), sha=FIXED_SHA, reviewed_at=FIXED_TIME)
            record_dir = root / tab.INVENTORY_RECORDS
            record_dir.mkdir(parents=True, exist_ok=True)
            (record_dir / "canary-resources-tab-20260830-01.json").write_text(
                '{"event_type":"CANARY","id":"canary-resources-tab-20260830-01"}\n',
                encoding="utf-8",
            )
            self.assertEqual(tab.measure(str(root))["state"], "STALE")
            row = tab.regenerate_or_alarm(
                str(root),
                sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                reviewed_at="2026-08-31T00:05:00Z",
            )
            page = (root / "resources.html").read_text(encoding="utf-8")
            self.assertEqual(row["state"], "FRESH")
            self.assertEqual(row.get("action"), "REGENERATED")
            self.assertEqual(row["digest"], row["page_digest"])
            self.assertIn("LAST REVIEWED 2026-08-31T00:05:00Z", page)
            self.assertIn("aaaaaaaaaaaa", page)
            self.assertNotIn('data-resources-freshness="STALE"', page)
            self.assertEqual(tab.measure(str(root))["state"], "FRESH")

    def test_source_digest_is_portable_across_path_and_line_endings(self) -> None:
        self.assertEqual(
            tab.digest_relpath(r"inventory\resources\records\example.json"),
            "inventory/resources/records/example.json",
        )
        with tempfile.TemporaryDirectory(prefix="resources-tab-lf-") as lf_tmp, tempfile.TemporaryDirectory(
            prefix="resources-tab-crlf-"
        ) as crlf_tmp:
            lf_root = Path(lf_tmp)
            crlf_root = Path(crlf_tmp)
            copy_live_tree(lf_root)
            copy_live_tree(crlf_root)
            for rel in tab.source_relpaths(str(lf_root)) + [tab.DEFAULT_PAGE]:
                lf_path = lf_root / rel
                crlf_path = crlf_root / rel
                lf_bytes = lf_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                lf_path.write_bytes(lf_bytes)
                crlf_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
            lf_body = tab.read_text(str(lf_root), tab.DEFAULT_PAGE)
            crlf_body = tab.read_text(str(crlf_root), tab.DEFAULT_PAGE)
            self.assertEqual(
                tab.source_digest(str(lf_root), lf_body),
                tab.source_digest(str(crlf_root), crlf_body),
            )

    def test_helper_and_workflow_do_not_gate_posting(self) -> None:
        helper = (ROOT / "host" / "resources_tab.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "resources-tab-freshness.yml").read_text(
            encoding="utf-8"
        )
        page = (ROOT / "resources.html").read_text(encoding="utf-8")
        for blob in (helper, workflow):
            _absent_constructions(blob)
        self.assertIn("No gate", helper)
        self.assertIn("Does not block posting", helper)
        self.assertIn("zero-credential POST", page)
        self.assertIn("Do not add login, credentials, identity proof, trust or approval gates", page)
        self.assertIn("cron:", workflow)
        self.assertIn("regenerate-or-alarm", workflow)
        self.assertIn("test_resources_tab.py", workflow)

    def test_workflow_is_scheduled_and_path_scoped(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "resources-tab-freshness.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("schedule:", workflow)
        self.assertIn("resources.html", workflow)
        self.assertIn("ground/RESOURCE_LEDGER.json", workflow)
        self.assertIn("inventory/resources/**", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("branch-protection", workflow)

    def test_open_door_guard_accepts_this_diff_shape(self) -> None:
        helper = (ROOT / "host" / "resources_tab.py").read_text(encoding="utf-8")
        added = [line for line in helper.splitlines() if line.strip()][:8]
        diff = "\n".join(
            [
                "diff --git a/host/resources_tab.py b/host/resources_tab.py",
                "--- a/host/resources_tab.py",
                "+++ b/host/resources_tab.py",
                "@@ -0,0 +1,%s @@" % len(added),
                *("+" + line for line in added),
                "",
            ]
        )
        proc = subprocess.run(
            [sys.executable, str(ROOT / "open_door_guard.py"), "--diff-file", "-"],
            input=diff,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class ResourcesTabCheckoutShaTests(unittest.TestCase):
    """Use real repositories to model a checkout newer than its workflow event."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="resources-tab-git-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("commit", "--allow-empty", "-qm", "initial checkout")
        self.initial_sha = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            [
                "git", "-C", str(self.root),
                "-c", "user.name=Resources Tab Test",
                "-c", "user.email=resources-tab@example.invalid",
                "-c", "commit.gpgsign=false", *args,
            ],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()

    def test_checkout_head_precedes_trigger_sha(self) -> None:
        with patch.dict(os.environ, {"GITHUB_SHA": FIXED_SHA}):
            self.assertEqual(tab.git_sha(str(self.root)), self.initial_sha)

    def test_explicit_sha_still_overrides_checkout_and_environment(self) -> None:
        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}):
            self.assertEqual(tab.git_sha(str(self.root), FIXED_SHA), FIXED_SHA)

    def test_detached_head_precedes_trigger_sha(self) -> None:
        self.git("commit", "--allow-empty", "-qm", "advance checkout")
        event_sha = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.initial_sha)
        with patch.dict(os.environ, {"GITHUB_SHA": event_sha}):
            self.assertEqual(tab.git_sha(str(self.root)), self.initial_sha)

    def test_source_export_retains_environment_fallback(self) -> None:
        export = Path(self.tmp.name) / "export"
        export.mkdir()
        with patch.dict(os.environ, {"GITHUB_SHA": FIXED_SHA}):
            self.assertEqual(tab.git_sha(str(export)), FIXED_SHA)
        with patch.dict(os.environ, {"GITHUB_SHA": "invalid"}):
            self.assertEqual(tab.git_sha(str(export)), "")

    def test_cli_regeneration_binds_new_checkout_not_event(self) -> None:
        for rel in tab.FIXED_SOURCES:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n", encoding="utf-8")
        page = self.root / tab.DEFAULT_PAGE
        page.write_text("<h1>Common Resources</h1>fixture\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "resource inputs after triggering event")
        checkout_sha = self.git("rev-parse", "HEAD")
        env = dict(os.environ, GITHUB_SHA=self.initial_sha)
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "host" / "resources_tab.py"),
                "--root", str(self.root), "--regenerate-or-alarm",
                "--reviewed-at", FIXED_TIME,
            ],
            cwd=self.tmp.name, env=env, capture_output=True, text=True, check=True,
        )
        row = json.loads(result.stdout)
        self.assertEqual(row["state"], "FRESH")
        self.assertEqual(row["sha"], checkout_sha)
        self.assertEqual(row["checkout_sha"], checkout_sha)
        self.assertEqual(row["digest"], row["page_digest"])
        self.assertEqual(tab.parse_stamp(page.read_text())["sha"], checkout_sha)

    def test_matching_stamp_is_not_rewritten_for_unrelated_commit(self) -> None:
        page = self.root / tab.DEFAULT_PAGE
        page.write_text("<h1>Common Resources</h1>fixture\n", encoding="utf-8")
        tab.regenerate(str(self.root), reviewed_at=FIXED_TIME)
        before = page.read_bytes()
        self.git("commit", "--allow-empty", "-qm", "unrelated commit")
        with patch.dict(os.environ, {"GITHUB_SHA": FIXED_SHA}):
            row = tab.regenerate_or_alarm(str(self.root))
        self.assertEqual(row["state"], "FRESH")
        self.assertEqual(page.read_bytes(), before)

    def test_workflow_uses_checkout_default_on_initial_and_retry_paths(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "resources-tab-freshness.yml").read_text(
            encoding="utf-8"
        )
        commands = [line.strip() for line in workflow.splitlines()
                    if "python3 host/resources_tab.py --regenerate-or-alarm" in line]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all("--sha" not in command for command in commands), commands)


if __name__ == "__main__":
    unittest.main()
