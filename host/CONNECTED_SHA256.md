# Hash retained UTF-8 files with SHA-256

`host/connected_sha256.cjs` exports one synchronous pure function:

```js
const digest = sha256Utf8(completeEditedFileText);
// {bytes: <UTF-8 byte count>, sha256: <64 lowercase hexadecimal characters>}
```

Use it when a document package needs content hashes and its complete files are
already retained as JavaScript strings. It runs in a connected JavaScript
orchestrator without a native process, Node imports, Web Crypto, TextEncoder,
network access or filesystem access. It also works as a normal CommonJS module.

## Load the source once, then hash current file contents

Retrieve the complete module from a known Commons Git commit using the existing
GitHub file reader. Preserve that returned source identity with the retained
source. A V8 caller without a CommonJS loader can load it directly:

```js
const digestModule = {exports: {}};
new Function('module', 'exports', completeDigestModuleSource)(
  digestModule, digestModule.exports);
const {sha256Utf8} = digestModule.exports;

const digest = sha256Utf8(completeEditedFileText);
```

An existing Node caller can use its normal loader:

```js
const {sha256Utf8} = require('./host/connected_sha256.cjs');
const digest = sha256Utf8(completeEditedFileText);
```

Loading defines the export. Hashing occurs only on the explicit function call.
Each call owns its hashing state and returns its result directly. Invalid input
throws a clear `TypeError`; a CLI that calls this API should preserve its own
nonzero error-exit behavior.

## Exact content contract

The input is a primitive JavaScript string with well-formed UTF-16. Lone high or
low surrogate code units are rejected before hashing. Valid surrogate pairs
encode as their supplementary Unicode character. Empty strings, embedded NULs,
existing byte-order marks and existing line endings are accepted.

The function encodes exactly that string as UTF-8. It does not normalize Unicode,
trim whitespace, alter line endings, insert or remove a byte-order mark, append a
newline, or serialize a parsed object. Keep the complete original file text when
reading JSON or other structured documents: parsing and reserializing can produce
different bytes even when values compare equal.

`bytes` counts the UTF-8 content bytes, not JavaScript UTF-16 code units. The
function first validates and counts the string, then feeds the text to the
bundled implementation. It does not retain a second, complete UTF-8 byte array.

A base64 string is hashed as text and is not decoded. A rendered web page,
extracted PDF text, excerpt, tool envelope or truncated file is also only the
supplied text. Its digest does not identify the unavailable original binary or
complete provider file. This API has no binary-input or streaming interface.

## Update the existing package manifest

The digest describes the exact supplied current file contents. Use it to update
the corresponding entries of the package's existing manifest:

```js
const digest = sha256Utf8(completeEditedFileText);
const manifestLine = digest.sha256 + '  ' + relativeFilePath + '\n';
```

This line format is suitable only when the package already uses the plain
`<digest><two spaces><relative path><newline>` convention and the filename needs
no escaping. Follow that package's actual filename encoding, ordering, inventory,
self-exclusion and final-newline contract. This module does not enumerate files,
format or escape paths, infer a closed inventory, fetch missing bytes, or update
any manifest automatically.

Hash the new complete text after the intended edit is finished. Preserve accepted
hashes for unchanged files according to the package's existing workflow. A new
digest is not a reason to rerun an accepted product result. Manifest completeness
and retained-file equality still come from the actual package inventory and
source records, not from a digest count.

## Keep SHA-256 and Git blob identity distinct

This function returns the SHA-256 of the content alone. Its 64-character
`sha256` value is a content digest for manifests and similar records.

The [Git blob identity helper](CONNECTED_GIT_BLOB_IDENTITY.md) returns the current
publisher's 40-character SHA-1 Git blob identity, including Git's
`blob <byte count>\0` object header in the hashed bytes. When the
[connected GitHub publisher](CONNECTED_GITHUB_PUBLISH.md) needs
`expected_new_blob_sha`, use that Git blob helper's `git_blob_sha` value.
The SHA-256 content digest cannot be substituted for a Git blob SHA.

Neither digest identifies the author, establishes source origin, proves a product
execution or changes an existing publication result. Keep the current file text,
provider readback and accepted execution results in their existing roles.

## Bundled implementation and license

The module includes the unchanged pure CommonJS build from
[js-sha256 1.0.0 at commit 9a54fb31d4594762987e1b5d175265f6bac921de](https://github.com/emn178/js-sha256/blob/9a54fb31d4594762987e1b5d175265f6bac921de/build/sha256.cjs),
upstream blob `e3a08633357cb7ca248e14751f9270d95fbbbdf2`.
The complete
[MIT license](https://github.com/emn178/js-sha256/blob/9a54fb31d4594762987e1b5d175265f6bac921de/LICENSE.txt)
and copyright notice are retained inside the module.

The Commons wrapper validates well-formed text, counts UTF-8 content bytes and
uses a separate upstream hasher for each call. Only `sha256Utf8` is exported.
There is no runtime download or dependency installation.
