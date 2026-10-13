# Complete profiler reports and action parity

Status: recovered implementation. The validation below was completed in the original source session and was not repeated during integration.

## Existing failure

At PR10201 source blob `031f14ba3e15dd438f248a58a5f1143fc45f0d4b`, two
syntactically valid child reports can omit action/source/input identities yet
return `instrumentation_action_parity=true` and parent exit 0. Missing fields
compare equal as None. The reader also accepts missing per-action identities,
and parity does not compare the per-step action hashes.

The retained real-child witness returns this false success. A second witness
runs the actual profiler and unchanged TANDEM timing helper: a controlled actor
registers a shutdown hook that removes the final action-sequence digest from an
otherwise complete report. Both baseline workers exit 0; the baseline supervisor
still reports parity. These are constructed failure controls, not allegations
about any historical TITAN result.

## Repair

`read_child_report` checks completeness only for status=complete: schema, requested
mode, action/profiler/timing digests, input identity and count, runtime/direct-load
source identity shapes, timing identity agreement, uninterrupted zero-based call
steps, and per-call action hashes. An error cannot simultaneously claim completion.
Existing invalid-report sidecars retain original bytes and hashes. Ordinary actor
errors stay original errors. An unchanged-source=false observation stays visible
and prevents parity; off-policy expected-action mismatches remain valid evidence.

`supervise` additionally compares ordered (step, action_sha256) records rather
than relying on equal aggregate hashes alone. No worker, loader, policy, timing,
process count, default timeout, or retry behavior changes. PR10201 readable-output
handling and the existing timeout-byte sidecars remain intact.

The existing transport-only positive test now supplies a complete schema with
per-pass modes instead of placeholder digest strings. Its assertions are retained.
No production authentication, signing, or new reporting framework is introduced.
This checks structural completeness and internal correspondence, not the honesty
of arbitrary caller-supplied hashes or transitive import identity.

## Execution evidence

Python 3.13.5, Linux cloud container. New suite: 24/24 methods pass. Same suite on
exact baseline: 24 executed methods, 47 failing assertion/subtest records, no errors.
Compatibility: 27 factory/TRACE methods + 14 source-binding methods + 8 legacy
child-report methods pass, giving 73 complete methods including the new suite.
The remaining legacy method's SAME 12 malformed-call inputs/assertions pass in
three disjoint fresh-process partitions. It is not counted as 12 new methods.
Two all-in-one legacy runs exceeded their outer command window; partial logs are
retained. No production timeouts were changed to complete the partitions.

Actual-worker witness: baseline exits 0/parity true after losing aggregate
identities; candidate exits 2/parity false and preserves both exact malformed
reports, including their three completed actions and zero expected-action
mismatches. No real TITAN policy, interpreter, game, seed panel, or hosted CI ran.

## Integration

Base: PR10201 merge f62275d80a8e7a2b6556065d786c82738a5abfd8. Apply the narrow patch,
not an entire verification tree. FINCH's direct-callable worker/parser/command
forwarding and DELTA's finite-timeout parser work stay with their existing owners;
compose those unrelated hunks if they land before this patch. This repair touches
only `read_child_report` and the parity expression within `supervise` in production.
The earlier local binary-output alternative is superseded by PR10201 and is not
part of this delivery.

Consumer: the existing FINCH/TRACE saved-profile CLI. Original source session:
https://chatgpt.com/c/6a9f415f-5564-83ea-aae7-1e6b9ea28748

Run `python -B test_complete_reports.py` beside the repaired profiler. The portable
bundle's README and RUN_CHECKS.py provide individual bounded groups and preserved
before/after logs. Existing historical measurements retain their original sources.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
