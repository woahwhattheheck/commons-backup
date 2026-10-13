# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import types
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import materialize_r04_retry as retry


PASS_SOURCE = b'PASS = {"farmer": ["PASS"], "hands": [], "market": []}\n'
OVERLAY = b"""
_ArleneAgent = Agent
class Agent(_ArleneAgent):
    def __init__(self):
        super().__init__()
        import r04_full_router as r04
        from r01_tapes import load_tapes
        self.R = {'R04-' + str(i): tape for i, tape in enumerate(load_tapes())}
        self.cur = 'R04-0'
        self._fs = None
        self._fs_for = None
        self._r04 = r04
        self._policy = r04.install(horizon=8, opening=0, row_order=True,
            evening_flush=True, sale_fertilizer=True, cattle_early=False,
            kill_late_water=False, strawberry_endgame=False,
            no_late_sale_advance=True, no_late_sale_advance_step=648,
            strawberry_topup=True, b5_carrot_fertilizer=True,
            b5_jit_fertilize=True, row_shed=True, fert_hand=True,
            terminal_fertilizer=True, goose_rescue=True)

    def act(self, obs):
        import full_production_context
        out = self._policy(obs, full_production_context.configuration)
        state = self._r04._POLICY.players[int(obs['player'])]
        self.cur = 'R04-' + str(state.plan)
        return out
"""


class _State:
    def __init__(self):
        self.plan = 0
        self.last_step = -1
        self.queue = []
        self.sale_window_debts = {}


class DeadlineExceeded(Exception):
    """Canonical outer timer exception only."""


def public_agent(instance, obs):
    """Mirror cloud-execution-lab/main.py::agent(): catch only DeadlineExceeded."""
    try:
        return instance.act(obs)
    except DeadlineExceeded:
        return {"farmer": ["PASS"], "hands": [], "market": []}


