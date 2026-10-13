# Exact recovery execution logs

`execution-20260919.json.xz` is a standard XZ-compressed UTF-8 JSON object.
Its keys are `normal.txt`, `optimized.txt`, `root-normal.txt`,
`root-optimized.txt`, and `cli-recovery.json`; values retain literal outputs
from the recovery cloud container. Each text value's UTF-8 SHA-256 is bound by
`../TRANSPORT_RECOVERY.json` for the four suites.

Archive SHA-256:
`b4aa5a1cff81767d90b24408bd2bc439e15224c33af4c6f194276214503b10e4`.
Git blob: `e76c0a6d5dbe9f7ecca2e9b46606b11ffc554b99`; 2528 bytes.

Read using Python's standard library:

```python
import json
import lzma
from pathlib import Path
logs = json.loads(lzma.decompress(Path("execution-20260919.json.xz").read_bytes()))
print(logs["root-normal.txt"])
```

There are 77 distinct test methods, not 308; all four executions passed with
zero skips. These are local cloud-container executions, not GitHub Actions
execution authority, full-repository success or proof of document authenticity.
Original semantic tests and fixture remain unchanged. All referenced source
identities are in the adjacent recovery receipt.
