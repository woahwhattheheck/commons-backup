#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the existing, named clock/recovery/worker cases with core reuse active."""
import argparse,json,sys,time,unittest
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();sys.path[:0]=[str(a.runtime.resolve()),str((a.runtime/'checks').resolve())]
    import scheduler,selected_sell_core
    scheduler.MarketPath.score=selected_sell_core.MarketPath.score
    names=['test_entrypoint_clock.EntryClock','test_module_recovery.ModuleRecovery',
           'test_route_recovery.RouteRecovery','test_worker_deadline.WorkerDeadline']
    started=time.perf_counter();suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    binding_preserved=scheduler.MarketPath.score is selected_sell_core.MarketPath.score
    report={'successful':result.wasSuccessful() and binding_preserved,'binding_preserved_after_suite':binding_preserved,'tests':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skips':len(result.skipped),'named_test_classes':names,
            'elapsed_seconds':time.perf_counter()-started,'score_source':'selected_sell_core.MarketPath.score',
            'new_full_games':0}
    a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    raise SystemExit(0 if report['successful'] else 1)
if __name__=='__main__':main()