class RetrySafeR04(unittest.TestCase):
    def fixture(self):
        r04 = types.ModuleType("r04_full_router")
        r04._POLICY = types.SimpleNamespace(players={})
        calls = []

        def install(**kwargs):
            def donor(obs, cfg):
                player, step = int(obs["player"]), int(obs["step"])
                state = r04._POLICY.players.get(player)
                if state is None or step <= state.last_step:
                    state = r04._POLICY.players[player] = _State()
                state.last_step = step
                if step == 144:
                    state.plan = 7 if player == 0 else 9
                if step == 648:
                    state.plan = 2
                state.queue.append((step, obs.get("tag")))
                state.sale_window_debts.setdefault(step + 1, {})["WOOL"] = len(state.queue)
                calls.append((player, step, state.plan, deepcopy(state.queue)))
                return {"farmer": ["PASS"], "market": [["SELL", "WOOL", state.plan]],
                        "call": len(calls)}
            return donor

        r04.install = install
        tapes = types.ModuleType("r01_tapes")
        tapes.load_tapes = lambda: [[{"route": i}] for i in range(13)]
        context = types.ModuleType("full_production_context")
        context.configuration = {"turnsPerDay": 24}

        class Base:
            def __init__(self):
                self.base_initialized = True

        raw = PASS_SOURCE + b"class Agent:\n    def __init__(self):\n        pass\n" + OVERLAY
        patched = retry.patch_vendor(raw)
        namespace = {}
        sys.modules["r04_full_router"] = r04
        sys.modules["r01_tapes"] = tapes
        sys.modules["full_production_context"] = context
        exec(compile(patched, "fixture_arlene.py", "exec"), namespace)
        agent = namespace["Agent"]()
        return agent, r04, context, calls

    def test_adapter_does_not_raise_runtimeerror_on_changed_evidence(self):
        self.assertNotIn(b"RuntimeError", retry._ACT_REPLACEMENT)
        self.assertIn(b"return deepcopy(PASS)", retry._ACT_REPLACEMENT)

    def test_transform_changes_only_vendor(self):
        raw = PASS_SOURCE + b"prefix\n" + OVERLAY + b"suffix\n"
        files = {retry.VENDOR: raw, "main.py": b"same\n", "x.py": b"same\n"}
        out = retry.transform(files)
        self.assertEqual(set(out), set(files))
        self.assertNotEqual(out[retry.VENDOR], raw)
        self.assertEqual(out["main.py"], files["main.py"])
        self.assertEqual(out["x.py"], files["x.py"])

    def test_missing_or_duplicate_seams_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "install seam"):
            retry.patch_vendor(b"nothing")
        with self.assertRaisesRegex(ValueError, "install seam"):
            retry.patch_vendor(OVERLAY + OVERLAY)
        with self.assertRaisesRegex(ValueError, "act seam"):
            retry.patch_vendor(retry._INIT_ANCHOR + b"\n")
        with self.assertRaisesRegex(ValueError, "canonical vendored PASS"):
            retry.patch_vendor(OVERLAY)

    def test_nonzero_route_survives_identical_retry_without_reentry(self):
        agent, r04, context, calls = self.fixture()
        a144 = agent.act({"player": 0, "step": 144})
        first = agent.act({"player": 0, "step": 145, "tag": "same"})
        state = r04._POLICY.players[0]
        queue = deepcopy(state.queue)
        debts = deepcopy(state.sale_window_debts)
        retry_action = agent.act({"player": 0, "step": 145, "tag": "same"})
        self.assertEqual(a144["market"], [["SELL", "WOOL", 7]])
        self.assertEqual(first, retry_action)
        self.assertEqual(first["call"], 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(state.plan, 7)
        self.assertEqual(state.queue, queue)
        self.assertEqual(state.sale_window_debts, debts)
        retry_action["market"][0][2] = 999
        again = agent.act({"player": 0, "step": 145, "tag": "same"})
        self.assertEqual(again["market"], [["SELL", "WOOL", 7]])
        self.assertEqual(len(calls), 2)

    def test_changed_same_step_returns_legal_pass_without_donor_mutation(self):
        agent, r04, context, calls = self.fixture()
        agent.act({"player": 0, "step": 144})
        agent.act({"player": 0, "step": 145, "tag": "a"})
        state = r04._POLICY.players[0]
        before = deepcopy(state.__dict__)
        returned = agent.act({"player": 0, "step": 145, "tag": "b"})
        self.assertEqual(returned, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(state.__dict__, before)
        self.assertEqual(len(calls), 2)
        continued = agent.act({"player": 0, "step": 146, "tag": "c"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(state.plan, 7)
        self.assertEqual(state.last_step, 146)
        self.assertEqual(state.queue[-1], (146, "c"))
        self.assertEqual(continued["market"], [["SELL", "WOOL", 7]])

    def test_outer_public_entry_changed_same_step_is_legal_action(self):
        instance, r04, context, calls = self.fixture()
        public_agent(instance, {"player": 0, "step": 144})
        public_agent(instance, {"player": 0, "step": 145, "tag": "a"})
        state = r04._POLICY.players[0]
        before = deepcopy(state.__dict__)
        escaped = []
        try:
            returned = public_agent(instance, {"player": 0, "step": 145, "tag": "b"})
        except Exception as error:
            escaped.append(error)
            raise
        self.assertEqual(escaped, [])
        self.assertEqual(returned, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(state.__dict__, before)
        self.assertEqual(len(calls), 2)
        continued = public_agent(instance, {"player": 0, "step": 146, "tag": "c"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(state.plan, 7)
        self.assertEqual(state.last_step, 146)
        self.assertEqual(continued["market"], [["SELL", "WOOL", 7]])

    def test_configuration_change_same_step_returns_legal_pass(self):
        agent, r04, context, calls = self.fixture()
        obs = {"player": 0, "step": 144}
        agent.act(obs)
        before = deepcopy(r04._POLICY.players[0].__dict__)
        context.configuration = {"turnsPerDay": 12}
        returned = agent.act(obs)
        self.assertEqual(returned, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(r04._POLICY.players[0].__dict__, before)
        self.assertEqual(len(calls), 1)

    def test_same_step_internal_state_drift_returns_legal_pass(self):
        agent, r04, context, calls = self.fixture()
        obs = {"player": 0, "step": 144}
        agent.act(obs)
        r04._POLICY.players[0].last_step = 143
        before = deepcopy(r04._POLICY.players[0].__dict__)
        returned = agent.act(obs)
        self.assertEqual(returned, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(r04._POLICY.players[0].__dict__, before)
        self.assertEqual(len(calls), 1)

    def test_backward_step_delegates_to_donor_reset(self):
        agent, r04, context, calls = self.fixture()
        agent.act({"player": 0, "step": 144})
        agent.act({"player": 0, "step": 145})
        returned = agent.act({"player": 0, "step": 140})
        self.assertEqual(len(calls), 3)
        self.assertEqual(returned["market"], [["SELL", "WOOL", 0]])
        self.assertEqual(r04._POLICY.players[0].plan, 0)
        self.assertEqual(r04._POLICY.players[0].last_step, 140)

    def test_pair_publication_is_create_exclusive_and_alias_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, receipt = root / "candidate.tar.gz", root / "receipt.json"
            retry._publish_pair(out, receipt, b"tar-bytes", b"{}\n")
            self.assertEqual(out.read_bytes(), b"tar-bytes")
            self.assertEqual(receipt.read_bytes(), b"{}\n")
            alias = root / "alias"
            with self.assertRaisesRegex(ValueError, "distinct paths"):
                retry._publish_pair(alias, alias, b"x", b"y")
            self.assertFalse(alias.exists())

    def test_preexisting_receipt_rolls_back_owned_tar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, receipt = root / "candidate.tar.gz", root / "receipt.json"
            receipt.write_bytes(b"sentinel")
            with self.assertRaises(FileExistsError):
                retry._publish_pair(out, receipt, b"tar-bytes", b"{}\n")
            self.assertFalse(out.exists())
            self.assertEqual(receipt.read_bytes(), b"sentinel")

    def test_receipt_write_failure_rolls_back_owned_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, receipt = root / "candidate.tar.gz", root / "receipt.json"
            real = retry._write_fd
            calls = []
            def fail_second(fd, body):
                calls.append(body)
                if len(calls) == 2:
                    raise OSError("injected receipt write failure")
                return real(fd, body)
            with patch.object(retry, "_write_fd", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "receipt write failure"):
                    retry._publish_pair(out, receipt, b"tar-bytes", b"{}\n")
            self.assertFalse(out.exists())
            self.assertFalse(receipt.exists())

    def test_players_are_independent_and_forced_plan2_retries(self):
        agent, r04, context, calls = self.fixture()
        agent.act({"player": 0, "step": 144})
        agent.act({"player": 1, "step": 144})
        self.assertEqual(r04._POLICY.players[0].plan, 7)
        self.assertEqual(r04._POLICY.players[1].plan, 9)
        p0 = agent.act({"player": 0, "step": 648})
        p1 = agent.act({"player": 1, "step": 648})
        before = len(calls)
        self.assertEqual(agent.act({"player": 0, "step": 648}), p0)
        self.assertEqual(agent.act({"player": 1, "step": 648}), p1)
        self.assertEqual(len(calls), before)
        self.assertEqual(r04._POLICY.players[0].plan, 2)
        self.assertEqual(r04._POLICY.players[1].plan, 2)


if __name__ == "__main__":
    unittest.main()
