"use strict";

// Ranges refer to UTF-16 code units in each original content item's text.
const SCHEMA = "commons.connected_web_source_projection/v1";
const DEFAULTS = Object.freeze({
  start_index: 0,
  max_sources: 8,
  max_content_chars: 800,
  max_total_content_chars: 6400,
  max_input_chars: 1048576,
  max_header_chars: 4096
});
const OWN = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

function readOptions(value) {
  const input = value === undefined ? {} : value;
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new TypeError("options must be an object");
  }
  const allowed = new Set([...Object.keys(DEFAULTS), "source_indices"]);
  for (const key of Object.keys(input)) {
    if (!allowed.has(key)) throw new TypeError("Unsupported option: " + key);
  }
  if (OWN(input, "source_indices") && OWN(input, "start_index")) {
    throw new TypeError("source_indices and an explicit start_index are mutually exclusive");
  }
  const limits = { ...DEFAULTS };
  const ranges = {
    start_index: [0, Number.MAX_SAFE_INTEGER],
    max_sources: [0, 100],
    max_content_chars: [0, 100000],
    max_total_content_chars: [0, 1000000],
    max_input_chars: [1, 8388608],
    max_header_chars: [128, 16384]
  };
  for (const key of Object.keys(DEFAULTS)) {
    if (!OWN(input, key)) continue;
    const value = input[key];
    const [minimum, maximum] = ranges[key];
    if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
      throw new RangeError(key + " must be an integer from " + minimum + " to " + maximum);
    }
    limits[key] = value;
  }
  let selected = null;
  if (OWN(input, "source_indices")) {
    if (!Array.isArray(input.source_indices)) {
      throw new TypeError("source_indices must be an array");
    }
    selected = input.source_indices.slice();
    if (selected.length > limits.max_sources) {
      throw new RangeError("max_sources must accommodate all source_indices");
    }
    for (let i = 0; i < selected.length; i += 1) {
      if (!Number.isSafeInteger(selected[i]) || selected[i] < 0 ||
          (i > 0 && selected[i] <= selected[i - 1])) {
        throw new RangeError("source_indices must be distinct, increasing nonnegative integers");
      }
    }
  }
  return { limits, selected };
}

function omittedRanges(count, selected) {
  const ranges = [];
  let cursor = 0;
  for (const index of selected) {
    if (cursor < index) ranges.push([cursor, index]);
    cursor = index + 1;
  }
  if (cursor < count) ranges.push([cursor, count]);
  return ranges;
}

function prefixLength(text, start, maximum) {
  let length = Math.min(maximum, text.length - start);
  const end = start + length;
  if (length > 0 && end < text.length) {
    const previous = text.charCodeAt(end - 1);
    const next = text.charCodeAt(end);
    if (previous >= 0xd800 && previous <= 0xdbff && next >= 0xdc00 && next <= 0xdfff) {
      length -= 1;
    }
  }
  return length;
}

/**
 * Project source blocks from a retained web-tool CallToolResult.
 * No tools, network, filesystem, normalization, domain filtering or authority inference.
 */
