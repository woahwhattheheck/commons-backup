"""Build the standalone Arlene + FLORA extra-hand candidate."""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / "cloud-frontier-policy" / "next-panel" / "vendor" / "arlene.py"
EXPECTED = "1dc166ae"


def main():
    base = BASE.read_text()
    digest = hashlib.sha256(base.encode()).hexdigest()
    if not digest.startswith(EXPECTED):
        raise SystemExit(f"unexpected Arlene bytes: {digest}")
    overlay = (HERE / "overlay-v1.py").read_text()
    (HERE / "candidate-v1.py").write_text(base + "\n\n" + overlay)
    print(digest)


if __name__ == "__main__":
    main()
