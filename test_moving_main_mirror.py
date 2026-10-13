#!/usr/bin/env python3
"""Moving-main mirror adapter: cursor, overlap, receipts, restore drill, no secrets."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import open_door_guard as guard
from host import moving_main_mirror as mmm
from host import repo_backup

ROOT = Path(__file__).resolve().parent


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def init_repo(path: Path, text: str = "open door\n") -> str:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "mirror-test@example.invalid")
    git(path, "config", "user.name", "mirror-test")
    (path / "fresh.md").write_text(text, encoding="utf-8")
    (path / "mirrors.json").write_text('{"law":"git HEAD is canonical"}\n', encoding="utf-8")
    (path / "START.md").write_text("# start\n", encoding="utf-8")
    git(path, "add", "fresh.md", "mirrors.json", "START.md")
    git(path, "commit", "-m", "proof")
    return git(path, "rev-parse", "HEAD")


class MovingMainMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.head = init_repo(self.source)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_snapshot_has_manifest_hash_and_head(self) -> None:
        snap = mmm.build_snapshot(self.source, paths=("fresh.md", "mirrors.json", "START.md"))
        self.assertEqual(snap["schema_version"], mmm.SCHEMA_VERSION)
        self.assertEqual(snap["head_sha"], self.head)
        self.assertRegex(snap["digest"], r"^[0-9a-f]{64}$")
        paths = {row["path"] for row in snap["entries"]}
        self.assertEqual(paths, {"fresh.md", "mirrors.json", "START.md"})
        self.assertTrue(all(mmm.SHA256_RE.fullmatch(row["sha256"]) for row in snap["entries"]))

    def test_cursor_is_monotonic_and_idempotent(self) -> None:
        snap = mmm.build_snapshot(self.source, paths=("fresh.md",))
        first = mmm.advance_cursor(None, snap, "ancestor")
        self.assertEqual(first["state"], "ADVANCE")
        self.assertEqual(first["seq"], 1)
        again = mmm.advance_cursor(first, snap, "equal")
        self.assertEqual(again["state"], "IDEMPOTENT")
        self.assertEqual(again["seq"], 1)
        older = dict(snap)
        older["head_sha"] = "0" * 40
        older["digest"] = "1" * 64
        stale = mmm.advance_cursor(first, older, "descendant")
        self.assertEqual(stale["state"], "STALE")

    def test_overlap_merges_disjoint_dedupes_identical_conflicts_on_disagreement(self) -> None:
        left = {
            "head_sha": "a" * 40,
            "entries": [
                {"path": "fresh.md", "bytes": 4, "sha256": "1" * 64},
                {"path": "START.md", "bytes": 2, "sha256": "2" * 64},
            ],
        }
        right = {
            "head_sha": "b" * 40,
            "entries": [
                {"path": "fresh.md", "bytes": 4, "sha256": "1" * 64},
                {"path": "ENTRY.md", "bytes": 3, "sha256": "3" * 64},
            ],
        }
        merged = mmm.merge_manifests(left, right)
        self.assertEqual(merged["state"], "MERGED")
        self.assertEqual(merged["identical"], 1)
        self.assertEqual(merged["disjoint"], 2)
        self.assertEqual(merged["conflicts"], [])
        disagree = {
            "head_sha": "c" * 40,
            "entries": [{"path": "fresh.md", "bytes": 9, "sha256": "9" * 64}],
        }
        conflict = mmm.merge_manifests(left, disagree)
        self.assertEqual(conflict["state"], "CONFLICT")
        self.assertEqual(conflict["conflicts"][0]["path"], "fresh.md")
        overlap = mmm.advance_cursor(
            {"seq": 4, "head_sha": "a" * 40, "digest": "d" * 64, "entries": left["entries"]},
            {
                "head_sha": "b" * 40,
                "digest": "e" * 64,
                "entries": right["entries"],
                "created_at": "2026-08-28T00:00:00Z",
            },
            "diverged",
        )
        self.assertEqual(overlap["state"], "OVERLAP_MERGED")
        self.assertEqual(overlap["seq"], 5)

    def test_corrupt_and_stale_detection(self) -> None:
        snap = mmm.build_snapshot(self.source, paths=("fresh.md",))
        blobs = {"fresh.md": b"tamper"}
        self.assertEqual(mmm.detect_corrupt(snap, blobs), ["fresh.md"])
        good = {row["path"]: (self.source / row["path"]).read_bytes() for row in snap["entries"]}
        self.assertEqual(mmm.detect_corrupt(snap, good), [])
        same_sha = dict(snap)
        same_sha["digest"] = "f" * 64
        prev = {"seq": 2, "head_sha": snap["head_sha"], "digest": snap["digest"]}
        corrupt = mmm.advance_cursor(prev, same_sha, "equal")
        self.assertEqual(corrupt["state"], "CORRUPT")

    def test_compact_cursor_stays_under_cap_and_refuses_other_topics(self) -> None:
        snap = mmm.build_snapshot(self.source, paths=("fresh.md", "mirrors.json", "START.md"))
        cursor = mmm.advance_cursor(None, snap, "ancestor")
        raw = mmm.compact_cursor(snap, cursor)
        self.assertLessEqual(len(raw), mmm.MAX_BYTES)
        msg = json.loads(raw.decode("utf-8"))
        self.assertEqual(msg["kind"], mmm.CURSOR_KIND)
        self.assertEqual(msg["head"], self.head)
        self.assertNotIn("token", json.dumps(msg))
        self.assertTrue(mmm.refuse_write_topic("https://ntfy.sh/" + mmm.WRITE_TOPIC))
        self.assertTrue(mmm.refuse_fresh_topic("https://ntfy.sh/" + mmm.FRESH_TOPIC))
        self.assertFalse(mmm.refuse_write_topic("https://ntfy.sh/" + mmm.CURSOR_TOPIC))

    def test_ntfy_publish_skips_write_and_fresh_topics(self) -> None:
        seen = []

        def post(url: str, body: bytes) -> int:
            seen.append(url)
            self.assertFalse(mmm.refuse_write_topic(url))
            self.assertFalse(mmm.refuse_fresh_topic(url))
            self.assertIn(mmm.CURSOR_TOPIC, url)
            self.assertLessEqual(len(body), mmm.MAX_BYTES)
            return 200

        snap = mmm.build_snapshot(self.source, paths=("fresh.md",))
        cursor = mmm.advance_cursor(None, snap, "ancestor")
        out = mmm.publish_ntfy_cursor(mmm.compact_cursor(snap, cursor), post=post)
        self.assertEqual(out["state"], "PUBLISHED")
        self.assertTrue(out["verified"])
        self.assertTrue(seen)
        self.assertTrue(all(mmm.WRITE_TOPIC not in u and mmm.FRESH_TOPIC not in u for u in seen))

    def test_prefer_multiple_independently_verified_receipts(self) -> None:
        a = {"id": "ntfy-cursor", "verified": True, "independent_origin": True, "digest": "a" * 64}
        b = {"id": "software-heritage", "verified": True, "independent_origin": True, "digest": "a" * 64}
        c = {"id": "jsdelivr-main", "verified": True, "independent_origin": False, "digest": "a" * 64}
        preferred = mmm.prefer_receipts([c, b, a])
        self.assertEqual(preferred["state"], "PREFERRED")
        self.assertTrue(preferred["receipt"]["independent_origin"])
        self.assertEqual(preferred["agreeing"], 2)
        self.assertEqual(preferred["independent"], 2)
        clash = mmm.prefer_receipts(
            [
                {**a, "digest": "a" * 64},
                {**b, "digest": "b" * 64},
            ]
        )
        self.assertEqual(clash["state"], "CONFLICT")

    def test_bounded_writeback_idempotent_and_conflict(self) -> None:
        mailed = []

        def post(url: str, body: bytes) -> int:
            mailed.append((url, body))
            self.assertIn(mmm.WRITE_TOPIC, url)
            self.assertNotIn(mmm.CURSOR_TOPIC, url)
            return 200

        env = {"id": "grok-dir9-moving-main-mirror-20260828-01", "from": "GROK", "to": "TABLE", "body": "PLAIN: hi"}
        first = mmm.bounded_writeback(env, post=post)
        self.assertEqual(first["state"], "MAILED")
        restored = {
            "same-id-20260828-aaaaaaaa": {"sha256": "1" * 64, "body": "one", "from": "GROK"},
            "only-restore-20260828-bbbbbbbb": {"sha256": "2" * 64, "body": "two", "from": "GROK"},
        }
        live = {
            "same-id-20260828-aaaaaaaa": {"sha256": "1" * 64, "body": "one"},
            "conflict-20260828-cccccccc": {"sha256": "9" * 64, "body": "other"},
        }
        restored["conflict-20260828-cccccccc"] = {"sha256": "8" * 64, "body": "nope", "from": "GROK"}
        result = mmm.writeback_from_restore(restored, live, post=post)
        self.assertEqual(result["state"], "CONFLICT")
        self.assertEqual(result["conflicts"], ["conflict-20260828-cccccccc"])
        self.assertIn("same-id-20260828-aaaaaaaa", result["skipped_identical"])
        self.assertIn("only-restore-20260828-bbbbbbbb", result["mailed"])
        huge = mmm.bounded_writeback(
            {"id": "oversize-20260828-dddddddd", "body": "x" * 5000},
            post=post,
        )
        self.assertEqual(huge["state"], "OVERSIZE")

    def test_restore_drill_composes_open_repo_backup(self) -> None:
        workdir = self.root / "drill"
        receipt = mmm.restore_drill(self.source, workdir)
        self.assertEqual(receipt["state"], "RESTORED")
        self.assertEqual(receipt["head_sha"], self.head)
        self.assertEqual(receipt["preferred"]["state"], "PREFERRED")
        restored = workdir / "restored"
        self.assertEqual((restored / "fresh.md").read_text(encoding="utf-8"), "open door\n")
        self.assertTrue((workdir / "backup").exists())
        manifests = list((workdir / "backup").glob("*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        verified = repo_backup.verify(manifests[0])
        self.assertEqual(verified["head_sha"], self.head)

    def test_external_provider_action_is_exact_and_not_ready(self) -> None:
        catalog = mmm.adapters_catalog()
        by_id = {row["id"]: row for row in catalog["adapters"]}
        for key in ("gitlab-pull-mirror", "codeberg-pull-mirror", "object-store-bundle"):
            row = by_id[key]
            self.assertEqual(row["credentials"], "EXTERNAL_PROVIDER_ACTION")
            self.assertFalse(row["operational"])
            action = row["external_provider_action"]
            self.assertIn("Do not put", action)
            self.assertIn("this repository", action)
            self.assertIsNone(row["href"])
        self.assertTrue(by_id["ntfy-cursor"]["operational"])
        self.assertTrue(by_id["ntfy-cursor"]["independent_origin"])
        self.assertTrue(by_id["software-heritage"]["operational"])
        self.assertFalse(by_id["jsdelivr-main"]["independent_origin"])
        self.assertTrue(by_id["internet-archive"]["operational"])
        self.assertIn("200", by_id["internet-archive"]["notes"])
        self.assertIn("523", by_id["internet-archive"]["notes"])

    def test_no_secret_logs_and_open_door(self) -> None:
        self.assertIn("<redacted>", mmm.redact("Authorization: Bearer supersecret-token-value"))
        self.assertNotIn("supersecret-token-value", mmm.redact("token=supersecret-token-value"))
        paths = (
            ROOT / "host" / "moving_main_mirror.py",
            ROOT / "test_moving_main_mirror.py",
            ROOT / "ground" / "MOVING_MAIN_MIRROR.md",
            ROOT / "mirrors.json",
            ROOT / "mirrors.html",
            ROOT / ".github" / "workflows" / "moving-main-mirror.yml",
        )
        present = [path for path in paths if path.is_file()]
        lines = [
            guard.AddedLine(path.as_posix(), line_number, text)
            for path in present
            for line_number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        ]
        self.assertEqual(guard.scan_added(lines), [])

    def test_catalog_files_match_adapter_contract(self) -> None:
        catalog = mmm.adapters_catalog()
        on_disk = json.loads((ROOT / "ci" / "moving_main" / "adapters.json").read_text(encoding="utf-8"))
        self.assertEqual([row["id"] for row in on_disk["adapters"]], [row["id"] for row in catalog["adapters"]])
        mirrors = json.loads((ROOT / "mirrors.json").read_text(encoding="utf-8"))
        self.assertIn("EXTERNAL_PROVIDER_ACTION", mirrors["still_open"])
        html = (ROOT / "mirrors.html").read_text(encoding="utf-8")
        self.assertIn("Exact adapter status", html)
        self.assertIn("EXTERNAL_PROVIDER_ACTION", html)
        self.assertIn("ci/moving_main/adapters.json", html)

        tool = ROOT / "host" / "moving_main_mirror.py"
        snap = subprocess.run(
            [sys.executable, str(tool), "snapshot", "--source", str(self.source)],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(snap.stdout)
        self.assertEqual(payload["head_sha"], self.head)
        status = subprocess.run(
            [sys.executable, str(tool), "status"],
            check=True,
            text=True,
            capture_output=True,
        )
        catalog = json.loads(status.stdout)
        self.assertTrue(any(row["id"] == "ntfy-cursor" for row in catalog["adapters"]))
        outdir = self.root / "out"
        sync = subprocess.run(
            [
                sys.executable,
                str(tool),
                "sync",
                "--source",
                str(self.source),
                "--output",
                str(outdir),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        summary = json.loads(sync.stdout)
        self.assertEqual(summary["head_sha"], self.head)
        last = json.loads((outdir / "last.json").read_text(encoding="utf-8"))
        self.assertEqual(last["state"], "ADVANCE")
        self.assertEqual(last["receipts"][0]["state"], "DRY")

    def test_swh_origin_listed_is_not_origin_readable(self) -> None:
        origin = {
            "url": "https://github.com/woahwhattheheck/commons",
            "visit_types": ["git"],
            "origin_visits_url": "https://archive.softwareheritage.org/api/1/origin/https://github.com/woahwhattheheck/commons/visits/",
            "metadata_authorities_url": (
                "https://archive.softwareheritage.org/api/1/raw-extrinsic-metadata/swhid/"
                "swh:1:ori:c68d456744314c4bb098c5f40e126a0a1cb09beb/authorities/"
            ),
        }
        visits = [{"origin": origin["url"], "visit": 1, "status": "created", "snapshot": None}]
        listed = mmm.classify_swh_origin(origin, visits)
        self.assertEqual(listed["state"], "ORIGIN_LISTED")
        self.assertTrue(listed["listed"])
        self.assertFalse(listed["origin_readable"])
        self.assertFalse(listed["verified"])
        self.assertEqual(listed["ori_swhid"], "swh:1:ori:c68d456744314c4bb098c5f40e126a0a1cb09beb")
        ready = mmm.classify_swh_origin(
            origin,
            [{"status": "full", "snapshot": "swh:1:snp:" + "a" * 40}],
        )
        self.assertEqual(ready["state"], "SNAPSHOT_READY")
        self.assertTrue(ready["origin_readable"])
        self.assertTrue(ready["verified"])
        hex_ready = mmm.classify_swh_origin(
            origin,
            [{"status": "full", "snapshot": "e840cec6d1ebcc876c723024e9931dd6842d038f"}],
        )
        self.assertEqual(hex_ready["state"], "SNAPSHOT_READY")
        self.assertEqual(
            hex_ready["snapshot_swhid"],
            "swh:1:snp:e840cec6d1ebcc876c723024e9931dd6842d038f",
        )
        self.assertEqual(
            mmm.normalize_snapshot_swhid("e840cec6d1ebcc876c723024e9931dd6842d038f"),
            "swh:1:snp:e840cec6d1ebcc876c723024e9931dd6842d038f",
        )
        self.assertIsNone(mmm.normalize_snapshot_swhid(None))
        self.assertEqual(mmm.classify_swh_origin({}, []).get("state"), "MISS")
        skip = mmm.request_swh_vault(None)
        self.assertEqual(skip["state"], "SKIP")
        self.assertFalse(skip["verified"])

    def test_internet_archive_classifies_523_miss_and_memento_ready(self) -> None:
        miss = mmm.classify_internet_archive(save_status=523, availability={"archived_snapshots": {}})
        self.assertEqual(miss["state"], "MISS")
        self.assertFalse(miss["verified"])
        self.assertFalse(miss["operational"])
        ready = mmm.classify_internet_archive(
            save_status=200,
            availability={
                "archived_snapshots": {
                    "closest": {
                        "status": "200",
                        "available": True,
                        "url": "http://web.archive.org/web/20260829195122/https://woahwhattheheck.github.io/commons/mirrors.json",
                        "timestamp": "20260829195122",
                    }
                }
            },
            cdx_rows=[
                ["urlkey", "timestamp"],
                ["io,github,woahwhattheheck)/commons/mirrors.json", "20260829195122"],
            ],
            memento_status=200,
        )
        self.assertEqual(ready["state"], "READY")
        self.assertTrue(ready["verified"])
        self.assertTrue(ready["operational"])
        self.assertEqual(ready["cdx_hits"], 1)
        self.assertTrue(str(ready["closest_url"]).startswith("https://"))
        readback = mmm.classify_internet_archive(
            availability={
                "archived_snapshots": {
                    "closest": {
                        "status": "200",
                        "available": True,
                        "url": "https://web.archive.org/web/20260829195122/https://woahwhattheheck.github.io/commons/mirrors.json",
                        "timestamp": "20260829195122",
                    }
                }
            },
            memento_status=200,
        )
        self.assertEqual(readback["state"], "READBACK")
        cdx_only = mmm.classify_internet_archive(
            cdx_rows=[
                ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                [
                    "io,github,woahwhattheheck)/commons/mirrors.json",
                    "20260829195122",
                    "https://woahwhattheheck.github.io/commons/mirrors.json",
                    "application/json",
                    "200",
                    "YJPTXMUWQR33YMVEHUBABGZTMOP6AXFM",
                    "3984",
                ],
            ],
            memento_status=200,
        )
        self.assertEqual(cdx_only["state"], "READBACK")
        self.assertEqual(cdx_only["closest_timestamp"], "20260829195122")
        self.assertIn("20260829195122", cdx_only["closest_url"])
        self.assertEqual(
            mmm.latest_cdx_memento(
                [
                    ["urlkey", "timestamp", "original"],
                    ["k", "20260828154648", "https://woahwhattheheck.github.io/commons/mirrors.json"],
                    ["k", "20260829195122", "https://woahwhattheheck.github.io/commons/mirrors.json"],
                ]
            )["timestamp"],
            "20260829195122",
        )
        self.assertTrue((ROOT / "ci" / "moving_main" / "receipts" / "ia-save-523.json").is_file())

    def test_prefer_skips_empty_keys_so_save_receipt_does_not_false_conflict(self) -> None:
        ntfy = {
            "id": "ntfy-cursor",
            "verified": True,
            "independent_origin": True,
            "digest": "a" * 64,
        }
        save = {
            "id": "software-heritage",
            "verified": True,
            "independent_origin": True,
            "state": "SAVE_ACCEPTED",
        }
        preferred = mmm.prefer_receipts([ntfy, save])
        self.assertEqual(preferred["state"], "PREFERRED")
        self.assertEqual(preferred["receipt"]["id"], "ntfy-cursor")
        self.assertEqual(preferred["independent"], 2)


if __name__ == "__main__":
    unittest.main()
