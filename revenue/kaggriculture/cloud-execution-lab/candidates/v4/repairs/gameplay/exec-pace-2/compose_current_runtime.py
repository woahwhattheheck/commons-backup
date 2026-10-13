# SPDX-License-Identifier: Apache-2.0
"""Source-bound current-ABI composer for the default-OFF EXEC-PACE-2 experiment.

The composer refuses source drift by requiring exact, unique anchors in the
current production sources.  It does not execute legacy V4 materializers and it
does not enable the feature in TITAN-CONFIG.json.
"""
from __future__ import annotations

import json
from pathlib import Path

FEATURE_ANCHOR = "    early_capital: bool = False\n"
FEATURE_INSERT = FEATURE_ANCHOR + "    exec_pace: bool = False\n"
BOOL_GUARD_ANCHOR = (
    "        for name in bool_fields:\n"
    "            if type(getattr(self, name)) is not bool:\n"
)
BOOL_GUARD_INSERT = (
    "        bool_fields = (*bool_fields, 'exec_pace')\n"
    + BOOL_GUARD_ANCHOR
)
EXEC_PACE_GUARD_ANCHOR = (
    "        if self.terminal_route and self.consumer != 'frozen':\n"
    "            raise ValueError('terminal_route is the tested frozen SELL composition')\n"
)
EXEC_PACE_GUARD_INSERT = EXEC_PACE_GUARD_ANCHOR + (
    "        if self.exec_pace and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('exec_pace is the tested nonterminal frozen SELL composition')\n"
)

FALLBACK_STATE_ANCHOR = (
    "        self._completed_seller_state = None\n"
    "        self._seller_fallback_observations = []\n"
    "        self.spatial = None\n"
)
FALLBACK_STATE_INSERT = (
    "        self._completed_seller_state = None\n"
    "        self._seller_fallback_observations = []\n"
    "        self._exec_pace_fallback_observations = []\n"
    "        self.spatial = None\n"
)

FALLBACK_OBSERVER_ANCHOR = (
    "    def _remember_seller_fallback(self, obs):\n"
    "        \"\"\"Queue one completed fallback observation for a later reconstruction.\"\"\"\n"
    "        if self.features.consumer != 'frozen':\n"
    "            return\n"
    "        step = int(obs['step'])\n"
)
FALLBACK_OBSERVER_INSERT = FALLBACK_OBSERVER_ANCHOR + (
    "        if getattr(self.features, 'exec_pace', False) is True:\n"
    "            self._exec_pace_fallback_observations.append({\n"
    "                'step': step,\n"
    "                'player': int(obs['player']),\n"
    "                'market': {'prices': deepcopy(obs['market']['prices'])},\n"
    "            })\n"
)

CONSUMER_ANCHOR = "            self.consumer = FrozenSelected()\n"
CONSUMER_INSERT = CONSUMER_ANCHOR + (
    "            if f.exec_pace is True:\n"
    "                pace = load('_titan_exec_pace_runtime', HERE/'exec_pace_runtime.py')\n"
    "                exec_pace_state = getattr(self, '_exec_pace_state', None)\n"
    "                if exec_pace_state is None:\n"
    "                    exec_pace_state = pace.PriceTrendState()\n"
    "                    self._exec_pace_state = exec_pace_state\n"
    "                self.consumer.exec_pace_state = exec_pace_state\n"
    "                self.consumer.exec_pace_apply = pace.apply_candidate\n"
    "                for exec_pace_obs in getattr(self, '_exec_pace_fallback_observations', ()):\n"
    "                    exec_pace_state.note_prices(exec_pace_obs)\n"
    "                self._exec_pace_fallback_observations = []\n"
)

