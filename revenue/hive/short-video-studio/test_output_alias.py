#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
import unittest

from studio import ProjectError, render_project


def sample_project() -> dict:
    return {
        "title": "Alias guard",
        "preset": "vertical",
        "fps": 12,
        "audio": {"kind": "tone", "frequency": 220, "volume": 0.03},
        "segments": [
            {"duration": 10, "text": "One", "color": "#123456"},
            {"duration": 10, "text": "Two", "color": "#234567"},
            {"duration": 10, "text": "Three", "color": "#345678"},
        ],
    }


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg unavailable")
class OutputAliasTests(unittest.TestCase):
    def test_render_output_cannot_replace_editable_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            project = root / "editable-project.mp4"
            original = json.dumps(sample_project()).encode("utf-8")
            project.write_bytes(original)

            with self.assertRaisesRegex(ProjectError, "render output aliases protected project"):
                render_project(project, project)

            self.assertEqual(project.read_bytes(), original)
            self.assertFalse(project.with_suffix(".srt").exists())

    def test_caption_output_cannot_replace_editable_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            project = root / "render.srt"
            original = json.dumps(sample_project()).encode("utf-8")
            project.write_bytes(original)

            with self.assertRaisesRegex(ProjectError, "caption output aliases protected project"):
                render_project(project, root / "render.mp4")

            self.assertEqual(project.read_bytes(), original)
            self.assertFalse((root / "render.mp4").exists())

    def test_existing_hardlink_output_cannot_alias_asset(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            asset = root / "frame.png"
            asset.write_bytes(b"synthetic image bytes")
            output = root / "render.mp4"
            os.link(asset, output)
            project_data = sample_project()
            project_data["segments"][0]["asset"] = asset.name
            project = root / "project.json"
            project.write_text(json.dumps(project_data), encoding="utf-8")
            original = asset.read_bytes()

            with self.assertRaisesRegex(ProjectError, "render output aliases protected segment 1 asset"):
                render_project(project, output)

            self.assertEqual(asset.read_bytes(), original)
            self.assertEqual(output.read_bytes(), original)
            self.assertFalse(output.with_suffix(".srt").exists())

    def test_output_cannot_replace_file_audio_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            audio = root / "voice.wav"
            original = b"synthetic wav bytes"
            audio.write_bytes(original)
            project_data = sample_project()
            project_data["audio"] = {"kind": "file", "path": audio.name}
            project = root / "project.json"
            project.write_text(json.dumps(project_data), encoding="utf-8")

            with self.assertRaisesRegex(ProjectError, "render output aliases protected audio source"):
                render_project(project, audio)

            self.assertEqual(audio.read_bytes(), original)
            self.assertFalse(audio.with_suffix(".srt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
