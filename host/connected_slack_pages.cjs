'use strict';

// Native reads only. Responses remain private caller-owned data.
const OPERATIONS = {
  read_channel: {
    binding: 'mcp__codex_apps__slack_slack_read_channel',
    fields: ['channel_id', 'cursor', 'latest', 'limit', 'oldest', 'response_format'],
    maximumLimit: 100,
  },
  read_thread: {
    binding: 'mcp__codex_apps__slack_slack_read_thread',
    fields: ['channel_id', 'cursor', 'latest', 'limit', 'message_ts', 'oldest', 'response_format'],
    maximumLimit: 1000,
  },
  search_public: {
    binding: 'mcp__codex_apps__slack_slack_search_public',
    fields: ['after', 'before', 'content_types', 'context_channel_id', 'cursor',
      'filters', 'include_bots', 'include_context', 'keywords', 'limit',
      'max_context_length', 'natural_language_query', 'only_my_channels', 'query',
      'response_format', 'sort', 'sort_dir'],
    maximumLimit: 20,
  },
  search: {
    binding: 'mcp__codex_apps__slack_slack_search_public_and_private',
    fields: ['after', 'before', 'channel_types', 'content_types', 'context_channel_id',
      'cursor', 'filters', 'include_bots', 'include_context', 'keywords', 'limit',
      'max_context_length', 'natural_language_query', 'only_my_channels', 'query',
      'response_format', 'sort', 'sort_dir'],
    maximumLimit: 20,
  },
};

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}

function positive(value, label, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < 1 || value > maximum) {
    throw new TypeError(label + ' must be a positive integer no greater than ' + maximum);
  }
  return value;
}

function nonempty(value, label) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new TypeError(label + ' must be a nonempty string');
  }
  return value;
}

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

function diagnostic(error) {
  return {name: String(error?.name ?? 'Error'),
    message: String(error?.message ?? error).slice(0, 1200)};
}

/** Describe explicit native search date operators without changing the request. */
function searchDateFilters(args) {
  if (!args || typeof args.filters !== 'string') return [];
  const found = [];
  for (const match of args.filters.matchAll(/(?:^|\s)(after|on):(\d{4}-\d{2}-\d{2})(?=\s|$)/g)) {
    found.push({
      operator: match[1],
      date: match[2],
      semantics: match[1] === 'after'
        ? 'excludes_named_calendar_date_observed'
        : 'exact_named_calendar_date',
    });
  }
  return found;
}

/** Project only the native failure envelope, never nested application payloads. */
function projectSlackReadFailure(response) {
  const record = value => value && typeof value === 'object' && !Array.isArray(value);
  if (!record(response)) return null;
  const value = record(response.structuredContent) ? response.structuredContent : response;
  const data = record(value.error_data) ? value.error_data : {};
  if (response.isError !== true && value.isError !== true && value.ok !== false
      && !(response instanceof Error)
      && !(typeof value.error_code === 'string' && typeof value.error === 'string')) return null;

  const rawRetry = Object.prototype.hasOwnProperty.call(value, 'retry_after')
    ? value.retry_after : data.retry_after;
  const seconds = Object.prototype.hasOwnProperty.call(value, 'retry_after_seconds')
    ? value.retry_after_seconds : rawRetry;
  // HTTP-date values remain literal; no clock, reset time or quota is inferred.
  const parsedSeconds = typeof seconds === 'number' ? seconds
    : typeof seconds === 'string' && /^[0-9]+$/.test(seconds) ? Number(seconds) : null;
  const retrySeconds = Number.isSafeInteger(parsedSeconds) && parsedSeconds >= 0
    ? parsedSeconds : null;
  const nativeMessage = typeof value.error === 'string' ? value.error
    : typeof data.message === 'string' ? data.message
    : typeof value.message === 'string' ? value.message
    : Array.isArray(response.content)
      ? response.content.find(block => block?.type === 'text' && typeof block.text === 'string')?.text
      : null;
  const code = typeof data.code === 'string' || typeof data.code === 'number' ? data.code : null;
  return {
    error_code: typeof value.error_code === 'string' ? value.error_code : null,
    error_type: typeof data.type === 'string' ? data.type : null,
    code,
    http_status: data.type === 'http_error' && Number.isInteger(code) && code >= 100 && code <= 599
      ? code : null,
    message: String(nativeMessage ?? 'Native read failed').slice(0, 1200),
    retry_after: ['string', 'number', 'boolean'].includes(typeof rawRetry) ? rawRetry : null,
    retry_after_seconds: retrySeconds,
  };
}

function payload(response) {
  if (response.structuredContent && typeof response.structuredContent === 'object'
      && !Array.isArray(response.structuredContent)
      && 'pagination_info' in response.structuredContent) return response.structuredContent;
  for (const block of response.content ?? []) {
    if (block?.type !== 'text' || typeof block.text !== 'string') continue;
    try {
      const value = JSON.parse(block.text);
      if (value && typeof value === 'object' && !Array.isArray(value)) return value;
    } catch (_) { /* Keep the original response; try another native text block. */ }
  }
  if (response.structuredContent && typeof response.structuredContent === 'object'
      && !Array.isArray(response.structuredContent)) return response.structuredContent;
  throw new Error('Native response has no readable JSON payload');
}

function pagination(value) {
  const info = value.pagination_info;
  if (typeof info !== 'string') return {known: false, info: null, next_cursor: null, end: false};
  const normalized = info.trim().replace(/\\n/g, '').trim();
  const cursors = new Set(Array.from(info.matchAll(/\bcursor\s*:?\s*\x60([^\x60]+)\x60/gi),
    match => match[1]));
  // Exact observed provider endings; message text is never inspected for cursors.
  const end = /^(?:There are no more messages (?:in this thread|available)\.?|End of results - No more pages available\.?)$/i.test(normalized);
  if (cursors.size === 1 && !end) {
    return {known: true, info, next_cursor: Array.from(cursors)[0], end: false};
  }
  if (cursors.size === 0 && end) return {known: true, info, next_cursor: null, end: true};
  return {known: false, info, next_cursor: null, end: false};
}

function argumentsAt(base, cursor) {
  const args = {...base};
  if (cursor !== null) args.cursor = cursor;
  return args;
}

/**
 * Collect one bounded native cursor chain. This does not interpret messages,
 * prove source completeness, open thread replies from a channel, or decide ownership.
 */