TRANSFORM_ANCHOR = (
    "        self.observe(obs)\n"
    "        farm,private=post_units(obs,base,config)\n"
)
TRANSFORM_INSERT = (
    "        self.observe(obs)\n"
    "        exec_pace_state=getattr(self,'exec_pace_state',None)\n"
    "        if exec_pace_state is not None:exec_pace_state.note_prices(obs)\n"
    "        farm,private=post_units(obs,base,config)\n"
)

PLAN_ANCHOR = (
    "            info['baseline_horizon_end']=horizon['baseline_end'];info['horizon_end']=item_end\n"
    "            self.diagnostics['evaluations'].append(info)\n"
    "            eligible,rank=seller_choice_rank(info)\n"
)
PLAN_INSERT = (
    "            info['baseline_horizon_end']=horizon['baseline_end'];info['horizon_end']=item_end\n"
    "            exec_pace_apply=getattr(self,'exec_pace_apply',None)\n"
    "            if exec_pace_apply is not None:\n"
    "                plan,info=exec_pace_apply(exec_pace_state,item,reference,plan,info)\n"
    "            self.diagnostics['evaluations'].append(info)\n"
    "            eligible,rank=seller_choice_rank(info)\n"
)


def _replace_once(source, anchor, replacement, label):
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"{label} source drift: expected one anchor, found {count}")
    return source.replace(anchor, replacement, 1)


def compose_sources(titan_runtime_source, frozen_selected_source):
    titan = _replace_once(titan_runtime_source, FEATURE_ANCHOR, FEATURE_INSERT, "Features")
    titan = _replace_once(titan, BOOL_GUARD_ANCHOR, BOOL_GUARD_INSERT,
                          "Features exact-bool guard")
    titan = _replace_once(titan, EXEC_PACE_GUARD_ANCHOR, EXEC_PACE_GUARD_INSERT,
                          "EXEC-PACE composition guard")
    titan = _replace_once(titan, FALLBACK_STATE_ANCHOR, FALLBACK_STATE_INSERT,
                          "EXEC-PACE fallback state")
    titan = _replace_once(titan, FALLBACK_OBSERVER_ANCHOR, FALLBACK_OBSERVER_INSERT,
                          "seller fallback observer")
    titan = _replace_once(titan, CONSUMER_ANCHOR, CONSUMER_INSERT, "FrozenSelected construction")
    frozen = _replace_once(frozen_selected_source, TRANSFORM_ANCHOR, TRANSFORM_INSERT,
                           "FrozenSelected transform observer")
    frozen = _replace_once(frozen, PLAN_ANCHOR, PLAN_INSERT, "FrozenSelected plan gate")
    compile(titan, "titan_runtime.py", "exec")
    compile(frozen, "frozen_selected.py", "exec")
    return titan, frozen


def compose_config(config_source):
    config = json.loads(config_source)
    if "exec_pace" in config:
        raise ValueError("exec_pace already present; refuse ambiguous source")
    config["exec_pace"] = False
    return json.dumps(config, indent=2, sort_keys=False) + "\n"


def materialize(source_root, target_root, runtime_module_source):
    source_root = Path(source_root)
    target_root = Path(target_root)
    if target_root.exists():
        raise FileExistsError(target_root)
    titan_src = (source_root / "titan_runtime.py").read_text()
    frozen_src = (source_root / "frozen_selected.py").read_text()
    config_src = (source_root / "TITAN-CONFIG.json").read_text()
    titan, frozen = compose_sources(titan_src, frozen_src)
    config = compose_config(config_src)
    target_root.mkdir(parents=True)
    (target_root / "titan_runtime.py").write_text(titan)
    (target_root / "frozen_selected.py").write_text(frozen)
    (target_root / "TITAN-CONFIG.json").write_text(config)
    (target_root / "exec_pace_runtime.py").write_text(runtime_module_source)
    return {
        "titan_runtime.py": len(titan),
        "frozen_selected.py": len(frozen),
        "TITAN-CONFIG.json": len(config),
        "exec_pace_runtime.py": len(runtime_module_source),
    }
