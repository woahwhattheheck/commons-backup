"""Profile archived TITAN on retained observations, without advancing a game."""
from __future__ import annotations
import argparse, cProfile, gzip, hashlib, importlib.util, io, json, pstats, sys, time
from pathlib import Path


def retained_calls(path: Path, seat: int):
    observations, actions = {}, {}
    with gzip.open(path, 'rt') as handle:
        for line in handle:
            row = json.loads(line)
            if row['kind'] == 'state' and row['index'] < 719:
                obs = row['state'][seat]['observation']
                obs['step'] = row['index']
                observations[row['index']] = obs
            elif row['kind'] == 'call' and row['seat'] == seat:
                actions[row['step']] = row['response']['action']
    if set(observations) != set(range(719)) or set(actions) != set(range(719)):
        raise ValueError('Incomplete retained input/action stream')
    return [(observations[i], actions[i]) for i in range(719)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    rows = retained_calls(args.trace, args.seat)
    specification = json.loads((args.root/'checks/reference/engine/kaggriculture.json').read_text())
    cfg = {key: value.get('default') if isinstance(value, dict) else value
           for key, value in specification['configuration'].items()}
    # Replay metadata is not supplied to the agent.
    cfg['seed'] = None
    sys.path.insert(0, str(args.root.resolve()))
    spec = importlib.util.spec_from_file_location('swift_candidate_main', args.root/'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profiler = cProfile.Profile()
    timings, mismatches, statuses, actual = [], [], {}, []
    before = time.perf_counter()
    if args.profile: profiler.enable()
    for step, (obs, expected) in enumerate(rows):
        call_start = time.perf_counter()
        action = module.agent(obs, cfg)
        timings.append(time.perf_counter() - call_start)
        actual.append(action)
        if action != expected: mismatches.append(step)
        status = module._INSTANCE.diagnostics.get('status', 'unknown')
        statuses[status] = statuses.get(status, 0) + 1
    if args.profile: profiler.disable()
    elapsed = time.perf_counter() - before
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'mode': 'retained_observation_inference_only', 'new_games': 0,
              'profiled': args.profile,
              'runtime_sha256': hashlib.sha256((args.root/'titan_runtime.py').read_bytes()).hexdigest(),
              'config_sha256': hashlib.sha256((args.root/'TITAN-CONFIG.json').read_bytes()).hexdigest(),
              'calls': len(rows), 'seat': args.seat, 'elapsed_seconds': elapsed,
              'action_mismatch_steps': mismatches, 'statuses': statuses,
              'timings_seconds': timings,
              'action_sha256': hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
              'trace_sha256': hashlib.sha256(args.trace.read_bytes()).hexdigest(),
              'root': str(args.root.resolve())}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'timings_seconds'}, indent=2))
    if args.profile:
        profiler.dump_stats(str(args.output.with_suffix('.pstats')))
        buf = io.StringIO()
        pstats.Stats(profiler, stream=buf).strip_dirs().sort_stats('cumulative').print_stats(40)
        args.output.with_suffix('.profile.txt').write_text(buf.getvalue())
        print(buf.getvalue())
    raise SystemExit(1 if mismatches else 0)

if __name__ == '__main__': main()
