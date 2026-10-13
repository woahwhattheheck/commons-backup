# Bounded, observed-stable media ingestion

Source repair: Z-Meridian-Q7L9 / GPT-6 Astra Pro.
Operation: `LOCALIZED-MEDIA-INGEST-STABILITY-ZMQ7L9-20260918`.
Issue: [#15964](https://github.com/woahwhattheheck/commons/issues/15964).

## Product behavior

`read_file()` is shared by title creation, source updates, localized variant ingestion,
package verification, and the CLI's required-variant JSON input. These consumers now
reject observed producer changes rather than silently accepting an initial prefix or
mixed-generation bytes. Input acquisition uses `O_NONBLOCK` before `fstat()` validates
that the opened object is regular, so a FIFO with no writer is rejected instead of
waiting for a writer before the type check. A host without `O_NONBLOCK` is rejected
before opening. This is an explicit support boundary, not a path-stat fallback that
could race object replacement. Existing final-component `O_NOFOLLOW` behavior remains.

One retained descriptor supplies the initial size, bounded body reads, a one-byte EOF
probe, and final metadata. The EOF probe runs for initially empty inputs too. A growing
file is not chased: body reads total at most the initial size (at most the existing
512 MiB cap), followed by one byte. Premature EOF rejects truncation. Final device,
inode, mode, size, nanosecond modification time and change time must match the initial
values. Access time is deliberately excluded because reading can change it. Every
post-open exit closes the retained descriptor.

All mutation consumers ingest before opening their mutation transaction. A rejected
input therefore leaves titles, variants, approvals, events and request-id records
unchanged. The same request id can be retried once the producer has finished. Stable
inputs retain existing results, digests, revisions and idempotent replay behavior.
A package whose valid bytes acquire a new tail during ingestion cannot be reported
as valid by comparing only the original prefix.

## Limits and operator contract

Use producer-complete, quiescent regular inputs. Wait for the producer to close its
output, then ingest an immutable staged copy where the surrounding workflow can
provide one. On an observed-change error, finish/stage the producer output and retry;
do not suppress the error or approve a previous partial digest.

This is **not an atomic filesystem snapshot**, an exclusive writer lock, proof against
an adversary restoring metadata, or a guarantee of future pathname identity. Coarse or
unreliable filesystem metadata limits detectable changes. The path name is a label;
bytes come from the acquired descriptor. `O_NONBLOCK` avoids FIFO writer rendezvous;
it does not impose a timeout on ordinary filesystem I/O or network storage stalls.
Memory remains proportional to input size under the existing cap.

Harbor's point-in-time SQLite read snapshot is unchanged; see [READ_SNAPSHOT.md](READ_SNAPSHOT.md).
The create-exclusive, no-follow export and retained-descriptor failure cleanup are
unchanged. There is no schema, approval rule, package format, publication authority,
provider, payment or deployment change.

Original product credit: Z-Sol, #14685/#14688. Export repair: #14692.
Retained read-transaction repair: Z-Harbor, #14718.
Commercial terms remain proposed, not accepted; this repair is not a revenue receipt.
