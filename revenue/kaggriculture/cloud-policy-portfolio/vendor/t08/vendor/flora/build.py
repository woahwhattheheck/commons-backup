"""Build intact Arlene plus dependency-free dated allocator and overlay."""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / "cloud-frontier-policy" / "next-panel" / "vendor" / "arlene.py"
EXPECTED = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"


def main():
    base = BASE.read_text()
    digest = hashlib.sha256(base.encode()).hexdigest()
    if digest != EXPECTED:
        raise SystemExit(f"unexpected Arlene bytes: {digest}")
    allocator = (HERE / "dated_allocation.py").read_text()
    overlay = (HERE / "overlay.py").read_text()
    (HERE / "candidate.py").write_text(base + "\n\n" + allocator + "\n\n" + overlay)
    print(digest)


if __name__ == "__main__":
    main()
