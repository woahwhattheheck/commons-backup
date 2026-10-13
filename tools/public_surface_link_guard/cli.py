from __future__ import annotations
import argparse,sys
from pathlib import Path
from .codec import GuardError,dump
from .core import scan_paths

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Fail closed on public/customer-facing backlinks to Commons")
    p.add_argument("manifest",type=Path); p.add_argument("--root",type=Path,default=Path(".")); a=p.parse_args(argv)
    try:r=scan_paths(root=a.root,manifest_path=a.manifest)
    except GuardError as e: print(f"GUARD_ERROR: {e}",file=sys.stderr); return 2
    sys.stdout.write(dump(r)); return 1 if r["violations"] else 0
if __name__=="__main__": raise SystemExit(main())
