#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run deliberate edge-frontier faults against the retained native tests.

Four isolated generated-source copies only; production source is never changed.
Uses an existing compiler, parent and official checker; no download or service.
"""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent

def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-source',type=Path,required=True)
    parser.add_argument('--parent-binary',type=Path,required=True)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--vendor',type=Path,required=True)
    parser.add_argument('--pair-component',type=Path,default=HERE.parent)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compiler',default='g++')
    parser.add_argument('--only',choices=('inactive_frontier','omitted_middle','omitted_prefix','omitted_suffix'))
    a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    tests=load(HERE/'check_edge_seeded.py','edge_controls_tests')
    original=tests.BUILD.generate(a.parent_source.read_bytes(),HERE).decode('utf-8')
    cases=[
        ('inactive_frontier','if (!cedarEdgeSeeds || cedarSeedArcLimit == 0) return false;',
         'if (true) return false;', ['test_03_default_width_miss_becomes_native_gain']),
        ('omitted_middle','if (!avoids(first, second) || expired()) continue;',
         'if (expired()) continue;', ['test_08_input_arc_is_not_forced_shortest_path',
                                      'test_09_middle_ecmp_exposure_is_not_rounded_to_zero']),
        ('omitted_prefix','if (!prefixes[first] || expired()) continue;',
         'if (expired()) continue;', ['test_10_prefix_ecmp_exposure_is_not_ignored']),
        ('omitted_suffix','if (!suffixes[second] || expired()) continue;',
         'if (expired()) continue;', ['test_11_suffix_ecmp_exposure_is_not_ignored']),
    ]
    rows=[]
    for name,old,new,methods in cases:
        if a.only is not None and a.only != name:continue
        if original.count(old)!=1:raise ValueError('Expected exactly one fault anchor: '+name)
        folder=a.output/name;folder.mkdir()
        src=folder/'fault.cpp';src.write_text(original.replace(old,new,1),encoding='utf-8')
        binary=folder/'fault'
        with (folder/'compile.log').open('w') as log:
            result=subprocess.run([a.compiler,'-O3','-std=c++20','-DNDEBUG','-I'+str(a.vendor),str(src),'-o',str(binary)],stdout=log,stderr=subprocess.STDOUT,timeout=40)
        if result.returncode:raise RuntimeError('Compile failed for '+name)
        tests.RECORDS=[]
        tests.ARGS=SimpleNamespace(output=folder,parent_source=a.parent_source,parent_binary=a.parent_binary,
                                   candidate_binary=binary,checker=a.checker,pair_component=a.pair_component)
        tests.FIXTURE=load(a.pair_component/'check_native.py','original_pair_fixture_'+name)
        suite=unittest.TestSuite(tests.EdgeSeedTests(method) for method in methods)
        log=io.StringIO();outcome=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        (folder/'tests.log').write_text(log.getvalue(),encoding='utf-8')
        row={'name':name,'methods':methods,'tests':outcome.testsRun,'failures':len(outcome.failures),
             'errors':len(outcome.errors),'official_checker_calls':len(tests.RECORDS),
             'detected':len(outcome.failures)==len(methods) and not outcome.errors,
             'fault_source_sha256':tests.sha(src),'fault_binary_sha256':tests.sha(binary),
             'records':tests.RECORDS}
        rows.append(row)
        (a.output/'summary.json').write_text(json.dumps({'controls':rows,'all_detected':all(r['detected'] for r in rows),
            'checker_sha256':tests.sha(a.checker),'parent_source_sha256':tests.sha(a.parent_source),
            'public_instances':0,'scope':'Deliberate faults; failing assertions are the expected negative result.'},indent=2,sort_keys=True)+'\n')
        print(name,'detected',row['detected'],'failures',row['failures'],'errors',row['errors'],'checker calls',row['official_checker_calls'],flush=True)
        if not row['detected']:raise AssertionError(log.getvalue())

if __name__=='__main__':main()
