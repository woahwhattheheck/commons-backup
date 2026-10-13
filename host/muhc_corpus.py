#!/usr/bin/env python3
"""host/muhc_corpus.py — freeze the MUHC leftover corpus and matrix.

Peer land `muhc.py` / `ground/MUHC.md` already shipped the container
(PR 2283, `826332170`). Ranked leftover 1 from that card:

  Freeze a named corpus (SEED0 + one screenshot 1bpp + one GGUF slice)
  with exact SHAs and a matrix vs zlib/bz2/lzma/zstd.

This leftover does not remint cursor-grok-46-muhc-roundtrip-20260825-01
or demon-redteam-compression-productization-20260825-03. It does not
edit muhc.py, test_muhc.py, foldpack.py, stackpack.py, or evolve.py.
It does not write titan. No auth. No gate.

GGUF is ABSENT from the public tree. zstd availability is measured from the
current runtime: PRESENT is benchmarked, while ABSENT names the calibrated
module-import search space. Neither result is inferred from a missing number.

  python3 host/muhc_corpus.py
  python3 host/muhc_corpus.py --root .
  python3 host/muhc_corpus.py --self-test
"""
from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import lzma
import os
import sys
import zlib

try:
    import zstandard as zstandard_mod
except ImportError:
    zstandard_mod = None
try:
    import zstd as zstd_mod
except ImportError:
    zstd_mod = None

ROOT_DEFAULT = "."
PUBLISHED_PROGRAM = ["TRANSPOSE", "REV_COLS", "XOR_COL", "XOR_COL", "REV_COLS", "ROT4"]
SLACK_TS = "1787645475.191099"
PEER_RECEIPT = "cursor-grok-46-muhc-roundtrip-20260825-01"
MANDATE = "demon-redteam-compression-productization-20260825-03"