async function collectSlackPages(tools, request, options = {}) {
  object(request, 'request');
  for (const key of Object.keys(request)) {
    if (!['operation', 'args', 'max_pages', 'timeout_ms'].includes(key)) {
      throw new TypeError('Unsupported request field: ' + key);
    }
  }
  const operation = request.operation;
  if (!Object.prototype.hasOwnProperty.call(OPERATIONS, operation)) {
    throw new TypeError('operation must be read_channel, read_thread, search or search_public');
  }
  const spec = OPERATIONS[operation];
  const suppliedArgs = object(request.args, 'args');
  for (const key of Object.keys(suppliedArgs)) {
    if (!spec.fields.includes(key)) throw new TypeError('Unsupported native argument: ' + key);
  }
  const args = copy(suppliedArgs);
  if (!['search', 'search_public'].includes(operation)) {
    nonempty(args.channel_id, 'channel_id');
    for (const field of ['oldest', 'latest']) {
      if (args[field] !== undefined &&
          (typeof args[field] !== 'string' || !/^[0-9]+\.[0-9]+$/.test(args[field]))) {
        throw new TypeError(field + ' must be a decimal Slack timestamp string');
      }
    }
  }
  if (operation === 'read_thread') {
    nonempty(args.message_ts, 'message_ts');
    if (!/^[0-9]+\.[0-9]+$/.test(args.message_ts)) {
      throw new TypeError('message_ts must retain the observed decimal Slack string');
    }
  }
  if (args.cursor === '') delete args.cursor;
  if (args.cursor !== undefined) nonempty(args.cursor, 'cursor');
  // New search chains need matched messages by default. Preserve explicit
  // context options and the original semantics of a resumed native cursor.
  if (['search', 'search_public'].includes(operation) && args.cursor === undefined
      && args.include_context === undefined && args.max_context_length === undefined) {
    args.include_context = false;
  }
  // The observed native binding also needs its explicit query field. Build it
  // only for a fresh search from already supplied lexical tokens and filters;
  // an existing cursor must retain the exact query that produced it.
  if (['search', 'search_public'].includes(operation) && args.cursor === undefined
      && args.query === undefined
      && (args.keywords === undefined || (Array.isArray(args.keywords)
        && args.keywords.every(term => typeof term === 'string')))
      && (args.filters === undefined || typeof args.filters === 'string')) {
    const query = [...(args.keywords ?? []), args.filters ?? '']
      .filter(part => part.trim()).join(' ');
    if (query) args.query = query;
  }
  args.limit = positive(args.limit ?? 20, 'limit', spec.maximumLimit);
  if (args.response_format !== undefined && args.response_format !== 'detailed') {
    throw new TypeError('This collector retains detailed native responses');
  }
  args.response_format = 'detailed';
  const maxPages = positive(request.max_pages ?? 4, 'max_pages');
  const timeout = positive(request.timeout_ms ?? 30000, 'timeout_ms');
  if (typeof tools?.[spec.binding] !== 'function') {
    throw new Error('Binding not present: ' + spec.binding
      + '. Repeat discovery alongside useful work.');
  }
  if (options.onResponse !== undefined && typeof options.onResponse !== 'function') {
    throw new TypeError('onResponse must be a function');
  }
  const initialCursor = args.cursor ?? null;
  delete args.cursor;
  const start = Date.now();
  const result = {
    schema: 'commons.connected_slack_pages/v1',
    operation, binding: spec.binding,
    request: {operation, args: argumentsAt(args, initialCursor),
      max_pages: maxPages, timeout_ms: timeout},
    started_at: new Date(start).toISOString(),
    pages: [], responses: [], next_request: null,
    summary: {calls: 0, successful_pages: 0, retained_responses: 0,
      started_with_cursor: initialCursor !== null, provider_end_observed: false,
      next_cursor: initialCursor, stop_reason: null, snapshot: false,
      coverage: 'native_pagination_only'},
  };
  if (['search', 'search_public'].includes(operation)) {
    result.search_date_filters = searchDateFilters(args);
  }
  const seen = new Set();
  let cursor = initialCursor;
  let mayContinue = true;
  while (result.summary.calls < maxPages) {
    if (Date.now() - start >= timeout) {
      result.summary.stop_reason = 'TIME_BUDGET';
      break;
    }
    const requested = argumentsAt(args, cursor);
    const page = {call: result.summary.calls + 1, request_args: copy(requested),
      response_index: null, pagination_info: null, next_cursor: null,
      provider_end_observed: false};
    result.pages.push(page);
    result.summary.calls += 1;
    seen.add(cursor);
    let response;
    try {
      response = await tools[spec.binding](requested);
    } catch (error) {
      page.error = {...diagnostic(error), ...projectSlackReadFailure(error)};
      result.summary.native_error = copy(page.error);
      result.summary.stop_reason = 'NATIVE_EXCEPTION';
      break;
    }
    page.response_index = result.responses.length;
    result.responses.push(response);
    result.summary.retained_responses = result.responses.length;
    if (!response || typeof response !== 'object' || response.isError === true) {
      page.error = {name: 'NativeToolError', message: 'Native tool returned an error or non-object response',
        ...projectSlackReadFailure(response)};
      result.summary.native_error = copy(page.error);
      result.summary.stop_reason = 'NATIVE_ERROR';
    } else {
      try {
        const decoded = payload(response);
        if (decoded.isError === true || decoded.ok === false) {
          const error = new Error('Native payload reports a failed read');
          error.name = 'NativeReadError';
          error.native_failure = projectSlackReadFailure(decoded);
          throw error;
        }
        const state = pagination(decoded);
        page.pagination_info = state.info;
        page.next_cursor = state.next_cursor;
        page.provider_end_observed = state.end;
        result.summary.successful_pages += 1;
        if (!state.known) {
          mayContinue = false;
          result.summary.next_cursor = null;
          result.summary.stop_reason = 'UNKNOWN_PAGINATION';
        } else if (state.end) {
          mayContinue = false;
          result.summary.provider_end_observed = true;
          result.summary.next_cursor = null;
          result.summary.stop_reason = 'PROVIDER_END';
        } else if (seen.has(state.next_cursor)) {
          mayContinue = false;
          result.summary.next_cursor = state.next_cursor;
          result.summary.stop_reason = 'CURSOR_REPEAT';
        } else {
          cursor = state.next_cursor;
          result.summary.next_cursor = cursor;
        }
      } catch (error) {
        page.error = diagnostic(error);
        if (error?.name === 'NativeReadError') {
          Object.assign(page.error, error.native_failure);
          result.summary.native_error = copy(page.error);
          result.summary.stop_reason = 'NATIVE_ERROR';
        } else {
          mayContinue = false;
          result.summary.next_cursor = null;
          result.summary.stop_reason = 'UNREADABLE_RESPONSE';
        }
      }
    }
    if (options.onResponse) {
      try { await options.onResponse({page: copy(page), response: copy(response)}); }
      catch (error) {
        page.callback_error = diagnostic(error);
        result.summary.stop_reason = 'CALLBACK_ERROR';
      }
    }
    if (result.summary.stop_reason) break;
  }
  if (!result.summary.stop_reason) result.summary.stop_reason = 'PAGE_BUDGET';
  if (mayContinue) {
    result.next_request = {operation, args: argumentsAt(args, cursor),
      max_pages: maxPages, timeout_ms: timeout};
  }
  result.finished_at = new Date().toISOString();
  result.elapsed_ms = Date.now() - start;
  return result;
}

/**
 * Project a detailed read_channel/read_thread envelope without changing it.
 * Content and ranges refer to the connector rendering, not Slack stored text.
 */