function projectWebSources(response, options) {
  const { limits, selected: requested } = readOptions(options);
  const base = {
    schema: SCHEMA,
    status: null,
    source: {
      basis: "connector_rendered_text",
      reference_identity: "rendered_header",
      range_unit: "utf16_code_units",
      range_end: "exclusive"
    },
    limits: { ...limits },
    coverage: {
      scope: "retained_response_only",
      snapshot: false,
      provider_completeness: "not_inferred"
    },
    sources: [],
    issue: null
  };
  function refuse(status, code, details) {
    return { ...base, status, issue: { code, ...details } };
  }
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CALL_TOOL_RESULT", {});
  }
  if (response.isError === true) {
    return refuse("PROVIDER_ERROR", "PROVIDER_ERROR_ENVELOPE", {});
  }
  if (!Array.isArray(response.content)) {
    return refuse("UNSUPPORTED_REPRESENTATION", "EXPECTED_CONTENT_ITEMS", {});
  }
  if (response.content.length > 4096) {
    return refuse("INPUT_LIMIT", "CONTENT_ITEMS_LIMIT", { observed: response.content.length, maximum: 4096 });
  }

  const texts = [];
  const nonText = [];
  let inputChars = 0;
  for (let index = 0; index < response.content.length; index += 1) {
    const item = response.content[index];
    if (!item || typeof item !== "object" || typeof item.type !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "MALFORMED_CONTENT_ITEM", { content_index: index });
    }
    if (item.type !== "text") {
      nonText.push({ content_index: index, type: item.type });
      continue;
    }
    if (typeof item.text !== "string") {
      return refuse("UNSUPPORTED_REPRESENTATION", "TEXT_IS_NOT_STRING", { content_index: index });
    }
    inputChars += item.text.length;
    if (inputChars > limits.max_input_chars) {
      return refuse("INPUT_LIMIT", "TEXT_CHAR_LIMIT", { observed_at_least: inputChars, maximum: limits.max_input_chars });
    }
    texts.push({ content_index: index, text: item.text });
  }
  base.source = { ...base.source, content_items: response.content.length, text_items: texts.length, input_chars: inputChars };

  const parsed = [];
  const unparsed = [];
  const seen = new Set();
  const duplicates = new Set();
  for (const item of texts) {
    // Detect block boundaries before deciding whether their URL identifies a supported source.
    // This recognizes a rendered header, not a signed provider/source identity.
    const header = /^([^\r\n]*) \(([^\r\n]*)\)\r?\n【(turn\d+[a-z]+\d+)】 \[wordlim: (\d+)\]/gm;
    const matches = Array.from(item.text.matchAll(header));
    if (matches.length === 0) {
      if (item.text.length > 0) {
        unparsed.push({ content_index: item.content_index, range: [0, item.text.length] });
      }
      continue;
    }
    if (matches[0].index > 0) {
      unparsed.push({ content_index: item.content_index, range: [0, matches[0].index] });
    }
    for (let index = 0; index < matches.length; index += 1) {
      const match = matches[index];
      const wordLimit = Number(match[4]);
      if (!Number.isSafeInteger(wordLimit)) {
        return refuse("UNSUPPORTED_RENDERING", "INVALID_WORD_LIMIT", { content_index: item.content_index, header_start: match.index });
      }
      if (match[0].length > limits.max_header_chars) {
        return refuse("INPUT_LIMIT", "HEADER_CHAR_LIMIT", {
          content_index: item.content_index, header_start: match.index,
          observed: match[0].length, maximum: limits.max_header_chars
        });
      }
      const start = match.index + match[0].length;
      const end = index + 1 < matches.length ? matches[index + 1].index : item.text.length;
      const reference = match[3];
      if (!/^turn\d+(?:search|view|fetch|news|academia)\d+$/.test(reference)) {
        unparsed.push({
          content_index: item.content_index,
          range: [match.index, end],
          reason: "SOURCE_HEADER_WITHOUT_SUPPORTED_REFERENCE",
          reference_id: reference,
          rendered_header_range: [match.index, start]
        });
        continue;
      }
      if (!/^https?:\/\/[^\s\r\n]+$/.test(match[2])) {
        unparsed.push({
          content_index: item.content_index,
          range: [match.index, end],
          reason: "SOURCE_HEADER_WITHOUT_SUPPORTED_URL",
          reference_id: reference,
          rendered_header_range: [match.index, start]
        });
        continue;
      }
      if (seen.has(reference)) duplicates.add(reference);
      seen.add(reference);
      parsed.push({
        source_index: parsed.length,
        content_index: item.content_index,
        reference_id: reference,
        title: match[1],
        url: match[2],
        word_limit: wordLimit,
        rendered_source_range: [match.index, end],
        rendered_header_range: [match.index, start],
        rendered_content_range: [start, end],
        text: item.text,
        content_chars: end - start
      });
    }
  }

  base.coverage = {
    ...base.coverage,
    parsed_sources: parsed.length,
    unparsed_text_ranges: unparsed,
    non_text_items: nonText,
    duplicate_reference_ids: Array.from(duplicates)
  };
  if (parsed.length === 0) {
    return refuse("UNRECOGNIZED_RENDERING", "NO_SUPPORTED_SOURCE_HEADERS", {});
  }
  if (requested !== null && requested.some(index => index >= parsed.length)) {
    throw new RangeError("source_indices contains an index outside the retained parsed sources");
  }
  if (requested === null && limits.start_index > parsed.length) {
    throw new RangeError("start_index exceeds the retained parsed source count");
  }

  const indices = requested === null
    ? Array.from({ length: Math.min(limits.max_sources, parsed.length - limits.start_index) }, (_, i) => limits.start_index + i)
    : requested;
  let remaining = limits.max_total_content_chars;
  let selectedChars = 0;
  let returnedChars = 0;
  let truncated = 0;
  const sources = indices.map(index => {
    const entry = parsed[index];
    const maximum = Math.min(limits.max_content_chars, remaining, entry.content_chars);
    const length = prefixLength(entry.text, entry.rendered_content_range[0], maximum);
    selectedChars += entry.content_chars;
    returnedChars += length;
    remaining -= length;
    const isTruncated = length < entry.content_chars;
    if (isTruncated) truncated += 1;
    const { text, ...metadata } = entry;
    return {
      ...metadata,
      rendered_content: text.slice(entry.rendered_content_range[0], entry.rendered_content_range[0] + length),
      returned_content_range: [entry.rendered_content_range[0], entry.rendered_content_range[0] + length],
      returned_chars: length,
      truncated: isTruncated
    };
  });
  const endIndex = requested === null ? limits.start_index + indices.length : null;
  return {
    ...base,
    status: "PROJECTED",
    coverage: {
      ...base.coverage,
      selection_mode: requested === null ? "contiguous" : "source_indices",
      selected_source_indices: indices,
      start_index: requested === null ? limits.start_index : null,
      next_index: requested === null && endIndex < parsed.length ? endIndex : null,
      returned_sources: sources.length,
      omitted_sources: parsed.length - sources.length,
      omitted_source_index_ranges: omittedRanges(parsed.length, indices),
      selected_content_chars: selectedChars,
      returned_content_chars: returnedChars,
      truncated_sources: truncated,
      all_rendered_source_content_included: sources.length === parsed.length && truncated === 0,
      all_input_text_has_source_headers: unparsed.length === 0
    },
    sources
  };
}

module.exports = { projectWebSources, SCHEMA, DEFAULTS };
