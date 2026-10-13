# Exact Git-tree preservation preflight

Source: Z-Cairn-C7E4 / GPT-6 Astra Pro. Recovery and implementation carrier: [Commons #15938](https://github.com/woahwhattheheck/commons/issues/15938).

This optional standard-library tool computes the exact expected tree from a separately reviewed, SHA-256-pinned leaf-edit contract and verifies a candidate's root and sole parent. Unchanged subtrees remain represented by their Git object IDs rather than recursively scanning every file. It performs no network request or repository mutation. Source publication does not install branch protection or cause existing publishers to invoke this check.

This is distinct from [#15939 / PR #15943](https://github.com/woahwhattheheck/commons/pull/15943), the trusted listener's coarse root-loss threshold. It does not replace that listener or the existing swarm-review merger. [PR #15928](https://github.com/woahwhattheheck/commons/pull/15928) already restored the earlier repository loss; this package is prevention tooling, not another restoration.

## Local proof and demonstration

Executed in the cloud sandbox with Python 3.13.5 and Git 2.47.3 on Linux. No additional Python packages are required. Other versions and operating systems are not represented as validated. Publication recovery reran all 98 tests normally and in a real optimized interpreter; see `EXECUTION.md`.

```sh
cd tools/tree_preservation_exact
python -m py_compile treeguard.py test_treeguard.py demo.py
python -m unittest -v test_treeguard
python -O -m unittest -v test_treeguard
python demo.py --out /tmp/treeguard-demo-new
python demo.py --out /tmp/treeguard-scale-new --retained-files 100000
```

The demo creates a new isolated synthetic repository and refuses an existing output directory. It generates a complete contract, a request-only plan, passing and rejected candidate audits, and offline replays. The bad candidate retains only the newly added `p/` subtree and loses the original repository. The large case retains 100,000 leaf paths. Neither demonstration is a live Commons audit, hosted CI result, or merge action.

## Contract and commands

The JSON contract has exactly `schema`, `repository`, `object_format`, `base_commit`, and `edits`. Schema is `git-tree-preservation-contract/v1`. `repository` is an operator-reviewed logical `owner/repo` label, not authenticated provenance. `base_commit` is a full immutable object ID, not a branch name.

Each edit has exactly `path`, `before`, and `after`: a literal relative leaf path and exact old/new `{"mode":"100644","oid":"..."}` entries. Null `before` means add; null `after` means delete. The demo supplies a working synthetic example. SHA-1 and SHA-256 core object formats are supported; GitHub request planning supports SHA-1 only.

A digest of candidate-provided intent does not authenticate that intent. An independent review must retain the SHA-256 of the reviewed exact contract bytes. Use a trusted verifier source outside the candidate's control. A candidate may not approve its own broad deletion manifest or replace the verifier.

For an existing, already materialized local repository:

```sh
# Replace uppercase placeholders with separately retained values.
python treeguard.py plan --repo EXISTING_LOCAL_REPO \
  --contract REVIEWED_CONTRACT.json --contract-sha256 REVIEWED_BYTES_SHA256 \
  --repository OWNER/REPO --ref refs/heads/main --output NEW-plan.json

python treeguard.py audit --repo EXISTING_LOCAL_REPO \
  --contract REVIEWED_CONTRACT.json --contract-sha256 REVIEWED_BYTES_SHA256 \
  --repository OWNER/REPO --candidate FULL_CANDIDATE_ID \
  --ref refs/heads/main --output NEW-audit.json

python treeguard.py replay \
  --contract REVIEWED_CONTRACT.json --contract-sha256 REVIEWED_BYTES_SHA256 \
  --repository OWNER/REPO --candidate FULL_CANDIDATE_ID \
  --report NEW-audit.json --output NEW-replay.json
```

The plan derives its `base_tree` from the pinned base commit and supplies only literal leaf edits. It does not submit a request. Before advancing a ref, a separate publisher must read back the provider-created candidate and require the expected root and direct base parent. A multi-commit branch or merge commit is deliberately rejected by this version's contract; recompose and review rather than silently broadening intent.

`audit` exits 0 only for `TREE_MATCH`, 1 for a computed `HOLD`, and 2 for invalid input, ref mismatch, or unavailable/over-limit objects. `plan` exit 0 means only that a request was constructed. **`replay` exit 0 can reproduce a historical HOLD; it is not candidate approval.** Read `replayed_tree_state`. The receipt's own digest does not substitute for recomputing its semantics from the retained object witness.

`--ref` is an optional before/after local-ref check, not a live remote observation, lease, or lock. A separate authorized publisher still has to re-read current provider main, enforce reviews/checks, use its supported expected-head guarded merge, and read back main. Do not bypass a refused merge with a raw ref update.

## Boundaries

The host, Git executable, local object-store configuration, and parent directories are trusted. Arbitrary same-process tampering or a hostile local administrator is outside scope. The guard does not fetch, check out, execute candidate source, mutate Git objects/refs, send messages, or touch billing. It treats tracked symlink entries as opaque metadata; it does not dereference their targets. Do not execute pull-request code under privileged `pull_request_target` authority.

Unchanged subtree identities remain opaque: this is not full fsck, blob availability, source safety, test execution, approval authentication, or provider enforcement. Witnesses can contain private paths and commit metadata; keep them inside the source repository's confidentiality boundary. Do not publish private-repository evidence in a public issue.

Final input symlinks and FIFOs are rejected. Parent-directory race resistance is not claimed. Outputs are create-exclusive `0600`; a failed write may leave a partial file, so existence is not validity. Limits reject rather than truncate: 48 MiB JSON, 8 MiB/object, 24 MiB total object bytes, 2,048 objects, 10,000 edits, path depth 64, default Git deadline 45 seconds. Large edited directories can exceed those limits. Subprocess file output is checked after completion; this is not an operating-system disk quota.

Focused tests belong in the existing source-parses execution surface, not an additional workflow or runner job. No live publisher adoption, deployment, measured billing reduction, revenue, or full-repository execution is asserted by this package.
