"""Build a standalone Apache-2.0 derivative from the pinned cached parent."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT_SHA256 = '8ac34abce129cf5c9456776c90edf7d2233b3a280bbdcf7622628825ef3669a0'


def build():
    parent = (HERE / 'vendor/igor_multiroute.py').read_bytes()
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError('Pinned Igor source changed')
    source = (b'# Apache-2.0; see LICENSE and NOTICE.md.\n'
              b'# Unchanged Igor Zharov parent follows; LARK additions at end.\n'
              + parent + b'\n\n# BEGIN LARK FRONTIER ADDITIONS\n'
              + (HERE / 'overlay.py').read_bytes())
    compile(source, 'candidate.py', 'exec')
    (HERE / 'candidate.py').write_bytes(source)
    print(hashlib.sha256(source).hexdigest())


if __name__ == '__main__':
    build()
