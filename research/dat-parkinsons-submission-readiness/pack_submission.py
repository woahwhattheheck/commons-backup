#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dat_readiness.package import deterministic_zip

def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic data-guarded DaT submission ZIP")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(deterministic_zip(args.source, args.output))

if __name__ == "__main__":
    main()
