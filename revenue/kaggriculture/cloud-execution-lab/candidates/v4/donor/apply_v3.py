"""Apply the V3 integration edits to an extracted canonical TITAN package.

    python apply_v3.py <package_dir>           edit the package in place
    from apply_v3 import apply; apply(path)    same, as a library call (build_v3.py)

The lane modules and the check live in overlay/ and are copied in by build_v3.py; this
script only edits canonical files.  Every edit is an exact-string replacement asserted
to match exactly once, so it fails loudly if the canonical base moves.

Seams (from the ARGUS semantic audit, candidates/v3-g01-argus-safe/AUDIT.md):
  E11  seller-owned seam BEFORE pending accounting, in both seller variants
       (scheduler.SellScheduler.act and frozen_selected.FrozenSelected.transform)
  O01 / E20  TitanAgent._v3_post on the completed path, before _finish_production,
       so the early_capital ordering stage sees any appended land / blanked hire
  SHOP no production seam (A7); shop_arb.py ships as a tested callable only
Flags travel as deterministic TITAN-CONFIG.json keys carried in cfg['titan_v3'];
nothing reads the environment.
"""
import io
import json
import os
import sys

PARAMS = {
    "rival_dump_price_drop": 15.0,
    "rival_dump_lookback_steps": 8,
    "e11_min_future_absorption": 2,
    "e20_max_hires_per_day": 3,
    "e20_min_unwatered_crops": 3,
    "g01_early_expander_step": 144,
    "g01_land_cash_floor": 0,
    "r04_sale_horizon": 8,
    "r04_open_roundtrip": 0,
    "r04_row_order": True,
    "r04_evening_flush": True,
    "r04_sale_fertilizer": True,
    "r04_cattle_early": False,
    "r04_kill_late_water": False,
    "r04_strawberry_endgame": False,
    "r04_strawberry_max_plants": 8,
    "r04_no_late_sale_advance": True,
    "r04_no_late_sale_advance_step": 648,
    "r04_strawberry_topup": True,
    "r04_b5_carrot_fertilizer": True,
    "r04_b5_jit_fertilize": True,
    "r04_row_shed": True,
    "r04_fert_hand": True,
    "r04_dribble_dump": False,
    "r04_mirror_horizon": False,
    "r04_terminal_fertilizer": True,
    "r04_goose_rescue": True,
}

FIELDS = (
    "    # V3 integration (candidates/v3): fleet lanes behind deterministic package keys.\n"
    "    e11_rival_sell: bool = False\n"
    "    rival_model: bool = False\n"
    "    e20_hire_guard: bool = False\n"
    "    rival_dump_price_drop: float = 15.0\n"
    "    rival_dump_lookback_steps: int = 8\n"
    "    e11_min_future_absorption: int = 2\n"
    "    e20_max_hires_per_day: int = 3\n"
    "    e20_min_unwatered_crops: int = 3\n"
    "    g01_early_expander_step: int = 144\n"
    "    g01_land_cash_floor: float = 0.0\n"
    "    # L01 leader mechanisms (Grok Build #5, PR #11459) as keys; tape patches at _initialize.\n"
    "    l01_land: bool = False\n"
    "    l01_sheep: bool = False\n"
    "    l01_day0buy: bool = False\n"
    "    l01_tranche: bool = False\n"
    "    l01_leanplant: bool = False\n"
    "    # R01 shop-router plan selector (yhay81 Shop Router 0909, Apache-2.0): whole-route delegate.\n"
    "    r01_shop_router: bool = False\n"
    "    # R02 route bank: the same tapes seated as the canonical MAIN route (TITAN keeps the market).\n"
    "    r02_route_bank: bool = False\n"
    "    # R03 complete published shop-router policy (base + nine layers, Apache-2.0): whole-route delegate.\n"
    "    r03_full_router: bool = False\n"
    "    # R04 the R03 policy with the E184 sale window outermost (Gluzdov, Apache-2.0): whole-route delegate.\n"
    "    r04_sale_window: bool = False\n"
    "    r04_sale_horizon: int = 8\n"
    "    r04_open_roundtrip: int = 0\n"
    "    r04_row_order: bool = True\n"
    "    r04_evening_flush: bool = True\n"
    "    r04_sale_fertilizer: bool = True\n"
    "    r04_cattle_early: bool = False\n"
    "    r04_kill_late_water: bool = False\n"
    "    r04_strawberry_endgame: bool = False\n"
    "    r04_strawberry_max_plants: int = 8\n"
    "    r04_no_late_sale_advance: bool = True\n"
    "    r04_no_late_sale_advance_step: int = 648\n"
    "    r04_strawberry_topup: bool = True\n"
    "    r04_b5_carrot_fertilizer: bool = True\n"
    "    r04_b5_jit_fertilize: bool = True\n"
    "    r04_row_shed: bool = True\n"
    "    r04_fert_hand: bool = True\n"
    "    r04_dribble_dump: bool = False\n"
    "    r04_mirror_horizon: bool = False\n"
    "    r04_terminal_fertilizer: bool = True\n"
    "    r04_goose_rescue: bool = True\n"
)

L01_KEYS = ("l01_land", "l01_sheep", "l01_day0buy", "l01_tranche", "l01_leanplant")

