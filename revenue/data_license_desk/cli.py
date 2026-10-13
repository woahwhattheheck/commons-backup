from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

from .desk import DataLicenseError, HOLD, build_catalog, canonical_json, verify_catalog

MAX_INPUT = 2_000_000

def _read_plain(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise DataLicenseError("input must be ordinary file")
        if st.st_size > MAX_INPUT:
            raise DataLicenseError("input too large")
        data = b""
        while len(data) < st.st_size:
            chunk = os.read(fd, min(65536, st.st_size - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) != st.st_size:
            raise DataLicenseError("short read")
        return data
    finally:
        os.close(fd)

def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DataLicenseError(f"refuse symlink output: {path}")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

def _load(path: Path):
    return json.loads(_read_plain(path).decode("utf-8"))

def cmd_build(args: argparse.Namespace) -> int:
    document = _load(Path(args.input))
    receipt, packs = build_catalog(document, args.at)
    receipt_path = Path(args.receipt)
    _atomic_write(receipt_path, canonical_json(receipt))
    pack_dir = Path(args.pack_dir)
    for dataset_id, payload in packs.items():
        _atomic_write(pack_dir / f"{dataset_id}.zip", payload)
    print(f"decision={receipt['decision']} ready_packs={len(packs)} receipt_sha256={receipt['receipt_sha256']}")
    return 0 if receipt["decision"] != HOLD else 3

def cmd_verify(args: argparse.Namespace) -> int:
    document = _load(Path(args.input))
    receipt = _load(Path(args.receipt))
    packs = {}
    for row in receipt.get("datasets", []):
        if row.get("sample_pack_sha256"):
            packs[row["dataset_id"]] = _read_plain(Path(args.pack_dir) / f"{row['dataset_id']}.zip")
    ok = verify_catalog(document, receipt, packs, args.at)
    print("VERIFIED" if ok else "INVALID")
    return 0 if ok else 2

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Commons data-license sample-pack desk")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("input")
    b.add_argument("--receipt", required=True)
    b.add_argument("--pack-dir", required=True)
    b.add_argument("--at", required=True, help="trusted UTC RFC3339 Z evaluation time")
    b.set_defaults(func=cmd_build)
    v = sub.add_parser("verify")
    v.add_argument("input")
    v.add_argument("--receipt", required=True)
    v.add_argument("--pack-dir", required=True)
    v.add_argument("--at", required=True, help="trusted UTC RFC3339 Z verification time")
    v.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DataLicenseError, json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"HOLD: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
