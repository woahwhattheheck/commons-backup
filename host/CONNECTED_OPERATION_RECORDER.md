# Recording connected operations without losing request, result, or error custody

`host/connected_operation_recorder.cjs` provides one caller-owned recorder for already-authorized native bindings and local collector/projector operations. The caller injects its existing private retention function. The module has no filesystem, network client, credential lookup, discovery, retry, route selection, sleep, or provider policy.

The concrete motivation is repeated orchestration bookkeeping. An earlier real Slack backlog intake retained its native responses, but local projector exceptions passed through `Promise.allSettled` lost their Error name/message when the result was serialized. Another intake manually retained four pre-provider decimal-timestamp errors. Existing publisher guidance also had to explain keeping known journal locators attached to receipts after an original native envelope could no longer be located.

This helper records those boundaries directly. It does not recover the missing exceptions, replay the old inputs, or infer whether any provider accepted a call.

## Existing capabilities and scope

The inspected current host directory returned 977 entries. Relevant existing implementations were:

- `connected_publishing_tools.mjs`, blob `4af2b96b9481d470d336b5bd8324ae7d8126c783`: tool inventory and schema inspection.
- `connected_tool_request.py`, blob `5962de26bcfc3515f4cd81864bc1ba83839af440`: prepares search/read arguments for the existing Python router.
- The existing router guide, blob `1b9cd99fbf8a5a2680ede093fd1377d829fd3748`, describes a separate filesystem-backed dispatch/resume journal, provider classification and quota/fallback behavior.
- The GitHub publisher guide describes manual native journaling and stable private receipt locators. The current publisher has progress callbacks; the Slack collector has a returned-response callback and retained page responses.

Those contracts do not supply a standalone pure-V8 wrapper for both arbitrary supplied bindings and local exceptions. The existing helpers, exports, dispatch, pagination, retry policies and return shapes are untouched. This recorder does not adopt the Python router's fallback behavior or replace any provider-specific collector.

## Interface

```javascript
const {
  createConnectedOperationRecorder,
} = require('./host/connected_operation_recorder.cjs');

const recorder = createConnectedOperationRecorder({
  operation_id: actualOperationId,
  entry_prefix: freshPrivateEntryPrefix,
  retain: (key, value) => store(key, value),
  max_calls: 64,
  serializable_errors: true,
});

const recordedTools = recorder.wrapBindings(selectedNativeBindings);

const collection = await recorder.run({
  kind: 'local',
  name: 'collectSlackPages:current-window',
  request: {request: actualCollectionRequest},
}, ({request}) => collectSlackPages(recordedTools, request));

store(actualCollectionKey, collection);

const projection = await recorder.run({
  kind: 'local',
  name: 'projectSlackCollectedMessages:headers',
  request: {
    collection_key: actualCollectionKey,
    options: actualHeaderProjectionOptions,
  },
}, ({collection_key, options}) =>
  projectSlackCollectedMessages(load(collection_key), options));

store(actualReceiptKey, {
  projection,
  operation_recording: recorder.snapshot(),
});
```

These are integration examples using actual caller-supplied requests and keys, not executed fixtures. In a pure V8 carrier without CommonJS loading, the caller can adopt the complete independently identified source through its existing source-loading mechanism. The recorder does not load itself or fetch another dependency.

Options:

| Field | Contract |
|---|---|
| `operation_id` | Existing caller operation label, 1–256 characters without control characters. |
| `entry_prefix` | Fresh caller-owned private key prefix, 1–200 characters without control characters. |
| `retain(key, value)` | Required synchronous or promise-returning retention callback. Fulfillment is an acknowledgement, not a durability proof. |
| `max_calls` | Integer 1–1,000, default 128. Includes native and local operations in this recorder. |
| `serializable_errors` | Boolean, default false. Opt in to JSON-serializable wrappers for recorded invocation/preparation errors. |

No automatic prefix collision lookup or cross-instance deduplication is performed. Use a new prefix for a new operation and keep the exact prefix/directory key on its private receipt. Reusing an old prefix can overwrite old records in a caller's store; this module does not resume an earlier operation.

`wrapBindings(map)` wraps only the supplied own enumerable function bindings. It discovers nothing and verifies no name against a service registry. Each wrapper delegates once to its supplied function with the copied arguments. Functions whose `this` context matters should already be bound by the caller; the wrapper otherwise uses the supplied map as receiver.

`run({kind, name, request}, invoke)` calls `invoke(copiedRequest)` once after its pre-invocation records are acknowledged. `kind` is either `binding` or `local`. For a binding, request means the actual arguments passed to that binding. For a local step, it is an explicit caller-supplied input/provenance descriptor; the recorder does not claim to capture every value in a callback's closure. For large retained collections, pass their exact private locator plus actual projection options, as above.

`snapshot()` returns bounded directory/entry metadata: names, IDs, phases, locators and acknowledgement states. It contains no request arguments, raw results or error-message text. Caller-chosen operation and step names may themselves be sensitive; this is not a public-output or redaction guarantee.

## Ordering, keys, and concurrency

Indices are assigned synchronously before any await. Completion order can differ from assignment order. Each call uses its own index, which is preserved through settlement.

For prefix `P` and call index `N`:

| Key | Retained value |
|---|---|
| `P_directory` | Operation identity, prefix, highest assigned count, limits, and exact key patterns. |
| `P_call_N_request` | Operation/call identity, kind/name, and the copied request. |
| `P_call_N_entry` | Metadata, first as invocation intent and later as settled metadata. |
| `P_call_N_result` | Complete returned value, unchanged. |
| `P_call_N_error` | Bounded serializable description of a thrown value. |

