# Observe a lost operation-journal index locator

`connected_operation_journal_locator.cjs` exports
`observeOperationJournalLocator(execCommand, reader, options)` and
`OperationJournalLocatorError`. It observes the highest complete matching index
sequence in one explicitly supplied local cloud directory/prefix, then restores
that index through the existing [bounded JSON reader](CONNECTED_EXEC_JSON_READER.md).

The [operation journal bridge](CONNECTED_OPERATION_JOURNAL.md) records exact
physical locators beside repeated logical keys. Its own actual publication
created 105 immutable index revisions. A runtime reset can remove the latest
in-memory descriptor while those complete files remain. This optional observer
restores an observed locator without repeating any recorder or provider call.
The bridge, reader, writer and publisher stay unchanged.

## Explicit use

Load the complete identified source through the ordinary CommonJS/source loader
and inject the existing cloud execution binding and reader:

```javascript
const reader = readerModule.createExecJsonReader(
  tools.exec_command, shaModule.sha256Utf8,
  {directory: actualSavedOperationDirectory}
);
const observed = await locatorModule.observeOperationJournalLocator(
  tools.exec_command, reader, {prefix: actualSavedJournalPrefix}
);
// Runtime convenience; retain observed locator custody before this call ends.
store(actualPrivateLocatorKey, observed.index_locator);
text({
  sequence: observed.index_locator.sequence,
  indexes: observed.observation.matching_indexes,
  bytes: observed.index_locator.file_bytes
});
const recovered = await journalModule.recoverOperationJournalEntry(
  reader, observed.index_locator, actualRecordedResultKey
);
```

The caller expressly chooses this local directory observation. It does not infer
a directory, choose a provider account, discover credentials or automatically
resume an operation. Print metadata only. Full returned index/execution content
and caller-chosen keys remain private.

Retain the exact directory/prefix and complete observed `index_locator`,
including its operation identity, in the existing private durable checkpoint
before leaving the live tool call. Physically retain the full observation and
reader responses there as well. The example's `store` call is runtime convenience;
its value can disappear after a runtime reset and does not save that checkpoint.
Saved observation custody does not establish the original writer's acknowledgement.

## Exact observation and scope

One bounded quoted Python3 command enumerates the supplied directory. Every
directory entry counts toward the listing bound, including unrelated files
and pending directories. Matching names are exactly
`<prefix>-iNNNNNN.json`, with sequence 1–100000. Matching nonregular files,
out-of-range sequences or no matching complete file fail explicitly.
Incomplete pending directories are outside that completed filename pattern.

The command selects the highest matching sequence, binds its descriptor identity
to the listing observation, hashes its complete bounded bytes and checks the file
again. Directory device/inode/mtime/size must also stay identical across this
observation. Any concurrent directory change stops the operation; there is no
retry or partial newest-index claim.

The existing reader then reconstructs that selected file and verifies its full
SHA256/byte count. Its exact path and observed device/inode/nanosecond mtime/size
must match the command observation. The parsed index schema, operation ID,
prefix, directory, index filename and sequence must match before a locator is
returned. Device/inode/timestamp values remain decimal strings.

The result describes the highest matching completed sequence at that stable
local listing boundary. It does not claim that the directory will never change
afterwards, that every index revision exists, that pending writes completed, or
that the selected index write was acknowledged by an earlier process.
This observed descriptor is distinct from the bridge's returned producer
acknowledgement. The later recovery helper validates indexed record metadata
and exact recorded bytes; neither helper settles a provider effect.

## Bounds and returned data

| Option | Default | Bound |
| --- | --- | --- |
| `prefix` | required | Plain ASCII basename, 1–60 characters. |
| `max_entries` | 10000 | Integer 1–1000000; every directory entry is counted. |
| `max_index_bytes` | 8388608 | Integer 1–67108864; selected file's complete size. |
| `max_command_bytes` | 48000 | Integer 8192–60000; complete UTF-8 command including syntax/path. |

The existing reader's file bound also applies. Raise both explicit bounds for
a larger known index. Unsupported options and malformed paths fail before
execution. Execution requires Bash/Python3 standard libraries and a completed
`exec_command` response with exit 0/output and no process session.
No package install, shell expansion of input, filesystem write or provider
operation is performed.

Success returns `status: "observed"`, an exact `index_locator`, literal file and
directory identities, complete digest, listing counts and command byte count.
`execution_response` and `retained_index` preserve the actual complete supplied
execution response and reader result for private custody. Nothing is mutated.
Scope remains `producer_acknowledgement_and_provider_outcome_not_assessed`.

Failure throws `OperationJournalLocatorError` with observed stage/metadata and
cause. An incomplete/nonzero command's original result is retained on the cause
when available. Preserve that private evidence; do not interpret a read failure
as authority to repeat a provider write.

## Actual consumer

The actual closed operation-journal publication directory supplies the real
input: 261 directory entries, 105 matching index revisions and highest sequence 105. The observer
uses the real cloud execution binding and landed reader to restore its known
20,707-byte complete index in eight local commands (one observation plus
seven reader commands for six chunks). The observation command is 2,546 UTF-8
bytes. Its observed locator/digest matches the already accepted producer
descriptor; the literal merge-response key's indexed file/bytes/digest match
the accepted record source. This is a new local recovery consumer; no earlier
provider operation is replayed.
