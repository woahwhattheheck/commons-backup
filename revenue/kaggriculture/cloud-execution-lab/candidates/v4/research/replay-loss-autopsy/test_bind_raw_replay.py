import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

from bind_raw_replay import BindError, bind_replay


def replay(*, episode=108038484, submission="56158124", team="Opponent"):
    info = {
        "EpisodeId": episode,
        "TeamNames": ["Us", team],
        "SubmissionIds": ["ours", submission],
        "Agents": [
            {"Name": "Us", "SubmissionId": "ours"},
            {"Name": team, "SubmissionId": submission},
        ],
        "seed": 77,
    }
    steps = []
    for step in range(3):
        states = []
        for seat in range(2):
            state = {
                "observation": {"step": step, "player": seat},
                "reward": None if step < 2 else (87580 if seat == 0 else 90026),
                "status": "ACTIVE" if step < 2 else "DONE",
            }
            if step > 0:
                state["action"] = {
                    "farmer": ["PASS"] if seat == 0 else ["EAST" if step == 1 else "WEST"],
                    "hands": [],
                    "market": [] if step == 1 else [["SELL", "WHEAT", step]],
                }
            states.append(state)
        steps.append(states)
    return {"info": info, "configuration": {"seed": 77, "episodeSteps": 720}, "steps": steps}


def raw(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=True).encode()


class BinderTests(unittest.TestCase):
    def bind(self, value=None, **kw):
        value = replay() if value is None else value
        opts = dict(expected_episode="108038484", recorded_seat=1,
                    expected_team="opponent", expected_submission="56158124")
        opts.update(kw)
        return bind_replay(raw(value), source_name="episode.json", **opts)

    def test_good_binding(self):
        manifest, trace = self.bind()
        self.assertEqual("titan.v4.raw-replay-binding.v1", manifest["schema"])
        self.assertEqual("108038484", manifest["episode_id"])
        self.assertEqual([0, 1], [row["step"] for row in trace])
        self.assertEqual(["EAST"], trace[0]["action"]["farmer"])
        self.assertEqual(["WEST"], trace[1]["action"]["farmer"])
        self.assertEqual(2, manifest["trace"]["actions"])

    def test_action_is_mapped_to_preceding_observation(self):
        _, trace = self.bind()
        self.assertEqual(0, trace[0]["step"])
        self.assertEqual(["EAST"], trace[0]["action"]["farmer"])

    def test_wrong_episode_rejected(self):
        with self.assertRaisesRegex(BindError, "episode mismatch"):
            self.bind(expected_episode="nope")

    def test_wrong_submission_rejected(self):
        with self.assertRaisesRegex(BindError, "submission mismatch"):
            self.bind(expected_submission="other")

    def test_wrong_team_rejected_casefolded(self):
        self.bind(expected_team="OPPONENT")
        with self.assertRaisesRegex(BindError, "team mismatch"):
            self.bind(expected_team="different")

    def test_identity_disagreement_rejected(self):
        value = replay()
        value["info"]["Agents"][1]["SubmissionId"] = "different"
        with self.assertRaisesRegex(BindError, "submission identity disagrees"):
            self.bind(value)

    def test_inconsistent_player_count_rejected(self):
        value = replay()
        value["steps"][1].pop()
        with self.assertRaisesRegex(BindError, "player count differs"):
            self.bind(value)

    def test_out_of_range_seat_rejected(self):
        with self.assertRaisesRegex(BindError, "outside player range"):
            self.bind(recorded_seat=2, expected_team=None, expected_submission=None)

    def test_missing_action_rejected(self):
        value = replay()
        del value["steps"][1][1]["action"]
        with self.assertRaisesRegex(BindError, "action must be an object"):
            self.bind(value)

    def test_duplicate_observation_step_rejected(self):
        value = replay()
        value["steps"][1][1]["observation"]["step"] = 0
        with self.assertRaisesRegex(BindError, "duplicate recorded observation step"):
            self.bind(value)

    def test_boolean_step_rejected(self):
        value = replay()
        value["steps"][0][1]["observation"]["step"] = False
        with self.assertRaisesRegex(BindError, "not boolean"):
            self.bind(value)

    def test_nonfinite_value_rejected(self):
        value = replay()
        value["steps"][1][1]["action"]["market"] = [["SELL", "WHEAT", float("nan")]]
        with self.assertRaisesRegex(BindError, "non-finite"):
            self.bind(value)

    def test_deterministic_trace_digest_for_key_order(self):
        a_manifest, _ = self.bind()
        value = replay()
        action = value["steps"][1][1]["action"]
        value["steps"][1][1]["action"] = {
            "market": action["market"], "hands": action["hands"], "farmer": action["farmer"]
        }
        b_manifest, _ = self.bind(value)
        self.assertEqual(a_manifest["trace"]["sha256"], b_manifest["trace"]["sha256"])

    def test_source_digest_is_exact_raw_bytes(self):
        value = replay()
        payload = raw(value)
        manifest, _ = bind_replay(
            payload, source_name="episode.json", expected_episode=108038484,
            recorded_seat=1, expected_team="Opponent", expected_submission=56158124,
        )
        self.assertEqual(hashlib.sha256(payload).hexdigest(), manifest["source"]["sha256"])
        self.assertEqual(len(payload), manifest["source"]["bytes"])

    def test_cli_writes_manifest_and_trace_fail_closed(self):
        here = os.path.dirname(__file__)
        with tempfile.TemporaryDirectory() as td:
            replay_path = os.path.join(td, "episode.json")
            out_path = os.path.join(td, "manifest.json")
            trace_path = os.path.join(td, "trace.json")
            with open(replay_path, "wb") as fh:
                fh.write(raw(replay()))
            cmd = [
                sys.executable, os.path.join(here, "bind_raw_replay.py"), replay_path,
                "--expected-episode", "108038484", "--recorded-seat", "1",
                "--expected-team", "Opponent", "--expected-submission", "56158124",
                "--output", out_path, "--trace-output", trace_path,
            ]
            first = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(0, first.returncode, first.stderr)
            with open(out_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            with open(trace_path, encoding="utf-8") as fh:
                trace = json.load(fh)
            self.assertEqual("108038484", manifest["episode_id"])
            self.assertEqual(2, len(trace))
            second = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(2, second.returncode)


if __name__ == "__main__":
    unittest.main()
