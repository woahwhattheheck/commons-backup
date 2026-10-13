"""Recreate the bounded, explicitly non-model comparison inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = {
        "main.py": (HERE.parent.parent / "cloud-market/main.py",
                    "d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62"),
        "submission.tar.gz": (HERE.parent / "exports/lean20/submission.tar.gz",
                    "9bf553da0ff3c057cbc167150ce5c1c88d8ee18eb031648a4f055fa21532227d")}
    for name, (source, expected) in files.items():
        if source.stat().st_size > 262144:
            raise ValueError("Control input exceeds the bounded sample budget")
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("Use the pinned PR9770 control bytes for " + name)
        shutil.copyfile(source, args.output / name)
    rng = random.Random(20260907)
    previous = bytearray(rng.randbytes(25))
    data = bytearray()
    for _ in range(10000):
        for index in rng.sample(range(25), 4): previous[index] = rng.randrange(256)
        data.extend(previous)
    data.extend(b"bounded-tail!")
    (args.output / "synthetic-correlated-25.bin").write_bytes(data)
    (args.output / "synthetic-noise.bin").write_bytes(random.Random(721991).randbytes(65537))
    print(json.dumps({p.name:{"bytes":p.stat().st_size,
        "sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in args.output.iterdir()},indent=2))


if __name__ == "__main__":
    main()
