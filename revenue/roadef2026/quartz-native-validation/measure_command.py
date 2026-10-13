"""Record an existing native command and sampled process-tree resource usage.

The caller supplies the runtime command, including its own timeout policy.
No solver, environment budgets or process limits are changed by this observer.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import time


def read_limit(name):
    try:
        return Path('/sys/fs/cgroup', name).read_text().strip()
    except OSError:
        return None


def tree_rss(pid, parent_pid):
    """Sample reachable child processes; absent/racing proc entries are counted."""
    # This cloud runtime exposes host PID numbers in procfs but returns namespace
    # PID numbers from Popen. Resolve the direct child by BOTH parent and NSpid;
    # the namespace number alone can belong to other concurrent command cells.
    processes = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines())
            processes[int(fields['Pid'])] = {
                'parent': int(fields['PPid']),
                'namespace_pid': int(fields.get('NSpid', fields['Pid']).split()[-1]),
                'rss': int(fields.get('VmRSS', '0').split()[0]),
            }
        except (OSError, ValueError, KeyError):
            continue
    roots = [host_pid for host_pid, values in processes.items()
             if values['parent'] == parent_pid and values['namespace_pid'] == pid]
    if len(roots) != 1:
        return 0, 0, 1
    pending, seen, missing, rss = roots, set(), 0, 0
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        rss += processes[current]['rss']
        pending.extend(host_pid for host_pid, values in processes.items()
                       if values['parent'] == current)
    return rss, len(seen), missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == '--':
        command = command[1:]
    if not command:
        parser.error('supply a command after --')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'command': command, 'cwd': os.getcwd(),
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'platform': platform.platform(), 'cpu_max': read_limit('cpu.max'),
        'memory_max': read_limit('memory.max'),
        'observer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'environment_controls': {key: os.environ.get(key) for key in (
            'PORTFOLIO_SECONDS', 'PORTFOLIO_CHECK_INTERVAL', 'PORTFOLIO_CHECK_TIMEOUT',
            'SEDGE_SECONDS', 'SEDGE_MAX_ROUNDS', 'CLOUD_INITIAL_SOLUTION',
            'FLEET_DIRECTED', 'FLEET_JOINT', 'FLEET_WAYPOINT_LIMIT')},
        'sample_period_seconds': 0.5,
        'wall_observation_resolution_seconds': 0.5,
        'memory_measurement': 'sum of reachable process-tree VmRSS at 0.5s; excludes page cache; not a hard bound',
    }
    start = time.monotonic()
    peak, samples, missing, maximum_processes = 0, 0, 0, 0
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    parent_pid = int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                          if line.startswith('Pid:')))
    with args.output.with_suffix('.stdout').open('wb') as stdout, args.output.with_suffix('.stderr').open('wb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        record['pid'] = process.pid
        while process.poll() is None:
            rss, count, absent = tree_rss(process.pid, parent_pid)
            peak = max(peak, rss)
            maximum_processes = max(maximum_processes, count)
            samples += 1
            missing += absent
            time.sleep(0.5)
        result = process.returncode
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    record.update(returncode=result, wall_seconds=time.monotonic() - start,
                  sampled_peak_tree_rss_kib=peak, samples=samples,
                  missing_or_racing_proc_entries=missing,
                  maximum_observed_processes=maximum_processes,
                  waited_children_user_seconds=after.ru_utime - before.ru_utime,
                  waited_children_system_seconds=after.ru_stime - before.ru_stime,
                  waited_children_maxrss_kib=after.ru_maxrss,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)
    return result if result >= 0 else 128 - result


if __name__ == '__main__':
    raise SystemExit(main())