function projectSlackMessages(response, request, options = {}) {
  object(request, 'projection request');
  object(options, 'projection options');
  const operation = request.operation;
  if (!['read_channel', 'read_thread'].includes(operation)) {
    throw new TypeError('projection operation must be read_channel or read_thread');
  }
  const args = object(request.args, 'projection request.args');
  const channel = nonempty(args.channel_id, 'projection channel_id');
  const stamp = /^[0-9]{1,16}\.[0-9]{1,16}$/;
  if (!/^[CGD][A-Z0-9]{1,127}$/.test(channel)) throw new TypeError('invalid projection channel_id');
  if (args.response_format !== undefined && args.response_format !== 'detailed') {
    throw new TypeError('projection does not accept a concise request');
  }
  if (operation === 'read_thread' && (typeof args.message_ts !== 'string' || !stamp.test(args.message_ts))) {
    throw new TypeError('projection requires an exact decimal-string parent message_ts');
  }
  const requestWindow = {};
  const windowBounds = {};
  const invalidBounds = [];
  const stampValue = value => {
    const [seconds, fraction] = value.split('.');
    return BigInt(seconds) * 10000000000000000n + BigInt(fraction.padEnd(16, '0'));
  };
  if (operation === 'read_thread') requestWindow.message_ts = args.message_ts;
  for (const field of ['oldest', 'latest']) {
    if (!Object.prototype.hasOwnProperty.call(args, field)) continue;
    requestWindow[field] = args[field];
    if (typeof args[field] === 'string' && stamp.test(args[field])) {
      windowBounds[field] = stampValue(args[field]);
    } else {
      invalidBounds.push(field);
    }
  }
  const headerOnly = Object.prototype.hasOwnProperty.call(options, 'header_only')
    ? options.header_only : false;
  if (typeof headerOnly !== 'boolean') throw new TypeError('header_only must be boolean');
  const observeApplicationSuppression = Object.prototype.hasOwnProperty.call(options, 'observe_application_suppression')
    ? options.observe_application_suppression : false;
  if (typeof observeApplicationSuppression !== 'boolean') {
    throw new TypeError('observe_application_suppression must be boolean');
  }
  const observeThreadSummaries = Object.prototype.hasOwnProperty.call(options, 'observe_thread_summaries')
    ? options.observe_thread_summaries : false;
  if (typeof observeThreadSummaries !== 'boolean') {
    throw new TypeError('observe_thread_summaries must be boolean');
  }
  if (observeThreadSummaries && operation !== 'read_channel') {
    throw new TypeError('observe_thread_summaries requires read_channel');
  }
  const defaults = {start_index: 0, max_messages: 8, max_body_chars: 800,
    max_total_body_chars: 6400, max_input_chars: 1048576,
    ...(headerOnly ? {max_header_chars: 800, max_total_header_chars: 6400} : {})};
  const ceilings = {start_index: Number.MAX_SAFE_INTEGER, max_messages: 1000,
    max_body_chars: 65536, max_total_body_chars: 262144, max_input_chars: 8388608,
    max_header_chars: 65536, max_total_header_chars: 262144};
  for (const key of Object.keys(options)) {
    if (key !== 'source_indices' && key !== 'header_only' && key !== 'observe_application_suppression' &&
        key !== 'observe_thread_summaries' &&
        !Object.prototype.hasOwnProperty.call(defaults, key)) {
      const modeHint = !headerOnly && (key === 'max_header_chars' || key === 'max_total_header_chars')
        ? '; header budgets require header_only: true; omit both header-budget options for body projection'
        : '';
      throw new TypeError('unknown projection option: ' + key + modeHint);
    }
  }
  const limits = {...defaults, ...options};
  delete limits.header_only;
  delete limits.observe_application_suppression;
  delete limits.observe_thread_summaries;
  for (const [key, value] of Object.entries(limits)) {
    if (key === 'source_indices') continue;
    if (!Number.isSafeInteger(value) || value < (['max_messages', 'max_input_chars'].includes(key) ? 1 : 0) ||
        value > ceilings[key]) throw new TypeError('invalid projection option: ' + key);
  }
  let sourceIndices = null;
  if (Object.prototype.hasOwnProperty.call(options, 'source_indices')) {
    if (Object.prototype.hasOwnProperty.call(options, 'start_index')) {
      throw new TypeError('source_indices and start_index are mutually exclusive');
    }
    if (!Array.isArray(options.source_indices) || options.source_indices.length > limits.max_messages) {
      throw new TypeError('source_indices must be an array with at most max_messages entries');
    }
    sourceIndices = options.source_indices.slice();
    for (let i = 0; i < sourceIndices.length; i++) {
      if (!Number.isSafeInteger(sourceIndices[i]) || sourceIndices[i] < 0 ||
          (i > 0 && sourceIndices[i] <= sourceIndices[i - 1])) {
        throw new TypeError('source_indices must contain distinct increasing nonnegative safe integers');
      }
    }
    limits.source_indices = sourceIndices;
  }
  const result = {schema: 'commons.connected_slack_message_projection/v1', status: 'REFUSED',
    source: {operation, channel_id: channel,
      parent_message_ts: operation === 'read_thread' ? args.message_ts : null,
      request_window: requestWindow, window_application: 'not_verified',
      content_basis: 'connector_rendered_content', message_identity: 'rendered_header',
      channel_binding: 'retained_request', representations: 0, input_chars: 0,
      ...(observeThreadSummaries ? {thread_summary_observation: 'selected_channel_suffix_only'} : {})},
    limits, coverage: {scope: 'retained_response_only', snapshot: false}, messages: [], issue: null};
  const refuse = (code, detail) => {
    result.issue = {code, detail}; return result;
  };
  const bad = (code, detail) => { throw {projection: true, code, detail}; };
  let charged = 0;
  const charge = value => {
    charged += value.length;
    result.source.input_chars = charged;
    if (charged > limits.max_input_chars) bad('INPUT_LIMIT', 'Native payload text exceeds max_input_chars.');
  };
  try {
    if (!response || typeof response !== 'object' || Array.isArray(response) || response.isError === true) {
      bad('NATIVE_ERROR', 'Expected a successful retained native response.');
    }
    const representations = [];
    const accept = value => {
      if (!value || typeof value !== 'object' || Array.isArray(value) ||
          Object.keys(value).length !== 2 || typeof value.messages !== 'string' ||
          typeof value.pagination_info !== 'string') {
        bad('UNSUPPORTED_PAYLOAD', 'Expected only string messages and pagination_info fields.');
      }
      representations.push(value);
    };
    if (Object.prototype.hasOwnProperty.call(response, 'messages')) {
      if (typeof response.messages === 'string') charge(response.messages);
      if (typeof response.pagination_info === 'string') charge(response.pagination_info);
      accept(response);
    } else {
      if (Object.prototype.hasOwnProperty.call(response, 'structuredContent')) {
        const value = response.structuredContent;
        if (typeof value?.messages === 'string') charge(value.messages);
        if (typeof value?.pagination_info === 'string') charge(value.pagination_info);
        accept(value);
      }
      if (Object.prototype.hasOwnProperty.call(response, 'content')) {
        if (!Array.isArray(response.content) || response.content.length === 0) {
          bad('UNSUPPORTED_PAYLOAD', 'Native content must contain JSON text blocks.');
        }
        for (const block of response.content) {
          if (!block || block.type !== 'text' || typeof block.text !== 'string') {
            bad('UNSUPPORTED_PAYLOAD', 'Non-text native content is outside this projection format.');
          }
          charge(block.text);
          let value;
          try { value = JSON.parse(block.text); } catch (_) {
            bad('UNREADABLE_PAYLOAD', 'Native text is not a JSON envelope.');
          }
          accept(value);
        }
      }
    }
    if (!representations.length) bad('UNSUPPORTED_PAYLOAD', 'No rendered messages envelope was retained.');
    result.source.representations = representations.length;
    const page = representations[0];
    if (representations.some(value => value.messages !== page.messages || value.pagination_info !== page.pagination_info)) {
      bad('CONFLICTING_REPRESENTATIONS', 'Retained native representations disagree.');
    }
    const rendered = page.messages;
    result.source.rendered_chars = rendered.length;
    const nativePage = pagination(page);
    result.coverage.native_pagination_recognized = nativePage.known;
    result.coverage.provider_end_observed = nativePage.end;
    result.coverage.next_cursor_available = Boolean(nativePage.next_cursor);
    const rows = [];
    const ids = new Set();
    const add = (header, bodyStart, bodyEnd, id, kind) => {
      if (!stamp.test(id)) bad('UNSUPPORTED_LAYOUT', 'A message timestamp is outside the exact decimal format.');
      if (ids.has(id)) bad('DUPLICATE_IDENTITY', 'The rendered page repeats a message timestamp.');
      if (bodyEnd < bodyStart) bad('UNSUPPORTED_LAYOUT', 'Message framing overlaps.');
      ids.add(id);
      rows.push({source_index: rows.length, channel_id: channel, message_ts: id, kind,
        parent_message_ts: operation === 'read_thread' ? args.message_ts : null,
        header_range: [header.index, bodyStart], rendered_content_range: [bodyStart, bodyEnd]});
    };
    const boundary = (end, suffix) => {
      if (rendered.slice(end - suffix.length, end) !== suffix) {
        bad('UNSUPPORTED_LAYOUT', 'Expected a detailed-message separator.');
      }
      return end - suffix.length;
    };
    if (rendered === '') {
      result.coverage.declared_replies = null;
    } else if (operation === 'read_channel') {
      const prefix = /^Channel: [^\n]+ \(([CGD][A-Z0-9]+)\)\n\n/.exec(rendered);
      if (!prefix || prefix[1] !== channel) bad('CHANNEL_MISMATCH', 'Rendered channel header does not match the retained request.');
      result.source.channel_binding = 'retained_request_and_rendered_header';
      const pattern = /^=== Message (?:from [^\n]+ )?at [^\n]+ ===[ \t]*\nMessage TS: ([0-9]+\.[0-9]+)\n/gm;
      const headers = Array.from(rendered.matchAll(pattern));
      const markerCount = (rendered.match(/^=== Message (?:from |at )/gm) || []).length;
      if ((headers.length === 0 && rendered !== prefix[0]) ||
          (headers.length > 0 && headers[0].index !== prefix[0].length) ||
          markerCount !== headers.length) {
        bad('UNSUPPORTED_LAYOUT', 'Channel message headers are incomplete or ambiguous.');
      }
      for (let i = 0; i < headers.length; i++) {
        const header = headers[i];
        const end = i + 1 < headers.length ? boundary(headers[i + 1].index, '\n\n') : rendered.length;
        add(header, header.index + header[0].length, end, header[1], 'channel_message');
      }
      result.coverage.declared_replies = null;
    } else {
      const parent = /^=== THREAD PARENT MESSAGE ===\nFrom: [^\n]+\nTime: [^\n]+\nMessage TS: ([0-9]+\.[0-9]+)\n/.exec(rendered);
      if (!parent || parent[1] !== args.message_ts) {
        bad('PARENT_MISMATCH', 'Detailed thread parent does not match the retained request.');
      }
      const separators = Array.from(rendered.matchAll(/\n\n=== THREAD REPLIES \(([0-9]+) total\) ===\n\n/g));
      if (separators.length > 1) bad('AMBIGUOUS_LAYOUT', 'The rendering repeats the thread-replies separator.');
      if (!separators.length) {
        const end = boundary(rendered.length, '\n\nNo thread messsages\n');
        add(parent, parent[0].length, end, parent[1], 'thread_parent');
        result.coverage.declared_replies = 0;
      } else {
        const separator = separators[0];
        const count = Number(separator[1]);
        if (!Number.isSafeInteger(count) || count < 1) bad('UNSUPPORTED_LAYOUT', 'Invalid declared reply count.');
        const pattern = /^--- Reply ([1-9][0-9]*) of ([1-9][0-9]*) ---\nFrom: [^\n]+\nTime: [^\n]+\nMessage TS: ([0-9]+\.[0-9]+)\n/gm;
        const headers = Array.from(rendered.matchAll(pattern));
        const markers = (rendered.match(/^--- Reply /gm) || []).length;
        result.coverage.declared_replies = count;
        result.coverage.observed_reply_headers = headers.length;
        if (headers.length !== count || markers !== count ||
            headers[0]?.index !== separator.index + separator[0].length) {
          bad('REPLY_COUNT_MISMATCH', 'Declared replies and complete rendered reply headers differ.');
        }
        add(parent, parent[0].length, separator.index, parent[1], 'thread_parent');
        for (let i = 0; i < headers.length; i++) {
          const header = headers[i];
          if (Number(header[1]) !== i + 1 || Number(header[2]) !== count) {
            bad('REPLY_SEQUENCE_MISMATCH', 'Rendered reply numbering is inconsistent.');
          }
          const end = i + 1 < headers.length ? boundary(headers[i + 1].index, '\n\n') : boundary(rendered.length, '\n');
          add(header, header.index + header[0].length, end, header[3], 'thread_reply');
        }
      }
    }
    // Marker-like body lines cannot be distinguished from connector framing.
    for (const row of rows) {
      const body = rendered.slice(...row.rendered_content_range);
      if (/^(?:=== THREAD (?:PARENT MESSAGE|REPLIES)|--- Reply |=== Message from |Message TS:)/m.test(body)) {
        bad('AMBIGUOUS_LAYOUT', 'Rendered content contains reserved message-framing lines.');
      }
    }
    const comparedBounds = Object.keys(windowBounds);
    const windowCoverage = {
      scope: operation === 'read_thread' ? 'rendered_replies_only' : 'rendered_channel_messages',
      compared_bounds: comparedBounds, invalid_bounds: invalidBounds,
      bounds_order: comparedBounds.length === 2
        ? (windowBounds.oldest <= windowBounds.latest ? 'ordered' : 'inverted') : null,
      compared_messages: 0, excluded_thread_parents: 0,
      before_oldest: 'oldest' in windowBounds ? 0 : null,
      after_latest: 'latest' in windowBounds ? 0 : null,
      outside_compared_bounds: comparedBounds.length ? 0 : null,
      outside_source_indices: [],
    };
    for (const row of rows) {
      if (row.kind === 'thread_parent') { windowCoverage.excluded_thread_parents++; continue; }
      if (!comparedBounds.length) continue;
      windowCoverage.compared_messages++;
      const value = stampValue(row.message_ts);
      const before = 'oldest' in windowBounds && value < windowBounds.oldest;
      const after = 'latest' in windowBounds && value > windowBounds.latest;
      if (before) windowCoverage.before_oldest++;
      if (after) windowCoverage.after_latest++;
      if (before || after) {
        windowCoverage.outside_compared_bounds++;
        windowCoverage.outside_source_indices.push(row.source_index);
      }
    }
    result.coverage.request_window = windowCoverage;
    const from = Math.min(limits.start_index, rows.length);
    const until = Math.min(rows.length, from + limits.max_messages);
    if (sourceIndices !== null) {
      result.coverage.parsed_messages = rows.length;
      if (sourceIndices.some(index => index >= rows.length)) {
        bad('SOURCE_INDEX_OUT_OF_RANGE', 'A requested source index is outside the parsed retained page.');
      }
    }
    const selected = sourceIndices === null ? rows.slice(from, until) : sourceIndices.map(index => rows[index]);
    if (observeApplicationSuppression) {
      // Exact retained rendering only: this is not authenticated application state.
      const notice = '_Due to a high volume of activity, we are not displaying some messages sent by this application. • <https://api.slack.com/docs/rate-limits|Details>_';
      const observation = {
        scope: 'all_parsed_rendered_message_content_ranges',
        format: 'slack_application_high_volume_v1',
        authentication: 'not_performed', interpretation: 'literal_notice_only',
        suppressed_messages_count: null, complete_message_coverage: 'not_established',
        observed_literal_count: 0, record_limit: 20, records: [], omitted_records: 0,
      };
      for (const row of rows) {
        const [start, end] = row.rendered_content_range;
        if (end - start !== notice.length || rendered.slice(start, end) !== notice) continue;
        observation.observed_literal_count++;
        if (observation.records.length < observation.record_limit) {
          observation.records.push({source_index: row.source_index,
            message_ts: row.message_ts, kind: row.kind,
            rendered_content_range: [start, end]});
        } else {
          observation.omitted_records++;
        }
      }
      result.coverage.application_suppression_notice = observation;
    }
    let used = 0;
    let full = 0;
    let truncated = 0;
    let headerUsed = 0;
    let headerFull = 0;
    let headerTruncated = 0;
    for (const row of selected) {
      const [start, end] = row.rendered_content_range;
      let projectedRow = row;
      if (observeThreadSummaries) {
        // This terminal connector-shaped literal is not authenticated thread state.
        const suffix = /(?:^|\n)(Thread: ([1-9][0-9]*) replies \(latest: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [A-Z]{2,5})\))(?:\nReactions: [^\n]*)?(?:\nFiles: [^\n]+)?\n*$/.exec(rendered.slice(start, end));
        let summary = null;
        if (suffix && Number.isSafeInteger(Number(suffix[2]))) {
          const summaryStart = start + suffix.index + (suffix[0].startsWith('\n') ? 1 : 0);
          summary = {reply_count: Number(suffix[2]), latest_rendered: suffix[3],
            source_range: [summaryStart, summaryStart + suffix[1].length],
            basis: 'rendered_literal_only', authentication: 'not_performed'};
        }
        projectedRow = {...row, thread_summary: summary};
      }
      if (headerOnly) {
        const [headerStart, headerEnd] = row.header_range;
        let length = Math.min(headerEnd - headerStart, limits.max_header_chars,
          limits.max_total_header_chars - headerUsed);
        if (length > 0 && length < headerEnd - headerStart &&
            rendered.charCodeAt(headerStart + length - 1) >= 0xd800 &&
            rendered.charCodeAt(headerStart + length - 1) <= 0xdbff &&
            rendered.charCodeAt(headerStart + length) >= 0xdc00 &&
            rendered.charCodeAt(headerStart + length) <= 0xdfff) length--;
        const clipped = length < headerEnd - headerStart;
        result.messages.push({...projectedRow,
          rendered_header: rendered.slice(headerStart, headerStart + length),
          header_chars: headerEnd - headerStart, returned_header_chars: length,
          header_truncated: clipped, rendered_content: '', content_chars: end - start,
          returned_chars: 0, body_withheld: true, truncated: false});
        full += end - start;
        headerFull += headerEnd - headerStart;
        headerUsed += length;
        headerTruncated += clipped ? 1 : 0;
        continue;
      }
      let length = Math.min(end - start, limits.max_body_chars, limits.max_total_body_chars - used);
      if (length > 0 && length < end - start &&
          rendered.charCodeAt(start + length - 1) >= 0xd800 && rendered.charCodeAt(start + length - 1) <= 0xdbff &&
          rendered.charCodeAt(start + length) >= 0xdc00 && rendered.charCodeAt(start + length) <= 0xdfff) length--;
      const clipped = length < end - start;
      result.messages.push({...projectedRow, rendered_content: rendered.slice(start, start + length),
        content_chars: end - start, returned_chars: length, truncated: clipped});
      full += end - start; used += length; truncated += clipped ? 1 : 0;
    }
    if (sourceIndices === null) {
      Object.assign(result.coverage, {parsed_messages: rows.length, start_index: from,
        returned_messages: result.messages.length, omitted_before: from, omitted_after: rows.length - until,
        next_index: until < rows.length ? until : null, selected_content_chars: full,
        returned_content_chars: used, truncated_messages: truncated,
        all_rendered_messages_included: from === 0 && until === rows.length &&
          truncated === 0 && (!headerOnly || selected.length === 0)});
    } else {
      const omittedRanges = [];
      let cursor = 0;
      for (const index of sourceIndices) {
        if (cursor < index) omittedRanges.push([cursor, index]);
        cursor = index + 1;
      }
      if (cursor < rows.length) omittedRanges.push([cursor, rows.length]);
      const first = sourceIndices.length ? sourceIndices[0] : null;
      const last = sourceIndices.length ? sourceIndices[sourceIndices.length - 1] : null;
      Object.assign(result.coverage, {parsed_messages: rows.length, selection_mode: 'source_indices',
        selected_source_indices: sourceIndices.slice(), start_index: null, next_index: null,
        navigation: 'caller_selected_indices', returned_messages: result.messages.length,
        omitted_messages: rows.length - selected.length, omitted_before: first === null ? 0 : first,
        omitted_interior: first === null ? 0 : last - first + 1 - selected.length,
        omitted_after: last === null ? rows.length : rows.length - last - 1,
        omitted_source_index_ranges: omittedRanges, source_index_range_end: 'exclusive',
        selected_content_chars: full, returned_content_chars: used, truncated_messages: truncated,
        all_rendered_messages_included: selected.length === rows.length &&
          truncated === 0 && (!headerOnly || selected.length === 0)});
    }
    if (headerOnly) {
      Object.assign(result.coverage, {body_mode: 'withheld_by_caller',
        withheld_bodies: selected.length, selected_header_chars: headerFull,
        returned_header_chars: headerUsed, truncated_headers: headerTruncated,
        all_rendered_headers_included: selected.length === rows.length && headerTruncated === 0});
    }
    result.status = rows.length ? 'PROJECTED' : 'EMPTY_RENDERING';
    return result;
  } catch (error) {
    if (!error?.projection) throw error;
    result.messages = [];
    return refuse(error.code, error.detail);
  }
}

