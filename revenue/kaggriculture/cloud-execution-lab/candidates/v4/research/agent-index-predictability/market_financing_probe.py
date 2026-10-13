"""Official-interpreter cash attribution for market-order research, not a policy.

Reuse compare_actions(context, state, env, seat, candidate_action) with an existing
candidate. Rival actions/private stores are evaluation inputs, NEVER policy inputs.
The bundled experiment applies exact incumbent pressure bytes to synthetic states.
It measures financing externalities, not their prevalence or full-game strength.
"""
from __future__ import annotations

import argparse
import builtins
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
from typing import Any

PINS = {
    'reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'reference/evaluator/evaluate.py': '1fb6b655bb4ca1e1684be165a8ef513e2e6c2325',
    'reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
    'pressure_priority.py': '7261674962d10fc8bc6af5ff73ff9212c40f61ad',
    'sell_priority.py': 'd832174e26451d2bbe326991cc206a212cfebc12',
}
GOODS = ('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL')
_LOCK = threading.RLock()


class ProbeError(ValueError):
    """Evidence, source or accounting contract was not met."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load_context(lab: Path, pressure_path: Path) -> SimpleNamespace:
    """Consume the existing evaluator/loader; validate every byte BEFORE execution.

    Captured sources execute from a temporary fixture copy, so the existing
    loader cannot fetch a missing file or reread a changed original. Its temporary
    module registrations are restored. This is an isolated research process API,
    not an instrumentation hook for concurrent production agent execution.
    """
    lab, pressure_path = Path(lab).resolve(), Path(pressure_path).resolve()
    paths = {name: lab / name for name in PINS if name.startswith('reference/')}
    paths.update({'pressure_priority.py': pressure_path,
                  'sell_priority.py': pressure_path.with_name('sell_priority.py')})
    captured, sources = {}, {}
    for name, expected in PINS.items():
        data = paths[name].read_bytes()
        actual = git_blob(data)
        if actual != expected:
            raise ProbeError('source pin mismatch: ' + name)
        captured[name] = data
        sources[name] = {'git_blob': actual, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    names = ('kaggle_environments', 'kaggle_environments.utils', 'kag_eval_existing_loader')
    missing = object()
    with _LOCK:
        saved = {name: sys.modules.get(name, missing) for name in names}
        try:
            with tempfile.TemporaryDirectory(prefix='titan-financing-sources-') as folder:
                root = Path(folder)
                for name, data in captured.items():
                    dest = root / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                ev = ModuleType('titan_financing_existing_evaluator')
                ev.__file__ = str(root / 'reference/evaluator/evaluate.py')
                exec(compile(captured['reference/evaluator/evaluate.py'], ev.__file__, 'exec'), ev.__dict__)
                engine, _ = ev.get_engine(root / 'reference/engine', root / 'reference/evaluator/loader.py')
        finally:
            for name, module in saved.items():
                if module is missing:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
    sell = ModuleType('titan_financing_pinned_sell')
    exec(compile(captured['sell_priority.py'], str(paths['sell_priority.py']), 'exec'), sell.__dict__)
    native_import = builtins.__import__

    def imports(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'sell_priority' and level == 0:
            return sell
        return native_import(name, globals, locals, fromlist, level)

    pressure = ModuleType('titan_financing_pinned_pressure')
    pressure.__dict__['__builtins__'] = dict(vars(builtins), __import__=imports)
    exec(compile(captured['pressure_priority.py'], str(pressure_path), 'exec'), pressure.__dict__)
    return SimpleNamespace(engine=engine, ev=ev, pressure=pressure, sources=sources,
                           protected_paths=frozenset(paths.values()))


def fixture(ctx, *, item='MILK', stock=(2, 2), cash=(0, 682), inventory=10000,
            seat=0, step=718, cap=10, hires=0):
    """Build explicit synthetic post-unit-compatible microstates, not replay claims.

    Stock/cash are in logical (own, rival) order, independent of physical seat.
    All unit actions PASS. Existing workers, when requested, have matching private
    inventory entries. Town is empty; at default terminal step718 no shop tick runs.
    """
    if type(seat) is not int or seat not in (0, 1):
        raise ProbeError('physical seat must be integer 0 or 1')
    if item not in GOODS or any(type(x) is not int or x < 0 or x > 100 for x in stock):
        raise ProbeError('invalid synthetic shed stock')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in cash):
        raise ProbeError('invalid starting cash')
    e, S = ctx.engine, ctx.ev.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v for k, v in e.specification['configuration'].items()})
    cfg.weedSpawnChance, cfg.maxMarketOrdersPerTurn = 0, cap
    farms = [e._new_farm(10, cash[p ^ seat]) for p in range(2)]
    market = e._new_market()
    market['inventory'][item] = inventory
    e._refresh_prices(market)
    town, state = {'unlocked_shops': []}, []
    for p in range(2):
        private = e._new_private()
        private['shed'][item] = stock[p ^ seat]
        if p != seat:
            for _ in range(hires):
                farms[p]['hands'].append(e._spawn_hand(farms[p], 10))
                private['inventories'].append({})
            farms[p]['hires_today'] = hires
        state.append(S(observation=S(player=p, step=step, day=step // 24, hour=step % 24,
                                     farms=farms, market=market, town=town, private=private),
                       action={'farmer': ['PASS'], 'hands': [['PASS'] for _ in farms[p]['hands']], 'market': []},
                       status='ACTIVE', reward=0))
    return state, S(configuration=cfg, done=False, info={'seed': 9600803})


def snapshot(state):
    return {'farms': copy.deepcopy(state[0].observation.farms),
            'market': copy.deepcopy(state[0].observation.market),
            'town': copy.deepcopy(state[0].observation.town),
            'private': [copy.deepcopy(s.observation.private) for s in state],
            'status': [s.status for s in state], 'reward': [s.reward for s in state],
            'clocks': [{key: getattr(s.observation, key, None) for key in ('player', 'step', 'day', 'hour')} for s in state]}


def run_action(ctx, state, env, seat, action):
    """Run the WHOLE official interpreter and wrap only committed cash operations.

    The wrappers call the unmodified official functions. Quotes, raw truncation,
    accept/reject, capacity, lockstep, units, town, EOD and rewards stay official.
    The private copy of the engine must not be used concurrently outside this API.
    """
    if type(seat) is not int or seat not in (0, 1) or len(state) != 2:
        raise ProbeError('exactly two physical seats required')
    trial, trial_env = copy.deepcopy((state, env))
    trial[seat].action = copy.deepcopy(action)
    farms = trial[0].observation.farms
    indices = {id(farm): i for i, farm in enumerate(farms)}
    initial = [float(farm['money']) for farm in farms]
    events = []
    e = ctx.engine
    with _LOCK:
        originals = {name: getattr(e, name) for name in ('_commit_unit', '_do_hire', '_do_buy_land')}

        def record(farm, before, op, item, ok):
            events.append({'seat': indices[id(farm)], 'op': op, 'item': item,
                           'ok': bool(ok), 'cash_delta': float(farm['money']) - before})

        def commit(op, item, price, farm, private, market, capacity):
            before = float(farm['money'])
            ok = originals['_commit_unit'](op, item, price, farm, private, market, capacity)
            record(farm, before, op, item, ok)
            return ok

        def hire(farm, private, board_size, mult=1):
            before, count = float(farm['money']), len(farm['hands'])
            result = originals['_do_hire'](farm, private, board_size, mult)
            record(farm, before, 'HIRE', None, len(farm['hands']) > count)
            return result

        def land(farm, board_size):
            before, count = float(farm['money']), len(farm['unlocked_quadrants'])
            result = originals['_do_buy_land'](farm, board_size)
            record(farm, before, 'BUY_LAND', None, len(farm['unlocked_quadrants']) > count)
            return result

        e._commit_unit, e._do_hire, e._do_buy_land = commit, hire, land
        try:
            e.interpreter(trial, trial_env)
        finally:
            for name, original in originals.items():
                setattr(e, name, original)
    post = snapshot(trial)
    actors = []
    for p in range(2):
        own_events = [event for event in events if event['seat'] == p]
        sales = sum(event['cash_delta'] for event in own_events if event['op'] == 'SELL')
        spend = -sum(event['cash_delta'] for event in own_events if event['op'] != 'SELL')
        final = float(farms[p]['money'])
        other = final - initial[p] - sales + spend
        if any(not math.isfinite(x) for x in (sales, spend, final, other)):
            raise ProbeError('non-finite cash evidence')
        if sales < 0 or spend < 0:
            raise ProbeError('cash operation sign conflict')
        actors.append({'initial_cash': initial[p], 'final_cash': final,
                       'sales': sales, 'spend': spend, 'other_cash': other,
                       'reward': trial[p].reward, 'status': trial[p].status,
                       'events': own_events,
                       'assets': {'hands': len(farms[p]['hands']),
                                  'quadrants': list(farms[p]['unlocked_quadrants']),
                                  'shed': copy.deepcopy(trial[p].observation.private['shed']),
                                  'seeds': copy.deepcopy(trial[p].observation.private['seeds'])}})
    return {'own': actors[seat], 'rival': actors[1 - seat], 'poststate_sha256': digest(post)}


def compare_actions(ctx, state, env, seat, candidate_action):
    """Independent paired evaluation; supplies no rival information to a policy."""
    parent = run_action(ctx, state, env, seat, state[seat].action)
    candidate = run_action(ctx, state, env, seat, candidate_action)
    delta = {actor: {key: candidate[actor][key] - parent[actor][key]
                     for key in ('final_cash', 'sales', 'spend', 'other_cash')}
             for actor in ('own', 'rival')}
    sale_margin = delta['own']['sales'] - delta['rival']['sales']
    spend_effect = delta['rival']['spend'] - delta['own']['spend']
    other_effect = delta['own']['other_cash'] - delta['rival']['other_cash']
    cash_margin = delta['own']['final_cash'] - delta['rival']['final_cash']
    if not math.isclose(cash_margin, sale_margin + spend_effect + other_effect, abs_tol=1e-8):
        raise ProbeError('paired cash attribution does not reconcile')
    return {'seat': seat, 'parent_action': copy.deepcopy(state[seat].action),
            'candidate_action': copy.deepcopy(candidate_action),
            'rival_action': copy.deepcopy(state[1 - seat].action),
            'changed': candidate_action != state[seat].action,
            'parent': parent, 'candidate': candidate, 'delta': delta,
            'delta_sale_margin': sale_margin, 'delta_spend_effect': spend_effect,
            'delta_other_effect': other_effect, 'delta_cash_margin': cash_margin}


def pressure_pair(ctx, *, own=None, rival=None, **kwargs):
    state, env = fixture(ctx, **kwargs)
    seat = kwargs.get('seat', 0)
    state[seat].action['market'] = copy.deepcopy(own if own is not None else [[], ['SELL', 'MILK', 2]])
    state[1 - seat].action['market'] = copy.deepcopy(rival if rival is not None else [['SELL', 'MILK', 2], ['BUY_LAND']])
    action = ctx.pressure.transform(copy.deepcopy(state[seat].action),
                                    copy.deepcopy(state[seat].observation),
                                    copy.deepcopy(env.configuration), quote=ctx.engine.market_price)
    return compare_actions(ctx, state, env, seat, action)


def panel(ctx):
    """Threshold-calibrated synthetic stress, not an unbiased EV/field sample."""
    operations = [('HIRE', ['HIRE'], 13), ('LAND', ['BUY_LAND'], 0),
                  ('COW', ['BUY_ANIMAL', 'COW', 1], 0),
                  ('SEED', ['BUY_SEED', 'WHEAT', 40], 0),
                  ('INPUT', ['BUY_PRODUCT', 'FERTILIZER', 40], 0)]
    # Sizes and thresholds are declared in code. Cost calibration uses executed
    # synthetic controls, not future/replay data, and is reported explicitly.
    costs = {}
    for name, order, hires in operations:
        state, env = fixture(ctx, stock=(0, 0), cash=(0, 100000), hires=hires)
        state[1].action['market'] = [order]
        result = run_action(ctx, state, env, 0, state[0].action)
        costs[name] = result['rival']['spend']
    counts = {'pairs': 0, 'changed': 0, 'cash_negative': 0, 'cash_zero': 0, 'cash_positive': 0,
              'sale_margin_negative': 0, 'spend_changed': 0, 'terminal_new_losses': 0,
              'thresholds_skipped_negative_initial_cash': 0}
    grouped, examples, stream = {}, [], hashlib.sha256()
    worst = None
    for item in GOODS:
        for inventory in (9800, 10000, 11000):
            for requested, available in ((1, 1), (2, 2), (5, 3)):
                own = [[], ['SELL', item, requested]]
                sell = ['SELL', item, requested]
                raw = pressure_pair(ctx, own=own, rival=[sell], item=item, inventory=inventory,
                                    stock=(available, available), cash=(0, 0))
                revenue = raw['parent']['rival']['sales']
                for name, order, hires in operations:
                    for offset in (-1, 0, 1, 2):
                        initial = costs[name] - revenue + offset
                        if initial < 0:
                            counts['thresholds_skipped_negative_initial_cash'] += 2
                            continue
                        for seat in (0, 1):
                            result = pressure_pair(ctx, own=own, rival=[sell, order], item=item,
                                                   inventory=inventory, stock=(available, available),
                                                   cash=(0, initial), seat=seat, hires=hires)
                            case = {'item': item, 'inventory': inventory, 'requested': requested,
                                    'physical_stock': available, 'operation': name,
                                    'cost_control': costs[name], 'rival_initial_cash': initial,
                                    'cash_offset': offset, 'seat': seat}
                            row = {'case': case, 'result': result}
                            stream.update(canonical(row))
                            dm = result['delta_cash_margin']
                            counts['pairs'] += 1
                            counts['changed'] += int(result['changed'])
                            counts['cash_negative' if dm < 0 else 'cash_positive' if dm > 0 else 'cash_zero'] += 1
                            counts['sale_margin_negative'] += int(result['delta_sale_margin'] < 0)
                            counts['spend_changed'] += int(result['delta_spend_effect'] != 0)
                            old_margin = result['parent']['own']['final_cash'] - result['parent']['rival']['final_cash']
                            new_margin = result['candidate']['own']['final_cash'] - result['candidate']['rival']['final_cash']
                            counts['terminal_new_losses'] += int(old_margin >= 0 and new_margin < 0)
                            g = grouped.setdefault(name, {'pairs': 0, 'negative': 0, 'minimum_delta_cash_margin': 0})
                            g['pairs'] += 1
                            g['negative'] += int(dm < 0)
                            g['minimum_delta_cash_margin'] = min(g['minimum_delta_cash_margin'], dm)
                            if worst is None or dm < worst['result']['delta_cash_margin']:
                                worst = row
                            if dm < 0 and not any(x['case']['operation'] == name for x in examples):
                                examples.append(row)
    witnesses = {str(seat): pressure_pair(ctx, seat=seat) for seat in (0, 1)}
    return {'schema': 'titan.market-financing-evidence.v1', 'sources': ctx.sources,
            'scope': 'Exact incumbent component plus full official interpreter on synthetic microstates. No replay, full-game, frequency or promotion claim.',
            'panel_design': {'products': list(GOODS), 'inventories': [9800, 10000, 11000],
                             'requested_available': [[1, 1], [2, 2], [5, 3]],
                             'offsets': [-1, 0, 1, 2], 'physical_seats': [0, 1],
                             'operations': [x[0] for x in operations], 'declared_grid_slots': 2520,
                             'cash_calibration': 'successful full purchase cost minus parent sale receipts plus offset',
                             'step': 718, 'default_market_cap': 10},
            'counts': counts, 'by_operation': grouped, 'result_stream_sha256': stream.hexdigest(),
            'land_flip_both_seats': witnesses, 'first_negative_per_operation': examples, 'worst': worst,
            'identity': 'delta cash margin = delta sale margin + delta rival spend - delta own spend + delta other cash margin'}


def write_report(path: Path, report: dict, protected=()):
    path = Path(path).resolve()
    if path in {Path(p).resolve() for p in protected} or path.suffix.lower() != '.json':
        raise ProbeError('output must be a non-source .json path')
    data = canonical(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as f:
            temporary = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    here = Path(__file__).resolve()
    default_lab = here.parents[4] if len(here.parents) > 4 else Path.cwd()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lab', type=Path, default=default_lab)
    ap.add_argument('--pressure', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(argv)
    pressure = args.pressure or args.lab.parent / 'cloud-opponent-league/lark-responsive/pressure_priority.py'
    try:
        ctx = load_context(args.lab, pressure)
        protected = ctx.protected_paths | {here, here.with_name('test_market_financing_probe.py')}
        if args.output.resolve() in protected or args.output.suffix.lower() != '.json':
            raise ProbeError('output must be a non-source .json path')
        report = panel(ctx)
        write_report(args.output, report, protected)
        print(json.dumps(report['counts'], sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print('market financing probe: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
