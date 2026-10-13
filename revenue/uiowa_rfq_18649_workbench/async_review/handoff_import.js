"use strict";

// Draft notes are portable only within the exact report generation they annotate.
// This module never changes the report, emits evidence authority, or mutates UI state.
(function (root) {
  const MAX_DRAFT_BYTES = 1024 * 1024;
  const MAX_JSON_DEPTH = 64;
  function fail(message) { throw new Error(message); }

  // JSON.parse silently accepts duplicate object keys. A small bounded parser
  // preserves JSON string/number semantics while rejecting that information loss.
  function parseJson(input) {
    if (typeof input !== "string") fail("Draft content must be JSON text.");
    if (new TextEncoder().encode(input).length > MAX_DRAFT_BYTES) {
      fail("Draft exceeds the 1 MiB intake limit.");
    }
    let position = 0;
    function whitespace() {
      while (position < input.length && /[\x20\t\r\n]/.test(input[position])) position++;
    }
    function string() {
      const start = position++;
      while (position < input.length) {
        const char = input[position++];
        if (char === "\\") { position++; continue; }
        if (char === '"') {
          try { return JSON.parse(input.slice(start, position)); }
          catch { fail("Draft contains an invalid JSON string."); }
        }
      }
      fail("Draft contains an unterminated JSON string.");
    }
    function value(depth) {
      if (depth > MAX_JSON_DEPTH) fail("Draft JSON nesting exceeds the supported limit.");
      whitespace();
      const char = input[position];
      if (char === '"') return string();
      if (char === "{") {
        position++;
        const object = Object.create(null);
        const seen = new Set();
        whitespace();
        if (input[position] === "}") { position++; return object; }
        while (position < input.length) {
          whitespace();
          if (input[position] !== '"') fail("Draft contains an invalid JSON object.");
          const key = string();
          if (seen.has(key)) fail("Draft contains a duplicate JSON key.");
          seen.add(key);
          whitespace();
          if (input[position++] !== ":") fail("Draft contains an invalid JSON object.");
          object[key] = value(depth + 1);
          whitespace();
          const delimiter = input[position++];
          if (delimiter === "}") return object;
          if (delimiter !== ",") fail("Draft contains an invalid JSON object.");
        }
        fail("Draft contains an unterminated JSON object.");
      }
      if (char === "[") {
        position++;
        const array = [];
        whitespace();
        if (input[position] === "]") { position++; return array; }
        while (position < input.length) {
          array.push(value(depth + 1));
          whitespace();
          const delimiter = input[position++];
          if (delimiter === "]") return array;
          if (delimiter !== ",") fail("Draft contains an invalid JSON array.");
        }
        fail("Draft contains an unterminated JSON array.");
      }
      for (const [token, literal] of [["true", true], ["false", false], ["null", null]]) {
        if (input.startsWith(token, position)) { position += token.length; return literal; }
      }
      const match = input.slice(position).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
      if (match) {
        position += match[0].length;
        const number = Number(match[0]);
        if (!Number.isFinite(number)) fail("Draft contains a non-finite JSON number.");
        return number;
      }
      fail("Draft is not valid JSON.");
    }
    const result = value(0);
    whitespace();
    if (position !== input.length) fail("Draft contains trailing or invalid JSON content.");
    return result;
  }

  function parseDraft(input, report) {
    const handoff = typeof module !== "undefined" && module.exports
      ? require("./handoff.js") : root?.WorkbenchHandoff;
    if (!handoff) fail("The draft handoff schema module is unavailable.");
    const rows = handoff.validateDraft(parseJson(input), report);
    // Shared schema validation finishes before either map is returned. The
    // strict parser keeps duplicate JSON properties from being silently lost.
    return {
      notes: new Map(rows.map(row => [`${row.group}|${row.dimension}`, row.analyst_note])),
      dispositions: new Map(rows.map(row => [`${row.group}|${row.dimension}`, row.disposition]))
    };
  }

  const api = Object.freeze({ parseDraft, MAX_DRAFT_BYTES });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.HandoffImport = api;
})(typeof window === "undefined" ? null : window);
