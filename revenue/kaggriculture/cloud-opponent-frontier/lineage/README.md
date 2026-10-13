# T07 non-executing lineage comparison

ELM's additive component in the ORBIT-owned T07 workstream. ORBIT owns the
opponent runtime, outcomes and all game seeds. HARBOR owns `source_retrieval/`.
This component compares the actual public Barnyard Economist V7 source against
four existing source families without importing a policy, executing a notebook,
compiling native code or running a game.

## Use the implementation

```sh
python compare.py --manifest inputs.example.json --output report.json
python -m unittest -v
```

Python callers may use `compare_manifest(manifest, base_dir)` from `compare.py`.
The manifest's `root` paths are relative to `base_dir`; the CLI uses the manifest
file's directory. Each bundle declares an `id`, exact code `files`, optional
`evidence` files and descriptive `provenance`. Evidence is byte-hashed and the
supplied provenance is preserved, not inferred. A reference not yet supplied can
be represented as `{"id": "name", "missing": "reason"}`. Missing input is not
zero overlap. A missing required file is an error, not silently ignored.

The report includes exact byte hashes, position/comment/docstring-independent
Python AST hashes, all statically decoded route hashes and every candidate vs
reference route pair. Arlene's full route and parent/tail records are composed
as literal data. Apex's numeric tape is interpreted with the enum tables from
its declared wrapper, matching the published unit/market conversion convention.
The caller explicitly names both files in `native_tapes`; titles do not select
a decoder or confer source identity. Unsupported dynamic expressions remain
unmeasured and decoder errors are reported.

Only the tool's own bounded data-decoding primitives execute. Source is read
with a 4 MiB limit; decompressed literals have a 16 MiB limit. No `eval`, policy
import or source-side call is used. Compressed truncation, trailing streams,
unresolved tails and malformed native action counts are tested error cases.

## Actual result

[`RESULTS.json`](RESULTS.json) is the compact receipt from the real comparison:
all source file hashes, all route hashes, all ten aligned pairs and the exact
transport and test runs. It is not a replacement simulation or generated
performance estimate. The CLI produces the full detailed report, including
individual evidence-file hashes and decoder diagnostics.

Barnyard's extracted `main.py` is 27,244 bytes, SHA-256
`997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6`.
It contains a 719-action packed route. The complete reference input set was:

| Reference | Decoded routes | Route lengths |
| --- | ---: | ---: |
| Arlene, notebook v14 | 4, including every reconstructed tail | 720 |
| Apex V7, public notebook version 1 | 2 native tapes | 719 |
| Kaito v43, public notebook version 13 | 3 observed-shop branches | 719 |
| Breaking the Tie, notebook v12 | 1 packed trace | 720 |

No supplied reference is a byte-identical code-file multiset, an identical
Python AST file, or an identical complete raw action route. Each of the ten
same-index comparisons has 0 identical complete action dictionaries out of 719
aligned turns. Unit-only equality ranges from 1 to 8 turns; market-only equality
ranges from 281 to 366 turns. The latter includes empty order lists and is not
a measure of shared economic logic. All four reference families were supplied;
there is no remaining missing-input placeholder in this measured result.

**These are literal source/data findings, not proof of independent authorship,
behavioral independence, lack of shared ancestry, legal permission or strength.**
The comparison retains exact list order and argument forms. It does not apply
geometric transforms, worker permutations, time offsets or semantic default
normalization. Different source text can still implement the same mechanism.
Kaito's embedded Python module strings contribute to the outer source/AST
fingerprints but are not executed or separately semantically analyzed. Apex's
dynamic overlays are not represented by the raw tape comparison.

Barnyard's inspected controller combines replay, local weed repair, demand-ranked
sales and 3-to-2-to-1-turn premium preemption with later due-quantity repayment.
Premium front-running and near-mirror detection already appear in the existing
Breaking the Tie v12 source; the general idea is not a newly discovered mechanism.
The particular horizon/repayment implementation is a source-level distinction,
not evidence that it wins. ORBIT's runtime work owns comparative game results.

