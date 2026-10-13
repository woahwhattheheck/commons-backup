#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound GANDER x Apex clone-radar composition theorem.

This is research evidence inside the existing opening-expansion authority. It
combines two already-canonical source contracts without adding a controller:

* GANDER's strongest certified day-0 frontier is nine GOOSE + exactly one HIRE.
* Authenticated Apex V7 latches its clone flag only during steps 2..10 when the
  opponent has at least three hired hands and at least one animal structure.

Therefore the certified one-hire GANDER frontier cannot satisfy Apex's clone
latch, even under the adversarial assumption that a structure is already
visible throughout the entire latch window. This says nothing about Apex
behaviour that is independent of the clone flag.

The two local helper modules are themselves part of the theorem authority. They
are captured once, Git-blob authenticated before any helper code executes, and
compiled from those exact captured bytes. No helper pathname is reopened for
execution after authentication.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[6]
ENGINE_PATH = HERE.parents[3] / "reference" / "engine" / "kaggriculture.py"
GANDER_PATH = HERE / "goose_printer_oracle.py"
APEX_ORACLE_PATH = HERE.parent / "market-pressure" / "apex_counter_ambush.py"

PINNED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PINNED_APEX_SHA256 = "1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a"
PINNED_GANDER_HELPER_GIT_BLOB = "38ae7715c233c74f24aacd5fe09f4d0d7a630037"
PINNED_APEX_ORACLE_GIT_BLOB = "afdabf68fd262259a29b80d9dd6dad34eb7cae0e"


class RadarCompositionError(RuntimeError):
    pass


def _git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _capture_helper(path: Path, expected_blob: str, label: str) -> bytes:
    """Read one helper exactly once and authenticate it before any execution."""
    data = path.read_bytes()
    observed = _git_blob(data)
    if observed != expected_blob:
        raise RadarCompositionError(
            f"{label} helper identity drift: {observed} != {expected_blob}"
        )
    return data


