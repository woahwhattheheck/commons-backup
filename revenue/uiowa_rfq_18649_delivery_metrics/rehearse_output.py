#!/usr/bin/env python3
"""Run the real metrics CLI on disposable synthetic evidence; never live records.

Calculator source and the fixture are captured once. The captured source buffer
is executed, and the captured fixture buffer supplies every scenario. Results
are observations, not provider execution authority or a release decision.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest import mock

HERE = Path(__file__).resolve().parent
START = '2026-09-01T00:00:00Z'
END = '2026-09-15T00:00:00Z'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_captured(path: Path):
    source = path.read_bytes()
    name = '_uiowa64_rehearsal_' + git_blob(source)
    module = types.ModuleType(name)
    module.__file__ = str(path.resolve())
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path.resolve()), 'exec'), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module, source, name, previous


def rehearse(calculator: Path, fixture: Path) -> dict:
    fixture_bytes = fixture.read_bytes()
    calc, source_bytes, module_name, previous = load_captured(calculator)
    cases = []
    try:
        with tempfile.TemporaryDirectory(prefix='uiowa64-rehearsal-') as td:
            root = Path(td)
            evidence, output = root/'evidence.csv', root/'report.json'
            evidence.write_bytes(fixture_bytes)

            def invoke(destination=None):
                args = [str(evidence), '--window-start', START, '--window-end', END]
                if destination is not None:
                    args += ['--output', str(destination)]
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = calc.main(args)
                # Temporary path names are not meaningful scenario identity.
                error = stderr.getvalue().replace(str(root), '<temporary>')
                return code, stdout.getvalue().encode('utf-8'), error

            code, reference, error = invoke()
            if code != 0:
                raise ValueError(f'reference CLI failed: {error}')
            report = json.loads(reference)

            def observe(case_id, action, expected_code, before, result, expected_after, explanation):
                code, stdout, error = result
                after = output.read_bytes() if output.exists() else None
                source_ok = evidence.read_bytes() == fixture_bytes
                clean = not list(root.glob('.uiowa64-report-*.tmp'))
                ok = code == expected_code and not stdout and after == expected_after and source_ok and clean
                cases.append({
                    'id': case_id, 'action': action, 'expected_exit': expected_code,
                    'observed_exit': code, 'diagnostic': error.strip(),
                    'source_preserved': source_ok, 'temporary_files_cleaned': clean,
                    'prior_report_preserved': before is not None and before == after,
                    'report_matches_reference': after == reference,
                    'report_before_sha256': sha256(before) if before is not None else None,
                    'report_after_sha256': sha256(after) if after is not None else None,
                    'passed': ok, 'interpretation': explanation,
                })

            observe('NEW', 'Publish a new report', 0, None, invoke(output), reference,
                    'A successful file export agrees byte-for-byte with the actual stdout report.')
            observe('INPUT_ALIAS', 'Attempt to use the evidence CSV as the output', 2, reference,
                    invoke(evidence), reference,
                    'The source is evidence, not a report destination. Choose a different regular path.')

            # The supported candidate exposes os for flush/replace operations. A
            # baseline without that helper still runs through the failure probe;
            # the probe then reports its observed unsafe success, not a fake pass.
            with mock.patch.object(os, 'fsync', side_effect=OSError('synthetic disk flush failure')):
                observe('INTERRUPTED', 'Interrupt publication during flush', 2, reference,
                        invoke(output), reference,
                        'A failed publication must not truncate the last complete report.')
            observe('RETRY', 'Retry with the same evidence after the failure', 0, reference,
                    invoke(output), reference,
                    'The same input produces the same complete report after the interruption clears.')

            alias = root/'source-hardlink.csv'
            os.link(evidence, alias)
            observe('HARDLINK_ALIAS', 'Attempt to overwrite a hardlink to the evidence', 2, reference,
                    invoke(alias), reference,
                    'A different filename is not enough: both names can refer to the same evidence file.')

            archive = root/'retained-report.json'
            archive.write_bytes(b'previous retained report\n')
            os.unlink(output)
            os.link(archive, output)
            with mock.patch.object(os, 'replace', side_effect=OSError('synthetic replace failure')):
                observe('REPLACE_FAILURE', 'Interrupt replacement of a prior hardlinked report', 2,
                        b'previous retained report\n', invoke(output), b'previous retained report\n',
                        'A replacement failure leaves the previous report and its archived name unchanged.')
            observe('REPLACE_RETRY', 'Retry replacement while retaining the archived report', 0,
                    b'previous retained report\n', invoke(output), reference,
                    'Successful replacement updates the destination but not the separate archived name.')
            cases[-1]['archive_preserved'] = archive.read_bytes() == b'previous retained report\n'
            cases[-1]['passed'] &= cases[-1]['archive_preserved']
            final_source_ok = evidence.read_bytes() == fixture_bytes
        return {
            'schema': 'uiowa64.output-rehearsal.v1', 'synthetic': True,
            'source_binding': {
                'calculator_git_blob': git_blob(source_bytes),
                'calculator_sha256': sha256(source_bytes),
                'fixture_git_blob': git_blob(fixture_bytes), 'fixture_sha256': sha256(fixture_bytes),
                'basis': 'execute captured calculator bytes; copy captured fixture bytes',
            },
            'window': {'start': START, 'end_exclusive': END},
            'reference_report': report, 'reference_report_sha256': sha256(reference),
            'cases': cases, 'passed': all(case['passed'] for case in cases) and final_source_ok,
            'boundaries': {
                'provider_execution_authority': False, 'release_approval': False,
                'university_findings': False, 'live_data_access': False,
                'crash_durability_proved': False, 'hostile_directory_swap_protection_proved': False,
                'concurrent_writer_serialization_proved': False,
            },
        }
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous


def render_markdown(result: dict) -> str:
    state = 'PASS' if result['passed'] else 'FAIL'
    lines = ['# Synthetic report-publication rehearsal', '',
             f"Result: **{state}**; {sum(x['passed'] for x in result['cases'])}/{len(result['cases'])} scenarios satisfied.",
             '', 'This is an executed offline workflow, not University evidence, hosted CI or release approval.', '',
             f"Captured calculator blob: `{result['source_binding']['calculator_git_blob']}`.",
             f"Captured fixture blob: `{result['source_binding']['fixture_git_blob']}`.", '',
             '| Scenario | Exit | Source intact | Expected state |', '|---|---:|---|---|']
    for case in result['cases']:
        lines.append(f"| {case['id']} | {case['observed_exit']} | {case['source_preserved']} | {'PASS' if case['passed'] else 'FAIL'} |")
    for case in result['cases']:
        lines += ['', f"## {case['id']}: {case['action']}", '', case['interpretation']]
        if case['diagnostic']:
            lines += ['', 'Observed diagnostic:', '```text', case['diagnostic'], '```']
    m = result['reference_report']['metrics']
    lines += ['', '## Report produced by the real calculator', '',
              f"The supplied fictional history gives {result['reference_report']['scope']['deployment_count']} deployments, "
              f"{m['deployment_frequency']['deployments_per_week']} deployments/week, "
              f"{m['change_lead_time']['median']} hours median lead time, "
              f"{m['failed_deployment_recovery_time']['median']} hours median recovery, "
              f"{m['change_fail_rate']['percent']}% failure and {m['deployment_rework_rate']['percent']}% rework.", '',
              'Only disposable copies are mutated. The final JSON includes complete reports, per-scenario hashes and explicit limits.',
              'The source path must name trusted local calculator code. This command executes it; it does not sandbox arbitrary Python.',
              'No power-loss, hostile directory-swap, concurrent-writer or provider-execution guarantee is established.', '']
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calculator', type=Path, default=HERE/'calculator.py')
    parser.add_argument('--fixture', type=Path, default=HERE/'fixtures/synthetic_deployments.csv')
    parser.add_argument('--format', choices=('json', 'markdown'), default='markdown')
    args = parser.parse_args(argv)
    try:
        result = rehearse(args.calculator, args.fixture)
        text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+'\n' if args.format == 'json' else render_markdown(result)
        sys.stdout.write(text)
        return 0 if result['passed'] else 1
    except (OSError, ValueError, SyntaxError, TypeError) as exc:
        print(f'ERROR: rehearsal could not complete: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
