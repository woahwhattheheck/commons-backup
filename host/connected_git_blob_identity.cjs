'use strict';

/** Compute a UTF-8 Git blob identity with bounded working memory and no I/O. */
function gitBlobIdentity(value) {
  if (typeof value !== 'string') throw new TypeError('gitBlobIdentity requires a string');
  let bytes = 0;
  for (const char of value) {
    const code = char.codePointAt(0);
    if (code >= 0xd800 && code <= 0xdfff) throw new TypeError('Unpaired UTF-16 surrogate');
    bytes += code < 0x80 ? 1 : code < 0x800 ? 2 : code < 0x10000 ? 3 : 4;
  }

  // Git hashes its ASCII type/byte-count header followed by the exact UTF-8 bytes.
  const header = 'blob ' + bytes + '\0';
  const bits = BigInt(header.length + bytes) * 8n;
  const block = new Uint8Array(64);
  const words = new Uint32Array(80);
  const state = new Uint32Array([0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]);
  const rotate = (word, count) => ((word << count) | (word >>> (32 - count))) >>> 0;
  let used = 0;

  function compress() {
    for (let i = 0; i < 16; i++) {
      const start = i * 4;
      words[i] = ((block[start] << 24) | (block[start + 1] << 16)
        | (block[start + 2] << 8) | block[start + 3]) >>> 0;
    }
    for (let i = 16; i < 80; i++) {
      words[i] = rotate(words[i - 3] ^ words[i - 8] ^ words[i - 14] ^ words[i - 16], 1);
    }
    let [a, b, c, d, e] = state;
    for (let i = 0; i < 80; i++) {
      let mix, constant;
      if (i < 20) { mix = (b & c) | ((~b) & d); constant = 0x5a827999; }
      else if (i < 40) { mix = b ^ c ^ d; constant = 0x6ed9eba1; }
      else if (i < 60) { mix = (b & c) | (b & d) | (c & d); constant = 0x8f1bbcdc; }
      else { mix = b ^ c ^ d; constant = 0xca62c1d6; }
      const next = (rotate(a, 5) + mix + e + constant + words[i]) >>> 0;
      e = d; d = c; c = rotate(b, 30); b = a; a = next;
    }
    state[0] = (state[0] + a) >>> 0;
    state[1] = (state[1] + b) >>> 0;
    state[2] = (state[2] + c) >>> 0;
    state[3] = (state[3] + d) >>> 0;
    state[4] = (state[4] + e) >>> 0;
  }

  function put(byte) {
    block[used++] = byte;
    if (used === block.length) { compress(); used = 0; }
  }

  for (let i = 0; i < header.length; i++) put(header.charCodeAt(i));
  // A second pass avoids retaining an encoded copy of the complete source.
  for (const char of value) {
    const code = char.codePointAt(0);
    if (code < 0x80) put(code);
    else if (code < 0x800) { put(0xc0 | (code >> 6)); put(0x80 | (code & 63)); }
    else if (code < 0x10000) {
      put(0xe0 | (code >> 12)); put(0x80 | ((code >> 6) & 63)); put(0x80 | (code & 63));
    } else {
      put(0xf0 | (code >> 18)); put(0x80 | ((code >> 12) & 63));
      put(0x80 | ((code >> 6) & 63)); put(0x80 | (code & 63));
    }
  }
  put(0x80);
  while (used !== 56) put(0);
  for (let i = 7; i >= 0; i--) put(Number((bits >> (8n * BigInt(i))) & 255n));
  return {bytes, git_blob_sha: Array.from(state, word => word.toString(16).padStart(8, '0')).join('')};
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {gitBlobIdentity};
}
