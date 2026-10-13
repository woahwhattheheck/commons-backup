'use strict';

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const DEFAULTS = Object.freeze({max_files: 64, max_source_chars: 16777216,
  max_matches: 100, max_metadata_chars: 8192, excerpt_chars: 0,
  max_total_excerpt_chars: 0});

class RetainedGitHubFileSearchError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'RetainedGitHubFileSearchError';
    this.code = code;
    this.details = {...details};
  }
  toJSON() {
    return {name: this.name, code: this.code, message: this.message, details: {...this.details}};
  }
}

function fail(code, message, details) {
  throw new RetainedGitHubFileSearchError(code, message, details);
}

/**
 * Case-sensitive literal search over explicitly supplied retained UTF-8
 * native full-file requests/responses. No provider call, regex, retry or repository-wide inference.
 */
function findRetainedGitHubText(files, options) {
  if (!Array.isArray(files) || !object(options)) {
    fail('INVALID_INPUT', 'Supply retained file descriptors and options');
  }
  for (const key of Object.keys(options)) {
    if (key !== 'literal' && !own(DEFAULTS, key)) fail('INVALID_OPTIONS', 'Unknown option: ' + key);
  }
  const literal = options.literal;
  if (typeof literal !== 'string' || literal.length < 1 || literal.length > 4096) {
    fail('INVALID_LITERAL', 'literal must contain 1 to 4096 UTF-16 code units');
  }
  const limits = {...DEFAULTS}, bounds = {max_files: [1, 1024],
    max_source_chars: [1, 67108864], max_matches: [0, 10000],
    max_metadata_chars: [0, 1048576], excerpt_chars: [0, 8192],
    max_total_excerpt_chars: [0, 1048576]};
  for (const key of Object.keys(DEFAULTS)) {
    if (!own(options, key)) continue;
    const value = options[key], [min, max] = bounds[key];
    if (!Number.isSafeInteger(value) || value < min || value > max) {
      fail('INVALID_BOUND', key + ' must be an integer from ' + min + ' to ' + max);
    }
    limits[key] = value;
  }
  if (files.length > limits.max_files) fail('FILE_BOUND', 'Retained files exceed max_files');
  let totalSourceChars = 0;
  const accepted = [];
  for (let index = 0; index < files.length; index++) {
    const file = files[index], request = file?.request, response = file?.response;
    const data = response?.structuredContent;
    if (!own(files, index) || !object(file) || !object(request) || !object(response)
        || response.isError === true || !object(data) || typeof data.content !== 'string'
        || data.encoding !== 'utf-8' || !/^[0-9a-f]{40}$/.test(data.sha ?? '')
        || typeof request.repository_full_name !== 'string' || !request.repository_full_name
        || typeof request.path !== 'string' || !request.path
        || (own(request, 'ref') && request.ref !== null && typeof request.ref !== 'string')) {
      fail('EXPECTED_NATIVE_FILE', 'Expected retained UTF-8 native file request/response', {file_index: index});
    }
    if (request.start_line != null || request.end_line != null
        || (request.encoding != null && request.encoding !== 'utf-8')) {
      fail('PARTIAL_FILE_REQUEST', 'Line-selected or non-UTF-8 requests are not full-file inputs', {file_index: index});
    }
    totalSourceChars += data.content.length;
    if (totalSourceChars > limits.max_source_chars) {
      fail('SOURCE_BOUND', 'Supplied retained texts exceed max_source_chars', {file_index: index});
    }
    accepted.push({index, request, data});
  }

  let metadataChars = 0, excerptChars = 0, totalMatches = 0;
  const metadataOmissions = [], views = [], matches = [];
  const field = (fileIndex, name, value, present, sourcePath) => {
    if (!present) return {status: 'absent', source_path: sourcePath};
    if (value === null) return {status: 'null', value: null, source_path: sourcePath};
    if (typeof value !== 'string') return {status: 'unsupported_type', source_path: sourcePath,
      observed_type: typeof value};
    if (metadataChars + value.length > limits.max_metadata_chars) {
      metadataOmissions.push({file_index: fileIndex, field: name,
        source_path: sourcePath, original_chars: value.length, reason: 'metadata_budget'});
      return {status: 'omitted_budget', source_path: sourcePath, original_chars: value.length};
    }
    metadataChars += value.length;
    return {status: 'retained', value, source_path: sourcePath};
  };
  let literalNewlines = 0, lastLiteralNewline = -1;
  for (let index = 0; index < literal.length; index++) {
    if (literal[index] === '\n') { literalNewlines++; lastLiteralNewline = index; }
  }

  for (const file of accepted) {
    const base = ['files', file.index], contentPath = [...base, 'response', 'structuredContent', 'content'];
    const fields = {
      repository_full_name: field(file.index, 'repository_full_name', file.request.repository_full_name,
        true, [...base, 'request', 'repository_full_name']),
      path: field(file.index, 'path', file.request.path, true, [...base, 'request', 'path']),
      ref: field(file.index, 'ref', file.request.ref, own(file.request, 'ref'), [...base, 'request', 'ref']),
      sha: field(file.index, 'sha', file.data.sha, true, [...base, 'response', 'structuredContent', 'sha']),
      display_url: field(file.index, 'display_url', file.data.display_url, own(file.data, 'display_url'),
        [...base, 'response', 'structuredContent', 'display_url'])
    };
    let from = 0, scannedThrough = 0, line = 1, lineStart = 0, fileMatches = 0;
    for (;;) {
      const offset = file.data.content.indexOf(literal, from);
      if (offset < 0) break;
      let newline = file.data.content.indexOf('\n', scannedThrough);
      while (newline >= 0 && newline < offset) {
        line++;
        lineStart = newline + 1;
        scannedThrough = newline + 1;
        newline = file.data.content.indexOf('\n', scannedThrough);
      }
      scannedThrough = offset;
      const column = offset - lineStart + 1, ordinal = totalMatches++;
      fileMatches++;
      if (matches.length < limits.max_matches) {
        const returned = Math.min(limits.excerpt_chars,
          limits.max_total_excerpt_chars - excerptChars, file.data.content.length - offset);
        const excerpt = file.data.content.slice(offset, offset + returned);
        excerptChars += excerpt.length;
        matches.push({match_index: ordinal, file_index: file.index,
          match: {source_path: contentPath, start_offset: offset,
            end_offset_exclusive: offset + literal.length, start_line: line, start_column: column,
            end_line: line + literalNewlines, end_column_exclusive: literalNewlines
              ? literal.length - lastLiteralNewline : column + literal.length},
          excerpt: {source_path: contentPath, start_offset: offset,
            end_offset_exclusive: offset + excerpt.length, returned_chars: excerpt.length,
            contains_full_match: excerpt.length >= literal.length,
            status: excerpt.length ? 'retained' : 'omitted_budget', text: excerpt}});
      }
      from = offset + 1;
    }
    views.push({file_index: file.index, fields, content_source_path: contentPath,
      retained_source_chars: file.data.content.length, full_file_requested: true,
      total_retained_text_matches: fileMatches});
  }
  return {schema: 'commons.connected_github_file_search/v1', status: 'searched',
    query: {literal_chars: literal.length, case_sensitive: true, matching: 'literal',
      overlapping_matches: true, line_separator: 'LF', offsets: 'zero_based_utf16',
      line_columns: 'one_based_utf16; end_column_exclusive'},
    coverage: {scope: 'supplied_retained_texts_only', repository_wide: false,
      provided_files: files.length, total_retained_source_chars: totalSourceChars,
      sha_semantics: 'literal_native_header; content_identity_not_independently_computed'},
    files: views, total_matches: totalMatches, returned_matches: matches.length,
    omitted_matches: totalMatches - matches.length, matches,
    budgets: {metadata_chars: metadataChars, excerpt_chars: excerptChars,
      max_metadata_chars: limits.max_metadata_chars, max_total_excerpt_chars: limits.max_total_excerpt_chars},
    metadata_omissions: metadataOmissions, provider_calls: 0};
}

module.exports = {findRetainedGitHubText, RetainedGitHubFileSearchError};
