from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import production_queue as pq


def project(text: str = "hello") -> dict:
    return {
        "title": "Demo",
        "preset": "vertical",
        "fps": 12,
        "segments": [{"duration": 30, "text": text, "color": "#20242a"}],
        "audio": {"kind": "tone", "frequency": 220, "volume": 0.03},
    }


def manifest(jobs: list[dict] | None = None) -> dict:
    return {
        "schema": pq.MANIFEST_SCHEMA,
        "campaign_id": "campaign-1",
        "brand": {"brand_id": "demo-brand", "preset_id": "clean-v1"},
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
        value = manifest(jobs)
        for job in value["jobs"]:
            path = root / job["project"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(project(job["job_id"])), encoding="utf-8")
        self.manifest_path.write_text(json.dumps(value), encoding="utf-8")
        self.calls: list[str] = []

    def renderer(self, project_path: pathlib.Path, output_path: pathlib.Path):
        self.calls.append(project_path.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        digest = pq.sha256_bytes(project_path.read_bytes())
        output_path.write_bytes(("mp4:" + digest).encode())
        output_path.with_suffix(".srt").write_text(
            "1\n00:00:00,000 --> 00:00:30,000\nok\n", encoding="utf-8"
        )
        return {"ok": True}


class ProductionQueueTests(unittest.TestCase):
    def test_resume_skips_only_exact_verified_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            first = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=ws.renderer
            )
            second = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=ws.renderer
            )
            self.assertTrue(first["all_rendered"])
            self.assertEqual(["one.json"], ws.calls)
            self.assertEqual("SKIPPED_VERIFIED", second["actions"][0]["action"])

    def test_project_revision_change_forces_rerender(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            (ws.root / "projects/one.json").write_text(
                json.dumps(project("changed")), encoding="utf-8"
            )
            result = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=ws.renderer
            )
            self.assertEqual(["one.json", "one.json"], ws.calls)
            self.assertEqual("RENDERED", result["actions"][0]["action"])

    def test_output_tamper_forces_rerender(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            (ws.root / "exports/one.mp4").write_bytes(b"tampered")
            result = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=ws.renderer
            )
            self.assertEqual(["one.json", "one.json"], ws.calls)
            self.assertEqual("RENDERED", result["actions"][0]["action"])

    def test_partial_failure_persists_success_and_retry_only_failed_job(self):
        jobs = [
            {
                "job_id": "video-1",
                "project": "projects/one.json",
                "output": "exports/one.mp4",
            },
            {
                "job_id": "video-2",
                "project": "projects/two.json",
                "output": "exports/two.mp4",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)
            failed_once = {"value": False}

            def flaky(project_path: pathlib.Path, output_path: pathlib.Path):
                if project_path.name == "two.json" and not failed_once["value"]:
                    failed_once["value"] = True
                    raise RuntimeError("synthetic failure")
                return ws.renderer(project_path, output_path)

            first = pq.run_campaign(ws.manifest_path, ws.state_path, renderer=flaky)
            self.assertFalse(first["all_rendered"])
            self.assertEqual(
                ["RENDERED", "FAILED"], [a["action"] for a in first["actions"]]
            )
            second = pq.run_campaign(ws.manifest_path, ws.state_path, renderer=flaky)
            self.assertTrue(second["all_rendered"])
            self.assertEqual(
                ["SKIPPED_VERIFIED", "RENDERED"],
                [a["action"] for a in second["actions"]],
            )
            self.assertEqual(["one.json", "two.json"], ws.calls)

    def test_changed_job_spec_forces_rerender(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            changed = manifest()
            changed["jobs"][0]["output"] = "exports/renamed.mp4"
            ws.manifest_path.write_text(json.dumps(changed), encoding="utf-8")
            result = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=ws.renderer
            )
            self.assertEqual("RENDERED", result["actions"][0]["action"])
            self.assertTrue((ws.root / "exports/renamed.mp4").is_file())

    def test_duplicate_job_id_rejected(self):
        jobs = [
            {
                "job_id": "same",
                "project": "projects/one.json",
                "output": "exports/one.mp4",
            },
            {
                "job_id": "same",
                "project": "projects/two.json",
                "output": "exports/two.mp4",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)
            with self.assertRaisesRegex(pq.ProductionError, "duplicate job_id"):
                pq.load_manifest(ws.manifest_path)

    def test_duplicate_output_target_rejected(self):
        jobs = [
            {
                "job_id": "one",
                "project": "projects/one.json",
                "output": "exports/same.mp4",
            },
            {
                "job_id": "two",
                "project": "projects/two.json",
                "output": "exports/same.mp4",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td), jobs)
            with self.assertRaisesRegex(pq.ProductionError, "globally unique"):
                pq.load_manifest(ws.manifest_path)

    def test_project_output_alias_rejected(self):
        jobs = [
            {
                "job_id": "one",
                "project": "projects/one.json",
                "output": "projects/one.mp4",
            }
        ]
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            ws = Workspace(root, jobs)
            (root / "projects/one.mp4").hardlink_to(root / "projects/one.json")
            with self.assertRaisesRegex(pq.ProductionError, "aliases project source"):
                pq.load_manifest(ws.manifest_path)

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            outside = root.parent / "outside.json"
            outside.write_text(json.dumps(project()), encoding="utf-8")
            value = manifest()
            value["jobs"][0]["project"] = "../outside.json"
            path = root / "campaign.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            try:
                with self.assertRaisesRegex(
                    pq.ProductionError, "escapes campaign directory"
                ):
                    pq.load_manifest(path)
            finally:
                outside.unlink(missing_ok=True)

    def test_delivery_is_deterministic_and_authority_negative(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            first = pq.compile_delivery(ws.manifest_path, ws.state_path)
            second = pq.compile_delivery(ws.manifest_path, ws.state_path)
            self.assertEqual(first, second)
            self.assertEqual("DELIVERY_READY", first["state"])
            self.assertEqual("READY_FOR_DELIVERY", first["jobs"][0]["status"])
            self.assertEqual("vertical", first["jobs"][0]["project_preset"])
            self.assertTrue(all(value is False for value in first["authority"].values()))
            unsigned = dict(first)
            digest = unsigned.pop("delivery_sha256")
            self.assertEqual(pq.sha256_json(unsigned), digest)

    def test_failed_job_never_becomes_delivery_ready_from_old_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            (ws.root / "exports").mkdir()
            (ws.root / "exports/one.mp4").write_bytes(b"old")
            (ws.root / "exports/one.srt").write_text("old", encoding="utf-8")

            def fail(*_args):
                raise RuntimeError("nope")

            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=fail)
            delivery = pq.compile_delivery(ws.manifest_path, ws.state_path)
            self.assertEqual("INCOMPLETE", delivery["state"])
            self.assertEqual("FAILED", delivery["jobs"][0]["status"])
            self.assertIsNone(delivery["jobs"][0]["output_sha256"])

    def test_delivery_refuses_overwrite_and_state_alias(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))
            pq.run_campaign(ws.manifest_path, ws.state_path, renderer=ws.renderer)
            out = ws.root / "delivery.json"
            pq.write_delivery(ws.manifest_path, out, ws.state_path)
            with self.assertRaisesRegex(pq.ProductionError, "refusing to overwrite"):
                pq.write_delivery(ws.manifest_path, out, ws.state_path)
            with self.assertRaisesRegex(pq.ProductionError, "alias state"):
                pq.write_delivery(ws.manifest_path, ws.state_path, ws.state_path)

    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "projects").mkdir()
            (root / "projects/one.json").write_text(
                json.dumps(project()), encoding="utf-8"
            )
            path = root / "campaign.json"
            path.write_text(
                '{"schema":"%s","schema":"%s","campaign_id":"x",'
                '"brand":{"brand_id":"b","preset_id":"p"},"jobs":[]}'
                % (pq.MANIFEST_SCHEMA, pq.MANIFEST_SCHEMA),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(pq.ProductionError, "duplicate JSON key"):
                pq.load_manifest(path)

    def test_mutating_project_during_render_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(pathlib.Path(td))

            def mutating_renderer(
                project_path: pathlib.Path, output_path: pathlib.Path
            ):
                ws.renderer(project_path, output_path)
                project_path.write_text(
                    json.dumps(project("mutated during render")), encoding="utf-8"
                )

            result = pq.run_campaign(
                ws.manifest_path, ws.state_path, renderer=mutating_renderer
            )
            self.assertFalse(result["all_rendered"])
            self.assertEqual("FAILED", result["actions"][0]["action"])
            delivery = pq.compile_delivery(ws.manifest_path, ws.state_path)
            self.assertNotEqual("DELIVERY_READY", delivery["state"])


if __name__ == "__main__":
    unittest.main()
