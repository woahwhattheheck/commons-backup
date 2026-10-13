# Invocation-local frontier alignment reuse

`pareto_frontier` retains its existing API and exact ordered result. The nested
scan previously reconstructed each candidate's scenario-aligned comparison key
and objective vector at every pair. Exact built-in `Alternative`/`Trace` inputs
now align once per invocation; vectors are built lazily when comparable keys
first meet. Nothing is cached across calls. Custom subclasses keep the original
method-dispatch path. No snapshot map is sorted, no equality test is replaced by
a digest, and no alternative or scenario is removed to reduce work.

The first-dominator scan order, kept-object identity, ties, comparison count,
ranking callback order, explicit approximate cap, and input validation remain
unchanged. All other top-level runtime definitions have identical ASTs to the
original. This changes the existing library, not a controller, solver, gameplay
policy, source exporter, workflow, or selected TITAN package.

## Executed changed-path validation

15 new methods pass, zero errors or skips. They cover 126 exhaustive four-point
sets at three caps (378 comparisons), 180 random fixture banks, scenario order,
ordered inventories, custom dispatch, failures and input isolation. The exact
original passes all functional checks and fails only the new work-count test:
1,984 key/vector constructions versus 32 on its 32-candidate case. That is an
optimization discriminator, not evidence that the former function chose wrong.

The original pinned interpreter produced six complete synthetic terminal traces
in both player positions, 18 transitions total. Eight actual unchanged T06
search calls consume the old/new frontiers. Complete search results agree after
excluding elapsed time: late sale yields 352 and is selected without a cash
deadline; early sale yields 318 and is selected when 100 must be available after
step 716. Idle is dominated; original input states remain unchanged. These are
fixed integration cases, not full games or a new win-rate result. No prior game
panel or original 29-method suite is represented as rerun by this receipt.

## Measured warm-call cost

Two warmups per implementation precede nine alternating old/new timed pairs for
each workload. All 90 measured result signatures match, including complete
kept/dominated/budget-dropped order and logical comparison counts. Preparation,
engine transitions and source loading are outside these timings. All raw samples
and complete output signatures are retained in the evidence below.

| Synthetic workload | Original median | New median | Reduction |
|---|---:|---:|---:|
| 16 candidates, 1 scenario, tradeoff | 0.750 ms | 0.120 ms | 84.0% |
| 64 candidates, 16 scenarios, tradeoff | 48.520 ms | 2.595 ms | 94.7% |
| 128 candidates, 32 scenarios, tradeoff | 348.180 ms | 12.901 ms | 96.3% |
| 128 candidates, 16 scenarios, dominated | 99.024 ms | 5.653 ms | 94.3% |
| 128 candidates, 16 scenarios, incomparable | 104.249 ms | 2.346 ms | 97.7% |

This measures the frontier function on constructed workloads in this Linux
Python 3.13.5 cloud container (4-CPU cgroup, 4 GiB). It is not a whole-agent speed
claim, Kaggle hardware result, wall-time guarantee, or game-policy promotion.
Small banks and custom subclasses can have different cost tradeoffs. Pairwise
comparison remains quadratic; aligned keys/vectors add per-invocation storage.

## Reproduction and source identities

Run inside this directory, reusing the existing engine artifact 10005621438 and
the existing T06 source. No new download or environment initialization is part
of these commands:

```sh
python -B -m unittest -v test_frontier_alignment
python -B benchmark_frontier_alignment.py --engine-dir "$ENGINE_DIR" \
  --kernel-file ../cloud-search-kernel/search_kernel.py --samples 9 \
  --output /tmp/frontier-alignment-results.json
python -B -m py_compile route_frontier.py test_frontier_alignment.py \
  benchmark_frontier_alignment.py
```

The benchmark reads the original runtime from local Git at
`09ee5b81cab4bb5b1237a6c2a20ac66672a68617`; alternatively supply an exact previously
materialized file with `--baseline`. It checks original blob
`5a08c7a016d0576a38454ac70af98621b26398ca`, T06 blob
`d05b35057509ed706679c0c841a81ffba05a9936`, and all three official engine hashes
at `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
New runtime blob is `832686e874ba31d0bfdc04505d8398c7ee61fb51`.
Existing dependency authorship/licenses remain intact; no dependency is vendored
or modified by this change. New tests and benchmark are Apache-2.0.

`FRONTIER-ALIGNMENT.json` is the compact receipt. Full evidence is retained in
Bryce's Library as `TITAN-BRIDGE-frontier-alignment-20260908.zip`, file ID
`file_000000006c9c81f5b338715cfa56612c` (40,992 bytes, SHA-256
`432334df39ec89304e70f29eccddb0d23000bed4e8417bfe4ac56fb6bc10a05a`).
Its 15 manifested members include the exact candidate/original source, benchmark,
all raw timing samples, six native state/action traces and both actual test logs.
The compressed JSON is a member of that Library ZIP, not a separate repository
file. From the materialized package directory, read it without executing code
or writing archive paths:

```python
import base64, gzip, hashlib, json
from pathlib import Path
receipt = json.loads(Path("FRONTIER-ALIGNMENT.json").read_text())
e = receipt["evidence"]
packed = base64.b64decode(Path(e["file"]).read_bytes())
assert hashlib.sha256(packed).hexdigest() == e["gzip_sha256"]
raw = gzip.decompress(packed)
assert hashlib.sha256(raw).hexdigest() == e["json_sha256"]
bundle = json.loads(raw)
for name, text in bundle["files"].items():
    assert hashlib.sha256(text.encode()).hexdigest() == e["members_sha256"][name]
report = json.loads(bundle["files"]["frontier-alignment-results.json"])
```

Historical source/evidence files are left untouched. FIR's existing T06 consumer
can import the same in-place API; no optional layer or new game run is needed to
adopt this library change. Hosted repository checks remain separate from the
executed local evidence here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
