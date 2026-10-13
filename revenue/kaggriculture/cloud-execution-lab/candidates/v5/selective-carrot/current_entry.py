# SPDX-License-Identifier: Apache-2.0
"""Current-V5 selective-carrot treatment entry.

The canonical V5 package is copied unchanged by build_current.py, with its
main.py retained as baseline_main.py. This entry composes the already-landed
selective_carrot mechanism over that parent and reads only the generated
CARROT-CAPACITY.json profile. There is one implementation for all profiles.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import baseline_main as baseline
from selective_carrot import CropChoice

HERE = Path(__file__).resolve().parent
PROFILE_PATH = HERE / "CARROT-CAPACITY.json"


def _git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _require_hex(raw: dict, name: str, length: int) -> str:
    value = raw.get(name)
    if (
        type(value) is not str
        or len(value) != length
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise RuntimeError(f"invalid {name}")
    return value


def _load_profile() -> dict:
    raw = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    expected = {
        "schema",
        "max_active",
        "control_package_sha256",
        "parent_main_git_blob",
        "selective_carrot_git_blob",
        "entry_git_blob",
    }
    if set(raw) != expected:
        raise RuntimeError("invalid selective-carrot current-V5 profile schema")
    if raw["schema"] != "titan-v5-selective-carrot-current/v1":
        raise RuntimeError("unknown selective-carrot current-V5 profile")
    if type(raw["max_active"]) is not int or raw["max_active"] not in (4, 12):
        raise RuntimeError("max_active must be plain int 4 or 12")
    _require_hex(raw, "control_package_sha256", 64)
    _require_hex(raw, "parent_main_git_blob", 40)
    _require_hex(raw, "selective_carrot_git_blob", 40)
    _require_hex(raw, "entry_git_blob", 40)
    if _git_blob(HERE / "baseline_main.py") != raw["parent_main_git_blob"]:
        raise RuntimeError("current-V5 parent main identity drift")
    if _git_blob(HERE / "selective_carrot.py") != raw["selective_carrot_git_blob"]:
        raise RuntimeError("selective-carrot implementation identity drift")
    if _git_blob(Path(__file__).resolve()) != raw["entry_git_blob"]:
        raise RuntimeError("selective-carrot entry identity drift")
    return raw


_PROFILE = _load_profile()
_MAX_ACTIVE = _PROFILE["max_active"]
_FACTORY = baseline._new_instance
_CHOICE = None
_INSTANCE = None


def _factory(root, features):
    global _CHOICE
    from mechanics import market_price
    from scheduler import post_units

    instance = _FACTORY(root, features)
    if _CHOICE is None:
        _CHOICE = CropChoice(market_price, max_active=_MAX_ACTIVE)

    selected_transform = instance.transform_selected
    final_market = instance._early_capital_selected

    def units(obs, cfg, selected):
        changed = _CHOICE.units(obs, cfg, selected, instance.controller.cur)
        return selected_transform(obs, cfg, changed)

    def market(obs, cfg, selected):
        out = final_market(obs, cfg, selected)
        if instance.diagnostics.get("status") == "completed":
            farm, private = post_units(obs, out, cfg)
            post = dict(obs, farms=list(obs["farms"]), private=private)
            post["farms"][obs["player"]] = farm
            out = _CHOICE.market(
                obs,
                cfg,
                out,
                instance.controller.R[instance.controller.cur],
                instance.controller.cur,
                post,
            )
            instance.diagnostics["crop_choice"] = dict(_CHOICE.report)
            instance.diagnostics["crop_choice"]["max_active"] = _MAX_ACTIVE
        return out

    instance.transform_selected = units
    instance._early_capital_selected = market
    return instance


baseline._new_instance = _factory


def _previous_public_step():
    """Mirror the parent entrypoint's retained-step authority without mutating it."""
    instance = baseline._INSTANCE
    if instance is not None:
        return getattr(instance, "_entrypoint_last_step", None)
    journal = getattr(baseline, "_SPATIAL_RECOVERY", None)
    if isinstance(journal, dict):
        return journal.get("last_step")
    return None


def _choice_match_reset(step: int) -> bool:
    """Preserve only a positively proven same-match step-zero retry.

    The parent may discard its whole instance after an outer deadline. If that
    leaves neither an instance marker nor a recovery journal, ``None`` is not
    evidence that a later step-zero call belongs to the same match. Resetting in
    that ambiguous case keeps CropChoice reconstruction aligned with the parent.
    """
    previous_step = _previous_public_step()
    return step == 0 and previous_step != 0


def agent(observation, configuration=None):
    """Return one canonical V5 action with optional selective-carrot changes."""
    global _CHOICE, _INSTANCE
    normalized = baseline._canonical_entrypoint_observation(
        observation, dict(configuration or {})
    )
    if _choice_match_reset(normalized["step"]):
        _CHOICE = None
    returned = baseline.agent(observation, configuration)
    _INSTANCE = baseline._INSTANCE
    if _CHOICE is not None:
        _CHOICE.commit(normalized, returned)
    return returned


def profile():
    """Expose immutable profile identity for evaluation receipts."""
    return deepcopy(_PROFILE)
