"""Additive full-trajectory league consumer of the pinned official evaluator."""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

from selected_action_audit import duplicate_harvest_targets

def load_evaluator(path):
    spec = importlib.util.spec_from_file_location("ultra_existing_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def detailed_actor(base):
    class DetailedActor(base):
        def report(self):
            result = super().report()
            result["call_seconds"] = list(self.stats["call_seconds"])
            result["rpc_seconds"] = list(self.stats["rpc_seconds"])
            return result
    return DetailedActor

def lark_actor(base, paths, engine):
    """Consume the two configured, unchanged LARK wrappers around one Actor.

    The pressure module's sibling import must resolve the configured quote
    module, without inheriting another experiment's module or import path.
    """
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, Path(path).resolve())
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    sell = load('_ultra_lark_sell_priority', paths['sell_priority'])
    missing = object()
    previous = sys.modules.get('sell_priority', missing)
    try:
        sys.modules['sell_priority'] = sell
        pressure = load('_ultra_lark_pressure_priority', paths['pressure_priority'])
    finally:
        if previous is missing:
            sys.modules.pop('sell_priority', None)
        else:
            sys.modules['sell_priority'] = previous
    return pressure.actor_class(sell.actor_class(base), engine.market_price)

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)

class RecordingEngine:
    """Record official transition outputs; do not change agent observations."""
    def __init__(self, engine, stream):
        self.engine, self.stream = engine, stream
        self.specification = engine.specification
        self.index = 0

    def interpreter(self, state, env):
        conflicts = [duplicate_harvest_targets(s.observation, s.action) for s in state]
        result = self.engine.interpreter(state, env)
        record = {'transition': self.index, 'state': state, 'selected_action_conflicts': conflicts}
        self.stream.write(json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n')
        self.index += 1
        return result

def load_job(path):
    """Read one configuration snapshot and reject ambiguous cell identities."""
    payload = Path(path).read_bytes()
    cfg = json.loads(payload)
    cells = cfg['cells']
    if not isinstance(cells, list):
        raise ValueError("cells must be a list")
    seen = set()
    for item in cells:
        cell_id = item.get('id') if isinstance(item, dict) else None
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError("Each cell must have a nonempty string id")
        if cell_id in seen:
            raise ValueError("Duplicate cell id: " + cell_id)
        seen.add(cell_id)
    if 'lark_wrappers' in cfg:
        paths = cfg['lark_wrappers']
        if (not isinstance(paths, dict)
                or set(paths) != {'sell_priority', 'pressure_priority'}
                or any(not isinstance(value, str) or not Path(value).is_absolute()
                       for value in paths.values())):
            raise ValueError('lark_wrappers requires the two absolute module paths')
        for spec in [cfg['candidate'], *cfg['opponents'].values()]:
            if not isinstance(spec, str):
                raise ValueError('LARK actor specifications must be strings')
            # An explicit callable separates markers from pipes in filenames.
            tail = spec.rpartition('::')[2] if '::' in spec else spec
            if '|' in tail:
                parts = tail.split('|')
                if (len(parts) != 2 or not parts[0]
                        or parts[1] not in {'sell-priority', 'supply-pressure'}):
                    raise ValueError('LARK requires one supported terminal marker')
    return cfg, hashlib.sha256(payload).hexdigest()


def read_cell_result(path, item, returncode, freeze_sha256):
    """Bind a saved result to its scheduled cell, configuration and process exit.

    Keep original result files intact, including genuine evaluator failures.
    A stale or unreadable result must not supply scores for another execution.
    """
    def failed(kind, **details):
        return {'status': 'driver_failed', 'failure': {
            'kind': kind, 'returncode': returncode, **details}}

    try:
        result = json.loads(path.read_text())
    except (OSError, ValueError, UnicodeError) as exc:
        return failed('result_read_error', error=f"{type(exc).__name__}: {exc}"[:1000])
    if not isinstance(result, dict) or result.get('status') not in ('complete', 'failed'):
        return failed('result_schema_error')
    expected = {'cell_id': item['id'], 'seed': item['seed'],
                'candidate_seat': item['seat'], 'opponent': item['opponent'],
                'freeze_sha256': freeze_sha256}
    mismatches = [key for key, value in expected.items()
                  if type(result.get(key)) is not type(value) or result.get(key) != value]
    if mismatches:
        return failed('result_identity_mismatch', fields=mismatches)
    if result['status'] == 'complete' and returncode != 0:
        return failed('child_exit_after_result')
    return result

def publish_trajectory(partial, final, expected_transitions):
    """Publish closed, synced gzip bytes after checking every recorded frame.

    The final name is absent during recording. This checks capture integrity,
    not game completion, and cannot prevent a later external file mutation.
    Failed publication leaves the partial (or already-promoted file) intact.
    """
    if type(expected_transitions) is not int or expected_transitions < 0:
        raise ValueError('Invalid recorded transition count')
    with partial.open('r+b') as raw:
        os.fsync(raw.fileno())
        count = 0
        with gzip.GzipFile(fileobj=raw, mode='rb') as stream:
            for line in stream:
                record = json.loads(line)
                if (not isinstance(record, dict)
                        or type(record.get('transition')) is not int
                        or record['transition'] != count):
                    raise ValueError('Noncontiguous trajectory transition at %s' % count)
                count += 1
        if count != expected_transitions:
            raise ValueError('Trajectory count %s != recorded count %s'
                             % (count, expected_transitions))
        raw.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: raw.read(1024 * 1024), b''):
            digest.update(block)
    partial.replace(final)
    directory = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return digest.hexdigest()

