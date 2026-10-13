'use strict';

// Native Gmail search only. No MIME parsing, writes, retries, query rewriting or account inference.
const BINDING = 'mcp__codex_apps__gmail_search_emails';
const SCHEMA = 'commons.connected_gmail_search_pages/v1';
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function fail(code, message) {
  const error = new TypeError(message);
  error.code = code;
  throw error;
}
function integer(value, fallback, maximum, name, minimum = 1) {
  const result = value === undefined ? fallback : value;
  if (!Number.isSafeInteger(result) || result < minimum || result > maximum) {
    fail('INVALID_INPUT', name + ' is outside its integer budget');
  }
  return result;
}
function boundedText(value, name, maximum, allowEmpty = false) {
  if (typeof value !== 'string' || (!allowEmpty && value.length === 0) || value.length > maximum) {
    fail('INVALID_INPUT', name + ' must be bounded text');
  }
  return value;
}
function copyArgs(args) {
  const out = {};
  for (const key of ['query', 'label_ids', 'max_results', 'next_page_token']) {
    if (own(args, key)) out[key] = Array.isArray(args[key]) ? args[key].slice() : args[key];
  }
  return out;
}
function normalizeRequest(input) {
  if (!record(input) || !record(input.args)) fail('INVALID_INPUT', 'request.args is required');
  const allowed = new Set(['args', 'max_pages', 'timeout_ms', 'max_response_chars', 'max_total_response_chars']);
  for (const key of Object.keys(input)) if (!allowed.has(key)) fail('INVALID_INPUT', 'Unknown request field: ' + key);
  const native = new Set(['query', 'label_ids', 'max_results', 'next_page_token']);
  for (const key of Object.keys(input.args)) if (!native.has(key)) fail('INVALID_INPUT', 'Unknown native argument: ' + key);
  const args = copyArgs(input.args);
  if (own(args, 'query')) boundedText(args.query, 'query', 8192, true);
  if (own(args, 'label_ids') && args.label_ids !== null) {
    if (!Array.isArray(args.label_ids) || args.label_ids.length > 100) fail('INVALID_INPUT', 'label_ids must be a bounded array or null');
    for (let i = 0; i < args.label_ids.length; i += 1) {
      if (!own(args.label_ids, i)) fail('INVALID_INPUT', 'label_ids must be dense');
      boundedText(args.label_ids[i], 'label_ids[' + i + ']', 256);
    }
  }
  args.max_results = integer(args.max_results, 20, 100, 'max_results');
  if (own(args, 'next_page_token')) boundedText(args.next_page_token, 'next_page_token', 8192);
  return {
    args,
    max_pages: integer(input.max_pages, 1, 10, 'max_pages'),
    timeout_ms: integer(input.timeout_ms, 30000, 60000, 'timeout_ms'),
    max_response_chars: integer(input.max_response_chars, 1048576, 8388608, 'max_response_chars'),
    max_total_response_chars: integer(input.max_total_response_chars, 4194304, 16777216, 'max_total_response_chars'),
  };
}
function nextRequest(request, args) {
  return Object.assign({}, request, {args: copyArgs(args)});
}
function nativeError(raw) {
  if (!record(raw)) return false;
  const data = raw.structuredContent;
  return raw.isError === true || (record(data) && (own(data, 'error') || own(data, 'error_code')));
}
function parsePage(raw, size) {
  if (!record(raw) || nativeError(raw)) fail('NATIVE_ERROR', 'Native response is not successful');
  const data = raw.structuredContent;
  if (!record(data) || !Array.isArray(data.emails) || !own(data, 'next_page_token')) {
    fail('UNSUPPORTED_PAYLOAD', 'Expected structuredContent.emails and next_page_token');
  }
  if (data.emails.length > size) fail('PAGE_SIZE_MISMATCH', 'Native row count exceeds the requested max_results');
  for (let i = 0; i < data.emails.length; i += 1) {
    if (!own(data.emails, i) || !record(data.emails[i])) fail('UNSUPPORTED_PAYLOAD', 'Email rows must be dense objects');
  }
  const token = data.next_page_token;
  if (token !== null && (typeof token !== 'string' || !token.length || token.length > 8192)) {
    fail('UNSUPPORTED_PAGINATION', 'next_page_token must be null or bounded nonempty text');
  }
  return {emails: data.emails, token};
}
function errorMetadata(raw) {
  const data = record(raw) && record(raw.structuredContent) ? raw.structuredContent : {};
  const detail = record(data.error_data) ? data.error_data : {};
  const out = {response_is_error: record(raw) ? raw.isError === true : null};
  if (typeof data.error_code === 'string' && data.error_code.length <= 128) out.error_code = data.error_code;
  else if (own(data, 'error_code')) out.error_code_status = 'invalid_or_limit_exceeded';
  if (Number.isInteger(detail.code)) out.http_status = detail.code;
  if (typeof data.retry_after === 'string' && data.retry_after.length <= 256) out.retry_after = data.retry_after;
  else if (own(data, 'retry_after')) out.retry_after_status = 'invalid_or_limit_exceeded';
  if (Number.isFinite(data.retry_after_seconds)) out.retry_after_seconds = data.retry_after_seconds;
  return out;
}

