'use strict';

const {gitBlobIdentity} = require('./connected_git_blob_identity.cjs');

function object(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(name + ' must be an object');
  }
  return value;
}

function onlyKeys(value, allowed, name) {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) throw new TypeError('unknown ' + name + ': ' + key);
  }
}

// Numeric limits and surrogate-safe prefixes follow connected_text_diff.cjs.
function limitsFor(options, defaults, ceilings, zero) {
  object(options, 'options');
  onlyKeys(options, Object.keys(defaults), 'option');
  const limits = {...defaults, ...options};
  for (const [key, value] of Object.entries(limits)) {
    if (!Number.isSafeInteger(value) || value < (zero.includes(key) ? 0 : 1)
        || value > ceilings[key]) throw new TypeError('invalid option: ' + key);
  }
  return limits;
}

function retainedLines(text, maximum) {
  const lines = [];
  let start = 0;
  while (start < text.length) {
    if (lines.length === maximum) throw new RangeError('content exceeds max_lines');
    const newline = text.indexOf('\n', start);
    const end = newline === -1 ? text.length : newline + 1;
    lines.push({start, end});
    start = end;
  }
  return lines;
}

/** Verify one complete UTF-8 leaf once, then project its literal line ranges. */
function createTextLines(leaf, options = {}) {
  object(leaf, 'leaf');
  onlyKeys(leaf, ['content', 'encoding', 'expected_blob_sha', 'locators'], 'leaf field');
  if (typeof leaf.content !== 'string' || leaf.encoding !== 'utf-8') {
    throw new TypeError('leaf requires string content and explicit utf-8 encoding');
  }
  if (typeof leaf.expected_blob_sha !== 'string'
      || !/^[0-9a-f]{40}$/.test(leaf.expected_blob_sha)) {
    throw new TypeError('expected_blob_sha must be a complete lowercase Git blob SHA');
  }
  const limits = limitsFor(options, {max_input_chars: 1048576, max_lines: 10000},
    {max_input_chars: 8388608, max_lines: 50000}, []);
  const content = leaf.content;
  if (content.length > limits.max_input_chars) {
    throw new RangeError('content exceeds max_input_chars');
  }
  const locators = {};
  if (Object.prototype.hasOwnProperty.call(leaf, 'locators')) {
    object(leaf.locators, 'locators');
    onlyKeys(leaf.locators, ['repository_full_name', 'path', 'ref', 'url'], 'locator');
    for (const [key, value] of Object.entries(leaf.locators)) {
      if (typeof value !== 'string' || value.length === 0 || value.length > 4096) {
        throw new TypeError('invalid locator: ' + key);
      }
      locators[key] = value;
    }
  }
  const identity = gitBlobIdentity(content);
  if (identity.git_blob_sha !== leaf.expected_blob_sha) {
    const error = new Error('complete UTF-8 content does not match expected_blob_sha');
    error.code = 'TEXT_SOURCE_BLOB_MISMATCH';
    error.expected_blob_sha = leaf.expected_blob_sha;
    error.observed_blob_sha = identity.git_blob_sha;
    error.observed_bytes = identity.bytes;
    throw error;
  }
  const lines = retainedLines(content, limits.max_lines);
  const source = Object.freeze({
    encoding: 'utf-8', expected_blob_sha: leaf.expected_blob_sha,
    git_blob_sha: identity.git_blob_sha, bytes: identity.bytes,
    identity_matches: true, identity_basis: 'computed_git_blob_sha1_utf8',
    chars: content.length, lines: lines.length,
    locators: Object.freeze(locators), locator_binding: 'caller_supplied_not_verified',
    range_units: 'utf16_code_units', range_origin: 'zero_based', range_end: 'exclusive',
    line_numbers: 'one_based', line_range_end: 'exclusive',
    line_separator: 'LF', normalization: 'none',
  });
  const sourceRange = (startLine, endLine) => [
    startLine <= lines.length ? lines[startLine - 1].start : content.length,
    endLine <= lines.length ? lines[endLine - 1].start : content.length,
  ];

  function project(projectionOptions = {}) {
    object(projectionOptions, 'projection options');
    onlyKeys(projectionOptions,
      ['start_line', 'line_ranges', 'max_lines', 'max_line_chars', 'max_total_line_chars'],
      'projection option');
    const numericOptions = {};
    for (const key of ['start_line', 'max_lines', 'max_line_chars', 'max_total_line_chars']) {
      if (Object.prototype.hasOwnProperty.call(projectionOptions, key)) {
        numericOptions[key] = projectionOptions[key];
      }
    }
    const viewLimits = limitsFor(numericOptions,
      {start_line: 1, max_lines: 160, max_line_chars: 400, max_total_line_chars: 12000},
      {start_line: lines.length + 1, max_lines: 2000,
        max_line_chars: 65536, max_total_line_chars: 262144},
      ['max_line_chars', 'max_total_line_chars']);
    const sparse = Object.prototype.hasOwnProperty.call(projectionOptions, 'line_ranges');
    const ranges = [];
    let selectedLines = 0;
    if (sparse) {
      if (Object.prototype.hasOwnProperty.call(projectionOptions, 'start_line')) {
        throw new TypeError('line_ranges and start_line are mutually exclusive');
      }
      const supplied = projectionOptions.line_ranges;
      if (!Array.isArray(supplied) || supplied.length > 128) {
        throw new TypeError('line_ranges must be an array of at most 128 ranges');
      }
      let previousEnd = 1;
      for (let index = 0; index < supplied.length; index++) {
        if (!Object.prototype.hasOwnProperty.call(supplied, index)) {
          throw new TypeError('line_ranges must be dense');
        }
        const pair = supplied[index];
        if (!Array.isArray(pair) || pair.length !== 2
            || !Object.prototype.hasOwnProperty.call(pair, 0)
            || !Object.prototype.hasOwnProperty.call(pair, 1)) {
          throw new TypeError('each line range must be a dense start/end pair');
        }
        const [start, end] = pair;
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end)
            || start < previousEnd || start < 1 || end <= start || end > lines.length + 1) {
          throw new RangeError('line ranges must be ordered, nonoverlapping, and in bounds');
        }
        selectedLines += end - start;
        if (selectedLines > viewLimits.max_lines) {
          throw new RangeError('selected line ranges exceed max_lines');
        }
        ranges.push([start, end]);
        previousEnd = end;
      }
    } else {
      const end = Math.min(lines.length + 1, viewLimits.start_line + viewLimits.max_lines);
      if (end > viewLimits.start_line) ranges.push([viewLimits.start_line, end]);
      selectedLines = end - viewLimits.start_line;
    }

    const omittedLineRanges = [];
    let cursor = 1;
    for (const [start, end] of ranges) {
      if (cursor < start) omittedLineRanges.push([cursor, start]);
      cursor = end;
    }
    if (cursor <= lines.length) omittedLineRanges.push([cursor, lines.length + 1]);
    const rows = [], truncatedSourceRanges = [];
    let selectedChars = 0, returnedChars = 0, truncatedLines = 0;
    for (const [start, end] of ranges) {
      for (let number = start; number < end; number++) {
        const line = lines[number - 1];
        const size = line.end - line.start;
        let length = Math.min(size, viewLimits.max_line_chars,
          viewLimits.max_total_line_chars - returnedChars);
        if (length > 0 && length < size
            && content.charCodeAt(line.start + length - 1) >= 0xd800
            && content.charCodeAt(line.start + length - 1) <= 0xdbff
            && content.charCodeAt(line.start + length) >= 0xdc00
            && content.charCodeAt(line.start + length) <= 0xdfff) length--;
        const truncated = length < size;
        const ending = content.charCodeAt(line.end - 1) === 10
          ? (line.end - line.start >= 2 && content.charCodeAt(line.end - 2) === 13
            ? 'CRLF' : 'LF') : 'none';
        rows.push({
          line_number: number, source_range: [line.start, line.end],
          returned_range: [line.start, line.start + length], line_ending: ending,
          text: content.slice(line.start, line.start + length),
          content_chars: size, returned_chars: length, truncated,
        });
        selectedChars += size;
        returnedChars += length;
        if (truncated) {
          truncatedLines++;
          truncatedSourceRanges.push([line.start + length, line.end]);
        }
      }
    }
    const nextLine = sparse ? null : viewLimits.start_line + selectedLines;
    return {
      schema: 'commons.connected_text_lines_projection/v1', status: 'PROJECTED', source,
      limits: {
        max_lines: viewLimits.max_lines, max_line_chars: viewLimits.max_line_chars,
        max_total_line_chars: viewLimits.max_total_line_chars,
        ...(sparse ? {} : {start_line: viewLimits.start_line}),
      },
      selection: {mode: sparse ? 'line_ranges' : 'contiguous',
        line_ranges: ranges.map(pair => pair.slice()), line_numbers: 'one_based',
        range_end: 'exclusive'},
      lines: rows,
      coverage: {
        scope: 'retained_verified_utf8_text_only', snapshot: false,
        source_lines: lines.length, returned_lines: rows.length,
        omitted_lines: lines.length - rows.length,
        omitted_line_ranges: omittedLineRanges,
        omitted_source_ranges: omittedLineRanges.map(pair => sourceRange(...pair)),
        selected_content_chars: selectedChars, returned_content_chars: returnedChars,
        omitted_content_chars: content.length - selectedChars,
        truncated_content_chars: selectedChars - returnedChars,
        truncated_lines: truncatedLines, truncated_source_ranges: truncatedSourceRanges,
        all_source_lines_selected: rows.length === lines.length,
        all_selected_content_included: truncatedLines === 0,
        all_source_content_included: rows.length === lines.length && truncatedLines === 0,
        navigation: sparse ? 'caller_selected_ranges' : 'next_start_line',
        next_start_line: nextLine !== null && nextLine <= lines.length ? nextLine : null,
      },
    };
  }

  return Object.freeze({schema: 'commons.connected_text_lines/v1',
    source, limits: Object.freeze({...limits}), project});
}

module.exports = {createTextLines};
