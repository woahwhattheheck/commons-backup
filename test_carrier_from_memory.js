#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const carrier = fs.readFileSync("carrier.js", "utf8");
const diagnostic = fs.readFileSync("diagnostic.html", "utf8");

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}()`);
  assert.notStrictEqual(start, -1, `${name} was not found`);
  const opening = source.indexOf("{", start);
  let depth = 0;
  for (let index = opening; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`${name} did not have a balanced body`);
}

const bindFromMemory = extractFunction(carrier, "bindFromMemory");
const formTag = diagnostic.match(/<form\b[^>]*\bid="say"[^>]*>/i);
assert(formTag, "diagnostic say form was not found");
const noFromMemory = /\bdata-no-from-memory="true"/i.test(formTag[0]);
assert.strictEqual(noFromMemory, true, "diagnostic form must opt out of sender memory");

function executeWith(fields, savedSender = "remembered-sender") {
  const localCalls = [];
  const sessionCalls = [];
  const sandbox = {
    document: {
      querySelectorAll(selector) {
        assert.strictEqual(selector, 'input[name="from"]');
        return fields;
      },
    },
    localStorage: {
      getItem(key) { localCalls.push(["getItem", key]); return savedSender; },
      setItem(key, value) { localCalls.push(["setItem", key, value]); },
    },
    sessionStorage: {
      getItem(key) { sessionCalls.push(["getItem", key]); return savedSender; },
      setItem(key, value) { sessionCalls.push(["setItem", key, value]); },
    },
  };
  vm.runInNewContext(`${bindFromMemory}\nbindFromMemory();`, sandbox, {
    filename: "carrier.js#bindFromMemory",
  });
  return { localCalls, sessionCalls };
}

const actualDiagnosticFromFields = Array.from(
  diagnostic.matchAll(/<input\b[^>]*\bname="from"[^>]*>/gi)
);
assert.deepStrictEqual(actualDiagnosticFromFields, [], "diagnostic must not expose a sender field");
const diagnosticRun = executeWith(actualDiagnosticFromFields);
assert.deepStrictEqual(diagnosticRun.localCalls, [], "diagnostic must not touch localStorage");
assert.deepStrictEqual(diagnosticRun.sessionCalls, [], "diagnostic must not touch sessionStorage");

let listeners = 0;
const optedOutField = {
  type: "text",
  value: "",
  getAttribute(name) { return name === "data-no-from-memory" ? null : null; },
  form: {
    getAttribute(name) {
      return name === "data-no-from-memory" && noFromMemory ? "true" : null;
    },
  },
  addEventListener() { listeners += 1; },
};
const optedOutRun = executeWith([optedOutField]);
assert.deepStrictEqual(optedOutRun.localCalls, [], "form opt-out must not touch localStorage");
assert.deepStrictEqual(optedOutRun.sessionCalls, [], "form opt-out must not touch sessionStorage");
assert.strictEqual(listeners, 0, "opted-out sender fields must not receive persistence listeners");
assert.strictEqual(optedOutField.value, "", "remembered sender must not populate an opted-out field");

const positiveListeners = {};
const rememberedField = {
  type: "text",
  value: "",
  getAttribute() { return null; },
  form: { getAttribute() { return null; } },
  addEventListener(type, listener) {
    assert.strictEqual(positiveListeners[type], undefined, `${type} listener was registered twice`);
    positiveListeners[type] = listener;
  },
};
const positiveRun = executeWith([rememberedField]);
assert.deepStrictEqual(positiveRun.localCalls, [], "eligible sender memory must never use localStorage");
assert.deepStrictEqual(
  positiveRun.sessionCalls,
  [["getItem", "commons-from-session-v1"]],
  "eligible sender memory must read the per-tab session key exactly once"
);
assert.strictEqual(rememberedField.value, "remembered-sender", "session sender was not restored");
assert.deepStrictEqual(Object.keys(positiveListeners), ["change"], "sender persistence must remain change-only");
rememberedField.value = "new-tab-sender";
positiveListeners.change();
assert.deepStrictEqual(
  positiveRun.sessionCalls,
  [
    ["getItem", "commons-from-session-v1"],
    ["setItem", "commons-from-session-v1", "new-tab-sender"],
  ],
  "change must persist the sender once to the per-tab session key"
);
assert.deepStrictEqual(positiveRun.localCalls, [], "change persistence must not use localStorage");

console.log("carrier sender-memory spy PASS: diagnostic zero calls; positive sessionStorage control works");