async function collectGmailSearchPages(tools, input) {
  const request = normalizeRequest(input);
  if (!tools || typeof tools[BINDING] !== 'function') fail('MISSING_BINDING', 'Native Gmail search binding is required');
  const start = Date.now();
  const result = {
    schema: SCHEMA, operation: 'search_emails', binding: BINDING,
    request: nextRequest(request, request.args),
    started_at: new Date(start).toISOString(),
    pages: [], responses: [],
    next_request: nextRequest(request, request.args),
    summary: {
      calls: 0, successful_pages: 0, retained_responses: 0, rows_observed: 0,
      response_chars: 0, provider_end_observed: false, stop_reason: null,
      next_request_basis: 'unattempted_request',
      query_application: 'not_verified', snapshot: false, account_identity: 'not_inferred',
    },
  };
  let args = copyArgs(request.args);
  const seenTokens = new Set(own(args, 'next_page_token') ? [args.next_page_token] : []);
  while (result.pages.length < request.max_pages) {
    if (Date.now() - start >= request.timeout_ms) {
      result.summary.stop_reason = 'TIME_BUDGET';
      break;
    }
    const page = {
      page_index: result.pages.length, request_args: copyArgs(args),
      response_index: null, status: 'pending', row_count: null,
      response_chars: null, next_page_token: null, provider_end_observed: false,
    };
    // Retain the exact normalized native arguments before dispatch, then raw before inspection.
    result.pages.push(page);
    result.summary.calls += 1;
    result.summary.next_request_basis = 'unresolved_current_request';
    result.next_request = nextRequest(request, args);
    let raw;
    try {
      raw = await tools[BINDING](copyArgs(args));
    } catch (error) {
      page.status = 'exception';
      page.exception = {name: error && typeof error.name === 'string' ? error.name : null,
        message: error && typeof error.message === 'string' ? error.message : null, thrown_value: error};
      result.summary.stop_reason = 'THROWN_ERROR';
      break;
    }
    page.response_index = result.responses.length;
    result.responses.push(raw);
    result.summary.retained_responses += 1;
    if (nativeError(raw)) {
      page.status = 'native_error';
      page.error = errorMetadata(raw);
      result.summary.stop_reason = 'NATIVE_ERROR';
      break;
    }
    try {
      const serialized = JSON.stringify(raw);
      if (typeof serialized !== 'string') fail('UNSUPPORTED_PAYLOAD', 'Response is not serializable');
      page.response_chars = serialized.length;
      result.summary.response_chars += serialized.length;
      if (serialized.length > request.max_response_chars
          || result.summary.response_chars > request.max_total_response_chars) {
        page.status = 'response_limit';
        result.summary.stop_reason = 'RESPONSE_BUDGET';
        break;
      }
      const parsed = parsePage(raw, args.max_results);
      page.status = 'ok';
      page.row_count = parsed.emails.length;
      page.next_page_token = parsed.token;
      result.summary.successful_pages += 1;
      result.summary.rows_observed += parsed.emails.length;
      if (parsed.token === null) {
        page.provider_end_observed = true;
        result.summary.provider_end_observed = true;
        result.summary.stop_reason = 'PROVIDER_END';
        result.summary.next_request_basis = 'none_provider_end';
        result.next_request = null;
        break;
      }
      args = copyArgs(args);
      args.next_page_token = parsed.token;
      result.next_request = nextRequest(request, args);
      result.summary.next_request_basis = 'native_next_page_token';
      if (seenTokens.has(parsed.token)) {
        result.summary.stop_reason = 'TOKEN_CYCLE';
        result.summary.next_request_basis = 'repeated_native_token';
        break;
      }
      seenTokens.add(parsed.token);
    } catch (error) {
      page.status = 'payload_error';
      page.issue = {code: error.code || 'UNSUPPORTED_PAYLOAD'};
      result.summary.stop_reason = 'PAYLOAD_ERROR';
      break;
    }
  }
  if (result.summary.stop_reason === null) {
    result.summary.stop_reason = Date.now() - start >= request.timeout_ms ? 'TIME_BUDGET' : 'PAGE_BUDGET';
  }
  result.finished_at = new Date().toISOString();
  result.elapsed_ms = Date.now() - start;
  return result;
}

