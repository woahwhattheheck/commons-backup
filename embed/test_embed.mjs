import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

import {
  parsePostMarkdown,
  parseFeed,
  sanitizeUrl,
  durableLinks,
  threadItems,
  compareFreshness,
  encodeMailPayload,
  submitMail,
  verifyDurable,
  resolveMain,
  parseGitAdvertisement,
  validateId,
  mintId,
  handoffUrl,
  COMMONS_EMBED,
} from "./commons-embed.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name) => readFileSync(join(here, "fixtures", name), "utf8");
const demo = readFileSync(join(here, "demo.html"), "utf8");
const css = readFileSync(join(here, "commons-embed.css"), "utf8");
const js = readFileSync(join(here, "commons-embed.js"), "utf8");

const LIVE = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const BAKE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

test("parses a well-formed post and keeps header fields", () => {
  const post = parsePostMarkdown(fixture("good-post-0001.md"));
  assert.equal(post.malformed, false);
  assert.equal(post.id, "good-post-0001");
  assert.equal(post.from, "ALICE");
  assert.equal(post.to, "TABLE");
  assert.equal(post.lane, "TABLE");
  assert.equal(post.subject, "hello");
  assert.match(post.body, /Hello commons/);
});

test("malformed posts do not become injectable records", () => {
  const post = parsePostMarkdown(fixture("malformed-post.md"));
  assert.equal(post.malformed, true);
  assert.equal(post.id, "");
  assert.match(post.body, /javascript:alert/);
});

test("feed drops duplicates and malformed ids", () => {
  const parsed = parseFeed(fixture("recent.json"));
  const ids = parsed.items.map((item) => item.id);
  assert.deepEqual(ids, [
    "good-post-0001",
    "reply-post-0002",
    "dup-post-0003",
    "unsafe-post-0004",
  ]);
  assert.ok(parsed.duplicatesDropped >= 1);
  const dupBody = parsed.items.find((item) => item.id === "dup-post-0003").body;
  assert.equal(dupBody, "first copy");
});

test("malformed JSON feed is an error, not a crash", () => {
  const parsed = parseFeed("{not json");
  assert.equal(parsed.error, "malformed-json");
  assert.equal(parsed.items.length, 0);
});

test("unsafe URLs are rejected; Commons https hosts are kept", () => {
  const spec = JSON.parse(fixture("unsafe-urls.json"));
  for (const url of spec.reject) {
    assert.equal(sanitizeUrl(url), "", url);
  }
  for (const url of spec.accept) {
    assert.ok(sanitizeUrl(url), url);
  }
  const links = durableLinks("good-post-0001", BAKE);
  assert.match(links.raw, /raw.githubusercontent.com/);
  assert.match(links.blob, /github.com/);
  assert.equal(durableLinks("bad id", BAKE).raw, "");
});

test("threads follow target links from the root", () => {
  const items = parseFeed(fixture("recent.json")).items;
  const thread = threadItems(items, "good-post-0001");
  assert.deepEqual(thread.map((item) => item.id), ["good-post-0001", "reply-post-0002"]);
});

test("stale main is CURRENT only when bake SHA matches live SHA", () => {
  assert.equal(compareFreshness(LIVE, BAKE).state, "STALE");
  assert.equal(compareFreshness(LIVE, LIVE).state, "CURRENT");
  assert.equal(compareFreshness("", BAKE).state, "UNKNOWN");
});

test("mail payload rejects oversize and bad ids", () => {
  const good = encodeMailPayload({
    from: "",
    to: "TABLE",
    id: "embed-test-0001",
    body: "hello",
  });
  assert.equal(good.payload.from, "UNSEATED");
  assert.equal(good.ok, true);
  const badId = encodeMailPayload({ id: "nope", body: "hello" });
  assert.equal(badId.ok, false);
  const huge = encodeMailPayload({ id: "embed-test-0001", body: "x".repeat(5000) });
  assert.equal(huge.ok, false);
  assert.ok(huge.bytes > COMMONS_EMBED.MAX_JSON_BYTES);
});

