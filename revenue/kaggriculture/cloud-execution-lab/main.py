# SPDX-License-Identifier: Apache-2.0
"""Canonical TITAN entrypoint. Feature choices are deterministic package data."""
_INSTANCE = None
_SPATIAL_RECOVERY = None
_ROUTE_RECOVERY = None
_SPATIAL_RECOVERY_FIELDS = ('_committed', 'sale_obligation', 'receipt_events', 'crop_intent')


def _install_funding_eod_boundary(module):
    """Fail closed before a represented funding replay crosses official EOD."""
    from functools import wraps

    current = None if module is None else getattr(module, '_funding_trace', None)
    if not callable(current):
        raise RuntimeError('loaded frozen seller has no funding trace')
    if getattr(current, '_titan_funding_eod_boundary', False):
        return current

    @wraps(current)
    def guarded(obs, config, farm, private, route, now, end, current_market,
                stress_units=0):
        turns = config.get('turnsPerDay')
        if type(turns) is not int or turns != 24:
            raise ValueError('funding replay requires plain-int turnsPerDay == 24')
        if now // turns != end // turns:
            raise ValueError('funding replay cannot cross end-of-day lifecycle')
        return current(obs, config, farm, private, route, now, end,
                       current_market, stress_units=stress_units)

    guarded._titan_funding_eod_boundary = True
    guarded._titan_funding_eod_original = current
    module._funding_trace = guarded
    return guarded


def _runtime_feature_data(feature_data):
    """Remove reserved harness metadata without weakening the public schema.

    Top-level keys beginning with ``_`` are non-behavioral experiment
    annotations. Every public key is retained so unsupported runtime options
    still fail closed when ``Features`` binds the configuration.
    """
    return {
        key: value for key, value in dict(feature_data).items()
        if not (isinstance(key, str) and key.startswith('_'))
    }


def _town_procurement_enabled(feature_data):
    """Bind the entrypoint-owned town flag with the runtime's exact-bool policy."""
    value = feature_data.get('town_procurement', False)
    if type(value) is not bool:
        raise TypeError('town_procurement must be bool')
    return value


def _canonical_entrypoint_observation(observation, configuration):
    """Bind public identity exactly before any retained root state is touched."""
    obs = dict(observation)
    cfg = dict(configuration or {})

    if 'player' not in obs:
        raise ValueError('entrypoint requires public player')
    player = obs['player']
    if type(player) is not int or player not in (0, 1):
        raise ValueError('entrypoint player must be plain integer 0 or 1')

    step_present = 'step' in obs
    day_present = 'day' in obs
    hour_present = 'hour' in obs

    def exact_turns_per_day():
        turns = cfg.get('turnsPerDay', 24)
        if type(turns) is not int or turns <= 0:
            raise ValueError('entrypoint turnsPerDay must be a positive plain integer')
        return turns

    if step_present:
        step = obs['step']
        if type(step) is not int or step < 0:
            raise ValueError('entrypoint step must be a nonnegative plain integer')
        if day_present != hour_present:
            raise ValueError('entrypoint redundant clock requires both day and hour')
        if day_present:
            turns = exact_turns_per_day()
            day = obs['day']
            hour = obs['hour']
            if type(day) is not int or day < 0:
                raise ValueError('entrypoint day must be a nonnegative plain integer')
            if type(hour) is not int or not 0 <= hour < turns:
                raise ValueError('entrypoint hour must be a bounded plain integer')
            if step != day * turns + hour:
                raise ValueError('entrypoint step/day/hour identity mismatch')
    else:
        if not day_present or not hour_present:
            raise ValueError('entrypoint requires step or complete day/hour clock')
        turns = exact_turns_per_day()
        day = obs['day']
        hour = obs['hour']
        if type(day) is not int or day < 0:
            raise ValueError('entrypoint day must be a nonnegative plain integer')
        if type(hour) is not int or not 0 <= hour < turns:
            raise ValueError('entrypoint hour must be a bounded plain integer')
        step = day * turns + hour

    normalized = dict(obs)
    normalized['player'] = player
    normalized['step'] = step
    return normalized


