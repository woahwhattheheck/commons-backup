#!/usr/bin/env python3
"""Deterministically expand the public synthetic fixture for scale smoke tests."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows=[]
    for lineno,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():
            continue
        value=json.loads(line)
        if not isinstance(value,dict):
            raise ValueError(f'line {lineno} must be object')
        rows.append(value)
    if not rows:
        raise ValueError('source fixture is empty')
    return rows


def generate(rows: list[dict], batches: int) -> list[dict]:
    if batches < 1:
        raise ValueError('batches must be >=1')
    out=[]
    for batch in range(batches):
        for row in rows:
            clone=dict(row)
            clone['doc_id']=f"{row['doc_id']}-b{batch:02d}"
            clone['text']=str(row['text']) + f" Batch reference {batch:02d}; deliverable sequence {(batch*7)%31:02d}."
            out.append(clone)
    return out


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--batches',type=int,default=25)
    args=ap.parse_args()
    rows=generate(load_jsonl(args.source),args.batches)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows),encoding='utf-8')
    print(json.dumps({'documents':len(rows),'batches':args.batches,'output':str(args.output)},sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