function clip(value, limit) {
  let end = Math.min(value.length, limit);
  if (end < value.length && end > 0 && /[\uD800-\uDBFF]/.test(value[end - 1])
      && /[\uDC00-\uDFFF]/.test(value[end])) end -= 1;
  return value.slice(0, end);
}
function projectGmailSearchHeaders(collection, options = {}) {
  if (!record(options)) fail('INVALID_INPUT', 'options must be an object');
  const allowed = new Set(['start_index', 'max_messages', 'max_field_chars', 'max_total_header_chars']);
  for (const key of Object.keys(options)) if (!allowed.has(key)) fail('INVALID_INPUT', 'Unknown projection option: ' + key);
  const limits = {
    start_index: integer(options.start_index, 0, 1000, 'start_index', 0),
    max_messages: integer(options.max_messages, 20, 1000, 'max_messages'),
    max_field_chars: integer(options.max_field_chars, 300, 4000, 'max_field_chars'),
    max_total_header_chars: integer(options.max_total_header_chars, 12000, 64000, 'max_total_header_chars'),
  };
  const result = {
    schema: 'commons.connected_gmail_search_headers/v1', status: 'REFUSED', limits,
    source: {scope: 'retained_successful_pages_only', query_application: 'not_verified',
      snapshot: false, account_identity: 'not_inferred'},
    messages: [], coverage: {}, issue: null,
  };
  try {
    if (!record(collection) || collection.schema !== SCHEMA || collection.operation !== 'search_emails'
        || collection.binding !== BINDING || !Array.isArray(collection.pages) || !Array.isArray(collection.responses)) {
      fail('UNSUPPORTED_COLLECTOR', 'Expected a Gmail search collector');
    }
    const request = normalizeRequest(collection.request);
    if (collection.pages.length > request.max_pages || collection.responses.length > collection.pages.length) {
      fail('UNSUPPORTED_COLLECTOR', 'Collector exceeds page limits');
    }
    const rows = [];
    let expectedArgs = copyArgs(request.args);
    let stopped = false;
    let countResponses = 0;
    let successfulPages = 0;
    const unresolvedPages = [];
    let providerEnd = false;
    for (let i = 0; i < collection.pages.length; i += 1) {
      const page = collection.pages[i];
      if (!record(page) || page.page_index !== i || !record(page.request_args)
          || JSON.stringify(page.request_args) !== JSON.stringify(expectedArgs) || stopped) {
        fail('COLLECTOR_BINDING_MISMATCH', 'Page arguments or ordering do not match the retained request');
      }
      if (page.response_index === null) {
        if (page.status !== 'exception' || i !== collection.pages.length - 1) fail('UNSUPPORTED_COLLECTOR', 'Unresolved page is not terminal');
        unresolvedPages.push({page_index: i, status: page.status});
        stopped = true;
        continue;
      }
      if (page.response_index !== countResponses || page.response_index >= collection.responses.length) {
        fail('COLLECTOR_BINDING_MISMATCH', 'Response mapping is invalid');
      }
      countResponses += 1;
      if (page.status !== 'ok') {
        if (!['native_error', 'response_limit', 'payload_error'].includes(page.status)
            || i !== collection.pages.length - 1) fail('UNSUPPORTED_COLLECTOR', 'Failed page is not terminal');
        unresolvedPages.push({page_index: i, status: page.status});
        stopped = true;
        continue;
      }
      const parsed = parsePage(collection.responses[page.response_index], request.args.max_results);
      if (page.row_count !== parsed.emails.length || page.next_page_token !== parsed.token
          || page.provider_end_observed !== (parsed.token === null)) {
        fail('COLLECTOR_BINDING_MISMATCH', 'Recorded pagination does not match the native page');
      }
      successfulPages += 1;
      for (let j = 0; j < parsed.emails.length; j += 1) {
        rows.push({page_index: i, row_index: j, response_index: page.response_index, value: parsed.emails[j]});
      }
      if (parsed.token === null) { stopped = true; providerEnd = true; }
      else expectedArgs = Object.assign(copyArgs(expectedArgs), {next_page_token: parsed.token});
    }
    if (countResponses !== collection.responses.length) fail('COLLECTOR_BINDING_MISMATCH', 'Unmapped responses');
    let remaining = limits.max_total_header_chars;
    let originalChars = 0;
    let returnedChars = 0;
    let fieldsWithLoss = 0;
    const selected = rows.slice(limits.start_index, limits.start_index + limits.max_messages);
    for (let i = 0; i < selected.length; i += 1) {
      const entry = selected[i];
      const path = 'responses[' + entry.response_index + '].structuredContent.emails[' + entry.row_index + ']';
      const row = {
        source_index: limits.start_index + i, source_page_index: entry.page_index,
        source_row_index: entry.row_index, source_path: path,
        body_withheld: true, fields: {},
      };
      for (const name of ['id', 'thread_id', 'from_', 'subject', 'email_ts', 'has_attachment']) {
        const detail = {source_path: path + '.' + name};
        row.fields[name] = detail;
        if (!own(entry.value, name)) { detail.status = 'missing'; continue; }
        const value = entry.value[name];
        if (name === 'has_attachment') {
          if (typeof value === 'boolean') { detail.status = 'included'; detail.value = value; }
          else detail.status = 'invalid_type';
          continue;
        }
        if (name === 'email_ts' && Number.isFinite(value)) {
          detail.status = 'included'; detail.value = value; continue;
        }
        if (typeof value !== 'string') { detail.status = 'invalid_type'; continue; }
        originalChars += value.length;
        detail.original_chars = value.length;
        const budget = Math.min(limits.max_field_chars, remaining);
        // Identity and timestamp fields are never returned as misleading prefixes.
        if (['id', 'thread_id', 'email_ts'].includes(name) && value.length > budget) {
          detail.status = 'limit_exceeded'; detail.returned_chars = 0;
          detail.omitted_chars = value.length; fieldsWithLoss += 1; continue;
        }
        const text = clip(value, budget);
        detail.value = text;
        detail.returned_chars = text.length;
        detail.omitted_chars = value.length - text.length;
        detail.truncated = text.length !== value.length;
        detail.status = detail.truncated ? 'truncated' : 'included';
        remaining -= text.length;
        returnedChars += text.length;
        if (detail.truncated) fieldsWithLoss += 1;
      }
      result.messages.push(row);
    }
    result.status = unresolvedPages.length ? (rows.length ? 'PARTIAL' : 'UNAVAILABLE')
      : successfulPages ? (rows.length ? 'PROJECTED' : 'EMPTY_PAGE') : 'NO_SUCCESSFUL_PAGES';
    result.source.provider_end_observed = providerEnd;
    result.source.unresolved_pages = unresolvedPages;
    result.source.collector_stop_reason = collection.summary && collection.summary.stop_reason;
    result.source.collector_state_basis = 'reported_by_supplied_collector';
    result.coverage = {
      successful_pages: successfulPages, successful_rows: rows.length, start_index: limits.start_index, returned_messages: selected.length,
      omitted_before: Math.min(limits.start_index, rows.length),
      omitted_after: Math.max(0, rows.length - limits.start_index - selected.length),
      next_index: limits.start_index + selected.length < rows.length ? limits.start_index + selected.length : null,
      selected_header_chars: originalChars, returned_header_chars: returnedChars,
      omitted_header_chars: originalChars - returnedChars, fields_with_text_loss: fieldsWithLoss,
      all_successful_rows_included: limits.start_index === 0 && selected.length === rows.length,
      snippets_bodies_and_attachment_details: 'not_selected',
      full_mail_content_included: false,
    };
    return result;
  } catch (error) {
    result.messages = [];
    result.issue = {code: error.code || 'UNSUPPORTED_COLLECTOR', detail: error.message};
    return result;
  }
}


