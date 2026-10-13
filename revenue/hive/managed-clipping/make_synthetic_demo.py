#!/usr/bin/env python3
"""Generate and fully render a labeled 20-clip synthetic acceptance packet."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from managed_clipping import create_project, edit_moment, export_handoff, render_project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise SystemExit(f"refusing to overwrite existing demo directory: {root}")
    root.mkdir(parents=True)
    source = root / "synthetic-managed-clipping-demo.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=30:duration=24", "-f", "lavfi", "-i",
        "sine=frequency=660:sample_rate=48000:duration=24", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "28", "-c:a", "aac", "-shortest", str(source)
    ], check=True)
    segments = []
    for i in range(20):
        start = 0.4 + i * 1.1
        segments.append({
            "id": f"seg-{i+1}", "start": start, "end": start + 0.55,
            "speaker": "Synthetic Demo", "text": f"Synthetic demo moment {i+1}", "verified": True,
        })
    (root / "transcript.json").write_text(json.dumps({"segments": segments}, indent=2) + "\n", encoding="utf-8")
    (root / "keep.json").write_text(json.dumps([[0.0, 24.0]], indent=2) + "\n", encoding="utf-8")
    project = root / "project.json"
    create_project(source, project, transcript_document={"segments": segments}, cedar_keeps=[[0.0, 24.0]], synthetic_demo=True)
    render_project(project, root / "renders")
    current = json.loads(project.read_text(encoding="utf-8"))
    clip = current["moments"][6]
    edit_moment(project, clip["id"], start_ms=clip["start_ms"] + 60, end_ms=clip["end_ms"] - 40,
                caption="Edited synthetic caption seven", hook="Edited hook seven", crop="0.1,0.0,0.8,1.0")
    render_project(project, root / "renders", [clip["id"]])
    manifest = export_handoff(project, root / "handoff")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
