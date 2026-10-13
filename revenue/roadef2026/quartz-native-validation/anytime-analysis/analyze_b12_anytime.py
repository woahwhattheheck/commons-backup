#!/usr/bin/env python3
"""Read QUARTZ's immutable B12 evidence; never run a solver or checker.

Usage: python analyze_b12_anytime.py --evidence ARCHIVE.zip --context CONTEXT.zip --output RESULT.json
Reuses the unchanged, source-pinned compare_checker.py inside the context archive.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
from typing import Any
import zipfile

EVIDENCE_SHA = '1494b0faf268be12b99f25444ce5bd6c42539a187c00ca7ef29f11d24484fd9f'
CONTEXT_SHA = '62bb113f6fecf074fad8a5a76623c548d099466e230f509c8e353fb2b2e181e6'
COMPARATOR_SHA = '225169ef7e1e81f1006b296a186973e9b885d24dbfa5304b2695286cadf8d765'
PREFIX = 'full-budget/artifacts/roadef-portfolio-u51si52l/'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_archive(path: Path, expected: str, manifest_name: str) -> tuple[zipfile.ZipFile, dict]:
    require(sha(path.read_bytes()) == expected, f'Archive digest mismatch: {path.name}')
    archive = zipfile.ZipFile(path)
    try:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate ZIP member names')
        manifest = json.loads(archive.read(manifest_name))
        entries = manifest['files']
        require(len({entry['path'] for entry in entries}) == len(entries), 'Duplicate manifest entry')
        for entry in entries:
            data = archive.read(entry['path'])
            require(len(data) == entry['bytes'] and sha(data) == entry['sha256'],
                    f"Manifest mismatch: {entry['path']}")
        return archive, {'zip_sha256': expected, 'manifest': manifest_name,
                         'verified_payload_count': len(entries)}
    except BaseException:
        archive.close()
        raise


def log_summary(data: bytes) -> dict:
    text = data.decode('utf-8')
    match = re.search(r'Completed (\d+) improving moves / (\d+) attempts; MLU ([\d.eE+-]+); elapsed ([\d.eE+-]+)s', text)
    require(match is not None, 'Missing completed lane record')
    return {'accepted_moves': int(match[1]), 'attempts': int(match[2]),
            'logged_mlu': match[3], 'logged_elapsed_seconds': float(match[4]), 'log_sha256': sha(data)}


def analyze(evidence_path: Path, context_path: Path) -> dict[str, Any]:
    evidence, evidence_integrity = verify_archive(evidence_path, EVIDENCE_SHA, 'MANIFEST.json')
    context, context_integrity = verify_archive(context_path, CONTEXT_SHA, 'TRANSFER-MANIFEST.json')
    with evidence, context, tempfile.TemporaryDirectory(prefix='b12-evidence-reader-') as temporary:
        work = Path(temporary)
        comparator_bytes = context.read('context/compare_checker.py')
        require(sha(comparator_bytes) == COMPARATOR_SHA, 'Comparator source changed')
        comparator_path = work / 'compare_checker.py'
        comparator_path.write_bytes(comparator_bytes)
        spec = importlib.util.spec_from_file_location('b12_pinned_comparator', comparator_path)
        require(spec is not None and spec.loader is not None, 'Could not load pinned comparator')
        comparator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(comparator)

        def load(member: str) -> dict:
            # A single temporary input avoids copying the benchmark archive or running native binaries.
            path = work / 'checker.json'
            path.write_bytes(evidence.read(member))
            record = comparator.load_result(path)
            record['path'] = member
            return record

        receipt = json.loads(evidence.read('full-budget/portfolio-B12.json.portfolio.json'))
        resources = json.loads(evidence.read('full-budget/portfolio-resources.json'))
        baseline_resources = json.loads(evidence.read('full-budget/baseline-resources.json'))
        baseline_member = 'full-budget/baseline/setB-12/sedge/checker-6.stdout'
        baseline = load(baseline_member)
        flora_member = PREFIX + '8403ec1044d7ec8dff3ae4d150d04e40c3c34638dab65a3850d49997aed2a546.checker-6.json'
        flora = load(flora_member)
        final = load('full-budget/portfolio-independent-checker-6.json')
        baseline_solution_sha = sha(evidence.read('full-budget/baseline/setB-12/sedge/solution.json'))
        require(baseline_solution_sha == sha(evidence.read(PREFIX + 'sedge.json')),
                'Independent baseline and portfolio SEDGE final solutions differ')
        require(sha(evidence.read('full-budget/portfolio-B12.json')) == receipt['solution_sha256'],
                'Final solution and receipt differ')
        for path, digest in receipt['input_sha256'].items():
            require(sha(evidence.read('inputs/' + Path(path).name)) == digest, 'Input binding mismatch')
        for lane in receipt['lanes']:
            require(sha(evidence.read('bin/' + lane['name'])) == lane['source_binary_sha256'],
                    'Lane binary binding mismatch')

        events = receipt['events']
        improved = {e['solution_sha256']: e for e in events if e['event'] == 'incumbent_improved'}
        require(len(improved) == sum(e['event'] == 'incumbent_improved' for e in events),
                'Incumbent digest appears twice')
        best = None
        best_digest = None
        rows = []
        for event in events:
            if event['event'] != 'check_completed':
                continue
            digest = event['solution_sha256']
            solution_member = PREFIX + digest + '.solution.json'
            checker_member = PREFIX + digest + '.checker-6.json'
            require(sha(evidence.read(solution_member)) == digest, 'Checkpoint identity mismatch')
            record = load(checker_member)
            require(record['valid'] == event['valid'], 'Recorded checker validity mismatch')
            versus_previous = comparator.compare(record, best) if best is not None else None
            accept = record['valid'] and (best is None or versus_previous['winner'] == 'left')
            require(accept == (digest in improved), 'Reconstructed selection disagrees with recorded incumbent')
            if accept:
                best = record
                best_digest = digest
            row = {'lane': event['lane'], 'checked_at_seconds': event['elapsed_seconds'],
                   'checker_seconds': event['checker_seconds'], 'solution_sha256': digest,
                   'checker_member': checker_member, 'checker_sha256': record['sha256'],
                   'valid': record['valid'], 'selected': accept,
                   'versus_previous_incumbent': versus_previous,
                   'installed_at_seconds': improved[digest]['elapsed_seconds'] if accept else None,
                   'versus_independent_sedge_final': comparator.compare(record, baseline),
                   'versus_flora_final': comparator.compare(record, flora),
                   'versus_selected_final': comparator.compare(record, final)}
            rows.append(row)
        require(best_digest == receipt['solution_sha256'], 'Reconstructed final differs from receipt')
        reference = json.loads(evidence.read('full-budget/B12-comparison.json'))
        comparison = comparator.compare(final, baseline)
        require(all(reference[k] == v for k, v in comparison.items()), 'Existing final comparison differs')

        def first(predicate):
            return next(({'lane': r['lane'], 'installed_at_seconds': r['installed_at_seconds'],
                          'checked_at_seconds': r['checked_at_seconds'], 'solution_sha256': r['solution_sha256'],
                          'versus_sedge': r['versus_independent_sedge_final'],
                          'versus_flora': r['versus_flora_final']}
                         for r in rows if predicate(r)), None)

        lane_logs = {name: log_summary(evidence.read(PREFIX + name + '.log'))
                     for name in ('sedge', 'flora', 'candidate')}
        for name, values in lane_logs.items():
            source = context.read('context/sources/' + name + '/main.cpp')
            text = source.decode()
            expected_terms = ['stalled >= 64', 'stalled >= 12', 'stalled % count', '1000000']
            require(all(term in text for term in expected_terms), 'Historical termination source changed')
            values.update(source_sha256=sha(source),
                          maximum_rounds_from_logged_accepts_and_stall_rule=64 * (values['accepted_moves'] + 1))
        checks = [e for e in events if e['event'] == 'check_completed']
        return {
            'schema': 'roadef.quill.b12-anytime.v1', 'analysis_kind': 'offline retained-evidence consumer',
            'new_solver_runs': 0, 'new_checker_runs': 0, 'runtime_source_changes': 0,
            'source_commit': '2885d176373c33410148829fef93c310c3752c0b',
            'integrity': {'evidence': evidence_integrity, 'context': context_integrity,
                          'comparator_sha256': COMPARATOR_SHA, 'original_event_count': len(events),
                          'baseline_checker_sha256': baseline['sha256'],
                          'final_checker_sha256': final['sha256'], 'same_sedge_solution_bytes': True},
            'counts': {'checked_snapshots': len(rows), 'recorded_and_reconstructed_incumbents': len(improved),
                       'checked_per_lane': dict(Counter(r['lane'] for r in rows)),
                       'accepted_per_lane': dict(Counter(r['lane'] for r in rows if r['selected'])),
                       'loads_per_valid_snapshot': len(final['vector'])},
            'milestones': {
                'first_incumbent_with_final_peak': first(lambda r: r['selected'] and r['versus_selected_final'].get('left_mlu') == r['versus_selected_final'].get('right_mlu')),
                'first_incumbent_equal_to_sedge_final': first(lambda r: r['selected'] and r['versus_independent_sedge_final']['winner'] == 'tie'),
                'first_incumbent_beating_sedge_final': first(lambda r: r['selected'] and r['versus_independent_sedge_final']['winner'] == 'left'),
                'first_candidate_beating_flora_final': first(lambda r: r['lane'] == 'candidate' and r['versus_flora_final']['winner'] == 'left'),
                'final_incumbent_first_installed_seconds': improved[best_digest]['elapsed_seconds'],
                'final_solution_sha256': best_digest},
            'final_comparison': comparison, 'lane_logs': lane_logs,
            'timing': {'search_allowance_seconds': receipt['search_allowance_seconds'],
                       'supervisor_deadline_seconds': receipt['deadline_seconds'],
                       'supervisor_wall_seconds': receipt['wall_seconds'],
                       'observer_wall_seconds': resources['wall_seconds'],
                       'seconds_after_last_install_until_supervisor_finish': round(receipt['wall_seconds'] - improved[best_digest]['elapsed_seconds'], 4),
                       'unused_search_allowance_at_supervisor_finish_seconds': round(receipt['search_allowance_seconds'] - receipt['wall_seconds'], 4),
                       'check_seconds_sum': round(sum(e['checker_seconds'] for e in checks), 4),
                       'check_seconds_are_overlapped_not_serial_overhead': True,
                       'signal_received': receipt['signal_received'],
                       'lane_returncodes': {l['name']: l['returncode'] for l in receipt['lanes']},
                       'process_tree_peak_rss_kib': resources['sampled_peak_tree_rss_kib'],
                       'memory_limit_bytes': int(resources['memory_max']),
                       'cpu_quota': resources['cpu_max'],
                       'independent_baseline_observer_wall_seconds': baseline_resources['wall_seconds']},
            'termination_interpretation': {
                'source_rule': 'adaptive && stalled >= 64 breaks; adaptive enabled after >=12 stalled rounds or 65% of time allowance',
                'supervisor_rule': 'finishes after all lane final outputs are checked; does not restart completed lanes',
                'recorded_terminal_stall_counter': None,
                'recorded_solver_exit_reason': None,
                'inference': 'Elapsed times, normal return codes, absent supervisor signal, reset-on-accept stall bound, and unset round cap support the bounded-stall exit, not exhaustion of the 565-second allowance. The terminal counter itself was not logged.',
                'not_established': 'Global or exhaustive local optimality, benefit from more time, benefit from restarting, or a new deadline/Docker qualification.'},
            'snapshots': rows,
            'limits': ['Milestones are retrospective checker-availability times, not exact discovery times.',
                       'The independent final baseline is an offline analysis reference, never a solver input.',
                       'Only one public B12 instance/run; no held sample, competitive rank, or policy promotion.',
                       'No snapshots or errors have been replaced; the original QUARTZ archives remain the evidence.']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.evidence, args.context)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Analysis failed: {error}\n')
    print(json.dumps({k: result[k] for k in ('counts', 'milestones', 'timing')}, indent=2))


if __name__ == '__main__':
    main()
