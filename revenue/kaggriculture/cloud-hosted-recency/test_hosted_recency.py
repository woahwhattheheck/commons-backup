"""Synthetic parser tests; these are not hosted games or performance samples."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from hosted_recency import analyze, main, normalize, timestamp


def replay(episode=100, rewards=(10, 5), statuses=("DONE", "DONE"), frames=3):
    states = []
    for i in range(frames):
        last = i == frames - 1
        states.append([dict(observation={"step": i}, action={}, info={},
                            status=statuses[p] if last else "ACTIVE",
                            reward=rewards[p] if last else 0) for p in range(2)])
    return dict(name="kaggriculture", info={"EpisodeId":episode,"TeamNames":["A","B"]},
                configuration={"episodeSteps":3}, steps=states,
                statuses=list(statuses), rewards=list(rewards))


class RecencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.m = dict(schema_version=1, submission_id=7, identity_evidence="synthetic test binding",
                      coverage_complete=False, entries=[])

    def add(self, data=None, **metadata):
        data = replay() if data is None else data
        path = self.root / f"replay-{len(self.m['entries'])}.json"
        path.write_text(json.dumps(data))
        self.m["entries"].append(dict(replay=path.name, own_seat=0, **metadata))
        return path

    def run_report(self):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.m))
        return analyze(path)

    def row(self, data=None, **metadata):
        return normalize(data or replay(), dict(own_seat=0, **metadata), self.m, {"sha256":"test"})

    def test_win_and_round_count(self):
        r = self.row()
        self.assertEqual((r["outcome"], r["decision_rounds"], r["margin"]), ("W",2,5))

    def test_seat_reversal(self):
        r = normalize(replay(), {"own_seat":1}, self.m, {})
        self.assertEqual((r["outcome"],r["margin"],r["opponent_name"]),("L",-5,"A"))

    def test_tie(self):
        self.add(replay(rewards=(7,7)))
        stats = self.run_report()["available_completed"]
        self.assertEqual((stats["ties"],stats["win_rate"],stats["result_score_rate"]),(1,0,0.5))

    def test_missing_seat_not_guessed_from_name(self):
        with self.assertRaises(ValueError): normalize(replay(), {}, self.m, {})

    def test_boolean_seat_rejected(self):
        with self.assertRaises(ValueError): normalize(replay(), {"own_seat":True}, self.m, {})

    def test_seat_out_of_range(self):
        with self.assertRaises(ValueError): normalize(replay(), {"own_seat":2}, self.m, {})

    def test_episode_binding_mismatch(self):
        with self.assertRaises(ValueError): self.row(episode_id=101)

    def test_uuid_does_not_supply_episode_id(self):
        d = replay(); del d["info"]["EpisodeId"]; d["id"] = "1234"
        with self.assertRaises(ValueError): self.row(d)

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError): timestamp("2026-01-01T12:00:00","time")

    def test_timezones_normalize(self):
        self.assertEqual(timestamp("2026-01-01T06:00:00-06:00","time"),
                         timestamp("2026-01-01T12:00:00Z","time"))

    def test_future_timestamp_rejected(self):
        self.m["as_of"]="2026-01-01T00:00:00Z"
        with self.assertRaises(ValueError): self.row(completed_at="2026-01-02T00:00:00Z",metadata_evidence="test")

    def test_timestamp_requires_source(self):
        with self.assertRaises(ValueError): self.row(completed_at="2026-01-01T00:00:00Z")

    def test_rating_requires_source(self):
        with self.assertRaises(ValueError): self.row(opponent_rating_before=2100)

    def test_nonfinite_reward_rejected(self):
        with self.assertRaises(ValueError): self.row(replay(rewards=(float("inf"),5)))

    def test_boolean_reward_rejected(self):
        with self.assertRaises(ValueError): self.row(replay(rewards=(True,5)))

    def test_null_completed_reward_rejected(self):
        with self.assertRaises(ValueError): self.row(replay(rewards=(None,5)))

    def test_reward_disagreement_rejected(self):
        d=replay(); d["rewards"][0]=77
        with self.assertRaises(ValueError): self.row(d)

    def test_status_disagreement_rejected(self):
        d=replay(); d["statuses"][0]="ACTIVE"
        with self.assertRaises(ValueError): self.row(d)

    def test_partial_cash_is_not_final_score(self):
        r=self.row(replay(statuses=("ACTIVE","ACTIVE"),frames=2))
        self.assertEqual(r["classification"],"incomplete")
        self.assertIsNone(r["own_cash"])
        self.assertIsNone(r["outcome"])

    def test_early_done_is_not_full_game(self):
        self.assertEqual(self.row(replay(frames=2))["classification"],"incomplete")

    def test_own_runtime_failure_is_not_strategy_loss(self):
        r=self.row(replay(statuses=("TIMEOUT","DONE"),rewards=(None,8)))
        self.assertEqual(r["classification"],"runtime_failure")
        self.assertIsNone(r["outcome"])
        self.assertEqual(r["runtime_failures"],[{"seat":0,"status":"TIMEOUT"}])

    def test_opponent_runtime_failure_is_not_strategy_win(self):
        self.assertIsNone(self.row(replay(statuses=("DONE","ERROR"),rewards=(8,None)))["outcome"])

    def test_internal_error_not_hidden_by_done(self):
        d=replay();d["steps"][1][0]["status"]="INVALID"
        self.assertEqual(self.row(d)["classification"],"runtime_failure")

    def test_skipped_step_rejected(self):
        d=replay();d["steps"][1][0]["observation"]["step"]=5
        with self.assertRaises(ValueError): self.row(d)

    def test_wrong_seat_count_rejected(self):
        d=replay();d["steps"][1].pop()
        with self.assertRaises(ValueError): self.row(d)

    def test_duplicate_upload_counted_once(self):
        self.add();self.add()
        r=self.run_report()
        self.assertEqual((r["input_count"],r["unique_episode_seats"],r["duplicate_snapshots"]),(2,1,1))
        self.assertEqual(len(r["records"][0]["sources"]),2)

    def test_distinct_episode_same_scores_not_deduped(self):
        self.add(); self.add(replay(episode=101))
        self.assertEqual(self.run_report()["available_completed"]["n"],2)

    def test_partial_is_superseded_not_added_as_failure(self):
        self.add(replay(statuses=("ACTIVE","ACTIVE"),frames=2));self.add()
        r=self.run_report()
        self.assertEqual(r["classifications"],{"completed":1})
        self.assertEqual(r["records"][0]["superseded_partial_snapshots"],1)

    def test_contradictory_terminal_snapshots_quarantined(self):
        self.add();self.add(replay(rewards=(1,5)))
        r=self.run_report()
        self.assertEqual(len(r["conflicts"]),1)
        self.assertEqual(r["available_completed"]["n"],0)

    def test_timestamp_disagreement_quarantined(self):
        for date in ("2026-01-01T00:00:00Z","2026-01-02T00:00:00Z"):
            self.add(completed_at=date,metadata_evidence="test")
        self.assertEqual(len(self.run_report()["conflicts"]),1)

    def test_metadata_enrichment_of_duplicate(self):
        self.add();self.add(completed_at="2026-01-01T00:00:00Z",metadata_evidence="test")
        r=self.run_report()
        self.assertEqual((r["available_completed"]["n"],r["missing_completion_times"]),(1,0))

    def test_missing_file_retained_and_blocks_full_coverage(self):
        path=self.add();path.unlink()
        r=self.run_report()
        self.assertEqual(len(r["rejected_inputs"]),1)
        self.assertFalse(r["latest_normal_completion_windows"]["20"]["supported"])

    def test_missing_time_never_ordered_by_filename_or_episode(self):
        self.add(replay(episode=999));self.add(replay(episode=1))
        r=self.run_report()
        self.assertEqual(r["missing_completion_times"],2)
        self.assertIsNone(r["latest_normal_completion_windows"]["20"]["statistics"])

    def full_history(self,n=51):
        self.m.update(coverage_complete=True,coverage_evidence="synthetic fixture, not provider history",
                      as_of="2026-01-02T00:00:00Z")
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        for i in range(n):
            self.add(replay(episode=500-i,rewards=(0,1) if i<31 else (2,1)),
                     completed_at=(start+timedelta(minutes=i)).isoformat(),metadata_evidence="test")

    def test_windows_use_completion_order_not_episode_id(self):
        self.full_history()
        r=self.run_report()
        w=r["latest_normal_completion_windows"]["20"]
        self.assertTrue(w["supported"])
        self.assertEqual((w["statistics"]["n"],w["statistics"]["wins"]),(20,20))
        self.assertEqual(w["episode_ids"][0],450)
        self.assertEqual(r["latest_normal_completion_windows"]["50"]["statistics"]["losses"],30)

    def test_many_rows_do_not_prove_coverage(self):
        self.full_history();self.m["coverage_complete"]=False
        self.assertFalse(self.run_report()["latest_normal_completion_windows"]["20"]["supported"])

    def test_boundary_timestamp_tie_not_arbitrarily_broken(self):
        self.full_history(21)
        self.m["entries"][0]["completed_at"]=self.m["entries"][1]["completed_at"]
        w=self.run_report()["latest_normal_completion_windows"]["20"]
        self.assertFalse(w["supported"])
        self.assertEqual(w["statistics"]["n"],21)

    def test_declared_coverage_requires_source_and_asof(self):
        self.add();self.m["coverage_complete"]=True
        with self.assertRaises(ValueError): self.run_report()

    def test_boolean_coverage_not_string(self):
        self.add();self.m["coverage_complete"]="true"
        with self.assertRaises(ValueError): self.run_report()

    def test_bands_only_from_supplied_ratings(self):
        for i,rating in enumerate((1999,2000,2499.99999,2500,None)):
            self.add(replay(episode=100+i),opponent_rating_before=rating,metadata_evidence="test")
        bands=self.run_report()["by_supplied_rating_band"]
        self.assertEqual({k:v["n"] for k,v in bands.items()},
                         {"below_2000":1,"2000_to_below_2500":2,"2500_and_above":1,"unknown":1})

    def test_cli_writes_real_report(self):
        self.add();self.run_report()
        out=self.root/"report.json"
        self.assertEqual(main([str(self.root/"manifest.json"),"--output",str(out)]),0)
        self.assertEqual(json.loads(out.read_text())["available_completed"]["wins"],1)

    def test_cli_does_not_overwrite_replay(self):
        path=self.add();self.run_report();before=path.read_bytes()
        self.assertEqual(main([str(self.root/"manifest.json"),"--output",str(path)]),2)
        self.assertEqual(path.read_bytes(),before)

    def test_cli_exit_one_preserves_partial_report(self):
        self.add();path=self.add();path.unlink();self.run_report()
        out=self.root/"report.json"
        self.assertEqual(main([str(self.root/"manifest.json"),"--output",str(out)]),1)
        self.assertEqual(json.loads(out.read_text())["available_completed"]["n"],1)

    def test_nonfinite_json_is_rejected_input(self):
        p=self.add();p.write_text(p.read_text().replace('10','NaN',1))
        self.assertEqual(len(self.run_report()["rejected_inputs"]),1)

    def test_missing_info_is_rejected_input(self):
        d=replay();d["info"]=None;self.add(d)
        self.assertEqual(len(self.run_report()["rejected_inputs"]),1)

    def test_conflicting_seat_bindings_are_not_two_games(self):
        self.add();self.add();self.m["entries"][1]["own_seat"]=1
        r=self.run_report()
        self.assertEqual(r["available_completed"]["n"],0)
        self.assertEqual(len(r["conflicts"]),2)

    def test_output_hardlink_does_not_modify_input(self):
        path=self.add();self.run_report();before=path.read_bytes()
        out=self.root/"hardlink.json";out.hardlink_to(path)
        self.assertEqual(main([str(self.root/"manifest.json"),"--output",str(out)]),2)
        self.assertEqual(path.read_bytes(),before)

    def test_invalid_opponent_name_is_rejected(self):
        d=replay();d["info"]["TeamNames"][1]=["bad"]
        with self.assertRaises(ValueError): self.row(d)


if __name__=="__main__":
    unittest.main()