RUNTIME_METHODS = (
    "    # ------------------------------------------------------------ V3 lanes\n"
    "    def _v3_active(self):\n"
    "        f = self.features\n"
    "        return bool(f.e11_rival_sell or f.rival_model or f.e20_hire_guard\n"
    "                    or f.l01_land or f.l01_sheep or f.l01_day0buy or f.l01_tranche or f.l01_leanplant\n"
    "                    or f.r01_shop_router or f.r02_route_bank or f.r03_full_router\n"
    "                    or f.r04_sale_window or f.r04_kill_late_water\n"
    "                    or f.r04_strawberry_endgame)\n\n"
    "    def _v3_config(self):\n"
    "        \"\"\"Deterministic package keys for the V3 lanes, carried inside the game config.\"\"\"\n"
    "        f = self.features\n"
    "        return {'e11_rival_sell': bool(f.e11_rival_sell), 'rival_model': bool(f.rival_model),\n"
    "                'e20_hire_guard': bool(f.e20_hire_guard),\n"
    "                'params': {'rival_dump_price_drop': float(f.rival_dump_price_drop),\n"
    "                           'rival_dump_lookback_steps': int(f.rival_dump_lookback_steps),\n"
    "                           'e11_min_future_absorption': int(f.e11_min_future_absorption),\n"
    "                           'e20_max_hires_per_day': int(f.e20_max_hires_per_day),\n"
    "                           'e20_min_unwatered_crops': int(f.e20_min_unwatered_crops),\n"
    "                           'g01_early_expander_step': int(f.g01_early_expander_step),\n"
    "                           'g01_land_cash_floor': float(f.g01_land_cash_floor)}}\n\n"
    "    def _v3_post(self, obs, cfg, output):\n"
    "        \"\"\"V3 lanes O01 (queue-safe BUY_LAND append) and E20 (low-demand HIRE limiter).\n\n"
    "        Runs on the completed path before _finish_production so the early_capital\n"
    "        ordering stage sees the edited queue.  Identity when both keys are off.  A\n"
    "        raised error keeps the selected action and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        v3 = cfg.get('titan_v3') or {}\n"
    "        if not (v3.get('rival_model') or v3.get('e20_hire_guard')):\n"
    "            return output\n"
    "        params = dict(cfg)\n"
    "        params.update(v3.get('params') or {})\n"
    "        report = {}\n"
    "        try:\n"
    "            if v3.get('rival_model'):\n"
    "                from rival_model import apply_rival_model\n"
    "                previous = getattr(self, '_v3_prev_prices', None)\n"
    "                output, report['rival_model'] = apply_rival_model(obs, output, previous, params, enabled=True)\n"
    "                self._v3_prev_prices = dict((obs.get('market') or {}).get('prices') or {})\n"
    "            if v3.get('e20_hire_guard'):\n"
    "                from e20_hire_guard import apply_hire_guard\n"
    "                output, report['e20_hire_guard'] = apply_hire_guard(obs, output, params, enabled=True)\n"
    "        except Exception as error:\n"
    "            report['error'] = type(error).__name__\n"
    "        self.diagnostics['v3'] = report\n"
    "        return output\n\n"
    "    def _v3_l01_install(self):\n"
    "        \"\"\"V3 lane L01: patch the route tapes once (land / sheep / day0buy / leanplant keys).\n\n"
    "        Runs at the end of _initialize, after the controller and its tapes exist.  With\n"
    "        every l01 key off the tapes are untouched and the reason L01_noop:flag_off is\n"
    "        recorded.  A raised error keeps the canonical tapes and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        try:\n"
    "            from l01_mechanics import flags_from_features, install\n"
    "            state = install(self, flags_from_features(self.features))\n"
    "            self.diagnostics['v3_l01'] = {'activations': dict(state['activations']),\n"
    "                                          'reasons': list(state['reasons'])}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_l01'] = {'activations': {}, 'reasons': ['V3_L01_ERROR_' + type(error).__name__]}\n\n"
    "    def _v3_r01_act(self, observation, configuration, invoked, entry_started):\n"
    "        \"\"\"V3 lane R01: whole-route delegate to the shop-router plan selector (key r01_shop_router).\n"
    "\n"
    "        Runs before any canonical state is touched; the canonical controller is never built\n"
    "        while the key is on.  A raised error returns a legal PASS (the terminal liquidation\n"
    "        fallback on the last decision step) and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        started = invoked if entry_started is None else min(invoked, float(entry_started))\n"
    "        cpu_started = time.process_time()\n"
    "        cfg = dict(configuration or {})\n"
    "        obs = dict(observation)\n"
    "        obs['step'] = int(obs['step']) if obs.get('step') is not None else int(obs['day'])*int(cfg.get('turnsPerDay', 24))+int(obs['hour'])\n"
    "        self.selected = None\n"
    "        self.post = None\n"
    "        self.diagnostics = {'consumer': self.features.consumer, 'parent_calls': 0,\n"
    "                            'entrypoint_prelude_seconds': invoked-started, 'route': 'r01_shop_router'}\n"
    "        try:\n"
    "            from r01_shop_router import install\n"
    "            output = install(self).act(obs)\n"
    "            self.diagnostics['r01_plan'] = self._v3_r01.policy.players[int(obs['player'])].plan\n"
    "            self.diagnostics['status'] = 'completed'\n"
    "        except Exception as error:\n"
    "            last = int(cfg.get('episodeSteps', 720))-2\n"
    "            output = (deadline.terminal_liquidation_fallback(obs, cfg) if obs['step'] == last\n"
    "                      else deadline.legal_pass(obs))\n"
    "            self.diagnostics.update(status='r01_error', error=type(error).__name__)\n"
    "        self.diagnostics.update(elapsed_seconds=time.perf_counter()-started,\n"
    "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
    "        return output\n"
    "\n"
    "    def _v3_r03_act(self, observation, configuration, invoked, entry_started):\n"
    "        \"\"\"V3 lanes R03 / R04: whole-route delegate to the complete published shop-router policy.\n"
    "\n"
    "        Key r03_full_router runs the base rules and the nine additive layers exactly as published;\n"
    "        key r04_sale_window runs the same policy with the E184 sale window outermost, at horizon\n"
    "        r04_sale_horizon.  Both run on the observation and configuration the entrypoint received;\n"
    "        the canonical controller is never built while either key is on.  A raised error returns a\n"
    "        legal PASS (the terminal liquidation fallback on the last decision step) and is recorded.\n"
    "        \"\"\"\n"
    "        started = invoked if entry_started is None else min(invoked, float(entry_started))\n"
    "        cpu_started = time.process_time()\n"
    "        cfg = dict(configuration or {})\n"
    "        obs = dict(observation)\n"
    "        obs['step'] = int(obs['step']) if obs.get('step') is not None else int(obs['day'])*int(cfg.get('turnsPerDay', 24))+int(obs['hour'])\n"
    "        route = 'r04_sale_window' if self.features.r04_sale_window else 'r03_full_router'\n"
    "        self.selected = None\n"
    "        self.post = None\n"
    "        self.diagnostics = {'consumer': self.features.consumer, 'parent_calls': 0,\n"
    "                            'entrypoint_prelude_seconds': invoked-started, 'route': route}\n"
    "        try:\n"
    "            if route == 'r04_sale_window':\n"
    "                from r04_full_router import install\n"
    "                output = install(self, int(self.features.r04_sale_horizon),\n"
    "                                 int(self.features.r04_open_roundtrip),\n"
    "                                 bool(self.features.r04_row_order),\n"
    "                                 bool(self.features.r04_evening_flush),\n"
    "                                 bool(self.features.r04_sale_fertilizer),\n"
    "                                 bool(self.features.r04_cattle_early),\n"
    "                                 bool(self.features.r04_kill_late_water),\n"
    "                                 bool(self.features.r04_strawberry_endgame),\n"
    "                                 int(self.features.r04_strawberry_max_plants),\n"
    "                                 bool(self.features.r04_no_late_sale_advance),\n"
    "                                 int(self.features.r04_no_late_sale_advance_step),\n"
    "                                 bool(self.features.r04_strawberry_topup),\n"
    "                                 bool(self.features.r04_b5_carrot_fertilizer),\n"
    "                                 bool(self.features.r04_b5_jit_fertilize),\n"
    "                                 bool(self.features.r04_row_shed),\n"
    "                                 fert_hand=bool(self.features.r04_fert_hand),\n"
    "                                 dribble_dump=bool(self.features.r04_dribble_dump),\n"
    "                                 mirror_horizon=bool(self.features.r04_mirror_horizon),\n"
    "                                 terminal_fertilizer=bool(self.features.r04_terminal_fertilizer),\n"
    "                                 goose_rescue=bool(self.features.r04_goose_rescue))(observation, configuration)\n"
    "                self.diagnostics['sale_horizon'] = int(self.features.r04_sale_horizon)\n"
    "                self.diagnostics['open_roundtrip'] = int(self.features.r04_open_roundtrip)\n"
    "                self.diagnostics['row_order'] = bool(self.features.r04_row_order)\n"
    "                self.diagnostics['evening_flush'] = bool(self.features.r04_evening_flush)\n"
    "                self.diagnostics['sale_fertilizer'] = bool(self.features.r04_sale_fertilizer)\n"
    "                self.diagnostics['cattle_early'] = bool(self.features.r04_cattle_early)\n"
    "                self.diagnostics['kill_late_water'] = bool(self.features.r04_kill_late_water)\n"
    "                self.diagnostics['strawberry_endgame'] = bool(self.features.r04_strawberry_endgame)\n"
    "                self.diagnostics['strawberry_max_plants'] = int(self.features.r04_strawberry_max_plants)\n"
    "                self.diagnostics['no_late_sale_advance'] = bool(self.features.r04_no_late_sale_advance)\n"
    "                self.diagnostics['no_late_sale_advance_step'] = int(self.features.r04_no_late_sale_advance_step)\n"
    "                self.diagnostics['strawberry_topup'] = bool(self.features.r04_strawberry_topup)\n"
    "                self.diagnostics['b5_carrot_fertilizer'] = bool(self.features.r04_b5_carrot_fertilizer)\n"
    "                self.diagnostics['b5_jit_fertilize'] = bool(self.features.r04_b5_jit_fertilize)\n"
    "                self.diagnostics['row_shed'] = bool(self.features.r04_row_shed)\n"
    "                self.diagnostics['fert_hand'] = bool(self.features.r04_fert_hand)\n"
    "                self.diagnostics['dribble_dump'] = bool(self.features.r04_dribble_dump)\n"
    "                self.diagnostics['mirror_horizon'] = bool(self.features.r04_mirror_horizon)\n"
    "                self.diagnostics['terminal_fertilizer'] = bool(self.features.r04_terminal_fertilizer)\n"
    "                self.diagnostics['goose_rescue'] = bool(self.features.r04_goose_rescue)\n"
    "            else:\n"
    "                from r03_full_router import install\n"
    "                output = install(self)(observation, configuration)\n"
    "            self.diagnostics['status'] = 'completed'\n"
    "        except Exception as error:\n"
    "            last = int(cfg.get('episodeSteps', 720))-2\n"
    "            output = (deadline.terminal_liquidation_fallback(obs, cfg) if obs['step'] == last\n"
    "                      else deadline.legal_pass(obs))\n"
    "            self.diagnostics.update(status=route + '_error', error=type(error).__name__)\n"
    "        self.diagnostics.update(elapsed_seconds=time.perf_counter()-started,\n"
    "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
    "        return output\n"
    "\n"
    "    def _v3_r02_install(self):\n"
    "        \"\"\"V3 lane R02: seat the shop-router tapes as the MAIN route contents (key r02_route_bank).\n"
    "\n"
    "        Runs at the end of _initialize, after the controller exists, beside the L01 patch.  With\n"
    "        the key off the route is untouched and R02_noop:flag_off is recorded.  A raised error\n"
    "        keeps the canonical route and is recorded, never swallowed.\n"
    "        \"\"\"\n"
    "        try:\n"
    "            from r02_route_bank import install\n"
    "            state = install(self, bool(self.features.r02_route_bank))\n"
    "            self.diagnostics['v3_r02'] = {'plan': state.get('plan'), 'replaced': state.get('replaced'),\n"
    "                                          'reasons': list(state.get('reasons') or [])}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_r02'] = {'plan': None, 'reasons': ['V3_R02_ERROR_' + type(error).__name__]}\n"
    "\n"
    "    def _v3_r02_step(self, obs):\n"
    "        \"\"\"V3 lane R02: the published plan switches at steps 144 and 648. Identity when off.\"\"\"\n"
    "        if not self.features.r02_route_bank:\n"
    "            return\n"
    "        try:\n"
    "            from r02_route_bank import step\n"
    "            state = step(self, obs, True)\n"
    "            self.diagnostics['v3_r02_step'] = {'plan': state.get('plan'), 'endgame': state.get('endgame'),\n"
    "                                               'replaced': state.get('replaced')}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_r02_step'] = {'error': type(error).__name__}\n"
    "\n"
    "    def _v3_post_final(self, obs, cfg, output):\n"
    "        \"\"\"V3 lane L01 tranche: live SELL enlargement after _finish_production (as measured).\"\"\"\n"
    "        if not self.features.l01_tranche:\n"
    "            return output\n"
    "        try:\n"
    "            from collections import Counter\n"
    "            from l01_mechanics import apply_tranche, flags_from_features, shed_snapshot\n"
    "            activations = Counter()\n"
    "            output = apply_tranche(output, obs, flags_from_features(self.features), activations,\n"
    "                                   shed=shed_snapshot(self, obs))\n"
    "            self.diagnostics['v3_l01_tranche'] = {'activations': dict(activations)}\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_l01_tranche'] = {'activations': {}, 'error': type(error).__name__}\n"
    "        return output\n\n"
)

