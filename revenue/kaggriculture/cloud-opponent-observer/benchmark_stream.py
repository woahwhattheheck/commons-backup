"""Compare existing and streaming observation consumers in fresh processes.

This only replays supplied observations; it does not run an interpreter or game.
Tracemalloc timings include instrumentation and are not policy latency claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tracemalloc


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def worker(args):
    if args.worker == 'baseline':
        from observe import run_jsonl
    else:
        from stream_observations import run_jsonl
    root = args.output_dir
    output, summary = root/f'{args.worker}.jsonl', root/f'{args.worker}-summary.json'
    tracemalloc.start()
    started = time.perf_counter()
    result = run_jsonl(args.source, args.pack, args.input, output, summary)
    seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {'runner': args.worker, 'python_peak_bytes': peak,
            'instrumented_seconds': seconds,
            'telemetry_sha256': file_hash(output), 'summary_sha256': file_hash(summary),
            'calls': sum(a['calls'] for a in result['actors']),
            'actors': len(result['actors']),
            'telemetry_errors': sum(a['telemetry_errors'] for a in result['actors'])}


def _write_checkpoint(path: Path, report: dict) -> None:
    """Replace one complete JSON snapshot without truncating the previous one."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                dir=path.parent, prefix=f'.{path.name}.', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _measurement(text: str, mode: str) -> dict:
    """A completed child must return this worker's actual measurement shape."""
    result = json.loads(text)
    if not isinstance(result, dict) or result.get('runner') != mode:
        raise ValueError('Unexpected benchmark worker result')
    for key in ('calls', 'actors', 'telemetry_errors', 'python_peak_bytes'):
        value = result.get(key)
        if type(value) is not int or value < (1 if key == 'python_peak_bytes' else 0):
            raise ValueError(f'Invalid benchmark measurement: {key}')
    seconds = result.get('instrumented_seconds')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Invalid benchmark measurement: instrumented_seconds')
    for key in ('telemetry_sha256', 'summary_sha256'):
        value = result.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'Invalid benchmark measurement: {key}')
    return result


def _retain_failure(path: Path, report: dict, exc: Exception) -> None:
    # Preserve the original failure if even the checkpoint writer is unavailable.
    try:
        _write_checkpoint(path, report)
    except Exception as save_error:
        exc.add_note(f'Benchmark failure checkpoint not saved: {type(save_error).__name__}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='New directory for this measurement; existing directories are untouched')
    parser.add_argument('--worker', choices=['baseline', 'stream'])
    args = parser.parse_args(argv)
    if args.worker:
        print(json.dumps(worker(args), sort_keys=True))
        return 0
    # A new directory ensures benchmark artifacts cannot collide with inputs.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    original_digest = file_hash(args.input)
    results = []
    report = {'schema': 'cok-stream-benchmark-v1', 'python': sys.version.split()[0],
        'input_sha256': original_digest, 'input_unchanged': None,
        'results': results, 'telemetry_bytes_equal': None, 'summary_bytes_equal': None,
        'peak_python_memory_reduction_fraction': None,
        'scope': 'Supplied observation processing in fresh Python processes, with tracemalloc enabled; not scored games or policy action latency.',
        'complete': False, 'active_worker': None, 'attempts': [], 'failure': None}
    checkpoint = args.output_dir / 'benchmark.json'
    _write_checkpoint(checkpoint, report)
    for mode in ('baseline', 'stream'):
        attempt = {'runner': mode, 'status': 'running', 'returncode': None}
        report['attempts'].append(attempt)
        report['active_worker'] = mode
        _write_checkpoint(checkpoint, report)
        process = None
        stage = 'worker'
        try:
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                '--source', str(args.source.resolve()), '--pack', str(args.pack.resolve()),
                '--input', str(args.input.resolve()), '--output-dir', str(args.output_dir.resolve()),
                '--worker', mode], text=True, capture_output=True, check=True)
            attempt['returncode'] = process.returncode
            stage = 'measurement'
            results.append(_measurement(process.stdout, mode))
        except Exception as exc:
            attempt['status'] = 'failed'
            if isinstance(exc, subprocess.CalledProcessError):
                attempt['returncode'] = exc.returncode
                attempt['stdout'], attempt['stderr'] = exc.stdout, exc.stderr
            elif process is not None:
                attempt['stdout'], attempt['stderr'] = process.stdout, process.stderr
            report['active_worker'] = None
            report['failure'] = {'stage': stage, 'runner': mode,
                                 'type': type(exc).__name__, 'message': str(exc)}
            try:
                report['input_unchanged'] = file_hash(args.input) == original_digest
            except OSError:
                report['input_unchanged'] = None
            _retain_failure(checkpoint, report, exc)
            raise
        attempt['status'] = 'completed'
        report['active_worker'] = None
        # Persist this returned measurement before any next worker starts.
        _write_checkpoint(checkpoint, report)
    try:
        old, new = results
        report.update(input_unchanged=file_hash(args.input) == original_digest,
            telemetry_bytes_equal=old['telemetry_sha256'] == new['telemetry_sha256'],
            summary_bytes_equal=old['summary_sha256'] == new['summary_sha256'],
            peak_python_memory_reduction_fraction=1 - new['python_peak_bytes']/old['python_peak_bytes'])
    except Exception as exc:
        report['failure'] = {'stage': 'comparison', 'runner': None,
                             'type': type(exc).__name__, 'message': str(exc)}
        _retain_failure(checkpoint, report, exc)
        raise
    report['complete'] = True
    _write_checkpoint(checkpoint, report)
    print(json.dumps(report, sort_keys=True))
    return int(not all(report[k] for k in ('input_unchanged','telemetry_bytes_equal','summary_bytes_equal')))


if __name__ == '__main__':
    raise SystemExit(main())
