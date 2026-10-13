'use strict';

/**
 * Exact, bounded line alignment for retained strings.
 * No I/O, patch application, source normalization, or provider assumptions.
 */
function limitsFor(options, defaults, ceilings, zero) {
  if (!options || typeof options !== 'object' || Array.isArray(options)) {
    throw new TypeError('options must be an object');
  }
  for (const key of Object.keys(options)) {
    if (!Object.prototype.hasOwnProperty.call(defaults, key)) {
      throw new TypeError('unknown option: ' + key);
    }
  }
  const limits = {...defaults, ...options};
  for (const [key, value] of Object.entries(limits)) {
    if (!Number.isSafeInteger(value) || value < (zero.includes(key) ? 0 : 1) ||
        value > ceilings[key]) {
      throw new TypeError('invalid option: ' + key);
    }
  }
  return limits;
}

function retainedLines(text, maximum, side) {
  const lines = [];
  let start = 0;
  while (start < text.length) {
    if (lines.length === maximum) {
      throw new RangeError(side + ' exceeds max_lines_per_input');
    }
    const newline = text.indexOf('\n', start);
    const end = newline === -1 ? text.length : newline + 1;
    lines.push({start, end, text: text.slice(start, end)});
    start = end;
  }
  return lines;
}

function createTextDiff(beforeText, afterText, options = {}) {
  if (typeof beforeText !== 'string' || typeof afterText !== 'string') {
    throw new TypeError('beforeText and afterText must be complete retained strings');
  }
  const limits = limitsFor(options, {
    context_lines: 3, max_input_chars: 1048576,
    max_lines_per_input: 10000, max_matrix_cells: 2000000,
  }, {
    context_lines: 20, max_input_chars: 8388608,
    max_lines_per_input: 50000, max_matrix_cells: 4000000,
  }, ['context_lines']);
  if (beforeText.length + afterText.length > limits.max_input_chars) {
    throw new RangeError('combined retained strings exceed max_input_chars');
  }
  const before = retainedLines(beforeText, limits.max_lines_per_input, 'beforeText');
  const after = retainedLines(afterText, limits.max_lines_per_input, 'afterText');
  let lineIds = new Map();
  for (const lines of [before, after]) {
    for (const line of lines) {
      if (!lineIds.has(line.text)) lineIds.set(line.text, lineIds.size);
      line.key = lineIds.get(line.text);
    }
  }
  lineIds = null;
  let prefix = 0;
  while (prefix < before.length && prefix < after.length &&
         before[prefix].key === after[prefix].key) prefix++;
  let suffix = 0;
  while (suffix < before.length - prefix && suffix < after.length - prefix &&
         before[before.length - suffix - 1].key === after[after.length - suffix - 1].key) {
    suffix++;
  }
  const oldMiddle = before.length - prefix - suffix;
  const newMiddle = after.length - prefix - suffix;
  const width = newMiddle + 1;
  const cells = oldMiddle && newMiddle ? (oldMiddle + 1) * width : 0;
  if (cells > limits.max_matrix_cells) {
    throw new RangeError('line alignment needs ' + cells +
      ' matrix cells; exceeds max_matrix_cells=' + limits.max_matrix_cells);
  }
  let matrix = cells ? new Uint32Array(cells) : null;
  if (matrix) {
    for (let i = oldMiddle - 1; i >= 0; i--) {
      for (let j = newMiddle - 1; j >= 0; j--) {
        matrix[i * width + j] = before[prefix + i].key === after[prefix + j].key
          ? matrix[(i + 1) * width + j + 1] + 1
          : Math.max(matrix[(i + 1) * width + j], matrix[i * width + j + 1]);
      }
    }
  }
  const operations = [];
  let oldCursor = 0, newCursor = 0, matched = 0;
  const emit = kind => {
    operations.push({kind, before_cursor: oldCursor, after_cursor: newCursor,
      before_index: kind === 'insert' ? null : oldCursor,
      after_index: kind === 'delete' ? null : newCursor});
    if (kind !== 'insert') oldCursor++;
    if (kind !== 'delete') newCursor++;
    if (kind === 'context') matched++;
  };
  for (let i = 0; i < prefix; i++) emit('context');
  let i = 0, j = 0;
  while (i < oldMiddle || j < newMiddle) {
    if (i < oldMiddle && j < newMiddle &&
        before[prefix + i].key === after[prefix + j].key) {
      emit('context'); i++; j++;
    } else if (i < oldMiddle && (j === newMiddle ||
               matrix[(i + 1) * width + j] >= matrix[i * width + j + 1])) {
      emit('delete'); i++;
    } else {
      emit('insert'); j++;
    }
  }
  for (let k = 0; k < suffix; k++) emit('context');
  matrix = null;

  const spans = [];
  for (let k = 0; k < operations.length; k++) {
    if (operations[k].kind === 'context') continue;
    const start = Math.max(0, k - limits.context_lines);
    const end = Math.min(operations.length, k + limits.context_lines + 1);
    const last = spans[spans.length - 1];
    if (last && start <= last.end) last.end = Math.max(last.end, end);
    else spans.push({start, end});
  }
  const offsets = [0];
  const hunks = spans.map((span, index) => {
    const first = operations[span.start], last = operations[span.end - 1];
    const rowCount = span.end - span.start;
    offsets.push(offsets[offsets.length - 1] + rowCount);
    return {index, operation_start: span.start, row_count: rowCount,
      before_start_line: first.before_cursor + 1,
      before_line_count: last.before_cursor + (last.kind === 'insert' ? 0 : 1) - first.before_cursor,
      after_start_line: first.after_cursor + 1,
      after_line_count: last.after_cursor + (last.kind === 'delete' ? 0 : 1) - first.after_cursor};
  });
  const source = Object.freeze({
    before_chars: beforeText.length, after_chars: afterText.length,
    before_lines: before.length, after_lines: after.length,
    exact_equal: beforeText === afterText, range_units: 'utf16_code_units',
    range_end: 'exclusive', line_numbers: 'one_based',
    line_separator: 'LF', normalization: 'none',
  });
  const statistics = Object.freeze({
    comparison_complete: true, algorithm: 'line_lcs', tie_break: 'delete_before_insert',
    common_prefix_lines: prefix, common_suffix_lines: suffix,
    matrix_cells: cells, matrix_bytes: cells * Uint32Array.BYTES_PER_ELEMENT,
    matched_lines: matched, inserted_lines: after.length - matched,
    deleted_lines: before.length - matched, hunk_count: hunks.length,
    hunk_rows: offsets[offsets.length - 1],
  });

  function project(projectionOptions = {}) {
    const viewLimits = limitsFor(projectionOptions, {
      start_hunk: 0, start_row: 0, max_hunks: 8, max_rows: 160,
      max_line_chars: 400, max_total_line_chars: 12000,
    }, {
      start_hunk: Number.MAX_SAFE_INTEGER, start_row: Number.MAX_SAFE_INTEGER,
      max_hunks: 256, max_rows: 2000, max_line_chars: 65536,
      max_total_line_chars: 262144,
    }, ['start_hunk', 'start_row', 'max_line_chars', 'max_total_line_chars']);
    if (viewLimits.start_hunk > hunks.length ||
        (viewLimits.start_hunk === hunks.length && viewLimits.start_row !== 0) ||
        (viewLimits.start_hunk < hunks.length &&
         viewLimits.start_row >= hunks[viewLimits.start_hunk].row_count)) {
      throw new RangeError('projection start is outside the retained hunk rows');
    }
    const result = {
      schema: 'commons.connected_text_diff_projection/v1', status: 'PROJECTED',
      source, statistics, limits: viewLimits, hunks: [], coverage: null,
    };
    let hunkIndex = viewLimits.start_hunk, rowIndex = viewLimits.start_row;
    let returnedRows = 0, returnedChars = 0, selectedChars = 0, clippedRows = 0;
    while (hunkIndex < hunks.length && result.hunks.length < viewLimits.max_hunks &&
           returnedRows < viewLimits.max_rows) {
      const hunk = hunks[hunkIndex];
      const firstRow = rowIndex;
      const rows = [];
      while (rowIndex < hunk.row_count && returnedRows < viewLimits.max_rows) {
        const op = operations[hunk.operation_start + rowIndex];
        const oldLine = op.before_index === null ? null : before[op.before_index];
        const newLine = op.after_index === null ? null : after[op.after_index];
        const line = oldLine || newLine;
        let length = Math.min(line.text.length, viewLimits.max_line_chars,
          viewLimits.max_total_line_chars - returnedChars);
        if (length > 0 && length < line.text.length &&
            line.text.charCodeAt(length - 1) >= 0xd800 &&
            line.text.charCodeAt(length - 1) <= 0xdbff &&
            line.text.charCodeAt(length) >= 0xdc00 &&
            line.text.charCodeAt(length) <= 0xdfff) length--;
        const truncated = length < line.text.length;
        rows.push({
          kind: op.kind,
          before_line: op.before_index === null ? null : op.before_index + 1,
          after_line: op.after_index === null ? null : op.after_index + 1,
          before_range: oldLine ? [oldLine.start, oldLine.end] : null,
          after_range: newLine ? [newLine.start, newLine.end] : null,
          line_ending: line.text.endsWith('\r\n') ? 'CRLF' : line.text.endsWith('\n') ? 'LF' : 'none',
          text: line.text.slice(0, length), content_chars: line.text.length,
          returned_chars: length, truncated,
        });
        returnedRows++; returnedChars += length; selectedChars += line.text.length;
        if (truncated) clippedRows++;
        rowIndex++;
      }
      result.hunks.push({
        index: hunk.index, before_start_line: hunk.before_start_line,
        before_line_count: hunk.before_line_count,
        after_start_line: hunk.after_start_line, after_line_count: hunk.after_line_count,
        row_count: hunk.row_count, selected_row_range: [firstRow, rowIndex], rows,
      });
      if (rowIndex === hunk.row_count) { hunkIndex++; rowIndex = 0; }
    }
    const omittedBefore = offsets[viewLimits.start_hunk] + viewLimits.start_row;
    result.coverage = {
      scope: 'retained_input_strings_only', snapshot: false,
      comparison_complete: true, hunk_count: hunks.length,
      total_hunk_rows: statistics.hunk_rows,
      start_hunk: viewLimits.start_hunk, start_row: viewLimits.start_row,
      returned_hunks: result.hunks.length, returned_rows: returnedRows,
      omitted_rows_before: omittedBefore,
      omitted_rows_after: statistics.hunk_rows - omittedBefore - returnedRows,
      truncated_rows: clippedRows, selected_line_chars: selectedChars,
      returned_line_chars: returnedChars,
      all_hunks_included: viewLimits.start_hunk === 0 && result.hunks.length === hunks.length,
      all_hunk_rows_included: omittedBefore === 0 &&
        returnedRows === statistics.hunk_rows && clippedRows === 0,
      next_position: hunkIndex < hunks.length ? {hunk_index: hunkIndex, row_index: rowIndex} : null,
    };
    return result;
  }

  return Object.freeze({schema: 'commons.connected_text_diff/v1', source, statistics, project});
}

module.exports = {createTextDiff};
