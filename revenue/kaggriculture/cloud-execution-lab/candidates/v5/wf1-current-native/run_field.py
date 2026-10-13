#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import sys

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parents[2]
COMPONENT_REL = Path('candidates/v5/wf1-current-native')
RUNNER_REL = Path('candidates/v4/repairs/gameplay/s8-egg-care/run_s8_field.py')
WF1_REL = Path('candidates/v4/repairs/gameplay/wf1-wheat-fertilize')
SOURCE_FILES = (
    COMPONENT_REL / 'run_field.py',
    COMPONENT_REL / 'materialize.py',
    COMPONENT_REL / 'entry.py',
    RUNNER_REL,
    WF1_REL / 'r04_wheat_fert.py',
    WF1_REL / 'wf1_current_adapter.py',
    WF1_REL / 'WF1-CURRENT-NATIVE-FIELD-RECEIPT.json',
)
DEFAULT_SEEDS = (2026091201, 2026091207, 2026091213, 2026091219)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_digest(root: Path) -> str:
    """Match the native runner's deterministic package digest exactly."""
    root = Path(root).resolve()
    members = {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob('*'))
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
    }
    return hashlib.sha256(_encoded(members)).hexdigest()


def snapshot_runtime(runtime: Path, snapshot: Path) -> str:
    """Copy one immutable control closure and prove the input did not move."""
    runtime = Path(runtime).resolve()
    snapshot = Path(snapshot).resolve()
    if runtime == snapshot or runtime in snapshot.parents:
        raise ValueError('control snapshot must be outside runtime')
    if snapshot.exists():
        raise FileExistsError(snapshot)
    before = package_digest(runtime)
    try:
        shutil.copytree(runtime, snapshot, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    except Exception:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise
    copied = package_digest(snapshot)
    after = package_digest(runtime)
    if before != after:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise RuntimeError('runtime package changed while snapshotting')
    if before != copied:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise RuntimeError('control snapshot differs from authenticated runtime package')
    return before


def snapshot_harness_source(snapshot_root: Path) -> dict[str, str]:
    """Freeze every repo-source byte used by the WF1 field harness."""
    snapshot_root = Path(snapshot_root).resolve()
    if snapshot_root.exists():
        raise FileExistsError(snapshot_root)
    before = {}
    for rel in SOURCE_FILES:
        source = SOURCE_ROOT / rel
        if not source.is_file():
            raise FileNotFoundError(source)
        before[rel.as_posix()] = _sha256(source)
    try:
        for rel in SOURCE_FILES:
            source = SOURCE_ROOT / rel
            target = snapshot_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except Exception:
        shutil.rmtree(snapshot_root, ignore_errors=True)
        raise
    after = {rel.as_posix(): _sha256(SOURCE_ROOT / rel) for rel in SOURCE_FILES}
    copied = {rel.as_posix(): _sha256(snapshot_root / rel) for rel in SOURCE_FILES}
    if before != after:
        shutil.rmtree(snapshot_root, ignore_errors=True)
        raise RuntimeError('WF1 harness source changed while snapshotting')
    if before != copied:
        shutil.rmtree(snapshot_root, ignore_errors=True)
        raise RuntimeError('frozen WF1 harness source differs from authenticated source')
    return copied


def validate_source_snapshot(snapshot_root: Path, expected: dict[str, str]) -> None:
    actual = {}
    for key in expected:
        path = Path(snapshot_root).resolve() / Path(key)
        if not path.is_file():
            raise RuntimeError(f'frozen WF1 harness source missing: {key}')
        actual[key] = _sha256(path)
    if actual != expected:
        raise RuntimeError('frozen WF1 harness source changed during field execution')


def parse_seed_set(raw: str) -> tuple[int, ...]:
    values = tuple(int(value) for value in raw.split(',') if value.strip())
    if not values:
        raise ValueError('at least one seed is required')
    if len(set(values)) != len(values):
        raise ValueError('duplicate field seeds are not allowed')
    return tuple(sorted(values))


def validate_cell_custody(baseline: dict, candidate: dict, *, seed: int, seat: int,
                          control_digest: str, candidate_digest: str) -> None:
    """Bind both arms and both opponents to the exact paired package closures."""
    for label, row in (('base', baseline), ('wf1', candidate)):
        if row.get('seed') != seed or row.get('seat') != seat:
            raise ValueError(f'{label} result identity mismatch')
    if baseline.get('package_sha256') != control_digest:
        raise ValueError('base package digest mismatch')
    if candidate.get('package_sha256') != candidate_digest:
        raise ValueError('WF1 package digest mismatch')
    base_opp = baseline.get('opponent')
    wf1_opp = candidate.get('opponent')
    if not isinstance(base_opp, dict) or base_opp.get('package_sha256') != control_digest:
        raise ValueError('base opponent closure mismatch')
    if not isinstance(wf1_opp, dict) or wf1_opp.get('package_sha256') != control_digest:
        raise ValueError('WF1 opponent closure mismatch')


def paired_first_change(base_rows: Path, candidate_rows: Path):
    base = read_json(base_rows)
    candidate = read_json(candidate_rows)
    for left, right in zip(base, candidate):
        if left['step'] != right['step']:
            return min(left['step'], right['step'])
        if left['own_action_sha256'] != right['own_action_sha256']:
            return left['step']
    if len(base) != len(candidate):
        return min(len(base), len(candidate))
    return None


def outcome(margin):
    if margin > 0:
        return 'W'
    if margin < 0:
        return 'L'
    return 'T'


def summarize_cells(cells: list[dict]) -> tuple[dict, dict]:
    """Publish economics only for a complete paired panel."""
    complete = [cell for cell in cells if cell.get('complete')]
    panel_complete = bool(cells) and len(complete) == len(cells)
    economic_cells = complete if panel_complete else []
    margins = [cell['delta']['margin'] for cell in economic_cells]
    own = [cell['delta']['own'] for cell in economic_cells]
    rival = [cell['delta']['rival'] for cell in economic_cells]
    transitions = {}
    for cell in economic_cells:
        key = cell['outcome_transition']
        transitions[key] = transitions.get(key, 0) + 1
    validation = {
        'closure_bound': True,
        'complete_panel': panel_complete,
        'economic_summary_valid': panel_complete,
    }
    summary = {
        'requested_cells': len(cells),
        'complete_cells': len(complete),
        'game_failures': len(cells) - len(complete),
        'changed_action_cells': (sum(cell['first_action_change_step'] is not None
                                     for cell in economic_cells)
                                 if panel_complete else None),
        'positive_margin_cells': (sum(value > 0 for value in margins)
                                  if panel_complete else None),
        'zero_margin_cells': (sum(value == 0 for value in margins)
                              if panel_complete else None),
        'negative_margin_cells': (sum(value < 0 for value in margins)
                                  if panel_complete else None),
        'mean_margin_delta': statistics.mean(margins) if margins else None,
        'median_margin_delta': statistics.median(margins) if margins else None,
        'min_margin_delta': min(margins) if margins else None,
        'max_margin_delta': max(margins) if margins else None,
        'mean_own_delta': statistics.mean(own) if own else None,
        'mean_rival_delta': statistics.mean(rival) if rival else None,
        'outcome_transitions': transitions if panel_complete else None,
    }
    return validation, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-main-git-blob', required=True)
    parser.add_argument('--expected-config-git-blob', required=True)
    parser.add_argument('--seeds', default=','.join(map(str, DEFAULT_SEEDS)))
    args = parser.parse_args()

    runtime = args.runtime.resolve()
    output = args.output.resolve()
    if runtime == output or runtime in output.parents:
        raise ValueError('field output must be outside runtime')
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)

    control_runtime = output / 'materialized-base'
    control_digest = snapshot_runtime(runtime, control_runtime)
    source_snapshot = output / 'frozen-source'
    source_hashes = snapshot_harness_source(source_snapshot)

    candidate_runtime = output / 'materialized-wf1'
    frozen_materializer = source_snapshot / COMPONENT_REL / 'materialize.py'
    materializer = load(frozen_materializer, 'wf1_v5_materializer')
    materialization = materializer.materialize(
        control_runtime, candidate_runtime,
        expected_main_blob=args.expected_main_git_blob,
        expected_config_blob=args.expected_config_git_blob,
    )
    if package_digest(control_runtime) != control_digest:
        raise RuntimeError('control package drifted after materialization')
    validate_source_snapshot(source_snapshot, source_hashes)
    candidate_digest = package_digest(candidate_runtime)

    frozen_runner = source_snapshot / RUNNER_REL
    runner = load(frozen_runner, 'wf1_v5_native_runner')
    entry = candidate_runtime / 'wf1_v5_entry.py'
    seeds = parse_seed_set(args.seeds)
    cells = []

    for seed in seeds:
        for seat in (0, 1):
            key = f'seed-{seed}-seat-{seat}'
            base_dir = output / key / 'base'
            candidate_dir = output / key / 'wf1'
            baseline = runner.play(
                control_runtime, seed, seat, base_dir,
                opponent=control_runtime, passive=False,
                expected_package_sha256=control_digest,
            )
            candidate = runner.play(
                candidate_runtime, seed, seat, candidate_dir,
                opponent=control_runtime, passive=False,
                entry=str(entry) + '::agent',
                expected_package_sha256=candidate_digest,
            )
            validate_cell_custody(
                baseline, candidate, seed=seed, seat=seat,
                control_digest=control_digest, candidate_digest=candidate_digest,
            )
            if package_digest(control_runtime) != control_digest:
                raise RuntimeError('control package changed during field execution')
            if package_digest(candidate_runtime) != candidate_digest:
                raise RuntimeError('WF1 package changed during field execution')
            validate_source_snapshot(source_snapshot, source_hashes)

            complete = (baseline.get('status') == 'complete'
                        and candidate.get('status') == 'complete')
            delta = None
            transition = None
            if complete:
                delta = {
                    'own': candidate['scores'][seat] - baseline['scores'][seat],
                    'rival': candidate['scores'][1-seat] - baseline['scores'][1-seat],
                    'margin': candidate['margin'] - baseline['margin'],
                }
                transition = f"{outcome(baseline['margin'])}->{outcome(candidate['margin'])}"
            cells.append({
                'seed': seed,
                'seat': seat,
                'complete': complete,
                'base': {name: baseline.get(name) for name in
                         ('status', 'steps', 'scores', 'margin', 'failure',
                          'trace_sha256', 'action_sha256', 'world_sha256',
                          'package_sha256', 'opponent')},
                'wf1': {name: candidate.get(name) for name in
                        ('status', 'steps', 'scores', 'margin', 'failure',
                         'trace_sha256', 'action_sha256', 'world_sha256',
                         'package_sha256', 'opponent')},
                'first_action_change_step': paired_first_change(
                    base_dir / 'rows.json', candidate_dir / 'rows.json'),
                'outcome_transition': transition,
                'delta': delta,
            })

    validation, summary = summarize_cells(cells)
    result = {
        'schema': 'titan.v5.wf1-current-native-field/v2',
        'materialization': materialization,
        'control_package_sha256': control_digest,
        'candidate_package_sha256': candidate_digest,
        'source_snapshot_sha256': source_hashes,
        'seeds': list(seeds),
        'cells': cells,
        'validation': validation,
        'summary': summary,
    }
    (output / 'WF1-V5-FIELD-RESULT.json').write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n',
        encoding='utf-8')
    print(json.dumps(result['summary'], sort_keys=True, allow_nan=False))
    return int(not validation['complete_panel'])


if __name__ == '__main__':
    raise SystemExit(main())