function inspectGmailSearchEmailTimestamps(response, options = {}) {
  if (!record(options)) fail('INVALID_INPUT', 'options must be an object');
  const allowed = new Set(['after', 'before', 'max_records']);
  for (const key of Object.keys(options)) {
    if (!allowed.has(key)) fail('INVALID_INPUT', 'Unknown timestamp option: ' + key);
  }
  const maxRecords = integer(options.max_records, 20, 100, 'max_records', 0);
  if (!own(options, 'after') && !own(options, 'before')) {
    fail('INVALID_INPUT', 'At least one explicit timestamp bound is required');
  }

  // Deliberately narrower than all ISO 8601 forms. No unit or local-zone inference.
  function parseInstant(value) {
    if (value === null) return {reason: 'null'};
    if (typeof value === 'number') {
      return {reason: Number.isFinite(value) ? 'numeric_unit_unspecified' : 'non_finite_number'};
    }
    if (typeof value !== 'string') return {reason: 'unsupported_type'};
    if (value.length > 64) return {reason: 'timestamp_text_limit'};
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
    if (!match) return {reason: 'unsupported_format'};
    const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
    const hour = Number(match[4]), minute = Number(match[5]), second = Number(match[6]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1] ||
        hour > 23 || minute > 59 || second > 59) {
      return {reason: 'invalid_calendar_or_clock'};
    }
    if (match[8] !== 'Z') {
      if (Number(match[10]) > 23 || Number(match[11]) > 59) {
        return {reason: 'invalid_utc_offset'};
      }
      // The unknown-offset spelling does not establish an instant for this reader.
      if (match[8] === '-00:00') return {reason: 'unknown_utc_offset'};
    }
    // Calendar fields were checked above; avoid Date.UTC's special years 00..99.
    const milliseconds = Date.parse(value);
    if (!Number.isFinite(milliseconds)) return {reason: 'unsupported_instant'};
    return {milliseconds};
  }

  const bounds = {basis: 'caller_declared', operators: 'exclusive'};
  const instants = {};
  for (const name of ['after', 'before']) {
    if (!own(options, name)) continue;
    const parsed = parseInstant(options[name]);
    if (parsed.reason) fail('INVALID_INPUT', name + ' must be a supported explicit-offset timestamp');
    bounds[name] = options[name];
    instants[name] = parsed.milliseconds;
  }
  if (own(instants, 'after') && own(instants, 'before') && instants.after >= instants.before) {
    fail('INVALID_INPUT', 'after must precede before');
  }

  const result = {
    schema: 'commons.connected_gmail_reported_timestamp_observation/v1',
    status: 'REFUSED',
    source: {
      scope: 'supplied_native_page_only',
      field: 'structuredContent.emails[i].email_ts',
      time_basis: 'reported_email_ts',
      provider_search_date_semantics: 'not_established',
      query_application: 'not_verified',
      query_syntax_parsed: false,
      authentication: 'not_performed',
      snapshot: false,
      account_identity: 'not_inferred',
      row_values_returned: false,
    },
    bounds,
    limits: {max_input_rows: 100, max_timestamp_chars: 64, max_records: maxRecords},
    stats: null, records: [], all_rows_inspected: false,
    all_supplied_timestamps_assessed: false, issue: null,
  };
  try {
    const parsed = parsePage(response, result.limits.max_input_rows);
    const stats = {
      supplied_rows: parsed.emails.length, inspected_rows: 0, assessed_rows: 0,
      inside_rows: 0, outside_rows: 0,
      on_or_before_after_rows: 0, on_or_after_before_rows: 0,
      unassessed_rows: 0, unassessed_by_reason: {},
      diagnostic_rows: 0, returned_records: 0, omitted_records: 0,
    };
    result.stats = stats;
    const diagnostic = (index, state, detail) => {
      stats.diagnostic_rows += 1;
      if (result.records.length < maxRecords) {
        result.records.push({
          source_index: index,
          source_path: 'structuredContent.emails[' + index + '].email_ts',
          state, ...detail,
        });
      }
    };
    for (let i = 0; i < parsed.emails.length; i += 1) {
      stats.inspected_rows += 1;
      const row = parsed.emails[i];
      const instant = own(row, 'email_ts') ? parseInstant(row.email_ts) : {reason: 'missing'};
      if (instant.reason) {
        stats.unassessed_rows += 1;
        stats.unassessed_by_reason[instant.reason] = (stats.unassessed_by_reason[instant.reason] || 0) + 1;
        diagnostic(i, 'unassessed', {reason: instant.reason});
        continue;
      }
      stats.assessed_rows += 1;
      if (own(instants, 'after') && instant.milliseconds <= instants.after) {
        stats.outside_rows += 1;
        stats.on_or_before_after_rows += 1;
        diagnostic(i, 'outside_window', {relation: 'on_or_before_after'});
      } else if (own(instants, 'before') && instant.milliseconds >= instants.before) {
        stats.outside_rows += 1;
        stats.on_or_after_before_rows += 1;
        diagnostic(i, 'outside_window', {relation: 'on_or_after_before'});
      } else {
        stats.inside_rows += 1;
      }
    }
    stats.returned_records = result.records.length;
    stats.omitted_records = stats.diagnostic_rows - stats.returned_records;
    result.all_rows_inspected = stats.inspected_rows === stats.supplied_rows;
    result.all_supplied_timestamps_assessed = stats.assessed_rows === stats.supplied_rows;
    result.status = stats.supplied_rows === 0 ? 'EMPTY_PAGE'
      : stats.outside_rows > 0 ? 'OUTSIDE_REPORTED_TIMESTAMP_OBSERVED'
      : stats.unassessed_rows > 0 ? 'INCOMPLETE_TIMESTAMP_ASSESSMENT'
      : 'NO_OUTSIDE_REPORTED_TIMESTAMP_OBSERVED';
    return result;
  } catch (error) {
    result.stats = null;
    result.records = [];
    result.issue = {code: error.code || 'UNSUPPORTED_PAYLOAD', detail: error.message};
    return result;
  }
}

module.exports = { collectGmailSearchPages, projectGmailSearchHeaders, inspectGmailSearchEmailTimestamps };
