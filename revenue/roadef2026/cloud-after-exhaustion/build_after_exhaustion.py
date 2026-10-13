#!/usr/bin/env python3
"""Prepare an opt-in natural-exhaustion integration; no build or network access."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f"
PRISM_COMMIT = "73a805e290cee36981917ac09e7ce2133f35afd7"
PRISM_PATH = "revenue/roadef2026/cloud-a-rank1/build_rank1_candidate.py"
PRISM_BLOB_SHA1 = "96d457207f1e3a63e8932a20dce8be63e4f87a1d"
PRISM_OUTPUT_SHA256 = "038cffc7121f6447423d231c473af1f49e6f75d4d315bdc5c7fc2b2391f94306"
RUN_ANCHOR = "\n    void run() {\n"
MAIN = "    try { Solver solver(argv[1], argv[2], argv[3], argv[4]); solver.run(); }\n"
PRISM_MAIN = (
    "    try { Solver solver(argv[1], argv[2], argv[3], argv[4]); "
    'if (setting("FLEET_RANK1", 0) != 0) solver.rankOne(); else solver.run(); }\n'
)
ATTRIBUTION = (
    "    // PRISM rankOne() body reused verbatim from commons PR10430,\n"
    "    // merged 73a805e290cee36981917ac09e7ce2133f35afd7 (cloud-a-rank1).\n"
    "    // Natural-exhaustion dispatch below is a separate opt-in integration.\n"
)
GLUE = r'''
    void polishAfterExhaustion(bool naturallyExhausted) {
        if (setting("FLEET_POLISH_AFTER_EXHAUSTION", 0) == 0) return;
        const double phaseStart = elapsed();
        const char* reason = interrupted ? "signal" : phaseStart >= seconds ? "deadline"
            : naturallyExhausted ? nullptr : "round_limit";
        if (reason) {
            std::cerr << "FLEET_POLISH {\"event\":\"skipped\",\"reason\":\"" << reason
                      << "\",\"elapsed\":" << phaseStart << ",\"remaining\":"
                      << std::max(0.0, seconds - phaseStart) << "}\n";
            return;
        }
        const long long attemptsBefore = attempted, acceptedBefore = accepted;
        std::cerr << "FLEET_POLISH {\"event\":\"begin\",\"reason\":\"natural_exhaustion\","
                  << "\"elapsed\":" << phaseStart << ",\"remaining\":" << (seconds - phaseStart)
                  << ",\"attempted_before\":" << attemptsBefore
                  << ",\"accepted_before\":" << acceptedBefore << "}\n";
        rankOne();
        const double phaseEnd = elapsed();
        std::cerr << "FLEET_POLISH {\"event\":\"end\",\"reason\":\""
                  << (interrupted ? "signal" : phaseEnd >= seconds ? "deadline" : "completed")
                  << "\",\"elapsed\":" << phaseEnd << ",\"phase_seconds\":" << (phaseEnd - phaseStart)
                  << ",\"remaining\":" << std::max(0.0, seconds - phaseEnd)
                  << ",\"attempted\":" << (attempted - attemptsBefore)
                  << ",\"accepted\":" << (accepted - acceptedBefore) << "}\n";
    }
'''


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("expected exactly one source anchor: " + repr(old))
    return text.replace(old, new, 1)


def prism_method(builder: bytes) -> str:
    git_blob = b"blob " + str(len(builder)).encode("ascii") + b"\0" + builder
    if hashlib.sha1(git_blob).hexdigest() != PRISM_BLOB_SHA1:
        raise ValueError("PRISM builder differs from pinned Git blob")
    assignments = [
        node.value for node in ast.parse(builder.decode("utf-8")).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "METHOD" for target in node.targets)
    ]
    if len(assignments) != 1:
        raise ValueError("expected one literal PRISM METHOD assignment")
    method = ast.literal_eval(assignments[0])
    if not isinstance(method, str) or method.count("void rankOne()") != 1:
        raise ValueError("unexpected PRISM method literal")
    return method


def transform(source: bytes, builder: bytes) -> tuple[bytes, dict]:
    if sha256(source) != BASE_SHA256:
        raise ValueError("source differs from the frozen composed candidate")
    text = source.decode("utf-8")
    method = prism_method(builder)
    historical = replace_once(text, RUN_ANCHOR, "\n" + method + RUN_ANCHOR)
    historical = replace_once(historical, MAIN, PRISM_MAIN)
    if sha256(historical.encode("utf-8")) != PRISM_OUTPUT_SHA256:
        raise ValueError("pinned method does not reproduce PRISM's measured source")
    changed = replace_once(text, RUN_ANCHOR, "\n" + ATTRIBUTION + method + GLUE + RUN_ANCHOR)
    changed = replace_once(changed, "    void run() {\n        int stalled = 0;\n",
                           "    void run() {\n        bool naturallyExhausted = false;\n        int stalled = 0;\n")
    changed = replace_once(changed, "            if (adaptive && stalled >= 64) break;\n",
                           "            if (adaptive && stalled >= 64) { naturallyExhausted = true; break; }\n")
    finish = (
        '        std::cerr << "Completed " << accepted << " improving moves / " << attempted << " attempts; MLU "\n'
        '                  << *std::max_element(loads.begin(), loads.end()) << "; elapsed " << elapsed() << "s\\n";\n'
    )
    changed = replace_once(changed, finish, finish + "        polishAfterExhaustion(naturallyExhausted);\n")
    if changed.count(method) != 1 or changed.count(MAIN) != 1:
        raise ValueError("method body or original four-argument dispatch drifted")
    result = changed.encode("utf-8")
    receipt = {
        "schema": "roadef.after-natural-exhaustion.source.v1",
        "status": "proposal; no build, runtime trial, promotion, or submission",
        "base": {"bytes": len(source), "sha256": sha256(source)},
        "prism": {
            "commit": PRISM_COMMIT, "path": PRISM_PATH,
            "builder_git_blob_sha1": PRISM_BLOB_SHA1,
            "builder_sha256": sha256(builder),
            "method_bytes": len(method.encode("utf-8")),
            "method_sha256": sha256(method.encode("utf-8")),
            "historical_output_sha256": sha256(historical.encode("utf-8")),
            "method_reused_verbatim": True,
        },
        "output": {"bytes": len(result), "sha256": sha256(result)},
        "opt_in": "FLEET_POLISH_AFTER_EXHAUSTION=1",
        "four_argument_main_unchanged": True,
        "clock_or_budget_reset": False,
    }
    return result, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--prism-builder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patch", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    outputs = [path for path in (args.output, args.patch, args.receipt) if path is not None]
    resolved = [path.resolve() for path in outputs]
    if len(set(resolved)) != len(resolved) or any(path.exists() for path in outputs):
        parser.error("outputs must be distinct fresh files")
    if any(path in (args.source.resolve(), args.prism_builder.resolve()) for path in resolved):
        parser.error("output must not replace an input")
    source = args.source.read_bytes()
    try:
        changed, receipt = transform(source, args.prism_builder.read_bytes())
    except (ValueError, SyntaxError, UnicodeDecodeError) as error:
        parser.error(str(error))
    patch = "".join(difflib.unified_diff(source.decode("utf-8").splitlines(keepends=True),
                                       changed.decode("utf-8").splitlines(keepends=True),
                                       fromfile="a/main.cpp", tofile="b/main.cpp")).encode("utf-8")
    receipt["patch"] = {"bytes": len(patch), "sha256": sha256(patch)}
    with args.output.open("xb") as stream:
        stream.write(changed)
    if args.patch:
        with args.patch.open("xb") as stream:
            stream.write(patch)
    if args.receipt:
        with args.receipt.open("xb") as stream:
            stream.write((json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
