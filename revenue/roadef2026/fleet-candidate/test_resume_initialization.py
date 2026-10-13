"""Cloud-only fixed-work comparison of the current solver and its parent.

Synthetic inputs only. This checks output compatibility and eliminated route
initialization calls; it does not measure competition quality or wall-time gains.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import unittest

OPTIONS = None
RECORDS = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(seed=0):
    rng = random.Random(seed)
    nodes = list(range(6))
    links = []
    for u in nodes:
        for v in nodes:
            if u != v:
                links.append(dict(id=len(links), **{'from': u, 'to': v},
                                  metric=1 + rng.randrange(3), capacity=10 + rng.randrange(40)))
    net = dict(nodes=[dict(id=n) for n in nodes], links=links)
    tm = dict(num_time_slots=4, demands=[dict(s=d, t=(d+3) % 6,
              v=[5+rng.randrange(40) for _ in range(4)]) for d in range(4)])
    scenario = dict(max_segments=3, budget=[dict(t=t, value=40) for t in range(4)],
                    interventions=[dict(t=1, links=[0]), dict(t=3, links=[0])])
    # Omitted demand/time cells are deliberately default routes.
    incumbent = dict(srpaths=[dict(d=0, t=1, w=[1]), dict(d=1, t=2, w=[2, 3])])
    return net, tm, scenario, incumbent


class ResumeInitializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='roadef-resume-check-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.binaries = {}
        for label, source_path in (('parent', OPTIONS.parent), ('candidate', OPTIONS.candidate)):
            source = source_path.read_text(encoding='utf-8')
            for instrument in (False, True):
                code = source
                suffix = '-counted' if instrument else ''
                if instrument:
                    signature = 'bool routeFlow(int d, int t, const Route& route, Sparse& flow) {'
                    invocation = 'Solver solver(argv[1], argv[2], argv[3], argv[4]); solver.run();'
                    if code.count(signature) != 1 or code.count(invocation) != 1:
                        raise AssertionError('Native instrumentation context changed; inspect before testing')
                    code = 'static unsigned long long recovery_route_calls = 0;\n' + code
                    code = code.replace(signature, signature+'\n        ++recovery_route_calls;')
                    code = code.replace(invocation, invocation +
                        '\n        std::cerr << "RECOVERY_ROUTE_CALLS=" << recovery_route_calls << "\\n";')
                staged = cls.root/(label+suffix+'.cpp')
                binary = cls.root/(label+suffix)
                staged.write_text(code, encoding='utf-8')
                built = subprocess.run(['g++', '-std=c++20', '-O2', '-DNDEBUG', str(staged), '-o', str(binary)],
                                       capture_output=True, text=True, timeout=120)
                if built.returncode:
                    raise AssertionError(built.stderr)
                cls.binaries[label+suffix] = binary

    def run_case(self, label, data, rounds=0, resume=True, in_place=False, raw=None):
        case = Path(tempfile.mkdtemp(prefix=label+'-', dir=self.root))
        net, tm, scenario, incumbent = copy.deepcopy(data)
        for name, value in (('net', net), ('tm', tm), ('scenario', scenario)):
            (case/(name+'.json')).write_text(json.dumps(value), encoding='utf-8')
        initial = case/'initial.json'
        initial_bytes = raw if raw is not None else json.dumps(incumbent).encode()
        initial.write_bytes(initial_bytes)
        output = initial if in_place else case/'solution.json'
        stats = case/'stats.json'
        env = {k:v for k,v in os.environ.items() if not k.startswith(('SEDGE_', 'FLEET_', 'CLOUD_INITIAL_'))}
        env.update(SEDGE_SECONDS='3600', SEDGE_MAX_ROUNDS=str(rounds), SEDGE_STATS=str(stats))
        if resume:
            env['CLOUD_INITIAL_SOLUTION'] = str(initial)
        process = subprocess.run([str(self.binaries[label]), str(case/'net.json'), str(case/'tm.json'),
                                  str(case/'scenario.json'), str(output)], env=env,
                                 capture_output=True, text=True, timeout=30)
        statistics = json.loads(stats.read_text()) if stats.exists() else None
        if statistics is not None:
            statistics.pop('seconds')
        count = re.search(r'RECOVERY_ROUTE_CALLS=(\d+)', process.stderr)
        result = dict(exit=process.returncode, stderr=process.stderr,
                      solution=output.read_bytes() if output.exists() else None,
                      statistics=statistics, initial=initial.read_bytes(),
                      route_calls=int(count[1]) if count else None)
        RECORDS.append(dict(label=label, rounds=rounds, resume=resume, in_place=in_place,
                            exit=result['exit'], route_calls=result['route_calls'],
                            solution_sha256=hashlib.sha256(result['solution']).hexdigest()
                              if result['solution'] is not None else None))
        return result

    def pair(self, data, **kwargs):
        a = self.run_case('parent', data, **kwargs)
        b = self.run_case('candidate', data, **kwargs)
        self.assertEqual(a['exit'], 0, a['stderr'])
        self.assertEqual(b['exit'], 0, b['stderr'])
        self.assertEqual(a['solution'], b['solution'])
        self.assertEqual(a['statistics'], b['statistics'])
        self.assertEqual(b['statistics']['resumed'], kwargs.get('resume', True))
        return a, b

    def test_fixed_work_outputs_and_statistics(self):
        for seed in range(3):
            for resumed, rounds_list in ((True, (0, 1, 5, 20, 128)), (False, (0, 5, 128))):
                for rounds in rounds_list:
                    with self.subTest(seed=seed, resumed=resumed, rounds=rounds):
                        self.pair(fixture(seed), rounds=rounds, resume=resumed)

    def test_same_file_resume_and_omitted_default_routes(self):
        data = fixture()
        for rounds in (0, 5):
            self.pair(data, rounds=rounds, in_place=True)
        data[3]['srpaths'] = []
        a, b = self.pair(data)
        self.assertEqual(json.loads(b['solution']), {'srpaths': []})
        self.assertGreater(b['statistics']['initial_mlu'], 0)

    def test_invalid_incumbents_preserve_input_and_diagnostic(self):
        cases = [
            (b'{', 'Invalid JSON'),
            (b'[]', 'Invalid JSON'),
            (b'{}', 'Initial solution has no srpaths array'),
            (b'{"srpaths":[{"d":"0","t":0,"w":[]}]}', 'Malformed initial route'),
            (b'{"srpaths":[{"d":99,"t":0,"w":[]}]}', 'Invalid or duplicate initial route index'),
            (b'{"srpaths":[{"d":0,"t":0,"w":[]},{"d":0,"t":0,"w":[]}]}',
             'Invalid or duplicate initial route index'),
            (b'{"srpaths":[{"d":0,"t":0,"w":[99]}]}', 'Unknown initial waypoint'),
            (b'{"srpaths":[{"d":0,"t":0,"w":[1,2,4]}]}', 'Initial route exceeds segment limit'),
            (b'{"srpaths":[{"d":0,"t":0,"w":[0]}]}', 'Initial route repeats an endpoint or waypoint'),
            (b'{"srpaths":[{"d":0,"t":0,"w":[1,1]}]}', 'Initial route repeats an endpoint or waypoint'),
        ]
        for raw, message in cases:
            for label in ('parent', 'candidate'):
                with self.subTest(raw=raw, label=label):
                    result = self.run_case(label, fixture(), raw=raw, in_place=True)
                    self.assertEqual(result['exit'], 1)
                    self.assertIn(message, result['stderr'])
                    self.assertEqual(result['initial'], raw)
                    self.assertIsNone(result['statistics'])

    def test_transition_budget_is_still_enforced(self):
        data = fixture()
        data[2]['budget'] = [dict(t=t, value=0) for t in range(4)]
        for label in ('parent', 'candidate'):
            result = self.run_case(label, data, in_place=True)
            self.assertEqual(result['exit'], 1)
            self.assertIn('Initial route exceeds transition budget', result['stderr'])
            self.assertEqual(json.loads(result['initial']), data[3])

    def test_cold_start_publishes_checkpoint_before_unreachable_failure(self):
        data = fixture()
        data[2]['interventions'] = [dict(t=0, links=[e['id'] for e in data[0]['links']])]
        for label in ('parent', 'candidate'):
            result = self.run_case(label, data, resume=False)
            self.assertEqual(result['exit'], 1)
            self.assertIn('A demand is unreachable', result['stderr'])
            self.assertEqual(json.loads(result['solution']), {'srpaths': []})

    def test_one_route_bank_on_resume_with_cold_control(self):
        data = fixture()
        cells = len(data[1]['demands']) * data[1]['num_time_slots']
        for resumed in (False, True):
            parent = self.run_case('parent-counted', data, resume=resumed)
            candidate = self.run_case('candidate-counted', data, resume=resumed)
            self.assertEqual(parent['exit'], 0, parent['stderr'])
            self.assertEqual(candidate['exit'], 0, candidate['stderr'])
            # Future source changes may start from the already optimized parent.
            self.assertIn(parent['route_calls'], (cells, 2*cells) if resumed else (cells,))
            self.assertEqual(candidate['route_calls'], cells)
            self.assertEqual(parent['solution'], candidate['solution'])
            self.assertEqual(parent['statistics'], candidate['statistics'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    OPTIONS = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ResumeInitializationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(schema='roadef-resume-initialization-recovery-v1',
                  parent_sha256=digest(OPTIONS.parent), candidate_sha256=digest(OPTIONS.candidate),
                  tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skipped=len(result.skipped), successful=result.wasSuccessful(), records=RECORDS,
                  scope='Synthetic compatibility and route-call counts; no official score or timing claim.')
    OPTIONS.output.parent.mkdir(parents=True, exist_ok=True)
    OPTIONS.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
