import contextlib
import importlib.util
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("lerobot_quality", HERE / "lerobot_quality.py")
q = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
import sys
sys.modules[SPEC.name] = q
SPEC.loader.exec_module(q)


def vec(seed=0.0, dim=20):
    return tuple(seed + i * 0.01 for i in range(dim))


def rows(n=5, fps=10.0, ep=0):
    return [q.FrameRow(ep, i, i / fps, vec(i * 0.1), vec(i * 0.2)) for i in range(n)]


def camera(ep=0, name="cam0", start=0.0, dt=0.1, n=5, mean=120.0, std=30.0, edge=0.1):
    return [q.VisualFrame(ep, i, name, start + i * dt, mean, std, edge, True) for i in range(n)]


class LayoutTests(unittest.TestCase):
    def make_root(self, version="v2.1", episodes=None, total=2):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        for d in ("meta", "data", "videos"):
            (root / d).mkdir()
        features = {
            "observation.state": {"dtype": "float32", "shape": [20]},
            "action": {"dtype": "float32", "shape": [20]},
            "observation.images.left": {"dtype": "video"},
            "observation.images.right": {"dtype": "video"},
            "observation.images.head": {"dtype": "video"},
        }
        (root / "meta/info.json").write_text(json.dumps({"codebase_version": version, "fps": 10, "total_episodes": total, "features": features}), encoding="utf-8")
        records = episodes if episodes is not None else [{"episode_index": 0, "length": 5}, {"episode_index": 1, "length": 5}]
        (root / "meta/episodes.jsonl").write_text("".join(json.dumps(x)+"\n" for x in records), encoding="utf-8")
        return td, root

    def test_valid_v21_layout_contract(self):
        td, root = self.make_root()
        self.addCleanup(td.cleanup)
        info, eps, faults = q.validate_layout(root, q.AuditConfig())
        self.assertEqual("v2.1", info["codebase_version"])
        self.assertEqual([0, 1], sorted(eps))
        self.assertEqual([], faults)

    def test_version_gap_duplicate_and_camera_count_fail_closed(self):
        td, root = self.make_root(version="v3.0", episodes=[{"episode_index":0,"length":5},{"episode_index":2,"length":5},{"episode_index":2,"length":5}], total=3)
        self.addCleanup(td.cleanup)
        info = json.loads((root / "meta/info.json").read_text())
        info["features"].pop("observation.images.head")
        (root / "meta/info.json").write_text(json.dumps(info))
        _, _, faults = q.validate_layout(root, q.AuditConfig())
        codes = {f.code for f in faults}
        self.assertTrue({"wrong_version", "episode_index_gap", "episode_index_duplicate", "camera_count_mismatch"} <= codes)

    def test_missing_required_directories_and_metadata_localized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "meta").mkdir()
            info, eps, faults = q.validate_layout(root, q.AuditConfig())
            self.assertEqual({}, info)
            self.assertEqual({}, eps)
            self.assertIn("missing_file", {f.code for f in faults})
            self.assertGreaterEqual(sum(f.code == "missing_directory" for f in faults), 2)


class TimingFaultInjectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = q.AuditConfig()

    def test_frame_loss_and_fps_jitter(self):
        sample = rows(5)
        bad = [sample[0], sample[1], q.FrameRow(0, 3, 0.22, vec(.3), vec(.6)), sample[4]]
        faults = q._timing_faults(bad, 10.0, self.cfg)
        codes = [f.code for f in faults]
        self.assertIn("frame_loss", codes)
        self.assertIn("fps_jitter", codes)
        self.assertTrue(any(f.frame_index == 3 for f in faults))

    def test_timestamp_reversal_duplicate_and_frame_order(self):
        sample = [
            q.FrameRow(0,0,0.0,vec(0),vec(0)),
            q.FrameRow(0,1,0.1,vec(1),vec(1)),
            q.FrameRow(0,1,0.1,vec(2),vec(2)),
            q.FrameRow(0,2,0.05,vec(3),vec(3)),
        ]
        faults = q._timing_faults(sample, 10.0, self.cfg)
        codes = {f.code for f in faults}
        self.assertTrue({"frame_order", "timestamp_duplicate", "timestamp_reversal"} <= codes)