ROWS = (
    {
        "id": "tail7",
        "path": os.path.join("compress", "muhc_v1", "corpus", "tail7.bin"),
        "kind": "frozen-fixture",
        "width": 5,
        "sha256": "707bfe8053852e63e1183ed7bdeba47bda56f7ca126418b59b4154a4fca69fca",
        "bytes": 7,
        "bench_evolve": True,
    },
    {
        "id": "shot1bpp",
        "path": os.path.join("compress", "muhc_v1", "corpus", "shot1bpp.bin"),
        "kind": "screenshot-1bpp",
        "source_png": os.path.join("shots", "p2-dir5-demo-20260820.png"),
        "source_png_sha256": "746e39e78a18d177563b06b95fe90ca7b8dc9dffd0172584d8f6a1d77b9682d0",
        "width": 64,
        "sha256": "f69acd4dca88fea007bb3542f71f238f005ab6b213094d24ce3e13c7ffb083b9",
        "bytes": 192,
        "bench_evolve": True,
    },
    {
        "id": "SEED0",
        "path": os.path.join("muhl", "containers", "MUHLNICKEL_DISTRO", "SEED0.mno"),
        "kind": "published-mno",
        "width": 200,
        "sha256": "faa70efc328e9b596eb27d6c1b2e2c4d76a863d8a81380f0d22ec7a8e4d85071",
        "bytes": 8192,
        "bench_evolve": True,
    },
    {
        "id": "FOUNDRY0",
        "path": os.path.join("muhl", "containers", "MUHL_VISIBLE", "FOUNDRY0.mno"),
        "kind": "published-mno",
        "width": 200,
        "sha256": "228659b3279865ddb255358ee3689cd57883eebd7f38c4f9a3851f8d2057a9af",
        "bytes": 12800,
        "bench_evolve": True,
    },
    {
        "id": "AUTOFAB0",
        "path": os.path.join("muhl", "containers", "MUHL_VISIBLE", "AUTOFAB0.mno"),
        "kind": "published-mno",
        "width": 200,
        "sha256": "50fd404807ed0042a5513395d4cfc40867d9721aa1c46d19bdd2cea75a3857ab",
        "bytes": 102925,
        "bench_evolve": True,
    },
)
SEARCH_SPACE = (
    os.path.join("ground", "MUHC.md"),
    os.path.join("muhc.py"),
    os.path.join("test_muhc.py"),
    os.path.join("host", "muhc_corpus.py"),
    os.path.join("compress", "muhc_v1", "corpus", "tail7.bin"),
    os.path.join("compress", "muhc_v1", "corpus", "shot1bpp.bin"),
    os.path.join("shots", "p2-dir5-demo-20260820.png"),
    os.path.join("muhl", "containers", "MUHLNICKEL_DISTRO", "SEED0.mno"),
    os.path.join("muhl", "containers", "MUHL_VISIBLE", "FOUNDRY0.mno"),
    os.path.join("muhl", "containers", "MUHL_VISIBLE", "AUTOFAB0.mno"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    os.path.join("muhc.py"),
    os.path.join("ground", "MUHC.md"),
)
GGUF_SEARCH = (
    "*.gguf",
    os.path.join("muhl", "**", "*.gguf"),
    "titan.gguf",
)
ZSTD_SEARCH = ("zstandard", "zstd", "import zstandard", "import zstd")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def file_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def entropy_file(data: bytes) -> dict:
    rows = {
        "zlib_file": len(zlib.compress(data, 9)),
        "bz2_file": len(bz2.compress(data, 9)),
        "lzma_file": len(lzma.compress(data, preset=9)),
    }
    if zstandard_mod is not None:
        rows["zstd_file"] = len(zstandard_mod.ZstdCompressor(level=19).compress(data))
        return rows, "PRESENT", "zstandard module present"
    if zstd_mod is not None:
        rows["zstd_file"] = len(zstd_mod.compress(data))
        return rows, "PRESENT", "zstd module present"
    rows["zstd_file"] = None
    return rows, "ABSENT", "search: import zstandard / import zstd — ModuleNotFoundError"


def find_gguf(root: str) -> list[str]:
    hits = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "/.git/" in (dirpath + "/"):
            continue
        for name in filenames:
            if name.lower().endswith(".gguf"):
                hits.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(hits)


def _load_muhc(root: str):
    sys.path.insert(0, root)
    import muhc
    return muhc


def measure_row(root: str, row: dict, muhc) -> dict:
    path = os.path.join(root, row["path"])
    measured = {
        "id": row["id"],
        "path": row["path"],
        "kind": row["kind"],
        "present": os.path.isfile(path),
        "width": row["width"],
    }
    if not measured["present"]:
        measured["state"] = "NOT_LANDED"
        measured["z"] = "FINDER-FAILED"
        measured["note"] = "missing %s" % row["path"]
        return measured
    data = file_bytes(path)
    digest = hashlib.sha256(data).hexdigest()
    measured["bytes"] = len(data)
    measured["sha256"] = digest
    sha_ok = digest == row["sha256"] and len(data) == row["bytes"]
    measured["sha_ok"] = sha_ok
    if not sha_ok:
        measured["state"] = "NOT_LANDED"
        measured["z"] = "FINDER-FAILED"
        measured["note"] = "sha/bytes mismatch"
        return measured
    program = PUBLISHED_PROGRAM if row.get("bench_evolve") else None
    muhc_rows = muhc.bench_bytes(data, row["width"], program)
    entropy, zstd_state, zstd_note = entropy_file(data)
    blob = muhc.encode_bytes(data, row["width"], codec="stack", tile_w=row["width"], tile_h=1)
    rec, _header = muhc.decode_bytes(blob)
    measured["stack_roundtrip_sha"] = hashlib.sha256(rec).hexdigest()
    measured["stack_roundtrip_ok"] = rec == data
    measured["muhc"] = {
        key: {
            "payload_b": val.get("payload_b"),
            "overhead_b": val.get("overhead_b"),
            "container_b": val.get("container_b"),
            "container_pct": val.get("container_pct"),
            "transform_delta_b": val.get("transform_delta_b"),
            "encode_s": val.get("encode_s"),
            "decode_s": val.get("decode_s"),
        }
        for key, val in muhc_rows.items()
    }
    measured["entropy_file"] = entropy
    measured["zstd"] = zstd_state
    measured["zstd_note"] = zstd_note
    measured["state"] = "INTEGRATED" if measured["stack_roundtrip_ok"] else "NOT_LANDED"
    return measured


def measure_root(root: str = ROOT_DEFAULT) -> dict:
    root = os.path.abspath(root)
    hits = [rel for rel in CALIBRATION if os.path.isfile(os.path.join(root, rel))]
    misses = [rel for rel in SEARCH_SPACE if not os.path.isfile(os.path.join(root, rel))]
    calibration_ok = len(hits) == len(CALIBRATION)
    gguf = find_gguf(root)
    muhc = _load_muhc(root)
    rows = [measure_row(root, row, muhc) for row in ROWS]
    report = {
        "kind": "MUHC_CORPUS",
        "mandate": MANDATE,
        "peer_receipt": PEER_RECEIPT,
        "slack_ts": SLACK_TS,
        "do_not_remint": [PEER_RECEIPT, MANDATE],
        "untouched": ["muhc.py", "test_muhc.py", "foldpack.py", "stackpack.py", "evolve.py"],
        "calibration_ok": calibration_ok,
        "calibration_hits": hits,
        "search_space": list(SEARCH_SPACE),
        "search_misses": misses,
        "gguf": {
            "state": "ABSENT" if not gguf else "PRESENT",
            "hits": gguf,
            "search_space": list(GGUF_SEARCH) + ["os.walk *.gguf excluding .git"],
            "note": "public tree has no GGUF slice; do not invent one; titan NOT_WRITTEN",
        },
        "zstd": {
            "state": "UNMEASURED",
            "search_space": list(ZSTD_SEARCH),
            "note": "measured from the first verified corpus row",
        },
        "published_program": PUBLISHED_PROGRAM,
        "rows": rows,
        "titan": "NOT_WRITTEN",
        "cash": "NOT_LANDED",
        "no_auth": True,
        "no_gate": True,
    }
    if not calibration_ok:
        report["state"] = "UNMEASURED"
        report["z"] = "FINDER-FAILED"
        report["note"] = "instrument failure: calibration miss %s" % [
            rel for rel in CALIBRATION if rel not in hits
        ]
        return report
    if any(row.get("state") != "INTEGRATED" for row in rows):
        report["state"] = "NOT_LANDED"
        report["z"] = "FINDER-FAILED"
        return report
    if rows:
        report["zstd"]["state"] = rows[0].get("zstd", "ABSENT")
        report["zstd"]["note"] = rows[0].get("zstd_note")
    report["state"] = "INTEGRATED"
    return report


def self_test() -> int:
    report = measure_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".")
    if report.get("state") != "INTEGRATED":
        print("SELF-TEST FAIL %s %s" % (report.get("state"), report.get("z")))
        print(json.dumps(report, indent=2)[:2000])
        return 1
    print("SELF-TEST OK rows=%d gguf=%s zstd=%s" % (
        len(report["rows"]), report["gguf"]["state"], report["zstd"]["state"]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MUHC frozen corpus + matrix")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    report = measure_root(args.root)
    print(json.dumps(report, indent=2))
    return 0 if report.get("state") == "INTEGRATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
