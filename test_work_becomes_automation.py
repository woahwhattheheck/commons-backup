#!/usr/bin/env python3
"""Canary: leftover-id-on-main 404/blob census. Missing is not a gate."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "host"))

import leftover_id_census as census  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "commons_union_git_ntfy",
    str(ROOT / "ping" / "union_git_ntfy.py"),
)
U = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(U)

FIXED_SHA = "3530dc16d7916c861b0127efd1264ed9d41d5023"
FIXED_TIME = "2026-08-31T02:20:00Z"
CALIBRATE = "change-rate-single-read-digest-20260830-01"
LEFTOVER = "work-becomes-automation-20260830-01"
BANNED_PHONE = "".join(["680", "328", "3352"])


def _absent_constructions(blob: str) -> None:
    lowered = blob.lower()
    assert "must authenticate" not in lowered
    assert "seat is required" not in lowered
    assert "required reviewers" not in lowered
    assert ("allowed" + "_verbs") not in lowered
    assert ("tos" + "_gate") not in lowered
    assert BANNED_PHONE not in blob


def pin_payload(ids=None, calibrate=CALIBRATE):
    return {
        "id": LEFTOVER,
        "check": "leftover_id_on_main_census",
        "note": "Report only. MISSING is not a gate. Posting stays ungated. Memory records are never a posting gate.",
        "calibrate_present": calibrate,
        "leftover_ids": ids or [LEFTOVER, CALIBRATE],
        "cite": ["ping/union_git_ntfy.py", "repo_pulse.py"],
        "do_not_remint": ["repo-pulse", "kimi-automations-eventdriven-20260829-01"],
    }


def write_pin(root: Path, payload=None) -> None:
    ground = root / "ground"
    ground.mkdir(parents=True, exist_ok=True)
    (ground / "WORK_AUTOMATION.json").write_text(
        json.dumps(payload or pin_payload(), indent=2) + "\n",
        encoding="utf-8",
    )
    union_src = ROOT / "ping" / "union_git_ntfy.py"
    dest = root / "ping"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(union_src, dest / "union_git_ntfy.py")


def fake_probe(present, missing=(), unverified=()):
    present = set(present)
    missing = set(missing)
    unverified = set(unverified)

    def _probe(sha, ident):
        if ident in present:
            return {
                "id": ident,
                "status": census.PRESENT,
                "blob": "b" * 40,
                "evidence": "git-blob",
                "http": None,
                "note": "present",
            }
        if ident in missing:
            return {
                "id": ident,
                "status": census.MISSING,
                "blob": "",
                "evidence": "git-blob",
                "http": 404,
                "note": "sha-pinned raw 404",
            }
        return {
            "id": ident,
            "status": census.FINDER_UNVERIFIED,
            "blob": "",
            "evidence": "git",
            "http": 0,
            "note": "FINDER UNVERIFIED — injected",
        }

    return _probe


class WorkBecomesAutomationTests(unittest.TestCase):
    def test_union_helper_is_cited_not_cloned(self) -> None:
        argv = U.ls_remote_argv()
        self.assertEqual(argv, ["git", "ls-remote", U.REPO_GIT, "HEAD"])
        self.assertNotIn("clone", argv)
        url = U.raw_post_url(FIXED_SHA, LEFTOVER)
        self.assertTrue(url.endswith("/p/%s.md" % LEFTOVER))
        self.assertIn(FIXED_SHA, url)
        self.assertNotIn("/main/", url)

    def test_missing_leftover_is_data_not_a_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leftover-census-") as tmp:
            root = Path(tmp)
            write_pin(root)
            payload = census.regenerate(
                str(root),
                sha=FIXED_SHA,
                now=FIXED_TIME,
                probe=fake_probe({CALIBRATE}, missing={LEFTOVER}),
            )
            self.assertEqual(payload["state"], census.FRESH)
            ids = {row["id"]: row["status"] for row in payload["rows"]}
            self.assertEqual(ids[LEFTOVER], census.MISSING)
            self.assertEqual(ids[CALIBRATE], census.PRESENT)
            self.assertEqual(payload["counts"]["missing"], 1)
            checked = census.check(
                str(root),
                sha=FIXED_SHA,
                now=FIXED_TIME,
                probe=fake_probe({CALIBRATE}, missing={LEFTOVER}),
            )
            self.assertEqual(checked["state"], census.FRESH)
            self.assertEqual(checked["calibrate_status"], census.PRESENT)

    def test_stale_stamp_fails_check(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leftover-census-stale-") as tmp:
            root = Path(tmp)
            write_pin(root)
            census.regenerate(
                str(root),
                sha=FIXED_SHA,
                now=FIXED_TIME,
                probe=fake_probe({CALIBRATE}, missing={LEFTOVER}),
            )
            write_pin(root, pin_payload(ids=[LEFTOVER, CALIBRATE, "named-leftover-still-open-20260830-01"]))
            checked = census.check(
                str(root),
                sha=FIXED_SHA,
                now=FIXED_TIME,
                probe=fake_probe(
                    {CALIBRATE},
                    missing={LEFTOVER, "named-leftover-still-open-20260830-01"},
                ),
            )
            self.assertEqual(checked["state"], census.STALE)

    def test_unresolved_head_is_unverified_not_zero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leftover-census-head-") as tmp:
            root = Path(tmp)
            write_pin(root)
            env_sha = os.environ.pop("GITHUB_SHA", None)
            try:
                payload = census.measure(
                    str(root),
                    sha="",
                    now=FIXED_TIME,
                    probe=fake_probe({CALIBRATE}, missing={LEFTOVER}),
                    runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="no"),
                )
            finally:
                if env_sha is not None:
                    os.environ["GITHUB_SHA"] = env_sha
            self.assertEqual(payload["state"], census.FINDER_UNVERIFIED)
            self.assertEqual(payload["head_sha"], "")
            self.assertIn("search_space", payload)
            self.assertNotEqual(payload["counts"]["pinned"], 0)

    def test_calibration_miss_voids_the_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="leftover-census-cal-") as tmp:
            root = Path(tmp)
            write_pin(root)
            payload = census.regenerate_or_alarm(
                str(root),
                sha=FIXED_SHA,
                now=FIXED_TIME,
                probe=fake_probe(set(), unverified={CALIBRATE}, missing={LEFTOVER}),
            )
            self.assertEqual(payload["state"], census.FINDER_UNVERIFIED)
            self.assertEqual(payload["calibrate_status"], census.FINDER_UNVERIFIED)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "host" / "leftover_id_census.py"),
                    "--root",
                    str(root),
                    "--sha",
                    FIXED_SHA,
                    "--now",
                    FIXED_TIME,
                    "--check",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)

    def test_http_probe_distinguishes_404_from_unverified(self) -> None:
        import email.message
        import io
        import urllib.error

        headers = email.message.Message()

        class Fake404:
            def __enter__(self):
                raise urllib.error.HTTPError(
                    "https://example.invalid/x", 404, "no", headers, io.BytesIO()
                )

            def __exit__(self, *args):
                return False

        class Fake500:
            def __enter__(self):
                raise urllib.error.HTTPError(
                    "https://example.invalid/x", 500, "no", headers, io.BytesIO()
                )

            def __exit__(self, *args):
                return False

        url = U.raw_post_url(FIXED_SHA, LEFTOVER)
        self.assertEqual(census.http_probe(url, opener=lambda *a, **k: Fake404())["status"], census.MISSING)
        self.assertEqual(census.http_probe(url, opener=lambda *a, **k: Fake500())["status"], census.FINDER_UNVERIFIED)
        refused = census.http_probe(
            "https://raw.githubusercontent.com/woahwhattheheck/commons/main/p/%s.md" % LEFTOVER
        )
        self.assertEqual(refused["status"], census.FINDER_UNVERIFIED)
        self.assertIn("raw/main", refused["note"])

    def test_git_probe_present_and_missing(self) -> None:
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            spec = argv[-1]
            if argv[-2] == "-e" and spec.endswith("p/%s.md" % CALIBRATE):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if argv[-2] == "rev-parse" and spec.endswith("p/%s.md" % CALIBRATE):
                return SimpleNamespace(returncode=0, stdout="c" * 40 + "\n", stderr="")
            return SimpleNamespace(
                returncode=128,
                stdout="",
                stderr="fatal: path 'p/%s.md' does not exist in '%s'\n" % (LEFTOVER, FIXED_SHA),
            )

        present = census.git_probe(".", FIXED_SHA, CALIBRATE, runner=runner)
        missing = census.git_probe(".", FIXED_SHA, LEFTOVER, runner=runner)
        self.assertEqual(present["status"], census.PRESENT)
        self.assertEqual(present["blob"], "c" * 40)
        self.assertEqual(missing["status"], census.MISSING)

    def test_workflow_is_scheduled_regenerate_or_alarm(self) -> None:
        yml = (ROOT / ".github" / "workflows" / "leftover-id-census.yml").read_text(encoding="utf-8")
        self.assertIn("leftover-id-census", yml)
        self.assertIn("schedule:", yml)
        self.assertIn("regenerate-or-alarm", yml)
        self.assertIn("cron:", yml)
        self.assertNotIn("fire_action", yml)
        _absent_constructions(yml)
        for name in (
            "repo-pulse.yml",
            "llms-txt.yml",
            "job-watchdog.yml",
            "resources-tab-freshness.yml",
        ):
            self.assertTrue((ROOT / ".github" / "workflows" / name).is_file())
        self.assertTrue((ROOT / "host" / "finder_zero.py").is_file())
        self.assertTrue((ROOT / "ping" / "union_git_ntfy.py").is_file())

    def test_new_files_have_no_gates_or_owner_phone(self) -> None:
        rels = [
            "host/leftover_id_census.py",
            "ground/WORK_AUTOMATION.md",
            "ground/WORK_AUTOMATION.json",
            ".github/workflows/leftover-id-census.yml",
            "p/work-becomes-automation-20260830-01.md",
        ]
        for rel in rels:
            blob = (ROOT / rel).read_text(encoding="utf-8")
            _absent_constructions(blob)
            self.assertNotIn(BANNED_PHONE, blob)

    def test_live_pin_is_small_and_cites_not_remints(self) -> None:
        pin = json.loads((ROOT / "ground" / "WORK_AUTOMATION.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["id"], LEFTOVER)
        self.assertEqual(pin["check"], "leftover_id_on_main_census")
        self.assertLessEqual(len(pin["leftover_ids"]), 8)
        self.assertIn(LEFTOVER, pin["leftover_ids"])
        self.assertIn(CALIBRATE, pin["leftover_ids"])
        self.assertIn(CALIBRATE, pin["calibrate_present"])
        self.assertIn("kimi-automations-eventdriven-20260829-01", pin["do_not_remint"])
        self.assertTrue((ROOT / "p" / (CALIBRATE + ".md")).is_file())

    def test_receipt_id_is_exact(self) -> None:
        path = ROOT / "p" / (LEFTOVER + ".md")
        self.assertTrue(path.is_file(), "receipt must exist for this leftover")
        text = path.read_text(encoding="utf-8")
        self.assertIn("id: %s" % LEFTOVER, text)
        self.assertIn("from: SETH", text)
        self.assertIn("state: DURABLE_PAGE", text)
        self.assertIn("leftover-id-on-main", text)
        _absent_constructions(text)


if __name__ == "__main__":
    unittest.main()