class VectorFaultInjectionTests(unittest.TestCase):
    def test_malformed_nonfinite_and_out_of_range_20d(self):
        cfg = q.AuditConfig(vector_abs_limit=100.0)
        sample = [
            q.FrameRow(0,0,0.0,vec(0,19),vec(0)),
            q.FrameRow(0,1,0.1,tuple([math.nan] + [0.0]*19),tuple([101.0]+[0.0]*19)),
        ]
        faults = q._vector_faults(sample, cfg)
        codes = {f.code for f in faults}
        self.assertTrue({"malformed_vector", "nonfinite_vector", "out_of_range_vector"} <= codes)
        self.assertTrue(all(f.episode_index == 0 for f in faults))


class VisualFaultInjectionTests(unittest.TestCase):
    def test_corrupt_black_and_occluded_frames(self):
        visuals = {"cam": [
            q.VisualFrame(0,0,"cam",0.0,120,30,.1,False),
            q.VisualFrame(0,1,"cam",.1,0.5,1,.0,True),
            q.VisualFrame(0,2,"cam",.2,50,1,.0001,True),
        ]}
        faults = q._visual_faults(visuals, q.AuditConfig())
        self.assertEqual({"corrupt_visual","black_frame","occluded_frame"}, {f.code for f in faults})
        self.assertEqual({0,1,2}, {f.frame_index for f in faults})


class SynchronizationFaultInjectionTests(unittest.TestCase):
    def test_offset_drift_and_overlap_across_three_cameras(self):
        sample = rows(5, fps=10)
        visuals = {
            "cam-good": camera(name="cam-good"),
            "cam-offset": camera(name="cam-offset", start=.2),
            "cam-drift": camera(name="cam-drift", dt=.15),
        }
        faults = q._sync_faults(sample, visuals, q.AuditConfig(max_offset_ms=50, max_drift_ms=50, min_overlap_ratio=.95))
        codes = {f.code for f in faults}
        self.assertTrue({"stream_offset", "stream_drift", "stream_overlap"} <= codes)
        self.assertTrue(any(f.modality == "cam-offset" for f in faults))
        self.assertTrue(any(f.modality == "cam-drift" for f in faults))


class ScoringAndReportingTests(unittest.TestCase):
    def test_clean_dynamic_episode_scores_100(self):
        visuals = {name: camera(name=name) for name in ("cam0","cam1","cam2")}
        result = q.analyze_episode(0, 5, rows(5), visuals, 10.0, q.AuditConfig())
        self.assertEqual(100.0, result["scores"]["quality"])
        self.assertEqual(100.0, result["scores"]["dynamic_signal"])
        self.assertEqual(100.0, result["scores"]["training_value"])
        self.assertEqual([], result["faults"])

    def test_static_episode_training_value_is_lower_and_explained(self):
        same = [q.FrameRow(0,i,i/10,vec(0),vec(0)) for i in range(5)]
        visuals = {name: camera(name=name) for name in ("cam0","cam1","cam2")}
        result = q.analyze_episode(0, 5, same, visuals, 10, q.AuditConfig())
        self.assertLess(result["scores"]["training_value"], result["scores"]["quality"])
        self.assertIn("low_dynamic_range", {f["code"] for f in result["faults"]})

    def test_report_is_deterministic_and_contains_localization_and_scoring_contract(self):
        cfg = q.AuditConfig()
        info = {"codebase_version":"v2.1","fps":10}
        meta = {0:{"episode_index":0,"length":5}}
        injected = [q.Fault("missing_file","error","fixture missing",0,2,"cam0")]
        visuals = {0:{name: camera(name=name) for name in ("cam0","cam1","cam2")}}
        report1 = q.aggregate_report(Path("/fixture"), info, meta, {0:rows(5)}, visuals, injected, cfg, {"meta/info.json":"abc"})
        report2 = q.aggregate_report(Path("/fixture"), info, meta, {0:rows(5)}, visuals, injected, cfg, {"meta/info.json":"abc"})
        encoded1 = json.dumps(report1, sort_keys=True, allow_nan=False)
        encoded2 = json.dumps(report2, sort_keys=True, allow_nan=False)
        self.assertEqual(encoded1, encoded2)
        self.assertIn("quality_category_weights", report1["scoring"])
        self.assertEqual("abc", report1["provenance_sha256"]["meta/info.json"])
        md = q.report_markdown(report1)
        self.assertIn("Fault localization", md)
        self.assertIn("fixture missing", md)
        self.assertIn("not evidence of competition registration", md)
        h = q.report_html(report1)
        self.assertIn("<!doctype html>", h)
        self.assertIn("Wuhu LeRobot", h)

    def test_write_reports_emits_json_markdown_html(self):
        cfg=q.AuditConfig(); info={"codebase_version":"v2.1","fps":10}; meta={0:{"episode_index":0,"length":5}}; visuals={0:{name:camera(name=name) for name in ("cam0","cam1","cam2")}}
        report=q.aggregate_report(Path("/fixture"),info,meta,{0:rows(5)},visuals,[],cfg,{})
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); q.write_reports(report,out)
            self.assertEqual({"report.json","report.md","report.html"},{p.name for p in out.iterdir()})
            self.assertEqual(report,json.loads((out/"report.json").read_text()))


