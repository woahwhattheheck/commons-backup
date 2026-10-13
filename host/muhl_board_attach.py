#!/usr/bin/env python3
# host/muhl_board_attach.py
# Routing button: Bryce has no file input next to the board textarea.
# Drop files in Desktop/COMMONS_DROP. This writes two siblings then dies:
#   <stem>.bin  lossless copy of the original bytes
#   <stem>.thumb.jpg  small preview if Pillow is present
# Does not git. Does not fire. ntfy cannot carry the bytes (door ~3900).
#   python host/muhl_board_attach.py
# Never --inject 0x01.

from __future__ import annotations

import hashlib
import os
import shutil
import sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

DROP = os.path.join(os.path.expanduser("~"), "Desktop", "COMMONS_DROP")
SKIP = {".thumb.jpg", ".bin"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def thumb(src, dest):
    try:
        from PIL import Image
    except ImportError:
        return "NO_PIL"
    im = Image.open(src)
    im = im.convert("RGB")
    im.thumbnail((320, 320))
    im.save(dest, "JPEG", quality=70, optimize=True)
    return dest


def main():
    os.makedirs(DROP, exist_ok=True)
    readme = os.path.join(DROP, "README.txt")
    if not os.path.isfile(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("Drop images/files here. PLAYER2 button: python host/muhl_board_attach.py\n")
            f.write("Output: <name>.bin (lossless bytes) + <name>.thumb.jpg (preview).\n")
    seen = 0
    for name in os.listdir(DROP):
        if name == "README.txt":
            continue
        if name.endswith(".bin") or name.endswith(".thumb.jpg"):
            continue
        src = os.path.join(DROP, name)
        if not os.path.isfile(src):
            continue
        seen += 1
        stem = src
        lossless = stem + ".bin"
        preview = stem + ".thumb.jpg"
        if not os.path.isfile(lossless):
            shutil.copyfile(src, lossless)
        tstat = thumb(src, preview) if not os.path.isfile(preview) else preview
        print("FILE", name)
        print("  bytes", os.path.getsize(src), "sha256", sha256(src))
        print("  lossless", lossless, os.path.getsize(lossless))
        print("  thumb", tstat)
    if seen == 0:
        print("DROP empty", DROP)
    print("NO GIT")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
