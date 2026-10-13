"""Paired official-engine games with per-game isolated actors and frozen sources."""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import importlib.metadata
import platform
import json
import os
import tempfile
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
RUN_LIMITS = {"action_timeout": 1.0, "startup_timeout": 10, "game_timeout": 90}


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execution_identity(manifest, engine_hashes, evaluator, loader):
    """Bind the prepared closure, not just the four policy-source filenames.

    The preparer has no per-actor dependency graph. Keep its entire manifest so
    an untracked guess about imports cannot turn a changed runtime into a hit.
    This is deliberately stricter than selectively reusing an Arlene control.
    """
    try:
        engine_package = importlib.metadata.version('kaggle-environments')
    except importlib.metadata.PackageNotFoundError:
        engine_package = None
    return {
        'schema': 'titan.t03.execution-inputs.v1',
        'manifest': manifest,
        'adapter_sha256': {name: sha256_file(path)
                           for name, path in manifest['adapters'].items()},
        'engine_sha256': engine_hashes,
        'harness_sha256': {
            'panel': sha256_file(__file__),
            'evaluator': sha256_file(evaluator),
            'loader': sha256_file(loader),
            'offline': sha256_file(ROOT / 'cloud-frontier-policy/next-panel/offline.py'),
        },
        # play() receives only these limits; configuration defaults are bound by
        # the evaluator, loader, engine schema and installed engine package.
        'limits': dict(RUN_LIMITS),
        'python': sys.version,
        'platform': [sys.platform, platform.machine()],
        'kaggle_environments_version': engine_package,
    }


def cell_identity(inputs, seed, opponent, seat, arm):
    return {'inputs': inputs, 'cell': {'seed': seed, 'opponent': opponent,
                                     'candidate_seat': seat, 'arm': arm}}


def read_cached(path, expected):
    """Read an exact prior attempt without rewriting or upgrading its metadata."""
    row = json.loads(path.read_text())
    if not isinstance(row, dict) or row.get('run_identity') != expected:
        raise ValueError(f'Existing game lacks matching execution inputs: {path}; '
                         'preserve it and use another output directory')
    # A filename or copied identity must not override the actual result's labels.
    for key, value in expected['cell'].items():
        if row.get(key) != value:
            raise ValueError(f'Existing game cell mismatch ({key}): {path}')
    inputs = expected['inputs']
    if (row.get('source_sha256') != inputs['manifest']['source_sha256'] or
            row.get('engine_sha256') != inputs['engine_sha256']):
        raise ValueError(f'Existing game source/engine metadata mismatch: {path}')
    if not isinstance(row.get('status'), str):
        raise ValueError(f'Existing game has no attempt status: {path}')
    return row


def publish_json(path, value, *, replace=False):
    """Expose complete JSON only; retain a staging file if publication fails.

    Cell creation uses an atomic hard link so an overlapping writer cannot be
    overwritten. Summaries replace atomically. This is per-file visibility,
    not a multi-file transaction or a power-loss durability guarantee.
    """
    path = Path(path)
    payload = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.pending',
                                dir=path.parent)
    staged = Path(name)
    try:
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError('Report staging write made no progress')
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if replace:
            os.replace(staged, path)
        else:
            os.link(staged, path)
            staged.unlink()
    except BaseException as error:
        # Preserve partial or complete unpublished bytes for inspection. A
        # process kill also leaves .pending files; read_cached never consumes them.
        if hasattr(error, 'add_note'):
            error.add_note(f'Report staging path (not a published result): {staged}')
        raise


