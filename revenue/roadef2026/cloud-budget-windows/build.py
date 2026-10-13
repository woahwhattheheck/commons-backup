#!/usr/bin/env python3
"""Build a distinct budget-window continuation from the preserved FLORA source ZIP.

No downloads or changes to the parent source. The exact derivative source and
licenses are retained under build/ for reproduction and later packaging.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

PARENT_BLOB = '944608368469a84358b3d0e958de32a90678d110'
METHOD = r'''
    bool propose(int d, int left, int right, int focus, const Route& next) {
        bool budgetBlocked = false;
        if (move(d, left, right, next, &budgetBlocked)) return true;
        // Evaluate the complementary neighborhood once per single-slot proposal,
        // not repeatedly for each old radius/prefix/suffix interval.
        if (!budgetBlocked || windowBoundaries == 0 || h < 2 || left != focus || right != focus || finished())
            return false;
        if (next.size() + 1 > static_cast<std::size_t>(maxSegments)) return false;
        std::set<int> nodes(next.begin(), next.end());
        if (nodes.size() != next.size() || nodes.count(demands[d].from) || nodes.count(demands[d].to))
            return false;
        // Cheap discriminating check: do not scan multi-slot windows unless
        // this route strictly improves the affected sorted loads at the focus.
        // This is proposal pruning only; move() still checks the whole window.
        Sparse focusFlow;
        if (!routeFlow(d, focus, next, focusFlow)) return false;
        if (++generation == 0) { std::fill(marked.begin(), marked.end(), 0); ++generation; }
        std::vector<int> touched;
        auto add = [&](int e, double value) {
            int i = focus*m+e;
            if (marked[i] != generation) {
                marked[i] = generation; delta[i] = 0; touched.push_back(i);
            }
            delta[i] += value;
        };
        double volume = demands[d].volume[focus];
        for (auto [e, ratio] : routed[d*h+focus]) add(e, -volume*ratio);
        for (auto [e, ratio] : focusFlow) add(e, volume*ratio);
        std::vector<long long> before, after;
        for (int i : touched) {
            if (std::abs(delta[i]) <= 1e-12) continue;
            before.push_back(static_cast<long long>(std::floor(std::max(0.0, loads[i]-1e-10)*1e6)));
            after.push_back(static_cast<long long>(std::floor(std::max(0.0, loads[i]+delta[i]+1e-10)*1e6)));
        }
        std::sort(before.begin(), before.end(), std::greater<long long>());
        std::sort(after.begin(), after.end(), std::greater<long long>());
        if (!(after < before)) return false;
        auto leftOK = [&](int l) {
            if (l == 0) return true;
            return used[l] - distance(d, routes[d*h+l-1], routes[d*h+l])
                 + distance(d, routes[d*h+l-1], next) <= budget[l];
        };
        auto rightOK = [&](int r) {
            if (r == h-1) return true;
            return used[r+1] - distance(d, routes[d*h+r], routes[d*h+r+1])
                 + distance(d, next, routes[d*h+r+1]) <= budget[r+1];
        };
        for (auto [l, r] : budget_windows::nearest(h, focus, windowBoundaries, leftOK, rightOK)) {
            if (finished()) break;
            if (l == focus && r == focus) continue;
            // These exact intervals already belong to the parent neighborhood.
            if ((l == 0 && r == h-1) || (l == 0 && r == focus) || (l == focus && r == h-1)) continue;
            bool symmetric = false;
            for (int radius : {1, 2, 3})
                symmetric |= l == std::max(0, focus-radius) && r == std::min(h-1, focus+radius);
            if (symmetric) continue;
            ++windowAttempts;
            // Reuse the unchanged parent routine: full reachability, transition
            // budget and conservative six-decimal sorted-load acceptance.
            if (move(d, l, r, next)) {
                ++windowAccepted;
                lastWindowDemand = d; lastWindowLeft = l; lastWindowRight = r;
                return true;
            }
        }
        return false;
    }

'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def transform(data: bytes) -> bytes:
    if git_blob(data) != PARENT_BLOB:
        raise ValueError('parent source differs from the preserved FLORA baseline')
    text = data.decode('utf-8')
    old_signature = 'bool move(int d, int left, int right, const Route& next) {'
    assert text.count(old_signature) == 1
    text = text.replace(old_signature, old_signature.replace('next)', 'next, bool* budgetBlocked = nullptr)'), 1)
    old_budget = 'if (value > budget[t]) return false;'
    assert text.count(old_budget) == 1
    text = text.replace(old_budget, 'if (value > budget[t]) { if (budgetBlocked) *budgetBlocked = true; return false; }', 1)
    text = text.replace('#include "rapidjson/document.h"', '#include "budget_windows.hpp"\n#include "rapidjson/document.h"', 1)
    needle = '    bool resumed = false;'
    assert text.count(needle) == 1
    text = text.replace(needle, needle + '''
    int windowBoundaries = static_cast<int>(std::min(setting("CLOUD_WINDOW_BOUNDARIES", 4), 16.0));
    long long windowAttempts = 0, windowAccepted = 0;
    int lastWindowDemand = -1, lastWindowLeft = -1, lastWindowRight = -1;''', 1)
    assert text.count('    void writeSolution() const {') == 1
    text = text.replace('    void writeSolution() const {', METHOD + '    void writeSolution() const {', 1)
    needle = '            << ",\\\"attempted\\\":" << attempted'
    assert text.count(needle) == 1
    text = text.replace(needle, '''            << ",\\\"window_attempts\\\":" << windowAttempts
            << ",\\\"window_accepted\\\":" << windowAccepted
            << ",\\\"window_last_demand\\\":" << lastWindowDemand
            << ",\\\"window_last_left\\\":" << lastWindowLeft
            << ",\\\"window_last_right\\\":" << lastWindowRight
''' + needle, 1)
    # Parent run() contains five direct calls; retain their order and candidates.
    beginning, run = text.split('    void run() {', 1)
    assert run.count('move(d, left, right, ') == 5
    run = run.replace('move(d, left, right, ', 'propose(d, left, right, t, ')
    return (beginning + '    void run() {' + run).encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument('--parent', type=Path, default=here.parent/'cloud-optimizer/source.zip')
    parser.add_argument('--output', type=Path, default=here/'build')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.parent) as archive:
        source = archive.read('cloud-optimizer/main.cpp')
        result = transform(source)
        # Copy only the required source dependency and its existing notices.
        prefix = 'cloud-optimizer/'
        for item in archive.infolist():
            relative = Path(item.filename.removeprefix(prefix))
            if not item.filename.startswith(prefix) or item.is_dir():
                continue
            if relative.parts and relative.parts[0] == 'vendor' or relative.as_posix() == 'LICENSE':
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('invalid parent archive path')
                target = output/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
    (output/'main.cpp').write_bytes(result)
    shutil.copyfile(here/'budget_windows.hpp', output/'budget_windows.hpp')
    print('parent', PARENT_BLOB, 'derivative', git_blob(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
