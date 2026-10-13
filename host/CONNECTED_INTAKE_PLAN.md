# Plan one connected intake batch without dispatching it

`host/connected_intake_plan.cjs` exports the pure CommonJS function
`planConnectedIntakeBatch(input)`. It selects a bounded number of distinct
pending request indices, keeps caller-reported exact holds excluded, and reports
a caller-chosen pause separately from provider timing. It never calls a tool,
reads a clock, waits, retries, rewrites a request, or stores state.

This addresses an observed caller problem: independent GitHub intake requests
were dispatched concurrently and repeatedly met secondary limits. The existing
operation recorder correctly preserves request/result/error custody; its
serialization tail orders retention callbacks, not native invocations. The
existing issue-search helper sequences pages within one search and deduplicates
returned issue IDs. Neither of those inspected surfaces plans a batch of
independent requests against caller-held exact requests.

Those existing helpers are unchanged. This module is a separate planning step.
It does not classify GitHub errors, introduce a publication protocol, or replace
the caller's source, privacy, authorization, and failed-route dispositions.

## Input

Supply one plain object with these fields:

| Field | Meaning |
| --- | --- |
| `pending` | Ordered array of request descriptors to consider now; required. |
| `held` | Array of exact request descriptors the caller says remain held; required, including an explicit empty array if that is the actual caller input. |
| `observed_at_ms` | Caller-supplied nonnegative safe integer epoch milliseconds; required. The helper does not obtain or authenticate this observation. |
| `local_pause` | Omit or use `null` when no chosen pause is supplied. Otherwise `{until_ms, label?}`, with nonnegative safe integer epoch milliseconds and an optional bounded label. |
| `max_selected` | Integer 1 through 128; defaults to 1. This bounds this plan's selection only. |

Each request descriptor is `{operation, args, id?}`:

- `operation` is the exact binding name as a nonempty string.
- `args` is the complete plain JSON argument object the caller intends to pass.
- `id`, when supplied, is a bounded caller-owned identifier. Matching uses only
  operation and arguments; IDs do not change request identity.

Use actual retained pending descriptors and hold records. Keep their original
request/envelope locators in private caller custody. The report does not include
argument values, native error text, response bodies, credentials, or the original
envelopes. Optional IDs and pause labels are copied into the report; supply only
metadata appropriate for that report's destination.

The module does not verify that a binding is read-only or authorized. Its
intended consumer is already-authorized read-only intake. A selected descriptor
is not permission to invoke a tool or to expand its response.

## Exact matching and bounded selection

Request equality is the binding name plus structural equality of plain JSON
arguments:

- Object member order is ignored at every depth.
- Array order, exact JavaScript string contents, and all supplied JSON values
  remain significant.
- Missing members and explicit `null` remain different.
- URL strings and query strings are never parsed, decoded, reordered, trimmed,
  or otherwise normalized.
- Operation aliases and alternative routes are never equated.
- JSON's numeric representation applies: JavaScript `-0` and `0` both encode
  as `0`. This compares the supplied JavaScript values, not an earlier textual
  representation or precision that may already have been lost.

This is an exact-argument aid. A differently written request may target the same
held resource; lack of an exact match does not clear an existing semantic,
source, privacy, or provider hold. The caller retains those wider dispositions.

Each pending record receives one disposition, in this order:

1. `excluded_exact_hold`: at least one supplied held descriptor matches. The
   first matching held source index and the matching record count are retained.
2. `duplicate_pending`: an earlier pending descriptor has the same exact
   identity. Its index is retained.
3. `deferred_local_pause`: the caller's pause end is later than
   `observed_at_ms`.
4. `deferred_batch_limit`: the requested selection count has been reached.
5. `selected`: its original index is included in `selected_indices`.

Every record also retains an earlier duplicate index when one exists, including
when the exact-hold disposition takes precedence. Duplicate hold records are
counted; the module does not erase the caller's originals.

A duplicate disposition does not mean the first request ran or succeeded. The
first request can itself be held or deferred. Preserve the original pending
intent and link dependants to its eventual actual outcome. Likewise, a deferred
record remains pending; this function neither completes nor removes it.

Retain the original input JSON beside the report. Source indices describe that
specific supplied array and argument version. Do not apply them to reordered or
edited pending descriptors; such work is a new input requiring a new plan. The
report deliberately emits no argument copy or request hash.

Selection is advisory and stateless. To use a one-request batch, dispatch only
that selected original descriptor through the existing recorder, await and
inspect the actual outcome, update caller custody, and plan the still-pending
work with a fresh observation if useful. On a newly observed provider failure,
preserve the exact request and outcome and apply the caller's existing stop/hold
policy. There is no automatic continuation or retry.

Multiple callers can independently select work at the same time. This function
provides no cross-agent lock, reservation, global rate limit, fairness policy,
minimum spacing guarantee, or protection against a caller disregarding a plan.

## Caller-chosen pause is not a provider reset

A supplied pause is reported as `active` when `until_ms > observed_at_ms`,
otherwise `elapsed`. The report retains both integers and the signed
`until_minus_observed_ms` difference. It identifies the pause as
`caller_chosen` and provider reset as `not_inferred`.

