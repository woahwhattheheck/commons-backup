"""Apply V4 key plumbing after the frozen V3.1 integration.

V3.1 source is the submitted baseline.  V4 lanes add exact-string edits in this
small follow-on layer so the V3.1 integration recipe remains an immutable receipt.
Every edit is asserted to match exactly once.
"""
import io
import json
import os

KEYS = ("r04_place_delivery", "r04_goose_pass_rescue", "r04_v217_eod_tail")


def _replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, "%s: expected 1 match, found %d" % (label, count)
    return text.replace(old, new)


def apply(src):
    def read(name):
        return io.open(os.path.join(src, name), encoding="utf-8", newline="").read()

    def write(name, text):
        with io.open(os.path.join(src, name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    router = read("r04_full_router.py")
    router = _replace_once(
        router,
        "GOOSE_RESCUE = False\n_TERMINAL_FERTILIZER_AGENT = None\n",
        "GOOSE_RESCUE = False\n"
        "PLACE_DELIVERY = False\n"
        "GOOSE_PASS_RESCUE = False\n"
        "V217_EOD_TAIL = False\n"
        "_TERMINAL_FERTILIZER_AGENT = None\n",
        "R04 V4 flags",
    )
    router = _replace_once(
        router,
        "def _v217_plan(view, st, step, action, pending):\n",
        "def _v217_standard_configuration(configuration):\n"
        "    def read(name):\n"
        "        if isinstance(configuration, dict):\n"
        "            return configuration.get(name)\n"
        "        return getattr(configuration, name, None) if configuration is not None else None\n"
        "    for name, expected in (('episodeSteps',720),('turnsPerDay',24),('boardSize',10),\n"
        "                           ('shedCapacity',100),('maxMarketOrdersPerTurn',10)):\n"
        "        value=read(name)\n"
        "        if type(value) is not int or value!=expected:return False\n"
        "    return True\n"
        "\n"
        "def _v217_plan(view, st, step, action, pending, configuration=None):\n",
        "V217 EOD tail standard configuration",
    )
    router = _replace_once(
        router,
        "        opposite = {'EAST':'WEST','WEST':'EAST','NORTH':'SOUTH','SOUTH':'NORTH'}\n"
        "        commands = ([['PICKUP','WHEAT']] if need_pickup else []) + [[m] for m in moves] + [['FEED']] + [[opposite[m]] for m in reversed(moves)]\n"
        "        if len(commands) > end-step or any(_v217_farmer(tape, step+i) != ['PASS'] for i in range(len(commands))):\n"
        "            continue\n"
        "        positions = []\n"
        "        pos = start\n"
        "        for cmd in commands:\n"
        "            positions.append(pos)\n"
        "            if cmd[0] in _V217_MOVES:\n"
        "                dx, dy = _V217_MOVES[cmd[0]]\n"
        "                pos = (pos[0]+dx, pos[1]+dy)\n"
        "        assert pos == start\n"
        "        return {'step':step, 'route':st.get('plan'), 'commands':commands,\n"
        "                'positions':positions, 'target':(x,y)}\n",
        "        opposite = {'EAST':'WEST','WEST':'EAST','NORTH':'SOUTH','SOUTH':'NORTH'}\n"
        "        forward = ([['PICKUP','WHEAT']] if need_pickup else []) + [[m] for m in moves] + [['FEED']]\n"
        "        roundtrip = forward + [[opposite[m]] for m in reversed(moves)]\n"
        "        # The official engine resets the farmer at the nightly boundary.\n"
        "        # Use that reset only when FEED itself occupies tonight's final\n"
        "        # callback: otherwise the displaced farmer would be observable\n"
        "        # for another parent callback before reset. Existing round-trip\n"
        "        # rescues are never shortened; day 29 has no later reset.\n"
        "        eod_tail = (V217_EOD_TAIL and _v217_standard_configuration(configuration)\n"
        "                    and len(targets) == 1 and end < 719\n"
        "                    and len(forward) == end-step < len(roundtrip)\n"
        "                    and all(_v217_farmer(tape, future_step) == ['PASS']\n"
        "                            for future_step in range(step, end)))\n"
        "        commands = forward if eod_tail else roundtrip\n"
        "        if len(commands) > end-step or any(_v217_farmer(tape, step+i) != ['PASS'] for i in range(len(commands))):\n"
        "            continue\n"
        "        positions = []\n"
        "        pos = start\n"
        "        for cmd in commands:\n"
        "            positions.append(pos)\n"
        "            if cmd[0] in _V217_MOVES:\n"
        "                dx, dy = _V217_MOVES[cmd[0]]\n"
        "                pos = (pos[0]+dx, pos[1]+dy)\n"
        "        if eod_tail:\n"
        "            assert pos == (x, y)\n"
        "        else:\n"
        "            assert pos == start\n"
        "        return {'step':step, 'route':st.get('plan'), 'commands':commands,\n"
        "                'positions':positions, 'target':(x,y), 'eod_tail':eod_tail}\n",
        "V217 EOD tail planner",
    )
    router = _replace_once(
        router,
        "        task=_v217_plan(view,st,step,action,pending)\n",
        "        task=_v217_plan(view,st,step,action,pending,configuration)\n",
        "V217 EOD tail configuration forwarding",
    )
    router = _replace_once(
        router,
        "def _v3_stack(observation, configuration=None):\n"
        "    action = POLICY_AGENT(observation, configuration)\n",
        "def _v3_stack(observation, configuration=None):\n"
        "    action = POLICY_AGENT(observation, configuration)\n"
        "    if PLACE_DELIVERY:\n"
        "        import r04_place_delivery\n"
        "        action = r04_place_delivery.apply_place_delivery(observation, action, enabled=True)\n"
        "    if GOOSE_PASS_RESCUE:\n"
        "        import r04_goose_pass_rescue\n"
        "        action = r04_goose_pass_rescue.apply_goose_pass_rescue(\n"
        "            action, observation, configuration, enabled=True)\n",
        "R04 V4 stack seams",
    )
    router = _replace_once(
        router,
        "            dribble_dump=None, mirror_horizon=None, terminal_fertilizer=None, goose_rescue=None):\n",
        "            dribble_dump=None, mirror_horizon=None, terminal_fertilizer=None, goose_rescue=None,\n"
        "            place_delivery=None, goose_pass_rescue=None, v217_eod_tail=None):\n",
        "R04 V4 install parameters",
    )
    router = _replace_once(
        router,
        "    mirror_horizon, terminal_fertilizer and goose_rescue switch the ASTRA lanes B11, B9 and H3c,\n"
        "    applied around the whole agent in v3_agent().\n",
        "    mirror_horizon, terminal_fertilizer and goose_rescue switch the ASTRA lanes B11, B9 and H3c,\n"
        "    applied around the whole agent in v3_agent(). place_delivery converts terminal DROP cargo\n"
        "    deliveries to capacity-bounded PLACE actions so overflow remains on the worker.\n"
        "    goose_pass_rescue banks clipping hour-23 GOOSE eggs when the authored unit action is PASS.\n"
        "    v217_eod_tail makes only a sole otherwise-unreachable V217 starvation rescue fit before\n"
        "    a proven nightly reset; any rescue whose incumbent round trip fits is unchanged.\n",
        "R04 V4 install docs",
    )
    router = _replace_once(
        router,
        "    global MIRROR_HORIZON, TERMINAL_FERTILIZER, GOOSE_RESCUE\n",
        "    global MIRROR_HORIZON, TERMINAL_FERTILIZER, GOOSE_RESCUE, PLACE_DELIVERY, GOOSE_PASS_RESCUE, V217_EOD_TAIL\n",
        "R04 V4 globals",
    )
    router = _replace_once(
        router,
        "    if goose_rescue is not None:\n"
        "        GOOSE_RESCUE = bool(goose_rescue)\n"
        "    return v3_agent\n",
        "    if goose_rescue is not None:\n"
        "        GOOSE_RESCUE = bool(goose_rescue)\n"
        "    if place_delivery is not None:\n"
        "        PLACE_DELIVERY = bool(place_delivery)\n"
        "    if goose_pass_rescue is not None:\n"
        "        GOOSE_PASS_RESCUE = bool(goose_pass_rescue)\n"
        "    if v217_eod_tail is not None:\n"
        "        V217_EOD_TAIL = bool(v217_eod_tail)\n"
        "    return v3_agent\n",
        "R04 V4 install setters",
    )
    write("r04_full_router.py", router)

    runtime = read("titan_runtime.py")
    runtime = _replace_once(
        runtime,
        "    r04_goose_rescue: bool = True\n\n    def __post_init__(self):",
        "    r04_goose_rescue: bool = True\n"
        "    r04_place_delivery: bool = False\n"
        "    r04_goose_pass_rescue: bool = False\n"
        "    r04_v217_eod_tail: bool = False\n\n    def __post_init__(self):",
        "Features V4 fields",
    )
    runtime = _replace_once(
        runtime,
        "                                 terminal_fertilizer=bool(self.features.r04_terminal_fertilizer),\n"
        "                                 goose_rescue=bool(self.features.r04_goose_rescue))(observation, configuration)\n",
        "                                 terminal_fertilizer=bool(self.features.r04_terminal_fertilizer),\n"
        "                                 goose_rescue=bool(self.features.r04_goose_rescue),\n"
        "                                 place_delivery=bool(self.features.r04_place_delivery),\n"
        "                                 goose_pass_rescue=bool(self.features.r04_goose_pass_rescue),\n"
        "                                 v217_eod_tail=bool(self.features.r04_v217_eod_tail))(observation, configuration)\n",
        "TitanAgent V4 install arguments",
    )
    runtime = _replace_once(
        runtime,
        "                self.diagnostics['goose_rescue'] = bool(self.features.r04_goose_rescue)\n",
        "                self.diagnostics['goose_rescue'] = bool(self.features.r04_goose_rescue)\n"
        "                self.diagnostics['place_delivery'] = bool(self.features.r04_place_delivery)\n"
        "                self.diagnostics['goose_pass_rescue'] = bool(self.features.r04_goose_pass_rescue)\n"
        "                self.diagnostics['v217_eod_tail'] = bool(self.features.r04_v217_eod_tail)\n",
        "TitanAgent V4 diagnostics",
    )
    write("titan_runtime.py", runtime)

    cfg_path = os.path.join(src, "TITAN-CONFIG.json")
    data = json.loads(io.open(cfg_path, encoding="utf-8").read())
    for key in KEYS:
        assert key not in data, key
        data[key] = False
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
    return src
