# SPDX-License-Identifier: Apache-2.0
"""Exact-source C5 port into a NEW scratch package; never a legacy materializer.

This module does not import or execute the input runtime or C5 donor. The C5
algorithm stays in its existing, unchanged donor; only modern lifecycle wiring
is added. Production source, entrypoint, defaults and archive are not edited.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

RUNTIME_BLOB = "b952c9c228ecbde592bf3d2df01638677abb0d24"
DONOR_BLOB = "d5ea1757975099409a00a32e9c7eb6d40bf51926"
KEY = "r04_c5_wheat_demand"


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require_pin(data: bytes, expected: str, label: str) -> None:
    actual = blob_id(data)
    if actual != expected:
        raise ValueError(f"{label} source drift: expected {expected}, got {actual}")


def replace_exact(source: str, old: str, new: str, count: int = 1) -> str:
    actual = source.count(old)
    if actual != count:
        raise ValueError(f"anchor count {actual}, expected {count}: {old[:80]!r}")
    return source.replace(old, new)


METHODS = '''    @staticmethod
    def _c5_same_value(left, right):
        # Exact JSON-type binding: Python's True == 1 must not certify a row.
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            return (left.keys() == right.keys() and all(
                TitanAgent._c5_same_value(left[k], right[k]) for k in left))
        if type(left) in (list, tuple):
            return len(left) == len(right) and all(
                TitanAgent._c5_same_value(a, b) for a, b in zip(left, right))
        return type(left) in (str, int, float, bool, type(None)) and left == right

    def _c5_prepare_return(self, obs, cfg, returned):
        if not self.features.r04_c5_wheat_demand or self._c5_rider is None:
            return returned
        # No mutable global RIDER: a cancelled/unreturned preview is discarded.
        pending = deepcopy(self._c5_rider)
        pending.enabled = self.diagnostics.get('status') == 'completed'
        if self._c5_input_valid:
            returned = pending.apply(obs, returned, cfg)
        else:
            # The parent normalizes its clock; C5 may not use that coercion as
            # proof of an exact contiguous public transition.
            pending.reset()
        self._c5_pending = (pending, deepcopy(returned))
        return returned

    def _c5_commit_return(self, returned):
        if not self.features.r04_c5_wheat_demand:
            return
        pending = self._c5_pending
        self._c5_pending = None
        if pending is None:
            return
        rider, expected = pending
        if not self._c5_same_value(returned, expected):
            # A later finalizer changed the proposed rows. Do not self-certify
            # a later inventory decline from this unbound action record.
            self._c5_rider.reset()
            self.diagnostics['c5_wheat_demand'] = {
                'committed': False, 'reason': 'post_finalizer_action_drift'}
            return
        self._c5_rider = rider
        self.diagnostics['c5_wheat_demand'] = {
            'committed': True, 'observe_only': not rider.enabled,
            'telemetry': dict(rider.telemetry)}

'''


def compose(runtime: bytes, donor: bytes) -> bytes:
    require_pin(runtime, RUNTIME_BLOB, "runtime")
    require_pin(donor, DONOR_BLOB, "C5 donor")
    source = runtime.decode("utf-8")
    source = replace_exact(source, "    early_capital: bool = False\n",
                           "    early_capital: bool = False\n    r04_c5_wheat_demand: bool = False\n")
    source = replace_exact(source, "    def __post_init__(self):\n",
        "    def __post_init__(self):\n"
        "        if type(self.r04_c5_wheat_demand) is not bool:\n"
        "            raise ValueError('r04_c5_wheat_demand must be a literal bool')\n"
        "        if self.r04_c5_wheat_demand and (self.consumer != 'frozen' or self.terminal_route):\n"
        "            raise ValueError('C5 current port requires nonterminal frozen SELL')\n")
    source = replace_exact(source, "        self.committed_seed_retry_module = None\n",
        "        self.committed_seed_retry_module = None\n"
        "        self._c5_rider = None\n"
        "        self._c5_pending = None\n"
        "        self._c5_input_valid = False\n")
    source = replace_exact(source, "        self._restore_seller_state()\n        self.ready = True\n",
        "        self._restore_seller_state()\n"
        "        if self.features.r04_c5_wheat_demand and self._c5_rider is None:\n"
        "            c5 = load('_titan_c5_donor', HERE/'r04_c5_wheat_demand.py')\n"
        "            self._c5_rider = c5.WheatDemandRider(enabled=True)\n"
        "        self.ready = True\n")
    source = replace_exact(source, "    def _finish_production(self, obs, returned, cfg=None):\n",
                           METHODS + "    def _finish_production(self, obs, returned, cfg=None):\n")
    source = replace_exact(source,
        "        returned = self._early_capital_selected(obs, cfg or {}, returned)\n",
        "        returned = self._early_capital_selected(obs, cfg or {}, returned)\n"
        "        returned = self._c5_prepare_return(obs, cfg or {}, returned)\n")
    source = replace_exact(source, "        invoked = time.perf_counter()\n",
        "        invoked = time.perf_counter()\n        self._c5_pending = None\n")
    source = replace_exact(source, "        obs = dict(observation)\n",
        "        obs = dict(observation)\n"
        "        if self.features.r04_c5_wheat_demand:\n"
        "            self._c5_input_valid = (type(obs.get('step')) is int and obs['step'] >= 0\n"
        "                and type(obs.get('player')) is int and obs['player'] in (0, 1))\n")
    source = replace_exact(source, "        if seconds <= 0:\n",
        "        if seconds <= 0:\n"
        "            if self.features.r04_c5_wheat_demand and self._c5_rider is not None:\n"
        "                self._c5_rider.reset()\n")
    source = replace_exact(source,
        "            output = self._finish_production(obs, output, cfg)\n",
        "            output = self._finish_production(obs, output, cfg)\n"
        "            self._c5_commit_return(output)\n")
    source = replace_exact(source,
        "        output = self._finish_production(obs, output, cfg)\n        # A completed action receipt",
        "        output = self._finish_production(obs, output, cfg)\n"
        "        self._c5_commit_return(output)\n        # A completed action receipt")
    ast.parse(source, filename="titan_runtime.py")
    return source.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="New, nonexistent scratch directory; never an existing package")
    args = parser.parse_args()
    original = args.runtime.read_bytes()
    donor = args.donor.read_bytes()
    candidate = compose(original, donor)
    # All reads, pin checks and compilation happen before creating any output.
    # mkdir(exist_ok=False) is the create-only guard; no input can be overwritten.
    args.out.mkdir(parents=False, exist_ok=False)
    (args.out / "titan_runtime.py").write_bytes(candidate)
    (args.out / "r04_c5_wheat_demand.py").write_bytes(donor)
    receipt = {
        "kind": "titan-v4-c5-current-runtime-composition/v1",
        "runtime_input_blob": RUNTIME_BLOB, "donor_blob": DONOR_BLOB,
        "runtime_output_blob": blob_id(candidate),
        "default": False, "entrypoint_modified": False,
        "scope": "two-file component scratch only, not an executable release package",
    }
    (args.out / "COMPOSITION.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
