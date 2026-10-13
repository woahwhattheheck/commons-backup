# SPDX-License-Identifier: Apache-2.0
"""Current selected-action adapter for submitted V3.1 B9 -> H3c wrappers.

No gameplay theorem is copied here. Exact submitted donor blobs are vendored by
Git object identity, authenticated once, and executed from the same captured
byte buffers. The adapter removes only the old parent-call shell so current V5
can pass an already-selected action through the submitted outer-wrapper order.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import types
from typing import Any

DONOR_COMMIT = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
B9_GIT_BLOB = "ed8d6923541e700c3a0ae4b93695bbd56455a3b6"
H3C_GIT_BLOB = "2044d6cf1e0c51f95027229863f910aa43ac7008"

HERE = Path(__file__).resolve().parent
B9_PATH = HERE / "vendor/b9_terminal_fertilizer.py"
H3C_PATH = HERE / "vendor/h3c_goose_eod_cap_rescue.py"


def _git_blob_id_bytes(data: bytes) -> str:
    if type(data) is not bytes:
        raise TypeError("Git blob source must be exact bytes")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git_blob_id(path: Path) -> str:
    return _git_blob_id_bytes(Path(path).read_bytes())


def _load_pinned(name: str, path: Path, expected_blob: str):
    """Authenticate and execute one immutable donor snapshot.

    The path is read exactly once.  We intentionally do not ask an import loader
    to reopen it after authentication: the bytes whose Git blob is checked are
    the exact bytes compiled and executed, closing the auth/exec TOCTOU boundary.
    """
    path = Path(path)
    raw = path.read_bytes()
    actual = _git_blob_id_bytes(raw)
    if actual != expected_blob:
        raise RuntimeError(
            f"submitted donor drift: {path.name} expected {expected_blob}, got {actual}"
        )
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    previous = sys.modules.get(name)
    try:
        sys.modules[name] = module
        code = compile(raw, str(path), "exec")
        exec(code, module.__dict__, module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module


_B9 = _load_pinned("_titan_v31_b9_donor", B9_PATH, B9_GIT_BLOB)
_H3C = _load_pinned("_titan_v31_h3c_donor", H3C_PATH, H3C_GIT_BLOB)


class B9H3CCurrentABI:
    """Stateful B9 terminal-fertilizer followed by stateless H3c goose rescue.

    ``transform()`` consumes only a current public observation/configuration and
    an already-selected parent action. It never invokes a producer/controller.
    B9 state semantics mirror ``TerminalFertilizerAgent.__call__`` exactly after
    the historical parent returned its action. H3c then consumes that B9 result,
    matching the submitted ``v3_agent`` outer-wrapper order.
    """

    def __init__(self, *, terminal_fertilizer: bool = False, goose_rescue: bool = False):
        if type(terminal_fertilizer) is not bool or type(goose_rescue) is not bool:
            raise TypeError("terminal_fertilizer and goose_rescue must be exact bool")
        self.terminal_fertilizer = terminal_fertilizer
        self.goose_rescue = goose_rescue
        self._b9_state: dict[int, dict[str, Any]] = {}

    def _b9(self, observation: Any, configuration: Any, selected: Any):
        if not self.terminal_fertilizer:
            return selected, {
                "enabled": False,
                "changed": False,
                "reason": "disabled",
                "collected_episode": False,
            }

        executable_market_cap = _B9._executable_market_cap(configuration)
        if not _B9._standard_terminal_timing(configuration) or executable_market_cap is None:
            self._b9_state.clear()
            return selected, {
                "enabled": True,
                "changed": False,
                "reason": "nonstandard_terminal_configuration",
                "collected_episode": False,
            }

        if not isinstance(observation, dict):
            self._b9_state.clear()
            return selected, {
                "enabled": True,
                "changed": False,
                "reason": "malformed_observation",
                "collected_episode": False,
            }
        try:
            step = observation["step"]
            player = observation["player"]
            farms = observation["farms"]
        except (KeyError, TypeError):
            self._b9_state.clear()
            return selected, {
                "enabled": True,
                "changed": False,
                "reason": "malformed_observation",
                "collected_episode": False,
            }
        if (
            not _B9._exact_int(step)
            or not 0 <= step < _B9.EPISODE_STEPS
            or not _B9._exact_int(player)
            or not isinstance(farms, list)
            or not 0 <= player < len(farms)
        ):
            self._b9_state.clear()
            return selected, {
                "enabled": True,
                "changed": False,
                "reason": "malformed_public_identity",
                "collected_episode": False,
            }
        if not _B9._valid_selected_farm_envelope(farms[player]):
            self._b9_state.clear()
            return selected, {
                "enabled": True,
                "changed": False,
                "reason": "malformed_farm_envelope",
                "collected_episode": False,
            }

        state = self._b9_state.get(player)
        reset = state is None or step <= state["last_step"]
        if reset:
            state = self._b9_state[player] = {"last_step": -1, "collected": False}
        state["last_step"] = step
        before = selected

        if step in _B9.COLLECT_STEPS:
            result, changed = _B9._collect_passes(observation, selected)
            if changed:
                state["collected"] = True
            return result, {
                "enabled": True,
                "changed": result != before,
                "reason": "terminal_collect" if changed else "collect_identity",
                "reset": reset,
                "collected_episode": state["collected"],
            }
        if step == _B9.TERMINAL_STEP and state["collected"]:
            result = _B9._trail_fertilizer_sales(selected, executable_market_cap)
            return result, {
                "enabled": True,
                "changed": result != before,
                "reason": "terminal_sale_partition" if result != before else "terminal_identity",
                "reset": reset,
                "collected_episode": True,
            }
        return selected, {
            "enabled": True,
            "changed": False,
            "reason": "outside_terminal_transform",
            "reset": reset,
            "collected_episode": state["collected"],
        }

    def transform(self, observation: Any, configuration: Any, selected: Any):
        """Return ``(action, report)`` in exact submitted B9 then H3c order."""
        action, b9_report = self._b9(observation, configuration, selected)
        before_h3c = action
        if self.goose_rescue:
            action = _H3C.apply_goose_eod_cap_rescue(
                action, observation, configuration, enabled=True
            )
        h3c_report = {
            "enabled": self.goose_rescue,
            "changed": action != before_h3c,
            "reason": (
                "goose_eod_cap_rescue"
                if action != before_h3c
                else ("identity" if self.goose_rescue else "disabled")
            ),
        }
        return action, {
            "order": ("terminal_fertilizer", "goose_rescue"),
            "b9": b9_report,
            "h3c": h3c_report,
            "changed": action != selected,
        }
