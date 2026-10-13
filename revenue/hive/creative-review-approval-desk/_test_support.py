#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from desk import (  # noqa: E402
    AUTHORITY,
    CreativeReviewDesk,
    IdempotencyConflict,
    InvalidInput,
    InvalidState,
    canonical_bytes,
    normalize_spec,
    strict_json_loads,
    verify_bundle,
)


class CreativeReviewDeskTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "desk.sqlite3"
        self.desk = CreativeReviewDesk(self.db)
        self.spec = {
            "campaign_id": "fall-launch",
            "name": "Synthetic Fall Launch",
            "policy": {
                "require_distinct_reviewers": True,
                "prohibit_author_review": True,
            },
            "assets": [
                {
                    "asset_id": "hero-image",
                    "title": "Hero image",
                    "media_type": "image",
                    "destinations": ["meta-feed", "shop-home"],
                    "required_roles": ["brand", "legal"],
                    "constraints": {
                        "width": 1200,
                        "height": 628,
                        "duration_ms": None,
                        "page_count": None,
                    },
                },
                {
                    "asset_id": "social-video",
                    "title": "Synthetic vertical spot",
                    "media_type": "video",
                    "destinations": ["short-video"],
                    "required_roles": ["accessibility", "brand"],
                    "constraints": {
                        "width": 1080,
                        "height": 1920,
                        "duration_ms": 15000,
                        "page_count": None,
                    },
                },
            ],
        }
        self.hero = self.root / "hero.bin"
        self.video = self.root / "spot.bin"
        self.hero.write_bytes(b"synthetic hero generation 1")
        self.video.write_bytes(b"synthetic video generation 1")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def image_metadata() -> dict[str, int | None]:
        return {"width": 1200, "height": 628, "duration_ms": None, "page_count": None}

    @staticmethod
    def video_metadata() -> dict[str, int | None]:
        return {"width": 1080, "height": 1920, "duration_ms": 15000, "page_count": None}

    def create(self) -> None:
        self.desk.create_campaign("create-1", self.spec)

    def submit_hero(self, request: str = "submit-hero", path: Path | None = None) -> dict:
        return self.desk.submit_asset(
            request,
            "fall-launch",
            "hero-image",
            "designer-a",
            self.hero if path is None else path,
            "image",
            self.image_metadata(),
            "self-authored:synthetic-fixture",
        )

    def submit_video(self, request: str = "submit-video", path: Path | None = None) -> dict:
        return self.desk.submit_asset(
            request,
            "fall-launch",
            "social-video",
            "editor-a",
            self.video if path is None else path,
            "video",
            self.video_metadata(),
            "self-authored:synthetic-fixture",
        )

    def assign_hero(self) -> None:
        self.desk.assign_reviewer("assign-h-brand", "fall-launch", "hero-image", "brand", "reviewer-brand")
        self.desk.assign_reviewer("assign-h-legal", "fall-launch", "hero-image", "legal", "reviewer-legal")

    def assign_video(self) -> None:
        self.desk.assign_reviewer("assign-v-brand", "fall-launch", "social-video", "brand", "reviewer-v-brand")
        self.desk.assign_reviewer(
            "assign-v-accessibility",
            "fall-launch",
            "social-video",
            "accessibility",
            "reviewer-accessibility",
        )

    def approve_hero(self) -> None:
        self.desk.decide(
            "approve-h-brand",
            "fall-launch",
            "hero-image",
            "brand",
            "reviewer-brand",
            "APPROVE",
            "owner workflow requirement reviewed",
        )
        self.desk.decide(
            "approve-h-legal",
            "fall-launch",
            "hero-image",
            "legal",
            "reviewer-legal",
            "APPROVE",
            "owner workflow requirement reviewed",
        )

    def approve_video(self) -> None:
        self.desk.decide(
            "approve-v-brand",
            "fall-launch",
            "social-video",
            "brand",
            "reviewer-v-brand",
            "APPROVE",
            "reviewed",
        )
        self.desk.decide(
            "approve-v-accessibility",
            "fall-launch",
            "social-video",
            "accessibility",
            "reviewer-accessibility",
            "APPROVE",
            "reviewed",
        )

    def make_ready(self) -> None:
        self.create()
        self.submit_hero()
        self.submit_video()
        self.assign_hero()
        self.assign_video()
        self.approve_hero()
        self.approve_video()
