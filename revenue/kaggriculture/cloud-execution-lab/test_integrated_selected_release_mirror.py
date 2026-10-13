# SPDX-License-Identifier: Apache-2.0
"""Package-source guard for the ordered selected module entrypoint."""
import ast
from pathlib import Path
import unittest

import build_integrated


ROOT = Path(__file__).resolve().parent
MIRROR = ROOT / "reference/titan-current/latest/integrated_selected.py"


class _StubAgent:
    def __init__(self, name, *, fail_step=None):
        self.name = name
        self.fail_step = fail_step
        self.calls = []

    def act(self, observation, configuration=None):
        step = observation["step"]
        self.calls.append(step)
        if step == self.fail_step:
            raise RuntimeError("planned reset failure")
        return {"instance": self.name, "calls": len(self.calls)}


def _load_packaged_entrypoint():
    """Execute only the packaged module's state + entrypoint definition."""
    parsed = ast.parse(MIRROR.read_text(encoding="utf-8"), filename=str(MIRROR))
    body = []
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & {"_INSTANCE", "_LAST_STEP"}:
                body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "agent":
            body.append(node)
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)

    created = []
    plans = [
        _StubAgent("agent-0"),
        _StubAgent("agent-1", fail_step=2),
        _StubAgent("agent-2"),
    ]

    def make_agent():
        agent = plans[len(created)]
        created.append(agent)
        return agent

    namespace = {
        "absolute_step": lambda observation, configuration: observation["step"],
        "make_agent": make_agent,
    }
    exec(compile(module, str(MIRROR), "exec"), namespace)
    return namespace, created


class IntegratedSelectedReleaseMirrorTests(unittest.TestCase):
    def test_release_builder_uses_guarded_mirror(self):
        self.assertEqual(
            build_integrated.source_files()["integrated_selected.py"],
            "reference/titan-current/latest/integrated_selected.py",
        )

    def test_packaged_entrypoint_replay_and_failed_reset_contract(self):
        namespace, created = _load_packaged_entrypoint()
        entrypoint = namespace["agent"]

        first = entrypoint({"step": 0}, {})
        replay = entrypoint({"step": 0}, {})
        forward = entrypoint({"step": 3}, {})
        with self.assertRaisesRegex(RuntimeError, "planned reset failure"):
            entrypoint({"step": 2}, {})
        retry = entrypoint({"step": 2}, {})

        self.assertEqual(first["instance"], "agent-0")
        self.assertEqual(replay["instance"], "agent-0")
        self.assertEqual(forward["instance"], "agent-0")
        self.assertEqual(retry["instance"], "agent-2")
        self.assertEqual([agent.calls for agent in created], [[0, 0, 3], [2], [2]])
        self.assertEqual(namespace["_LAST_STEP"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