def run(runtime,engine_dir,output,seeds,opponents,seats,arms):
    runtime=Path(runtime);engine_dir=Path(engine_dir)
    seeds,opponents,seats,arms=(tuple(dict.fromkeys(values))
                               for values in (seeds,opponents,seats,arms))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((runtime/'runtime-manifest.json').read_text())
    for name,digest in manifest['runtime_sha256'].items():
        if sha256_file(runtime/name) != digest:
            raise ValueError(f'Runtime changed: {name}')
    evaluator_path=ROOT/'cloud-eval/evaluate.py'
    ev=load(evaluator_path,'t03_panel_evaluator')
    engine,engine_hashes=ev.get_engine(engine_dir)
    inputs=execution_identity(manifest,engine_hashes,evaluator_path,ev.LOADER)
    # Preflight the entire requested grid before spending any new game compute.
    cells=[]
    for seed in seeds:
        for opponent in opponents:
            for seat in seats:
                for arm in arms:
                    name=f'{seed}-{opponent}-seat{seat}-{arm}'
                    destination=output/(name+'.json')
                    identity=cell_identity(inputs,seed,opponent,seat,arm)
                    cached=read_cached(destination,identity) if destination.exists() else None
                    cells.append((destination,identity,cached))
    # Benchmark-only per-game event collection; actor working directories remain
    # private and are deleted by the unchanged existing close implementation.
    original_close=ev.Actor.close
    def close(actor):
        data = None
        try:
            path = Path(actor.directory.name) / 't03-events.json'
            data = path.read_bytes()
            actor.stats['t03_events'] = json.loads(data.decode('utf-8'))
        except FileNotFoundError:
            pass  # Telemetry is optional, including a file removed before read.
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            actor.stats['t03_events_error'] = {
                'kind': 'read_error' if data is None else 'decode_error',
                'type': type(error).__name__, 'error': str(error),
                'bytes': len(data) if data is not None else None,
                'sha256': hashlib.sha256(data).hexdigest() if data is not None else None,
                'raw_base64': base64.b64encode(data).decode('ascii') if data is not None else None,
            }
        finally:
            # Never let optional telemetry prevent the original worker cleanup.
            # A cancellation still propagates after this finally block.
            result = original_close(actor)
        return result
    ev.Actor.close=close
    games=[]
    resumed={'reused_complete': 0, 'retained_incomplete': 0, 'executed': 0}
    try:
        for destination,identity,cached in cells:
            if cached is not None:
                games.append(cached)
                resumed['reused_complete' if cached['status']=='complete' else
                        'retained_incomplete'] += 1
                continue
            cell=identity['cell']
            seed,opponent,seat,arm=(cell[k] for k in ('seed','opponent','candidate_seat','arm'))
            candidate=manifest['adapters'][arm]
            rival=manifest['adapters'][opponent]
            pair=[candidate,rival] if seat==0 else [rival,candidate]
            row=ev.play(engine,pair,engine_dir,ev.LOADER,seed,seat,**RUN_LIMITS)
            row.update(arm=arm,opponent=opponent,source_sha256=manifest['source_sha256'],
                       engine_sha256=engine_hashes,run_identity=identity)
            # An overlapping caller must not overwrite a newly finished attempt.
            publish_json(destination, row)
            games.append(row)
            resumed['executed'] += 1
            print(json.dumps({k:row[k] for k in ('seed','opponent','candidate_seat','arm','status','steps','scores','failure')}),flush=True)
    finally:
        ev.Actor.close=original_close
    pairs=[]
    for seed in seeds:
        for opponent in opponents:
            for seat in seats:
                selected={r['arm']:r for r in games if r['seed']==seed and r['opponent']==opponent and r['candidate_seat']==seat}
                if 'arlene' not in selected or 'candidate' not in selected:continue
                a,b=selected['arlene'],selected['candidate']
                if a['status']!='complete' or b['status']!='complete':continue
                am=a['scores'][seat]-a['scores'][1-seat];bm=b['scores'][seat]-b['scores'][1-seat]
                outcome=lambda m:'W' if m>0 else 'L' if m<0 else 'T'
                pairs.append({'seed':seed,'opponent':opponent,'seat':seat,'control':outcome(am),'candidate':outcome(bm),
                              'own_cash_delta':b['scores'][seat]-a['scores'][seat],
                              'rival_cash_delta':b['scores'][1-seat]-a['scores'][1-seat],'margin_delta':bm-am})
    report={'games':games,'pairs':pairs,'resume':resumed,'seed_scope':'development unless accompanied by a prior immutable freeze receipt',
            'claim':'Offline simulations, not hosted leaderboard or cash earnings'}
    publish_json(output/'panel.json', report, replace=True)
    print(json.dumps({'pairs':pairs,'resume':resumed},indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--engine-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',required=True);p.add_argument('--opponents',default='arlene,apex');p.add_argument('--seats',default='0,1');p.add_argument('--arms',default='arlene,candidate')
    a=p.parse_args();run(a.runtime,a.engine_dir,a.output,[int(x) for x in a.seeds.split(',')],a.opponents.split(','),[int(x) for x in a.seats.split(',')],a.arms.split(','))
