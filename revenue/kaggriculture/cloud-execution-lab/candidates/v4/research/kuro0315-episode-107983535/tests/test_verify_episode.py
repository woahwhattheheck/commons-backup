import json, sys, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from verify_episode import ReplayError, TARGET_EPISODE_ID, verify_replay_bytes

def fixture(ep=TARGET_EPISODE_ID, r0=1000, r1=2487):
    return {
        "id":"uuid-not-episode",
        "info":{"EpisodeId": ep, "TeamNames":["ours","kuro0315"]},
        "steps":[
            [{"observation":{"player":0},"reward":0},{"observation":{"player":1},"reward":0}],
            [{"observation":{"player":0},"reward":r0},{"observation":{"player":1},"reward":r1}],
        ],
    }
def raw(x): return json.dumps(x,sort_keys=True,separators=(",",":")).encode()

class CustodyTests(unittest.TestCase):
    def test_exact_replay_and_claimed_margin(self):
        r=verify_replay_bytes(raw(fixture()),candidate_seat=0,expected_margin=-1487)
        self.assertEqual(r["episode_id"], TARGET_EPISODE_ID)
        self.assertEqual(r["candidate_margin"], -1487.0)
        self.assertIsNone(r["root_cause"])
        self.assertFalse(r["authority"]["root_cause_established"])
    def test_deterministic(self):
        b=raw(fixture())
        self.assertEqual(verify_replay_bytes(b),verify_replay_bytes(b))
    def test_wrong_episode_rejected(self):
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(fixture(1)))
    def test_conflicting_episode_ids_rejected(self):
        x=fixture(); x["episode_id"]=TARGET_EPISODE_ID+1
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_uuid_not_misread_as_episode(self):
        x=fixture(); del x["info"]["EpisodeId"]
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_boolean_episode_rejected(self):
        x=fixture(); x["info"]["EpisodeId"]=True
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_bad_player_binding_rejected(self):
        x=fixture(); x["steps"][1][1]["observation"]["player"]=0
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_bad_shape_rejected(self):
        x=fixture(); x["steps"][0].pop()
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_nonfinite_reward_rejected(self):
        x=fixture(); x["steps"][-1][0]["reward"]=float("nan")
        with self.assertRaises(ReplayError): verify_replay_bytes(raw(x))
    def test_margin_mismatch_rejected(self):
        with self.assertRaises(ReplayError):
            verify_replay_bytes(raw(fixture()),candidate_seat=0,expected_margin=-1)
    def test_expected_margin_needs_seat(self):
        with self.assertRaises(ReplayError):
            verify_replay_bytes(raw(fixture()),expected_margin=-1487)
    def test_bad_candidate_seat_rejected(self):
        with self.assertRaises(ReplayError):
            verify_replay_bytes(raw(fixture()),candidate_seat=2)

if __name__=="__main__": unittest.main()
