#!/usr/bin/env python3
"""Apply the measured ROADEF routeFlow experiment to a detached source copy.

Only the exact original method is replaced. Disjoint changes elsewhere survive.
This does not change a canonical solver, submission, or runtime by itself.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

ORIGINAL = b'    bool routeFlow(int d, int t, const Route& route, Sparse& flow) {\n        flow.clear();\n        int from = demands[d].from;\n        for (std::size_t k = 0; k <= route.size(); ++k) {\n            int to = k == route.size() ? demands[d].to : route[k];\n            const auto& part = segment(t, from, to);\n            if (!part.empty() && part.front().first == -1) return false;\n            flow.insert(flow.end(), part.begin(), part.end());\n            from = to;\n        }\n        std::sort(flow.begin(), flow.end());\n        std::size_t out = 0;\n        for (auto item : flow) {\n            if (out && flow[out - 1].first == item.first) flow[out - 1].second += item.second;\n            else flow[out++] = item;\n        }\n        flow.resize(out);\n        return true;\n    }\n'
CANDIDATE = b'    bool routeFlow(int d, int t, const Route& route, Sparse& flow) {\n        flow.clear();\n        int from = demands[d].from;\n        std::size_t split = 0;\n        for (std::size_t k = 0; k <= route.size(); ++k) {\n            int to = k == route.size() ? demands[d].to : route[k];\n            const auto& part = segment(t, from, to);\n            if (!part.empty() && part.front().first == -1) return false;\n            split = flow.size();\n            flow.insert(flow.end(), part.begin(), part.end());\n            from = to;\n        }\n        // A segment is already sorted and contains each directed edge once.\n        if (route.empty()) return true;\n        // For two sorted legs, preserve exactly the same (edge, ratio) order\n        // with a linear merge. Keep short and multi-waypoint routes on the\n        // original sort path; small sorts avoid the merge-buffer overhead.\n        if (route.size() == 1 && flow.size() > 32)\n            std::inplace_merge(flow.begin(), flow.begin() + split, flow.end());\n        else\n            std::sort(flow.begin(), flow.end());\n        std::size_t out = 0;\n        for (auto item : flow) {\n            if (out && flow[out - 1].first == item.first) flow[out - 1].second += item.second;\n            else flow[out++] = item;\n        }\n        flow.resize(out);\n        return true;\n    }\n'


def apply_bytes(source: bytes) -> bytes:
    """Return an exact one-method derivative, preserving all other bytes."""
    if source.count(ORIGINAL) != 1:
        raise ValueError("source must contain exactly one original routeFlow method")
    return source.replace(ORIGINAL, CANDIDATE, 1)


def write_new(path: Path, data: bytes) -> None:
    """Atomically create a new file without replacing any existing path."""
    handle, temporary = tempfile.mkstemp(prefix=".route-flow-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="existing fleet main.cpp")
    parser.add_argument("output", type=Path, help="new detached main.cpp path")
    args = parser.parse_args()
    try:
        source = args.source.read_bytes()
        candidate = apply_bytes(source)
        write_new(args.output, candidate)
    except (OSError, ValueError) as error:
        parser.exit(2, f"route-flow: {error}\n")
    print(json.dumps({"source_sha256": hashlib.sha256(source).hexdigest(),
                      "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                      "method_sha256": hashlib.sha256(CANDIDATE).hexdigest(),
                      "output": str(args.output), "default_changed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