SELLER_METHOD = (
    "    def _v3_e11_before_pending(self, obs, config, out, now):\n"
    "        \"\"\"V3 lane E11 at the seller-owned seam before pending accounting (ARGUS A3).\"\"\"\n"
    "        v3=config.get('titan_v3') if isinstance(config,dict) else None\n"
    "        if not v3 or not v3.get('e11_rival_sell'):return out\n"
    "        try:\n"
    "            from e11_rival_sell import apply_e11\n"
    "            cfg=dict(config);cfg.update(v3.get('params') or {})\n"
    "            history=list(getattr(self,'_v3_price_history',[]))\n"
    "            out,report=apply_e11(obs,out,history,cfg,absorption,enabled=True)\n"
    "            self.diagnostics['v3_e11']=report\n"
    "            prices=dict((obs.get('market') or {}).get('prices') or {})\n"
    "            history.append((int(now),prices))\n"
    "            lookback=max(0,int(cfg.get('rival_dump_lookback_steps',8)))\n"
    "            self._v3_price_history=[entry for entry in history if 0<=int(now)-int(entry[0])<=lookback]\n"
    "            return out\n"
    "        except Exception as error:\n"
    "            self.diagnostics['v3_e11']={'enabled':True,'changed':False,'reason':'V3_E11_ERROR_'+type(error).__name__}\n"
    "            return out\n\n"
)

