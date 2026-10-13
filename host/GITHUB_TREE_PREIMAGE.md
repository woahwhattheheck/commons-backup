# Recover a complete Git-tree preimage

`github_tree_preimage.py` reads retained raw Git tree bytes, checks the Git
object SHA-1 framing, parses every immediate entry, and emits exact regular-file
mode/type/blob evidence for selected leaves. It performs no network or repository
writes. Existing publisher permissions, ownership and source checks still apply.

The consumer must independently observe the immutable base commit and its root
tree through the connected GitHub reader, then retain each parent-to-child tree
SHA. A caller-reported tree SHA alone does not bind a proof to current main.
Git objects are immutable; a later branch move requires a fresh native root
observation. Never reuse an old parent binding for a new source version.

Obtain available bytes from an existing authorized checkout without implicit
network access:

```sh
GIT_NO_LAZY_FETCH=1 git cat-file tree OBSERVED_TREE_SHA > PRIVATE_RAW_TREE
python host/github_tree_preimage.py --raw-tree PRIVATE_RAW_TREE \
  --base-tree-sha OBSERVED_TREE_SHA --tree-sha OBSERVED_TREE_SHA \
  --leaf EXISTING_IMMEDIATE_NAME --leaf NEW_IMMEDIATE_NAME
```

If the current tree object is unavailable, an older verified raw tree plus
immediate-entry proposals can recover the current object. `--patches` accepts a
private JSON list: `{"name":"immediate-name","sha":"40hex"}` replaces a blob
while preserving the observed old mode; a new entry also needs a proposed `mode`.
`{"name":"immediate-name","delete":true}` proposes removal from the recovered
object. These operations construct evidence bytes; they do not authorize source
deletion or any repository mutation. The final complete object's SHA **must equal
the independently observed target tree SHA**. Missing or incorrect proposals,
including wrong mode, fail that comparison. Compare-file completeness is never
assumed: only the final cryptographic identity admits the reconstructed tree.

Use `--output-raw-tree NEW_PRIVATE_FILE` to retain the admitted bytes. Existing
output files are refused. A publication adapter must consume the complete raw
bytes and independently verify the Git object identity against its own native
parent-tree observation. The compact JSON receipt is a useful handoff, not a
replacement for those bytes or the native root binding. Pass the complete
admitted bytes to the connected publisher's optional `retained_trees` input;
its [call contract](CONNECTED_GITHUB_PUBLISH.md#reuse-complete-tree-bytes-for-a-large-directory)
independently hashes/parses them and binds their path and SHA to the publisher's
own native base traversal before using any previous type, mode or blob.

Bounds: 16 MiB of input tree bytes and 200,000 entries. Names must be immediate,
strict UTF-8 names. Duplicate names, malformed records, noncanonical Git order,
unobserved target hashes and requested symlink/gitlink/directory leaves are
refused. An absent requested leaf is reported only after validating the complete
object. Output contains only explicitly requested names, never the whole private
tree. Select public repository paths for public receipts.

## Actual consumer execution — 2026-10-04

The connected reader observed main `8ebc4d3ad3bbe9a79502785542b922c6b0f877f8`,
root `4174df414ffd902d427367df5d80fa13c59846c0`, and its immediate `p` tree
`26cc2a5332d6b315b09d120cc1e0bbdf1d5ffa52`. The root response was complete:
1,002 entries, `truncated=false`.

The retained previous `p` object `d3d3d5cd98c179d2863a2817c565278b78b9ae0c`
and one exact source-blob update reconstructed that current `p` object:
3,513,744 bytes, 56,000 entries, complete Git SHA match. It proved the previous
Resource Master page is regular `100644`, blob
`d3d20ec1c725de7d9900e44bc6e2acf52122d6e8`, and the new activation-page leaf
is absent. This supplied exact preimage evidence for a real canonical publication
without transporting the full native tree or guessing previous mode/type.

Direct source execution also rejected changed raw bytes, missing source update,
wrong proposed mode, path traversal and malformed duplicate input. Re-reading
the recovered current bytes without patches produced the identical proof.
No fixture, test file, workflow, provider replay or full repository build was
added. No claim is made about adapter integration, deployment or future main.
