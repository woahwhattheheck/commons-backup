# Public-bank source binding

The public opponent bank checks a source file's SHA-256 before constructing the official file agent. The pinned official loader separately reads that file and compiles its retained text on the first action. A file change between the two reads could therefore execute a different program while the bank retained the first file's identity.

`make_agent` now captures and hashes one byte snapshot, then compares the official loader's retained program with that snapshot before calling the unchanged `get_last_callable`. The comparison mirrors the loader's UTF-8 universal-newline conversion; newline-only changes with identical compiled text are equivalent. Later file changes do not invalidate an already captured matching program. No per-action file reread is added.

The original official loader, generated adapters, argument slicing, assignment labels, dependency versions, and all opponent policy bytes remain unchanged. This change binds the top-level policy program; it is not a snapshot of arbitrary transitive imports or runtime data reads.

Validation: 16 new methods plus 8 unchanged bank methods pass. The exact predecessor fails 6 assertion records in 5 of the new methods, with no test errors. Six 32-decision official-engine fixtures, using the original raw-file adapters for COK and both lonespear modes in both positions, produce 192 identical action pairs. These are short loader-continuity fixtures on the already-spent development seed 9771001, not full games, competitive evidence, or proof about the historical benchmark's source identity.

Run from the repository with its existing `cloud-pack` closure:

```sh
python -m unittest discover -s revenue/kaggriculture/cloud-opponent-frontier/runtime/public_bank -p 'test_bank*.py' -v
```

The accompanying delivery evidence provides the exact original inputs, a self-contained reproduction command, and baseline/final logs. This repair does not create a new T07 opponent, panel, source bank, game result, workflow, or canonical TITAN package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