/**
 * Project detailed message search results from an already retained response.
 * Context stays in the retained source; only matched text consumes the body budget.
 */
function projectSlackSearchResults(response, request, options = {}) {
  object(request, 'search projection request');
  object(options, 'search projection options');
  const operation = request.operation;
  if (!['search', 'search_public'].includes(operation)) {
    throw new TypeError('search projection operation must be search or search_public');
  }
  const args = object(request.args, 'search projection request.args');
  const withContext = args.include_context !== false;
  const booleanFields = ['include_bots', 'include_context', 'only_my_channels'];
  for (const [key, value] of Object.entries(args)) {
    if (!OPERATIONS[operation].fields.includes(key)) throw new TypeError('unknown search argument: ' + key);
    if (key === 'keywords') {
      if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
        throw new TypeError('search keywords must be an array of strings');
      }
    } else if (booleanFields.includes(key)) {
      if (typeof value !== 'boolean') throw new TypeError('search ' + key + ' must be boolean');
    } else if (key === 'limit' || key === 'max_context_length') {
      if (!Number.isSafeInteger(value) || value < (key === 'limit' ? 1 : 0) ||
          (key === 'limit' && value > 20)) throw new TypeError('invalid search ' + key);
    } else if (typeof value !== 'string') {
      throw new TypeError('search ' + key + ' must be a string');
    }
  }
  if (Object.prototype.hasOwnProperty.call(options, 'include_channel_labels') &&
      typeof options.include_channel_labels !== 'boolean') {
    throw new TypeError('include_channel_labels must be boolean');
  }
  const includeChannelLabels = options.include_channel_labels === true;
  const defaults = {start_index: 0, max_results: 8, max_body_chars: 800,
    max_total_body_chars: 6400, max_input_chars: 1048576};
  const ceilings = {start_index: Number.MAX_SAFE_INTEGER, max_results: 20,
    max_body_chars: 65536, max_total_body_chars: 262144, max_input_chars: 8388608};
  if (includeChannelLabels) {
    Object.assign(defaults, {max_channel_label_chars: 512, max_total_channel_label_chars: 32768});
    Object.assign(ceilings, {max_channel_label_chars: 65536, max_total_channel_label_chars: 262144});
  }
  for (const key of Object.keys(options)) {
    if (key !== 'source_indices' && key !== 'include_channel_labels' &&
        !Object.prototype.hasOwnProperty.call(defaults, key)) {
      const modeHint = ['max_channel_label_chars', 'max_total_channel_label_chars'].includes(key)
        ? '; channel-label budgets require include_channel_labels: true' : '';
      throw new TypeError('unknown search projection option: ' + key + modeHint);
    }
  }
  const limits = {...defaults, ...options};
  delete limits.include_channel_labels;
  for (const [key, value] of Object.entries(limits)) {
    if (key === 'source_indices') continue;
    if (!Number.isSafeInteger(value) || value < (['max_results', 'max_input_chars'].includes(key) ? 1 : 0) ||
        value > ceilings[key]) throw new TypeError('invalid search projection option: ' + key);
  }
  let sourceIndices = null;
  if (Object.prototype.hasOwnProperty.call(options, 'source_indices')) {
    if (Object.prototype.hasOwnProperty.call(options, 'start_index')) {
      throw new TypeError('source_indices and start_index are mutually exclusive');
    }
    if (!Array.isArray(options.source_indices) || options.source_indices.length > limits.max_results) {
      throw new TypeError('source_indices must be an array with at most max_results entries');
    }
    sourceIndices = options.source_indices.slice();
    for (let i = 0; i < sourceIndices.length; i++) {
      if (!Number.isSafeInteger(sourceIndices[i]) || sourceIndices[i] < 0 ||
          (i > 0 && sourceIndices[i] <= sourceIndices[i - 1])) {
        throw new TypeError('source_indices must contain distinct increasing nonnegative safe integers');
      }
    }
    limits.source_indices = sourceIndices;
  }
  const result = {schema: 'commons.connected_slack_search_projection/v1', status: 'REFUSED',
    source: {operation, request_args: null, request_binding: 'caller_retained_request',
      content_basis: 'connector_rendered_content', message_identity: 'rendered_header',
      channel_binding: 'rendered_result_header', rendered_query: null,
      rendered_query_range: null, search_preamble_range: null,
      query_application: 'not_verified', search_date_filters: searchDateFilters(args),
      representations: 0, input_chars: 0},
    limits, coverage: {scope: 'retained_response_only', snapshot: false}, results: [], issue: null};
  const bad = (code, detail) => { throw {searchProjection: true, code, detail}; };
  let charged = 0;
  const charge = value => {
    charged += value.length;
    result.source.input_chars = charged;
    if (charged > limits.max_input_chars) bad('INPUT_LIMIT', 'Retained request and native payload text exceed max_input_chars.');
  };
  try {
    const serializedArgs = JSON.stringify(args);
    charge(serializedArgs);
    result.source.request_args = JSON.parse(serializedArgs);
    if ((args.response_format !== undefined && args.response_format !== 'detailed') ||
        (args.content_types !== undefined && args.content_types !== 'messages')) {
      bad('UNSUPPORTED_REQUEST', withContext ? 'Projection requires detailed message results.'
        : 'Projection requires detailed message results with explicit include_context:false.');
    }
    if (withContext) result.source.context_projection = 'matched_text_only';
    if (!response || typeof response !== 'object' || Array.isArray(response) || response.isError === true) {
      bad('NATIVE_ERROR', 'Expected a successful retained native search response.');
    }
    const representations = [];
    const accept = value => {
      if (!value || typeof value !== 'object' || Array.isArray(value) ||
          Object.keys(value).length !== 2 || typeof value.results !== 'string' ||
          typeof value.pagination_info !== 'string') {
        bad('UNSUPPORTED_PAYLOAD', 'Expected only string results and pagination_info fields.');
      }
      representations.push(value);
    };
    if (Object.prototype.hasOwnProperty.call(response, 'results')) {
      if (typeof response.results === 'string') charge(response.results);
      if (typeof response.pagination_info === 'string') charge(response.pagination_info);
      accept(response);
    } else {
      if (Object.prototype.hasOwnProperty.call(response, 'structuredContent')) {
        const value = response.structuredContent;
        if (typeof value?.results === 'string') charge(value.results);
        if (typeof value?.pagination_info === 'string') charge(value.pagination_info);
        accept(value);
      }
      if (Object.prototype.hasOwnProperty.call(response, 'content')) {
        if (!Array.isArray(response.content) || response.content.length === 0) {
          bad('UNSUPPORTED_PAYLOAD', 'Native content must contain JSON text blocks.');
        }
        for (const block of response.content) {
          if (!block || block.type !== 'text' || typeof block.text !== 'string') {
            bad('UNSUPPORTED_PAYLOAD', 'Non-text native content is outside this projection format.');
          }
          charge(block.text);
          let value;
          try { value = JSON.parse(block.text); } catch (_) {
            bad('UNREADABLE_PAYLOAD', 'Native text is not a JSON envelope.');
          }
          accept(value);
        }
      }
    }
    if (!representations.length) bad('UNSUPPORTED_PAYLOAD', 'No rendered search envelope was retained.');
    result.source.representations = representations.length;
    const page = representations[0];
    if (representations.some(value => value.results !== page.results || value.pagination_info !== page.pagination_info)) {
      bad('CONFLICTING_REPRESENTATIONS', 'Retained native representations disagree.');
    }
    const rendered = page.results;
    result.source.rendered_chars = rendered.length;
    const nativePage = pagination(page);
    Object.assign(result.coverage, {native_pagination_recognized: nativePage.known,
      provider_end_observed: nativePage.end, next_cursor_available: Boolean(nativePage.next_cursor)});
    const prefix = /^# Search Results for: ([^\r\n]*)\n\n/.exec(rendered);
    if (!prefix) bad('UNSUPPORTED_LAYOUT', 'Expected the detailed search preamble.');
    const queryStart = '# Search Results for: '.length;
    result.source.rendered_query = prefix[1];
    result.source.rendered_query_range = [queryStart, queryStart + prefix[1].length];
    result.source.search_preamble_range = [0, prefix[0].length];
    const rows = [];
    let declared = 0;
    if (rendered !== prefix[0] + 'No results found.\n') {
      const section = /^## Messages \(([1-9][0-9]?) results\)\n/.exec(rendered.slice(prefix[0].length));
      if (!section || Number(section[1]) > 20) {
        bad('UNSUPPORTED_LAYOUT', 'Expected one bounded detailed messages section.');
      }
      declared = Number(section[1]);
      const pattern = /^### Result ([1-9][0-9]*) of ([1-9][0-9]*)\nChannel: [^\r\n]+ \(ID: ([CGD][A-Z0-9]{1,127})\)\n(?:Participants: [^\r\n]+\n)?From: [^\r\n]+ \(ID: [UW][A-Z0-9]{1,127}\)(?: |  \[BOT\])?\nTime: [^\r\n]+\nMessage_ts: ([0-9]{1,16}\.[0-9]{1,16})\n(?:Reply count: [0-9]{1,16}\n)?Permalink: \[link\]\((https:\/\/[^\s()]+)\)\nText: \n/gm;
      const headers = Array.from(rendered.matchAll(pattern));
      const markers = (rendered.match(/^### Result\b/gm) || []).length;
      result.coverage.declared_results = declared;
      result.coverage.observed_result_headers = headers.length;
      if ((!withContext && headers.length !== declared) ||
          (withContext && (headers.length === 0 || headers.length > declared)) ||
          markers !== headers.length ||
          headers[0]?.index !== prefix[0].length + section[0].length ||
          (args.limit !== undefined && declared > args.limit)) {
        bad('RESULT_COUNT_MISMATCH', 'Declared results and complete rendered headers differ.');
      }
      const separator = '\n\n---\n\n';
      const ids = new Set();
      for (let i = 0; i < headers.length; i++) {
        const header = headers[i];
        const resultNumber = Number(header[1]);
        if (Number(header[2]) !== declared ||
            (!withContext && resultNumber !== i + 1) ||
            (withContext && (resultNumber > declared ||
              (i > 0 && resultNumber <= Number(headers[i - 1][1]))))) {
          bad('RESULT_SEQUENCE_MISMATCH', 'Rendered result numbering is inconsistent.');
        }
        const end = i + 1 < headers.length ? headers[i + 1].index : rendered.length;
        if (rendered.slice(end - separator.length, end) !== separator) {
          bad('UNSUPPORTED_LAYOUT', 'Expected the complete detailed-result separator.');
        }
        const bodyStart = header.index + header[0].length;
        const bodyEnd = end - separator.length;
        if (bodyEnd < bodyStart) bad('UNSUPPORTED_LAYOUT', 'Result framing overlaps.');
        const id = header[3] + ':' + header[4];
        if (ids.has(id)) bad('DUPLICATE_IDENTITY', 'The rendering repeats a channel/message identity.');
        ids.add(id);
        const link = /^https:\/\/[^/]+\/archives\/([CGD][A-Z0-9]+)\/p([0-9]+)(?:\?[^\s]*)?$/.exec(header[5]);
        if (!link || link[1] !== header[3] || link[2] !== header[4].replace('.', '')) {
          bad('PERMALINK_MISMATCH', 'Rendered permalink and result identity differ.');
        }
        let contentEnd = bodyEnd;
        const contextSections = [];
        if (withContext) {
          const body = rendered.slice(bodyStart, bodyEnd);
          const contexts = Array.from(body.matchAll(/^Context (before|after):[ \t]*\n/gm));
          if (contexts.length > 2 ||
              (contexts.length === 2 && (contexts[0][1] !== 'before' || contexts[1][1] !== 'after'))) {
            bad('AMBIGUOUS_LAYOUT', 'Context sections are repeated or out of order.');
          }
          if (contexts.length) contentEnd = bodyStart + contexts[0].index;
          for (let j = 0; j < contexts.length; j++) {
            const context = contexts[j];
            const start = bodyStart + context.index;
            const textStart = start + context[0].length;
            const end = j + 1 < contexts.length ? bodyStart + contexts[j + 1].index : bodyEnd;
            if (!/^- (?:From: |\[See result above\] From: )/.test(rendered.slice(textStart, end))) {
              bad('UNSUPPORTED_CONTEXT', 'Expected native context list framing.');
            }
            contextSections.push({kind: context[1], header_range: [start, textStart],
              rendered_content_range: [textStart, end], content_chars: end - textStart});
          }
        }
        const body = rendered.slice(bodyStart, contentEnd);
        if (/^(?:# Search Results for:|## (?:Messages|Files)\b|### Result\b|Context (?:before|after):)/m.test(body)) {
          bad('AMBIGUOUS_LAYOUT', 'Result content contains reserved search or context framing.');
        }
        const row = {source_index: i, channel_id: header[3], message_ts: header[4],
          permalink: header[5], rendered_result_range: [header.index, bodyEnd],
          header_range: [header.index, bodyStart], rendered_content_range: [bodyStart, contentEnd]};
        if (includeChannelLabels) {
          const channelPrefix = '\nChannel: ';
          const labelStart = header[0].indexOf(channelPrefix) + channelPrefix.length;
          const lineEnd = header[0].indexOf('\n', labelStart);
          const labelEnd = lineEnd - (' (ID: ' + header[3] + ')').length;
          row.rendered_channel_label_range = [header.index + labelStart, header.index + labelEnd];
        }
        if (withContext) Object.assign(row, {result_number: resultNumber,
          context_sections: contextSections, context_chars: bodyEnd - contentEnd});
        rows.push(row);
      }
    }
    const from = Math.min(limits.start_index, rows.length);
    const until = Math.min(rows.length, from + limits.max_results);
    if (sourceIndices !== null) {
      result.coverage.parsed_results = rows.length;
      if (sourceIndices.some(index => index >= rows.length)) {
        bad('SOURCE_INDEX_OUT_OF_RANGE', 'A requested source index is outside the parsed retained page.');
      }
    }
    const selected = sourceIndices === null ? rows.slice(from, until) : sourceIndices.map(index => rows[index]);
    let full = 0;
    let used = 0;
    let truncated = 0;
    let selectedLabelChars = 0;
    let returnedLabelChars = 0;
    let truncatedLabels = 0;
    for (const row of selected) {
      const [start, end] = row.rendered_content_range;
      let length = Math.min(end - start, limits.max_body_chars, limits.max_total_body_chars - used);
      if (length > 0 && length < end - start &&
          rendered.charCodeAt(start + length - 1) >= 0xd800 && rendered.charCodeAt(start + length - 1) <= 0xdbff &&
          rendered.charCodeAt(start + length) >= 0xdc00 && rendered.charCodeAt(start + length) <= 0xdfff) length--;
      const clipped = length < end - start;
      const projected = {...row, rendered_content: rendered.slice(start, start + length),
        content_chars: end - start, returned_chars: length, truncated: clipped};
      if (includeChannelLabels) {
        const [labelStart, labelEnd] = row.rendered_channel_label_range;
        let labelLength = Math.min(labelEnd - labelStart, limits.max_channel_label_chars,
          limits.max_total_channel_label_chars - returnedLabelChars);
        if (labelLength > 0 && labelLength < labelEnd - labelStart &&
            rendered.charCodeAt(labelStart + labelLength - 1) >= 0xd800 &&
            rendered.charCodeAt(labelStart + labelLength - 1) <= 0xdbff &&
            rendered.charCodeAt(labelStart + labelLength) >= 0xdc00 &&
            rendered.charCodeAt(labelStart + labelLength) <= 0xdfff) labelLength--;
        const labelTruncated = labelLength < labelEnd - labelStart;
        Object.assign(projected, {
          rendered_channel_label: rendered.slice(labelStart, labelStart + labelLength),
          channel_label_chars: labelEnd - labelStart,
          returned_channel_label_chars: labelLength,
          channel_label_truncated: labelTruncated,
        });
        selectedLabelChars += labelEnd - labelStart;
        returnedLabelChars += labelLength;
        truncatedLabels += labelTruncated ? 1 : 0;
      }
      result.results.push(projected);
      full += end - start; used += length; truncated += clipped ? 1 : 0;
    }
    if (sourceIndices === null) {
      Object.assign(result.coverage, {declared_results: declared, parsed_results: rows.length,
        start_index: from, returned_results: result.results.length, omitted_before: from,
        omitted_after: rows.length - until, next_index: until < rows.length ? until : null,
        selected_content_chars: full, returned_content_chars: used, truncated_results: truncated,
        all_rendered_results_included: from === 0 && until === rows.length && truncated === 0});
    } else {
      const omittedRanges = [];
      let cursor = 0;
      for (const index of sourceIndices) {
        if (cursor < index) omittedRanges.push([cursor, index]);
        cursor = index + 1;
      }
      if (cursor < rows.length) omittedRanges.push([cursor, rows.length]);
      const first = sourceIndices.length ? sourceIndices[0] : null;
      const last = sourceIndices.length ? sourceIndices[sourceIndices.length - 1] : null;
      Object.assign(result.coverage, {declared_results: declared, parsed_results: rows.length,
        selection_mode: 'source_indices', selected_source_indices: sourceIndices.slice(),
        start_index: null, next_index: null, navigation: 'caller_selected_indices',
        returned_results: result.results.length, omitted_results: rows.length - selected.length,
        omitted_before: first === null ? 0 : first,
        omitted_interior: first === null ? 0 : last - first + 1 - selected.length,
        omitted_after: last === null ? rows.length : rows.length - last - 1,
        omitted_source_index_ranges: omittedRanges, source_index_range_end: 'exclusive',
        selected_content_chars: full, returned_content_chars: used, truncated_results: truncated,
        all_rendered_results_included: selected.length === rows.length && truncated === 0});
    }
    if (includeChannelLabels) result.coverage.channel_labels = {
      scope: 'selected_rendered_result_headers',
      interpretation: 'rendered_text_only',
      authentication: 'not_performed',
      selected_chars: selectedLabelChars,
      returned_chars: returnedLabelChars,
      truncated_labels: truncatedLabels,
    };
    if (withContext) Object.assign(result.coverage, {
      unrendered_results: declared - rows.length,
      rendered_result_numbers: rows.map(row => row.result_number),
      selected_context_chars: selected.reduce((total, row) => total + row.context_chars, 0),
      returned_context_chars: 0,
      all_declared_results_included: rows.length === declared && result.coverage.all_rendered_results_included,
    });
    result.status = rows.length
      ? (withContext && rows.length < declared ? 'PARTIAL' : 'PROJECTED')
      : 'EMPTY_RENDERING';
    return result;
  } catch (error) {
    if (!error?.searchProjection) throw error;
    result.results = [];
    result.issue = {code: error.code, detail: error.detail};
    return result;
  }
}


/**
 * Select one native response from a retained collector, then use an unchanged
 * single-page projector. Metadata consistency is not authentication.
 */
function projectCollectedSlackPage(collection, options, operations, projector) {
  object(options, 'collected projection options');
  for (const key of Object.keys(options)) {
    if (!['page_index', 'projection'].includes(key)) {
      throw new TypeError('unknown collected projection option: ' + key);
    }
  }
  if (options.page_index !== undefined &&
      (!Number.isSafeInteger(options.page_index) || options.page_index < 0)) {
    throw new TypeError('page_index must be a nonnegative safe integer');
  }
  const projectionOptions = options.projection === undefined ? {} :
    object(options.projection, 'collected projection options.projection');
  const result = {
    schema: 'commons.connected_slack_collected_projection/v1',
    status: 'REFUSED',
    collector: {
      metadata_binding: 'caller_retained_collector_consistency_only',
      authentication: 'not_performed', snapshot: false,
      projection_scope: 'one_retained_native_response',
    },
    limits: {max_recorded_pages: 1000, max_retained_responses: 1000,
      max_metadata_chars: 65536},
    projection: null, issue: null,
  };
  const fail = (code, detail) => { throw {collectedProjection: true, code, detail}; };
  const record = (value, label) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      fail('INVALID_COLLECTOR', label + ' must be an object.');
    }
    return value;
  };
  let metadataChars = 0;
  const textMetadata = (value, label, nullable = false) => {
    if (nullable && value === null) return null;
    if (typeof value !== 'string') fail('INVALID_COLLECTOR', label + ' must be a string.');
    metadataChars += value.length;
    if (metadataChars > result.limits.max_metadata_chars) {
      fail('COLLECTOR_METADATA_LIMIT', 'Recorded metadata exceeds max_metadata_chars.');
    }
    return value;
  };
  const dense = (value, maximum, label) => {
    if (!Array.isArray(value) || value.length > maximum) {
      fail('INVALID_COLLECTOR', label + ' must be a bounded array.');
    }
    for (let i = 0; i < value.length; i++) {
      if (!Object.prototype.hasOwnProperty.call(value, i)) {
        fail('INVALID_COLLECTOR', label + ' must not contain holes.');
      }
    }
  };
  try {
    record(collection, 'collector');
    if (collection.schema !== 'commons.connected_slack_pages/v1') {
      fail('UNSUPPORTED_COLLECTOR_SCHEMA', 'Expected commons.connected_slack_pages/v1.');
    }
    const operation = collection.operation;
    if (!operations.includes(operation)) {
      fail('COLLECTOR_OPERATION_MISMATCH', 'Collector operation does not match this projector.');
    }
    const spec = OPERATIONS[operation];
    if (collection.binding !== spec.binding) {
      fail('COLLECTOR_BINDING_MISMATCH', 'Collector binding does not match its operation.');
    }
    const request = record(collection.request, 'collector.request');
    if (Object.keys(request).some(key =>
      !['operation', 'args', 'max_pages', 'timeout_ms'].includes(key)) ||
      request.operation !== operation ||
      !Number.isSafeInteger(request.max_pages) || request.max_pages < 1 ||
      !Number.isSafeInteger(request.timeout_ms) || request.timeout_ms < 1) {
      fail('COLLECTOR_REQUEST_MISMATCH', 'Collector request must retain its normalized operation and budgets.');
    }
    const argumentSignature = args => {
      record(args, 'recorded request arguments');
      const keys = Object.keys(args).sort();
      if (keys.length > spec.fields.length || keys.some(key => !spec.fields.includes(key))) {
        fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded arguments contain an unsupported field.');
      }
      if (args.response_format !== 'detailed' || !Number.isSafeInteger(args.limit) ||
          args.limit < 1 || args.limit > spec.maximumLimit) {
        fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded arguments must retain normalized format and limit.');
      }
      const entries = [];
      for (const key of keys) {
        const value = args[key];
        if (key === 'keywords') {
          dense(value, 1000, 'recorded keywords');
          for (const term of value) textMetadata(term, 'recorded keyword');
        } else if (['include_bots', 'include_context', 'only_my_channels'].includes(key)) {
          if (typeof value !== 'boolean') fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded flag must be boolean.');
        } else if (key === 'limit' || key === 'max_context_length') {
          if (!Number.isSafeInteger(value) || value < (key === 'limit' ? 1 : 0)) {
            fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded numeric argument is invalid.');
          }
        } else {
          textMetadata(value, 'recorded ' + key);
        }
        if (key !== 'cursor') entries.push([key, value]);
      }
      if (args.cursor !== undefined && !args.cursor.trim()) {
        fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded cursor must be nonempty.');
      }
      return {base: JSON.stringify(entries), cursor: args.cursor ?? null};
    };
    const base = argumentSignature(request.args);
    dense(collection.pages, result.limits.max_recorded_pages, 'collector.pages');
    dense(collection.responses, result.limits.max_retained_responses, 'collector.responses');
    const pages = collection.pages, responses = collection.responses;
    const summary = record(collection.summary, 'collector.summary');
    if (pages.length > request.max_pages || summary.calls !== pages.length ||
        summary.retained_responses !== responses.length ||
        !Number.isSafeInteger(summary.successful_pages) || summary.successful_pages < 0 ||
        summary.successful_pages > responses.length || summary.snapshot !== false ||
        summary.coverage !== 'native_pagination_only' ||
        typeof summary.provider_end_observed !== 'boolean') {
      fail('INVALID_COLLECTOR', 'Collector counts or coverage metadata are inconsistent.');
    }
    textMetadata(summary.stop_reason, 'collector stop_reason');
    textMetadata(summary.next_cursor, 'collector next_cursor', true);
    let responseIndex = 0, cursor = base.cursor;
    for (let i = 0; i < pages.length; i++) {
      const page = record(pages[i], 'recorded page');
      if (page.call !== i + 1) fail('INVALID_COLLECTOR', 'Recorded call order is inconsistent.');
      const actual = argumentSignature(page.request_args);
      if (actual.base !== base.base || actual.cursor !== cursor) {
        fail('COLLECTOR_REQUEST_MISMATCH', 'Recorded page arguments do not match the request cursor chain.');
      }
      textMetadata(page.pagination_info, 'page pagination_info', true);
      textMetadata(page.next_cursor, 'page next_cursor', true);
      if (typeof page.provider_end_observed !== 'boolean') {
        fail('INVALID_COLLECTOR', 'Recorded page ending must be boolean.');
      }
      if (page.response_index === null) {
        if (i !== pages.length - 1 || !page.error ||
            summary.stop_reason !== 'NATIVE_EXCEPTION') {
          fail('COLLECTOR_RESPONSE_MAPPING', 'Only a final native exception may lack a retained response.');
        }
      } else if (page.response_index !== responseIndex++ ||
          !Number.isSafeInteger(page.response_index) ||
          page.response_index < 0 || page.response_index >= responses.length) {
        fail('COLLECTOR_RESPONSE_MAPPING', 'Each retained response must have one ordered page mapping.');
      }
      if (i + 1 < pages.length) {
        if (page.error || page.callback_error || page.provider_end_observed ||
            typeof page.next_cursor !== 'string' || !page.next_cursor.trim()) {
          fail('COLLECTOR_REQUEST_MISMATCH', 'A stopped page cannot have a following recorded call.');
        }
        cursor = page.next_cursor;
      }
    }
    if (responseIndex !== responses.length) {
      fail('COLLECTOR_RESPONSE_MAPPING', 'Collector has unmapped retained responses.');
    }
    if (summary.successful_pages !== pages.filter(page => !page.error).length ||
        summary.provider_end_observed !== pages.some(page => !page.error && page.provider_end_observed)) {
      fail('INVALID_COLLECTOR', 'Collector success or ending summary differs from its recorded pages.');
    }
    Object.assign(result.collector, {
      operation, binding: collection.binding, recorded_pages: pages.length,
      retained_responses: responses.length, metadata_chars: metadataChars,
      reported_stop_reason: summary.stop_reason,
      reported_provider_end_observed: summary.provider_end_observed,
      reported_next_cursor: summary.next_cursor,
    });
    if (!pages.length) fail('NO_RECORDED_PAGE', 'Collector has no recorded page to select.');
    if (options.page_index === undefined && pages.length !== 1) {
      fail('PAGE_SELECTION_REQUIRED', 'Supply page_index for a collector with multiple recorded pages.');
    }
    const selected = options.page_index ?? 0;
    if (selected >= pages.length) fail('PAGE_INDEX_OUT_OF_RANGE', 'page_index is outside collector.pages.');
    const page = pages[selected];
    Object.assign(result.collector, {
      selection_mode: options.page_index === undefined ? 'single_page_default' : 'explicit_page_index',
      page_index: selected, call: page.call, response_index: page.response_index,
      page_source_path: 'pages[' + selected + ']',
      response_source_path: page.response_index === null ? null : 'responses[' + page.response_index + ']',
      omitted_pages: pages.length - 1,
      omitted_page_index_ranges: [
        ...(selected ? [[0, selected]] : []),
        ...(selected + 1 < pages.length ? [[selected + 1, pages.length]] : []),
      ],
      page_index_range_end: 'exclusive',
      unselected_responses: responses.length - (page.response_index === null ? 0 : 1),
      selected_page_error_recorded: !!page.error,
      selected_callback_error_recorded: !!page.callback_error,
    });
    if (page.response_index === null) {
      fail('SELECTED_PAGE_HAS_NO_RESPONSE', 'The selected native call has no retained response; inspect its original error.');
    }
    // Original response and arguments stay untouched. The page projector keeps
    // its own payload, request, source-range, refusal and content-budget rules.
    result.projection = projector(responses[page.response_index],
      {operation, args: copy(page.request_args)}, projectionOptions);
    result.status = result.projection.status;
    result.issue = result.projection.issue;
    return result;
  } catch (error) {
    if (!error?.collectedProjection) throw error;
    result.collector.metadata_chars = metadataChars;
    result.issue = {code: error.code, detail: error.detail};
    return result;
  }
}