An elapsed pause does not establish service recovery, available quota, or
permission to retry a held request. Exact holds are checked before the pause and
remain excluded after it elapses. A later hold received after planning remains
the caller's responsibility. There is no timer or automatic future dispatch.

Actual fleet secondary-limit receipts motivating this work supplied no
Retry-After/reset metadata. The shared quiet interval ending 2026-10-06
04:31:23 UTC was a conservative local choice, not a GitHub reset time.
Three exact held request tuples were transferred by the root caller from the
Delivery custodian: binding `mcp__codex_apps__github_search_prs`, repository
`Protocol-Guild/PayD`, state `all`, topn `20`, and respectively the literal
queries `391`, `186`, and `187`. This module accepts caller-reported
descriptors; it cannot authenticate their original native outcomes.
Earlier in-memory custody loss is not repaired by this report.

## Bounds and failures

The implementation accepts at most 128 pending and 512 held records. Operation
names are at most 256 UTF-16 code units, optional IDs 128, and pause labels 256.
Request identity encoding is bounded to 65,536 UTF-16 code units per request and
1,048,576 across the full input, including repeated pending/held descriptors.
JSON depth is at most 16; each argument object is bounded to 4,096 visited value
nodes. The report's `input_request_characters` charges the canonical encoding
of operation plus arguments; it is not wire-byte size or original JSON text
length.

Plain objects, dense arrays, strings, finite numbers, booleans, and null form the
argument contract. Undefined, functions, symbols, accessors, nonenumerable data
members, cycles, sparse/extended arrays, class instances, and nonfinite numbers
are rejected. The API accepts ordinary data objects, not proxies or objects with
behavior. Unknown option/descriptor fields are rejected. Input data is read
without modification; no original descriptor or argument object is returned.

The function validates all supplied descriptors before returning a selection.
A malformed or over-budget input throws a local TypeError or RangeError; it
does not return a partial plan or call any provider. Use the existing operation
recorder around this local boundary when serializable exception custody is
needed. Do not treat a local failure as a provider response.

The metadata report includes source indices, optional IDs, binding names,
dispositions, duplicate/hold indices and counts, selection counts, pause
metadata, and explicit zero-dispatch/no-persistence statements. It includes no
request arguments. It does not infer snapshot coverage, complete hold coverage,
authentication, provider success, owner absence, or source eligibility.

## First actual consumer

The frozen 10,969-byte source was banked with Git blob identity
`9c8ad88fa1faa65c2f079ad2a51693092c389382`. The native create-blob SHA and an
independently computed UTF-8 Git blob SHA agreed before the first use.

At 2026-10-06 05:40:14 UTC, the root caller's two genuinely pending frontend
reads were planned once: a named-main observation and the already specified
path-scoped commit-history request for the accessibility configuration. Neither
request was dispatched by this invocation. The input also contained the three
exact caller-reported held tuples described above and the chosen 04:31:23 pause
end. No failed request was replayed and no fixture was constructed.

With `max_selected: 1`, the result retained both pending records:

| Actual output | Value |
| --- | --- |
| Selected source indices | `[0]`, the named-main read |
| Deferred by batch limit | Source index `1`, the path-scoped history read |
| Supplied / unique held descriptors | `3 / 3` |
| Exact held matches among pending requests | `0` |
| Duplicate pending requests | `0` |
| Local pause | `elapsed`; signed difference `-4131000` ms |
| Charged request characters | `668` |
| Input JSON after invocation | Exact unchanged |
| Native provider calls from planning | `0` |

Private custody keys are retained by the author for input, original JSON,
clock, complete result, and receipt. The public guide carries no response bodies.

The root caller subsequently reported that it dispatched only the selected
named-main read under the recorder. At 05:42:43 UTC it independently planned the
still-pending one-request history batch once, retaining the same three holds:
selected index 0, 556 charged request characters, unchanged input, and no planner
I/O. The native history read occurred afterwards. Both actual reads completed;
the original two-request calculation was not rerun. This downstream observation
is caller-reported operational use, not provider evidence produced by the planner.

Only this normal planning path, elapsed-pause reporting, and one-record batch
deferral were exercised. Exact-held matches, duplicate elimination, active
pauses, malformed/oversized input, and thrown paths remain unexecuted. No
throughput timing, provider recovery, avoided-call measurement, or global
scheduling guarantee is claimed. Future genuinely pending requests may use the
API; accepted collections and failed routes should not be replayed to exercise
branches.

## Source custody and integration

The capability assessment used complete immutable Commons sources:

- Operation recorder:
  `bf0e3e56eae2bbc5da87ea8d92bd3fb04dd34a11`.
- Existing issue-search helper:
  `d279f18c22384d45f218384b7cee4c3f661724d5`.

They remain byte-for-byte unchanged by this publication. The new module uses
only built-in JavaScript operations and has no dependencies, executable CLI,
filesystem, network, or environment-variable access.

The source and guide form the deliverable. Validation is source inspection,
exact artifact identities, and the single actual consumer above. No test
fixtures, synthetic errors, provider replay, runtime benchmark, or application
execution were performed.
