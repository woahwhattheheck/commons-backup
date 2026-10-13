"""Offline contract tests for the single-file Kaggle deployment agent."""
from __future__ import annotations

from enum import Enum
import importlib.util
from pathlib import Path
import sys
import types
import unittest

SOURCE = Path(__file__).with_name("kaggle_my_agent.py")


class FakeGameState(Enum):
    NOT_PLAYED = 0
    NOT_FINISHED = 1
    WIN = 2
    GAME_OVER = 3


class FakeGameAction(Enum):
    RESET = 0
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6
    ACTION7 = 7

    @classmethod
    def from_id(cls, value: int):
        return cls(value)

    def is_complex(self) -> bool:
        return self is FakeGameAction.ACTION6

    def set_data(self, data):
        self._test_data = dict(data)


class FakeFrameData:
    def __init__(
        self,
        frame,
        available_actions,
        state=FakeGameState.NOT_FINISHED,
        levels_completed=0,
    ):
        self.frame = frame
        self.available_actions = available_actions
        self.state = state
        self.levels_completed = levels_completed


class FakeAgent:
    def __init__(self, *args, **kwargs):
        self.game_id = kwargs.get("game_id", "test")

    @property
    def name(self):
        return self.__class__.__name__.lower()


def load_module():
    arcengine = types.ModuleType("arcengine")
    arcengine.FrameData = FakeFrameData
    arcengine.GameAction = FakeGameAction
    arcengine.GameState = FakeGameState
    sys.modules["arcengine"] = arcengine

    agents = types.ModuleType("agents")
    agent_mod = types.ModuleType("agents.agent")
    agent_mod.Agent = FakeAgent
    agents.agent = agent_mod
    sys.modules["agents"] = agents
    sys.modules["agents.agent"] = agent_mod

    spec = importlib.util.spec_from_file_location("sol_arc3_kaggle", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class KaggleSingleFileContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def make_agent(self):
        return self.mod.MyAgent(game_id="ls20-test")

    def test_required_class_name_and_base(self):
        self.assertEqual(self.mod.MyAgent.__name__, "MyAgent")
        self.assertTrue(issubclass(self.mod.MyAgent, FakeAgent))

    def test_single_file_has_no_local_project_imports(self):
        text = SOURCE.read_text()
        self.assertNotIn("from .arc3_baseline", text)
        self.assertNotIn("import arc3_baseline", text)
        self.assertIn("from agents.agent import Agent", text)

    def test_reset_contract(self):
        agent = self.make_agent()
        for state in (FakeGameState.NOT_PLAYED, FakeGameState.GAME_OVER):
            frame = FakeFrameData([[0]], [1], state=state)
            self.assertIs(agent.choose_action([], frame), FakeGameAction.RESET)

    def test_only_currently_available_action_is_selected(self):
        agent = self.make_agent()
        frame = FakeFrameData([[0, 0], [0, 0]], [4])
        self.assertIs(agent.choose_action([], frame), FakeGameAction.ACTION4)

    def test_available_actions_arrive_as_ints(self):
        agent = self.make_agent()
        frame = FakeFrameData([[0, 0], [0, 0]], [2, 5])
        first = agent.choose_action([], frame)
        second = agent.choose_action([], frame)
        self.assertEqual([first.value, second.value], [2, 5])

    def test_action6_data_is_bounded(self):
        agent = self.make_agent()
        grid = [[0] * 5 for _ in range(5)]
        grid[4][1] = 9
        frame = FakeFrameData(grid, [6])
        action = agent.choose_action([], frame)
        self.assertIs(action, FakeGameAction.ACTION6)
        data = getattr(action, "_test_data")
        self.assertEqual(data, {"x": 1, "y": 4})
        self.assertTrue(0 <= data["x"] <= 63 and 0 <= data["y"] <= 63)

    def test_latest_grid_from_frame_stack(self):
        normalized = self.mod.normalize_grid(
            [[[0, 0], [0, 0]], [[1, 0], [0, 0]]]
        )
        self.assertEqual(normalized, ((1, 0), (0, 0)))

    def test_invalid_color_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.normalize_grid([[16]])

    def test_reproducible_action_sequence(self):
        sequence = [
            FakeFrameData([[0, 0], [0, 0]], [1, 2, 6]),
            FakeFrameData([[1, 0], [0, 0]], [1, 2, 6]),
            FakeFrameData([[1, 0], [0, 2]], [1, 2, 6]),
            FakeFrameData([[1, 0], [0, 2]], [1, 2, 6]),
        ]

        def run():
            agent = self.make_agent()
            output = []
            for frame in sequence:
                action = agent.choose_action([], frame)
                data = getattr(action, "_test_data", None) if action is FakeGameAction.ACTION6 else None
                output.append((action.value, data))
            return output

        self.assertEqual(run(), run())

    def test_frontier_route_is_preserved_in_single_file(self):
        agent = self.make_agent()
        a = FakeFrameData([[0, 0]], [1, 2])
        b = FakeFrameData([[1, 0]], [1, 2])
        self.assertEqual(agent.choose_action([], a).value, 1)
        self.assertEqual(agent.choose_action([], b).value, 1)
        self.assertEqual(agent.choose_action([], a).value, 2)
        routed = agent.choose_action([], a)
        self.assertEqual(routed.value, 1)
        self.assertIn("frontier-route", routed.reasoning["reason"])

    def test_reasoning_is_structured(self):
        agent = self.make_agent()
        frame = FakeFrameData([[0]], [1])
        action = agent.choose_action([], frame)
        self.assertIsInstance(action.reasoning, dict)
        self.assertEqual(action.reasoning["policy"], "deterministic-frontier-model-v2")
        self.assertIn("known_edges", action.reasoning)
        self.assertIn("frontier_routes", action.reasoning)


if __name__ == "__main__":
    unittest.main(verbosity=2)
