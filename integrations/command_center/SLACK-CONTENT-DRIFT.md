# Slack message-generation consistency

This repair extends the existing bounded command-center reader in `slack_threads.py`.
It does not create another work board, claim service, Slack transport, schedule,
or provider write path. `collectors.py` already imports and calls this reader.

## Failure being repaired

An overlapping Slack page can return the same message timestamp with different
claim text, author, bot identity, subtype, or edit timestamp. The previous reader
only compared `reply_count`, `latest_reply`, and `thread_ts` when deduplicating
pages. It could therefore report complete coverage after silently replacing the
actual work instruction with a different observed generation. History-to-reply
reconciliation had the same gap even when the counts and latest-reply anchors
matched.

The repaired reader captures an immutable tuple of the relevant scalar fields
before the next provider callback. Duplicate message identities are compared
within pages, across pages, and across history/reply reads. Any observed change
makes the affected coverage incomplete with the existing fixed reason
`thread_evidence_changed`. An earlier pagination/error reason keeps precedence.
Validated rows remain available; the last observed row is retained rather than
being described as an atomic or necessarily newest provider snapshot. Incomplete
coverage must not be used to replace unseen work.

## Deliberate equivalences and bounds

A thread-broadcast wrapper and its ordinary reply are the same stable message.
An omitted parent `thread_ts` and an explicit self-root timestamp are equivalent.
Reactions and profile display metadata are not work-instruction generations.
Those representation-only differences do not manufacture drift or extra reads.
Actual text, message author/bot identity, non-broadcast subtype, edit timestamp,
reply counts, latest reply, and resolved parent remain generation evidence.

Read counts, page/thread limits, cancellation, deadlines and the shared request
budget are unchanged. No eager retry or additional provider request is added.
Generation tuples are ephemeral and are not copied into source coverage metadata;
no message text, author ID, raw provider error or credential is added there.

## Reproduction

From the repository root:

```sh
python -B -m unittest -v integrations.command_center.test_slack_content_drift
python -O -B -m unittest -v integrations.command_center.test_slack_content_drift
python -m py_compile integrations/command_center/slack_threads.py integrations/command_center/test_slack_content_drift.py
```

The 21 tests execute the real reader with explicitly synthetic provider responses.
They cover stable overlaps, claim edits with unchanged counts, author/bot/subtype
and edit-marker changes, same-page duplicates, sticky drift across later pages,
root edits between endpoints, changed broadcast replies, normal broadcast/root
normalization, reply-page changes, count growth, missing roots, partial failures,
reason precedence, metadata privacy and reused provider-dictionary observations.

Initial exact-byte execution on September 19, 2026:

- Baseline reader Git blob `7c4609dcd590d24af48957a83a5031753fe6d58e`
  was reconstructed and matched byte-for-byte: 8,975 bytes.
- New suite against that baseline: exit 1, 21 tests, 18 failing assertions/subtests.
- Repaired reader Git blob `0dc7d69a79bfd875ceb51ae7f5ed39a16a0d170f`:
  21 tests passed in normal Python and 21 passed under real `python -O`.
- Test Git blob `0812c7dd4aa93100152a108f5457c75ce5703d11` and repaired
  reader both passed `py_compile`; GitHub blob creation matched the tested bytes.

Broader existing integration regression command, separate from those results:

```sh
python -B -m unittest integrations.command_center.test_slack_threads integrations.command_center.test_collector_response_shapes integrations.command_center.test_collector_pagination_evidence integrations.command_center.test_slack_content_drift
python -O -B -m unittest integrations.command_center.test_slack_threads integrations.command_center.test_collector_response_shapes integrations.command_center.test_collector_pagination_evidence integrations.command_center.test_slack_content_drift
```

## Limits

This is consistency of observed message generations, not an atomic Slack snapshot,
whole-workspace coverage, authenticated ownership, or a distributed claim lock.
Messages edited after their last observation can still change. Reading an empty
reply-as-root is not evidence that the original order is unclaimed: resolve and
read the original order root, follow bounded pagination, and reconcile the live
claim before posting. This repair does not change the native connector's thread
lookup behavior; separate root-resolution work retains its own ownership.

The initial narrow execution is not a full SQLite collector-suite pass, hosted CI,
a deployment receipt or a `swarm_review.py` merge verdict. Current integration and
provider evidence must be checked separately before finalization.

Operation: `slack-content-drift-rivet9j2c-20260919`.
Builder: ZZ-RIVET-9J2C / GPT-6 Astra Pro. Preserve the existing reader's authorship.
