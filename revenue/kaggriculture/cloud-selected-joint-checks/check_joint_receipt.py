# SPDX-License-Identifier: Apache-2.0
"""Read one existing TITAN validation ZIP; never execute its contents or rerun tests."""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Any
import zipfile

from supplemental_receipt import SUPPLEMENTS, inspect_supplemental

ROOT = 'revenue/kaggriculture/'
LAB = ROOT + 'cloud-execution-lab/'
PROJECTION = ROOT + 'cloud-selected-projection/'
MARKET = ROOT + 'cloud-selected-market-checks/'
ENGINE_FILES = ('kaggriculture.py', 'kaggriculture.json', 'utils.py')
RUNTIME_FILES = ('selected_action_sell.py', 'selected_sell_core.py', 'mechanics.py',
                 'reference/decision/decision.py')
SUITES = {
    'original': ('original-seller-tests.log', None, 16, LAB + 'test_selected_action_sell.py'),
    'projection': ('projection-tests.log', 'projection-results.json', 21, PROJECTION + 'test_projection.py'),
    'market': ('market-tests.log', 'market-results.json', 14, MARKET + 'check_market_contracts.py'),
}
# Additional suites are recognized when their evidence is present, declared by
# the aggregate, or explicitly requested. Historical three-suite ZIPs stay valid.
OPTIONAL_SUITES = {
    'reporter': ('reporter-tests.log', None, 22, PROJECTION + 'test_combined_report.py'),
    'funded_join': ('funded-join-tests.log', 'funded-join-results.json', 16,
                    ROOT + 'cloud-composition-cases/cypress/test_funded_join.py'),
}
FUNDED_SOURCES = (
    'cloud-composition-cases/cypress/test_funded_join.py',
    'cloud-execution-lab/integrated_selected.py',
    'cloud-execution-lab/ordered_selected_sell.py',
    'cloud-execution-lab/reference/engine/kaggriculture.py',
    'cloud-execution-lab/reference/integrated-selected/alder/seed_budget.py',
    'cloud-execution-lab/reference/ordered-feasibility/atlas/projection.py',
    'cloud-execution-lab/selected_action_sell.py',
    'cloud-integration-differentials/funded_main.py',
    'cloud-integration-differentials/seed_funding.py',
)
MAX_MEMBER = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_members(path: Path | BytesIO) -> dict[str, bytes]:
    """Read a path or captured ZIP stream without extracting archive paths."""
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if sum(info.file_size for info in infos) > MAX_TOTAL:
            raise ValueError('archive uncompressed size exceeds 32 MiB')
        result: dict[str, bytes] = {}
        for info in infos:
            parts = PurePosixPath(info.filename)
            if parts.is_absolute() or '..' in parts.parts or '\\' in info.filename:
                raise ValueError('ambiguous archive member path')
            name = parts.name
            if name in result:
                raise ValueError(f'duplicate or ambiguous member basename: {name}')
            if info.file_size > MAX_MEMBER:
                raise ValueError(f'member exceeds 8 MiB: {name}')
            result[name] = archive.read(info)
        return result


def integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def inspect_archive(path: Path, *, expected_sha256: str | None = None,
                    expected_checkout: str | None = None,
                    expected_run_id: str | None = None,
                    expected_attempt: str | None = None,
                    market_report: str = 'market-results.json',
                    market_log: str = 'market-tests.log',
                    required_suites: tuple[str, ...] = ()) -> dict[str, Any]:
    # Hash and parse one captured input. A downloader may replace the path
    # after this read; its later bytes must not inherit this snapshot's digest.
    archive_bytes = path.read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    problems: list[dict[str, str]] = []
    summaries: dict[str, Any] = {}
    reports: dict[str, dict[str, Any]] = {}
    sources: dict[str, Any] = {}
    snapshot: dict[str, Any] = {}

    def problem(level: str, detail: str) -> None:
        problems.append({'level': level, 'detail': detail})

    expected = expected_sha256.removeprefix('sha256:').lower() if expected_sha256 else None
    digest_ok = None if expected is None else expected == digest
    if expected is None:
        problem('missing', 'provider artifact digest was not supplied')
    elif not re.fullmatch(r'[0-9a-f]{64}', expected):
        problem('failure', 'invalid expected SHA-256')
    elif not digest_ok:
        problem('failure', 'artifact SHA-256 differs from supplied provider digest')

    try:
        members = read_members(BytesIO(archive_bytes))
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        members = {}
        problem('failure', f'cannot read evidence ZIP: {exc}')

    def obj(name: str) -> dict[str, Any] | None:
        if name not in members:
            problem('missing', f'missing {name}')
            return None
        try:
            value = json.loads(members[name].decode('utf-8'), object_pairs_hook=unique_object)
            if not isinstance(value, dict):
                raise ValueError('expected a JSON object')
            return value
        except (ValueError, UnicodeError) as exc:
            problem('failure', f'invalid {name}: {exc}')
            return None

    snapshot = obj('SOURCE-SNAPSHOT.json') or {}
    files = snapshot.get('files', {})
    if not isinstance(files, dict):
        problem('failure', 'snapshot files is not an object')
        files = {}
    for field, pattern in (('checkout', r'[0-9a-f]{40}'), ('run_id', r'[1-9][0-9]*'),
                           ('attempt', r'[1-9][0-9]*')):
        value = snapshot.get(field)
        if value is None:
            problem('missing', f'snapshot has no {field}')
        elif not re.fullmatch(pattern, str(value)):
            problem('failure', f'invalid snapshot {field}')
    for field, expected_value in (('checkout', expected_checkout), ('run_id', expected_run_id),
                                  ('attempt', expected_attempt)):
        if expected_value is not None and str(snapshot.get(field)) != str(expected_value):
            problem('failure', f'snapshot {field} differs from expected value')

    def source(name: str) -> str | None:
        entry = files.get(name)
        if entry is None:
            problem('missing', f'snapshot has no source: {name}')
            return None
        sha = entry.get('sha256') if isinstance(entry, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
            problem('failure', f'invalid source SHA-256: {name}')
            return None
        sources[name] = sha
        return sha

    for name in RUNTIME_FILES:
        source(LAB + name)
    source(PROJECTION + 'projection.py')
    for name in ENGINE_FILES:
        source(LAB + 'reference/engine/' + name)

    def match_source(value: Any, name: str, description: str) -> None:
        expected_source = sources.get(name) or source(name)
        if value is None:
            problem('missing', f'{description}: no reported hash')
        elif not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
            problem('failure', f'{description}: invalid reported hash')
        elif expected_source is not None and value != expected_source:
            problem('failure', f'{description}: source differs from snapshot')

    required = set(required_suites)
    unknown_required = required - (SUITES.keys() | OPTIONAL_SUITES.keys() | SUPPLEMENTS.keys())
    if unknown_required:
        raise ValueError('unknown required suites: ' + ', '.join(sorted(unknown_required)))
    before_combined = len(problems)
    combined = obj('COMBINED-RESULTS.json') if 'COMBINED-RESULTS.json' in members else None
    combined_problems = problems[before_combined:]
    del problems[before_combined:]
    core_receipt = None

    def core_result() -> dict[str, Any]:
        return {
            'status': ('FAIL' if any(p['level'] == 'failure' for p in problems) else
                       'INCOMPLETE' if problems else 'COMPLETE_PASS'),
            'reported_test_methods': sum(summaries[k]['test_methods'] or 0 for k in SUITES),
            'checkout': snapshot.get('checkout'),
            'problems': [dict(p) for p in problems],
        }
    suite_specs = dict(SUITES)
    for label, spec in OPTIONAL_SUITES.items():
        declared = combined is not None and (label + '_tests' in combined or
                   (isinstance(combined.get('suites'), dict) and label in combined['suites']))
        if label in required or declared or any(name in members for name in spec[:2] if name):
            suite_specs[label] = spec

    for label, (log_name, report_name, minimum, test_path) in suite_specs.items():
        if label not in SUITES and core_receipt is None:
            core_receipt = core_result()
        if label == 'market':
            log_name, report_name = market_log, market_report
        source(test_path)
        summary: dict[str, Any] = {'minimum_methods': minimum, 'test_methods': None,
                                   'log': log_name, 'reported_pass': False}
        summaries[label] = summary
        text = ''
        if log_name not in members:
            problem('missing', f'missing {log_name}')
        else:
            try:
                text = members[log_name].decode('utf-8').replace('\r\n', '\n')
            except UnicodeError:
                problem('failure', f'invalid UTF-8: {log_name}')
            counts = list(re.finditer(r'^Ran (\d+) tests? in [^\n]+$', text, re.MULTILINE))
            endings = list(re.finditer(r'^(OK(?: \([^\n]*\))?|FAILED(?: \([^\n]*\))?)$', text, re.MULTILINE))
            if re.search(r'^FAILED(?: |$)', text, re.MULTILINE):
                problem('failure', f'{label}: unittest failure footer is present')
            if (len(counts) != 1 or len(endings) != 1
                    or endings[0].start() < counts[0].end()):
                problem('missing', f'{label}: missing or ambiguous unittest completion')
            else:
                count = int(counts[0].group(1))
                ending = endings[0].group(1)
                summary['test_methods'] = count
                summary['reported_pass'] = ending == 'OK'
                if count < minimum:
                    problem('failure', f'{label}: {count} methods is below required coverage {minimum}')
                if ending.startswith('FAILED'):
                    problem('failure', f'{label}: unittest reports failure')
                elif ending != 'OK':
                    problem('missing', f'{label}: skipped/qualified completion is not full coverage')
        if report_name is None:
            continue
        report = obj(report_name)
        if report is None:
            continue
        reports[label] = report
        count_key = 'tests_run' if label == 'projection' else 'test_methods'
        for key in (count_key, 'failures', 'errors'):
            if not integer(report.get(key)):
                problem('failure', f'{label}: invalid {key}')
        if integer(report.get(count_key)):
            if report[count_key] < minimum:
                problem('failure', f'{label}: report omits required methods')
            if summary['test_methods'] is not None and report[count_key] != summary['test_methods']:
                problem('failure', f'{label}: report and log method counts differ')
        if report.get('failures') != 0 or report.get('errors') != 0:
            problem('failure', f'{label}: report contains failures/errors')
        if label == 'funded_join':
            if report.get('successful') is not True:
                problem('failure', 'funded_join: successful is not true')
            for field in ('full_games', 'new_game_seeds'):
                if not integer(report.get(field)) or report[field] != 0:
                    problem('failure', f'funded_join: unexpected {field}')
            for report_key, snapshot_key in (('workflow_run', 'run_id'),
                                             ('workflow_attempt', 'attempt')):
                value = report.get(report_key)
                if value is None:
                    problem('missing', f'funded_join: missing {report_key}')
                elif str(value) != str(snapshot.get(snapshot_key)):
                    problem('failure', f'funded_join: {report_key} differs from snapshot')
            reported_sources = report.get('sources', {})
            if not isinstance(reported_sources, dict):
                problem('failure', 'funded_join: sources is not an object')
                reported_sources = {}
            for name in dict.fromkeys((*FUNDED_SOURCES, *reported_sources)):
                entry = reported_sources.get(name)
                match_source(entry.get('sha256') if isinstance(entry, dict) else None,
                             ROOT + name, f'funded_join {name}')
            cases = report.get('official_transitions')
            if not integer(cases) or cases == 0:
                problem('failure', 'funded_join: no positive official_transitions')
            else:
                summary['official_transitions'] = cases
            continue
        engine = report.get('engine_sha256')
        if not isinstance(engine, dict):
            problem('missing', f'{label}: engine hashes absent')
            engine = {}
        for name in ENGINE_FILES:
            match_source(engine.get(name), LAB + 'reference/engine/' + name, f'{label} engine {name}')
        if label == 'projection':
            match_source(report.get('seller_sha256'), LAB + 'selected_action_sell.py', 'projection seller')
            match_source(report.get('projection_sha256'), PROJECTION + 'projection.py', 'projection implementation')
            for key in ('differential_cases', 'interpreter_transitions'):
                if not integer(report.get(key)) or report[key] == 0:
                    problem('failure', f'projection: missing positive {key}')
                else:
                    summary[key] = report[key]
        else:
            reported_sources = report.get('sources', {})
            if not isinstance(reported_sources, dict):
                problem('failure', 'market: sources is not an object')
                reported_sources = {}
            for name in RUNTIME_FILES:
                match_source(reported_sources.get(name), LAB + name, f'market {name}')
            if report.get('schema') != 'titan.selected-market-checks.v1':
                problem('failure', 'market: unexpected report schema')
            if report.get('successful') is not True:
                problem('failure', 'market: successful is not true')
            if report.get('game_panels') != 0 or report.get('seeds_consumed') != []:
                problem('failure', 'market: unexpected gameplay/seed scope')
            cases = report.get('official_market_cases')
            if not integer(cases) or cases == 0:
                problem('failure', 'market: no positive official market-case count')
            else:
                summary['official_market_cases'] = cases

    if core_receipt is None:
        core_receipt = core_result()
    supplemental = inspect_supplemental(members, snapshot, core_receipt)
    summaries.update(supplemental['suites'])
    sources.update(supplemental['sources'])
    problems.extend(supplemental['problems'])
    problems.extend(combined_problems)
    for label, (log, report, minimum, paths) in SUPPLEMENTS.items():
        declared = combined is not None and (label + '_tests' in combined or
                   (isinstance(combined.get('suites'), dict) and label in combined['suites']))
        if label in summaries or label in required or declared:
            suite_specs[label] = (log, report, minimum, paths[0])
        if label not in summaries and (label in required or declared):
            summaries[label] = {'log': log, 'minimum_methods': minimum,
                                'test_methods': None, 'reported_pass': False}
            problem('missing', f'required supplemental suite is absent: {label}')

    recognized_logs = {item['log'] for item in summaries.values()}
    unrecognized_logs = []
    for name, payload in members.items():
        if not name.endswith('.log') or name in recognized_logs:
            continue
        text = payload.decode('utf-8', errors='replace').replace('\r\n', '\n')
        if name.endswith('-tests.log') or re.search(r'^Ran \d+ tests? in ', text, re.MULTILINE):
            unrecognized_logs.append(name)
            problem('missing', f'unrecognized test evidence: {name}')
            if re.search(r'^FAILED(?: |$)', text, re.MULTILINE):
                problem('failure', f'{name}: unittest failure footer is present')
    recognized_methods = sum(item['test_methods'] or 0 for item in summaries.values())
    aggregate_summary = None
    if combined is not None:
        # Aggregate totals have historically covered a subset. Do not let this
        # advisory total overrule the actual logs/reports in either direction.
        declared_total = combined.get('total_tests')
        aggregate_summary = {
            'declared_total_tests': declared_total,
            'recognized_test_methods': recognized_methods,
            'total_matches_recognized': (integer(declared_total)
                                          and declared_total == recognized_methods),
            'authoritative_for_suite_verdicts': False,
        }
        if combined.get('checkout') is not None and combined['checkout'] != snapshot.get('checkout'):
            problem('failure', 'combined summary checkout differs from snapshot')

        if combined.get('schema') == 'titan.selected-projection.combined.v2':
            # The v2 producer declares exact per-suite logs and input digests.
            # Check those declarations against the original bytes; never import
            # or execute the producer, archived code, or any test suite.
            declared_suites = combined.get('suites')
            if not isinstance(declared_suites, dict):
                problem('failure', 'combined v2: suites is not an object')
                declared_suites = {}
            for key in ('run_id', 'attempt'):
                if str(combined.get(key)) != str(snapshot.get(key)):
                    problem('failure', f'combined v2: {key} differs from snapshot')
            for key in ('complete', 'successful'):
                if combined.get(key) is not True:
                    problem('failure', f'combined v2: {key} is not true')
            if not integer(combined.get('suite_count')) or combined['suite_count'] != len(declared_suites):
                problem('failure', 'combined v2: suite_count differs from declarations')
            declared_sum = 0
            for label, entry in declared_suites.items():
                if not isinstance(entry, dict):
                    problem('failure', f'combined v2 {label}: declaration is not an object')
                    continue
                count = entry.get('tests')
                if not integer(count):
                    problem('failure', f'combined v2 {label}: invalid tests')
                else:
                    declared_sum += count
                summary = summaries.get(label)
                if summary is None:
                    problem('missing', f'combined v2: unexamined declared suite {label}')
                    continue
                if count != summary['test_methods']:
                    problem('failure', f'combined v2 {label}: method count differs from log')
                if entry.get('log') != summary['log']:
                    problem('failure', f'combined v2 {label}: log differs from recognized suite')
                if entry.get('successful') is not summary['reported_pass']:
                    problem('failure', f'combined v2 {label}: success differs from log')
                match_source(entry.get('test_source_sha256'), suite_specs[label][3],
                             f'combined v2 {label} test source')
            for label in summaries.keys() - declared_suites.keys():
                problem('missing', f'combined v2: observed suite is undeclared: {label}')
            for key in ('observed_tests', 'total_tests'):
                if not integer(combined.get(key)) or combined[key] != declared_sum:
                    problem('failure', f'combined v2: {key} differs from declared suites')
            if combined.get('problems') != []:
                problem('failure', 'combined v2: producer reports problems or omits problems list')
            if not integer(combined.get('full_games')) or combined['full_games'] != 0:
                problem('failure', 'combined v2: unexpected full_games')
            inputs = combined.get('input_sha256')
            if not isinstance(inputs, dict):
                problem('failure', 'combined v2: input_sha256 is not an object')
                inputs = {}
            required_inputs = {'SOURCE-SNAPSHOT.json'}
            for label, entry in declared_suites.items():
                if isinstance(entry, dict) and isinstance(entry.get('log'), str):
                    required_inputs.add(entry['log'])
                if label in suite_specs and suite_specs[label][1] is not None:
                    required_inputs.add(market_report if label == 'market' else suite_specs[label][1])
            for name in dict.fromkeys((*sorted(required_inputs), *inputs)):
                declared_digest = inputs.get(name)
                if name not in members:
                    problem('missing', f'combined v2: missing declared input {name}')
                elif not isinstance(declared_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', declared_digest):
                    problem('failure', f'combined v2: invalid or missing input digest {name}')
                elif declared_digest != hashlib.sha256(members[name]).hexdigest():
                    problem('failure', f'combined v2: input digest differs: {name}')
            aggregate_summary['schema'] = combined['schema']
            aggregate_summary['declared_suite_count'] = len(declared_suites)
            aggregate_summary['declarations_checked'] = True

    # Repeated source lookup diagnostics are rendered once, preserving order.
    problems = [dict(pair) for pair in dict.fromkeys(tuple(item.items()) for item in problems)]
    status = ('FAIL' if any(item['level'] == 'failure' for item in problems) else
              'INCOMPLETE' if problems else 'COMPLETE_PASS')
    return {
        'schema': 'titan.selected-joint-receipt.v1', 'status': status,
        'artifact_sha256': digest, 'provider_digest_matched': digest_ok,
        'checkout': snapshot.get('checkout'), 'run_id': snapshot.get('run_id'),
        'attempt': snapshot.get('attempt'), 'sources': sources, 'suites': summaries,
        'reported_test_methods': recognized_methods,
        'suite_coverage': {
            'checked_suites': list(summaries),
            'absent_optional_suites': sorted((OPTIONAL_SUITES.keys() | SUPPLEMENTS.keys()) - suite_specs.keys()),
            'unrecognized_test_logs': sorted(unrecognized_logs),
            'all_discovered_test_logs_recognized': not unrecognized_logs,
            'required_suites': sorted(required),
        },
        'core_receipt': core_receipt,
        'supplemental_receipt': supplemental,
        'aggregate_summary': aggregate_summary,
        'problems': problems, 'tests_rerun': 0, 'game_panels': 0, 'seeds_consumed': [],
        'scope': 'One existing artifact: reported suite results and declared pre-execution source alignment. '
                 'Not independent execution attestation, whole-repository CI, a gameplay result, or policy promotion.',
    }


def write_json_output(path: Path, rendered: str, *, archive: Path) -> None:
    """Publish one complete receipt without replacing its evidence archive.

    Resolve symlink destinations as Path.write_text did; a hard-linked output
    is replaced as a directory entry, not truncated through the shared inode.
    Staging is in the destination directory. This is not a multi-file or
    power-loss transaction; uncatchable exits may leave an unused stage file.
    """
    destination = path.resolve()
    evidence = archive.resolve()

    def check_destination() -> None:
        # Repeat before publication in case a normal concurrent writer linked
        # the destination to the evidence while this receipt was staged.
        if destination == evidence or (destination.exists() and destination.samefile(evidence)):
            raise ValueError('JSON output must not refer to the evidence archive')

    check_destination()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                dir=destination.parent, prefix='.' + destination.name + '.',
                suffix='.tmp', delete=False) as stream:
            staged = Path(stream.name)
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        check_destination()
        os.replace(staged, destination)
        staged = None
    finally:
        if staged is not None:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                # Cleanup must not hide the original write/replace exception.
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-checkout')
    parser.add_argument('--expected-run-id')
    parser.add_argument('--expected-attempt')
    parser.add_argument('--market-report', default='market-results.json')
    parser.add_argument('--market-log', default='market-tests.log')
    parser.add_argument('--json-output', type=Path)
    parser.add_argument('--require-suite', action='append', default=[],
                        help='Require an optional suite even when its files are absent; repeatable')
    args = parser.parse_args()
    try:
        report = inspect_archive(args.archive, expected_sha256=args.expected_sha256,
                                 expected_checkout=args.expected_checkout,
                                 expected_run_id=args.expected_run_id,
                                 expected_attempt=args.expected_attempt,
                                 market_report=args.market_report, market_log=args.market_log,
                                 required_suites=tuple(args.require_suite))
        rendered = json.dumps(report, indent=2, sort_keys=True) + '\n'
        if args.json_output:
            write_json_output(args.json_output, rendered, archive=args.archive)
        print(rendered, end='')
        return {'COMPLETE_PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2}[report['status']]
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'ERROR', 'detail': str(exc)}), file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
