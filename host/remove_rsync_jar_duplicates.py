#!/usr/bin/env python3
"""Remove only byte-identical .rsync-tmp duplicates from named generated JARs."""

import argparse
from copy import copy
import os
from pathlib import Path
import stat
import tempfile
import zipfile


def repair(jar: Path) -> None:
    with zipfile.ZipFile(jar) as source:
        entries = source.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError(f"{jar}: duplicate archive entry names are ambiguous")
        by_name = {entry.filename: entry for entry in entries}
        transient = [entry for entry in entries if '.rsync-tmp' in entry.filename.split('/')]
        if not transient:
            print(f"{jar}: no transient entries")
            return
        remove = set()
        for entry in transient:
            canonical = '/'.join(part for part in entry.filename.split('/') if part != '.rsync-tmp')
            counterpart = by_name.get(canonical)
            if counterpart is None or entry.is_dir() != counterpart.is_dir():
                raise ValueError(f"{jar}: transient entry has no matching canonical entry: {entry.filename}")
            if source.read(entry) != source.read(counterpart):
                raise ValueError(f"{jar}: transient entry differs from its canonical entry: {entry.filename}")
            remove.add(entry.filename)
        keep = [entry for entry in entries if entry.filename not in remove]
        descriptor, temporary_name = tempfile.mkstemp(prefix='classes-sanitized-', suffix='.tmp', dir=jar.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'w+b') as output:
                with zipfile.ZipFile(output, 'w') as target:
                    target.comment = source.comment
                    for entry in keep:
                        target.writestr(copy(entry), source.read(entry))
                output.flush()
                os.fsync(output.fileno())
            with zipfile.ZipFile(temporary) as target:
                if target.namelist() != [entry.filename for entry in keep]:
                    raise ValueError(f"{jar}: rewritten archive entry list differs")
                for entry in keep:
                    if target.read(entry.filename) != source.read(entry):
                        raise ValueError(f"{jar}: rewritten canonical entry differs: {entry.filename}")
            os.chmod(temporary, stat.S_IMODE(jar.stat().st_mode))
            os.replace(temporary, jar)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"{jar}: removed {sum(not entry.is_dir() for entry in transient)} identical transient files and {sum(entry.is_dir() for entry in transient)} directories; preserved {len(keep)} entries")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jars', nargs='+', type=Path)
    args = parser.parse_args()
    try:
        for jar in args.jars:
            repair(jar)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
