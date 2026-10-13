# SPDX-License-Identifier: Apache-2.0
"""TITAN: one production selection, one explicit selected-action consumer."""
from copy import deepcopy
from dataclasses import dataclass
import importlib.util
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


_MODULE_CACHE = {}


def load(name, path, *, cache=False):
    """Cache only completed stateless modules; cancellation never publishes one.

    Controller instances and route/seed ledgers are constructed separately.
    Cache keys include the resolved artifact path to isolate relocated packages.
    """
    import sys
    key = (name, str(Path(path).resolve()))
    if cache and key in _MODULE_CACHE:
        # A different relocated package may have rebound this public name.
        # Restore this completed module before a sibling imports the name.
        module = _MODULE_CACHE[key]
        sys.modules[name] = module
        return module
    spec = importlib.util.spec_from_file_location(name, key[1])
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if cache:
            _MODULE_CACHE[key] = module
    except BaseException:
        _MODULE_CACHE.pop(key, None)
        if sys.modules.get(name) is module:
            if previous is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        raise
    return module


deadline = load('_titan_deadline', HERE/'reference/titan-current/deadline_adapter.py')


def _bind_public_observation(observation, cfg):
    """Copy and bind the public actor/clock without numeric coercion.

    The runtime is also a direct callable used by scratch/current-native
    evaluators, so it cannot rely on the outer canonical entrypoint to have
    already validated identity.  Reject aliases before fallback construction or
    any mutable controller state is cleared, observed, replayed, or indexed.
    """
    obs = dict(observation)
    player = obs.get('player') if 'player' in obs else None
    if type(player) is not int or player not in (0, 1):
        raise ValueError('player must be plain int 0 or 1')

    has_step = 'step' in obs
    if has_step:
        step = obs['step']
        if type(step) is not int or step < 0:
            raise ValueError('step must be a plain nonnegative int')

    has_day = 'day' in obs
    has_hour = 'hour' in obs
    if has_day != has_hour:
        raise ValueError('day and hour must be supplied together')
    if has_day:
        turns = cfg.get('turnsPerDay', 24)
        if type(turns) is not int or turns <= 0:
            raise ValueError('turnsPerDay must be a plain positive int')
        day = obs['day']
        hour = obs['hour']
        if type(day) is not int or day < 0:
            raise ValueError('day must be a plain nonnegative int')
        if type(hour) is not int or not 0 <= hour < turns:
            raise ValueError('hour must be a plain int in the configured day')
        derived = day * turns + hour
        if has_step:
            if step != derived:
                raise ValueError('step disagrees with day/hour clock')
        else:
            obs['step'] = derived
    elif not has_step:
        raise ValueError('step or paired day/hour clock required')
    return obs


@dataclass(frozen=True)
class Features:
    consumer: str = 'frozen'
    seed: bool = True
    funding: bool = True
    redundant_hire: bool = False
    terminal_route: bool = False
    committed: bool = True
    budget_seconds: float = 1.0
    reserve_seconds: float = 0.01
    terminal_history: bool = False
    history_hypotheses: dict | None = None
    terminal_tie_break: str = 'baseline'
    spatial_pathing: bool = False
    spatial_tempo: bool = False
    fourth_quadrant: bool = False
    market_pressure: bool = False
    committed_seed_retry: bool = False
    operating_stock: bool = False
    idle_fertilizer: bool = False
    crop_release: bool = False
    early_capital: bool = False
    exec_pace: bool = False
    overflow_safe_drop: bool = False

    def __post_init__(self):
        bool_fields = (
            'seed', 'funding', 'redundant_hire', 'terminal_route', 'committed',
            'terminal_history', 'spatial_pathing', 'spatial_tempo',
            'fourth_quadrant', 'market_pressure', 'committed_seed_retry',
            'operating_stock', 'idle_fertilizer', 'crop_release', 'early_capital',
        )
        bool_fields = (*bool_fields, 'exec_pace', 'overflow_safe_drop')
        for name in bool_fields:
            if type(getattr(self, name)) is not bool:
                raise TypeError(f'{name} must be bool')
        for name in ('budget_seconds', 'reserve_seconds'):
            value = getattr(self, name)
            if (type(value) not in (int, float)
                    or (type(value) is float and not math.isfinite(value))):
                raise TypeError(f'{name} must be a finite int or float')
        if self.history_hypotheses is not None and type(self.history_hypotheses) is not dict:
            raise TypeError('history_hypotheses must be dict or None')
        if type(self.terminal_tie_break) is not str:
            raise TypeError('terminal_tie_break must be str')
        if self.consumer not in ('frozen', 'ordered', 'parent'):
            raise ValueError('consumer must be frozen, ordered or parent')
        if self.terminal_route and self.consumer != 'frozen':
            raise ValueError('terminal_route is the tested frozen SELL composition')
        if self.exec_pace and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('exec_pace is the tested nonterminal frozen SELL composition')
        if self.overflow_safe_drop and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('overflow_safe_drop is the tested nonterminal frozen composition')
        if self.redundant_hire and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('redundant_hire is the tested nonterminal frozen SELL composition')
        if (self.spatial_pathing or self.spatial_tempo or self.fourth_quadrant or self.idle_fertilizer or self.crop_release) and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('spatial routes require nonterminal frozen SELL')
        if self.terminal_history and (self.consumer == 'parent' or self.history_hypotheses is None):
            raise ValueError('terminal_history needs a SELL snapshot and explicit scenario hypotheses')
        if not 0 <= self.reserve_seconds < self.budget_seconds <= 1:
            raise ValueError('invalid action deadline')


