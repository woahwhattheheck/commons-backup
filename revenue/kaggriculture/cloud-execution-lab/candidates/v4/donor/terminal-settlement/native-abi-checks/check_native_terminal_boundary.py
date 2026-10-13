# SPDX-License-Identifier: Apache-2.0
"""Isolated native-finalizer/T01 composition checks, not full-game acceptance.

The fixture contains exact native methods; the PASS/DROP projector dependency is
an explicitly limited unit-mechanics fixture. The positive boundary is a support
reference for ASTRA-ENDPORT, not a competing installed runtime or production key.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
import types
import unittest

import json
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
DONOR_BLOB = '01a2f5ffe6f1eb18243f92a052125dffddd38409'
FINISH_SHA256 = 'f9b82a6c2574822a9db31aef4fd91d85950af75fd1d656a153bac53788f57f37'


def _unit_key(action: dict) -> str:
    # JSON distinguishes bool/int; explicit outer types distinguish tuples/lists.
    if (type(action) is not dict or type(action.get('farmer')) is not list
            or type(action.get('hands')) is not list
            or any(type(a) is not list for a in action['hands'])):
        raise ValueError('invalid unit actions')
    return json.dumps([action['farmer'], action['hands']],
                      ensure_ascii=True, allow_nan=False, separators=(',', ':'))


class ReferenceBoundary:
    """Positive-control model for this proof harness; not an installed native port.

    Only completed, final-step, nonterminal-route frozen actions are admitted.
    No callback, projection or diagnostics mutation occurs on OFF/skipped paths.
    Ordinary errors preserve both parent objects. BaseException cancellation is
    deliberately not caught, matching the native DeadlineExceeded contract.
    """
    def __init__(self, compose: Callable, project_units: Callable, *, enabled=False):
        if type(enabled) is not bool:
            raise TypeError('enabled must be an explicit bool')
        if not callable(compose) or not callable(project_units):
            raise TypeError('composer and selected-unit projector are required')
        self.compose = compose
        self.project_units = project_units
        self.enabled = enabled

    def __call__(self, agent: Any, obs: dict, cfg: dict,
                 selected: dict, post: dict | None) -> tuple[dict, dict | None]:
        if not self.enabled:
            return selected, post
        if (agent.diagnostics.get('status') != 'completed'
                or agent.features.consumer != 'frozen'
                or agent.features.terminal_route):
            return selected, post
        if type(obs) is not dict or type(cfg) is not dict:
            return selected, post
        step, length, seat = obs.get('step'), cfg.get('episodeSteps', 720), obs.get('player')
        if (type(step) is not int or type(length) is not int or length < 2
                or step != length - 2 or type(seat) is not int or seat not in (0, 1)
                or type(obs.get('farms')) is not list or len(obs['farms']) != 2):
            return selected, post
        try:
            _unit_key(selected)
            # Callback-owned copies prevent errors or trial mutation from leaking.
            frozen_obs, frozen_cfg = deepcopy(obs), deepcopy(cfg)
            projections = {}
            projection_calls = 0

            def record_project(o, action, c):
                nonlocal projection_calls
                projection_calls += 1
                if o != frozen_obs or c != frozen_cfg:
                    raise ValueError('projector observation/configuration drift')
                key = _unit_key(action)
                pair = self.project_units(deepcopy(frozen_obs), deepcopy(action),
                                          deepcopy(frozen_cfg))
                if (type(pair) is not tuple or len(pair) != 2
                        or type(pair[0]) is not dict or type(pair[1]) is not dict):
                    raise ValueError('projector must return (farm, private)')
                projections[key] = deepcopy(pair)
                return pair

            candidate, report = self.compose(
                deepcopy(frozen_obs), deepcopy(frozen_cfg), deepcopy(selected),
                project_units=record_project)
            if (type(candidate) is not dict or type(report) is not dict
                    or report.get('changed') is not True
                    or report.get('certified') is not True
                    or report.get('market_prefix_preserved') is not True
                    or type(report.get('guaranteed_min_cash_gain')) is not int
                    or report['guaranteed_min_cash_gain'] <= 0
                    or candidate == selected):
                return selected, post
            pair = projections.get(_unit_key(candidate))
            if pair is None:
                # A different last/rejected trial cannot certify this action.
                return selected, post
            returned = deepcopy(candidate)
            matching_post = deepcopy(frozen_obs)
            matching_post['farms'][seat], matching_post['private'] = deepcopy(pair)
            receipt = deepcopy(report)
            receipt.update(snapshot_step=step, snapshot_player=seat,
                           snapshot_unit_key=_unit_key(returned),
                           native_pre_receipt_boundary=True,
                           snapshot_stage='post_units_pre_market',
                           projection_calls=projection_calls)
        except Exception:
            return selected, post
        # Publish only after a complete action+snapshot packet has been built.
        agent.diagnostics['v4_terminal_settlement'] = receipt
        return returned, matching_post


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def composer():
    # Existing canonical custody, or explicit test input; never a downloaded replacement.
    choices = [Path(os.environ['T01_DONOR'])] if 'T01_DONOR' in os.environ else [
        HERE.parent/'terminal_settlement.py', HERE/'dependencies/terminal_settlement.py']
    path = next((p for p in choices if p.is_file()), None)
    if path is None:
        raise RuntimeError('set T01_DONOR to preserved exact terminal_settlement.py')
    if git_blob(path.read_bytes()) != DONOR_BLOB:
        raise RuntimeError('T01 donor blob mismatch')
    return load('_t01_native_test_donor', path).compose_terminal_settlement


COMPOSE = composer()
SOURCE = (HERE/'fixtures/native_runtime_excerpt.py').read_text()
TREE = ast.parse(SOURCE)
METHOD = TREE.body[-1].body[0]
METHOD_SOURCE = ''.join(SOURCE.splitlines(keepends=True)[METHOD.lineno-1:METHOD.end_lineno])
if hashlib.sha256(METHOD_SOURCE.encode()).hexdigest() != FINISH_SHA256:
    raise RuntimeError('native finalizer fixture drift')
ANCHOR = '        returned = self._early_capital_selected(obs, cfg or {}, returned)\n'
INSERT = (
    "        boundary = getattr(self, '_v4_terminal_settlement_boundary', None)\n"
    '        if boundary is not None:\n'
    '            returned, post = boundary(self, obs, cfg or {}, returned, post)\n'
)
if METHOD_SOURCE.count(ANCHOR) != 1:
    raise RuntimeError('native boundary anchor drift')
namespace = {}
exec(compile(SOURCE, 'exact_native_method_fixture', 'exec'), namespace)
Native = namespace['TitanAgent']
namespace = {}
exec(compile(SOURCE.replace(ANCHOR, ANCHOR+INSERT, 1), 'native_boundary_positive_control', 'exec'), namespace)
PairedNative = namespace['TitanAgent']


class Cancel(BaseException):
    """Same BaseException inheritance contract as native DeadlineExceeded."""


class DropPassMechanics:
    """Restricted PASS/DROP unit fixture; refuses every other action.

    DROP has the pinned engine's actor order, shed-capacity clamp, cargo dict
    order and overflow discard. This is not a full engine or a match simulator.
    """
    @staticmethod
    def _apply_unit_action(farm, private, idx, action, board, day, tpd, cap):
        if action == ['PASS']:
            return
        if action != ['DROP']:
            raise ValueError('test mechanics only supports exact PASS/DROP')
        positions = [farm['farmer'], *farm['hands']]
        if idx >= len(positions):
            return
        half = board//2
        access = {(half-1, half-1), (half, half-1), (half-1, half), (half, half)}
        if tuple(positions[idx]) not in access:
            return
        inv = private['inventories'][idx]
        shed = private['shed']
        for item, n in list(inv.items()):
            if n <= 0:
                del inv[item]
                continue
            room = max(0, cap-sum(shed.values()))
            take = min(n, room)
            if take > 0:
                shed[item] = shed.get(item, 0)+take
            del inv[item]


PROJECTOR = load('_native_selected_projector_fixture', HERE/'fixtures/native_projector_excerpt.py')
PROJECTOR.detached_json_value = deepcopy
PROJECTOR.m = DropPassMechanics
PROJECT = PROJECTOR.post_units


def world(seat=0, *, cargo=None, shed=None, hands=None):
    farm = {'farmer': [4, 4], 'hands': deepcopy(hands or []),
            'tiles': [[None]*10 for _ in range(10)], 'money': 3000}
    obs = {'step': 718, 'player': seat, 'day': 29, 'hour': 22,
           'farms': [deepcopy(farm), deepcopy(farm)],
           'private': {'shed': deepcopy(shed if shed is not None else {'EGG': 2}),
                       'seeds': {},
                       'inventories': deepcopy(cargo if cargo is not None else [{'EGG': 3}])},
           'market': {'inventory': {p: 10000 for p in ['EGG', 'MILK', 'WOOL']},
                      'prices': {'EGG': 50, 'MILK': 160, 'WOOL': 200}},
           'town': {'unlocked_shops': []}}
    obs['farms'][1-seat]['money'] = 9999
    obs['farms'][1-seat]['farmer'] = [9, 9]
    action = {'farmer': ['PASS'], 'hands': [['PASS'] for _ in farm['hands']],
              'market': [['SELL', 'EGG', 2]] if obs['private']['shed'].get('EGG', 0)>=2 else []}
    return obs, {'episodeSteps': 720, 'shedCapacity': 100}, action


class Receiver:
    def __init__(self, log):
        self.log=log
        self.fill_result=None
        self.diagnostics={}
        self.events=[]
        self.receipt_events=[]
        self.sale_obligation=None
        self.crop_intent=None
        self.remembered=None
        self.finished=None
    def observe_crop_receipts(self, *args): self.log.append('observe')
    def guard_returned(self, obs, selected, **kwargs):
        self.log.append('unit_guard'); return selected
    def guard_crop_returned(self, obs, selected, post):
        self.log.append('crop_guard'); return selected
    def finish(self, obs, selected, post=None):
        self.log.append('finish'); self.finished=(deepcopy(selected), deepcopy(post))
    def finish_crop(self, obs, selected, post, route, **kwargs):
        self.log.append('finish_crop'); self.crop_finished=(deepcopy(selected), deepcopy(post))
    def remember(self, obs, cfg, selected, post):
        self.log.append('remember'); self.remembered=(deepcopy(selected),deepcopy(post))


def make_agent(obs, cfg, selected, *, paired=True, enabled=True, status='completed',
               with_history=True, settle=COMPOSE, projector=PROJECT):
    base = PairedNative if paired else Native
    agent = base()
    agent.log=[]
    agent.features=types.SimpleNamespace(consumer='frozen',terminal_route=False,
        crop_release=False,terminal_history=with_history)
    agent.diagnostics={'status':status}
    agent.consumer=types.SimpleNamespace(selected_post_units=PROJECT(obs,selected,cfg),
        selected_post_units_binding=(obs['step'],obs['player'],deepcopy(selected['farmer']),deepcopy(selected['hands'])))
    agent.history=Receiver(agent.log) if with_history else None
    agent.spatial=Receiver(agent.log)
    agent.quadrant=Receiver(agent.log)
    agent._quadrant_admission=None
    agent.controller=types.SimpleNamespace(cur=0)
    def feed(self, o, c, a): self.log.append('feed'); return a
    def final_pressure(self, o, c, a): self.log.append('final_pressure'); return a
    agent._feed_stock_selected=types.MethodType(feed,agent)
    agent._early_capital_selected=types.MethodType(final_pressure,agent)
    boundary=ReferenceBoundary(settle,projector,enabled=enabled)
    def traced(self, o, c, a, post):
        self.log.append('terminal'); return boundary(self,o,c,a,post)
    agent._v4_terminal_settlement_boundary=traced
    return agent,boundary


class NativeBoundaryChecks(unittest.TestCase):
    def test_custody_and_fixture(self):
        self.assertEqual(hashlib.sha256(METHOD_SOURCE.encode()).hexdigest(),FINISH_SHA256)
        self.assertIn('return farm, private', (HERE/'fixtures/native_projector_excerpt.py').read_text())

    def test_paired_native_action_and_all_receipts(self):
        for seat in (0,1):
            with self.subTest(seat=seat):
                o,c,a=world(seat); agent,_=make_agent(o,c,a)
                output=agent._finish_production(o,a,c)
                self.assertEqual(output['farmer'],['DROP'])
                self.assertEqual(output['market'],[['SELL','EGG',5]])
                expected=PROJECT(o,output,c)
                for receiver in (agent.history.remembered,agent.spatial.finished,agent.spatial.crop_finished):
                    self.assertEqual(receiver[0],output)
                    self.assertEqual(receiver[1]['farms'][seat],expected[0])
                    self.assertEqual(receiver[1]['private'],expected[1])
                    self.assertEqual(receiver[1]['farms'][1-seat],o['farms'][1-seat])
                    self.assertEqual(receiver[1]['private']['shed']['EGG'],5)
                self.assertEqual(agent.quadrant.finished[0],output)
                self.assertLess(agent.log.index('final_pressure'),agent.log.index('terminal'))
                self.assertLess(agent.log.index('terminal'),agent.log.index('finish'))

    def test_naive_early_hook_is_killed_by_stale_post(self):
        o,c,a=world(); agent,boundary=make_agent(o,c,a,paired=False)
        def naive(self,o,c,a):
            return boundary(self,o,c,a,self._selected_snapshot(o,a))[0]
        agent._early_capital_selected=types.MethodType(naive,agent)
        result=agent._finish_production(o,a,c)
        self.assertEqual(result['farmer'],['DROP'])
        self.assertEqual(agent.history.remembered[1]['private']['shed']['EGG'],2)
        self.assertNotEqual(agent.history.remembered[1]['private'],PROJECT(o,result,c)[1])

    def test_post_return_wrapper_is_killed_by_action_receipt(self):
        o,c,a=world(); agent,boundary=make_agent(o,c,a,paired=False)
        before=agent._finish_production(o,a,c)
        after,_=boundary(agent,o,c,before,agent.history.remembered[1])
        self.assertEqual(after['farmer'],['DROP'])
        self.assertNotEqual(after,agent.history.remembered[0])

    def test_default_off_has_exact_identity_and_no_callbacks(self):
        o,c,a=world(); agent,_=make_agent(o,c,a)
        calls=[]
        def poison(*args,**kw):
            calls.append('unexpected');raise AssertionError('OFF callback')
        boundary=ReferenceBoundary(poison,poison)
        self.assertIs(boundary.enabled,False)
        post=object();diag=deepcopy(agent.diagnostics)
        result,snapshot=boundary(agent,o,c,a,post)
        self.assertIs(result,a);self.assertIs(snapshot,post)
        self.assertEqual(agent.diagnostics,diag)
        self.assertEqual(calls,[])

    def test_native_off_matches_unpatched_receipts(self):
        o,c,a=world(); new,_=make_agent(o,c,a,enabled=False); old,_=make_agent(o,c,a,paired=False)
        self.assertIs(new._finish_production(o,a,c),a)
        self.assertIs(old._finish_production(o,a,c),a)
        self.assertEqual(new.history.remembered,old.history.remembered)
        self.assertEqual(new.diagnostics,old.diagnostics)

    def test_fallback_skips_callbacks(self):
        o,c,a=world(); agent,_=make_agent(o,c,a,status='deadline_fallback')
        calls=[]
        def poison(*args,**kw):
            calls.append('unexpected');raise AssertionError('fallback callback')
        b=ReferenceBoundary(poison,poison,enabled=True)
        p=object();out,post=b(agent,o,c,a,p)
        self.assertIs(out,a);self.assertIs(post,p)
        self.assertEqual(calls,[])

    def test_nonfinal_and_domains_skip_before_projection(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        calls=[]
        def poison(*args,**kw):
            calls.append('unexpected');raise AssertionError('invalid domain callback')
        b=ReferenceBoundary(poison,poison,enabled=True)
        for key,values in [('step',[0,717,719,True,718.0,'718',None]),('player',[-1,2,True,0.0,'0',None])]:
            for value in values:
                with self.subTest(key=key,value=value):
                    changed=deepcopy(o);changed[key]=value;p=object()
                    out,post=b(agent,changed,c,a,p);self.assertIs(out,a);self.assertIs(post,p)
        for length in (True,720.0,'720',None,1):
            out,_=b(agent,o,dict(c,episodeSteps=length),a,None);self.assertIs(out,a)
        self.assertEqual(calls,[])

    def test_other_consumers_and_terminal_route_skip(self):
        o,c,a=world();agent,b=make_agent(o,c,a)
        for consumer,terminal in [('ordered',False),('parent',False),('frozen',True)]:
            agent.features.consumer=consumer;agent.features.terminal_route=terminal
            p=object();out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)

    def test_no_history_still_returns_correct_packet(self):
        o,c,a=world();agent,_=make_agent(o,c,a,with_history=False)
        result=agent._finish_production(o,a,c)
        self.assertEqual(agent.spatial.finished[0],result)
        self.assertEqual(agent.spatial.finished[1]['private'],PROJECT(o,result,c)[1])

    def test_no_gain_is_original_identity(self):
        o,c,a=world(cargo=[{}]);agent,b=make_agent(o,c,a);p=object()
        out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)

    def test_mixed_market_is_original_identity(self):
        o,c,a=world();a['market'].append(['HIRE']);agent,b=make_agent(o,c,a);p=object()
        out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)

    def test_sale_only_extra_stock_has_baseline_unit_binding(self):
        o,c,a=world(cargo=[{}],shed={'EGG':5});agent,b=make_agent(o,c,a)
        out,post=b(agent,o,c,a,None)
        self.assertEqual(out['farmer'],['PASS']);self.assertEqual(out['market'],[['SELL','EGG',5]])
        self.assertEqual(post['private']['shed']['EGG'],5)

    def test_last_rejected_trial_not_used_as_snapshot(self):
        # First actor adds two units. Later actor's full-shed DROP clears cargo
        # but adds zero units, so T01 rejects that trial. Its snapshot must not win.
        o,c,a=world(cargo=[{'EGG':2},{'EGG':1}],shed={'EGG':98},hands=[[4,4]])
        a['market']=[['SELL','EGG',98]];agent,b=make_agent(o,c,a)
        out,post=b(agent,o,c,a,None)
        self.assertEqual(out['farmer'],['DROP']);self.assertEqual(out['hands'],[['PASS']])
        self.assertEqual(post['private']['inventories'],[{}, {'EGG':1}])
        self.assertEqual(post['private'],PROJECT(o,out,c)[1])
        self.assertEqual(agent.diagnostics['v4_terminal_settlement']['projection_calls'],3)

    def test_snapshot_is_pre_market_not_post_sale(self):
        o,c,a=world();agent,b=make_agent(o,c,a);out,post=b(agent,o,c,a,None)
        self.assertEqual(post['private']['shed']['EGG'],5)
        self.assertEqual(post['market'],o['market'])
        self.assertEqual(post['farms'][0]['money'],o['farms'][0]['money'])

    def test_unit_and_public_state_are_detached(self):
        o,c,a=world();agent,b=make_agent(o,c,a);saved=deepcopy((o,c,a))
        out,post=b(agent,o,c,a,None)
        out['farmer'][0]='PASS';post['private']['shed']['EGG']=900
        post['farms'][1]['money']=0;post['market']['inventory']['EGG']=0
        self.assertEqual((o,c,a),saved)
        self.assertEqual(agent.consumer.selected_post_units_binding[2],['PASS'])

    def test_ordinary_composer_error_is_fail_closed(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        def broken(o,c,a,**kw):o.clear();c.clear();a.clear();raise ValueError('bad')
        b=ReferenceBoundary(broken,PROJECT,enabled=True);saved=deepcopy((o,c,a));p=object()
        out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)
        self.assertEqual((o,c,a),saved)

    def test_ordinary_projection_error_is_fail_closed(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        def broken(*args):raise ValueError('bad projector')
        b=ReferenceBoundary(COMPOSE,broken,enabled=True);p=object()
        out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)

    def test_cancellation_crosses_helper_and_adapter(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        for location in ('composer','projector'):
            expired=Cancel('same cancellation object')
            def stop(*args,**kw):raise expired
            b=ReferenceBoundary(stop if location=='composer' else COMPOSE,
                                         stop if location=='projector' else PROJECT,enabled=True)
            with self.assertRaises(Cancel) as caught:b(agent,o,c,a,None)
            self.assertIs(caught.exception,expired)
            self.assertNotIn('v4_terminal_settlement',agent.diagnostics)

    def test_unprojected_candidate_fails_closed(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        def fake(o,c,a,**kw):
            a['farmer']=['DROP'];return a,{'changed':True,'certified':True,
                'market_prefix_preserved':True,'guaranteed_min_cash_gain':3}
        b=ReferenceBoundary(fake,PROJECT,enabled=True);p=object()
        out,post=b(agent,o,c,a,p);self.assertIs(out,a);self.assertIs(post,p)

    def test_uncertified_report_rejected(self):
        o,c,a=world();agent,_=make_agent(o,c,a)
        for value in (False,1,'true',None):
            def broken(o,c,a,**kw):
                out,rep=COMPOSE(o,c,a,**kw);rep['certified']=value;return out,rep
            b=ReferenceBoundary(broken,PROJECT,enabled=True)
            self.assertIs(b(agent,o,c,a,None)[0],a)

    def test_parameterized_capacity_seats_and_overlapping_actors(self):
        cases=0
        for seat in (0,1):
            for stock in (0,1,95,98,99,100):
                for q0 in (0,1,2,5):
                    for q1 in (0,1,3):
                        for cap in (99,100):
                            cases+=1
                            o,c,a=world(seat,cargo=[{'EGG':q0},{'EGG':q1}],
                                        shed={'EGG':stock},hands=[[4,4]])
                            c['shedCapacity']=cap
                            agent,b=make_agent(o,c,a)
                            saved=deepcopy((o,c,a));out,post=b(agent,o,c,a,None)
                            if out is not a:
                                self.assertEqual(post['private'],PROJECT(o,out,c)[1])
                                self.assertEqual(post['farms'][seat],PROJECT(o,out,c)[0])
                                requested=sum(row[2] for row in out['market'])
                                self.assertLessEqual(requested,post['private']['shed']['EGG'])
                            self.assertEqual((o,c,a),saved)
        self.assertEqual(cases,288)

    def test_enabled_must_be_explicit_bool(self):
        for value in (1,'true',None,[]):
            with self.assertRaises(TypeError):ReferenceBoundary(COMPOSE,PROJECT,enabled=value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
