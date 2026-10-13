import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const directory = await fs.mkdtemp(path.join(os.tmpdir(), "commons-network-bytes-"));
const binary = Buffer.from([0xff, 0xfe, 0x00, 0x61]);
await fs.writeFile(path.join(directory, "invalid.mno"), binary);
await fs.writeFile(path.join(directory, "valid.json"), '{"ok":true}\n', "utf8");
process.env.COMMONS_LOCAL_ROOT = directory;
const { protocolResource, readResourceTool } = await import("./server.mjs");

try {
  const binaryResult = await readResourceTool({ path: "invalid.mno", source: "local_checkout", max_bytes: 4 });
  assert.equal(binaryResult.bytes, binary.length);
  assert.equal(binaryResult.sha256, createHash("sha256").update(binary).digest("hex"));
  assert.equal(binaryResult.content_type, "application/octet-stream");
  assert.equal(binaryResult.content_encoding, "base64");
  assert.equal(binaryResult.content_base64, binary.toString("base64"));
  assert.equal(Object.hasOwn(binaryResult, "content"), false);

  await assert.rejects(
    readResourceTool({ path: "invalid.mno", source: "local_checkout", max_bytes: 3 }),
    /exceeded max_bytes/
  );

  const textResult = await readResourceTool({ path: "valid.json", source: "local_checkout", max_bytes: 64 });
  assert.equal(textResult.content, '{"ok":true}\n');
  assert.deepEqual(textResult.parsed_json, { ok: true });

  const resourceResult = await protocolResource("commons://resource/invalid.mno");
  assert.equal(resourceResult.contents[0].blob, binary.toString("base64"));
  assert.equal(resourceResult.contents[0].mimeType, "application/octet-stream");

  process.stdout.write("binary resource integrity: ok\n");
} finally {
  await fs.rm(directory, { recursive: true, force: true });
}
