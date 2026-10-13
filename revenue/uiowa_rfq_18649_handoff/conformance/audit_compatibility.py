"""Compare the actual retained legacy schema with the new mutation corpus.

From the handoff component directory:
    python conformance/audit_compatibility.py --out /tmp/schema-compatibility.json
The output must be new. A missing dependency, changed legacy snapshot, failed
suite, wrong test count or undocumented acceptance widening is a failure.
This is schema compatibility, not handoff.py semantic execution.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEGACY_BLOB = '9741733003f4fbad09cf9014382aadcd075eeab1'
ALLOWED_WIDENING = frozenset({
    'test_missing_evidence_fields_remain_representable_gaps',
    'test_empty_collections_are_not_fabricated_observations',
})

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def binding(path: Path) -> dict:
    data = path.read_bytes()
    return {'path':str(path.relative_to(ROOT)), 'bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest(), 'git_blob':git_blob(data)}

def changed_paths(before, after, path='$') -> list[str]:
    """Describe structural changes without copying entire packet bodies."""
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            child = path+'/'+key.replace('~','~0').replace('/','~1')
            if key not in before or key not in after:
                changes.append(child)
            else:
                changes.extend(changed_paths(before[key], after[key], child))
        return changes
    if isinstance(before, list):
        if len(before) != len(after):
            return [path]
        return [item for i,(left,right) in enumerate(zip(before,after))
                for item in changed_paths(left,right,path+'/'+str(i))]
    return [] if before == after else [path]


def run_audit() -> tuple[dict, bool]:
    source_paths = (ROOT/'schema.json', HERE/'legacy_schema.json',
                    HERE/'test_schema_contract.py', Path(__file__).resolve(),
                    ROOT/'examples/planned_release.json',
                    ROOT/'examples/urgent_maintenance.json')
    before_bindings = [binding(path) for path in source_paths]
    legacy_bytes = (HERE/'legacy_schema.json').read_bytes()
    if git_blob(legacy_bytes) != LEGACY_BLOB:
        raise ValueError('Legacy snapshot differs from the retained upstream Git blob.')
    legacy = json.loads(legacy_bytes)
    Draft202012Validator.check_schema(legacy)
    previous = Draft202012Validator(legacy, registry=Registry())
    corpus_path = HERE/'test_schema_contract.py'
    spec = importlib.util.spec_from_file_location('_uiowa050_schema_contract_corpus', corpus_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load the committed conformance corpus.')
    corpus = importlib.util.module_from_spec(spec)
    # The corpus imports no sibling modules and is not added to sys.path.
    spec.loader.exec_module(corpus)
    rows = {}
    observed = Counter()

    class ComparisonCases(corpus.SchemaContractTests):
        def valid(self, packet):
            current_valid = super().valid(packet)
            legacy_valid = previous.is_valid(packet)
            outcome = ('accepted_both' if current_valid and legacy_valid else
                       'rejected_both' if not current_valid and not legacy_valid else
                       'newly_rejected' if not current_valid else 'newly_accepted')
            observed[outcome] += 1
            fingerprint = hashlib.sha256(corpus.canonical(packet)).hexdigest()
            existing = rows.get(fingerprint)
            if existing is None:
                existing = {'input_sha256':fingerprint, 'outcome':outcome, 'test_methods':set(),
                            'changed_paths':changed_paths(self.base, packet)}
                rows[fingerprint] = existing
            elif existing['outcome'] != outcome:
                raise RuntimeError('Identical input produced inconsistent schema outcomes.')
            existing['test_methods'].add(self._testMethodName)
            return current_valid

        @classmethod
        def tearDownClass(cls):
            # Keep structured report stdout separate from unittest diagnostics.
            print(f'SCHEMA_CASES total={cls.evaluations} accepted={cls.accepted} '
                  f'rejected={cls.evaluations-cls.accepted}', file=sys.stderr)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ComparisonCases)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    serialized = []
    for fingerprint in sorted(rows):
        row = rows[fingerprint]
        serialized.append({**row, 'test_methods':sorted(row['test_methods'])})
    unexpected = [row for row in serialized if row['outcome'] == 'newly_accepted'
                  and not set(row['test_methods']).issubset(ALLOWED_WIDENING)]
    after_bindings = [binding(path) for path in source_paths]
    unchanged = before_bindings == after_bindings
    ok = result.wasSuccessful() and result.testsRun == 18 and not unexpected and unchanged
    report = {
        'contract_run_success':ok,
        'operation':'uiowa050-schema-conformance-rookbridge6v2p-20260919',
        'scope':'Legacy-to-current schema behavior on the retained synthetic mutation corpus; not semantic assessor parity.',
        'tests_run':result.testsRun,
        'suite_success':result.wasSuccessful(),
        'evaluation_counts':dict(sorted(observed.items())),
        'distinct_inputs':len(serialized),
        'distinct_outcomes':dict(sorted(Counter(row['outcome'] for row in serialized).items())),
        'allowed_widening_test_methods':sorted(ALLOWED_WIDENING),
        'unexpected_widening':unexpected,
        'source_files_unchanged':unchanged,
        'source_bindings_before':before_bindings,
        'source_bindings_after':after_bindings,
        'changed_inputs':[row for row in serialized if row['outcome'] in ('newly_accepted','newly_rejected')],
    }
    return report, ok

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='New output path; existing files are not overwritten.')
    args = parser.parse_args(argv)
    try:
        report, ok = run_audit()
        content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
        if args.out is None:
            sys.stdout.write(content)
        else:
            # Exclusive creation protects the schema, corpus and retained evidence.
            with args.out.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
        return 0 if ok else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'COMPATIBILITY ERROR: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
