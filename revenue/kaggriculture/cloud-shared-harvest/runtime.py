# SPDX-License-Identifier: Apache-2.0
"""One opt-in, returned-command-bound route patch on the existing producer.

The proposal's production certificate applies to its admitted schedule. Recovery
tracks remaining command order; yield and sale value need separate evidence.
Optional delivery is never promised to the SELL consumer in advance.
"""
from copy import deepcopy
from functools import wraps

from day_end_delivery import (guard_delivery, move, path, propose_delivery,
                              set_unit, unit)


def _units(action):
    return (action.get('farmer', ['PASS']), action.get('hands', []))


class SourceContractMismatch(RuntimeError):
    """The selected producer action invalidated an already exposed DROP.

    This is an operational failure, not a successful baseline fallback: the
    producer may already have derived market intent from the exposed arrival.
    """


class Runtime:
    def __init__(self, agent, mechanics, audit, branch_steps):
        self.agent, self.mechanics, self.audit = agent, mechanics, audit
        self.branch_steps = tuple(int(step) for step in branch_steps)
        self.configuration = {}
        self.plan = None
        self.recovery = None
        self.pending = None
        self.events = []
        self.candidate_reports = []
        self.controller = None
        self.pristine = None
        self.edits = []
        self.last_finished = None

    def _event(self, step, kind, **fields):
        self.events.append(dict(step=step, kind=kind, **fields))
        del self.events[:-13]

    def _report(self, report):
        self.candidate_reports.append(report)
        del self.candidate_reports[:-13]

    def _restore(self):
        if self.controller is not None:
            for route, step in self.edits:
                self.controller.R[route][step] = self.pristine[route][step]
        self.edits = []

    def _patch(self, route, step, actor, command):
        row = deepcopy(self.controller.R[route][step])
        set_unit(row, actor, command)
        self.controller.R[route][step] = row
        if (route, step) not in self.edits:
            self.edits.append((route, step))

    def _position(self, observation, actor):
        farm = observation['farms'][observation['player']]
        return tuple(farm['hands'][actor - 1]) if actor <= len(farm['hands']) else None

    def _recover(self, plan, observation):
        now = int(observation['step'])
        position = self._position(observation, plan['worker'])
        if position is None:
            self._event(now, 'worker_absent', mandatory_preservation=False)
            return None
        left = plan['end'] - now
        commands, due = [], []
        cursor = position
        for task in plan['tasks'][plan['completed']:]:
            commands.extend(path(cursor, task['position']))
            due.append(now + len(commands))
            commands.append(list(task['action']))
            cursor = tuple(task['position'])
        mandatory_fits = len(commands) <= left
        to_shed = path(cursor, plan['goal'])
        delivery = mandatory_fits and len(commands) + len(to_shed) + 1 <= left
        if delivery:
            commands += to_shed
            commands += [['PASS']] * (left - len(commands) - 1) + [['DROP']]
        else:
            commands = commands[:left]
            commands += [['PASS']] * (left - len(commands))
        for task, step in zip(plan['tasks'][plan['completed']:], due):
            task['due'] = step
        plan.update(schedule_step=now, schedule=commands, origin=list(position),
                    expected_position=list(position), force_recovery=False,
                    delivery_enabled=delivery, recovered=True,
                    mandatory_preservation=mandatory_fits)
        self._event(now, 'recovery', worker=plan['worker'],
                    mandatory_preservation=mandatory_fits,
                    optional_delivery=delivery,
                    production_certificate_applies=False)
        return plan

    def _prepare(self, observation):
        self._restore()
        self.pending = None
        now = int(observation['step'])
        committed = self.plan if self.plan is not None else self.recovery
        if committed is None:
            return None
        if now >= committed['end'] or now < committed['step']:
            self._event(now, 'expired', worker=committed['worker'],
                        remaining_tasks=len(committed['tasks']) - committed['completed'])
            self.plan = self.recovery = None
            return None
        plan = deepcopy(committed)
        position = self._position(observation, plan['worker'])
        overdue = (plan['completed'] < len(plan['tasks'])
                   and plan['tasks'][plan['completed']]['due'] < now)
        if (plan.get('force_recovery') or overdue
                or position != tuple(plan['expected_position'])
                or now != plan.get('next_step', now)):
            plan = self._recover(plan, observation)
            if plan is None:
                self.plan = self.recovery = None
                return None
        self._expose(plan, observation)
        return plan

    def _expose(self, plan, observation):
        now = int(observation['step'])
        route = self.controller.cur
        if route != plan['route']:
            self._event(now, 'route_changed', mandatory_preservation=False,
                        production_certificate_applies=False)
            plan['route'] = route
            plan['recovered'] = True
        for step in range(now, plan['end']):
            command = plan['schedule'][step - plan['schedule_step']]
            # Conditional future arrivals must not appear in projected_shed.
            visible = ['PASS'] if command == ['DROP'] else command
            self._patch(route, step, plan['worker'], visible)
        current = plan['schedule'][now - plan['schedule_step']]
        if current == ['DROP']:
            allowed, report = guard_delivery(
                self.mechanics, observation, self.controller.R[route][now],
                plan['worker'], self.configuration)
            self._event(now, 'delivery_guard', allowed=allowed, report=report)
            if allowed:
                self._patch(route, now, plan['worker'], ['DROP'])

    def _new_plan(self, proposal, route):
        plan = deepcopy(proposal)
        plan.update(route=route, schedule_step=plan['step'],
                    schedule=deepcopy(plan['replacement']),
                    expected_position=list(plan['origin']), completed=0,
                    tasks=[dict(deepcopy(task), due=plan['step'] + task['offset'])
                           for task in plan['mandatory_tasks']],
                    delivery_enabled=True, mandatory_preservation=True,
                    force_recovery=False, recovered=False)
        return plan

    def install(self, controller):
        if controller is self.controller:
            return
        self._restore()
        self.controller = controller
        # Only table/list structure is copied. Every changed row is detached
        # separately; pristine source rows remain available after cancellation.
        if isinstance(controller.R, dict):
            self.pristine = {key: list(rows) for key, rows in controller.R.items()}
            controller.R = {key: list(rows) for key, rows in self.pristine.items()}
        else:
            self.pristine = [list(rows) for rows in controller.R]
            controller.R = [list(rows) for rows in self.pristine]
        original = controller.act

        @wraps(original)
        def act(observation):
            plan = self._prepare(observation)
            admitted_drop = (plan is not None and unit(
                controller.R[controller.cur][int(observation['step'])],
                plan['worker']) == ['DROP'])
            selected = original(observation)  # The only producer invocation.
            now = int(observation['step'])
            if plan is None:
                # Bound the optional experiment to at most thirteen actions.
                per_day = int(self.configuration.get('turnsPerDay', 24))
                left = per_day - now % per_day
                if 3 <= left <= 13:
                    proposal, report = propose_delivery(
                        self.mechanics, observation, selected,
                        controller.R[controller.cur], self.configuration,
                        audit=self.audit, branch_steps=self.branch_steps)
                    self._report(report)
                    if proposal is not None:
                        plan = self._new_plan(proposal, controller.cur)
                        self._expose(plan, observation)
                        selected = deepcopy(selected)
                        set_unit(selected, plan['worker'],
                                 unit(controller.R[controller.cur][now], plan['worker']))
            elif controller.cur != plan['route']:
                # Unexpected live branch: retain the displaced worker's task
                # order, but withdraw the admitted-schedule certificate.
                self._expose(plan, observation)
                selected = deepcopy(selected)
                set_unit(selected, plan['worker'],
                         unit(controller.R[controller.cur][now], plan['worker']))
            if plan is not None:
                if _units(selected) != _units(controller.R[controller.cur][now]):
                    plan['recovered'] = True
                    self._event(now, 'producer_unit_divergence',
                                production_certificate_applies=False)
                if admitted_drop or unit(selected, plan['worker']) == ['DROP']:
                    allowed, report = guard_delivery(
                        self.mechanics, observation, selected, plan['worker'],
                        self.configuration)
                    if not allowed:
                        self._event(now, 'selected_delivery_contract_mismatch', report=report)
                        self._restore()
                        self._diagnostics()
                        raise SourceContractMismatch(
                            'Selected joint action invalidated admitted delivery: '
                            + report['reason'])
                self.pending = {'step': now, 'plan': plan,
                                'selected': deepcopy(selected)}
            return selected

        controller.act = act

    def finish(self, observation, returned):
        now = int(observation['step'])
        pending = self.pending if self.pending and self.pending['step'] == now else None
        if self.last_finished == now:
            self._diagnostics()
            return
        self.last_finished = now
        self.pending = None
        source = pending['plan'] if pending else (self.plan or self.recovery)
        if source is not None and (now >= source['end'] or now < source['step']):
            # A deadline can bypass controller.act entirely on the boundary.
            self._restore()
            self._event(now, 'expired', worker=source['worker'],
                        remaining_tasks=len(source['tasks']) - source['completed'])
            self.plan = self.recovery = source = None
        if source is not None and now < source['end']:
            updated = deepcopy(source)
            position = self._position(observation, updated['worker'])
            actual = unit(returned, updated['worker'])
            # Observed position and returned command together establish that a
            # stationary task was attempted; a same-position PASS does not.
            if position is not None and updated['completed'] < len(updated['tasks']):
                task = updated['tasks'][updated['completed']]
                if position == tuple(task['position']) and actual == task['action']:
                    updated['completed'] += 1
            if position is not None:
                updated['expected_position'] = list(move(position, actual, 10))
            updated['next_step'] = now + 1
            expected_command = updated['schedule'][now - updated['schedule_step']]
            if actual != expected_command:
                # A live producer intervention can itself be exactly returned.
                # That does not mean its replaced scheduled task was completed.
                updated['force_recovery'] = True
                updated['recovered'] = True
            exact = pending is not None and _units(returned) == _units(pending['selected'])
            if exact:
                self.plan, self.recovery = updated, None
                self._event(now, 'committed', worker=updated['worker'],
                            completed_tasks=updated['completed'])
            else:
                updated['force_recovery'] = True
                updated['recovered'] = True
                self._restore()
                if self.plan is not None:
                    # Retain obligations from a previously committed patch;
                    # an unreturned new recovery schedule is not committed.
                    retained = deepcopy(self.plan)
                    for key in ('completed', 'expected_position', 'next_step',
                                'force_recovery', 'recovered'):
                        retained[key] = updated[key]
                    self.plan = retained
                elif pending is not None and actual != unit(
                        self.pristine[updated['route']][now], updated['worker']):
                    # Some altered work may have been returned despite another
                    # unit's mismatch. Keep an uncommitted recovery obligation
                    # instead of resuming a pristine tape at the wrong location.
                    self.recovery = updated
                self._event(now, 'cancelled', worker=updated['worker'],
                            recovery_obligation=self.plan is not None or self.recovery is not None)
        self._diagnostics()

    def _diagnostics(self):
        plan = self.plan or self.recovery
        self.agent.diagnostics['shared_harvest'] = {
            'events': deepcopy(self.events),
            'candidate_reports': deepcopy(self.candidate_reports),
            'active': None if plan is None else {
                'step': plan['step'], 'end': plan['end'], 'worker': plan['worker'],
                'committed': self.plan is not None, 'completed_tasks': plan['completed'],
                'mandatory_tasks': len(plan['tasks']),
                'mandatory_preservation': plan['mandatory_preservation'],
                'production_certificate_applies': not plan['recovered'],
                'optional_delivery': plan['delivery_enabled']},
            'market_receipt_gain': None,
        }