class FullAuditAndBoundaryTests(unittest.TestCase):
    def make_root(self):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)/"dataset"; (root/"meta").mkdir(parents=True); (root/"data").mkdir(); (root/"videos").mkdir()
        features={"observation.state":{"dtype":"float32","shape":[20]},"action":{"dtype":"float32","shape":[20]},"cam0":{"dtype":"video"},"cam1":{"dtype":"video"},"cam2":{"dtype":"video"}}
        (root/"meta/info.json").write_text(json.dumps({"codebase_version":"v2.1","fps":10,"total_episodes":1,"features":features}))
        (root/"meta/episodes.jsonl").write_text(json.dumps({"episode_index":0,"length":5})+"\n")
        return td,root

    def test_audit_wires_layout_rows_visuals_provenance_without_mutating_dataset(self):
        td,root=self.make_root(); self.addCleanup(td.cleanup)
        before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()}
        visuals={0:{name:camera(name=name) for name in ("cam0","cam1","cam2")}}
        with mock.patch.object(q,"load_parquet_rows",return_value=({0:rows(5)},[],{"data/chunk-000/episode_000000.parquet":"d"})), mock.patch.object(q,"load_visuals",return_value=(visuals,[],{}, {"videos/chunk-000/cam0/episode_000000.mp4":"v"})):
            report=q.audit_dataset(root,q.AuditConfig())
        after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(100.0,report["overall_scores"]["quality"])
        self.assertIn("meta/info.json",report["provenance_sha256"])
        self.assertEqual("d",report["provenance_sha256"]["data/chunk-000/episode_000000.parquet"])

    def test_cli_refuses_output_inside_dataset_root(self):
        td,root=self.make_root(); self.addCleanup(td.cleanup)
        err=io.StringIO()
        with contextlib.redirect_stderr(err):
            rc=q.main(["audit",str(root),"--out-dir",str(root/"reports")])
        self.assertEqual(2,rc)
        self.assertIn("outside the immutable dataset root",err.getvalue())
        self.assertFalse((root/"reports").exists())

    def test_dependency_unavailability_is_explicit_fault_not_silent_skip(self):
        td,root=self.make_root(); self.addCleanup(td.cleanup)
        real_import=__import__
        def blocked(name,*args,**kwargs):
            if name.startswith("pyarrow") or name in {"av","numpy"}: raise ImportError(name)
            return real_import(name,*args,**kwargs)
        with mock.patch("builtins.__import__",side_effect=blocked):
            _,pf,_=q.load_parquet_rows(root,{"features":{}},{0:{}})
            vf,ff,_,_=q.load_visuals(root,{"features":{"cam0":{"dtype":"video"}}},{0:{}},q.AuditConfig(expected_cameras=1))
        self.assertIn("parquet_unavailable",{f.code for f in pf})
        self.assertIn("missing_file",{f.code for f in ff})
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            with mock.patch("builtins.__import__",side_effect=blocked):
                _,faults,_=q._decode_video(Path(tmp.name),0,"cam0",1)
        self.assertEqual("decoder_unavailable",faults[0].code)


if __name__ == "__main__":
    unittest.main()