def _new_instance(root, feature_data):
    """Construct the configured runtime and its opt-in economic admission."""
    from titan_runtime import TitanAgent, Features, load
    feature_data = _runtime_feature_data(feature_data)
    town_enabled = _town_procurement_enabled(feature_data)
    feature_data.pop('town_procurement', None)
    features = Features(**feature_data)
    if town_enabled and (features.consumer != 'frozen' or features.terminal_route):
        raise ValueError('town_procurement is the tested nonterminal frozen composition')

    overflow_safe_drop = None
    if getattr(features, 'overflow_safe_drop', False):
        source = root/'overflow_safe_drop.py'
        if not source.is_file():
            source = root/'candidates/v5/research/overflow-safe-drop/overflow_safe_drop.py'
        overflow_safe_drop = load('_titan_overflow_safe_drop', source, cache=True)

    class FinalPressureAgent(TitanAgent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.town_procurement_enabled = town_enabled
            self.overflow_safe_drop = overflow_safe_drop
            self._finalizer_checkpoint = None
            self._staged_spatial_recovery = None
            self._history_checkpoint = None

        def _export_spatial_recovery(self):
            """Copy only state certified before the next entrypoint call starts.

            SpatialTempo has transient proposal fields which can be half-mutated
            by a late outer deadline. Those are intentionally absent here. The
            four retained fields are committed/observed cross-turn state whose
            owning actions or receipts were already returned before this call.
            """
            from copy import deepcopy
            spatial = getattr(self, 'spatial', None)
            if spatial is None:
                return None
            return {name: deepcopy(getattr(spatial, name, None))
                    for name in _SPATIAL_RECOVERY_FIELDS}

        def _stage_spatial_recovery(self, snapshot):
            """Stage a bounded checkpoint for the next lazy spatial initialize."""
            from copy import deepcopy
            if snapshot is None:
                self._staged_spatial_recovery = None
                return True
            if (not isinstance(snapshot, dict)
                    or set(snapshot) != set(_SPATIAL_RECOVERY_FIELDS)):
                self._staged_spatial_recovery = None
                return False
            self._staged_spatial_recovery = deepcopy(snapshot)
            return True

        def _restore_spatial_recovery(self):
            """Restore certified state without restoring interrupted proposals."""
            from copy import deepcopy
            snapshot = self._staged_spatial_recovery
            self._staged_spatial_recovery = None
            spatial = getattr(self, 'spatial', None)
            if snapshot is None or spatial is None:
                return
            for name in _SPATIAL_RECOVERY_FIELDS:
                setattr(spatial, name, deepcopy(snapshot[name]))

        def _initialize(self):
            # Keep TitanAgent's normal lazy construction and controller install.
            # Install the lifecycle guard only after the exact relocated seller
            # module is loaded, but before any represented funding trace runs.
            super()._initialize()
            import sys
            selected_module = sys.modules.get(self.consumer.__class__.__module__)
            _install_funding_eod_boundary(selected_module)
            # Restore the bounded spatial journal only after a fresh SpatialTempo
            # exists, but before production consumes the new public observation.
            self._restore_spatial_recovery()
            # TerminalHistoryJoin publishes observation transitions transactionally.
            # Retain the fully constructed object before TitanAgent can suspend it
            # during a history_observation deadline, including the first lazy call.
            if self.history is not None:
                self._history_checkpoint = self.history

        def act(self, observation, configuration=None, *, entry_started=None):
            """Retain retryable history across the inner observation deadline."""
            history_checkpoint = self.history or self._history_checkpoint
            output = super().act(observation, configuration,
                                 entry_started=entry_started)
            if (self.history is None
                    and self.diagnostics.get('status') == 'deadline_fallback'
                    and self.diagnostics.get('fallback_stage') == 'history_observation'):
                history_checkpoint = history_checkpoint or self._history_checkpoint
                if history_checkpoint is not None:
                    # A signal can land after Titan marks the history stage but
                    # before TerminalHistoryJoin journals the observation. Fill
                    # only that tiny gap; if the join already journaled it, keep
                    # the existing stable copy/commit intact.
                    if (getattr(history_checkpoint, 'pending', None) is not None
                            and getattr(history_checkpoint, 'deferred_observation', None) is None
                            and getattr(history_checkpoint, '_observation_commit', None) is None):
                        recovery_obs = _canonical_entrypoint_observation(
                            observation, configuration)
                        history_checkpoint.defer_observation(recovery_obs)
                    # TitanAgent deliberately suspended history while constructing
                    # its safe fallback, so the fallback action was never rebound
                    # into the prior receipt. Restore only the pre-call join.
                    self.history = history_checkpoint
                    self._history_checkpoint = history_checkpoint
                    self.diagnostics['history_observation_recovery'] = 'restored_retryable'
            elif self.history is not None:
                self._history_checkpoint = self.history
            return output

        def _checkpoint_finalizer(self, obs, selected, stage):
            """Publish only a fully returned current-turn action stage.

            The outer entrypoint timer can interrupt later finalizers. Keeping
            this private action-only checkpoint lets that guard return the last
            completed bytes without trusting any partially mutated runtime state;
            the instance is still discarded after whole-call cancellation.
            """
            from copy import deepcopy
            self._finalizer_checkpoint = {
                'step': obs['step'],
                'player': obs['player'],
                'stage': str(stage),
                'action': deepcopy(selected),
            }

        """Keep public-curve pressure at the returned-action boundary.

        Pressure was originally the final SELL transform. Later stock, crop,
        feed and capital repairs are now allowed to finish first, then pressure
        may reorder only the resulting supported SELL blocks. Deadline fallback
        keeps its existing path and does not start a new optional transform.
        """
        def _market_pressure_selected(self, obs, cfg, selected):
            if not getattr(self, '_final_pressure_boundary', False):
                return selected
            return super()._market_pressure_selected(obs, cfg, selected)

        def _feed_stock_selected(self, obs, cfg, selected):
            # Enter the first late market finalizer with a current-turn action
            # already checkpointed. If this helper is cancelled, the outer guard
            # can keep all earlier completed crop/stock work instead of dropping
            # back to the raw producer selection.
            self._checkpoint_finalizer(obs, selected, 'pre_feed_stock')
            returned = super()._feed_stock_selected(obs, cfg, selected)
            self._checkpoint_finalizer(obs, returned, 'feed_stock')
            return returned

        def _early_capital_selected(self, obs, cfg, selected):
            # TitanAgent._finish_production calls this after every stock/crop
            # guard and before every receipt/history commit. Reuse that stable
            # boundary instead of copying the finalizer or mutating afterward.
            self._checkpoint_finalizer(obs, selected, 'pre_early_capital')
            returned = super()._early_capital_selected(obs, cfg, selected)
            self._checkpoint_finalizer(obs, returned, 'early_capital')
            completed = self.diagnostics.get('status') == 'completed'
            if completed:
                self._final_pressure_boundary = True
                try:
                    returned = super()._market_pressure_selected(obs, cfg, returned)
                finally:
                    self._final_pressure_boundary = False
                self._checkpoint_finalizer(obs, returned, 'market_pressure')
            if self.town_procurement_enabled:
                from town_procurement import apply
                returned, report = apply(obs, returned, cfg, completed=completed)
                self.diagnostics['town_procurement'] = report
                self._checkpoint_finalizer(obs, returned, 'town_procurement')
            # Overflow preservation is an optional final-return transform only.
            # Do not run it on an incomplete producer result or on the terminal
            # settlement step, where liquidation semantics own the returned bytes.
            if self.overflow_safe_drop is not None and completed:
                episode_steps = cfg.get('episodeSteps', 720)
                nonterminal = (type(episode_steps) is int and episode_steps >= 2
                               and obs.get('step') != episode_steps - 2)
                if nonterminal:
                    returned, report = self.overflow_safe_drop.transform(returned, obs, cfg)
                    self.diagnostics['overflow_safe_drop'] = report
                    self._checkpoint_finalizer(obs, returned, 'overflow_safe_drop')
            return returned

    admission = None
    if features.fourth_quadrant:
        source = root/'funded_payback.py'
        if not source.is_file():
            # Source-tree execution retains ECON's own attributed location;
            # the canonical archive maps those exact bytes beside main.py.
            source = root/'../cloud-economic-stress/funded_payback/funded_payback.py'
        module = load('_titan_funded_payback', source, cache=True)
        adapter = load('_titan_funded_payback_runtime',
                       root/'funded_payback_runtime.py', cache=True)
        admission = adapter.make_admission(module.FundedPaybackAdmission)(
            seconds=features.budget_seconds, max_proposals=24)
    return FinalPressureAgent(features, fourth_quadrant_admission=admission)


def _entrypoint_fallback(instance, observation, configuration, deadline):
    """Return the latest completed current action, else visible-state fallback."""
    from copy import deepcopy
    cfg = dict(configuration or {})
    obs = dict(observation)
    step = obs['step']
    player = obs['player']

    action = None
    checkpoint = None if instance is None else getattr(instance, '_finalizer_checkpoint', None)
    if (isinstance(checkpoint, dict)
            and checkpoint.get('step') == step
            and checkpoint.get('player') == player
            and checkpoint.get('action') is not None):
        action = deepcopy(checkpoint['action'])
    if action is None:
        selected = None if instance is None else getattr(instance, 'selected', None)
        if selected is not None:
            action = deepcopy(selected)
    if action is not None:
        if bool(getattr(instance, 'town_procurement_enabled', False)):
            from town_procurement import suppress_confirmed
            action, _ = suppress_confirmed(obs, action, cfg)
        return action

    last = int(cfg.get('episodeSteps', 720))-2
    return (deadline.terminal_liquidation_fallback(obs, cfg)
            if step == last else deadline.legal_pass(obs))


def _record_entrypoint_deadline(instance, stage, started):
    """Retain both the inner receipt and the whole-call cancellation boundary."""
    if instance is None:
        return
    import time
    diagnostics = dict(getattr(instance, 'diagnostics', {}) or {})
    if diagnostics.get('fallback_stage') is not None:
        diagnostics['inner_fallback_stage'] = diagnostics['fallback_stage']
    if diagnostics.get('elapsed_seconds') is not None:
        diagnostics['inner_elapsed_seconds'] = diagnostics['elapsed_seconds']
    checkpoint = getattr(instance, '_finalizer_checkpoint', None)
    if isinstance(checkpoint, dict) and checkpoint.get('stage') is not None:
        diagnostics['entrypoint_checkpoint_stage'] = checkpoint['stage']
    diagnostics.update(status='deadline_fallback', fallback_stage=stage,
                       entrypoint_guard=True,
                       elapsed_seconds=time.perf_counter()-started)
    instance.diagnostics = diagnostics


def _spatial_recovery_journal(snapshot, step):
    """Bind a pre-call spatial snapshot to the public step that was returned."""
    if snapshot is None:
        return None
    from copy import deepcopy
    return {'last_step': step, 'state': deepcopy(snapshot)}


def _route_recovery_capsule(value):
    """Validate route provenance separately from its latest observed callback."""
    if (not isinstance(value, dict)
            or set(value) != {'route_step', 'last_step', 'player', 'route'}):
        return None
    route_step = value['route_step']
    last_step = value['last_step']
    player = value['player']
    route = value['route']
    if type(route_step) is not int or route_step < 0:
        return None
    if type(last_step) is not int or last_step < route_step:
        return None
    if type(player) is not int or player not in (0, 1):
        return None
    if type(route) is not str or not route:
        return None
    return {
        'route_step': route_step,
        'last_step': last_step,
        'player': player,
        'route': route,
    }


def _route_recovery_matches(capsule, step, player):
    """Admit only a same-step retry or the next observed public callback."""
    return (capsule is not None
            and capsule['player'] == player
            and step in (capsule['last_step'], capsule['last_step'] + 1))


def _advance_route_recovery(capsule, step, player):
    """Carry prior route provenance while advancing only observation custody."""
    if not _route_recovery_matches(capsule, step, player):
        return None
    advanced = dict(capsule)
    advanced['last_step'] = step
    return advanced


def _instance_route_recovery(instance):
    """Read only the immutable route receipt published by a complete callback."""
    if instance is None:
        return None
    return _route_recovery_capsule(
        getattr(instance, '_entrypoint_route_receipt', None))


def _store_instance_route_recovery(instance, capsule):
    """Publish route provenance on the retained runtime without trusting live state."""
    normalized = _route_recovery_capsule(capsule)
    if instance is not None:
        instance._entrypoint_route_receipt = (
            None if normalized is None else dict(normalized))
        # Keep the completed-route origin explicit for review/tests and never
        # reinterpret the latest observed callback as a producer commit.
        instance._completed_route_step = (
            None if normalized is None else normalized['route_step'])
    return normalized


def agent(observation, configuration=None):
    global _INSTANCE, _SPATIAL_RECOVERY, _ROUTE_RECOVERY
    import time
    entry_started = time.perf_counter()
    from pathlib import Path
    import json
    import sys
    cfg = dict(configuration or {})
    observation = _canonical_entrypoint_observation(observation, cfg)
    path = globals().get('__file__') or cfg.get('__raw_path__')
    if not path:
        raise ValueError('Entrypoint path required')
    root = Path(path).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    step = observation['step']
    player = observation['player']

    journal = _SPATIAL_RECOVERY if isinstance(_SPATIAL_RECOVERY, dict) else None
    journal_step = None if journal is None else journal.get('last_step')
    raw_route_journal = _ROUTE_RECOVERY
    route_journal = _route_recovery_capsule(raw_route_journal)
    if raw_route_journal is not None and route_journal is None:
        _ROUTE_RECOVERY = None
    if journal_step is None and route_journal is not None:
        journal_step = route_journal['last_step']
    # Step zero is both a match boundary and a legal same-step retry. Reuse an
    # instance (or a recovery journal) that already returned step zero; only a
    # later-step -> 0 transition proves that retained state belongs to old play.
    previous_step = (getattr(_INSTANCE, '_entrypoint_last_step', None)
                     if _INSTANCE is not None else journal_step)
    match_reset = step == 0 and previous_step not in (None, 0)
    if match_reset:
        _SPATIAL_RECOVERY = None
        _ROUTE_RECOVERY = None
        journal = None
        route_journal = None
    elif route_journal is not None and not _route_recovery_matches(
            route_journal, step, player):
        # A skipped callback, rewind, or player change breaks route provenance.
        _ROUTE_RECOVERY = None
        route_journal = None
    replace = (_INSTANCE is None or match_reset)
    instance = None if replace else _INSTANCE

    # Snapshot only state certified before this call mutates the live instance.
    # If a prior outer timeout already discarded the instance, carry its saved
    # journal through another construction/prelude cancellation unchanged.
    spatial_recovery = None
    if not match_reset:
        if instance is not None:
            exporter = getattr(instance, '_export_spatial_recovery', None)
            if callable(exporter):
                spatial_recovery = exporter()
        elif (isinstance(journal, dict)
              and set(journal) == {'last_step', 'state'}):
            from copy import deepcopy
            spatial_recovery = deepcopy(journal['state'])

    feature_data = (json.loads((root/'TITAN-CONFIG.json').read_text())
                    if replace else None)
    town_enabled = (_town_procurement_enabled(feature_data) if replace
                    else instance.town_procurement_enabled)
    if town_enabled:
        receipt_obs = dict(observation)
        receipt_obs['step'] = step
        import town_procurement
        town_procurement.observe(receipt_obs)
    from titan_runtime import deadline
    budget = (float(instance.features.budget_seconds) if instance is not None
              else float(feature_data.get('budget_seconds', 1.0)))
    reserve = (float(instance.features.reserve_seconds) if instance is not None
               else float(feature_data.get('reserve_seconds', 0.01)))
    if not 0 <= reserve < budget <= 1:
        raise ValueError('invalid action deadline')
    # TitanAgent clears this itself, but clear both current-action publications
    # before arming the outer timer so an immediate cancellation cannot reuse a
    # prior step (or an earlier retry of this same public step).
    if instance is not None:
        instance.selected = None
        if hasattr(instance, '_finalizer_checkpoint'):
            instance._finalizer_checkpoint = None
    fallback = _entrypoint_fallback(None, observation, cfg, deadline)
    remaining = budget-(time.perf_counter()-entry_started)
    if remaining <= 0:
        # Construction is runtime work. Once the prelude has exhausted the
        # budget, starting a fresh lazy controller outside any timer would turn
        # this fallback branch into an unbounded call. Leave the instance absent;
        # the next visible observation can initialize it normally.
        if replace:
            _SPATIAL_RECOVERY = _spatial_recovery_journal(spatial_recovery, step)
            _ROUTE_RECOVERY = _advance_route_recovery(route_journal, step, player)
            _INSTANCE = None
            return fallback
        obs = dict(observation)
        obs['step'] = step
        if instance.features.consumer == 'frozen':
            instance.ready = False
        instance.selected = None
        instance.post = None
        instance._remember_seller_fallback(obs)
        instance._entrypoint_last_step = step
        _store_instance_route_recovery(
            instance,
            _advance_route_recovery(
                _instance_route_recovery(instance), step, player))
        instance.diagnostics = {
            'consumer': instance.features.consumer,
            'parent_calls': 0,
            'entrypoint_prelude_seconds': time.perf_counter()-entry_started,
            'status': 'deadline_fallback',
            'fallback_stage': 'entrypoint_prelude',
            'elapsed_seconds': time.perf_counter()-entry_started,
            'act_cpu_seconds': 0.0,
            'entrypoint_guard': True,
        }
        return fallback
    timer = deadline._DeadlineTimer(remaining)
    stage = 'entrypoint_construction' if replace else 'entrypoint_runtime'
    try:
        with timer:
            if replace:
                instance = _new_instance(root, feature_data)
                # Restore only the route's immutable identity. Provenance was
                # already validated against this exact public callback above.
                if route_journal is not None:
                    instance._completed_route = route_journal['route']
                    _store_instance_route_recovery(instance, route_journal)
                stager = getattr(instance, '_stage_spatial_recovery', None)
                if callable(stager):
                    stager(spatial_recovery)
                _INSTANCE = instance
            stage = 'entrypoint_runtime'
            output = instance.act(observation, cfg, entry_started=entry_started)
            # Publish only after a complete inner return. A foreign exception or
            # outer cancellation keeps the prior marker or discards the instance.
            instance._entrypoint_last_step = step
            inner = getattr(instance, 'diagnostics', {}) or {}
            selected = getattr(instance, 'selected', None)
            route = getattr(instance, '_completed_route', None)
            if (selected is not None
                    and inner.get('status') in ('completed', 'deadline_fallback')
                    and type(route) is str
                    and route):
                _store_instance_route_recovery(
                    instance,
                    {
                        'route_step': step,
                        'last_step': step,
                        'player': player,
                        'route': route,
                    })
            else:
                _store_instance_route_recovery(
                    instance,
                    _advance_route_recovery(
                        _instance_route_recovery(instance), step, player))
    except deadline.DeadlineExceeded as error:
        if error is not timer.expired:
            raise
        inner = getattr(instance, 'diagnostics', {}) if instance is not None else {}
        selected = getattr(instance, 'selected', None) if instance is not None else None
        if (selected is not None
                and inner.get('status') in ('completed', 'deadline_fallback')):
            stage = 'entrypoint_finalization'
        fallback = _entrypoint_fallback(instance, observation, cfg, deadline)
        prior_route = _instance_route_recovery(instance) or route_journal
        _record_entrypoint_deadline(instance, stage, entry_started)
        if instance is not None:
            instance.ready = False
        # Finalization may have been interrupted mid-mutation. Never expose that
        # object to the next observation; reconstruct from public state plus the
        # pre-call committed spatial journal, never current-call proposals.
        _SPATIAL_RECOVERY = _spatial_recovery_journal(spatial_recovery, step)
        # Only a producer action committed on THIS callback may move route_step.
        # Otherwise carry the immutable prior receipt and advance last_step only;
        # never read a possibly half-mutated live route to invent provenance.
        route = getattr(instance, '_completed_route', None) if instance is not None else None
        if (selected is not None
                and inner.get('status') in ('completed', 'deadline_fallback')
                and type(route) is str
                and route):
            _ROUTE_RECOVERY = {
                'route_step': step,
                'last_step': step,
                'player': player,
                'route': route,
            }
        else:
            _ROUTE_RECOVERY = _advance_route_recovery(prior_route, step, player)
        _INSTANCE = None
        return fallback
    _SPATIAL_RECOVERY = None
    _ROUTE_RECOVERY = None
    return output
