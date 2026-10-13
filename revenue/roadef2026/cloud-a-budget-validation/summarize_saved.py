"""Finish reports from saved outputs; invokes no solver or official checker."""
import argparse
import importlib.util
from pathlib import Path

from run_budget import CASES, digest, read, read_diagnostic, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    output = root / 'execution'
    spec = importlib.util.spec_from_file_location('frozen_compare', args.context / 'compare_checker.py')
    comparator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparator)
    reference = comparator.load_sprint_reference(root / 'loads_vector.csv')
    setup = read(output / 'SETUP.json')
    results = []
    for number in CASES:
        label = 'setA-' + number
        case = output / label
        receipt = read(case / 'solution.json.portfolio.json')
        resources = read(case / 'resources.json')
        if receipt['status'] != 'complete' or resources['returncode'] != 0:
            raise ValueError('Case is incomplete: ' + label)
        six = comparator.load_result(case / 'checker-6.json')
        twelve = read_diagnostic(case / 'checker-12.json', six)
        if not six['valid'] or six['sha256'] != receipt['selected_checker_sha256']:
            raise ValueError('Independent checker mismatch: ' + label)
        if digest(case / 'solution.json') != receipt['solution_sha256']:
            raise ValueError('Solution mismatch: ' + label)
        checks = read(case / 'VERIFIED-CHECKS.json')
        for check, (decimals, parsed) in zip(checks, ((6, six), (12, twelve)), strict=True):
            if (check['returncode'] != 0 or check['decimals'] != decimals
                    or check['sha256'] != parsed['sha256']
                    or digest(case / f'verified-checker-{decimals}.json') != parsed['sha256']):
                raise ValueError('Final recorded checker result mismatch: ' + label)
            check.update(valid=parsed['valid'], load_count=len(parsed['vector']))
        result = {'instance': label, 'status': 'complete',
                  'eligibility': setup['eligibility']['cases'][label],
                  'comparison': comparator.compare_sprint(six, reference, label),
                  'independent_checks': checks, 'resources': resources,
                  'portfolio_receipt': receipt, 'solution_sha256': digest(case / 'solution.json')}
        write(case / 'RESULT.json', result)
        results.append(result)
    write(output / 'RESULT.json', {'cases': results, 'all_complete': True,
          'historical_reference_resource_budgets_matched': False,
          'qualification_rank': 'unknown', 'postprocessor_sha256': digest(Path(__file__)),
          'postprocessing_only': True, 'new_solver_calls': 0, 'new_checker_calls': 0})
    for result in results:
        print(result['instance'], result['comparison'])


if __name__ == '__main__':
    main()
