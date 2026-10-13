# SPDX-License-Identifier: Apache-2.0
"""Require behavioral assertion failures for six deliberately wrong loader repairs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from repair_loader import repair_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    good = repair_source(args.source.read_bytes()).decode()
    seam = '            s.action = action  # Preserve ALL raw rows and the returned object itself.\n'
    mutations = {
        'truncate_ghost_hands': (seam, '''            hands = action.get("hands", [])
            if isinstance(hands, list) and len(hands) > len(s.observation.farms[i]["hands"]):
                action["hands"] = hands[:len(s.observation.farms[i]["hands"])]
''' + seam),
        'compact_empty_market_slots': (seam, '''            market = action.get("market", [])
            if isinstance(market, list) and any(not row for row in market):
                action["market"] = [row for row in market if row]
''' + seam),
        'drop_last_live_market_slot': (seam, '''            market = action.get("market", [])
            if isinstance(market, list) and len(market) > max(0, int(cfg.maxMarketOrdersPerTurn)-1):
                action["market"] = market[:max(0, int(cfg.maxMarketOrdersPerTurn)-1)]
''' + seam),
        'zero_cap_means_no_market': (seam, '''            if cfg.maxMarketOrdersPerTurn <= 0:
                action["market"] = []
''' + seam),
        'hide_surplus_hand_telemetry': ('    contract["extra_hand_rows"] += extra\n', '    contract["extra_hand_rows"] += 0\n'),
        'pad_missing_real_hands': (seam, '''            hands = action.get("hands", [])
            if isinstance(hands, list) and len(hands) < len(s.observation.farms[i]["hands"]):
                action["hands"] = hands + [["PASS"] for _ in range(max(0, len(s.observation.farms[i]["hands"])-len(hands)))]
''' + seam),
    }
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    with tempfile.TemporaryDirectory(prefix='titan-raw-mutants-') as tmp:
        for optimized in (False, True):
            for name, (old, new) in mutations.items():
                if good.count(old) != 1:
                    raise ValueError(f'Ambiguous mutant seam: {name}')
                source = good.replace(old, new, 1)
                candidate = Path(tmp)/(name+'.py')
                candidate.write_text(source)
                report_path = args.output/f'{name}-O{int(optimized)}.json'
                command = [sys.executable] + (['-O'] if optimized else []) + [
                    str(Path(__file__).with_name('test_loader_contract.py')),
                    '--source', str(args.source), '--engine', str(args.engine),
                    '--candidate', str(candidate), '--report', str(report_path)]
                done = subprocess.run(command, text=True, capture_output=True, timeout=30)
                (args.output/f'{name}-O{int(optimized)}.log').write_text(done.stdout+done.stderr)
                result = json.loads(report_path.read_text())
                killed = done.returncode == 1 and result['tests'] == 28 and result['failures'] > 0
                rows.append({'name': name, 'optimization': int(optimized), 'assertion_killed': killed, **result})
                print(name, int(optimized), 'KILLED' if killed else 'SURVIVED_OR_ERROR_ONLY',
                      result['failures'], 'assertion failures', result['errors'], 'errors', flush=True)
    report = {'mutants': rows, 'all_assertion_killed': all(r['assertion_killed'] for r in rows)}
    (args.output/'SUMMARY.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['all_assertion_killed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