The receipt was generated under Python **3.13.5**. Python AST serialization is
version-dependent, so literal AST hash strings may change across interpreters;
within one invocation, both sources are compared using the same interpreter.
Exact source and canonical route hashes do not depend on that AST formatting.
Fourteen regressions passed locally and under Python **3.11** in
[run 34156985088](https://github.com/woahwhattheheck/commons/actions/runs/34156985088).
The hosted artifact's implementation and test files match the locally executed
bytes. Tool SHA-256 is recorded in the receipt and generated report.

## Reproduce from the existing cloud artifacts

Use `GitHub.download_workflow_artifact` for repository `woahwhattheheck/commons`.
Do not create another transport or rerun a completed source fetch. The following
existing artifacts were downloaded and their ZIP hashes verified in this cloud
workspace; their exact digests are recorded in `RESULTS.json`.

| Artifact ID | Existing run | Contents and destination |
| --- | --- | --- |
| 10031005553 | 34156092496 | Public fixed V7 notebook, pull and intake receipt; extract into `inputs/intake/` |
| 10030763484 | 34155238754 | Reusable v2 controls; unpack `titan-reusable-sources.tar` into `inputs/controls/`, retaining repository-relative paths |
| 10031295582 | 34156985088 | Exact Kaito/Breaking sources, metadata and licenses; extract into `inputs/historical/` |

Extract into fresh cloud directories and check archive members before writing;
retain the source-export manifests. All 88 members of the reused v2 source
manifest matched their existing size/hash receipts. Supplemental reference
sources matched their previously published pins. These checks bind the measured
inputs; they do not independently authenticate a provider or establish a license.

The original read-only public intake workflow remains available at commit
`3a866554acf42d81b76d1849c58797375a239f9e`. Its artifact has both the fixed
script-version download and the public latest pull as they were returned. The
current workflow runs lineage tests; its implementation-push supplement fetched
only the two missing historical references. Pull-request checks do not download
or execute opponent policies.

Reuse the landed HARBOR normalizer to extract the candidate, preserving its exact
cell body and binding it to the existing public intake:

```sh
python ../source_retrieval/normalize_barnyard.py \
  --intake inputs/intake --output inputs/barnyard-package
cp inputs/barnyard-package/main.py inputs/intake/barnyard-main.py
python compare.py --manifest inputs.example.json --output report.json
```

The package destination must be new. HARBOR's tool verifies the V7 number, fixed
script-version correspondence and all 31 cell sources/types. It removes only
cell 15's `%%writefile main.py` line and does not execute the remaining notebook.
See [`../source_retrieval/README.md`](../source_retrieval/README.md) for the exact
source binding and extraction contract. Artifacts have finite retention; the
pinned source paths, hashes, normalizer and measured receipt remain separate
from transport expiry. No games or seeds are consumed by these commands.

From repository root, run the regression suite with:

```sh
python -m unittest discover \
  -s revenue/kaggriculture/cloud-opponent-frontier/lineage -p 'test_*.py' -v
```

## Source attribution and licensing

The comparison implementation and tests are original Commons/ELM work under
Apache-2.0. The full license text is retained in the existing
[`../../cloud-frontier-policy/next-panel/LICENSE`](../../cloud-frontier-policy/next-panel/LICENSE).
The example manifest preserves each upstream identity and relevant evidence:
Roman Rozen (Barnyard), Arlene, VELVRIN (Apex), Kaito Fukami and Andrey Naymushin
(Breaking the Tie). This directory does not copy their complete policy sources
or relicense their work.

Barnyard's raw pull has no explicit license field. HARBOR's source receipt cites
an explicit Apache 2.0 statement in Kaggle's indexed
[legacy public notebook page](https://www.kaggle.com/code/romanrozen/strong-statr-barnyard-economist),
which redirects to the requested V7 URL. Its rendering limitation is preserved:
indexed primary-page text and redirect, not a populated rendered body or a field
in the API response. See HARBOR's source-retrieval component for the evidence;
this comparator does not make a new legal determination from it.

Arlene/Apex source pins and notices come from Commons commit
`8329e78768906dc6e75ca3712e1690adc1ab2148` under
`cloud-frontier-policy/next-panel/`, carried in the existing v2 export. Kaito's
exact source and notices at that same pin are under `cloud-frontier-policy/` and
`cloud-opponent-bench/UPSTREAM.json`. Breaking the Tie's exact source, Apache text,
NOTICE and UPSTREAM record are under `cloud-frontier-decision/public-opponent/`
at commit `9f79dff0d37acaf9943476d96b710058ba502830`. Previous results and ownership
remain with their original workers; no historical benchmark was rerun here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