The directory is retained before invocation. The request is copied before the first await, then retained before invocation. The intent entry is acknowledged before the function is called. A persisted intent records `invocation_started: null`: interruption at that point does not establish whether the function or provider ran. A thrown pre-invocation custody error retains the known in-memory fact that invocation has not begun.

All injected retention callbacks are serialized through one promise queue. This prevents later metadata writes from overtaking earlier scheduled writes. The native/local invocations themselves may overlap. A rejected retention callback does not poison the queue for later independent calls; it remains a failure of the affected call.

After a return, the full value is retained before any caller receives it. After a throw, its serializable error description is retained. The final metadata write must also be acknowledged before the helper returns or rethrows the original invocation error.

A saved metadata record cannot acknowledge its own write. It omits that self-acknowledgement; the returned in-memory snapshot reports the callback's acknowledgement after settlement. Neither assigned IDs, intent records, nor callback fulfillment prove provider dispatch, provider success, durable storage, or process survival.

## Request-copy contract and bounds

The request snapshot is copied and recursively frozen before retention begins. The original caller object is not mutated. A later mutation of the original cannot alter the invocation's arguments or recorded intent.

Supported inputs are plain JSON values: null, booleans, strings, finite numbers other than negative zero, dense arrays, and objects with plain or null prototypes and enumerable data properties. Undefined, functions, symbols, BigInt, sparse/extended arrays, cycles, accessor properties, non-enumerable object data, and custom-prototype objects are rejected rather than silently omitted or coerced.

Fixed request-copy bounds are 100,000 visited nodes, 64 nesting levels, and 16,777,216 UTF-16 characters across property names and string values. These are local structure/text budgets, not a wire-byte limit, provider limit, elapsed-time limit, or proof of peak memory use. Shared noncyclic references are copied as repeated JSON values.

The original returned value is not copied, frozen, inspected, filtered, redacted, or truncated by the recorder. The injected retainer must preserve it without mutating it. It decides whether that value can be retained; a rejection is reported as a custody failure. No universal raw-result size limit is silently applied.

A request-copy error is a recorder preparation failure, before invocation. It is recorded when retention is available. Invalid factory/wrapBindings configuration occurs before a recording operation exists and throws normally. Descriptor validation or the call-count bound has no assigned call record; with the error-wrapper opt-in it still produces a serializable diagnostic with `call: null`. No rejected setup invokes a binding.

## Errors and persistence failures

A thrown Error's name, message and cause are not reliably represented by serializing the Error object itself. This recorder retains selected explicit fields instead. Each string field is limited to 2,048 UTF-16 characters with length/truncation metadata; at most three cause edges are followed. Cycles, depth limits, absent/undefined, null, non-string fields and unreadable properties remain distinct. Arbitrary properties, stacks and response bodies are not enumerated. Primitive throws retain their type; strings/numbers/booleans also retain a bounded message representation.

Those descriptions are diagnostic extracts, not complete native envelopes and not a privacy filter. Error messages may contain sensitive text. Keep them in the private operation store.

| Observation | Recorder behavior |
|---|---|
| Binding returns an MCP error envelope | Retain and return the same object; no classification or success inference. |
| Local projector or binding throws; all custody succeeds | Retain its serializable description, then rethrow the same original value by default. |
| Same throw with `serializable_errors: true` | Throw `ConnectedOperationRecordingError` with a plain `toJSON()` diagnostic; original error remains privately accessible as `cause` and `original_error`. |
| Retention fails before invocation | Reject with a distinct custody error; do not invoke the function. |
| Retention of a returned value or final metadata fails | Reject; never return successful recorded completion. The original returned value remains privately accessible as `returned_value`. |
| Retention fails while recording an earlier thrown error | Reject with both failures preserved separately: private `retention_error`/`cause` and `original_error`, with bounded diagnostic descriptions. |

Custody errors always use the typed wrapper, regardless of `serializable_errors`, because retention failure is a distinct failure from the invocation outcome. Their diagnostic identifies the failed key/slot and whether an original returned value or error is available privately. A callback may have partially stored data before rejecting; `not_acknowledged` does not mean that no bytes were stored.

The wrapper's private original values are non-enumerable and excluded from its `toJSON()` output. Do not append them to public output. With the opt-in, ordinary JSON serialization of `Promise.allSettled` results preserves the wrapper's bounded diagnostic. Without the opt-in, the original rejection identity is preserved, and the retained error key/directory remains the source of serializable diagnostics.

For a thrown native binding, `invocation_started: true` means the supplied JavaScript function was called, not that a provider received a request. A pre-provider schema failure, transport failure, or service failure is not classified by this module. For any returned native result, `provider_outcome: not_assessed` remains explicit. Local steps use `not_applicable`.

A post-result custody failure can occur after a successful external write. Its exception is not authority to repeat that write. Preserve the original value/error handles and apply the existing operation-specific reconciliation rules. The recorder itself never retries an invocation, retries a failed retention callback, switches routes, or rewrites an earlier provider result.

## Privacy and actual first consumer

Use the recorder only for already-authorized operations and private custody. It does not clear any message/body/source hold. Native payloads and local collection results may contain private material; this helper deliberately retains them in the injected private store and never writes them to a repository or public channel.

The intended first consumer is a genuinely new root intake: independent Slack windows and a later Gmail query, with native bindings plus local collector/projector steps wrapped. Its raw mail/Slack data remains private. No historical Error object, failed request, completed collection, publication or held body is replayed.

At publication time, the new recorder's paths are source-reviewed but unexecuted. No synthetic fixture, exception injection, persistence-failure simulation, test suite, benchmark, shell or executor was used. A later real consumer may record its exact counts and exercised paths operationally; successful calls do not establish thrown/error/custody-failure branch coverage. Existing receipts, original missing-error gaps and provider-specific holds remain unchanged.
