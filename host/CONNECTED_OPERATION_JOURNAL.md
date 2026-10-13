# Map operation keys to exact append-only JSON snapshots

`connected_operation_journal.cjs` exports `createOperationJournal`,
`recoverOperationJournalEntry` and `OperationJournalError`. It is an optional
bridge between the existing [operation recorder](CONNECTED_OPERATION_RECORDER.md),
[cloud JSON writer](CONNECTED_EXEC_JSON_JOURNAL.md), [bounded JSON reader](CONNECTED_EXEC_JSON_READER.md)
and [SHA256 helper](connected_sha256.cjs). Existing modules and direct tool
bindings remain available unchanged.

The actual bounded-reader publication retained105 callback snapshots. Recorder
directory and entry keys repeat as state advances, while the writer intentionally
installs unique files. Its caller manually assigned custody filenames. After
runtime state loss, a logical result key alone did not identify that physical
file. This bridge saves that mapping beside each accepted update.

## Retain through the existing recorder

Load the complete identified module sources through the current CommonJS
loader, or the carrier's complete-source loader, then use actual exports:

```javascript
const writer = writerModule.createExecJsonJournal(tools.exec_command, {
  directory: actualFreshPrivateDirectory
});
const journal = journalModule.createOperationJournal(
  writer, shaModule.sha256Utf8,
  {operation_id: actualOperationId, prefix: actualFreshBasename}
);
const recorder = recorderModule.createConnectedOperationRecorder({
  operation_id: actualOperationId,
  entry_prefix: actualLogicalKeyPrefix,
  retain: journal.retain,
  max_calls: 64
});
const recordedTools = recorder.wrapBindings(actualSelectedBindings);
// Pass recordedTools to the existing authorized consumer.
const recoveryLocators = journal.snapshot();
```

The journal injects no execution tool itself. The supplied writer controls file
creation and command bounds; the supplied SHA256 function returns exact
`{bytes, sha256}` for UTF-8 text. All snapshots are private: keys, operation
names and raw values can contain account information or secrets. This module
does not redact or publish them.

Options are `operation_id` (a nonempty label at most256 characters), `prefix`
(a plain ASCII basename at most60 characters), and optional `max_records`
(default10000, integer1–100000). Each retention callback counts as one record,
including repeated logical keys. A recorder invocation normally retains several
records. Choose a fresh writer directory/prefix. This backend does not resume
an old instance or overwrite a saved file.

## Record and index ordering

`retain(key, value)` copies ordinary JSON serialization before its first await,
then assigns a sequence synchronously. It serializes backend writes in call
order, including concurrent recorder invocations. It never mutates the supplied
value or changes the recorder's original returned object.

For prefix P and sequence N, data goes to `P-rNNNNNN.json`; the corresponding
index goes to `P-iNNNNNN.json`. Each record retains schema, operation ID, logical
key, sequence and the complete JSON value. Each index retains the latest
acknowledged record for every logical key, with exact name/path, UTF-8 byte
count and SHA256 of the writer's JSON bytes including its trailing newline.
Earlier revisions remain in their own immutable filenames.

Both writes must confirm the exact name/path/byte count before the callback
fulfills. The index is written after the data record. A saved index cannot
acknowledge its own write: `snapshot().latest_index` reports the locator after
that write returns. Retain that descriptor, operation identity and exact file
names in the existing private durable checkpoint before leaving the active
tool call. Runtime-only `store`/`load` values can disappear when that runtime
resets; they are not the custody checkpoint. Keep each accepted result and its
locator physically retained during the live invocation so recovery remains
possible without repeating a provider operation. The index's
`acknowledged_updates` counts backend updates mapped
by this fresh instance; it is not a count of directory files, provider calls
or successful provider effects.

`snapshot()` returns assigned count, acknowledged updates, latest key locators,
the latest acknowledged index descriptor, and bounded failure metadata. It
contains no recorded raw values. Keys and paths still require private handling.

The bridge uses standard JSON semantics. Undefined object properties and
unsupported JSON representations retain their ordinary JSON behavior; top-level
undefined and unserializable values fail. It does not claim to persist JavaScript
identity, descriptors, Error internals or unsupported non-JSON values. The
existing recorder's serializable error mode remains available. Actual connected
MCP response envelopes are ordinary JSON.

## Recover one known recorded value

Use the latest known private index descriptor and an actual logical key:

```javascript
const reader = readerModule.createExecJsonReader(
  tools.exec_command, shaModule.sha256Utf8,
  {directory: actualSavedDirectory}
);
const recovered = await journalModule.recoverOperationJournalEntry(
  reader, actualSavedLatestIndexLocator, actualResultKey
);
// Optional runtime convenience; recoverable record/index custody already exists.
store(actualRecoveredKey, recovered.value);
text({
  key: recovered.key,
  sequence: recovered.sequence,
  sha256: recovered.record_source.sha256
});
```

The companion first restores the known index using the existing reader, requires
its observed path/bytes/digest to match the saved descriptor, validates the
index metadata and unique logical keys, then restores the selected record
against its own exact indexed locator/digest. Operation/key/sequence must match.
A missing key, mismatching file or incomplete input fails explicitly.
No partial value is presented as recovered.

There is no directory scan, implicit newest-file selection, credential lookup,
provider call, retry or effect resume. Recovery retains standard JSON values
and literal source metadata. It proves correspondence to the supplied saved
index and record bytes, not provider acceptance or current state. Reconcile
any uncertain mutation through its existing canonical provider read before
dispatching another mutation. An intent record never authorizes replay.

## Failures

`OperationJournalError` retains private stage/sequence/key/file names and
available writer receipts, plus its original cause. A record may be installed
when its later index write fails. Callback rejection therefore does not mean
nothing was written. Preserve those exact file names and cause metadata.

A failed update does not enter the latest acknowledged mapping. Later
independent callbacks can use fresh sequences, but no failed write is retried
and no old file is overwritten. The existing recorder reports its own custody
failure and preserves an original returned provider value when applicable.
That exception never authorizes repeating a provider mutation.

## Actual consumer

This new source's own authorized three-file publication uses the real unchanged
publisher and token adapter, with the existing recorder's callback bound to
this backend. The landed JSON writer stores actual requests, raw returned
envelopes and invocation metadata; no fake binding or fixture is supplied.
After merge, the companion consumes the retained merge-result key through the
landed bounded reader, verifies its saved index and record digests and compares
the recovered JSON value with that accepted raw response. It makes no provider
mutation or replay during recovery. Counts and private file locators remain
in the existing operation checkpoint.
