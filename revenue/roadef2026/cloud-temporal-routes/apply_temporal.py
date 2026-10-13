#!/usr/bin/env python3
"""Build an additive temporal-neighborhood source from an existing kernel.

Does not edit the parent. The output records the actual input digest. The exact
parent kernel should come from its published archive or Git commit, not prose.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent

def apply(source: str) -> str:
    anchors={
        '#include <algorithm>': '#include "temporal_dp.hpp"\n#include <algorithm>',
        '    void writeSolution() const {': (HERE/'temporal_join.inc').read_text()+'    void writeSolution() const {',
        '    void run() {': '''    void run() {
        const bool dockEnabled=setting("DOCK_TEMPORAL",0)!=0;
        if(dockEnabled && setting("DOCK_TEMPORAL_ONLY",0)!=0) {
            Route nodes(n); std::iota(nodes.begin(),nodes.end(),0);
            for(int d=0;d<static_cast<int>(demands.size()) && !finished();++d) dockTemporal(d,nodes);
            writeSolution(); statistics();
            std::cerr << "DOCK temporal accepted " << dockAccepted << " / " << dockAttempted << '\\n';
            return;
        }''',
        '            if (accepted > oldAccepted) stalled = 0; else ++stalled;': '''            if(dockEnabled && accepted==oldAccepted && !finished() && stalled%4==3) {
                Route nodes(n); std::iota(nodes.begin(),nodes.end(),0);
                // Use the same critical-demand prefix. Bounded candidate menu
                // can also consume multi-waypoint routes from other authors.
                for(int j=0;j<limit && j<4 && !finished();++j)
                    if(dockTemporal(contributing[j].second,nodes)) break;
            }
            if (accepted > oldAccepted) stalled = 0; else ++stalled;'''
    }
    if 'auto contributing = contributors(t, e);' not in source:
        key = '            if (accepted > oldAccepted) stalled = 0; else ++stalled;'
        anchors[key] = anchors[key].replace('contributing[j].second', 'contributors[j].second')
    if 'dockTemporal' in source: raise ValueError('source already contains the temporal join')
    for old,new in anchors.items():
        if source.count(old)!=1: raise ValueError(f'expected one source anchor: {old}')
        source=source.replace(old,new,1)
    return source

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    raw=args.parent.read_bytes()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'main.cpp').write_text(apply(raw.decode('utf-8')))
    shutil.copy2(HERE/'temporal_dp.hpp',args.output/'temporal_dp.hpp')
    manifest={'parent_sha256':hashlib.sha256(raw).hexdigest(),
              'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(args.output.iterdir()) if p.is_file()},
              'mode':'additive generated source; parent unchanged',
              'default':'temporal neighborhood disabled unless DOCK_TEMPORAL=1'}
    (args.output/'SOURCE.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))
if __name__=='__main__':main()
