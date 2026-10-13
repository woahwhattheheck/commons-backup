import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src" / "hosted_recent_report.py"
spec = importlib.util.spec_from_file_location("reporter", MODULE)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
TEAM = "Our team"


def replay(episode=10, seat=0, rewards=(10, 8), statuses=("DONE", "DONE")):
    names = [TEAM, "Opponent"] if seat == 0 else ["Opponent", TEAM]
    states = [{"status": status, "reward": reward} for status, reward in zip(statuses, rewards)]
    return {"name": "kaggriculture", "module_version": "fixture", "configuration": {"actTimeout": 1},
            "info": {"EpisodeId": episode, "TeamNames": names, "Agents": [{"Name": n} for n in names]},
            "statuses": list(statuses), "rewards": list(rewards),
            "steps": [[{"status": "ACTIVE", "reward": 0}, {"status": "ACTIVE", "reward": 0}], states]}


def feed(ids, submission=100):
    return {"schema_version": 1, "as_of": "2026-09-08T10:00:00Z", "own_submission_id": submission,
            "source_reference": "test-fixture-not-provider-data", "latest_completed_episode_ids_newest_first": ids,
            "episodes": [{"episode_id": i, "own_submission_id": submission} for i in ids]}


class ReporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def save(self, name, value):
        p = self.root / name
        p.write_text(json.dumps(value))
        return p

    def run_report(self, **kwargs):
        return r.build_report([self.root], TEAM, **kwargs)

    def test_seat_one_win_is_not_reversed(self):
        self.save("10.json", replay(seat=1, rewards=(8, 10)))
        result = self.run_report()
        self.assertEqual(result["sample"]["wins"], 1)
        self.assertEqual(result["episodes"][0]["own_seat"], 1)
        self.assertEqual(result["episodes"][0]["cash_margin"], 2)

    def test_same_team_on_both_seats_is_ambiguous(self):
        d = replay(); d["info"]["TeamNames"] = [TEAM, TEAM]
        self.save("10.json", d)
        self.assertEqual(self.run_report()["sample"]["episodes"], 0)

    def test_display_names_must_agree(self):
        d = replay(); d["info"]["Agents"][0]["Name"] = "Different"
        self.save("10.json", d)
        self.assertIn("disagree", self.run_report()["input_issues"][0]["error"])

    def test_missing_team_is_not_assumed_seat_zero(self):
        self.save("10.json", replay())
        x = r.build_report([self.root], "Absent")
        self.assertFalse(x["episodes"])

    def test_filename_id_mismatch_rejected(self):
        self.save("11.json", replay(10))
        self.assertIn("filename", self.run_report()["input_issues"][0]["error"])

    def test_byte_and_whitespace_duplicates_count_once(self):
        d = replay(); self.save("10.json", d)
        (self.root / "10(1).json").write_text(json.dumps(d, indent=3))
        x = self.run_report()
        self.assertEqual(x["sample"]["episodes"], 1)
        self.assertEqual(len(x["episodes"][0]["sources"]), 2)
        self.assertFalse(x["input_issues"])

    def test_conflicting_duplicate_is_excluded_not_last_writer_wins(self):
        self.save("10.json", replay())
        self.save("10(1).json", replay(rewards=(20, 8)))
        x = self.run_report()
        self.assertFalse(x["episodes"])
        self.assertIn("conflicting", x["input_issues"][0]["error"])

    def test_wrong_episode_log_never_substituted(self):
        self.save("10.json", replay())
        self.save("11-0.json", [[{"duration": .1}]])
        x = self.run_report()
        self.assertEqual(x["episodes"][0]["own_log"]["status"], "missing")
        self.assertIn("orphan", x["input_issues"][0]["error"])

    def test_wrong_seat_log_never_substituted(self):
        self.save("10.json", replay(seat=1))
        self.save("10-0.json", [[{"duration": .1}]])
        self.assertEqual(self.run_report()["episodes"][0]["own_log"]["status"], "missing")

    def test_own_log_stats_and_timeout_flag(self):
        self.save("10.json", replay())
        self.save("10-0.json", [[{"duration": .2, "stderr": "diagnostic"}, {"duration": 1.2}]])
        log = self.run_report()["episodes"][0]["own_log"]
        self.assertEqual(log["duration_samples"], 2)
        self.assertAlmostEqual(log["p50_seconds"], .7)
        self.assertTrue(log["frame_count_matches_replay"])
        self.assertTrue(log["max_recorded_duration_exceeds_act_timeout"])
        self.assertEqual(log["stderr_nonempty_entries"], 1)

    def test_log_frame_mismatch_is_explicit(self):
        self.save("10.json", replay()); self.save("10-0.json", [])
        x = self.run_report()
        self.assertFalse(x["episodes"][0]["own_log"]["frame_count_matches_replay"])
        self.assertIn("Private hosted", r.markdown(x))

    def test_nan_json_rejected(self):
        (self.root / "10-0.json").write_text('[[{"duration":NaN}]]')
        x = self.run_report()
        self.assertIn("non-finite", x["input_issues"][0]["error"])

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(r.InputError):
            r.strict_json(b'{"a":1,"a":2}')

    def test_negative_duration_rejected(self):
        with self.assertRaises(r.InputError):
            r.parse_log([[{"duration": -.1}]])

    def test_reward_conflict_rejected(self):
        d = replay(); d["rewards"] = [0, 20]
        with self.assertRaises(r.InputError):
            r.parse_replay(d, TEAM, 10)

    def test_status_conflict_rejected(self):
        d = replay(); d["statuses"] = ["ACTIVE", "DONE"]
        with self.assertRaises(r.InputError):
            r.parse_replay(d, TEAM, 10)

    def test_nonstring_status_is_input_error(self):
        d = replay(); d["steps"][0][0]["status"] = {}
        with self.assertRaises(r.InputError):
            r.parse_replay(d, TEAM, 10)

    def test_nonterminal_scores_do_not_become_win(self):
        self.save("10.json", replay(statuses=("ACTIVE", "ACTIVE")))
        x = self.run_report()
        self.assertEqual(x["sample"]["wins"], 0)
        self.assertEqual(x["sample"]["unscored_or_incomplete"], 1)

    def test_fault_terminal_with_numeric_reward_is_not_silently_dropped(self):
        self.save("10.json", replay(rewards=(0, 10), statuses=("TIMEOUT", "DONE")))
        x = self.run_report()
        self.assertEqual(x["sample"]["losses"], 1)
        self.assertEqual(x["sample"]["own_fault_status_episodes"], 1)

    def test_no_latest_claim_from_episode_ids(self):
        for i in range(10, 40):
            self.save(f"{i}.json", replay(i))
        x = self.run_report()
        self.assertEqual(x["latest_windows"]["20"]["status"], "withheld")

    def test_explicit_order_used_not_sorted_id(self):
        self.save("10.json", replay(10, rewards=(20, 10)))
        self.save("11.json", replay(11, rewards=(0, 10)))
        x = self.run_report(windows=[1, 2], feed=feed([10, 11]))
        self.assertEqual(x["latest_windows"]["1"]["wins"], 1)
        self.assertEqual(x["latest_windows"]["1"]["episode_ids_newest_first"], [10])

    def test_missing_replay_withholds_window(self):
        self.save("10.json", replay(10))
        x = self.run_report(windows=[2], feed=feed([11, 10]))
        self.assertEqual(x["latest_windows"]["2"]["missing_replay_ids"], [11])

    def test_missing_submission_binding_withholds_window(self):
        self.save("10.json", replay(10)); f = feed([10]); f["episodes"] = []
        x = self.run_report(windows=[1], feed=f)
        self.assertEqual(x["latest_windows"]["1"]["submission_mismatch_or_missing_metadata_ids"], [10])

    def test_mixed_submission_withholds_window(self):
        self.save("10.json", replay(10)); f = feed([10]); f["episodes"][0]["own_submission_id"] = 101
        self.assertEqual(self.run_report(windows=[1], feed=f)["latest_windows"]["1"]["status"], "withheld")

    def test_short_feed_withholds_not_partial_percentage(self):
        self.save("10.json", replay(10))
        self.assertEqual(self.run_report(windows=[20], feed=feed([10]))["latest_windows"]["20"]["status"], "withheld")

    def test_duplicate_feed_ids_rejected(self):
        with self.assertRaises(r.InputError):
            self.run_report(feed=feed([10, 10]))

    def test_naive_feed_timestamp_rejected(self):
        f = feed([10]); f["as_of"] = "2026-09-08T10:00:00"
        with self.assertRaises(r.InputError):
            self.run_report(feed=f)

    def test_feed_order_conflicting_with_timestamps_rejected(self):
        f = feed([10, 11])
        f["episodes"][0]["finished_at"] = "2026-09-08T08:00:00Z"
        f["episodes"][1]["finished_at"] = "2026-09-08T09:00:00Z"
        with self.assertRaises(r.InputError):
            self.run_report(feed=f)

    def test_completion_after_feed_capture_rejected(self):
        f = feed([10]); f["episodes"][0]["finished_at"] = "2026-09-08T11:00:00Z"
        with self.assertRaises(r.InputError):
            self.run_report(feed=f)

    def test_conflicting_logs_excluded_without_dropping_game(self):
        self.save("10.json", replay())
        self.save("10-0.json", [[{"duration": .1}]])
        self.save("10-0(1).json", [[{"duration": .2}]])
        x = self.run_report()
        self.assertEqual(x["sample"]["episodes"], 1)
        self.assertEqual(x["episodes"][0]["own_log"]["status"], "conflicting_sources")

    def test_fault_with_null_reward_is_retained_unscored(self):
        self.save("10.json", replay(rewards=(None, 10), statuses=("ERROR", "DONE")))
        x = self.run_report()
        self.assertEqual(x["sample"]["episodes"], 1)
        self.assertEqual(x["sample"]["unscored_or_incomplete"], 1)
        self.assertEqual(x["sample"]["own_fault_status_episodes"], 1)

    def test_ratings_missing_not_invented(self):
        self.save("10.json", replay())
        self.assertEqual(self.run_report()["sample"]["opponent_rating_available"], 0)

    def test_window_must_be_positive(self):
        with self.assertRaises(r.InputError):
            self.run_report(windows=[0])

    def test_empty_selection_is_not_success(self):
        p = subprocess.run([sys.executable, str(MODULE), str(self.root), "--team", TEAM, "--output", str(self.root/'out.json')], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_cli_does_not_overwrite_previous_report(self):
        self.save("10.json", replay()); out = self.root / "out.json"; out.write_text("prior")
        p = subprocess.run([sys.executable, str(MODULE), str(self.root), "--team", TEAM, "--output", str(out)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(out.read_text(), "prior")

    def test_cli_success_writes_json_and_markdown(self):
        self.save("10.json", replay())
        out, md = self.root / "out.json", self.root / "out.md"
        p = subprocess.run([sys.executable, str(MODULE), str(self.root), "--team", TEAM, "--output", str(out), "--markdown", str(md)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(out.read_text())["sample"]["wins"], 1)
        self.assertIn("not the current", md.read_text())


if __name__ == '__main__':
    unittest.main()
