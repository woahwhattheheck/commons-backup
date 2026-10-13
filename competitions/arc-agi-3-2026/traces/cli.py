"""One-command synthetic demo and offline verifier for ARC3 trace custody."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import EpisodeRecorder, load_manifest, verify_manifest, write_manifest


def build_synthetic_demo() -> dict:
    recorder = EpisodeRecorder("synthetic-demo-001", max_actions=3)
    recorder.append_observation(
        (((0, 1), (0, 0)),),
        ("ACTION1", "ACTION2"),
        evidence_class="SYNTHETIC",
        source_ref="fixture:synthetic-demo/start",
    )
    recorder.append_action("ACTION1")
    recorder.append_observation(
        (
            ((0, 1), (1, 0)),
            ((0, 0), (1, 1)),
        ),
        ("ACTION1", "ACTION2"),
        levels_completed=1,
        evidence_class="SYNTHETIC",
        source_ref="fixture:synthetic-demo/step-1",
    )
    recorder.append_action("ACTION2", x=1, y=1)
    recorder.append_observation(
        (((0, 0), (0, 1)),),
        ("ACTION1",),
        state="WIN",
        levels_completed=2,
        win_levels=1,
        evidence_class="SYNTHETIC",
        source_ref="fixture:synthetic-demo/win",
    )
    return recorder.compile()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="write a deterministic synthetic trace")
    demo.add_argument("output", type=Path)
    verify = sub.add_parser("verify", help="verify canonical trace bytes offline")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    if args.command == "demo":
        manifest = build_synthetic_demo()
        write_manifest(args.output, manifest)
        print(json.dumps(verify_manifest(manifest), sort_keys=True))
        return 0
    result = verify_manifest(load_manifest(args.manifest))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
