"""Apply the converged V4 market/S4 plumbing as one declarative patch layer.

This is the static-materializer-compatible form of the c199 market assembly: no
dynamic import, sidecar execution, or top-level candidate behavior.  Every source
edit is a once-only literal replacement and every new key ships literal False.
"""
import io
import json
import os

KEYS = (
    "r04_place_delivery",
    "r04_goose_pass_rescue",
    "r04_h3b_sheep_clip",
    "r04_h3e_cow_feed_recycle",
    "r04_v233_eod_service",
    "r04_b10_public_supply_order",
    "r04_dead_sell_slot",
    "r04_advance_slot_value",
    "r04_eod_capacity_rescue",
    "r04_m1_wheat_trade",
    "r04_c5_wheat_demand",
    "r04_s4_route12_seed_reserve",
)


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
        "H3B_SHEEP_CLIP = False\n"
        "H3E_COW_FEED_RECYCLE = False\n"
        "V233_EOD_SERVICE = False\n"
        "B10_PUBLIC_SUPPLY_ORDER = False\n"
        "DEAD_SELL_SLOT = False\n"
        "ADVANCE_SLOT_VALUE = False\n"
        "EOD_CAPACITY_RESCUE = False\n"
        "M1_WHEAT_TRADE = False\n"
        "C5_WHEAT_DEMAND = False\n"
        "S4_ROUTE12_SEED_RESERVE = False\n"
        "_TERMINAL_FERTILIZER_AGENT = None\n",
        "R04 V4 flags",
    )
    router = _replace_once(
        router,
        "    stock = projected_shed(action, view)\n"
        "    for item in PRODUCTS:\n",
        "    stock = projected_shed(action, view)\n"
        "    if ADVANCE_SLOT_VALUE:\n"
        "        import r04_advance_slot_value\n"
        "        r04_advance_slot_value.apply_advance_slot_value(\n"
        "            action, view, state, stock, planned, already_selling, PRODUCTS,\n"
        "            MAX_ORDERS, next_step, enabled=True)\n"
        "        return\n"
        "    for item in PRODUCTS:\n",
        "R04 V4 advance-slot matching-module seam",
    )
    router = _replace_once(
        router,
        "        subtract_advanced_sales(action, state, step)\n"
        "        advance_sales(action, view, state, tape, step)\n",
        "        subtract_advanced_sales(action, state, step)\n"
        "        if DEAD_SELL_SLOT:\n"
        "            import r04_dead_sell_slot\n"
        "            action = r04_dead_sell_slot.prune_trailing_dead_sells(action, view, enabled=True)\n"
        "        advance_sales(action, view, state, tape, step)\n",
        "R04 dead SELL slot seam",
    )
    router = _replace_once(
        router,
        "def _v3_stack(observation, configuration=None):\n"
        "    action = POLICY_AGENT(observation, configuration)\n",
        "def _v3_stack(observation, configuration=None):\n"
        "    action = POLICY_AGENT(observation, configuration)\n"
        "    if PLACE_DELIVERY and configuration is not None:\n"
        "        import r04_place_delivery\n"
        "        action = r04_place_delivery.apply_place_delivery(\n"
        "            observation, action, enabled=True, configuration=configuration)\n"
        "    if GOOSE_PASS_RESCUE:\n"
        "        import r04_goose_pass_rescue\n"
        "        action = r04_goose_pass_rescue.apply_goose_pass_rescue(\n"
        "            action, observation, configuration, enabled=True)\n"
        "    if H3B_SHEEP_CLIP:\n"
        "        import r04_h3b_sheep_clip\n"
        "        action = r04_h3b_sheep_clip.apply_h3b_sheep_clip(\n"
        "            action, observation, configuration, enabled=True)\n",
        "R04 V4 stack seams",
    )
    router = _replace_once(
        router,
        "def v3_agent(observation, configuration=None):\n"
        "    global SALE_HORIZON, _TERMINAL_FERTILIZER_AGENT\n"
        "    if not (MIRROR_HORIZON or TERMINAL_FERTILIZER or GOOSE_RESCUE):\n"
        "        return _v3_core(observation, configuration)\n",
        "def v3_agent(observation, configuration=None):\n"
        "    global SALE_HORIZON, _TERMINAL_FERTILIZER_AGENT\n"
        "    if not (MIRROR_HORIZON or TERMINAL_FERTILIZER or GOOSE_RESCUE or PLACE_DELIVERY or GOOSE_PASS_RESCUE or H3B_SHEEP_CLIP or H3E_COW_FEED_RECYCLE or V233_EOD_SERVICE or B10_PUBLIC_SUPPLY_ORDER or DEAD_SELL_SLOT or EOD_CAPACITY_RESCUE or M1_WHEAT_TRADE or C5_WHEAT_DEMAND or S4_ROUTE12_SEED_RESERVE):\n"
        "        return _v3_core(observation, configuration)\n",
        "R04 V4 outer-wrapper dispatch",
    )
    router = _replace_once(
        router,
        "    if GOOSE_RESCUE:\n"
        "        import h3c_goose_eod_cap_rescue\n"
        "        action = h3c_goose_eod_cap_rescue.apply_goose_eod_cap_rescue(action, observation, configuration,\n"
        "                                                                     enabled=True)\n"
        "    return action\n",
        "    if GOOSE_RESCUE:\n"
        "        import h3c_goose_eod_cap_rescue\n"
        "        action = h3c_goose_eod_cap_rescue.apply_goose_eod_cap_rescue(action, observation, configuration,\n"
        "                                                                     enabled=True)\n"
        "    if H3E_COW_FEED_RECYCLE:\n"
        "        import r04_h3e_cow_feed_recycle\n"
        "        action = r04_h3e_cow_feed_recycle.apply_cow_feed_recycle(\n"
        "            action, observation, configuration, enabled=True)\n"
        "    if V233_EOD_SERVICE:\n"
        "        import r04_v233_eod_service\n"
        "        action = r04_v233_eod_service.apply_v233_eod_service(\n"
        "            action, observation, configuration, enabled=True)\n"
        "    if M1_WHEAT_TRADE:\n"
        "        import r04_m1_wheat_trade\n"
        "        try:\n"
        "            player = observation.get('player') if isinstance(observation, dict) else None\n"
        "            if type(player) is int:\n"
        "                state = _POLICY.players.get(player)\n"
        "                tape = _policy_tape(observation)\n"
        "                action = r04_m1_wheat_trade.apply_m1_wheat_trade(\n"
        "                    observation, action, tape, state, configuration, enabled=True)\n"
        "        except (AttributeError, KeyError, TypeError, IndexError, ValueError):\n"
        "            pass\n"
        "    if EOD_CAPACITY_RESCUE:\n"
        "        import r04_eod_capacity_rescue\n"
        "        action = r04_eod_capacity_rescue.apply_eod_capacity_rescue(\n"
        "            action, observation, configuration, enabled=True)\n"
        "    if B10_PUBLIC_SUPPLY_ORDER:\n"
        "        import r04_b10_public_supply_order\n"
        "        if configuration is None:\n"
        "            r04_b10_public_supply_order.invalidate_public_supply_order(observation)\n"
        "        else:\n"
        "            action = r04_b10_public_supply_order.apply_public_supply_order(\n"
        "                observation, action, configuration, enabled=True)\n"
        "    if C5_WHEAT_DEMAND:\n"
        "        import r04_c5_wheat_demand\n"
        "        action = r04_c5_wheat_demand.apply_c5_wheat_demand(\n"
        "            observation, action, configuration, enabled=True)\n"
        "    if S4_ROUTE12_SEED_RESERVE:\n"
        "        import r04_s4_route12_seed_reserve\n"
        "        action = r04_s4_route12_seed_reserve.apply_route12_seed_reserve(\n"
        "            observation, action, configuration, enabled=True)\n"
        "    return action\n",
        "R04 H3e, A1, M1, EOD, B10, C5 then S4 outer seams",
    )
    router = _replace_once(
        router,
        "            dribble_dump=None, mirror_horizon=None, terminal_fertilizer=None, goose_rescue=None):\n",
        "            dribble_dump=None, mirror_horizon=None, terminal_fertilizer=None, goose_rescue=None,\n"
        "            place_delivery=None, goose_pass_rescue=None, b10_public_supply_order=None,\n"
        "            h3b_sheep_clip=None, h3e_cow_feed_recycle=None, v233_eod_service=None,\n"
        "            dead_sell_slot=None, advance_slot_value=None, eod_capacity_rescue=None, m1_wheat_trade=None,\n"
        "            c5_wheat_demand=None, s4_route12_seed_reserve=None):\n",
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
        "    h3e_cow_feed_recycle runs on the fully reconstructed outer action and turns only a provably\n"
        "    dead nonfinal hour-23 COW service into same-tile FEED when the actor already carries WHEAT.\n"
        "    dead_sell_slot frees only saturated trailing nonbuyable dead SELL slots immediately before\n"
        "    advance_sales; advance_slot_value selects the highest public-value eligible advanced sales\n"
        "    for those scarce slots while emitting the selected set in incumbent product order.\n"
        "    m1_wheat_trade runs first in the outer market tail so any bounded future WHEAT buy is visible\n"
        "    to eod_capacity_rescue, which then fails closed on shed-changing market work. B10 runs after\n"
        "    EOD so its cross-callback own-sell record includes any rescue SELL. c5_wheat_demand runs last\n"
        "    so its transition record observes the M1 self-buy while preserving B10 own-sell attribution.\n"
        "    s4_route12_seed_reserve runs after C5 and appends only the measured route-12 WHEAT\n"
        "    seed reserve after validating the final market prefix and conservative funding.\n",
        "R04 V4 install docs",
    )
    router = _replace_once(
        router,
        "    global MIRROR_HORIZON, TERMINAL_FERTILIZER, GOOSE_RESCUE\n",
        "    global MIRROR_HORIZON, TERMINAL_FERTILIZER, GOOSE_RESCUE, PLACE_DELIVERY, GOOSE_PASS_RESCUE, H3B_SHEEP_CLIP, H3E_COW_FEED_RECYCLE, V233_EOD_SERVICE, B10_PUBLIC_SUPPLY_ORDER, DEAD_SELL_SLOT, ADVANCE_SLOT_VALUE, EOD_CAPACITY_RESCUE, M1_WHEAT_TRADE, C5_WHEAT_DEMAND, S4_ROUTE12_SEED_RESERVE\n",
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
        "    if h3b_sheep_clip is not None:\n"
        "        H3B_SHEEP_CLIP = bool(h3b_sheep_clip)\n"
        "    if h3e_cow_feed_recycle is not None:\n"
        "        H3E_COW_FEED_RECYCLE = bool(h3e_cow_feed_recycle)\n"
        "    if v233_eod_service is not None:\n"
        "        V233_EOD_SERVICE = bool(v233_eod_service)\n"
        "    if b10_public_supply_order is not None:\n"
        "        B10_PUBLIC_SUPPLY_ORDER = bool(b10_public_supply_order)\n"
        "    if dead_sell_slot is not None:\n"
        "        DEAD_SELL_SLOT = bool(dead_sell_slot)\n"
        "    if advance_slot_value is not None:\n"
        "        ADVANCE_SLOT_VALUE = bool(advance_slot_value)\n"
        "    if eod_capacity_rescue is not None:\n"
        "        EOD_CAPACITY_RESCUE = bool(eod_capacity_rescue)\n"
        "    if m1_wheat_trade is not None:\n"
        "        M1_WHEAT_TRADE = bool(m1_wheat_trade)\n"
        "    if c5_wheat_demand is not None:\n"
        "        C5_WHEAT_DEMAND = bool(c5_wheat_demand)\n"
        "    if s4_route12_seed_reserve is not None:\n"
        "        S4_ROUTE12_SEED_RESERVE = bool(s4_route12_seed_reserve)\n"
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
        "    r04_b10_public_supply_order: bool = False\n"
        "    r04_h3b_sheep_clip: bool = False\n"
        "    r04_h3e_cow_feed_recycle: bool = False\n"
        "    r04_v233_eod_service: bool = False\n"
        "    r04_dead_sell_slot: bool = False\n"
        "    r04_advance_slot_value: bool = False\n"
        "    r04_eod_capacity_rescue: bool = False\n"
        "    r04_m1_wheat_trade: bool = False\n"
        "    r04_c5_wheat_demand: bool = False\n"
        "    r04_s4_route12_seed_reserve: bool = False\n\n    def __post_init__(self):",
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
        "                                 h3b_sheep_clip=bool(self.features.r04_h3b_sheep_clip),\n"
        "                                 h3e_cow_feed_recycle=bool(self.features.r04_h3e_cow_feed_recycle),\n"
        "                                 v233_eod_service=bool(self.features.r04_v233_eod_service),\n"
        "                                 b10_public_supply_order=bool(self.features.r04_b10_public_supply_order),\n"
        "                                 dead_sell_slot=bool(self.features.r04_dead_sell_slot),\n"
        "                                 advance_slot_value=bool(self.features.r04_advance_slot_value),\n"
        "                                 eod_capacity_rescue=bool(self.features.r04_eod_capacity_rescue),\n"
        "                                 m1_wheat_trade=bool(self.features.r04_m1_wheat_trade),\n"
        "                                 c5_wheat_demand=bool(self.features.r04_c5_wheat_demand),\n"
        "                                 s4_route12_seed_reserve=bool(self.features.r04_s4_route12_seed_reserve))(observation, configuration)\n",
        "TitanAgent V4 install arguments",
    )
    runtime = _replace_once(
        runtime,
        "                self.diagnostics['goose_rescue'] = bool(self.features.r04_goose_rescue)\n",
        "                self.diagnostics['goose_rescue'] = bool(self.features.r04_goose_rescue)\n"
        "                self.diagnostics['place_delivery'] = bool(self.features.r04_place_delivery)\n"
        "                self.diagnostics['goose_pass_rescue'] = bool(self.features.r04_goose_pass_rescue)\n"
        "                self.diagnostics['h3b_sheep_clip'] = bool(self.features.r04_h3b_sheep_clip)\n"
        "                self.diagnostics['h3e_cow_feed_recycle'] = bool(self.features.r04_h3e_cow_feed_recycle)\n"
        "                self.diagnostics['v233_eod_service'] = bool(self.features.r04_v233_eod_service)\n"
        "                self.diagnostics['b10_public_supply_order'] = bool(self.features.r04_b10_public_supply_order)\n"
        "                self.diagnostics['dead_sell_slot'] = bool(self.features.r04_dead_sell_slot)\n"
        "                self.diagnostics['advance_slot_value'] = bool(self.features.r04_advance_slot_value)\n"
        "                self.diagnostics['eod_capacity_rescue'] = bool(self.features.r04_eod_capacity_rescue)\n"
        "                self.diagnostics['m1_wheat_trade'] = bool(self.features.r04_m1_wheat_trade)\n"
        "                self.diagnostics['c5_wheat_demand'] = bool(self.features.r04_c5_wheat_demand)\n"
        "                self.diagnostics['s4_route12_seed_reserve'] = bool(self.features.r04_s4_route12_seed_reserve)\n",
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