def _exec_snapshot(data: bytes, path: Path, name: str) -> ModuleType:
    """Compile/exec only an already-authenticated immutable helper snapshot."""
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        code = compile(data, str(path), "exec")
        exec(code, module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _plain_nonnegative_int(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _contract(apex: ModuleType) -> tuple[int, int, int, int]:
    raw = getattr(apex, "APEX_ANTI_CLONE", None)
    if not isinstance(raw, dict):
        raise RadarCompositionError("missing Apex anti-clone contract")
    window = raw.get("clone_window")
    if not isinstance(window, list) or len(window) != 2:
        raise RadarCompositionError("malformed Apex clone window")
    start = _plain_nonnegative_int(window[0])
    end = _plain_nonnegative_int(window[1])
    min_hands = _plain_nonnegative_int(raw.get("clone_min_opponent_hands"))
    min_structures = _plain_nonnegative_int(raw.get("clone_min_opponent_structures"))
    if None in (start, end, min_hands, min_structures) or start > end:
        raise RadarCompositionError("malformed Apex clone thresholds")
    return start, end, min_hands, min_structures


def clone_latch_possible(
    step: Any,
    hired_hands: Any,
    structures: Any,
    contract: tuple[int, int, int, int],
) -> bool:
    step_i = _plain_nonnegative_int(step)
    hands_i = _plain_nonnegative_int(hired_hands)
    structures_i = _plain_nonnegative_int(structures)
    if step_i is None or hands_i is None or structures_i is None:
        raise RadarCompositionError("clone-latch state must use plain nonnegative ints")
    start, end, min_hands, min_structures = contract
    return (
        start <= step_i <= end
        and hands_i >= min_hands
        and structures_i >= min_structures
    )


def _load_canonical_sources() -> tuple[ModuleType, ModuleType, dict[str, str]]:
    # Authenticate BOTH helper snapshots before either one executes. This keeps a
    # poisoned second helper from gaining execution merely because the first one
    # happened to authenticate successfully.
    gander_data = _capture_helper(
        GANDER_PATH,
        PINNED_GANDER_HELPER_GIT_BLOB,
        "GANDER",
    )
    apex_data = _capture_helper(
        APEX_ORACLE_PATH,
        PINNED_APEX_ORACLE_GIT_BLOB,
        "Apex oracle",
    )

    gander = _exec_snapshot(gander_data, GANDER_PATH, "titan_v4_gander_oracle")
    apex = _exec_snapshot(apex_data, APEX_ORACLE_PATH, "titan_v4_apex_counter_ambush")

    if getattr(gander, "EXPECTED_ENGINE_BLOB", None) != PINNED_ENGINE_GIT_BLOB:
        raise RadarCompositionError("GANDER engine identity drift")
    if getattr(apex, "EXPECTED_ENGINE_GIT_BLOB", None) != PINNED_ENGINE_GIT_BLOB:
        raise RadarCompositionError("Apex oracle engine identity drift")
    if getattr(apex, "EXPECTED_APEX_SHA256", None) != PINNED_APEX_SHA256:
        raise RadarCompositionError("Apex source identity drift")

    return gander, apex, {
        "gander_helper_git_blob": PINNED_GANDER_HELPER_GIT_BLOB,
        "apex_oracle_helper_git_blob": PINNED_APEX_ORACLE_GIT_BLOB,
    }


def build_report(verify_sources: bool = True) -> dict[str, Any]:
    gander, apex, helper_identities = _load_canonical_sources()
    contract = _contract(apex)

    rows = gander.day0_frontier()
    frontier = next((row for row in rows if row.get("geese") == 9), None)
    if not isinstance(frontier, dict) or frontier.get("feasible") is not True:
        raise RadarCompositionError("certified nine-goose frontier disappeared")
    hires = _plain_nonnegative_int(frontier.get("hires"))
    if hires is None:
        raise RadarCompositionError("GANDER hire count is malformed")

    start, end, min_hands, min_structures = contract
    # Worst-case the structure side of the conjunction. If one hired hand is
    # already below the hand threshold, any number of visible coops leaves the
    # clone conjunction false throughout the authenticated window.
    worst_case_structures = 9
    latch_rows = [
        {
            "step": step,
            "hired_hands": hires,
            "structures_assumed": worst_case_structures,
            "clone_latch": clone_latch_possible(
                step, hires, worst_case_structures, contract
            ),
        }
        for step in range(start, end + 1)
    ]
    if any(row["clone_latch"] for row in latch_rows):
        raise RadarCompositionError("GANDER frontier can trip authenticated clone latch")

    identities: dict[str, Any] = {
        "engine_git_blob": PINNED_ENGINE_GIT_BLOB,
        "apex_main_sha256": PINNED_APEX_SHA256,
        **helper_identities,
    }
    if verify_sources:
        identities["gander_engine"] = gander.verify_engine_source(ENGINE_PATH)
        identities["apex_sources"] = apex.verify_sources(REPO_ROOT)

    return {
        "schema": "titan.v4.gander-apex-radar-composite.v1",
        "sources": identities,
        "gander_frontier": {
            "geese": 9,
            "hires": hires,
            "last_unit_step": frontier.get("last_unit_step"),
            "fertilizer_ready_eod0": frontier.get("fertilizer_ready_eod0"),
        },
        "apex_clone_contract": {
            "window": [start, end],
            "min_opponent_hands": min_hands,
            "min_opponent_structures": min_structures,
        },
        "proof": {
            "hired_hand_margin_below_latch": min_hands - hires,
            "worst_case_structures_assumed": worst_case_structures,
            "window_rows": latch_rows,
            "clone_latch_possible": False,
        },
        "scope": {
            "claim": "certified GANDER frontier is invisible to Apex clone latch",
            "does_not_claim_apex_has_no_independent_timed_or_predator_actions": True,
            "runtime_change": False,
            "default_change": False,
        },
        "next_gate": (
            "Compare certified GANDER counts against current base in both seats versus "
            "authenticated Apex and non-Apex holdouts; preserve source identity and report "
            "terminal margin. Clone-latch invisibility is a defensive property, not an "
            "economics promotion theorem."
        ),
    }


def main() -> int:
    try:
        report = build_report(verify_sources=True)
    except (OSError, UnicodeError, ValueError, RadarCompositionError) as exc:
        print(f"GANDER_APEX_RADAR BLOCKED: {exc}")
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
