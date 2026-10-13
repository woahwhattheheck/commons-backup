from __future__ import annotations

from enum import Enum
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

from build_kaggle_v3 import build

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "kaggle_my_agent.py"
if not BASE.exists():
    BASE = HERE / "kaggle_my_agent.py"  # local authoring harness
EXTENSION = HERE / "arc3_object_transfer.py"


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

    def set_data(self, data):
        self._test_data = dict(data)


class FakeFrameData:
    def __init__(self, frame, available_actions, state=FakeGameState.NOT_FINISHED, levels_completed=0):
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


def install_stubs() -> None:
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


def load_generated(path: Path):
    install_stubs()
    spec = importlib.util.spec_from_file_location("sol_arc3_object_v3_generated", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def row(player_x: int, width: int = 8):
    values = [0] * width
    values[player_x] = 1
    values[-1] = 8
    return [values]


class KaggleV3BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tempdir.name) / "my_agent.py"
        build(BASE, EXTENSION, cls.output)
        cls.text = cls.output.read_text()
        cls.mod = load_generated(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def agent(self):
        return self.mod.MyAgent(game_id="ls20-test")

    def test_generated_file_is_self_contained(self):
        self.assertNotIn("from arc3_baseline import", self.text)
        self.assertNotIn("from arc3_object_transfer import", self.text)
        self.assertIn("class MyAgent(_BaseMyAgent):", self.text)

    def test_reset_contract(self):
        agent = self.agent()
        frame = FakeFrameData([[0]], [1], state=FakeGameState.GAME_OVER)
        self.assertIs(agent.choose_action([], frame), FakeGameAction.RESET)

    def test_object_transfer_is_live_in_generated_adapter(self):
        agent = self.agent()
        a = FakeFrameData(row(2), [1, 2])
        b = FakeFrameData(row(3), [1, 2])
        self.assertEqual(agent.choose_action([], a).value, 1)
        self.assertEqual(agent.choose_action([], b).value, 2)
        decision = agent.choose_action([], a)
        self.assertEqual(decision.value, 2)
        self.assertEqual(decision.reasoning["policy"], "object-transfer-frontier-v3")
        self.assertIn("object-frontier", decision.reasoning["reason"])

    def test_action6_salience_and_bounds_are_preserved(self):
        agent = self.agent()
        grid = [[0] * 5 for _ in range(5)]
        grid[4][1] = 9
        action = agent.choose_action([], FakeFrameData(grid, [6]))
        self.assertIs(action, FakeGameAction.ACTION6)
        data = getattr(action, "_test_data")
        self.assertEqual(data, {"x": 1, "y": 4})
        self.assertTrue(0 <= data["x"] <= 63 and 0 <= data["y"] <= 63)

    def test_deterministic_replay(self):
        sequence = [
            FakeFrameData(row(2), [1, 2, 3, 4]),
            FakeFrameData(row(3), [1, 2, 3, 4]),
            FakeFrameData(row(2), [1, 2, 3, 4]),
            FakeFrameData(row(1), [1, 2, 3, 4]),
        ]
        def run():
            agent = self.agent()
            return [agent.choose_action([], frame).value for frame in sequence]
        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
