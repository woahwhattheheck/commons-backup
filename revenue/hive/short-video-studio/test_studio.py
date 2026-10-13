#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from studio import ProjectError, render_project, validate_project, write_srt


def sample_project() -> dict:
    return {
        "title": "Test project",
        "preset": "vertical",
        "fps": 12,
        "audio": {"kind": "tone", "frequency": 330, "volume": 0.02},
        "segments": [
            {"duration": 10, "text": "One", "color": "#123456"},
            {"duration": 10, "text": "Two", "color": "#234567"},
            {"duration": 10, "text": "Three", "color": "#345678"},
        ],
    }


class StudioTests(unittest.TestCase):
    def test_validate_and_srt(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            normalized = validate_project(sample_project(), root)
            self.assertEqual(normalized["duration"], 30)
            self.assertEqual((normalized["width"], normalized["height"]), (360, 640))
            path = root / "captions.srt"
            write_srt(normalized, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("00:00:20,000 --> 00:00:30,000", text)
            self.assertIn("Three", text)

    def test_duration_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            project = sample_project()
            project["segments"][2]["duration"] = 9.9
            with self.assertRaisesRegex(ProjectError, "30-60"):
                validate_project(project, pathlib.Path(td))

    def test_asset_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            project = sample_project()
            project["segments"][0]["asset"] = "../outside.png"
            with self.assertRaisesRegex(ProjectError, "escapes"):
                validate_project(project, pathlib.Path(td))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg unavailable")
    def test_real_render_has_video_audio_and_editable_subtitle(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            project_path = root / "project.json"
            project_path.write_text(json.dumps(sample_project()), encoding="utf-8")
            output = root / "render.mp4"
            result = render_project(project_path, output)
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_suffix(".srt").is_file())
            streams = result["probe"]["streams"]
            kinds = {stream["codec_type"] for stream in streams}
            self.assertEqual(kinds, {"video", "audio", "subtitle"})
            video = next(s for s in streams if s["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (360, 640))
            self.assertGreaterEqual(float(result["probe"]["format"]["duration"]), 29.9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
