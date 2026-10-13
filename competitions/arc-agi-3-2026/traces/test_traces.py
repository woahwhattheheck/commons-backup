from __future__ import annotations

import copy
import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adapter import append_transition_object, effect_adapter_payload, replay_transition
from cli import build_synthetic_demo
from core import (
    EpisodeRecorder,
    TraceError,
    canonical_json_bytes,
    frame_record,
    strict_json_loads,
    verify_manifest,
    verify_manifest_bytes,
)


class TraceTests(unittest.TestCase):
    def manifest(self):
        return build_synthetic_demo()

    def test_demo_verifies(self):
        result = verify_manifest(self.manifest())
        self.assertEqual(result["status"], "VERIFIED_OFFLINE_TRACE")
        self.assertFalse(result["provider_capture_verified"])

    def test_intermediate_frames_preserved(self):
        manifest = self.manifest()
        obs = manifest["events"][2]["payload"]
        self.assertEqual(len(obs["frames"]), 2)
        self.assertNotEqual(obs["frames"][0]["sha256"], obs["frames"][1]["sha256"])

    def test_effect_adapter_shape(self):
        payload = effect_adapter_payload(self.manifest(), 0)
        self.assertEqual(payload["action_key"], "ACTION1")
        self.assertEqual(len(payload["frames"]), 2)
        self.assertEqual(set(payload), {"action_key", "before", "frames"})

    def test_complex_action_key(self):
        replay = replay_transition(self.manifest(), 1)
        self.assertEqual(replay.action_key, "ACTION2@1,1")

    def test_frame_hash_tamper_fails(self):
        manifest = copy.deepcopy(self.manifest())
        manifest["events"][0]["payload"]["frames"][0]["sha256"] = "0" * 64
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_frame_payload_tamper_fails(self):
        manifest = copy.deepcopy(self.manifest())
        payload = manifest["events"][0]["payload"]["frames"][0]["payload_b64"]
        manifest["events"][0]["payload"]["frames"][0]["payload_b64"] = ("A" if payload[0] != "A" else "B") + payload[1:]
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_reorder_fails(self):
        manifest = copy.deepcopy(self.manifest())
        manifest["events"][2], manifest["events"][4] = manifest["events"][4], manifest["events"][2]
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_event_omission_fails(self):
        manifest = copy.deepcopy(self.manifest())
        del manifest["events"][2:4]
        manifest["event_count"] -= 2
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_duplicate_json_key_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        self.assertRaises(TraceError, strict_json_loads, raw)

    def test_noncanonical_json_bytes_rejected(self):
        raw = canonical_json_bytes(self.manifest()).replace(b'"schema":', b'"schema" :', 1)
        self.assertRaises(TraceError, verify_manifest_bytes, raw)

    def test_bool_int_alias_rejected(self):
        manifest = copy.deepcopy(self.manifest())
        manifest["action_count"] = True
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_float_rejected_by_parser(self):
        self.assertRaises(TraceError, strict_json_loads, b'{"x":1.0}')

    def test_huge_integer_parser_normalizes_failure(self):
        raw = b'{"x":' + (b'9' * 5000) + b'}'
        with self.assertRaises(TraceError):
            strict_json_loads(raw)

    def test_lone_surrogate_string_normalizes_failure(self):
        with self.assertRaises(TraceError):
            strict_json_loads('{"x":"\ud800"}')

    def test_deep_json_parser_normalizes_failure(self):
        raw = (('[' * 2000) + '0' + (']' * 2000)).encode('ascii')
        with self.assertRaises(TraceError):
            strict_json_loads(raw)

    def test_deep_direct_object_rejected_without_recursion_escape(self):
        value = 0
        for _ in range(200):
            value = [value]
        with self.assertRaises(TraceError):
            canonical_json_bytes(value)

    def test_cyclic_direct_object_rejected_without_node_burn(self):
        value = []
        value.append(value)
        with self.assertRaisesRegex(TraceError, "cyclic"):
            canonical_json_bytes(value)

    def test_shared_noncyclic_container_is_allowed(self):
        shared = [1, 2]
        self.assertEqual(canonical_json_bytes({"a": shared, "b": shared}), b'{"a":[1,2],"b":[1,2]}')

    def test_unavailable_action_rejected(self):
        rec = EpisodeRecorder("unavailable", max_actions=2)
        rec.append_observation((((0,),),), ("ACTION1",), source_ref="synthetic:test")
        self.assertRaises(TraceError, rec.append_action, "ACTION2")

    def test_budget_drift_rejected(self):
        rec = EpisodeRecorder("budget", max_actions=2)
        rec.append_observation((((0,),),), ("ACTION1",), source_ref="synthetic:test")
        self.assertRaises(TraceError, rec.append_action, "ACTION1", actions_left_before=1)

    def test_terminal_action_rejected(self):
        rec = EpisodeRecorder("terminal", max_actions=2)
        rec.append_observation((((0,),),), ("ACTION1",), state="WIN", source_ref="synthetic:test")
        self.assertRaises(TraceError, rec.append_action, "ACTION1")

    def test_progress_regression_rejected(self):
        rec = EpisodeRecorder("progress", max_actions=2)
        rec.append_observation((((0,),),), ("ACTION1",), levels_completed=1, source_ref="synthetic:a")
        rec.append_action("ACTION1")
        self.assertRaises(
            TraceError,
            rec.append_observation,
            (((1,),),),
            ("ACTION1",),
            levels_completed=0,
            source_ref="synthetic:b",
        )

    def test_secret_like_source_ref_rejected(self):
        rec = EpisodeRecorder("secret", max_actions=1)
        self.assertRaises(
            TraceError,
            rec.append_observation,
            (((0,),),),
            ("ACTION1",),
            source_ref="authorization: Bearer not-a-real-secret-value",
        )

    def test_authority_widening_rejected(self):
        manifest = copy.deepcopy(self.manifest())
        manifest["authority"]["provider_capture_verified"] = True
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_evidence_summary_tamper_rejected(self):
        manifest = copy.deepcopy(self.manifest())
        manifest["evidence_classes"] = ["PUBLIC_SOURCE"]
        self.assertRaises(TraceError, verify_manifest, manifest)

    def test_event_chain_reseal_does_not_rescue_semantic_budget_tamper(self):
        rec = EpisodeRecorder("bad-budget", max_actions=3)
        rec.append_observation((((0,),),), ("ACTION1",), source_ref="synthetic:a")
        rec.append_action("ACTION1")
        rec.append_observation((((1,),),), ("ACTION1",), source_ref="synthetic:b")
        bad = rec.compile()
        bad["events"][1]["payload"]["actions_left_before"] = 2
        from hashlib import sha256
        event = bad["events"][1]
        core = {k: event[k] for k in ("seq", "kind", "payload", "prev_event_sha256")}
        event["event_sha256"] = sha256(canonical_json_bytes(core)).hexdigest()
        bad["events"][2]["prev_event_sha256"] = event["event_sha256"]
        core2 = {k: bad["events"][2][k] for k in ("seq", "kind", "payload", "prev_event_sha256")}
        bad["events"][2]["event_sha256"] = sha256(canonical_json_bytes(core2)).hexdigest()
        bad["event_chain_sha256"] = bad["events"][2]["event_sha256"]
        top = {k: bad[k] for k in bad if k != "manifest_sha256"}
        bad["manifest_sha256"] = sha256(canonical_json_bytes(top)).hexdigest()
        self.assertRaises(TraceError, verify_manifest, bad)

    def test_transition_object_adapter(self):
        @dataclass(frozen=True)
        class O:
            frames: tuple
            available_actions: tuple
            state: str = "NOT_FINISHED"
            levels_completed: int = 0
            win_levels: int = 0
        @dataclass(frozen=True)
        class A:
            name: str
            x: int | None = None
            y: int | None = None
        @dataclass(frozen=True)
        class T:
            before: O
            action: A
            after: O
        before = O(frames=(((0,),),), available_actions=("ACTION1",))
        after = O(frames=(((1,),),), available_actions=("ACTION1",), levels_completed=1)
        rec = EpisodeRecorder("adapter", max_actions=1)
        append_transition_object(
            rec,
            T(before, A("ACTION1"), after),
            before_evidence_class="SYNTHETIC",
            before_source_ref="synthetic:before",
            after_evidence_class="SYNTHETIC",
            after_source_ref="synthetic:after",
        )
        self.assertEqual(verify_manifest(rec.compile())["action_count"], 1)

    def test_transition_before_mismatch_rejected(self):
        @dataclass(frozen=True)
        class O:
            frames: tuple
            available_actions: tuple
            state: str = "NOT_FINISHED"
            levels_completed: int = 0
            win_levels: int = 0
        @dataclass(frozen=True)
        class A:
            name: str
            x: int | None = None
            y: int | None = None
        @dataclass(frozen=True)
        class T:
            before: O
            action: A
            after: O
        rec = EpisodeRecorder("mismatch", max_actions=2)
        rec.append_observation((((0,),),), ("ACTION1",), source_ref="synthetic:tail")
        wrong = O(frames=(((1,),),), available_actions=("ACTION1",))
        after = O(frames=(((2,),),), available_actions=("ACTION1",))
        self.assertRaises(
            TraceError,
            append_transition_object,
            rec,
            T(wrong, A("ACTION1"), after),
            before_evidence_class="SYNTHETIC",
            before_source_ref="synthetic:before",
            after_evidence_class="SYNTHETIC",
            after_source_ref="synthetic:after",
        )

    def test_frame_record_bool_cell_rejected(self):
        self.assertRaises(TraceError, frame_record, ((False,),))

    def test_python_optimized_suite_executes(self):
        if sys.flags.optimize:
            return
        env = dict(os.environ)
        proc = subprocess.run(
            [sys.executable, "-O", str(Path(__file__).resolve())],
            cwd=HERE,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
