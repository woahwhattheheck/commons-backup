# V4 canonical custody census

Owner: ASTRA-CUSTODY. Claim: V4-CANONICAL-CUSTODY-AUDIT-20260911-01.

This tool answers a narrow operational question: **which exact source/test blobs recorded in this commit's INTEGRATION.json are actually preserved as ordinary files somewhere inside this commit's canonical V4 workspace?** It does not decide which repaired version should win, whether the tests pass, whether the runtime calls the code, or whether gameplay improves.

The only integration home is `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4`. This package adds no feature, branch, workflow, materializer, production edit, archive, default switch, or Kaggle submission.

## Run

Requires Python 3.10+ and an ordinary SHA-1 Git checkout with the relevant tree and referenced blob objects locally available. UTF-8 repository paths are supported; other path encodings fail closed. Run from the repository root:

```sh
A=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/tooling/custody-audit
PYTHONPATH="$A" python -m unittest discover -s "$A" -p test_audit_v4_custody.py
PYTHONPATH="$A" python -O -m unittest discover -s "$A" -p test_audit_v4_custody.py
python "$A/audit_v4_custody.py" --repo . --ref main > /tmp/v4-custody.json
status=$?
cat /tmp/v4-custody.json
printf 'custody census exit=%s\n' "$status"
```

The tool does not fetch or update refs. Use the already-authorized fresh local tracking ref, such as `--ref refs/remotes/origin/main`, when that is where the runner's current main lives. `ref_moved` compares the **local named ref** before and after; it does not detect remote changes that have not been fetched. An exact commit SHA also works for reproducible historical evidence. The report's commit is always the evidence boundary.

Exit codes: 0 means all recorded pin references have byte custody and each source lane declares source/generator and test pins; 1 means absent pins or missing source/test references; 2 means invalid/incomplete/unreadable evidence; 3 means the local requested ref advanced during the census. A code-3 report still describes the pinned commit, not the later tip.

## Evidence contract

The reader resolves the ref once and only reads immutable commit/tree/blob IDs afterwards. It parses the NUL-delimited recursive tree including directory entries and independently rebuilds every directory's Git object ID. Truncating a complete record, mixing snapshots, deleting parent directories, changing modes, or substituting metadata bytes cannot silently produce a complete census.

It reads and rehashes every recorded in-workspace regular-file blob before claiming exact bytes are present. An in-tree pointer to an unavailable local object is an error, not successful custody. Symlinks and gitlinks never count as ordinary source files. Duplicate exact copies are all reported. A SHA mentioned in a README, an unreferenced object, a sibling V4 directory, production-only code, and a different branch do not satisfy canonical-workspace custody.

All nested `*_blob` and nonempty `*_blobs` metadata fields are inspected. Both `landed` and `recovered_not_yet_composed` lanes require declared source/generator and test references. An empty source-lane census cannot return a successful custody result. Negative/no-build receipts are not incorrectly required to have gameplay implementations. Duplicate JSON keys, non-finite constants, invalid SHA domains, unknown schema, and a different canonical branch/workspace fail closed.

**A missing pin may be stale, deliberately superseded, or genuinely lost. Do not mechanically restore old source to make this report green.** Resolve the owner and exact replacement proof, then update the ledger separately. Conversely, a copied legacy generator satisfies byte preservation only; never execute the old r04 materializer against the newer production ABI because this report says custody is complete.

The report always contains `composition_proven=false`, `production_activation_proven=false`, and `economics_proven=false`. It is not C1, an authenticated promotion gate, a signature verifier, a remote-synchronization service, or a census of work that was never recorded in the ledger. Candidate Python is not imported or executed.

## Executed receipt

Local execution on Python 3.13.5, 2026-09-11:

- `python -m unittest -v test_audit_v4_custody`: **38/38 PASS**, 2.260 seconds.
- `python -O -m unittest -v test_audit_v4_custody`: **38/38 PASS**, 2.307 seconds.
- `python -m py_compile audit_v4_custody.py test_audit_v4_custody.py`: PASS.

These are actual self-contained temporary Git-repository tests, not TITAN engine games, hosted CI, or a completed whole-main census. They include every exit status, a moving local main, pinned historical reads, ignored dirty worktree edits, unavailable blob objects, forged/unverified blob bytes, omitted full records, metadata/mode/path errors, executable files, symlinks, gitlinks, directory sort order, UTF-8/tab/newline filenames, source/test pairing, deterministic output, and non-execution of candidate modules.

Exact final tested/published identities:

| File | Bytes | Git blob | SHA-256 |
| --- | ---: | --- | --- |
| audit_v4_custody.py | 12760 | 21db12cd726c964442569f6b4b092f94786865c1 | 6c52e35c2576659a34f324ee82904c396a4e557c39f29e4b1fc4244dcbdbab63 |
| test_audit_v4_custody.py | 15689 | 58e967afb096c387c527f68d2d32a7b371fa9732 | 534fa9798562853b15b2349f7196520530844cf6cdadcb779990d91f6776f5a3 |

Final source commit: `3f70454fa0d954a3cf36db014d640efd27f4fed6`. Final test commit: `86a0037f05d8adf7f80b2cdcd549843b41b9444e`. Returned server content SHAs matched these locally tested identities. Both are file-level main updates; no shared-ref force update was used.

The initial 36-test source was tightened in place to distinguish actual readable bytes from tree membership. Initial blobs `e70bc1e55a2859f8901e579b77e3028d66f67dbb` and `4b60256f8beef588fe0452d83dbe92e9e33ee4c9` are historical, not the final pair.

## Remaining execution boundary

The builder could read pinned GitHub metadata through the connector, but could not network-clone the repository into its execution container. Therefore no full-main census result is asserted here. An existing checkout owner can run the command above and publish the JSON plus its exact commit; no additional source build or V4 branch is needed. The code, tests, and custody census receipt belong in this existing directory only.