def attach(agent, mechanics, audit, branch_steps=()):
    """Attach to one nonterminal frozen TitanAgent without replacing its hooks.

    The agent's regular act method supplies the actual configuration. Existing
    initialization, finish and market-pressure processing run exactly once.
    """
    conflicts = [name for name in ('spatial_pathing', 'spatial_tempo',
                                  'fourth_quadrant', 'terminal_route')
                 if getattr(agent.features, name, False)]
    if conflicts or getattr(agent.features, 'consumer', 'frozen') != 'frozen':
        raise ValueError('shared harvest requires the sole nonterminal frozen producer: '
                         + ', '.join(conflicts))
    if getattr(agent, '_shared_harvest_runtime', None) is not None:
        raise ValueError('shared harvest is already attached')
    runtime = Runtime(agent, mechanics, audit, branch_steps)
    original_initialize = agent._initialize
    original_finish = agent._finish_production
    original_act = agent.act

    @wraps(original_initialize)
    def initialize(*args, **kwargs):
        result = original_initialize(*args, **kwargs)
        runtime.install(agent.controller)
        return result

    @wraps(original_finish)
    def finish(observation, returned):
        result = original_finish(observation, returned)
        runtime.finish(observation, returned)
        return result

    @wraps(original_act)
    def act(observation, configuration=None, *, entry_started=None):
        runtime.configuration = dict(configuration or {})
        return original_act(observation, configuration, entry_started=entry_started)

    agent._initialize, agent._finish_production, agent.act = initialize, finish, act
    agent._shared_harvest_runtime = runtime
    if getattr(agent, 'ready', False):
        runtime.install(agent.controller)
    return runtime
