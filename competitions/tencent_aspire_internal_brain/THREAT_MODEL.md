# Threat model — Internal Brain local prototype

## Trust boundary and protected information

The engine applies a declared tenant's role, permission, clearance and document policy to individual operations. Authorized retrieval citations carry source provenance, `content_sha256` for content bytes and `document_sha256` for the whole normalized record. The record digest binds source URI, version, classification, allowed roles, labels and content together. Ingestion preserves document identity, and retained session outcomes and audit evidence support deterministic replay.

The local filesystem operator is trusted with the entire bundle. The operator can read all documents, edit policy, select a declared actor and replace artifacts. `validate` prints a full normalized bundle; updated bundles and retained runs also carry full document data. The CLI is not a security boundary between that operator and tenant information.

The supplied tenant, users and documents are fictional. Actor identifiers are not authenticated. Passing `--audit-actor chen` exercises an `audit:read` policy check for the declared identity; it does not prove who invoked the command. A person who can already read an artifact on disk does not need the CLI to inspect it.

## Operation controls and their scope

| Scenario | Implemented boundary | Limit |
| --- | --- | --- |
| A declared employee requests a finance document. | Role scope and clearance are checked before lexical scoring; requested IDs only narrow the candidate set. | The trusted operator can separately read the input bundle or declare another actor. |
| A request names another tenant. | It fails before writing to the engine tenant's audit stream. | A session can retain the failure as an operation outcome; this is not remote tenant isolation. |
| A normalized same-tenant request names an unknown actor or lacks permission. | Supported authorization denials are recorded in the tenant audit stream. | Malformed requests can fail before an auditable identity exists; not every error produces an audit event. |
| An actor attempts ingestion outside allowed clearance or role scope. | The ingestion is denied. | Policy is local input controlled by the trusted operator. |
| A document ID is reused. | An exact normalized repeat is idempotent; any changed document field produces `DOCUMENT_ID_CONFLICT`. | There is no document-update workflow or concurrent-write coordination. |
| Document text contains hostile instructions. | Text is used only as retrieval data and never changes permissions or executes instructions. | Reported instruction markers are diagnostics, not a complete detector. |
| Authorized candidates tie at the highest score. | Ambiguity is determined before the requested result limit truncates the list. | Lexical scoring does not establish relevance, truth or answer quality. |
| JSON contains duplicate keys, unsupported fields or invalid schema values. | Strict loading and normalization reject them. | Per-operation schema failures are retained outcomes, not necessarily tenant audit events. |

## Audit-chain verification

Audit events bind their sequence, previous digest, tenant, actor, operation type, decision, subject and payload digest. Successful ingestion audit payloads bind the complete normalized document record, including provenance and access metadata. `verify-audit` checks event structure, supported event/decision combinations and digest links. Optional expected head and event count values compare the retained chain with a separately held checkpoint.

A bare chain contains payload digests, not every original payload. Verifying it does not rerun authorization, reconstruct document state or establish that all operations were retained. Without an independent checkpoint, a valid prefix can verify, and an editor can replace and consistently rehash the entire chain. SHA-256 links provide consistency checks, not signatures, authenticated timestamps or protected retention.

Same-tenant normalized authorization denials and session failure outcomes have different scopes. The session preserves ordered outcomes so later operations can continue; the tenant audit stream includes only events supported by the engine. Cross-tenant failures do not contaminate the target tenant's audit stream.

## Retained sessions and replay

A retained run includes the starting normalized bundle, ordered operations, their outcomes and audit evidence needed for deterministic reexecution. Replay checks the artifact digest, runs the operations again in a fresh engine, and compares the ordered outcomes, complete audit chain and head, and final bundle digest.

A matching replay establishes that this implementation reproduced the retained run from its supplied inputs. It does not establish the identity of the original operator, the time of execution, the truth of source documents, the completeness of the session or an external service's behavior. Reproducing a denied operation remains a nonzero process outcome even when replay verification succeeds.

An editor who replaces the initial bundle, operations and outputs and computes a matching artifact digest can create a different reproducible artifact. `--expected-artifact-sha256` detects that change when its expected value was retained independently from the original run. An expected digest derived from the artifact currently under examination supplies no such independent comparison.

The retained `artifact_sha256` is computed over canonical JSON with that field excluded. It is distinct from a raw checksum of the formatted artifact file; use the original artifact digest for this comparison.

Replay artifacts contain full bundle data and operation inputs. Treat them with the same access restrictions as the original bundle. The supplied fictional session may be shared as demonstration material; the format is not a redacted export for employees or customers.

## Filesystem and runtime limits

New output paths are created exclusively and must not alias inputs or each other. Requested file writes complete before a final success result is emitted. These safeguards help prevent accidental replacement; they do not protect files from a privileged editor or supply a storage transaction across files, durable retention or crash recovery.

Each standalone command begins with a fresh engine. A session carries state only across its ordered operations. Later invocations need the retained updated bundle or the replay artifact. There is no background service or durable shared audit stream.

The CLI reads local inputs and performs deterministic operations. Source URIs are provenance labels supplied by the bundle; they are not fetched or independently authenticated. Content digests bind bytes, not factual correctness. The prototype provides no provider integration or generated-answer service.

## Work needed for a deployed service

A deployment would need authenticated identities tied to authorization decisions; protected tenant storage; encrypted transport and persistence; concurrency control; retention, backup and recovery; resource limits; and externally anchored audit evidence. Any semantic retrieval or generated-answer component would have to preserve the existing authorization boundary and restrict its inputs to authorized evidence.

Operational monitoring, cloud permissions and keys, network abuse protection and service availability are outside this local prototype. This document describes source behavior and intended boundaries; it is not a certification or an execution receipt. See [SUBMISSION.md](SUBMISSION.md) for the draft challenge status and [README.md](README.md) for commands and source lineage.
