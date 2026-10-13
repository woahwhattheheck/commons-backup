#!/usr/bin/env python3
"""Add narrowly scoped B05 visit telemetry to exact fleet2885 source."""
from pathlib import Path
import argparse, hashlib

BASE_SHA256='322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1'
TARGET=(654,9,1500,242)

def apply(source: str) -> str:
    replacements=[]
    replacements.append(('''        std::vector<Ranked> ranked;\n        int count = scanLimit > 0 ? std::min(n, scanLimit) : n;\n        int offset = count < n ? static_cast<int>(rng() % n) : 0;\n        for (int k = 0; k < count && !finished() && elapsed() < deadline; ++k) {\n            int w = (k + offset) % n;\n''','''        std::vector<Ranked> ranked;\n        int count = scanLimit > 0 ? std::min(n, scanLimit) : n;\n        int offset = count < n ? static_cast<int>(rng() % n) : 0;\n        int visitScanned = 0;\n        for (int k = 0; k < count && !finished() && elapsed() < deadline; ++k) {\n            int w = (k + offset) % n;\n            ++visitScanned;\n'''))
    replacements.append(('''        for (const auto& item : ranked) candidates.push_back(item.waypoint);\n        return candidates;\n''','''        for (const auto& item : ranked) candidates.push_back(item.waypoint);\n        if (std::getenv("FLEET_VISIT_TRACE") && d == 654 && t == 9 && edge == 1500) {\n            auto found = std::find(candidates.begin(), candidates.end(), 242);\n            std::cerr << "VISIT waypoint_candidates d=654 t=9 e=1500 scanned=" << visitScanned\n                      << " returned=" << candidates.size() << " target_rank="\n                      << (found == candidates.end() ? -1 : static_cast<int>(found - candidates.begin()) + 1)\n                      << " elapsed=" << elapsed() << "\\n";\n        }\n        return candidates;\n'''))
    replacements.append(('''            auto contributing = contributors(t, e);\n            long long oldAccepted = accepted;\n''','''            auto contributing = contributors(t, e);\n            if (std::getenv("FLEET_VISIT_TRACE") && t == 9 && e == 1500) {\n                auto found = std::find_if(contributing.begin(), contributing.end(), [](const auto& x){ return x.second == 654; });\n                std::cerr << "VISIT critical t=9 e=1500 stalled=" << stalled << " contributor_count=" << contributing.size()\n                          << " d654_rank=" << (found == contributing.end() ? -1 : static_cast<int>(found - contributing.begin()) + 1)\n                          << " accepted=" << accepted << " attempted=" << attempted << " elapsed=" << elapsed() << "\\n";\n            }\n            long long oldAccepted = accepted;\n'''))
    replacements.append(('''                    for (int w : candidates) {\n                        if (finished()) break;\n                        if (move(d, left, right, {w})) { improved = true; break; }\n''','''                    for (int w : candidates) {\n                        if (finished()) break;\n                        if (std::getenv("FLEET_VISIT_TRACE") && d == 654 && t == 9 && e == 1500 && w == 242) {\n                            std::cerr << "VISIT target_attempt d=654 t=9 e=1500 w=242 interval=" << left << ":" << right\n                                      << " accepted_before=" << accepted << " attempted_before=" << attempted\n                                      << " elapsed=" << elapsed() << "\\n";\n                        }\n                        if (move(d, left, right, {w})) {\n                            if (std::getenv("FLEET_VISIT_TRACE") && d == 654 && t == 9 && e == 1500 && w == 242)\n                                std::cerr << "VISIT target_accept interval=" << left << ":" << right << " accepted=" << accepted << " elapsed=" << elapsed() << "\\n";\n                            improved = true; break; }\n'''))
    for old,new in replacements:
        if source.count(old)!=1:
            raise ValueError('expected unique source anchor')
        source=source.replace(old,new,1)
    return source

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('source',type=Path); ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); raw=a.source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BASE_SHA256: raise ValueError('expected exact fleet2885 source')
    a.output.write_text(apply(raw.decode()),encoding='utf-8')
if __name__=='__main__': main()
