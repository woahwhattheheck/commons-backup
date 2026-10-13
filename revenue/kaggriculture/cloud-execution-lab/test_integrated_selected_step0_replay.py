# SPDX-License-Identifier: Apache-2.0
"""Recovery contract for the module-level ordered selected entrypoint."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import integrated_selected as selected


class _StubAgent:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def act(self, observation, configuration=None):
        self.calls.append((deepcopy(observation), dict(configuration or {})))
        return {"instance": self.name, "calls": len(self.calls)}


class _FailingAgent(_StubAgent):
    def act(self, observation, configuration=None):
        self.calls.append((deepcopy(observation), dict(configuration or {})))
        raise RuntimeError("injected reset failure")


class OrderedEntrypointReplayTests(unittest.TestCase):
    def setUp(self):
        selected._INSTANCE = None
        selected._LAST_STEP = None

    def tearDown(self):
        selected._INSTANCE = None
        selected._LAST_STEP = None

    def test_exact_step_zero_replay_reuses_instance_and_backward_step_resets(self):
        created = []

        def make_stub():
            stub = _StubAgent(f"agent-{len(created)}")
            created.append(stub)
            return stub

        with patch.object(selected, "make_agent", side_effect=make_stub) as factory:
            first = selected.agent({"step": 0}, {})
            replay = selected.agent({"step": 0}, {})
            forward = selected.agent({"step": 3}, {})
            same_nonzero = selected.agent({"step": 3}, {})
            rewind = selected.agent({"step": 2}, {})

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(first["instance"], "agent-0")
        self.assertEqual(replay["instance"], "agent-0")
        self.assertEqual(forward["instance"], "agent-0")
        self.assertEqual(same_nonzero["instance"], "agent-0")
        self.assertEqual(rewind["instance"], "agent-1")
        self.assertEqual(len(created[0].calls), 4)
        self.assertEqual(len(created[1].calls), 1)
        self.assertEqual(selected._LAST_STEP, 2)

    def test_failed_backstep_does_not_consume_reset_boundary(self):
        old = _StubAgent("old")
        failed = _FailingAgent("failed-reset")
        retry = _StubAgent("retry-reset")
        selected._INSTANCE = old
        selected._LAST_STEP = 5

        with patch.object(selected, "make_agent", side_effect=[failed, retry]) as factory:
            with self.assertRaisesRegex(RuntimeError, "injected reset failure"):
                selected.agent({"step": 0}, {})
            self.assertIs(selected._INSTANCE, failed)
            self.assertEqual(selected._LAST_STEP, 5)

            recovered = selected.agent({"step": 0}, {})

        self.assertEqual(factory.call_count, 2)
        self.assertIs(selected._INSTANCE, retry)
        self.assertEqual(recovered["instance"], "retry-reset")
        self.assertEqual(len(failed.calls), 1)
        self.assertEqual(len(retry.calls), 1)
        self.assertEqual(selected._LAST_STEP, 0)


if __name__ == "__main__":
    unittest.main()
