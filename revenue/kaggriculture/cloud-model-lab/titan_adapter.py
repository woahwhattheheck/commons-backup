"""Standalone TITAN-compatible callable: intact Arlene plus the cap-harvest overlay.

Interface, for T08 and any other integrator:

    from titan_adapter import agent, make_agent, CONFIG
    action = agent(observation, configuration)      # kaggle file-agent shape
    a = make_agent(storage_aware=False)             # a fresh, isolated instance
    action = a.act(observation)

`agent` keeps one instance per seat and rebuilds it at step 0, so a fresh episode
never inherits a previous one's route state or in-flight plan. Any exception
degrades to a legal PASS with the right number of hands, exactly as the parent
does -- a crash forfeits the game.

WHAT IT IS. The parent is Arlene v14, unmodified and loaded from the vendored
source by pinned sha256; this adds only the cap-harvest overlay, which writes into
worker slots the parent's own `_noop` predicate marks free. `one_way=True` is the
configuration every recorded panel used and is set explicitly here: the
`PlanOverlay` constructor default is False, so an integrator that builds the
overlay directly and omits it does NOT get the tested behaviour.

RUNTIME. No `kaggle_environments` at import or at turn time. The unit-phase
transition and `market_price` both come from the bundled `engine_pin.py`, copied
verbatim from the pinned engine under Apache-2.0 with the notice alongside. Files
required beside this one: arlene.py (or ARLENE_PATH set), engine_pin.py,
arlene_plan.py, run_cards.py, native_motifs.py.
"""

import hashlib
import importlib.util
import os

import arlene_plan
import native_motifs as NM

ARLENE_SHA = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
ARLENE_PATH = os.environ.get("TITAN_ARLENE_PATH") or None

CONFIG = {
    "parent": "arlene v14",
    "parent_sha256": ARLENE_SHA,
    "overlay": "cap-overflow harvest",
    # the frozen behavioural configuration of every recorded panel
    "one_way": True,
    "storage_aware": False,
    "max_plan_steps": arlene_plan.MAX_PLAN_STEPS,
    "engine_pin": "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c",
    "requires_kaggle_environments": False,
}


def _candidate_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    if ARLENE_PATH:
        yield ARLENE_PATH
    yield os.path.join(here, "arlene.py")
    yield os.path.join(here, "..", "cloud-frontier-policy", "next-panel",
                       "vendor", "arlene.py")


def load_parent(verify=True):
    """Load the vendored parent by pinned hash. A substitute is refused."""
    last = None
    for path in _candidate_paths():
        if not path or not os.path.exists(path):
            continue
        raw = open(path, "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        if verify and sha != ARLENE_SHA:
            last = f"{path}: sha256 {sha} != pinned {ARLENE_SHA}"
            continue
        spec = importlib.util.spec_from_file_location("arlene_parent",
                                                      os.path.realpath(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise RuntimeError("parent arlene.py not found or hash mismatch"
                       + (f" ({last})" if last else ""))


def make_agent(storage_aware=False, min_incremental=0.0, verify=True):
    """A fresh overlay instance. `one_way=True` is fixed: it is what was tested."""
    parent = load_parent(verify=verify)
    return arlene_plan.PlanOverlay(
        parent, arlene_plan.CapChooser(NM.engine()),
        one_way=True, storage_aware=storage_aware,
        min_incremental=min_incremental)


_SEATS = {}


def agent(observation, configuration=None):
    seat = 0
    try:
        seat = int(observation.get("player", 0) or 0)
        step = observation.get("step")
        step = (int(step) if step is not None
                else int(observation.get("day", 0)) * 24
                + int(observation.get("hour", 0)))
        if step == 0 or seat not in _SEATS:
            _SEATS[seat] = make_agent()
        return _SEATS[seat].act(observation)
    except Exception:
        try:
            hands = observation["farms"][seat].get("hands") or []
        except Exception:
            hands = []
        return {"farmer": ["PASS"], "hands": [["PASS"] for _ in hands],
                "market": []}