RELEASE_NOTE = (
    "\n## V3 integration lanes (candidates/v3)\n\n"
    "The V3 tree carries the fleet lanes inside this one package behind deterministic\n"
    "`TITAN-CONFIG.json` keys, all shipped off: `e11_rival_sell` (defer a SELL of a\n"
    "product whose public price dropped, when exact future absorption ticks still cover\n"
    "it; seller-owned seam before pending accounting in both seller variants),\n"
    "`rival_model` (public-state rival archetype; appends one BUY_LAND only into a free\n"
    "market slot, never edits SELLs) and `e20_hire_guard` (blanks every HIRE beyond the\n"
    "remaining low-demand allowance, preserving queue positions). Parameters:\n"
    "`rival_dump_price_drop`, `rival_dump_lookback_steps`, `e11_min_future_absorption`,\n"
    "`e20_max_hires_per_day`, `e20_min_unwatered_crops`, `g01_early_expander_step`,\n"
    "`g01_land_cash_floor`. The lanes descend from the TESSERA designs, the G01 patches\n"
    "(PR #11371) and the ARGUS semantic-safety repair (candidates/v3-g01-argus-safe).\n"
    "The shop multiplier ships as a scoring-only callable with no production seam. A\n"
    "panel variant is a copy of this tree with keys flipped in `TITAN-CONFIG.json`; no\n"
    "environment variable selects anything. With every key off the runtime path is the\n"
    "canonical archive's. Wiring and contract checks: `checks/test_v3_features.py`.\n"
    "Playing strength per key is measured by the V25 fleet panels recorded in\n"
    "`candidates/v3/V3-MANIFEST.json`; no strength claim accompanies these bytes.\n"
    "\n"
    "L01 leader mechanisms (Grok Build #5, PR #11459) ride the same tree as keys, all\n"
    "shipped off: `l01_land` (BUY_LAND posted at tape steps 74 and 98, the 150/265 posts\n"
    "kept), `l01_sheep` (COW purchases after step 1 become SHEEP), `l01_day0buy` (the\n"
    "step-0 market becomes the SpaTaro product basket), `l01_leanplant` (the last 92\n"
    "PLANT WHEAT units become PASS) and `l01_tranche` (from day 28 the returned queue\n"
    "sells WHEAT up to 57 and CARROT up to 32 and packs the other shed products). The\n"
    "four tape keys patch the Arlene MAIN routes once at `TitanAgent._initialize`; the\n"
    "tranche edits the queue after `_finish_production`. Checks: `checks/test_v3_l01.py`.\n"
    "\n"
    "R01 rides the same tree as a whole-route key, shipped off: `r01_shop_router` delegates\n"
    "every turn to the shop-router plan selector (yhay81 Shop Router 0909, Apache-2.0; 13\n"
    "complete 719-turn tapes in `r01_tapes.py`, plan chosen from the first two unlocked shops\n"
    "at step 144, plan 2 from step 648, weed repair, one-turn sale advance, last-turn\n"
    "liquidation). The delegate runs before any canonical state is built, so with the key on\n"
    "the canonical controller never runs; with the key off the runtime path is untouched.\n"
    "Attribution is appended to NOTICE. Checks: `checks/test_v3_r01.py`.\n"
    "\n"
    "R02 (`r02_route_bank`, shipped off) seats the same tapes as the contents of the\n"
    "canonical MAIN route instead of delegating: plan 0 at initialize, the shop-pair plan\n"
    "tail from step 144, the plan 2 tail from step 648, each replacement leaving every\n"
    "already-played step byte-identical. The frozen seller, pending accounting and every\n"
    "other canonical stage then run on that route unchanged. Checks: `checks/test_v3_r02.py`.\n"
    "\n"
    "R03 (`r03_full_router`, shipped off) delegates every turn to the complete published\n"
    "shop-router policy: the same base rules and tapes as R01 plus the nine additive layers\n"
    "shipped with it (V216 hire funding, V217 idle-farmer feed rescue, V218 terminal fertilizer\n"
    "collection, V219 late tomato investment, V224 sales-first market ordering, V226 bounded\n"
    "wheat top-up, V231 bounded livestock substitution, V233 six-sheep SE investment, V234\n"
    "sheep feed rescue). The module body is the published Apache-2.0 file with its inline tape\n"
    "blob replaced by `r01_tapes` (byte-identical tapes); no rule is changed. Checks:\n"
    "`checks/test_v3_r03.py`.\n"
    "\n"
    "R04 (`r04_sale_window`, shipped off; `r04_sale_horizon`, default 8) runs the R03 policy with\n"
    "Dmitrii Gluzdov's E184 Sale Window appended verbatim as the outermost layer: from step 288\n"
    "the one-turn sale advance is replaced by reservations that sell now the units the tape plans\n"
    "to sell over the next `r04_sale_horizon` own actions, bounded by projected stock, never\n"
    "across a 72-step route boundary, never past an upcoming pickup or purchase of the item,\n"
    "with per-due-step debts so no advanced unit is sold twice. `r04_open_roundtrip` (default 0)\n"
    "replaces the published step-0 wheat wash trade (BUY 13, SELL 13, BUY 13) with BUY 13, BUY n,\n"
    "SELL n: the same net +13 WHEAT, but the market pairs both players' rows index by index, so\n"
    "the larger round trip moves a few coins from a rival whose rows mirror the tape; 0 keeps the\n"
    "published opening. It ships at 0: against openers that sell a lot of wheat at step 0 every\n"
    "round trip size measured (10-45) gives up 67-103 coins, enough to stall the tape's early buys.\n"
    "`r04_row_order` (default True) sorts the leading SELL rows by the price drop\n"
    "each causes on the pinned default price curves, steepest first, so a contested unit clears\n"
    "before a rival's same-item row at a later index; quantities are unchanged. `r04_evening_flush`\n"
    "(default True) sells at hours 21-23 the projected shed stock of WOOL, MILK, STRAWBERRY and MELON,\n"
    "which no farm action consumes, ahead of the other rows. `r04_sale_fertilizer` (default True)\n"
    "lets the sale window advance FERTILIZER, which the published window skips with WHEAT.\n"
    "`r04_cattle_early` (default True) also runs V231's bounded sheep-to-cow swap at the day-8\n"
    "purchase (steps 190-215) when both of the first two shops consume MILK and neither is the\n"
    "YARN_STORE; the published day-9 window is unchanged. With either key on the canonical\n"
    "controller never runs; R04 takes precedence over R03, and both over R01. Attribution is\n"
    "appended to NOTICE. Checks: `checks/test_v3_r04.py`.\n"
    "\n"
    "R04 lane L1 (`r04_kill_late_water`, shipped off) suppresses WATER commands that provably\n"
    "cannot pay off at steps 672-718: a WATER on a tile with no planted crop (LOCKED / SOIL /\n"
    "WEED / None / COOP / PASTURE), on a tile already watered today (watering is day-granular;\n"
    "replay evidence shows the second watering changes nothing), or on a crop whose\n"
    "max_lifespan_step is at or before the current step. The suppressed worker becomes PASS:\n"
    "the tape route has no live worker reassignment, so the tape issues the next step's orders\n"
    "normally. No other command is touched and HARVEST is never preferred. The layer never\n"
    "raises; a malformed observation leaves the action unchanged. Checks:\n"
    "`checks/test_v3_r04_late_water.py`.\n"
    "\n"
    "V3.1 lane L2 `r04_strawberry_endgame` (shipped off; `r04_strawberry_max_plants`,\n"
    "default 8) converts up to `r04_strawberry_max_plants` [\"PLANT\", \"WHEAT\"] orders in\n"
    "steps [576, 648] into [\"PLANT\", \"STRAWBERRY\"], at most 2 per step, only while\n"
    "strawberry seeds are held at that step; with no seeds the action is unchanged and\n"
    "no BUY_SEED rows are added, so the wheat engine's budget is untouched. WATER,\n"
    "HARVEST and DROP are tile-agnostic, so a converted planting keeps the tape's\n"
    "watering / harvest / drop cadence and the evening-flush strawberry sale working.\n"
    "Honest accounting: replay-verified on the 31 audited episodes, strawberry seeds\n"
    "are 0 at every late step (the tape's ~35 seeds are planted on days 5-11), so the\n"
    "seed-gated conversion is a no-op there and the expected delta-margin is ~0; per\n"
    "the engine strawberry is an ongoing crop with first_yield_day 10, so a day 24-27\n"
    "planting cannot yield before step 718 anyway. Non-WHEAT plantings and market rows\n"
    "are never touched. Fleet deconfliction: strawberry throughput and sale-size\n"
    "optimization are ASTRA · GPT-5.6 SOL's claimed H4 lane (LIVE-R04 port on\n"
    "titan/v3.1-20260911); this lane is strictly production/staging timing and composes\n"
    "with it. Checks: `checks/test_v3_r04_strawberry.py`.\n"
"\n"
"Lane L3 (V3.1): `r04_no_late_sale_advance` (shipped on, against off-tape rivals) gates the E184 reservation\n"
"call site in the R04 `agent()` wrapper: at steps >= `r04_no_late_sale_advance_step`\n"
"(default 648) no future tape-planned sale is pulled forward into today's SELL rows;\n"
"the tape's own late SELL rows are published tape behavior, not advancement, and are\n"
"kept. Debts recorded before the threshold still settle through\n"
"`subtract_advanced_sales()`. This is the port of the peer B10 lane: ASTRA and\n"
"GPT-5.6 SOL's S20-R01 ablation on the canonical v3 optimizer found that disabling\n"
"sale advancement at absolute step >= 648 measured +328.60 own and +289.90 margin\n"
"(48/48 positive); the +289.90 margin is the prior for this lane and must be re-gated\n"
"on the R04 route. With the flag off the reservation path is byte-identical. Checks:\n"
"`checks/test_v3_r04_no_late_advance.py`.\n"
"The lane applies only against a rival that does not follow the public Shop Router tape:\n"
"`rival_on_tape()` counts, over the shared opening (steps 1-143), how often the rival's\n"
"farmer stands where ours does; at >= 80% the reservation is kept. Checks:\n"
"`checks/test_v3_r04_l3_rival_gate.py`.\n"
"\n"
"Lane H4 (V3.1, ASTRA · GPT-5.6 SOL): `r04_strawberry_topup` (shipped on) reuses a current\n"
"STRAWBERRY SELL row as the E184 reservation sink for already-planned future strawberry\n"
"sales, bounded by projected shed stock, and books the same per-due-step debt E184\n"
"subtracts later (overlay/r04_h4_strawberry.py). It runs first after the policy in\n"
"v3_agent(). Checks: `checks/test_v31_h4_strawberry.py`.\n"
"\n"
"Shipping evidence: the 41 live games of submission 56159263, each replayed on its own\n"
"seed with the opponent's recorded play pinned (V3.0 reproduces every recorded reward).\n"
"Against V3.1: H4 +32.6, rival-gated L3 +36.3, both together +68.9 margin per game\n"
"(34 better, 4 worse).\n"
"\n"
"Lane B5 (V3.1, ASTRA · GPT-5.6 SOL): `r04_b5_carrot_fertilizer` and `r04_b5_jit_fertilize`\n"
"(both shipped on) spend authored PASS turns on fertilizer that pays: a CARROT top-up where\n"
"the worker already stands (overlay/b5_fertilize.py, the #12499 functions verbatim) and\n"
"just-in-time fertilizer before a yield-bearing WATER on the worker's own tile\n"
"(overlay/jit_pass_fertilize.py, #12428 verbatim). Applied last in v3_agent(). Shipping\n"
"evidence on the same 41 live games, against the V3.1 package with H4 and gated L3: +106.0\n"
"margin per game, better in all 41. Checks: `checks/test_v31_b5_fertilize.py`.\n"
"\n"
"Key `r04_row_shed` (V3.1, shipped on; from the Gemini endgame lane): ROW_ORDER prices each\n"
"leading SELL row at min(order quantity, projected shed stock) instead of the order quantity,\n"
"so a tape row asking for more units than the shed holds is ranked by the units it can sell.\n"
"Field gate (official reference evaluator, 30 v25 shards x 32 seeds x both seats, 1,920 games\n"
"against 16 published agents), the a6120d0e R04 modules with r04_cattle_early off: +281.4 margin\n"
"per game, better in 1,912 of 1,920 games, 1911 W / 9 L against 1908 W / 2 T / 10 L without it.\n"
"Checks: `checks/test_v31_row_shed.py`. The production seam keeps raw market slots and tail\n"
"indices (an empty row ends the leading block) and falls back to requested-quantity pricing for\n"
"the whole block on incomplete or non-int projected-shed evidence (the reviewed #12551 contract).\n"
"\n"
"`r04_cattle_early` ships off. S34 field gate on this package's modules (official reference\n"
"evaluator, 1,280 games per arm against published agents): row shed with cattle_early off\n"
"1273 W / 7 L, +540.0 margin per game against V3.0; the top-40 leaderboard bench (160 recorded\n"
"games of the current top-40 teams, their play pinned) 96 W / 64 L for the same build.\n"
"\n"
"Key `r04_fert_hand` (V3.1, shipped on): the endgame fertilizer hand (overlay/r04_fert_hand.py).\n"
"On days 24-28 one extra hand is hired after the tape's own hires when the carrot price pays for\n"
"it (the n-th hire of a day costs fib(n)); it picks up FERTILIZER at the shed, buying the\n"
"shortfall, and fertilizes the tape's young CARROTs before their yield-bearing WATER (+1 carrot\n"
"per tile). The stack underneath never sees the extra hand. Seen on the ladder in senkin13's,\n"
"Syed Asad Ali's and Terry Luo's play. Live bench (80 games of submission 56159263, opponents\n"
"pinned), on the row-shed modules with cattle_early off: +439.4 margin per game, better in 55,\n"
"worse in none, 69-11 -> 70-10. Field gate (official reference evaluator on the v25 shards, 32\n"
"seeds x both seats per shard, 3,008 games against 16 published agents over two seed blocks,\n"
"base = 8e3d R04 modules with row-shed and cattle off): +320.3 margin per game, better in 2,109,\n"
"worse in 2, no result changed. Checks: `checks/test_v31_fert_hand.py`.\n"
"\n"
"Key `r04_dribble_dump` (V3.1 lane E1, Muse / Riot, shipped off): per-step caps on the SELL rows of\n"
"the fragile goods, STRAWBERRY 15, MILK 15, WOOL 12 and MELON 30 units, cumulative across rows,\n"
"and no fragile sale on days 0-2 (overlay/r04_dribble_dump.py). A good printing $1 passes through,\n"
"and WHEAT, EGG, CARROT, TOMATO and FERTILIZER rows are never touched; the evening flush and the\n"
"step-718 liquidation still sweep the shed. It runs after H4 and right before ROW_ORDER. Engine\n"
"measurement: 50 WOOL dumped at once $7,655, dribbled $8,978; 60 MILK $5,886 against $6,640.\n"
"Gate: clean trajectory-matched cells 9+ / 0- / 0=, mean +15.1, 8.2% of steps rewritten. The V3.1\n"
"stack with E1 measured +1,477 per game against V3.0, 16 of 16 cells positive.\n"
"Checks: `checks/test_v31_dribble_dump.py`.\n"
"\n"
"Lanes by ASTRA · GPT-5.6 SOL around the whole R04 agent, applied in v3_agent() the way each\n"
"was gated (modules are the reviewed donor blobs verbatim):\n"
"\n"
"Key `r04_goose_rescue` (H3c, shipped on; overlay/h3c_goose_eod_cap_rescue.py, blob 2044d6cf,\n"
"#12473 / #12555): at hour 23 a COLLECT_FERTILIZER on a fed and cared GOOSE whose held eggs would\n"
"clip at max_held 4 in tonight's production becomes HARVEST, guarded by the standard config, a\n"
"whole-farm shed-capacity bound, no stacked worker and no same-turn animal or product purchase.\n"
"ASTRA gate: Arlene 10+ / 6= / 0-, mean +110.4; ApexV7 6+ / 2= / 0-, +144.5; Reyhan 4+ / 4= / 0-,\n"
"+102.9. Final-stack gate on this package's modules: field (official reference evaluator, 21 v25\n"
"shards, 1,344 games) +142.1 margin per game, better in 1,030, 1340-4 against 1338-6; live bench\n"
"(88 games of submission 56159263, opponents pinned) +125.7 per game, better in 63, 77-11.\n"
"\n"
"Key `r04_terminal_fertilizer` (B9, shipped on; overlay/b9_terminal_fertilizer.py, #12538 blob\n"
"ed8d6923): at steps 716-717 a literal PASS by a worker beside the shed on an animal with fertilizer\n"
"available becomes COLLECT_FERTILIZER; at 718, when it collected, SELL FERTILIZER rows trail the\n"
"other rows inside the executable market prefix. ASTRA gate: Arlene 12+ / 4= / 0-, mean +4.75.\n"
"Final-stack gate: field +1.6 per game, better in 882, worse in none; live bench +2.0, 59 / 0.\n"
"\n"
"Key `r04_mirror_horizon` (B11, shipped off; overlay/b11_mirror_horizon.py, blob 94b270f3): sale\n"
"horizon 10 for a callback after eight consecutive exact public farm mirrors.\n"
"Checks: `checks/test_v31_astra_lanes.py`.\n"
)


