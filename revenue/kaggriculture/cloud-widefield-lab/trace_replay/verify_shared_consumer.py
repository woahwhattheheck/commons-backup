#!/usr/bin/env python3
"""Bind independent cases to the existing shared consumer; no replay algorithm."""
from __future__ import annotations
import argparse
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
import boundary_contract


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('consumer', 'engine-dir', 'evaluator', 'tracer', 'loader', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('consumer', 'engine_dir', 'evaluator', 'tracer', 'loader', 'report'):
        setattr(args, name, getattr(args, name).resolve())
    consumer = load(args.consumer, 'trace9042_shared_consumer')
    evaluator = load(args.evaluator, 'trace9042_contract_evaluator')
    tracer = load(args.tracer, 'trace9042_original_tracer')
    engine, hashes = evaluator.get_engine(args.engine_dir, args.loader)
    successful_views: dict[int, dict[str, Any]] = {}

    def recover(document: dict[str, Any], seat: int | None = None) -> dict[str, Any]:
        # Validation, seat selection and reconstruction all belong to the
        # published consumer. This adapter only checks and normalizes output.
        inputs, receipt = consumer.recover_record(document, evaluator, tracer,
            engine, args.engine_dir, args.loader, hashes, seat=seat)
        original = document['games'][0]['candidate_seat']
        selected = original if seat is None else seat
        expected_seed = 20260907 + int(selected != original)
        if receipt['original_candidate_seat'] != original:
            raise AssertionError('Original candidate identity changed')
        if (receipt['candidate_actor_rng_seed'] != expected_seed or
                receipt['candidate_pythonhashseed'] != expected_seed):
            raise AssertionError('View does not retain the original actor RNG contract')
        stream = b''.join(canonical(row) + b'\n' for row in inputs)
        if hashlib.sha256(stream).hexdigest() != receipt['input_jsonl_sha256']:
            raise AssertionError('Recovered stream and its receipt disagree')
        successful_views[selected] = receipt
        return {'configuration': inputs[0]['configuration'],
                'frame_count': len(inputs), 'frames': inputs}

    result = boundary_contract.run_contract(recover, evaluator, engine, hashes)
    # Exercise the actual CLI file boundary as well as the public callable.
    # These two checks are reported separately, not added to unittest methods.
    cli_checks = []
    if result['successful']:
        document = boundary_contract.ReplayTests.report
        expected = boundary_contract.ReplayTests.observations[0]
        with tempfile.TemporaryDirectory(prefix='trace9042-shared-') as temporary:
            root = Path(temporary)
            source = root / 'source.json'
            source.write_bytes(canonical(document))
            for suffix in ('.jsonl', '.jsonl.gz'):
                output, receipt_path = root / ('inputs' + suffix), root / ('receipt' + suffix + '.json')
                with contextlib.redirect_stdout(io.StringIO()):
                    code = consumer.main(['--record', str(source), '--engine-dir', str(args.engine_dir),
                        '--evaluator', str(args.evaluator), '--tracer', str(args.tracer),
                        '--loader', str(args.loader), '--expected-trace', document['games'][0]['trace_sha256'],
                        '--output', str(output), '--receipt', str(receipt_path)])
                encoded = output.read_bytes()
                decoded = gzip.decompress(encoded) if suffix.endswith('.gz') else encoded
                rows = [json.loads(line) for line in decoded.splitlines()]
                receipt = json.loads(receipt_path.read_bytes())
                checks = {'return_code_zero': code == 0,
                    'observations_match': [row['observation'] for row in rows] == expected,
                    'expected_actions_match': [row['expected_action'] for row in rows] ==
                        [row['actions'][0] for row in document['games'][0]['actions_and_timing']],
                    'decoded_hash_matches': hashlib.sha256(decoded).hexdigest() == receipt['input_jsonl_sha256'],
                    'file_hash_matches': hashlib.sha256(encoded).hexdigest() == receipt['output_file_sha256'],
                    'source_unchanged': source.read_bytes() == canonical(document)}
                cli_checks.append({'suffix': suffix, 'count': len(rows), 'checks': checks,
                                   'successful': all(checks.values())})
    result.update({'cli_checks': cli_checks,
        'successful_views': successful_views,
        'source_sha256': {key: hashlib.sha256(getattr(args, key).read_bytes()).hexdigest()
                          for key in ('consumer', 'evaluator', 'tracer', 'loader')},
        'test_adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'shared_source_executed': True,
        'retained_development_trace_executed': False})
    result['successful'] = result['successful'] and len(cli_checks) == 2 and all(c['successful'] for c in cli_checks)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ('successful', 'tests_run', 'failures', 'errors', 'source_sha256')}, sort_keys=True))
    return 0 if result['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