function projectSlackCollectedMessages(collection, options = {}) {
  return projectCollectedSlackPage(collection, options,
    ['read_channel', 'read_thread'], projectSlackMessages);
}

function projectSlackCollectedSearchResults(collection, options = {}) {
  return projectCollectedSlackPage(collection, options,
    ['search', 'search_public'], projectSlackSearchResults);
}


/**
 * Report caller-retained read_channel metadata across collections. Never reads
 * response bodies, recommends requests, or changes collection/hold state.
 */
function projectSlackCollectionHandoffs(records, options = {}) {
  object(options, 'handoff options');
  for (const key of Object.keys(options)) {
    if (!['max_collections', 'max_metadata_chars'].includes(key)) {
      throw new TypeError('unknown handoff option');
    }
  }
  const maxCollections = positive(options.max_collections ?? 20, 'max_collections', 100);
  const maxChars = positive(options.max_metadata_chars ?? 65536, 'max_metadata_chars', 262144);
  if (!Array.isArray(records) || records.length > maxCollections) {
    throw new TypeError('records must be an array within max_collections');
  }
  const result = {
    schema: 'commons.connected_slack_collection_handoffs/v1', status: 'PROJECTED',
    provenance: {
      basis: 'caller_retained_metadata_only', authentication: 'not_performed',
      native_responses_parsed: false, snapshot: false,
      window_application: 'not_verified', holds: 'not_assessed',
      scope: 'supplied_collections_only', continuation: 'recorded_not_recommended',
    },
    limits: {max_collections: maxCollections, max_metadata_chars: maxChars,
      max_pages_per_collection: 1000, max_overlap_records: 100},
    supplied_collections: records.length, records: [], omitted_collections: 0,
    requested_window_overlaps: [], omitted_overlap_records: 0, metadata_chars: 0,
  };
  const isRecord = value => value && typeof value === 'object' && !Array.isArray(value);
  const boundedText = (value, maximum = 4096) =>
    typeof value === 'string' && value.length <= maximum ? value : null;
  const cursorView = value => ({
    value: boundedText(value),
    state: value === null || value === undefined ? 'absent'
      : typeof value !== 'string' || !value.trim() ? 'invalid'
        : value.length > 4096 ? 'omitted_oversize' : 'present',
  });
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  const flag = value => typeof value === 'boolean' ? value : null;
  const fields = OPERATIONS.read_channel.fields;
  const requestView = value => {
    if (!isRecord(value)) return null;
    const args = isRecord(value.args) ? value.args : {};
    const view = {operation: value.operation === 'read_channel' ? 'read_channel' : null,
      args: {}, invalid_argument_fields: [],
      unrecognized_argument_count: Object.keys(args).filter(key => !fields.includes(key)).length,
      max_pages: count(value.max_pages), timeout_ms: count(value.timeout_ms)};
    for (const key of fields) {
      if (!Object.prototype.hasOwnProperty.call(args, key)) continue;
      const v = key === 'limit' ? count(args[key]) : boundedText(args[key]);
      view.args[key] = v;
      if (v === null) view.invalid_argument_fields.push(key);
    }
    return view;
  };
  const errorView = (value, sourcePath) => {
    if (!value) return null;
    return {source_path: sourcePath,
      error_code: typeof value.error_code === 'string' && /^[A-Z0-9_]{1,64}$/.test(value.error_code)
        ? value.error_code : null,
      http_status: Number.isInteger(value.http_status) && value.http_status >= 100 &&
        value.http_status <= 599 ? value.http_status : null};
  };
  const stops = new Set(['TIME_BUDGET', 'NATIVE_EXCEPTION', 'NATIVE_ERROR',
    'UNKNOWN_PAGINATION', 'PROVIDER_END', 'CURSOR_REPEAT', 'UNREADABLE_RESPONSE',
    'CALLBACK_ERROR', 'PAGE_BUDGET']);
  const admit = (target, value) => {
    const size = JSON.stringify(value).length;
    if (result.metadata_chars + size > maxChars) return false;
    result.metadata_chars += size;
    target.push(value);
    return true;
  };
  for (let i = 0; i < records.length; i++) {
    const entry = records[i];
    if (!Object.prototype.hasOwnProperty.call(records, i) || !isRecord(entry) ||
        typeof entry.custody_key !== 'string' || !entry.custody_key.trim() ||
        entry.custody_key.length > 256) {
      throw new TypeError('each record requires a nonempty custody_key of at most 256 characters');
    }
    const collection = entry.collection;
    const row = {source_index: i, custody_key: entry.custody_key,
      collection_source_path: 'records[' + i + '].collection',
      metadata_status: 'REFUSED', issue_code: null};
    if (!isRecord(collection) || collection.operation !== 'read_channel') {
      row.issue_code = 'UNSUPPORTED_COLLECTION';
    } else if (!Array.isArray(collection.pages) || collection.pages.length > 1000 ||
        !Array.isArray(collection.responses) || collection.responses.length > 1000) {
      row.issue_code = 'COLLECTION_ARRAY_LIMIT';
    } else {
      // Reuse the existing full-chain metadata checks with a body-free callback.
      // The callback neither parses nor copies its native-response argument.
      const checked = projectCollectedSlackPage(collection, {page_index: 0},
        ['read_channel'], () => ({status: 'METADATA_ONLY', issue: null}));
      row.metadata_status = checked.status === 'METADATA_ONLY' ||
        ['NO_RECORDED_PAGE', 'SELECTED_PAGE_HAS_NO_RESPONSE'].includes(checked.issue?.code)
        ? 'CONSISTENT_RECORDED_METADATA' : 'REFUSED';
      row.issue_code = checked.issue?.code ?? null;
      row.binding = collection.binding === OPERATIONS.read_channel.binding ? collection.binding : null;
      row.request = requestView(collection.request);
      row.started_at = boundedText(collection.started_at, 64);
      row.finished_at = boundedText(collection.finished_at, 64);
      row.retained_responses = collection.responses.length;
      const summary = isRecord(collection.summary) ? collection.summary : {};
      row.reported_summary = {
        calls: count(summary.calls), successful_pages: count(summary.successful_pages),
        retained_responses: count(summary.retained_responses),
        started_with_cursor: flag(summary.started_with_cursor),
        provider_end_observed: flag(summary.provider_end_observed),
        stop_reason: stops.has(summary.stop_reason) ? summary.stop_reason : 'UNRECOGNIZED',
        next_cursor: cursorView(summary.next_cursor),
        native_error: errorView(summary.native_error, row.collection_source_path + '.summary.native_error'),
      };
      row.recorded_next_request = requestView(collection.next_request);
      row.next_request_recorded = collection.next_request !== null && collection.next_request !== undefined;
      row.pages = collection.pages.map((page, j) => {
        if (!isRecord(page)) return {source_index: j, issue_code: 'INVALID_PAGE'};
        const path = row.collection_source_path + '.pages[' + j + ']';
        return {source_index: j, source_path: path, call: count(page.call),
          request: requestView({operation: 'read_channel', args: page.request_args}),
          response_index: count(page.response_index),
          response_source_path: Number.isSafeInteger(page.response_index) && page.response_index >= 0 &&
            page.response_index < collection.responses.length
            ? row.collection_source_path + '.responses[' + page.response_index + ']' : null,
          provider_end_observed: flag(page.provider_end_observed),
          next_cursor: cursorView(page.next_cursor),
          error: errorView(page.error, path + '.error'),
          callback_error_recorded: Boolean(page.callback_error)};
      });
      const args = row.request?.args ?? {};
      row.end_scope = row.metadata_status !== 'CONSISTENT_RECORDED_METADATA' ? 'unassessed'
        : summary.provider_end_observed !== true || summary.stop_reason !== 'PROVIDER_END'
          ? 'no_provider_end_disposition'
          : args.cursor !== undefined ? 'resumed_suffix_provider_end'
            : args.oldest !== undefined && args.latest !== undefined
              ? 'standalone_bounded_request_provider_end' : 'unbounded_request_provider_end';
      row.has_recorded_stop_error = Boolean(summary.native_error) ||
        collection.pages.some(page => Boolean(page?.error || page?.callback_error));
      if (row.has_recorded_stop_error && summary.provider_end_observed === true) {
        row.end_scope = 'provider_end_with_recorded_error';
      }
    }
    if (!admit(result.records, row)) {
      result.status = 'PARTIAL';
      result.omitted_collections = records.length - i;
      break;
    }
  }
  // Compare declared bounds only. No union, deduplication, snapshot or next
  // frontier is derived, including when a resumed suffix reports provider END.
  const stamp = value => {
    if (typeof value !== 'string' || !/^[0-9]{1,16}\.[0-9]{1,16}$/.test(value)) return null;
    const [seconds, fraction] = value.split('.');
    return BigInt(seconds) * 10000000000000000n + BigInt(fraction.padEnd(16, '0'));
  };
  for (let i = 0; i < result.records.length; i++) {
    const a = result.records[i], aa = a.request?.args;
    if (a.metadata_status !== 'CONSISTENT_RECORDED_METADATA' || !aa ||
        typeof aa.channel_id !== 'string' || !aa.channel_id.trim()) continue;
    const al = stamp(aa.oldest), ah = stamp(aa.latest);
    if (al === null || ah === null || al > ah) continue;
    for (let j = i + 1; j < result.records.length; j++) {
      const b = result.records[j], ba = b.request?.args;
      if (b.metadata_status !== 'CONSISTENT_RECORDED_METADATA' || !ba ||
          aa.channel_id !== ba.channel_id) continue;
      const bl = stamp(ba.oldest), bh = stamp(ba.latest);
      if (bl === null || bh === null || bl > bh || ah < bl || bh < al) continue;
      const overlap = {source_indices: [a.source_index, b.source_index],
        scope: 'requested_bounds_only',
        oldest: al >= bl ? aa.oldest : ba.oldest, latest: ah <= bh ? aa.latest : ba.latest,
        limit_changed: aa.limit !== ba.limit,
        response_format_changed: aa.response_format !== ba.response_format};
      if (result.requested_window_overlaps.length >= result.limits.max_overlap_records ||
          !admit(result.requested_window_overlaps, overlap)) result.omitted_overlap_records++;
    }
  }
  if (result.omitted_overlap_records) result.status = 'PARTIAL';
  return result;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {collectSlackPages, projectSlackMessages, projectSlackSearchResults, projectSlackReadFailure,
    projectSlackCollectedMessages, projectSlackCollectedSearchResults, projectSlackCollectionHandoffs};
}
