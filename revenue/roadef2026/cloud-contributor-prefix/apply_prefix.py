#!/usr/bin/env python3
"""Apply only QUAY's contributor-selection delta, preserving other solver edits."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ORIGINAL = '''    std::vector<std::pair<double, int>> contributors(int t, int edge, int excluded = -1) const {
        std::vector<std::pair<double, int>> result;
        for (int d = 0; d < static_cast<int>(demands.size()); ++d) {
            if (d == excluded || demands[d].volume[t] <= 0) continue;
            double value = coefficient(routed[d * h + t], edge) * demands[d].volume[t];
            if (value > 0) result.emplace_back(value, d);
        }
        std::sort(result.begin(), result.end(), [](auto a, auto b) {
            return a.first != b.first ? a.first > b.first : a.second < b.second;
        });
        return result;
    }
'''
REPLACEMENT = '''    std::vector<std::pair<double, int>> contributors(
        int t, int edge, int excluded = -1,
        std::size_t limit = std::numeric_limits<std::size_t>::max()) const {
        std::vector<std::pair<double, int>> result;
        for (int d = 0; d < static_cast<int>(demands.size()); ++d) {
            if (d == excluded || demands[d].volume[t] <= 0) continue;
            double value = coefficient(routed[d * h + t], edge) * demands[d].volume[t];
            if (value > 0) result.emplace_back(value, d);
        }
        auto precedes = [](auto a, auto b) {
            return a.first != b.first ? a.first > b.first : a.second < b.second;
        };
        // Both callers already consume bounded prefixes. Do not order an unused
        // tail; the default still returns the original complete sorted result.
        std::size_t keep = std::min(limit, result.size());
        // Dense prefixes are faster with the existing full sort on small lists.
        if (keep < result.size() / 4) {
            std::partial_sort(result.begin(), result.begin() + keep, result.end(), precedes);
        } else {
            std::sort(result.begin(), result.end(), precedes);
        }
        result.resize(keep);
        return result;
    }
'''
EDITS = (
    (ORIGINAL, REPLACEMENT),
    ('auto secondDemands = contributors(t, edge, d);',
     'auto secondDemands = contributors(t, edge, d, 4);'),
    ('auto contributing = contributors(t, e);',
     'auto contributing = contributors(t, e, -1, 32);'),
)

def apply(text: str) -> str:
    """Apply all three exact edits together, or recognize the complete result."""
    old = [text.count(before) for before, _ in EDITS]
    new = [text.count(after) for _, after in EDITS]
    if old == [0, 0, 0] and new == [1, 1, 1]:
        return text
    if old != [1, 1, 1] or new != [0, 0, 0]:
        raise ValueError(f'Contributor edit mismatch or partial application: old={old}, new={new}')
    for before, after in EDITS:
        text = text.replace(before, after, 1)
    return text

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path, help='new output; source is never overwritten')
    args = parser.parse_args()
    source = args.source.read_bytes()
    result = apply(source.decode('utf-8')).encode('utf-8')
    with args.output.open('xb') as out:
        out.write(result)
    print(json.dumps({'input_sha256': hashlib.sha256(source).hexdigest(),
                      'output_sha256': hashlib.sha256(result).hexdigest(),
                      'bytes': len(result), 'changed': result != source}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
