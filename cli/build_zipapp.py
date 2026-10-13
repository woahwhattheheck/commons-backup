#!/usr/bin/env python3
"""Build the portable commonsctl executable from its maintained source modules."""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import sys
import tempfile
import zipfile


MODULES = ("commonsctl.py", "ctl_client.py", "ctl_write.py", "ctl_ops.py", "ctl_cli.py")


def build(destination: Path) -> None:
    source = Path(__file__).resolve().parent
    content = io.BytesIO()
    content.write(b"#!/usr/bin/env python3\n")
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = {name: (source / name).read_bytes() for name in MODULES}
        entries["__main__.py"] = b"from commonsctl import main\nraise SystemExit(main())\n"
        for name, payload in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".commonsctl-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.chmod(0o755)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=Path(__file__).with_name("commonsctl.pyz"))
    args = parser.parse_args()
    try:
        build(args.output)
    except (OSError, ValueError) as exc:
        print("commonsctl build failed: %s" % exc, file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