class TitanAgent:
    """Construction is lazy so the guard includes the chosen parent's cold start.

    Ordered mode consumes its existing ledger, unit projection and seed funding
    internally. Frozen mode owns its frozen ledger and applies ALDER/JUNIPER once
    after SELL, matching the shipped seed_main order. Ledgers never compose twice.
    """
    def __init__(self, features=None, *, fourth_quadrant_admission=None):
        self.features = features or Features()
        self.ready = False
        self.diagnostics = {}
        self.selected = None
        self.history = None
        self.post = None
        self._completed_route = None
        # Frozen SELL mutates several planning/observer fields before returning.
        # Keep observer state associated with a successfully returned action
        # or a fully replayed fallback prefix. The newest fallback remains
        # pending and replaceable; interrupted planning is never promoted.
        self._completed_seller_state = None
        self._seller_fallback_observations = []
        self._exec_pace_fallback_observations = []
        self.spatial = None
        self.quadrant = None
        self._quadrant_admission = fourth_quadrant_admission
        self._seed_plan = None
        self.committed_seed_retry_module = None

    @staticmethod
    def _seller_public_observation(obs, *, copy_tiles=True):
        """Retain only the public rival tiles consumed by SellScheduler.observe."""
        if obs is None:
            return None
        player = int(obs['player'])
        rival = 1-player
        farms = [{'tiles': []}, {'tiles': []}]
        tiles = obs['farms'][rival]['tiles']
        farms[rival] = {'tiles': deepcopy(tiles) if copy_tiles else tiles}
        return {'step': int(obs['step']), 'player': player, 'farms': farms}

    @staticmethod
    def _seller_state(consumer):
        """Copy the mutable completed FrozenSelected state economically.

        ``previous`` is already a private deep copy created by FrozenSelected
        and is replaced, never mutated, by later successful calls.  Retaining
        that object avoids a second full-observation copy on every action.  The
        collection fields are copied because later observations mutate them.
        """
        return {
            'planned': {item:list(rows) for item,rows in consumer.planned.items()},
            'pending': dict(consumer.pending),
            # FrozenSelected assigns a new deep-copied observation after each
            # completed transform; it never mutates the previous object. Reuse
            # those already-private tile bytes and copy them only on recovery.
            'previous': TitanAgent._seller_public_observation(
                consumer.previous, copy_tiles=False),
            'observed_harvests': {
                item:list(rows) for item,rows in consumer.observed_harvests.items()
            },
        }

    def _restore_seller_state(self):
        """Restore SELL intent and compact fully replayed fallback prefixes.

        The newest pending observation remains outside the checkpoint so a
        retry of that same public step can replace it exactly. Older pending
        observations are observer-complete and may be checkpointed. Publishing
        the checkpoint first is interruption-safe: its exact prior observation
        identifies and removes a stale prefix if cancellation happens before
        the pending list is shortened.
        """
        if self.features.consumer != 'frozen':
            return
        checkpoint = self._completed_seller_state
        if checkpoint is not None:
            self.consumer.planned = {
                item:list(rows) for item,rows in checkpoint['planned'].items()
            }
            self.consumer.pending = dict(checkpoint['pending'])
            self.consumer.previous = deepcopy(checkpoint['previous'])
            self.consumer.observed_harvests = {
                item:list(rows) for item,rows in checkpoint['observed_harvests'].items()
            }

        pending = list(self._seller_fallback_observations)
        if (checkpoint is not None
                and checkpoint.get('_fallback_prefix_checkpoint')):
            compacted_through = checkpoint.get('previous')
            for index, skipped in enumerate(pending):
                if skipped == compacted_through:
                    pending = pending[index+1:]
                    self._seller_fallback_observations = pending
                    break
        if not pending:
            return

        prefix, tail = pending[:-1], pending[-1]
        for skipped in prefix:
            # Observe only public state actually supplied to a call whose
            # fallback was returned. Advancing ``previous`` mirrors the end
            # of a completed transform without retaining interrupted plans.
            self.consumer.observe(skipped)
            self.consumer.previous = deepcopy(skipped)

        if prefix:
            compacted = self._seller_state(self.consumer)
            compacted['_fallback_prefix_checkpoint'] = True
            # Publish the checkpoint before shortening the list. If the
            # deadline interrupts between these assignments, the marker and
            # exact previous observation suppress duplicate prefix replay.
            self._completed_seller_state = compacted
            self._seller_fallback_observations = [tail]

        self.consumer.observe(tail)
        self.consumer.previous = deepcopy(tail)

    def _remember_seller_fallback(self, obs):
        """Queue one completed fallback observation for a later reconstruction."""
        if self.features.consumer != 'frozen':
            return
        step = int(obs['step'])
        if getattr(self.features, 'exec_pace', False) is True:
            self._exec_pace_fallback_observations.append({
                'step': step,
                'player': int(obs['player']),
                'market': {'prices': deepcopy(obs['market']['prices'])},
            })
        if self._seller_fallback_observations:
            prior = int(self._seller_fallback_observations[-1]['step'])
            if step < prior:
                # A fresh/reordered stream cannot safely inherit old observations.
                self._seller_fallback_observations = []
            elif step == prior:
                # Retry of the same public step is represented once.  Preserve
                # the latest exact observation rather than double-count harvests.
                self._seller_fallback_observations[-1] = self._seller_public_observation(obs)
                return
        self._seller_fallback_observations.append(self._seller_public_observation(obs))

    def _commit_seller_state(self, checkpoint=None):
        """Bind a completed FrozenSelected state to the returned action."""
        if self.features.consumer != 'frozen':
            return
        self._completed_seller_state = (self._seller_state(self.consumer)
                                        if checkpoint is None else checkpoint)
        self._seller_fallback_observations = []
    def _initialize(self):
        f = self.features
        self.funding_module = load('_titan_funding', HERE/'reference/titan-current/seed_funding.py', cache=True)
        selector = self.funding_module.select_seed_queue if f.funding else None
        if f.consumer == 'ordered':
            from integrated_selected import IntegratedSelectedAgent
            self.consumer = IntegratedSelectedAgent(seed=f.seed, committed=f.committed,
                                                   sell=True, seed_queue_selector=selector)
            self.production = self.consumer.production
            self.controller = self.consumer.controller
        else:
            from frozen_selected import FrozenSelected
            self.consumer = FrozenSelected()
            if f.exec_pace is True:
                pace = load('_titan_exec_pace_runtime', HERE/'exec_pace_runtime.py')
                exec_pace_state = getattr(self, '_exec_pace_state', None)
                if exec_pace_state is None:
                    exec_pace_state = pace.PriceTrendState()
                    self._exec_pace_state = exec_pace_state
                self.consumer.exec_pace_state = exec_pace_state
                self.consumer.exec_pace_apply = pace.apply_candidate
                for exec_pace_obs in getattr(self, '_exec_pace_fallback_observations', ()):
                    exec_pace_state.note_prices(exec_pace_obs)
                self._exec_pace_fallback_observations = []
            self.consumer.capture_post_units = f.terminal_history
            self.consumer.capture_operating_stock = f.operating_stock
            self.controller = self.consumer.controller
            self.production = self.controller
            if f.terminal_route:
                module = load('_titan_terminal_composition', HERE/'reference/titan-current/terminal_composition.py')
                self.production = module.TerminalOwner(self.controller)
                self.consumer.controller = self.production
            budget = load('_titan_seed_budget', HERE/'reference/integrated-selected/alder/seed_budget.py', cache=True)
            self.seed_budget = budget.SeedBudget(self.controller.R)
            if f.redundant_hire:
                self.redundant_hire_module = load(
                    '_titan_redundant_hire', HERE/'reference/titan-current/redundant_hire.py', cache=True)
        if f.committed_seed_retry:
            source = (HERE/'seed_retry.py' if (HERE/'seed_retry.py').is_file() else
                      HERE.parent/'cloud-committed-seed-retry/seed_retry.py')
            self.committed_seed_retry_module = load(
                '_titan_committed_seed_retry', source, cache=True)
        if (f.terminal_history or f.idle_fertilizer or f.crop_release) and self.history is None:
            from terminal_history_join import TerminalHistoryJoin
            self.history = TerminalHistoryJoin(hypotheses=f.history_hypotheses,
                                               tie_break=f.terminal_tie_break,
                                               terminal_enabled=f.terminal_history)
        if self._completed_route is not None:
            self.controller.cur = self._completed_route
        if f.fourth_quadrant:
            from fourth_quadrant import FourthQuadrant
            # ECON evaluates full market queues and therefore needs the exact
            # parser/price-refresh surface retained by the terminal mechanics.
            # The root mechanics intentionally does not expose those helpers.
            m = load('_titan_fourth_quadrant_mechanics',
                     HERE/'reference/titan-history/terminal_mechanics.py', cache=True)
            if self.quadrant is None:
                self.quadrant = FourthQuadrant(m, self._quadrant_admission)
            self.quadrant.install(self.controller)
            self._seed_plan = None
        if f.consumer == 'frozen' and not f.terminal_route:
            from spatial_tempo import SpatialTempo
            from scheduler import m
            if self.spatial is None:
                self.spatial = SpatialTempo(m, pathing=f.spatial_pathing, tempo=f.spatial_tempo,
                                            idle_fertilizer=f.idle_fertilizer,
                                            crop_release=f.crop_release)
                transform = self.spatial.transform
                def compatible_transform(obs, selected, controller):
                    if self.quadrant is not None and (self.quadrant.plan is not None or self.quadrant.pending is not None):
                        return selected
                    return transform(obs, selected, controller)
                self.spatial.transform = compatible_transform
            self.spatial.install(self.controller)
            self.spatial.seed_reserve = lambda crop, step, current: self.seed_budget.remaining(crop, step, current)
        self._restore_seller_state()
        self.ready = True

    def _finish_production(self, obs, returned, cfg=None):
        if self.spatial is not None:
            self.spatial.observe_crop_receipts(obs,
                None if self.history is None else self.history.fill_result,self.controller.cur)
        if self.spatial is not None:
            returned = self.spatial.guard_returned(obs, returned,
                repair_fallback=self.diagnostics.get('status')=='deadline_fallback')
        post = self._selected_snapshot(obs, returned) if self.history is not None else None
        if self.spatial is not None:
            returned=self.spatial.guard_crop_returned(obs,returned,post)
        # This small stock/position calculation is the final market guard, so
        # crop/idle composition and a completed selected fallback cannot undo
        # its same-slot reservation. It never executes a producer or game.
        returned = self._feed_stock_selected(obs, cfg or {}, returned)
        returned = self._early_capital_selected(obs, cfg or {}, returned)
        if self.quadrant is not None:
            self.quadrant.finish(obs, returned)
            self.diagnostics['fourth_quadrant_events'] = list(self.quadrant.events)
            if self._quadrant_admission is not None:
                self.diagnostics['fourth_quadrant_admission'] = deepcopy(
                    self._quadrant_admission.last_report)
        if self.spatial is not None:
            self.spatial.finish(obs, returned, post)
            self.spatial.finish_crop(obs,returned,post,self.controller.cur,
                                     seller_completed=self.diagnostics.get('status')=='completed')
            self.diagnostics['route_events'] = list(self.spatial.events)
            self.diagnostics['idle_fertilizer_receipts'] = list(self.spatial.receipt_events)
            self.diagnostics['idle_fertilizer_obligation'] = deepcopy(self.spatial.sale_obligation)
            if self.features.crop_release:
                self.diagnostics['crop_release']=deepcopy(self.spatial.crop_intent)
                self.diagnostics['crop_release_action']=deepcopy(self.spatial.crop_report)
        if self.history is not None:
            needed = (self.features.terminal_history or
                      (self.spatial is not None and (self.spatial.sale_obligation is not None
                                                     or self.spatial.crop_intent is not None)))
            self.history.remember(obs,cfg or {},returned,
                                  post if needed else None)
            self.diagnostics['history'] = self.history.diagnostics
        return returned

    def _seed_selected(self, obs, cfg, selected):
        if not self.features.seed:
            return selected
        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
        market = selected.get('market')
        if not isinstance(market, list):
            return selected
        prefix = market[:maximum]
        if not any(isinstance(o, list) and o and o[0] == 'BUY_SEED' for o in prefix):
            return selected
        from scheduler import post_units, m
        snapshot = getattr(self.consumer, 'selected_post_units', None)
        farm, private = snapshot if snapshot is not None else post_units(obs, selected, cfg)
        proposed = self.seed_budget.apply(selected, private['seeds'], int(obs['step']),
                                         self.controller.cur, maximum,
                                         extra_requests={} if self.spatial is None else
                                             self.spatial.future_seed_requests(int(obs['step'])))
        edits = [i for i, (a, b) in enumerate(zip(prefix, proposed['market'][:maximum])) if a != b]
        dependent = any(isinstance(o, list) and o and
                        o[0] in ('HIRE', 'BUY_LAND', 'BUY_PRODUCT', 'BUY_ANIMAL')
                        for i in edits for o in prefix[i+1:])
        if not dependent:
            return proposed
        if not self.features.funding:
            return selected
        post = deepcopy(obs)
        post['farms'][int(obs['player'])] = farm
        post['private'] = private
        result, report = self.funding_module.select_seed_queue(
            m, post, deepcopy(selected), deepcopy(proposed), deepcopy(cfg))
        self.diagnostics['seed_funding'] = report
        return result

    def _operating_stock_selected(self, obs, cfg, selected):
        """Protect a current producer input at the final market boundary."""
        if (not self.features.operating_stock or self.features.consumer != 'frozen'
                or self.features.terminal_route):
            return selected
        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
        market = selected.get('market')
        if not isinstance(market, list):
            self.diagnostics['operating_stock'] = {
                'changed': False, 'reason': 'malformed_market'}
            return selected
        prefix = market[:maximum]
        if any(o and not isinstance(o, list) for o in prefix):
            self.diagnostics['operating_stock'] = {
                'changed': False, 'reason': 'malformed_market_row'}
            return selected
        if not any(isinstance(o, list) and len(o) > 2
                   and o[:2] == ['SELL', 'FERTILIZER'] for o in prefix):
            return selected
        snapshot = getattr(self.consumer, 'selected_post_units', None)
        if (snapshot is None or self.selected is None
                or selected.get('farmer') != self.selected.get('farmer')
                or selected.get('hands') != self.selected.get('hands')):
            self.diagnostics['operating_stock'] = {'changed': False, 'reason': 'no_completed_unit_snapshot'}
            return selected
        from operating_stock import protect_operating_stock
        from scheduler import m, parent
        farm, private = snapshot
        prefix_selected = deepcopy(selected)
        prefix_selected['market'] = deepcopy(prefix)
        result, report = protect_operating_stock(
            m, obs, cfg, prefix_selected, farm, private, self.controller.R[self.controller.cur],
            [item[0] for item in parent.DECISIONS])
        self.diagnostics['operating_stock'] = report
        if result == prefix_selected:
            return selected
        if (not isinstance(result, dict) or not isinstance(result.get('market'), list)
                or len(result['market']) != len(prefix)):
            self.diagnostics['operating_stock'] = {
                'changed': False, 'reason': 'prefix_helper_changed_market_shape'}
            return selected
        returned = deepcopy(result)
        returned['market'] = list(returned['market']) + deepcopy(market[maximum:])
        return returned

    def _feed_stock_selected(self, obs, cfg, selected):
        if (not self.features.operating_stock or self.features.consumer != 'frozen'
                or self.features.terminal_route):
            return selected
        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
        market = selected.get('market')
        if not isinstance(market, list):
            self.diagnostics['feed_stock'] = {
                'changed': False, 'certified': False, 'reason': 'malformed_market'}
            return selected
        prefix = market[:maximum]
        if any(o and not isinstance(o, list) for o in prefix):
            self.diagnostics['feed_stock'] = {
                'changed': False, 'certified': False, 'reason': 'malformed_market_row'}
            return selected
        if not any(isinstance(o, list) and o and o[:2] == ['SELL', 'WHEAT']
                   for o in prefix):
            return selected
        if self.spatial is not None and self.spatial._crop_repair is not None:
            self.diagnostics['feed_stock'] = {'changed': False, 'certified': False,
                                              'reason': 'crop_input_repair_owns_current_queue'}
            return selected
        post = self._selected_snapshot(obs, selected)
        if post is None:
            self.diagnostics['feed_stock'] = {'changed': False, 'certified': False,
                                              'reason': 'no_matching_completed_unit_snapshot'}
            return selected
        from operating_stock import protect_feed_stock
        from scheduler import m, parent
        result, report = protect_feed_stock(
            m, obs, cfg, selected, post['farms'][int(obs['player'])], post['private'],
            self.controller.R[self.controller.cur], [item[0] for item in parent.DECISIONS])
        self.diagnostics['feed_stock'] = report
        return result

    def _early_capital_selected(self, obs, cfg, selected):
        """Reorder current-queue capital after feed-stock; no new producer."""
        if (not getattr(self.features, 'early_capital', False)
                or self.features.consumer != 'frozen'
                or self.features.terminal_route):
            return selected
        import mechanics as mechanics_mod
        from early_capital import order_early_capital
        from scheduler import parent
        result, report = order_early_capital(
            mechanics_mod, obs, cfg, selected,
            self.controller.R[self.controller.cur], parent.DECISIONS)
        self.diagnostics['early_capital'] = report
        return result

    def _redundant_hire_selected(self, obs, cfg, selected):
        """Apply the landed T10 physical certificate to the final frozen-SELL queue."""
        if not self.features.redundant_hire:
            return selected
        maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
        if not any(isinstance(o, list) and o and o[0] == 'HIRE'
                   for o in (selected.get('market') or [])[:maximum]):
            return selected
        from scheduler import m, parent
        result, report = self.redundant_hire_module.propose_redundant_hires(
            m, obs, cfg, selected,
            route=self.controller.R[self.controller.cur],
            route_id=self.controller.cur,
            route_switch_steps=[item[0] for item in parent.DECISIONS],
        )
        self.diagnostics['redundant_hire'] = report
        return result

    def _committed_seed_retry_selected(self, obs, cfg, selected):
        """Append a certified seed deficit for the unchanged next-turn route.

        The attributed helper owns demand, route and reserve checks and calls the
        landed funding certificate in its reverse (richer-queue) direction. It
        never invokes the producer or substitutes the certificate's reduced
        action for the separately retained candidate.
        """
        if not self.features.committed_seed_retry:
            return selected
        result, report = self.committed_seed_retry_module.apply_committed_seed_retry(
            self, obs, cfg, selected)
        self.diagnostics['committed_seed_retry'] = report
        return result

    def transform_selected(self, obs, cfg, selected):
        """Dispatch an already-selected action; never calls a producer."""
        if self.features.consumer == 'ordered':
            return self.consumer.transform(obs, cfg, selected, fallback_action=selected)
        result = (self.consumer.transform(obs, cfg, selected)
                  if self.features.consumer == 'frozen' else deepcopy(selected))
        result = self._redundant_hire_selected(obs, cfg, result)
        result = self._seed_selected(obs, cfg, result)
        return self._committed_seed_retry_selected(obs, cfg, result)

    def _market_pressure_selected(self, obs, cfg, selected):
        """Order SELL blocks and eligible empty sale-only slots by public exposure.

        Source-tree tests load the landed LARK modules from their attributed
        directory.  The standalone release maps the same bytes beside this
        module.  No units, quantities, economic barriers or suffix orders move.
        """
        if not self.features.market_pressure:
            return selected
        source = (HERE if (HERE/'pressure_priority.py').is_file() else
                  HERE.parent/'cloud-opponent-league/lark-responsive')
        # pressure_priority imports the exact sibling by its public module name.
        load('sell_priority', source/'sell_priority.py', cache=True)
        pressure = load('_titan_pressure_priority', source/'pressure_priority.py', cache=True)
        mechanics = load('_titan_pressure_mechanics', HERE/'mechanics.py', cache=True)
        result = pressure.transform(selected, obs, cfg, quote=mechanics.market_price)
        self.diagnostics['market_pressure'] = {
            'enabled': True,
            'changed': result != selected,
        }
        return result

    def _selected_snapshot(self, obs, returned=None):
        if self.features.consumer == 'ordered':
            packet = self.consumer.last_packet
            return None if packet is None else packet['post_unit_observation']
        pair = getattr(self.consumer, 'selected_post_units', None)
        if pair is None:
            if (returned is not None and returned['farmer']==['PASS']
                    and all(a==['PASS'] for a in returned.get('hands',[]))):
                return obs  # PASS has no unit-stage stock mutation; EOD is later.
            return None
        binding = getattr(self.consumer, 'selected_post_units_binding', None)
        if binding is None or binding[:2] != (int(obs['step']),int(obs['player'])):
            return None
        if returned is not None and binding[2:] != (returned['farmer'],returned.get('hands',[])):
            return None
        post = deepcopy(obs)
        post['farms'][int(obs['player'])], post['private'] = pair
        return post

    def act(self, observation, configuration=None, *, entry_started=None):
        invoked = time.perf_counter()
        # The canonical entrypoint shares its start clock with this same timer.
        # A supplied future timestamp must never extend the configured budget.
        started = invoked if entry_started is None else min(invoked,float(entry_started))
        cpu_started = time.process_time()
        cfg = dict(configuration or {})
        obs = _bind_public_observation(observation, cfg)
        last = int(cfg.get('episodeSteps', 720))-2
        fallback = (deadline.terminal_liquidation_fallback(obs, cfg) if obs['step'] == last
                    else deadline.legal_pass(obs))
        self.selected = None
        self.post = None
        # Clear before the prelude deadline as well. A prior turn's post-unit
        # snapshot must never be rebound to the current returned action.
        if getattr(self,'consumer',None) is not None:
            self.consumer.selected_post_units = None
            self.consumer.selected_post_units_binding = None
        self.diagnostics = {'consumer': self.features.consumer, 'parent_calls': 0,
                            'entrypoint_prelude_seconds': invoked-started}
        selected_checkpoint = None
        seller_checkpoint = None
        stage = 'cold_start'
        seconds = self.features.budget_seconds-self.features.reserve_seconds-(time.perf_counter()-started)
        if seconds <= 0:
            # No current state mutated, but FrozenSelected must still observe the
            # public step before the next decision.  Reconstruct so the queued
            # fallback observation is replayed through the original observer.
            if self.features.consumer == 'frozen':
                self.ready = False
            self._remember_seller_fallback(obs)
            self.diagnostics.update(status='deadline_fallback',fallback_stage='entrypoint_prelude',
                elapsed_seconds=time.perf_counter()-started,act_cpu_seconds=time.process_time()-cpu_started)
            # The lazy controller does not exist yet, and the budget is already
            # exhausted. The queued public observation is sufficient for the
            # next reconstruction; no post-controller finalizer is safe here.
            return fallback
        timer = deadline._DeadlineTimer(seconds)
        try:
            with timer:
                if not self.ready:
                    self._initialize()
                if self.history is not None:
                    stage = 'history_observation'
                    self.history.observe(obs)
                if self.spatial is not None:
                    self.spatial.observe_market_receipt(obs,
                        None if self.history is None else self.history.fill_result)
                    self.spatial.observe_crop_receipts(obs,
                        None if self.history is None else self.history.fill_result,self.controller.cur)
                if self.features.consumer == 'ordered':
                    self.consumer.last_packet = None
                else:
                    self.consumer.selected_post_units = None
                stage = 'production'
                if self.quadrant is not None:
                    self.quadrant.configure(cfg)
                if self.spatial is not None:
                    self.spatial.configure(cfg)
                if self.features.terminal_route:
                    self.production.configuration = cfg
                if self._quadrant_admission is not None:
                    self._quadrant_admission.begin_action(
                        started+self.features.budget_seconds-self.features.reserve_seconds)
                self.diagnostics['parent_calls'] = 1
                selected = self.production.act(obs)
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                fallback = selected_checkpoint[0]
                if self.quadrant is not None:
                    plan = self.quadrant.pending or self.quadrant.plan
                    if plan is not self._seed_plan:
                        # The exact future PLANT additions enter ALDER's bound;
                        # no private seed purchase bypasses the selected queue.
                        budget = load('_titan_seed_budget', HERE/'reference/integrated-selected/alder/seed_budget.py', cache=True)
                        self.seed_budget = budget.SeedBudget(self.controller.R)
                        self._seed_plan = plan
                stage = 'selected_transform'
                if self.features.consumer == 'frozen':
                    self.consumer.capture_post_units = (self.features.terminal_history or
                        (self.spatial is not None and (self.spatial.sale_obligation is not None
                            or (self.features.crop_release and
                                (int(obs['step'])==372 or self.spatial.crop_intent is not None)))))
                    # Joint market admission follows the unchanged future tape.
                    # Keep producer-owned continuations outside that new path.
                    pending={} if self.spatial is None else (self.spatial._pending or {})
                    self.consumer.joint_producer_busy=bool(
                        self.features.terminal_route or self.features.fourth_quadrant
                        or self.features.spatial_pathing or self.features.spatial_tempo
                        or (self.spatial is not None and
                            (self.spatial.plans or pending.get('plans')
                             or self.spatial.crop_intent is not None
                             or self.spatial.sale_obligation is not None))
                        or (self.features.crop_release and int(obs['step'])==372))
                output = self.transform_selected(obs, cfg, selected)
                if self.history is not None:
                    self.post = self._selected_snapshot(obs)
                    stage = 'terminal_history'
                    output = self.history.transform(obs,cfg,output,self.post,
                        deadline=started+self.features.budget_seconds-self.features.reserve_seconds)
                stage = 'market_pressure'
                output = self._market_pressure_selected(obs, cfg, output)
                stage = 'operating_stock'
                output = self._operating_stock_selected(obs, cfg, output)
                if self.spatial is not None and self.features.crop_release:
                    stage='crop_release'
                    output=self.spatial.crop_market(obs,output,self._selected_snapshot(obs,output),
                                                    self.controller)
                # Build the checkpoint while the deadline is still active, but
                # publish it only after the context exits without cancellation.
                if self.features.consumer == 'frozen':
                    seller_checkpoint = self._seller_state(self.consumer)
        except deadline.DeadlineExceeded as error:
            if error is not timer.expired:
                raise
            # Cancellation can interrupt a state mutation. Reconstruct next turn
            # from observed state rather than reuse partially updated ledgers.
            self.ready = False
            # Retain only the route paired with a complete selected fallback.
            # A producer interrupted before returning cannot commit its choice.
            if selected_checkpoint is not None and fallback is selected_checkpoint[0]:
                self._completed_route = selected_checkpoint[1]
            self._remember_seller_fallback(obs)
            if self.history is not None:
                if stage in ('cold_start','history_observation'):
                    self.history = None
            output = deepcopy(fallback)
            self.diagnostics.update(status='deadline_fallback', fallback_stage=stage,
                                    elapsed_seconds=time.perf_counter()-started,
                                    act_cpu_seconds=time.process_time()-cpu_started)
            output = self._finish_production(obs, output, cfg)
            # Include the reserved fallback/finalizer window in the receipt.
            self.diagnostics.update(elapsed_seconds=time.perf_counter()-started,
                                    act_cpu_seconds=time.process_time()-cpu_started)
            return output
        # The deadline context has exited successfully.  Commit mutable state
        # only now, so a final trace/signal cancellation cannot bind planning for
        # an action that was never returned.
        self._completed_route = selected_checkpoint[1]
        self._commit_seller_state(seller_checkpoint)
        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,
                                act_cpu_seconds=time.process_time()-cpu_started)
        output = self._finish_production(obs, output, cfg)
        # A completed action receipt covers the exact bytes returned, including
        # late market guards and their state commits.
        self.diagnostics.update(elapsed_seconds=time.perf_counter()-started,
                                act_cpu_seconds=time.process_time()-cpu_started)
        return output

    __call__ = act
