from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

import production_queue as pq


def project(text: str = "hello") -> dict:
    return {
        "title": "Custody",
        "preset": "vertical",
        "fps": 12,
        "segments": [{"duration": 30, "text": text, "color": "#20242a"}],
        "audio": {"kind": "tone", "frequency": 220, "volume": 0.03},
    }


def manifest(
    jobs: list[dict] | None = None,
    *,
    brand_id: str = "demo-brand",
    preset_id: str = "clean-v1",
) -> dict:
    return {
        "schema": pq.MANIFEST_SCHEMA,
        "campaign_id": "campaign-1",
        "brand": {"brand_id": brand_id, "preset_id": preset_id},
        "jobs": jobs
        or [
            {
                "job_id": "video-1",
                "project": "projects/one.json",
                "output": "exports/one.mp4",
            }
        ],
    }


class Workspace:
    def __init__(self, root: pathlib.Path, jobs: list[dict] | None = None):
        self.root = root
        self.manifest_path = root / "campaign.json"
        self.state_path = root / "state.json"
        self.calls: list[str] = []
        self.write_manifest(manifest(jobs))

    def write_manifest(self, value: dict) -> None:
        for job in value["jobs"]:
            path = self.root / job["project"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(json.dumps(project(job["job_id"])), encoding="utf-8")
        self.manifest_path.write_text(json.dumps(value), encoding="utf-8")

    def renderer(self, project_path: pathlib.Path, output_path: pathlib.Path):
        self.calls.append(project_path.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        digest = pq.sha256_bytes(project_path.read_bytes())
        output_path.write_bytes(("mp4:" + digest).encode())
        output_path.with_suffix(".srt").write_text(
            "1\n00:00:00,000 --> 00:00:30,000\nok\n", encoding="utf-8"
        )
        return {"ok": True}


class CampaignCustodyTests(unittest.TestCase):
    def test_brand_change_cannot_relabel_rendered_state(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            changed = manifest(brand_id="other-brand")
            ws.write_manifest(changed)
            with self.assertRaisesRegex(pq.ProductionError, "campaign definition mismatch"):
                pq.compile_delivery(ws.manifest_path, ws.state_path)

    def test_preset_change_cannot_relabel_rendered_state(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            changed = manifest(preset_id="other-preset")
            ws.write_manifest(changed)
            with self.assertRaisesRegex(pq.ProductionError, "campaign definition mismatch"):
                pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)

    def test_adding_job_reuses_verified_job_under_same_campaign_definition(self):
        jobs = [
            {"job_id": "video-1", "project": "projects/one.json", "output": "exports/one.mp4"}
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)
            first = pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            expanded = manifest(
                jobs
                + [
                    {
                        "job_id": "video-2",
                        "project": "projects/two.json",
                        "output": "exports/two.mp4",
                    }
                ]
            )
            ws.write_manifest(expanded)
            second = pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            self.assertEqual(first["campaign_definition_sha256"], second["campaign_definition_sha256"])
            self.assertEqual(
                ["SKIPPED_VERIFIED", "RENDERED"],
                [action["action"] for action in second["actions"]],
            )
            self.assertEqual(["one.json", "two.json"], ws.calls)
            self.assertTrue(second["all_rendered"])

    def test_legacy_v1_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            ws.state_path.write_text(
                json.dumps(
                    {
                        "schema": "short-video-production-state/v1",
                        "campaign_id": "campaign-1",
                        "jobs": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(pq.ProductionError, "legacy v1 state"):
                pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)

    def test_preexisting_hardlink_equivalent_outputs_are_rejected(self):
        jobs = [
            {"job_id": "video-1", "project": "projects/one.json", "output": "exports/one.mp4"},
            {"job_id": "video-2", "project": "projects/two.json", "output": "exports/two.mp4"},
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)
            exports = ws.root / "exports"
            exports.mkdir()
            first = exports / "one.mp4"
            first.write_bytes(b"same-inode")
            os.link(first, exports / "two.mp4")
            with self.assertRaisesRegex(pq.ProductionError, "unique by file identity"):
                pq.load_manifest(ws.manifest_path)

    def test_renderer_created_hardlink_collision_is_rejected_after_render(self):
        jobs = [
            {"job_id": "video-1", "project": "projects/one.json", "output": "exports/one.mp4"},
            {"job_id": "video-2", "project": "projects/two.json", "output": "exports/two.mp4"},
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)

            def aliasing_renderer(project_path: pathlib.Path, output_path: pathlib.Path):
                if project_path.name == "one.json":
                    return ws.renderer(project_path, output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                os.link(ws.root / "exports/one.mp4", output_path)
                os.link(ws.root / "exports/one.srt", output_path.with_suffix(".srt"))
                return {"ok": True}

            with self.assertRaisesRegex(pq.ProductionError, "unique by file identity"):
                pq.run_campaign(ws.manifest_path, ws.state_path, renderer=aliasing_renderer)

    def test_final_all_rendered_revalidates_earlier_artifact(self):
        jobs = [
            {"job_id": "video-1", "project": "projects/one.json", "output": "exports/one.mp4"},
            {"job_id": "video-2", "project": "projects/two.json", "output": "exports/two.mp4"},
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)

            def mutating_renderer(project_path: pathlib.Path, output_path: pathlib.Path):
                if project_path.name == "two.json":
                    (ws.root / "exports/one.mp4").write_bytes(b"mutated-after-first-job")
                return ws.renderer(project_path, output_path)

            result = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=mutating_renderer
            )
            self.assertEqual(["RENDERED", "RENDERED"], [a["action"] for a in result["actions"]])
            self.assertFalse(result["all_rendered"])
            delivery = pq.compile_delivery(ws.manifest_path, ws.state_path)
            self.assertEqual("INCOMPLETE", delivery["state"])
            self.assertEqual("STALE", delivery["jobs"][0]["status"])

    def test_manifest_evolution_changes_manifest_digest_not_campaign_definition(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            first = pq.compile_delivery(ws.manifest_path, ws.state_path)
            expanded = manifest(
                [
                    {"job_id": "video-1", "project": "projects/one.json", "output": "exports/one.mp4"},
                    {"job_id": "video-2", "project": "projects/two.json", "output": "exports/two.mp4"},
                ]
            )
            ws.write_manifest(expanded)
            second = pq.compile_delivery(ws.manifest_path, ws.state_path)
            self.assertEqual(first["campaign_definition_sha256"], second["campaign_definition_sha256"])
            self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])
            self.assertEqual("INCOMPLETE", second["state"])
            self.assertEqual("PENDING", second["jobs"][1]["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
