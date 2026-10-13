# SPDX-License-Identifier: Apache-2.0
"""Exact-source review transform for integrated-selected market-tail readers.

Evidence-only tooling in the existing scheduler-action-prefix family.  It never
edits production in place and refuses source drift.
"""
from __future__ import annotations
import argparse, hashlib, os, tempfile
from pathlib import Path

SOURCE_BLOB = "bd08faf49e3caf464004e505d3984b309282bc29"

_REPLACEMENTS = (
    ("for o in action.get('market', [])):\n                    reason = 'future_product_purchase_needs_cash_bound'",
     "for o in action.get('market', [])[:maximum]):\n                    reason = 'future_product_purchase_needs_cash_bound'"),
    ("                    proposed = self.budget.apply(selected, private['seeds'], now, self.controller.cur,\n"
     "                        int(cfg.get('maxMarketOrdersPerTurn',10)))\n",
     "                    maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn',10)))\n"
     "                    proposed = self.budget.apply(selected, private['seeds'], now, self.controller.cur,\n"
     "                        maximum)\n"),
    ("zip(selected.get('market',[]), proposed.get('market',[]))",
     "zip(selected.get('market',[])[:maximum], proposed.get('market',[])[:maximum])"),
    ("for i in edits for o in selected['market'][i+1:])",
     "for i in edits for o in selected['market'][i+1:maximum])"),
)

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def fold_bytes(source: bytes) -> bytes:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    observed = git_blob(source)
    if observed != SOURCE_BLOB:
        raise ValueError(f"integrated_selected.py source drift: {observed}; expected {SOURCE_BLOB}")
    text = source.decode("utf-8")
    for before, after in _REPLACEMENTS:
        if text.count(before) != 1:
            raise ValueError("source anchor must occur exactly once")
        text = text.replace(before, after, 1)
    compile(text, "integrated_selected.py", "exec")
    return text.encode("utf-8")

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args(argv)
    tmp = None
    try:
        if a.source.resolve() == a.output.resolve():
            raise ValueError("output must be separate from source")
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("output already exists")
        result = fold_bytes(a.source.read_bytes())
        if not a.output.parent.is_dir():
            raise ValueError("output parent does not exist")
        with tempfile.NamedTemporaryFile(dir=a.output.parent, delete=False) as f:
            tmp = Path(f.name); f.write(result); f.flush(); os.fsync(f.fileno())
        os.link(tmp, a.output)
        print(f"source={SOURCE_BLOB} output={git_blob(result)} bytes={len(result)}")
        return 0
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print(f"ERROR: {exc}", file=__import__('sys').stderr); return 2
    finally:
        if tmp is not None: tmp.unlink(missing_ok=True)

if __name__ == "__main__":
    raise SystemExit(main())
