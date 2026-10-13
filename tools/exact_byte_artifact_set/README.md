# Exact-byte artifact-set publisher

`tools.exact_byte_artifact_set` is a small filesystem-custody primitive for commands that need to commit several exact byte strings as **one directory generation**.

The v1 implementation wrote several independently visible leaves into an already-existing output directory and verified them in finite sequential passes. That can prove individual observations, but it cannot create one collective linearization point: after an early leaf passes its last check, another writer can mutate it while later leaves are checked. The v2 contract therefore publishes the whole set with one no-clobber directory rename instead of treating another verification loop as atomicity.

## Contract

`publish_artifact_set(output_dir, artifacts)` now requires:

- `output_dir` itself is absent;
- its parent directory already exists and is reached through descriptor-relative `O_DIRECTORY|O_NOFOLLOW` custody;
- artifact names are bounded safe single-component leaves;
- the retained parent/staging namespace is a trusted transaction boundary. A same-UID/equivalent-authority actor that can deliberately substitute the random staging entry between `mkdir` and retained-FD acquisition, or mutate staged leaves between final verification and commit, is outside this primitive's authority. Use a private parent or stronger OS isolation for that adversary.

The publisher then:

1. retains the parent generation and refuses any existing target entry;
2. creates a private random staging directory inside that parent;
3. creates every staged leaf `O_EXCL|O_RDWR|O_NOFOLLOW`, drains short writes, fsyncs each file, and retains every readable descriptor;
4. fsyncs the staging directory and verifies exact expected bytes plus visible `(dev, ino, mode, size)` identity for every staged leaf;
5. revalidates the requested parent path, target absence, and retained staging generation;
6. performs exactly one `renameat2(..., RENAME_NOREPLACE)` from staging name to `output_dir` name. **That directory rename is the artifact-set publication linearization point.** Before it, the requested output namespace is absent; after it, the complete verified generation is present as one namespace object;
7. fsyncs the parent and revalidates the retained parent/published-directory generations. Failure after the rename is reported as a partial publication and never destructively rolls the committed generation back.

Retained-file readback compares 64 KiB chunks with matching slices of the original immutable payload and checks for an exact end of file. The comparison uses bounded temporary memory instead of buffering and joining another complete artifact. Caller-supplied payloads remain resident for publication; file-generation checks and receipt digests are unchanged.

Platforms without the required POSIX directory-descriptor primitives or `renameat2(RENAME_NOREPLACE)` fail closed. There is no ordinary-rename fallback that can overwrite a foreign target.

## Receipt truth

The v2 receipt uses schema `exact-byte-artifact-set-receipt/v2` and contains:

- `publication_committed: true` only after the no-clobber directory commit and required post-commit checks return successfully;
- `linearization: "RENAME_NOREPLACE_DIRECTORY_GENERATION"`;
- `post_commit_stability_proven: false`;
- sorted artifact names, exact byte lengths, SHA-256 digests, and a deterministic set digest.

`post_commit_stability_proven: false` is deliberate. No userspace function can make an ordinary writable directory permanently immutable against an equivalent-authority actor after the atomic commit. The receipt proves what exact directory generation was committed at the linearization point; consumers that need later-current bytes must use a private namespace, OS-enforced immutability, or re-verify at their use boundary.

If staging has begun and any later step fails, **nothing is pathname-deleted**. `PartialPublicationError` exposes `created_leaves`, the random `staging_name`, and `publication_committed` so an operator can reconcile whether evidence remains only in staging or was already atomically committed. This avoids cleanup that re-resolves a possibly foreign pathname.

## Example

```python
from tools.exact_byte_artifact_set import publish_artifact_set

# build/output must not exist; build must already exist.
receipt = publish_artifact_set(
    "build/output",
    {
        "packet.json": b'{"state":"HOLD"}\n',
        "packet.md": b"# Packet\n\nHOLD\n",
    },
)
assert receipt["publication_committed"] is True
assert receipt["post_commit_stability_proven"] is False
```

## Non-authority

This utility proves a bounded filesystem publication property only. It does not prove artifact semantics, evidence authenticity/currentness, buyer acceptance, external-send authority, payment authority, deployment authority, or future byte stability after the commit. Product-level authority gates remain separate.
