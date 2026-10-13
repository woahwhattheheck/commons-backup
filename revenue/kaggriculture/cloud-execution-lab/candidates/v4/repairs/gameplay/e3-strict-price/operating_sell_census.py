# SPDX-License-Identifier: Apache-2.0
"""Read-only staged census of the pinned native TITAN entrypoint.

No strategy, default, installer, market edit or production file write. Runtime
wrapping observes A=operating-stock input, B=feed-stock input (after crop guards),
C=feed-stock output, D=the exact entrypoint return. A missing/incomplete stage is
never an empty stage. This is observational evidence, not permission to port E3.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

PINS = {
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'operating_stock.py': '781aa90da0d85d0ba23c665e29d6087d182c085e',
    'TITAN-CONFIG.json': '3a3bef83899d3010fad623b628d9e95d9978111b',
}
ENGINE_PINS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
PRODUCTS = ('WHEAT', 'FERTILIZER')
STAGES = ('A', 'B', 'C', 'D')
DIAGNOSTICS = ('status', 'fallback_stage', 'operating_stock', 'feed_stock',
               'crop_release', 'crop_release_action', 'early_capital', 'market_pressure')


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def fingerprint(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Not an ordinary input file: {path}')
    data = path.read_bytes()
    return {'bytes': len(data), 'git_blob': blob(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def check_pins(root: Path, pins: dict[str, str]) -> dict:
    root = root.resolve(strict=True)
    result = {}
    for name, expected in pins.items():
        path = root / name
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(f'Escaped input: {name}')
        actual = fingerprint(path)
        if actual['git_blob'] != expected:
            raise ValueError(f'Pin mismatch {name}: {actual["git_blob"]} != {expected}')
        result[name] = actual
    return result


def read_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError(f'Nonfinite JSON: {value}')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=nonfinite)


def prefix(action: dict, cfg: dict) -> list:
    cap = cfg.get('maxMarketOrdersPerTurn', 10)
    if type(cap) is not int:
        raise ValueError('Market cap must be an exact integer')
    if not isinstance(action, dict) or type(action.get('market')) is not list:
        raise ValueError('Action must contain a raw market list')
    # Do not compact falsey slots before applying the engine cap.
    return copy.deepcopy(action['market'][:max(1, cap)])


def target_rows(market: list) -> list[dict]:
    rows = []
    for slot, order in enumerate(market):
        if not isinstance(order, list) or len(order) < 2:
            continue
        if order[:2] != ['SELL', 'WHEAT'] and order[:2] != ['SELL', 'FERTILIZER']:
            continue
        if len(order) != 3 or type(order[2]) is not int or order[2] < 0:
            raise ValueError(f'Malformed operating SELL at raw slot {slot}')
        if order[2] > 0:
            rows.append({'market_index': slot, 'product': order[1], 'qty': order[2]})
    return rows


class Recorder:
    """Snapshot at observation time; never retain an action/diagnostic alias."""
    def __init__(self, seed: int, seat: int):
        if type(seed) is not int or type(seat) is not int or seat not in (0, 1):
            raise ValueError('Exact seed/seat required')
        self.seed, self.seat = seed, seat
        self.current = None

    def begin(self, obs: dict, cfg: dict) -> None:
        step = obs.get('step')
        if type(step) is not int or type(obs.get('player')) is not int or obs['player'] != self.seat:
            raise ValueError('Observation step/player mismatch')
        turns = cfg.get('turnsPerDay', 24)
        if type(turns) is not int or turns != 24:
            raise ValueError('This pinned census requires turnsPerDay=24')
        self.current = {'seed': self.seed, 'seat': self.seat, 'step': step,
                        'day': step // turns, 'hour': step % turns,
                        'stages': {}, 'stage_order': [], 'problems': []}

    def capture(self, stage: str, action: dict, cfg: dict, diagnostics: dict) -> None:
        record = self.current
        if record is None or stage not in STAGES:
            raise ValueError('Capture outside a callback or unknown stage')
        if stage in record['stages']:
            record['problems'].append(f'duplicate_stage_{stage}')
            return
        market = prefix(action, cfg)
        # Validate target quantities before recording a misleading zero.
        rows = target_rows(market)
        record['stage_order'].append(stage)
        record['stages'][stage] = {
            'market': market, 'rows': rows,
            'diagnostics': copy.deepcopy({k: diagnostics[k] for k in DIAGNOSTICS if k in diagnostics}),
        }

    def finish(self, action: dict, cfg: dict, diagnostics: dict) -> dict:
        self.capture('D', action, cfg, diagnostics)
        record = self.current
        record['status'] = diagnostics.get('status', 'missing')
        if record['status'] != 'completed':
            record['problems'].append('runtime_not_completed')
        if record['stage_order'] != list(STAGES):
            record['problems'].append('incomplete_or_unordered_stages')
        record['returned_action_sha256'] = hashlib.sha256(encoded(action)).hexdigest()
        record['stage_complete'] = not record['problems']
        self.current = None
        return record


class CensusAgent:
    """Fresh process/instance boundary is supplied by the retained evaluator."""
    def __init__(self, runtime: str, trace: str, seed: int, seat: int):
        self.root = Path(runtime).resolve(strict=True)
        check_pins(self.root, PINS)
        existing = sys.modules.get('titan_runtime')
        if existing is not None and Path(existing.__file__).resolve().parent != self.root:
            raise ValueError('A different runtime is already imported')
        sys.path.insert(0, str(self.root))
        spec = importlib.util.spec_from_file_location('_e3_observed_main', self.root/'main.py')
        self.main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main)
        self.recorder = Recorder(seed, seat)
        self.last_instance = None
        self.trace_path = Path(trace)
        self.stream = self.trace_path.open('xb')  # Existing traces cannot be silently reused.
        factory = self.main._new_instance
        def observed_factory(*args, **kwargs):
            instance = factory(*args, **kwargs)
            self.last_instance = instance
            self.attach(instance)
            return instance
        self.main._new_instance = observed_factory

    def attach(self, instance) -> None:
        operating = instance._operating_stock_selected
        feed = instance._feed_stock_selected
        def observe_operating(obs, cfg, selected):
            self.recorder.capture('A', selected, cfg, instance.diagnostics)
            return operating(obs, cfg, selected)
        def observe_feed(obs, cfg, selected):
            self.recorder.capture('B', selected, cfg, instance.diagnostics)
            result = feed(obs, cfg, selected)
            self.recorder.capture('C', result, cfg, instance.diagnostics)
            return result
        # Each original bound method is called once, on the original instance.
        instance._operating_stock_selected = observe_operating
        instance._feed_stock_selected = observe_feed

    def __call__(self, observation, configuration=None):
        cfg = dict(configuration or {})
        self.recorder.begin(observation, cfg)
        result = self.main.agent(observation, cfg)
        instance = self.main._INSTANCE or self.last_instance
        diagnostics = {} if instance is None else instance.diagnostics
        record = self.recorder.finish(result, cfg, diagnostics)
        self.stream.write(encoded(record) + b'\n')
        self.stream.flush()
        return result  # Not a copy: the exact main.agent return value.


def summarize_records(records: list[dict], cells: list[dict], steps: int = 719) -> dict:
    if type(steps) is not int or steps < 1:
        raise ValueError('Positive exact callback count required')
    validate_panel({'provenance':'explicit argument', 'cells':cells})
    expected = {(c['seed'], c['seat']) for c in cells}
    if not expected or len(expected) != len(cells):
        raise ValueError('A nonempty distinct declared panel is required')
    totals = {s: {p: {'rows': 0, 'units': 0} for p in PRODUCTS} for s in STAGES}
    seen, residual_steps, flattened = set(), set(), []
    problems = []
    for rec in records:
        if (type(rec) is not dict or any(type(rec.get(k)) is not int for k in
                ('seed','seat','step','day','hour'))):
            raise ValueError('Exact integer callback metadata required')
        key = (rec['seed'], rec['seat'], rec['step'])
        if rec['day'] != key[2] // 24 or rec['hour'] != key[2] % 24:
            raise ValueError('Callback calendar mismatch')
        if key[:2] not in expected or type(key[2]) is not int or not 0 <= key[2] < steps:
            raise ValueError(f'Unexpected callback: {key}')
        if key in seen:
            raise ValueError(f'Duplicate callback: {key}')
        seen.add(key)
        stages_complete = (type(rec.get('stages')) is dict
            and set(rec['stages']) == set(STAGES)
            and rec.get('stage_order') == list(STAGES)
            and rec.get('status') == 'completed'
            and rec.get('stage_complete') is True
            and rec.get('problems') == [])
        if not stages_complete:
            problems.append({'cell_step': list(key), 'reasons': rec.get('problems') or ['incomplete']})
        if type(rec.get('stages')) is not dict:
            raise ValueError('Missing stage map')
        for stage, snapshot in rec['stages'].items():
            if stage not in STAGES:
                raise ValueError('Unknown stage in evidence')
            actual_rows = target_rows(snapshot['market'])
            if actual_rows != snapshot['rows']:
                raise ValueError('Stored target rows do not match market snapshot')
            for row in actual_rows:
                metric = totals[stage][row['product']]
                metric['rows'] += 1
                metric['units'] += row['qty']
                flattened.append({k: rec[k] for k in ('seed','seat','step','day','hour')} |
                                 {'stage':stage, **row, 'market':snapshot['market'],
                                  'diagnostics':snapshot['diagnostics']})
                if stage == 'D':
                    residual_steps.add(key)
    missing = [{'seed': seed, 'seat': seat, 'steps': [s for s in range(steps)
                if (seed,seat,s) not in seen]} for seed,seat in sorted(expected)]
    missing = [item for item in missing if item['steps']]
    residual = sum(totals['D'][p]['rows'] for p in PRODUCTS)
    complete = not missing and not problems
    return {
        'schema_version': 1, 'expected_callbacks':len(expected)*steps,
        'observed_callbacks':len(seen), 'missing':missing, 'stage_problems':problems,
        'complete':complete, 'totals':totals,
        'net_reductions': {f'{a}->{b}': {p: {k:totals[a][p][k]-totals[b][p][k]
            for k in ('rows','units')} for p in PRODUCTS} for a,b in zip(STAGES,STAGES[1:])},
        'final_residual_rows':residual, 'final_residual_unique_steps':len(residual_steps),
        'census_decision': ('INCOMPLETE' if not complete else
                            'RESIDUAL_PRESENT_NOT_PORT_AUTHORITY' if residual else
                            'NO_RESIDUAL_ON_EXECUTED_CELLS'),
        'rows':flattened,
    }


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_panel(panel: dict) -> list[dict]:
    if not isinstance(panel, dict) or not isinstance(panel.get('provenance'), str) or not panel['provenance']:
        raise ValueError('Panel provenance must be explicitly declared')
    cells = panel.get('cells')
    if type(cells) is not list or not cells:
        raise ValueError('Nonempty declared cells required')
    keys = set()
    for cell in cells:
        if (type(cell) is not dict or type(cell.get('seed')) is not int or
                type(cell.get('seat')) is not int or cell['seat'] not in (0,1) or
                type(cell.get('opponent')) is not str or not cell['opponent']):
            raise ValueError('Each cell needs exact seed, seat and opponent')
        key = (cell['seed'],cell['seat'])
        if key in keys:
            raise ValueError('Duplicate seed/seat cell')
        keys.add(key)
    return cells


def run_cell(runtime: Path, output: Path, cell: dict, evaluator: Path, engine_dir: Path,
             loader: Path, compare_baseline: bool) -> tuple[dict, list]:
    module = load_module(evaluator, '_e3_retained_evaluator')
    engine, _ = module.get_engine(engine_dir, loader)
    seed,seat = cell['seed'],cell['seat']
    trace = output/f'trace-{seed}-{seat}.jsonl'
    wrapper = output/f'observe-{seed}-{seat}.py'
    source = (f'import sys\nsys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n'
              f'from operating_sell_census import CensusAgent\n'
              f'agent = CensusAgent({str(runtime)!r}, {str(trace)!r}, {seed!r}, {seat!r})\n')
    wrapper.write_text(source)
    rival = module.resolve_spec(cell['opponent'])
    def play(candidate):
        pair = [candidate,rival] if seat==0 else [rival,candidate]
        # External diagnostic RPC allowance only. Canonical internal 1s timers stay unchanged.
        return module.play(engine, pair, engine_dir, loader, seed, seat,
                           action_timeout=2.0, game_timeout=180.0)
    baseline = play(str(runtime/'main.py')) if compare_baseline else None
    observed = play(str(wrapper))
    records = [json.loads(line) for line in trace.read_bytes().splitlines()] if trace.exists() else []
    same = (baseline is not None and baseline['status'] == observed['status'] == 'complete'
            and baseline['scores'] == observed['scores']
            and baseline['trace_sha256'] == observed['trace_sha256'])
    return {'cell':cell, 'baseline':baseline, 'observed':observed,
            'trace_and_score_identity':same, 'trace_file':trace.name,
            'trace_fingerprint':fingerprint(trace) if trace.exists() else None}, records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--panel',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--cell-index',type=int)
    args = parser.parse_args(argv)
    try:
        runtime = args.runtime.resolve(strict=True)
        pins = check_pins(runtime,PINS)
        panel = read_json(args.panel)
        cells = validate_panel(panel)
        if args.cell_index is not None:
            if not 0 <= args.cell_index < len(cells):
                raise ValueError('Cell index outside declared panel')
            cells = [cells[args.cell_index]]
        output = args.output_dir.resolve()
        if output.is_relative_to(runtime):
            raise ValueError('Output must be outside the runtime source tree')
        if output.exists():
            raise ValueError('Output directory must be new; old evidence is never reused')
        evaluator = runtime/'checks/reference/evaluator/evaluate.py'
        loader = evaluator.with_name('loader.py')
        engine_dir = runtime/'checks/reference/engine'
        epins = check_pins(engine_dir,ENGINE_PINS)
        execution_pins = {str(p.relative_to(runtime)):fingerprint(p) for p in (evaluator,loader)}
        all_inputs = {str(p.relative_to(runtime)):fingerprint(p) for p in sorted(runtime.rglob('*'))
                      if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts}
        output.mkdir(parents=True)
        (output/'declared-panel.json').write_bytes(encoded(panel)+b'\n')
        games, records = [], []
        for cell in cells:
            game,rows = run_cell(runtime,output,cell,evaluator,engine_dir,loader,True)
            games.append(game);records.extend(rows)
            print(json.dumps({'cell':cell,'status':game['observed']['status'],
                             'identity':game['trace_and_score_identity'],
                             'callbacks':len(rows)},sort_keys=True),flush=True)
        summary = summarize_records(records,cells)
        identity = all(g['trace_and_score_identity'] for g in games)
        source_unchanged = all(fingerprint(runtime/name)==pin for name,pin in all_inputs.items())
        report = {'panel':panel, 'executed_cells':cells, 'runtime_pins':pins,'engine_pins':epins,
                  'execution_pins':execution_pins, 'input_manifest':all_inputs,
                  'source_unchanged':source_unchanged, 'instrumentation_identity':identity,
                  'python':sys.version, 'summary':summary, 'games':games,
                  'full_declared_panel':len(cells)==len(panel['cells']),
                  'limits':{'candidate_internal_timer_unchanged':True,'external_rpc_seconds':2.0,
                            'hosted_kaggle':False,'economic_promotion':False,
                            'claims_canonical_v4_composition':False}}
        if not identity or not source_unchanged:
            report['summary']['census_decision']='UNRELIABLE_INSTRUMENTATION_OR_INPUT_DRIFT'
        (output/'REPORT.json').write_bytes(encoded(report)+b'\n')
        return 0 if summary['complete'] and identity and source_unchanged else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'CENSUS ERROR: {exc}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
