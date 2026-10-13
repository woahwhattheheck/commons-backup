# Windows credential text encodings

Windows text descriptors default to `text_encoding: "utf-8"`. An existing
credential stored as UTF-16LE text declares `text_encoding: "utf-16-le"`.
JSON parsing and JSON Pointer selection follow the declared decoding.

The package initializer composes the decoder with the existing native custody
reader. Local retrieval and encrypted delivery use the same implementation and
references. No additional service, credential grant, or holder process is needed.
Repeated package initialization does not install another wrapper.

Decoding does not guess from token prefixes or embedded NUL bytes. Malformed
declared text and unsupported text encodings return the existing constant
credential-source error through the public reader. `encoding: "base64"` takes
precedence and preserves every original byte, including non-UTF-8 data and
embedded or trailing NULs.

The separate standalone convenience reader retains its established text and
Base64 handling while honoring explicit text encodings.