R01_NOTICE = (
    "\n\nV3 lane R01 (candidates/v3/overlay/r01_shop_router.py, r01_tapes.py)\n"
    "Shop Router 0909 policy and its 13 action tapes: yhay81,\n"
    "https://www.kaggle.com/code/yhay81/shop-router-0909, Apache License 2.0.\n"
    "Sell timing and shed projection: aurax7,\n"
    "https://www.kaggle.com/code/aurax7/kaggriculture-reactive-router, Apache License 2.0.\n"
    "Lossless single-file tape packaging: prvsiyan,\n"
    "https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-soil-remembers-rain, Apache License 2.0.\n"
    "Carried behind the TITAN-CONFIG.json key r01_shop_router, shipped false.\n"
)


R03_NOTICE = (
    "\n\nV3 lanes R03 / R04 (candidates/v3/overlay/r03_full_router.py, r04_full_router.py)\n"
    "Complete published shop-router policy, Apache License 2.0:\n"
    "base policy and its 13 action tapes by yhay81, https://www.kaggle.com/code/yhay81/shop-router-0909;\n"
    "single-file packaging and the V216-V234 layers by prvsiyan,\n"
    "https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-soil-remembers-rain;\n"
    "sell timing and shed projection by aurax7; terminal fertilizer collection inspired by\n"
    "Dmitrii Gluzdov, https://www.kaggle.com/code/dmitriigluzdov/kaggriculture-seven-turn-rescue-best-lb-2800.\n"
    "E184 Sale Window (R04) by Dmitrii Gluzdov, Apache License 2.0,\n"
    "https://www.kaggle.com/code/dmitriigluzdov/kaggriculture-two-coins-one-sheep-lb-2700.\n"
    "Both modules retain the published license text inline. Carried behind the TITAN-CONFIG.json\n"
    "keys r03_full_router and r04_sale_window, shipped false.\n"
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

    runtime = read("titan_runtime.py")
    runtime = _replace_once(runtime, "\n\n    def __post_init__(self):", "\n" + FIELDS + "\n    def __post_init__(self):", "Features fields")
    runtime = _replace_once(
        runtime,
        "        cfg = dict(configuration or {})\n        obs = dict(observation)\n",
        "        cfg = dict(configuration or {})\n"
        "        if self._v3_active():\n"
        "            # V3 lanes travel with the package configuration, never the environment.\n"
        "            cfg['titan_v3'] = self._v3_config()\n"
        "        obs = dict(observation)\n",
        "cfg injection",
    )
    runtime = _replace_once(
        runtime,
        "        self._commit_seller_state(seller_checkpoint)\n"
        "        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,\n"
        "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
        "        output = self._finish_production(obs, output, cfg)\n",
        "        self._commit_seller_state(seller_checkpoint)\n"
        "        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,\n"
        "                                act_cpu_seconds=time.process_time()-cpu_started)\n"
        "        output = self._v3_post(obs, cfg, output)\n"
        "        output = self._finish_production(obs, output, cfg)\n"
        "        output = self._v3_post_final(obs, cfg, output)\n",
        "post hook",
    )
    runtime = _replace_once(
        runtime,
        "        self._restore_seller_state()\n        self.ready = True\n",
        "        self._restore_seller_state()\n        self._v3_l01_install()\n        self._v3_r02_install()\n        self.ready = True\n",
        "l01 install seam",
    )
    runtime = _replace_once(
        runtime,
        "        invoked = time.perf_counter()\n"
        "        # The canonical entrypoint shares its start clock with this same timer.\n",
        "        invoked = time.perf_counter()\n"
        "        if self.features.r03_full_router or self.features.r04_sale_window:\n"
        "            return self._v3_r03_act(observation, configuration, invoked, entry_started)\n"
        "        if self.features.r01_shop_router:\n"
        "            return self._v3_r01_act(observation, configuration, invoked, entry_started)\n"
        "        # The canonical entrypoint shares its start clock with this same timer.\n",
        "r01/r03/r04 delegate seam",
    )
    runtime = _replace_once(
        runtime,
        "                if not self.ready:\n"
        "                    self._initialize()\n"
        "                if self.history is not None:\n",
        "                if not self.ready:\n"
        "                    self._initialize()\n"
        "                self._v3_r02_step(obs)\n"
        "                if self.history is not None:\n",
        "r02 step seam",
    )
    runtime = _replace_once(runtime, "    __call__ = act\n", RUNTIME_METHODS + "    __call__ = act\n", "v3 methods")
    write("titan_runtime.py", runtime)

    sched = read("scheduler.py")
    sched = _replace_once(sched, "    def act(self, obs, config=None):\n", SELLER_METHOD + "    def act(self, obs, config=None):\n", "scheduler method")
    sched = _replace_once(
        sched,
        "        out['market']=market\n        for item,q in targets.items():\n",
        "        out['market']=market\n        out=self._v3_e11_before_pending(obs,config,out,now)\n        for item,q in targets.items():\n",
        "scheduler pre-pending seam",
    )
    write("scheduler.py", sched)

    frozen = read("frozen_selected.py")
    frozen = _replace_once(
        frozen,
        "        if funding is not None:self.diagnostics['same_turn_funding']=funding\n        for item,q in targets.items():\n",
        "        if funding is not None:self.diagnostics['same_turn_funding']=funding\n"
        "        out=self._v3_e11_before_pending(obs,config,out,now)\n"
        "        for item,q in targets.items():\n",
        "frozen pre-pending seam",
    )
    write("frozen_selected.py", frozen)

    cfg_path = os.path.join(src, "TITAN-CONFIG.json")
    data = json.loads(io.open(cfg_path, encoding="utf-8").read())
    for key in ("e11_rival_sell", "rival_model", "e20_hire_guard") + L01_KEYS + ("r01_shop_router", "r02_route_bank", "r03_full_router", "r04_sale_window"):
        assert key not in data, key
        data[key] = False
    for key, value in PARAMS.items():
        assert key not in data, key
        data[key] = value
    with io.open(cfg_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")

    write("TITAN-RELEASE.md", read("TITAN-RELEASE.md") + RELEASE_NOTE)
    write("NOTICE", read("NOTICE") + R01_NOTICE + R03_NOTICE)
    return src


if __name__ == "__main__":
    print("V3 edits applied to", apply(sys.argv[1]))
