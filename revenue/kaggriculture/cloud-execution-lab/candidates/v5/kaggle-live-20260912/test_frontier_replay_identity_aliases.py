#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import frontier_replay_profile as p


PINNED = 56156662
OTHER = 56161578
EPISODE = 108115160


def raw(obj):
    return json.dumps(obj, sort_keys=True).encode()


def row(action0=None, action1=None):
    return [{"action": action0}, {"action": action1}]


def pack():
    return {
        "frontier_targets": [
            {"rank": 1, "rated_submission_id": PINNED},
            {"rank": 2, "rated_submission_id": OTHER},
        ]
    }


def identity():
    return {
        "episode": {
            "id": EPISODE,
            "agents": [
                {"submissionId": PINNED},
                {"submissionId": OTHER},
            ],
        }
    }


def replay():
    return {"id": EPISODE, "steps": [row(), row()]}


def build(replay_obj=None, identity_obj=None):
    replay_obj = replay() if replay_obj is None else replay_obj
    identity_obj = identity() if identity_obj is None else identity_obj
    frontier_pack = pack()
    return p.build_profile(
        replay_obj,
        raw(replay_obj),
        frontier_pack,
        raw(frontier_pack),
        identity_obj,
        raw(identity_obj),
        submission_id=PINNED,
        seat=0,
    )


class ReplayIdentityAliasTest(unittest.TestCase):
    def test_replay_episode_aliases_must_agree(self):
        bad = replay()
        bad["episode_id"] = EPISODE + 1
        with self.assertRaisesRegex(p.ReplayProfileError, "replay episode id aliases disagree"):
            build(replay_obj=bad)

    def test_present_null_replay_episode_alias_is_not_absent(self):
        bad = replay()
        bad["episode_id"] = None
        with self.assertRaisesRegex(p.ReplayProfileError, "episode_id must be a plain integer"):
            build(replay_obj=bad)

    def test_identity_episode_aliases_must_agree(self):
        bad = identity()
        bad["episode"]["episode_id"] = EPISODE + 1
        with self.assertRaisesRegex(p.ReplayProfileError, "identity episode id aliases disagree"):
            build(identity_obj=bad)

    def test_agent_submission_aliases_must_agree(self):
        bad = identity()
        bad["episode"]["agents"][0]["submission_id"] = OTHER
        with self.assertRaisesRegex(p.ReplayProfileError, "submission id aliases disagree"):
            build(identity_obj=bad)

    def test_exact_redundant_aliases_remain_valid(self):
        replay_obj = replay()
        replay_obj["episode_id"] = EPISODE
        replay_obj["episodeId"] = EPISODE
        identity_obj = identity()
        identity_obj["episode"]["episode_id"] = EPISODE
        identity_obj["episode"]["agents"][0]["submission_id"] = PINNED
        profile = build(replay_obj=replay_obj, identity_obj=identity_obj)
        self.assertEqual(profile["identity"]["episode_id"], EPISODE)
        self.assertEqual(profile["identity"]["submission_id"], PINNED)


if __name__ == "__main__":
    unittest.main()
