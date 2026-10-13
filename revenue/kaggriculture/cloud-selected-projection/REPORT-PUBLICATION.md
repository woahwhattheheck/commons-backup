# Combined-report provenance and atomic publication

## Behavior

`build_report` preserves optional `SOURCE-SNAPSHOT.json.source_context` and checks its consistency with the recorded checkout. The event SHA must equal that checkout. PR merge context retains valid head and base references without substituting the source branch for the executed merge. Additional context fields are preserved. Invalid context adds ordinary problems and unsuccessful status while retaining available counts and source evidence. Legacy snapshots without context keep the previous output shape. These are declaration-consistency checks, not independent execution attestation.

CLI output stages a unique sibling file, writes and flushes complete UTF-8 text, fsyncs it, and replaces the target only after those steps succeed. Pre-replacement exceptions preserve a prior complete report. Existing file modes, the caller's umask for new files, existing symlink follow-target behavior, stdout output and unsuccessful-report exit status are retained. Missing parent directories are not created. Cleanup does not mask the original failure.

A hard kill can leave an unreferenced temporary sibling. This provides atomic target visibility, not a multi-file transaction, a concurrency lock or directory durability across power failure. Concurrent writers remain last-replacement-wins. The process fixtures were executed on Linux; no native Windows result is claimed.

## Source composition

The original prepared patch was based on reporter blob `46db299630894a75c8609604c75986f5ae752dec` at `967ffc169748d431f2d199838d0a61ed6ee4c1e9`. It is now reconciled with BIRCH's landed adaptive-context/lazy-suite change at `bb86959eddee8398c784e771ca317fefb3581193`, reporter blob `a2dcbaccc53c5aee0501b0a4a678640e6b11a731`, read from main `58c9c46ae321271634b26100938fb598da32f419`.

The resulting reporter blob is `eb53c34a179bb8fe3627d990dce0ab8e809bea02`, SHA256 `8afbc2a406f6d162ffd4385c72979ec134306d625839f59bc5f42656ae84f2ea`. BIRCH's suite declarations, source bindings and optional API remain intact. The publication test blob is `c2605359495d499f1d51c23ce08fbc54fa57c9f9` and is unchanged from the prepared delivery. Only the existing reporter, this note and that new test file are in this change. No workflow, policy, optimizer, timer, original suite or historical artifact is changed.

## Focused execution

From this directory:

```sh
python3 -B -m unittest test_report_publication -v
```

All 31 methods pass on the reconciled source, with zero failures, errors or skips. They cover optional source context, malformed or conflicting context, legacy output, input immutability, permissions, write/flush/fsync/replace failures, descriptor cleanup, Unicode, stdout and failure-result publication. Two actual child-process SIGKILL fixtures verify preservation of an old complete target and non-publication of a new partial target. Each child is killed and reaped by the test parent.

The retained original-source control from the prepared delivery fails 20 distinct methods (41 assertions/subtests), with zero execution errors. The 36 retained package members were hash-checked before reuse. These are synthetic parser and filesystem/process fixtures, not game results or evidence that a hosted job used the wrong source.

## Saved-output compatibility

The reconciled reporter and the exact BIRCH baseline were compared on nine unchanged, provider-digest-bound artifact ZIPs. Every pre-existing decoded output field is equal. The three snapshots containing source context preserve it exactly. Recorded method counts remain 37, 51, 79, 117, 159, 154, 206, 210 and 282. The old 37/51 artifacts remain incomplete under the current six-suite consumer contract; their historical accepted test scopes are not relabeled as failures.

This is reanalysis of saved outputs, not new executions of their tests, agents or games. The latest reused 282-method input is artifact `10039313918` from run `34182300969`, SHA256 `fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b`. Earlier hashes, raw logs and all nine archives remain in the retained ATLAS delivery package.

The normal PR workflow result is recorded separately in the PR receipt when available. The new 31-method file has an explicit command above; it is not silently added to existing hosted suite totals. This change does not claim full-repository CI, gameplay strength, selected-policy promotion, new seeds, Kaggle submission or owner-PC execution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