def cell(args):
    cfg, freeze_sha256 = load_job(args.config)
    ev = load_evaluator(cfg.get("evaluator", str(HERE.parent / "cloud-eval/evaluate.py")))
    ev.Actor = detailed_actor(ev.Actor)
    item = next(x for x in cfg['cells'] if x['id'] == args.cell)
    out = Path(cfg['output']) / item['id']
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'STARTED.json', {'started': now(), 'pid': os.getpid(), 'cell': item,
                                     'command': sys.argv, 'freeze_sha256': freeze_sha256})
    engine, engine_hashes = ev.get_engine(cfg['engine'], cfg['loader'])
    if 'lark_wrappers' in cfg:
        ev.Actor = lark_actor(ev.Actor, cfg['lark_wrappers'], engine)
    candidate, opponent = cfg['candidate'], cfg['opponents'][item['opponent']]
    specs = [candidate, opponent] if item['seat'] == 0 else [opponent, candidate]
    final = out / 'trajectory.jsonl.gz'
    partial = out / 'trajectory.jsonl.gz.partial'
    recorder, result, stage = None, None, 'recording'
    try:
        with partial.open('xb') as raw:
            # Preserve the original gzip header name despite staging elsewhere.
            with gzip.GzipFile(filename=final.name, mode='wb', fileobj=raw, compresslevel=1) as compressed:
                with io.TextIOWrapper(compressed, encoding='utf-8') as stream:
                    recorder = RecordingEngine(engine, stream)
                    result = ev.play(recorder, specs, cfg['engine'], cfg['loader'], item['seed'], item['seat'],
                                     cfg['rng_seed'], cfg['action_timeout'], cfg['startup_timeout'], cfg['game_timeout'], None)
        stage = 'publishing'
        trajectory_sha256 = publish_trajectory(partial, final, recorder.index)
        result.update(opponent=item['opponent'], cell_id=item['id'], finished=now(),
                      freeze_sha256=freeze_sha256,
                      engine_sha256=engine_hashes, recorded_transitions=recorder.index)
        result['trajectory_sha256'] = trajectory_sha256
        stage = 'result'
        write_json(out / 'result.json', result)
    except BaseException as exc:
        try:
            write_json(out / 'CAPTURE-ERROR.json', {
                'error_type': type(exc).__name__, 'error': str(exc), 'stage': stage,
                'partial': partial.name, 'trajectory': final.name,
                'partial_exists': partial.exists(), 'trajectory_exists': final.exists(),
                'recorded_transitions': recorder.index if recorder is not None else None,
                'evaluator_result': result,
            })
        except Exception as diagnostic_error:
            print('Capture diagnostic write failed: %s' % diagnostic_error, file=sys.stderr)
        raise
    print(json.dumps({k: result[k] for k in ['cell_id', 'seed', 'candidate_seat', 'opponent', 'status', 'scores', 'failure', 'wall_seconds']}), flush=True)
    return int(result['status'] != 'complete')

def launch(args):
    cfg_path = Path(args.config).resolve()
    cfg, freeze_sha256 = load_job(cfg_path)
    out = Path(cfg['output'])
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    state = {'started': now(), 'pid': os.getpid(), 'command': sys.argv, 'config': str(cfg_path),
             'freeze_sha256': freeze_sha256, 'scheduled': len(cfg['cells']), 'finished_cells': rows}
    write_json(out / 'BATCH-STATE.json', state)
    def run(item):
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--config', str(cfg_path), '--cell', item['id']]
        log = out / (item['id'] + '.log')
        started = now()
        proc, code = None, None
        try:
            with log.open('w') as f:
                proc = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT)
                code = proc.wait()
            path = out / item['id'] / 'result.json'
            result = read_cell_result(path, item, code, freeze_sha256)
            summary = {'status': result['status'], 'scores': result.get('scores'),
                       'failure': result.get('failure'), 'wall_seconds': result.get('wall_seconds')}
        except Exception as exc:
            # Retain a failed slot without dropping other completed cells or retrying.
            summary = {'status': 'driver_failed', 'scores': None, 'wall_seconds': None,
                       'failure': {'kind': 'driver_exception', 'error_type': type(exc).__name__,
                                   'error': str(exc)[:1000]}}
        return {'id': item['id'], 'seed': item['seed'], 'seat': item['seat'], 'opponent': item['opponent'],
                'started': started, 'finished': now(), 'pid': proc.pid if proc is not None else None,
                'returncode': code, **summary}
    # Complete the operational eight before launching the rest; no game is repeated.
    for phase, cells in [('operational8', cfg['cells'][:8]), ('remaining', cfg['cells'][8:])]:
        state['phase'] = phase
        write_json(out / 'BATCH-STATE.json', state)
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['jobs']) as pool:
            pending = [pool.submit(run, item) for item in cells]
            for future in concurrent.futures.as_completed(pending):
                row = future.result()
                rows.append(row)
                write_json(out / 'BATCH-STATE.json', state)
                print(json.dumps(row), flush=True)
        if phase == 'operational8':
            if any(x['status'] != 'complete' for x in rows):
                state['stopped'] = 'operational_failure'; write_json(out / 'BATCH-STATE.json', state); return 1
            print('OPERATIONAL8_COMPLETE', flush=True)
    state.update(phase='complete', finished=now())
    write_json(out / 'BATCH-STATE.json', state)
    return int(any(x['status'] != 'complete' for x in rows))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--cell')
    args = p.parse_args()
    raise SystemExit(cell(args) if args.cell else launch(args))