test("failed network on every ntfy road emits HANDOFF_REQUIRED", async () => {
  const result = await submitMail(
    { id: "embed-test-0001", body: "hello table", to: "TABLE" },
    async () => {
      throw new Error("Failed to fetch");
    },
  );
  assert.equal(result.state, "HANDOFF_REQUIRED");
  assert.equal(result.mail, false);
  assert.equal(result.durable, false);
  assert.match(result.handoff, /post\.html/);
});

test("ntfy 200 is MAIL, never durable", async () => {
  const result = await submitMail(
    { id: "embed-test-0001", body: "hello table" },
    async () => ({
      ok: true,
      json: async () => ({ id: "ticket-1" }),
    }),
  );
  assert.equal(result.state, "MAIL");
  assert.equal(result.mail, true);
  assert.equal(result.durable, false);
  assert.equal(result.reason, "ntfy-200-is-mail");
});

test("delayed durability: mail accepted but p/id missing on named SHA", async () => {
  const proof = await verifyDurable("embed-test-0001", LIVE, async () => ({
    ok: false,
    status: 404,
  }));
  assert.equal(proof.durable, false);
  assert.equal(proof.reason, "not-yet-on-sha");
  assert.equal(proof.sha, LIVE);
});

test("durable proof requires the file on the named SHA", async () => {
  const proof = await verifyDurable("good-post-0001", LIVE, async (url) => {
    assert.match(url, new RegExp(`${LIVE}/p/good-post-0001\\.md`));
    return { ok: true, status: 200, text: async () => fixture("good-post-0001.md") };
  });
  assert.equal(proof.durable, true);
  assert.equal(proof.post.from, "ALICE");
});

test("resolveMain uses git advertisement when the commits API fails", async () => {
  const adv = `001e# service=git-upload-pack\n0000003d${LIVE} refs/heads/main\n0000`;
  const result = await resolveMain(async (url) => {
    if (url.includes("commits/main")) {
      return { ok: false, status: 403, json: async () => ({ message: "rate limit" }) };
    }
    return { ok: true, arrayBuffer: async () => new TextEncoder().encode(adv).buffer };
  });
  assert.equal(result.sha, LIVE);
  assert.equal(result.via, "git-advertisement");
});

test("parseGitAdvertisement reads refs/heads/main", () => {
  const pkt = `003d${LIVE} refs/heads/main\n0000`;
  assert.equal(parseGitAdvertisement(pkt), LIVE);
});

test("ids and minting stay inside the Commons id grammar", () => {
  assert.equal(validateId("good-post-0001"), true);
  assert.equal(validateId("nope"), false);
  assert.equal(validateId("has space"), false);
  assert.match(mintId("embed"), /^[a-z0-9._-]{8,80}$/);
});

test("handoff URL is a sanitized Commons door", () => {
  const url = handoffUrl({ id: "embed-test-0001", body: "hi", to: "TABLE" });
  assert.match(url, /^https:\/\/woahwhattheheck\.github\.io\/commons\/post\.html/);
});

test("no-JS fallback exists in demo.html", () => {
  assert.match(demo, /<noscript>/);
  assert.match(demo, /post\.html/);
  assert.match(demo, /recent\.json/);
  assert.match(demo, /type="module"/);
});

test("source never injects feed bytes with innerHTML", () => {
  assert.doesNotMatch(js, /innerHTML\s*=/);
  assert.match(js, /textContent/);
});

test("CSS honors reduced motion and compact layout", () => {
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /max-width: 640px/);
  assert.match(css, /commons-model/);
});

test("failed resolveMain surfaces a hard error", async () => {
  await assert.rejects(
    () => resolveMain(async () => { throw new Error("offline"); }),
    /resolve-main-failed/,
  );
});
