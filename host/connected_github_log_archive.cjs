"use strict";

// Build a deterministic, UTF-8 ZIP32 archive containing decoded text files.
// No filesystem, network, Node built-ins, TextEncoder, or external packages are used.
// Returns base64 for GitHub create_blob; do not print the returned base64 in tool output.
// Storage method 0 preserves the exact UTF-8 bytes, including any leading BOM.

function buildStoredZip(entries) {
  if (!Array.isArray(entries) || entries.length > 65535) throw new Error("ZIP32 requires at most 65535 entries");
  function utf8(text) {
    if (typeof text !== "string") throw new TypeError("ZIP names and contents must be strings");
    const bytes = [];
    for (const char of text) {
      let cp = char.codePointAt(0);
      if (cp >= 0xd800 && cp <= 0xdfff) cp = 0xfffd;
      if (cp < 0x80) bytes.push(cp);
      else if (cp < 0x800) bytes.push(0xc0 | (cp >> 6), 0x80 | (cp & 63));
      else if (cp < 0x10000) bytes.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
      else bytes.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 63), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
    }
    return Uint8Array.from(bytes);
  }
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let bit = 0; bit < 8; bit++) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  function crc32(bytes) {
    let c = 0xffffffff;
    for (const byte of bytes) c = table[(c ^ byte) & 255] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }
  const names = new Set();
  let localSize = 0, centralSize = 0;
  const prepared = entries.map(entry => {
    if (!entry || typeof entry.name !== "string" || !entry.name ||
        entry.name.includes("\\") || /[\u0000-\u001f\u007f]/.test(entry.name) ||
        entry.name.includes(":") || entry.name.split("/").some(p => !p || p === "." || p === ".."))
      throw new Error("ZIP entry names must be unique safe relative file paths");
    const name = utf8(entry.name), nameIdentity = name.join(",");
    if (names.has(nameIdentity)) throw new Error("ZIP entry names must be unique safe relative file paths");
    names.add(nameIdentity);
    const data = utf8(entry.content);
    if (name.length > 65535 || data.length >= 0xffffffff) throw new Error("ZIP32 entry limit exceeded");
    const record = { label: entry.name, name, data, crc: crc32(data), offset: localSize };
    localSize += 30 + name.length + data.length;
    centralSize += 46 + name.length;
    return record;
  });
  const total = localSize + centralSize + 22;
  if (total >= 0xffffffff) throw new Error("ZIP64 is not supported");
  const archive = new Uint8Array(total), view = new DataView(archive.buffer);
  const u16 = (offset, value) => view.setUint16(offset, value, true);
  const u32 = (offset, value) => view.setUint32(offset, value, true);
  let centralOffset = localSize;
  for (const entry of prepared) {
    const p = entry.offset;
    u32(p, 0x04034b50); u16(p + 4, 20); u16(p + 6, 0x0800);
    u16(p + 8, 0); u16(p + 10, 0); u16(p + 12, 0x0021);
    u32(p + 14, entry.crc); u32(p + 18, entry.data.length); u32(p + 22, entry.data.length);
    u16(p + 26, entry.name.length); u16(p + 28, 0);
    archive.set(entry.name, p + 30);
    archive.set(entry.data, p + 30 + entry.name.length);
    const c = centralOffset;
    u32(c, 0x02014b50); u16(c + 4, 20); u16(c + 6, 20); u16(c + 8, 0x0800);
    u16(c + 10, 0); u16(c + 12, 0); u16(c + 14, 0x0021);
    u32(c + 16, entry.crc); u32(c + 20, entry.data.length); u32(c + 24, entry.data.length);
    u16(c + 28, entry.name.length);
    u32(c + 42, entry.offset);
    archive.set(entry.name, c + 46);
    centralOffset += 46 + entry.name.length;
  }
  u32(centralOffset, 0x06054b50);
  u16(centralOffset + 8, prepared.length); u16(centralOffset + 10, prepared.length);
  u32(centralOffset + 12, centralSize); u32(centralOffset + 16, localSize);
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let base64 = "";
  for (let i = 0; i < archive.length; i += 3) {
    const a = archive[i], b = archive[i + 1] ?? 0, c = archive[i + 2] ?? 0;
    base64 += alphabet[a >> 2] + alphabet[((a & 3) << 4) | (b >> 4)] +
      (i + 1 < archive.length ? alphabet[((b & 15) << 2) | (c >> 6)] : "=") +
      (i + 2 < archive.length ? alphabet[c & 63] : "=");
  }
  return {
    base64,
    byteLength: archive.length,
    records: prepared.map(e => ({
      name: e.label, offset: e.offset, bytes: e.data.length, crc32: e.crc.toString(16).padStart(8, "0")
    }))
  };
}

if (typeof module !== "undefined" && module.exports) module.exports = { buildStoredZip };
