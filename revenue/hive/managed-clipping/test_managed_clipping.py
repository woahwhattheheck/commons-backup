from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("managed_clipping", HERE / "managed_clipping.py")
mc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mc)


def make_source(path: Path, duration: float = 24.0) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        f"testsrc2=size=320x180:rate=30:duration={duration}", "-f", "lavfi", "-i",
        f"sine=frequency=660:sample_rate=48000:duration={duration}", "-c:v", "libx264",
        "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-shortest", str(path)
    ], check=True)


def transcript(count: int = 20) -> dict:
    segments = []
    for i in range(count):
        start = 0.4 + i * 1.1
        segments.append({
            "id": f"seg-{i+1}", "start": start, "end": start + 0.55,
            "speaker": "Demo", "text": f"Synthetic demo moment {i+1}", "verified": True,
        })
    return {"segments": segments}


class ManagedClippingTests(unittest.TestCase):
    def test_peer_contract_normalizers(self):
        segs = mc.normalize_kestrel_segments({"document": transcript(2)})
        self.assertEqual([s["id"] for s in segs], ["seg-1", "seg-2"])
        self.assertEqual(mc.normalize_cedar_keeps([[0, 1.0], [2.0, 3.0]]), [(0, 1000), (2000, 3000)])
        timeline = {"kept": [{"source_start": 30, "source_end": 60}, {"source_start": 90, "source_end": 120}]}
        self.assertEqual(mc.normalize_cedar_keeps(timeline), [(1000, 2000), (3000, 4000)])

    def test_source_fingerprint_detects_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.mp4"
            make_source(source, 2.0)
            project_path = root / "project.json"
            project = mc.create_project(source, project_path, moment_count=2, synthetic_demo=True)
            with source.open("ab") as f:
                f.write(b"changed")
            with self.assertRaisesRegex(mc.ManagedClippingError, "synchronization"):
                mc.verify_source(project)

    def test_edit_is_revisioned_and_validated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.mp4"
            make_source(source, 4.0)
            project_path = root / "project.json"
            mc.create_project(source, project_path, transcript_document=transcript(3), moment_count=3, synthetic_demo=True)
            before = mc.load_project(project_path)
            clip = before["moments"][0]
            after = mc.edit_moment(
                project_path, clip["id"], start_ms=clip["start_ms"] + 20,
                caption="Edited caption", crop="0.1,0.1,0.8,0.8",
            )
            self.assertEqual(after["edit_revision"], 2)
            self.assertEqual(after["moments"][0]["caption"], "Edited caption")
            with self.assertRaises(mc.ManagedClippingError):
                mc.edit_moment(project_path, clip["id"], start_ms=3000, end_ms=2000)

    def test_full_twenty_clip_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "synthetic-demo.mp4"
            make_source(source, 24.0)
            source_hash = mc._sha256(source)
            project_path = root / "project.json"
            mc.create_project(
                source, project_path, transcript_document=transcript(20),
                cedar_keeps=[[0.0, 24.0]], moment_count=20, synthetic_demo=True,
            )
            initial = mc.render_project(project_path, root / "renders")
            self.assertEqual(len(initial), 20)
            self.assertEqual(len({r["render"]["sha256"] for r in initial}), 20)
            first_paths = {r["clip_id"]: Path(r["video_path"]) for r in initial}
            first_hashes = {cid: mc._sha256(path) for cid, path in first_paths.items()}
            self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in first_paths.values()))

            project = mc.load_project(project_path)
            target = project["moments"][6]
            mc.edit_moment(
                project_path, target["id"],
                start_ms=target["start_ms"] + 60,
                end_ms=target["end_ms"] - 40,
                caption="Edited synthetic caption seven",
                hook="Edited hook seven",
                crop="0.1,0.0,0.8,1.0",
            )
            rerender = mc.render_project(project_path, root / "renders", [target["id"]])
            self.assertEqual(len(rerender), 1)
            self.assertIn("rev-0002", rerender[0]["video_path"])
            self.assertNotEqual(first_hashes[target["id"]], rerender[0]["render"]["sha256"])
            for cid, old_path in first_paths.items():
                self.assertEqual(mc._sha256(old_path), first_hashes[cid])

            reopened = mc.load_project(project_path)
            self.assertEqual(reopened["edit_revision"], 2)
            self.assertEqual(reopened["moments"][6]["caption"], "Edited synthetic caption seven")
            self.assertEqual(mc._sha256(source), source_hash)
            self.assertEqual(mc.verify_source(reopened), source.resolve())

            handoff = root / "handoff"
            manifest = mc.export_handoff(project_path, handoff)
            self.assertEqual(manifest["clip_count"], 20)
            self.assertTrue(manifest["synthetic_demo"])
            self.assertEqual(len(list((handoff / "videos").glob("*.mp4"))), 20)
            self.assertEqual(len(list((handoff / "captions").glob("*.srt"))), 20)
            with (handoff / "clips.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 20)
            self.assertEqual(rows[6]["caption"], "Edited synthetic caption seven")
            self.assertEqual(rows[6]["render_revision"], "2")
            self.assertTrue((handoff / "project.json").is_file())
            self.assertTrue((handoff / "manifest.json").is_file())
            self.assertTrue((handoff / "README.txt").read_text(encoding="utf-8").endswith("Synthetic demo: YES\n"))

    def test_no_overwrite_same_revision(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.mp4"
            make_source(source, 3.0)
            project_path = root / "project.json"
            mc.create_project(source, project_path, moment_count=1, synthetic_demo=True)
            mc.render_project(project_path, root / "renders")
            with self.assertRaisesRegex(mc.ManagedClippingError, "refusing to overwrite"):
                mc.render_project(project_path, root / "renders")


if __name__ == "__main__":
    unittest.main()
