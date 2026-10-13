#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate one opt-in derived solver from an exact existing fleet source.

No source retrieval, compiler, benchmark, submission, or default portfolio write.
The original strict moveTogether remains byte-identical. The output directory
contains generated main.cpp and the one header, with exact identities.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_BLOB = "9354ec61fc32bb7ebbdaaa4a9bff7c7780a7e1df"
MEMBER = r'''
    // DATE neutral operator: normalized unit flow is unchanged at every slot.
    // Load/routed arrays stay byte-identical; only route encoding and used change.
    bool budgetReleaseEnabled = setting("FLEET_BUDGET_RELEASE", 1) != 0;
    long long budgetReleaseAccepted = 0, budgetReleaseProposals = 0;
    long long budgetReleaseFlowChecks = 0;
    bool releaseBudget() {
        if (!budgetReleaseEnabled || finished()) return false;
        budget_release::Counters counts;
        auto proposal = budget_release::find_release(routes, routed, h, used,
            [this](int d, int t, const Route& next, Sparse& flow) {
                return routeFlow(d, t, next, flow);
            },
            [this](int d, const Route& a, const Route& b) { return distance(d, a, b); },
            [this] { return finished(); }, counts,
            static_cast<std::size_t>(std::min(setting("FLEET_BUDGET_RELEASE_LIMIT", 4096), 1000000.0)));
        budgetReleaseProposals += counts.proposals;
        budgetReleaseFlowChecks += counts.flow_checks;
        if (!proposal) return false;
        // Allocate the complete replacement before any live route is changed.
        std::vector<Route> staged(proposal->right - proposal->left + 1, proposal->next);
        if (finished()) return false;
        for (int t = proposal->left; t <= proposal->right; ++t)
            routes[proposal->demand * h + t].swap(staged[t - proposal->left]);
        used.swap(proposal->used_after);
        ++budgetReleaseAccepted;
        return true;
    }
'''

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one compatible source seam: {old[:80]!r}")
    return source.replace(old, new, 1)

def derive(source: bytes, expected: str = SOURCE_BLOB) -> bytes:
    if git_blob(source) != expected:
        raise ValueError("Source differs from explicit expected Git blob")
    text = source.decode("utf-8")
    text = replace_once(text, '#include "rapidjson/istreamwrapper.h"',
                        '#include "rapidjson/istreamwrapper.h"\n#include "budget_release.hpp"')
    anchor = '    struct Change { int d, left, right; Route next; };'
    text = replace_once(text, anchor, anchor + '\n' + MEMBER)
    text = replace_once(text, '    void run() {\n        int stalled = 0;', '''    void run() {
        int stalled = 0;
        // Finite preparatory pass over a resumed encoding, before primary search.
        for (int pass = 0; pass < 16 && !finished(); ++pass)
            if (!releaseBudget()) break;''')
    text = replace_once(text,
        '            if (accepted == oldAccepted && !finished() && stalled % 4 == 3)\n                eject(t, e, contributing, adaptive);\n            if (accepted > oldAccepted) stalled = 0; else ++stalled;',
        '''            bool budgetChanged = accepted == oldAccepted && !finished()
                && stalled % 4 == 3 && releaseBudget();
            if (!budgetChanged && accepted == oldAccepted && !finished() && stalled % 4 == 3)
                eject(t, e, contributing, adaptive);
            if (accepted > oldAccepted || budgetChanged) stalled = 0; else ++stalled;''')
    anchor = '            << ",\\\"accepted\\\":" << accepted'
    text = replace_once(text, anchor,
        '            << ",\\\"budget_release_accepted\\\":" << budgetReleaseAccepted\n'
        '            << ",\\\"budget_release_proposals\\\":" << budgetReleaseProposals\n'
        '            << ",\\\"budget_release_flow_checks\\\":" << budgetReleaseFlowChecks\n' + anchor)
    return text.encode("utf-8")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-source-blob", default=SOURCE_BLOB)
    a = p.parse_args()
    raw = a.source.read_bytes()
    result = derive(raw, a.expected_source_blob)
    header = Path(__file__).with_name("budget_release.hpp").read_bytes()
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / "main.cpp").write_bytes(result)
    (a.output / "budget_release.hpp").write_bytes(header)
    manifest = {"source_git_blob": git_blob(raw), "source_sha256": hashlib.sha256(raw).hexdigest(),
                "files": {name: {"bytes":len(value), "sha256":hashlib.sha256(value).hexdigest()}
                          for name,value in (("main.cpp",result),("budget_release.hpp",header))},
                "primary_acceptance": "unchanged", "default_portfolio_modified": False}
    (a.output / "SOURCE.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps(manifest))

if __name__ == "__main__":
    main()
