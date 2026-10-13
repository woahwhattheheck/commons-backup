#!/usr/bin/env python3
"""Run a complete synthetic creative-review workflow with no provider actions."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from desk import CreativeReviewDesk, canonical_json, read_json_file, verify_bundle

HERE = Path(__file__).resolve().parent


def run(workspace: Path) -> dict:
    if workspace.exists():
        if any(workspace.iterdir()):
            raise RuntimeError("workspace must be absent or empty")
    else:
        workspace.mkdir(parents=True)
    database = workspace / "creative-review.sqlite3"
    output = workspace / "approved-packet"
    output.mkdir()
    desk = CreativeReviewDesk(database)
    spec = read_json_file(HERE / "demo" / "spec.json")
    campaign = spec["campaign_id"]

    desk.create_campaign("demo-create", spec)
    desk.submit_asset(
        "demo-submit-hero",
        campaign,
        "hero-image",
        "designer-a",
        HERE / "demo" / "hero.txt",
        "image",
        {"width": 1200, "height": 628, "duration_ms": None, "page_count": None},
        "self-authored:demo/hero.txt",
    )
    desk.submit_asset(
        "demo-submit-video",
        campaign,
        "social-video",
        "editor-a",
        HERE / "demo" / "social-video.txt",
        "video",
        {"width": 1080, "height": 1920, "duration_ms": 15000, "page_count": None},
        "self-authored:demo/social-video.txt",
    )

    assignments = [
        ("hero-image", "brand", "reviewer-hero-brand"),
        ("hero-image", "legal", "reviewer-hero-legal"),
        ("social-video", "brand", "reviewer-video-brand"),
        ("social-video", "accessibility", "reviewer-video-accessibility"),
    ]
    for index, (asset, role, reviewer) in enumerate(assignments, 1):
        desk.assign_reviewer(f"demo-assign-{index}", campaign, asset, role, reviewer)

    desk.add_annotation(
        "demo-open-annotation",
        "demo-caption-timing",
        campaign,
        "social-video",
        "accessibility",
        "reviewer-video-accessibility",
        {"kind": "TIME_MS", "start_ms": 3000, "end_ms": 4500},
        "ACCESSIBILITY_REVIEW_REQUIRED",
        "Owner workflow asks for a caption-timing check in this synthetic interval.",
    )
    desk.resolve_annotation(
        "demo-resolve-annotation",
        campaign,
        "demo-caption-timing",
        "editor-a",
    )

    decisions = [
        ("hero-image", "brand", "reviewer-hero-brand"),
        ("hero-image", "legal", "reviewer-hero-legal"),
        ("social-video", "brand", "reviewer-video-brand"),
        ("social-video", "accessibility", "reviewer-video-accessibility"),
    ]
    for index, (asset, role, reviewer) in enumerate(decisions, 1):
        desk.decide(
            f"demo-decision-{index}",
            campaign,
            asset,
            role,
            reviewer,
            "APPROVE",
            "Owner-supplied workflow requirement reviewed for the exact retained bytes.",
        )

    exported = desk.export(campaign, output)
    verified = verify_bundle(output)
    return {
        "database": str(database),
        "output_directory": str(output),
        "export": exported,
        "verification": verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--replace", action="store_true", help="delete an existing demo workspace first")
    args = parser.parse_args()
    if args.replace and args.workspace.exists():
        shutil.rmtree(args.workspace)
    print(canonical_json(run(args.workspace)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
