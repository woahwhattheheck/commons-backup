# Compute a Git blob ID from retained UTF-8 source

`host/connected_git_blob_identity.cjs` exports one synchronous, pure function:

```js
const identity = gitBlobIdentity(completeSource);
// {bytes: <UTF-8 content byte count>, git_blob_sha: <40 lowercase hex characters>}
```

Use it when complete accepted source is already retained in a JavaScript
orchestrator and a Git, Node, Python or Web Crypto runtime is unavailable. The
module needs only standard JavaScript, typed arrays and BigInt. It has no
imports, filesystem access, network calls, clocks, timers or shared mutable
hashing state.

## Load the existing module

Retrieve its complete source at a known Git commit using the existing native
GitHub source reader. Keep the returned source identity with that capture.
For a V8 caller with no CommonJS loader, load that complete source as other
connected helpers are loaded:

```js
const identityModule = {exports: {}};
new Function('module', 'exports', completeIdentityModuleSource)(
  identityModule, identityModule.exports);
const {gitBlobIdentity} = identityModule.exports;

const acceptedIdentity = gitBlobIdentity(acceptedSource);
```

An existing Node caller can instead use its normal CommonJS loader:

```js
const {gitBlobIdentity} = require('./host/connected_git_blob_identity.cjs');
```

Loading defines the export. Hashing runs only when the caller explicitly
invokes the function; it performs no external operation.

## Keep source acceptance and publication separate

Calculate and retain the identity when accepting the complete source text,
before later transfer or publication. The result describes those supplied
bytes; it does not establish their origin, correctness, or previous execution.
Recomputing a pin from changed text does not preserve an earlier source identity.

Pass the retained result to the existing
[connected GitHub publisher](CONNECTED_GITHUB_PUBLISH.md):

```js
const preparedFile = {
  path: sourcePath,
  content: acceptedSource,
  encoding: 'utf-8',
  expected_blob_sha: observedPreviousBlobSha, // null for a confirmed new leaf
  expected_new_blob_sha: acceptedIdentity.git_blob_sha
};
```

The previous-file pin and the new-source pin identify different versions.
The publisher still proves the current preimage and mode, compares its native
blob result with the requested new-source pin before tree creation, and checks
complete text plus SHA at readback. This utility does not call, wrap or change
publication or merge continuation. Unpinned UTF-8 batching remains available
without loading or invoking this companion.

## Exact input and result contract

The input must be a primitive JavaScript string with well-formed UTF-16.
Non-string values and lone high or low surrogate code units throw `TypeError`.
Valid surrogate pairs encode as their supplementary Unicode character.
Empty strings, embedded NULs and existing line endings are accepted.

`bytes` counts only the encoded UTF-8 content, not JavaScript UTF-16 code units
or the Git object header. Text is encoded exactly as supplied, with no Unicode
normalization, line-ending conversion or inserted byte-order mark. A base64
string is still text to this function; it is not decoded into binary content.

The Git object format follows the
[Git Object Storage reference](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects):
the SHA-1 input is the ASCII header `blob <UTF-8 byte count>\0` followed by the
encoded content. The returned `git_blob_sha` uses the 40-character SHA-1 blob
identity expected by the current connected publisher. The header participates
in that digest.

For an empty source:

```js
gitBlobIdentity('');
// {bytes: 0, git_blob_sha: 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'}
```

## Working memory

The function first validates the string and counts its UTF-8 bytes, then makes
a second pass to feed the header and content into SHA-1. Its working buffers
are one 64-byte block, an 80-word schedule and five state words. It does not
allocate a complete encoded copy of the source or concatenate a second
header-plus-payload array. Time grows with the supplied content length; the
caller retains the original string.
