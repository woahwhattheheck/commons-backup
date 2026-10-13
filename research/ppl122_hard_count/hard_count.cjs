"use strict";

/*
 * Kimberling's A Hard Count: complete finite written-cell histories.
 * Original problem: https://faculty.evansville.edu/ck6/integer/unsolved.html, section 4.
 * This module constructs finite prefixes. It does not prove that every positive
 * integer appears. All positions include the seed and are zero based.
 */
const SCHEMA = "commons.kimberling_hard_count/v1";
const LIMITS = Object.freeze({
  seed_columns: 32, value_digits: 128, source_id_chars: 512,
  total_tables: 512, tables_per_advance: 256, written_tokens: 65536,
  page_size: 64, sessions: 16, events_per_session: 32,
  export_values: 8000000, export_string_key_chars: 40000000, depth: 48
});
const CORE_KEYS = Object.freeze([
  "seed_tokens_written", "tables_constructed", "frozen_count_reads",
  "value_map_lookups", "occurrence_positions_appended", "frequency_increments",
  "dictionary_insertions", "ordering_comparisons", "positive_prefix_checks",
  "row_cells_saved"
]);
const QUERY_KEYS = Object.freeze([
  "calls", "dictionary_lookups", "binary_comparisons", "stored_rows_read",
  "column_records_read", "occurrence_positions_read", "origin_records_read",
  "returned_records", "table_reconstructions", "recurrence_steps",
  "occurrence_index_rebuilds"
]);
const METHODS = new Set([
  "advance", "pageTables", "pageTable", "countAt", "firstAppearance",
  "locateToken", "rankOccurrences", "selectOccurrence", "pageOccurrences",
  "pageValues", "pageNewValues"
]);

function fail(code, message) {
  const error = new Error(message);
  error.name = "HardCountError";
  error.code = code;
  throw error;
}
function plain(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}
function shape(value, required, optional, label) {
  if (!plain(value)) fail("INPUT", label + " must be a plain object");
  const allowed = new Set(required.concat(optional || []));
  for (const key of required) if (!Object.hasOwn(value, key)) fail("INPUT", label + "." + key + " is required");
  for (const key of Object.keys(value)) if (!allowed.has(key)) fail("INPUT", label + "." + key + " is not supported");
}
function integer(value, low, high, label) {
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    fail("INPUT", label + " must be a safe integer in [" + low + "," + high + "]");
  }
  return value;
}
function decimal(value, label) {
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value <= 0) fail("INPUT", label + " must be positive and exact");
    value = String(value);
  }
  if (typeof value !== "string" || value.length > LIMITS.value_digits || !/^[1-9][0-9]*$/.test(value)) {
    fail("INPUT", label + " must be a positive canonical decimal of at most " + LIMITS.value_digits + " digits");
  }
  return value;
}
function storedDecimal(value, label) {
  if (typeof value !== "string") fail("RECORD", label + " must be a decimal string");
  return decimal(value, label);
}
function cmpDecimal(a, b) {
  return a.length === b.length ? (a < b ? -1 : a > b ? 1 : 0) : (a.length < b.length ? -1 : 1);
}
function zeros(keys) { return Object.fromEntries(keys.map(key => [key, 0])); }
function addCounters(target, delta) {
  for (const key of Object.keys(delta)) {
    if (!Object.hasOwn(target, key)) fail("INTERNAL", "unknown work counter " + key);
    const next = target[key] + delta[key];
    if (!Number.isSafeInteger(next) || next < 0) fail("COUNTER_LIMIT", "work counter overflow");
    target[key] = next;
  }
}
function counterObject(value, keys, label) {
  shape(value, keys, [], label);
  for (const key of keys) integer(value[key], 0, Number.MAX_SAFE_INTEGER, label + "." + key);
}
function assertUsage(usage) {
  if (usage.values > LIMITS.export_values ||
      usage.string_key_chars > LIMITS.export_string_key_chars ||
      usage.max_depth > LIMITS.depth) fail("EXPORT_LIMIT", "complete record exceeds the bounded JSON copy budget");
}
function walkJson(value, copying) {
  const usage = { values: 0, string_key_chars: 0, max_depth: 0 };
  const active = new Set();
  function visit(item, depth) {
    usage.values += 1;
    usage.max_depth = Math.max(usage.max_depth, depth);
    if (typeof item === "string") usage.string_key_chars += item.length;
    assertUsage(usage);
    if (item === null || typeof item === "string" || typeof item === "boolean") return item;
    if (typeof item === "number") {
      if (!Number.isSafeInteger(item)) fail("JSON", "record numbers must be safe integers");
      return item;
    }
    if (typeof item !== "object" || (!Array.isArray(item) && !plain(item))) {
      fail("JSON", "only plain JSON data is accepted");
    }
    if (active.has(item)) fail("JSON", "cyclic data is not accepted");
    if (Object.getOwnPropertySymbols(item).length !== 0) fail("JSON", "symbol properties are not accepted");
    active.add(item);
    let out = copying ? (Array.isArray(item) ? [] : {}) : null;
    if (Array.isArray(item)) {
      if (Object.keys(item).length !== item.length || Object.getOwnPropertyNames(item).length !== item.length + 1) {
        fail("JSON", "arrays must be dense and have no extra properties");
      }
      for (let i = 0; i < item.length; i += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(item, String(i));
        if (!descriptor || !Object.hasOwn(descriptor, "value")) fail("JSON", "array accessors are not accepted");
        const child = visit(descriptor.value, depth + 1);
        if (copying) out.push(child);
      }
    } else {
      const names = Object.getOwnPropertyNames(item);
      if (names.length !== Object.keys(item).length) fail("JSON", "non-enumerable object properties are not accepted");
      for (const key of names) {
        usage.string_key_chars += key.length;
        assertUsage(usage);
        const descriptor = Object.getOwnPropertyDescriptor(item, key);
        if (!descriptor || !Object.hasOwn(descriptor, "value")) fail("JSON", "object accessors are not accepted");
        const child = visit(descriptor.value, depth + 1);
        if (copying) Object.defineProperty(out, key, { value: child, writable: true, configurable: true, enumerable: true });
      }
    }
    active.delete(item);
    return out;
  }
  const result = visit(value, 0);
  return { value: result, usage };
}
function copyJson(value) { return walkJson(value, true); }
function measureJson(value) { return walkJson(value, false).usage; }
function usageAfter(base, removed, added, extra, extraDepth) {
  const result = {
    values: base.values - (removed ? removed.values : 0) + (added ? added.values : 0) + (extra ? extra.values : 0),
    string_key_chars: base.string_key_chars - (removed ? removed.string_key_chars : 0) +
      (added ? added.string_key_chars : 0) + (extra ? extra.string_key_chars : 0),
    max_depth: Math.max(base.max_depth, added ? added.max_depth + 1 : 0, extra ? extra.max_depth + extraDepth : 0)
  };
  assertUsage(result);
  return result;
}
function inputSeed(seed) {
  if (!plain(seed)) fail("INPUT", "seed must be a plain object");
  if (seed.kind === "one") {
    shape(seed, ["kind"], [], "seed");
    return { kind: "one" };
  }
  shape(seed, ["kind", "counts", "labels"], [], "seed");
  if (seed.kind !== "written_counting") fail("INPUT", "unknown seed kind");
  if (!Array.isArray(seed.counts) || !Array.isArray(seed.labels) ||
      seed.counts.length < 1 || seed.counts.length > LIMITS.seed_columns ||
      seed.counts.length !== seed.labels.length) fail("INPUT", "initial rows must have the same bounded positive width");
  const counts = seed.counts.map((value, i) => decimal(value, "seed.counts[" + i + "]"));
  const labels = seed.labels.map((value, i) => decimal(value, "seed.labels[" + i + "]"));
  if (new Set(labels).size !== labels.length) fail("INPUT", "initial bottom-row labels must be distinct");
  return { kind: "written_counting", counts, labels };
}
function physicalSeed(seed) {
  return seed.kind === "one" ? ["1"] : seed.counts.concat(seed.labels);
}
function makeValueMap(core) {
  return new Map(core.dictionary.map((entry, id) => [entry.value, id]));
}
function appendById(core, id, position) {
  core.occurrences[id].push(position);
  core.frontier.counts_by_id[id] += 1;
  core.work.occurrence_positions_appended += 1;
  core.work.frequency_increments += 1;
}
function appendValue(core, valueMap, value, position, step) {
  core.work.value_map_lookups += 1;
  let id = valueMap.get(value), inserted = false;
  if (id === undefined) {
    id = core.dictionary.length;
    valueMap.set(value, id);
    core.dictionary.push({ value, first_position: position, first_step: step });
    core.occurrences.push([]);
    core.frontier.counts_by_id.push(0);
    core.work.dictionary_insertions += 1;
    inserted = true;
  }
  appendById(core, id, position);
  return { id, inserted };
}
function refreshPositivePrefix(core, valueMap) {
  for (;;) {
    core.work.positive_prefix_checks += 1;
    if (!valueMap.has(String(core.frontier.positive_prefix + 1))) return;
    core.frontier.positive_prefix += 1;
  }
}
function orderIds(core, ids) {
  return ids.sort((left, right) => {
    core.work.ordering_comparisons += 1;
    return cmpDecimal(core.dictionary[left].value, core.dictionary[right].value);
  });
}
function mergeIds(core, oldIds, addedIds) {
  const sortedNew = orderIds(core, addedIds.slice());
  const result = [];
  let i = 0, j = 0;
  while (i < oldIds.length && j < sortedNew.length) {
    core.work.ordering_comparisons += 1;
    if (cmpDecimal(core.dictionary[oldIds[i]].value, core.dictionary[sortedNew[j]].value) < 0) {
      result.push(oldIds[i++]);
    } else result.push(sortedNew[j++]);
  }
  while (i < oldIds.length) result.push(oldIds[i++]);
  while (j < sortedNew.length) result.push(sortedNew[j++]);
  return result;
}
function createCore(seed) {
  const core = {
    input: seed,
    dictionary: [],
    seed_token_ids: [],
    tables: [],
    occurrences: [],
    frontier: { tables: 0, token_count: 0, sorted_ids: [], counts_by_id: [], positive_prefix: 0 },
    work: zeros(CORE_KEYS)
  };
  const map = new Map(), cells = physicalSeed(seed);
  for (let position = 0; position < cells.length; position += 1) {
    core.seed_token_ids.push(appendValue(core, map, cells[position], position, 0).id);
  }
  core.work.seed_tokens_written = cells.length;
  core.frontier.token_count = cells.length;
  core.frontier.sorted_ids = orderIds(core, core.dictionary.map((_, id) => id));
  refreshPositivePrefix(core, map);
  return core;
}
function constructTable(core, valueMap) {
  const oldIds = core.frontier.sorted_ids.slice();
  const counts = oldIds.map(id => {
    core.work.frozen_count_reads += 1;
    return core.frontier.counts_by_id[id];
  });
  const width = oldIds.length, step = core.frontier.tables + 1;
  const start = core.frontier.token_count, newIds = [];
  for (let column = 0; column < width; column += 1) {
    const result = appendValue(core, valueMap, String(counts[column]), start + column, step);
    if (result.inserted) newIds.push(result.id);
  }
  for (let column = 0; column < width; column += 1) appendById(core, oldIds[column], start + width + column);
  core.frontier.sorted_ids = mergeIds(core, oldIds, newIds);
  core.frontier.token_count += 2 * width;
  core.frontier.tables = step;
  refreshPositivePrefix(core, valueMap);
  const row = {
    step, token_start: start, token_end: core.frontier.token_count,
    label_ids: oldIds, counts, new_value_ids: newIds,
    distinct_after: core.dictionary.length,
    positive_prefix_after: core.frontier.positive_prefix,
    maximum_value_id_after: core.frontier.sorted_ids[core.frontier.sorted_ids.length - 1]
  };
  core.tables.push(row);
  core.work.tables_constructed += 1;
  core.work.row_cells_saved += 2 * width;
  return row;
}


function tableSummary(core, row) {
  return {
    step: row.step, width: row.label_ids.length, token_start: row.token_start,
    token_end: row.token_end, new_value_count: row.new_value_ids.length,
    distinct_after: row.distinct_after, positive_prefix_after: row.positive_prefix_after,
    first_missing_after: String(row.positive_prefix_after + 1),
    maximum_written_after: core.dictionary[row.maximum_value_id_after].value
  };
}
function smallSummary(record, session) {
  const c = record.core, f = c.frontier;
  return {
    schema: SCHEMA, source_id: record.source_id,
    session_id: session.session_id, recorded_events: session.events.length,
    tables: f.tables, written_tokens: f.token_count, distinct_values: c.dictionary.length,
    positive_prefix: f.positive_prefix, first_missing: String(f.positive_prefix + 1),
    maximum_written: c.dictionary[f.sorted_ids[f.sorted_ids.length - 1]].value,
    next_table_width: f.sorted_ids.length,
    remaining_table_capacity: LIMITS.total_tables - f.tables,
    remaining_token_capacity: LIMITS.written_tokens - f.token_count,
    construction_work: c.work, session_work: session.counters
  };
}
function lowerBound(numbers, target, work) {
  let low = 0, high = numbers.length;
  while (low < high) {
    work.binary_comparisons += 1;
    const mid = low + Math.floor((high - low) / 2);
    if (numbers[mid] < target) low = mid + 1; else high = mid;
  }
  return low;
}
function findColumn(core, row, value, work) {
  let low = 0, high = row.label_ids.length;
  while (low < high) {
    work.binary_comparisons += 1;
    const mid = low + Math.floor((high - low) / 2);
    const comparison = cmpDecimal(core.dictionary[row.label_ids[mid]].value, value);
    if (comparison < 0) low = mid + 1; else high = mid;
  }
  if (low < row.label_ids.length) {
    work.binary_comparisons += 1;
    if (core.dictionary[row.label_ids[low]].value === value) return low;
  }
  return -1;
}
function tokenLocation(core, valueMap, position, work) {
  if (position < core.seed_token_ids.length) {
    const id = core.seed_token_ids[position], seed = core.input;
    const width = seed.kind === "one" ? 1 : seed.counts.length;
    work.origin_records_read += 1;
    return {
      position, value_id: id, value: core.dictionary[id].value, step: 0,
      kind: seed.kind === "one" ? "seed_one" : position < width ? "seed_count" : "seed_label",
      column: seed.kind === "one" ? 0 : position % width,
      counted_label: seed.kind === "written_counting" && position < width ? seed.labels[position] : null
    };
  }
  let low = 0, high = core.tables.length;
  while (low < high) {
    work.binary_comparisons += 1;
    const mid = low + Math.floor((high - low) / 2);
    if (core.tables[mid].token_start <= position) low = mid + 1; else high = mid;
  }
  const row = core.tables[low - 1], width = row.label_ids.length;
  const within = position - row.token_start, countCell = within < width;
  const column = within % width, labelId = row.label_ids[column];
  const value = countCell ? String(row.counts[column]) : core.dictionary[labelId].value;
  if (countCell) work.dictionary_lookups += 1;
  const id = countCell ? valueMap.get(value) : labelId;
  work.stored_rows_read += 1;
  work.column_records_read += 1;
  work.origin_records_read += 1;
  return {
    position, value_id: id, value, step: row.step,
    kind: countCell ? "count" : "label", column,
    counted_label: countCell ? core.dictionary[labelId].value : null
  };
}
function requestedPage(args, required, optional, label) {
  shape(args, required.concat(["offset", "limit"]), optional || [], label);
  integer(args.offset, 0, LIMITS.written_tokens, label + ".offset");
  integer(args.limit, 1, LIMITS.page_size, label + ".limit");
}
function attachSession(record, opening) {
  if (record.sessions.length >= LIMITS.sessions) fail("SESSION_LIMIT", "no additional session can be opened");
  let totalUsage = measureJson(record), coreUsage = measureJson(record.core);
  const session = {
    session_id: record.sessions.length,
    opening,
    counters: { advances: 0, ...zeros(QUERY_KEYS) },
    events: []
  };
  totalUsage = usageAfter(totalUsage, null, null, measureJson(session), 2);
  record.sessions.push(session);
  let valueMap = makeValueMap(record.core);

  function reserve(extraValues, extraChars) {
    if (session.events.length >= LIMITS.events_per_session) fail("EVENT_LIMIT", "open a new bounded session before more retained calls");
    if (totalUsage.values + extraValues > LIMITS.export_values ||
        totalUsage.string_key_chars + extraChars > LIMITS.export_string_key_chars) {
      fail("EXPORT_LIMIT", "conservative complete-record reservation does not fit; current record is unchanged");
    }
  }
  function commit(method, args, payload, work, newCore, copiedCoreValues, preparedMap) {
    const reference = { session_id: session.session_id, event_id: session.events.length };
    const outcome = { ...payload, reference, query_work: work };
    if (copiedCoreValues !== null) outcome.preparation_core_copy_values = copiedCoreValues;
    const eventCopy = copyJson({ event_id: reference.event_id, method, args, outcome });
    const caller = copyJson(eventCopy.value.outcome).value;
    const nextCoreUsage = newCore ? measureJson(newCore) : coreUsage;
    const nextUsage = usageAfter(totalUsage, newCore ? coreUsage : null,
      newCore ? nextCoreUsage : null, eventCopy.usage, 4);
    const nextCounters = { ...session.counters };
    addCounters(nextCounters, work);
    if (method === "advance") nextCounters.advances += 1;
    if (newCore) {
      record.core = newCore;
      coreUsage = nextCoreUsage;
      valueMap = preparedMap || makeValueMap(newCore);
    }
    session.events.push(eventCopy.value);
    session.counters = nextCounters;
    totalUsage = nextUsage;
    return caller;
  }
  function query(method, supplied, operation) {
    reserve(10000, 100000);
    const args = copyJson(supplied).value, work = zeros(QUERY_KEYS);
    work.calls = 1;
    const payload = operation(record.core, args, work);
    return commit(method, args, payload, work, null, null);
  }
  const api = {
    advance(supplied) {
      const args = copyJson(supplied).value;
      shape(args, ["tables", "max_new_tokens"], [], "advance");
      integer(args.tables, 1, LIMITS.tables_per_advance, "advance.tables");
      integer(args.max_new_tokens, 1, LIMITS.written_tokens, "advance.max_new_tokens");
      reserve(10000 + 32 * args.max_new_tokens + 64 * args.tables,
        100000 + 160 * args.max_new_tokens + 512 * args.tables);
      const copied = copyJson(record.core), next = copied.value, map = makeValueMap(next);
      const from = next.frontier.tables, initialTokens = next.frontier.token_count;
      const beforeWork = { ...next.work };
      let status = "requested_tables_complete", stoppedWidth = null;
      while (next.frontier.tables - from < args.tables) {
        const width = next.frontier.sorted_ids.length;
        if (next.frontier.tables >= LIMITS.total_tables) { status = "total_table_limit"; stoppedWidth = width; break; }
        if (next.frontier.token_count + 2 * width > LIMITS.written_tokens) { status = "total_token_limit"; stoppedWidth = width; break; }
        if (next.frontier.token_count - initialTokens + 2 * width > args.max_new_tokens) {
          status = "new_token_budget"; stoppedWidth = width; break;
        }
        constructTable(next, map);
      }
      const constructionWork = Object.fromEntries(CORE_KEYS.map(key => [key, next.work[key] - beforeWork[key]]));
      const payload = {
        status, from_table: from, through_table: next.frontier.tables,
        tables_added: next.frontier.tables - from,
        tokens_added: next.frontier.token_count - initialTokens,
        total_tokens: next.frontier.token_count, distinct_values: next.dictionary.length,
        positive_prefix: next.frontier.positive_prefix,
        first_missing: String(next.frontier.positive_prefix + 1),
        maximum_written: next.dictionary[next.frontier.sorted_ids[next.frontier.sorted_ids.length - 1]].value,
        next_table_width: next.frontier.sorted_ids.length,
        stopped_before_width: stoppedWidth, construction_work: constructionWork,
        preparation_dictionary_entries_indexed: record.core.dictionary.length,
        new_dictionary_entries_inserted: next.dictionary.length - record.core.dictionary.length
      };
      return commit("advance", args, payload, zeros(QUERY_KEYS), next, copied.usage.values, map);
    },
    pageTables(supplied) {
      return query("pageTables", supplied, (core, args, work) => {
        requestedPage(args, [], [], "pageTables");
        const end = Math.min(core.tables.length, args.offset + args.limit), rows = [];
        for (let i = args.offset; i < end; i += 1) {
          rows.push(tableSummary(core, core.tables[i]));
          work.stored_rows_read += 1;
        }
        work.returned_records = rows.length;
        return { offset: args.offset, total: core.tables.length, next_offset: end < core.tables.length ? end : null, tables: rows };
      });
    },
    pageTable(supplied) {
      return query("pageTable", supplied, (core, args, work) => {
        requestedPage(args, ["step"], [], "pageTable");
        integer(args.step, 1, core.frontier.tables, "pageTable.step");
        const row = core.tables[args.step - 1], width = row.label_ids.length;
        const end = Math.min(width, args.offset + args.limit), columns = [];
        work.stored_rows_read += 1;
        for (let i = args.offset; i < end; i += 1) {
          const id = row.label_ids[i];
          columns.push({
            column: i, value_id: id, label: core.dictionary[id].value,
            count: row.counts[i], count_position: row.token_start + i,
            label_position: row.token_start + width + i
          });
          work.column_records_read += 1;
        }
        work.returned_records = columns.length;
        return { step: args.step, width, offset: args.offset, next_offset: end < width ? end : null, columns };
      });
    },
    countAt(supplied) {
      return query("countAt", supplied, (core, args, work) => {
        shape(args, ["value", "through_table"], [], "countAt");
        const value = decimal(args.value, "countAt.value");
        integer(args.through_table, 0, core.frontier.tables, "countAt.through_table");
        work.dictionary_lookups += 1;
        const id = valueMap.get(value);
        let count = 0, basis = "closed_absence";
        if (id !== undefined) {
          if (args.through_table === core.frontier.tables) {
            count = core.frontier.counts_by_id[id];
            basis = "saved_final_frequency";
          } else {
            const row = core.tables[args.through_table];
            work.stored_rows_read += 1;
            const column = findColumn(core, row, value, work);
            if (column >= 0) {
              count = row.counts[column];
              work.column_records_read += 1;
              basis = "next_table_saved_input";
            }
          }
        }
        work.returned_records = 1;
        return { value, through_table: args.through_table, count, basis };
      });
    },
    firstAppearance(supplied) {
      return query("firstAppearance", supplied, (core, args, work) => {
        shape(args, ["value"], [], "firstAppearance");
        const value = decimal(args.value, "firstAppearance.value");
        work.dictionary_lookups += 1;
        const id = valueMap.get(value);
        if (id === undefined) return { value, status: "absent_in_recorded_prefix", through_table: core.frontier.tables };
        const entry = core.dictionary[id];
        work.origin_records_read += 1;
        work.returned_records = 1;
        return { value, status: "present", total_occurrences: core.occurrences[id].length,
          location: tokenLocation(core, valueMap, entry.first_position, work) };
      });
    },
    locateToken(supplied) {
      return query("locateToken", supplied, (core, args, work) => {
        shape(args, ["position"], [], "locateToken");
        integer(args.position, 0, core.frontier.token_count - 1, "locateToken.position");
        work.returned_records = 1;
        return tokenLocation(core, valueMap, args.position, work);
      });
    }
  };


  Object.assign(api, {
    rankOccurrences(supplied) {
      return query("rankOccurrences", supplied, (core, args, work) => {
        shape(args, ["value", "before_position"], [], "rankOccurrences");
        const value = decimal(args.value, "rankOccurrences.value");
        integer(args.before_position, 0, core.frontier.token_count, "rankOccurrences.before_position");
        work.dictionary_lookups += 1;
        const id = valueMap.get(value), positions = id === undefined ? [] : core.occurrences[id];
        const rank = lowerBound(positions, args.before_position, work);
        work.returned_records = 1;
        return { value, before_position: args.before_position, rank, total_occurrences: positions.length,
          convention: "count of positions strictly below before_position" };
      });
    },
    selectOccurrence(supplied) {
      return query("selectOccurrence", supplied, (core, args, work) => {
        shape(args, ["value", "rank"], [], "selectOccurrence");
        const value = decimal(args.value, "selectOccurrence.value");
        integer(args.rank, 0, LIMITS.written_tokens, "selectOccurrence.rank");
        work.dictionary_lookups += 1;
        const id = valueMap.get(value), positions = id === undefined ? [] : core.occurrences[id];
        if (args.rank >= positions.length) return { value, rank: args.rank, status: "outside_recorded_occurrences", total_occurrences: positions.length };
        work.occurrence_positions_read += 1;
        work.returned_records = 1;
        return { value, rank: args.rank, status: "present", total_occurrences: positions.length,
          location: tokenLocation(core, valueMap, positions[args.rank], work) };
      });
    },
    pageOccurrences(supplied) {
      return query("pageOccurrences", supplied, (core, args, work) => {
        requestedPage(args, ["value"], [], "pageOccurrences");
        const value = decimal(args.value, "pageOccurrences.value");
        work.dictionary_lookups += 1;
        const id = valueMap.get(value), positions = id === undefined ? [] : core.occurrences[id];
        const end = Math.min(positions.length, args.offset + args.limit), items = [];
        for (let i = args.offset; i < end; i += 1) {
          work.occurrence_positions_read += 1;
          items.push({ rank: i, ...tokenLocation(core, valueMap, positions[i], work) });
        }
        work.returned_records = items.length;
        return { value, offset: args.offset, total: positions.length,
          next_offset: end < positions.length ? end : null, occurrences: items };
      });
    },
    pageValues(supplied) {
      return query("pageValues", supplied, (core, args, work) => {
        requestedPage(args, [], [], "pageValues");
        const ids = core.frontier.sorted_ids;
        const end = Math.min(ids.length, args.offset + args.limit), items = [];
        for (let i = args.offset; i < end; i += 1) {
          const id = ids[i], entry = core.dictionary[id], positions = core.occurrences[id];
          items.push({
            rank: i, value_id: id, value: entry.value,
            count: core.frontier.counts_by_id[id],
            first_position: entry.first_position, first_table: entry.first_step,
            last_position: positions[positions.length - 1]
          });
          work.origin_records_read += 1;
          work.occurrence_positions_read += 1;
        }
        work.returned_records = items.length;
        return { offset: args.offset, total: ids.length,
          next_offset: end < ids.length ? end : null, values: items };
      });
    },
    pageNewValues(supplied) {
      return query("pageNewValues", supplied, (core, args, work) => {
        requestedPage(args, ["step"], [], "pageNewValues");
        integer(args.step, 1, core.frontier.tables, "pageNewValues.step");
        const ids = core.tables[args.step - 1].new_value_ids;
        const end = Math.min(ids.length, args.offset + args.limit), items = [];
        work.stored_rows_read += 1;
        for (let i = args.offset; i < end; i += 1) {
          const id = ids[i], entry = core.dictionary[id];
          items.push({ discovery_rank_in_table: i, value_id: id, value: entry.value,
            location: tokenLocation(core, valueMap, entry.first_position, work) });
          work.origin_records_read += 1;
        }
        work.returned_records = items.length;
        return { step: args.step, offset: args.offset, total: ids.length,
          next_offset: end < ids.length ? end : null, values: items };
      });
    },
    summary() {
      return copyJson({ ...smallSummary(record, session), export_usage: totalUsage }).value;
    },
    snapshot() { return copyJson(record).value; }
  });
  return Object.freeze(api);
}
function createHardCount(supplied) {
  const args = copyJson(supplied).value;
  shape(args, ["source_id", "seed"], [], "createHardCount");
  if (typeof args.source_id !== "string" || args.source_id.length === 0 ||
      args.source_id.length > LIMITS.source_id_chars) fail("INPUT", "source_id is a bounded nonempty string");
  const seed = inputSeed(args.seed);
  const core = createCore(seed);
  const record = { schema: SCHEMA, source_id: args.source_id, core, sessions: [] };
  return attachSession(record, { mode: "construct", structural_work: null });
}
function openHardCount(supplied) {
  const copied = copyJson(supplied), record = copied.value;
  const work = validateRecord(record);
  work.copied_json_values = copied.usage.values;
  work.copied_string_key_chars = copied.usage.string_key_chars;
  return attachSession(record, { mode: "resume", structural_work: work });
}


const OPEN_KEYS = Object.freeze([
  "dictionary_entries", "occurrence_positions", "final_frequency_bindings",
  "seed_cell_bindings", "table_records", "column_pairs", "support_links",
  "new_value_links", "order_comparisons", "positive_prefix_checks",
  "forward_token_bindings", "historical_events", "historical_work_fields",
  "copied_json_values", "copied_string_key_chars", "recurrence_replays"
]);
function requireArray(value, label) {
  if (!Array.isArray(value)) fail("RECORD", label + " must be an array");
}
function validateRecord(record) {
  shape(record, ["schema", "source_id", "core", "sessions"], [], "record");
  if (record.schema !== SCHEMA) fail("RECORD", "unsupported schema");
  if (typeof record.source_id !== "string" || record.source_id.length === 0 ||
      record.source_id.length > LIMITS.source_id_chars) fail("RECORD", "invalid source_id");
  const core = record.core, work = zeros(OPEN_KEYS);
  shape(core, ["input", "dictionary", "seed_token_ids", "tables", "occurrences", "frontier", "work"], [], "core");
  const seed = inputSeed(core.input);
  if (seed.kind === "written_counting") {
    for (const value of core.input.counts.concat(core.input.labels)) storedDecimal(value, "stored initial cell");
  }
  for (const key of ["dictionary", "seed_token_ids", "tables", "occurrences"]) requireArray(core[key], "core." + key);
  const f = core.frontier;
  shape(f, ["tables", "token_count", "sorted_ids", "counts_by_id", "positive_prefix"], [], "frontier");
  integer(f.tables, 0, LIMITS.total_tables, "frontier.tables");
  integer(f.token_count, 1, LIMITS.written_tokens, "frontier.token_count");
  requireArray(f.sorted_ids, "frontier.sorted_ids");
  requireArray(f.counts_by_id, "frontier.counts_by_id");
  const n = core.dictionary.length, total = f.token_count;
  integer(n, 1, total, "dictionary size");
  if (core.tables.length !== f.tables || core.occurrences.length !== n ||
      f.counts_by_id.length !== n || f.sorted_ids.length !== n) fail("RECORD", "core dimensions disagree");
  integer(f.positive_prefix, 0, n, "frontier.positive_prefix");
  counterObject(core.work, CORE_KEYS, "core.work");
  const valueMap = new Map();
  let previousFirst = -1, positionCount = 0;
  for (let id = 0; id < n; id += 1) {
    const entry = core.dictionary[id];
    shape(entry, ["value", "first_position", "first_step"], [], "dictionary entry");
    const value = storedDecimal(entry.value, "dictionary value");
    if (valueMap.has(value)) fail("RECORD", "dictionary values must be distinct");
    valueMap.set(value, id);
    integer(entry.first_position, 0, total - 1, "first_position");
    integer(entry.first_step, 0, f.tables, "first_step");
    if (entry.first_position <= previousFirst) fail("RECORD", "dictionary order must be first-appearance order");
    previousFirst = entry.first_position;
    const positions = core.occurrences[id];
    requireArray(positions, "occurrence list");
    if (positions.length === 0 || positions[0] !== entry.first_position) fail("RECORD", "first occurrence binding is invalid");
    let previous = -1;
    for (const position of positions) {
      integer(position, 0, total - 1, "occurrence position");
      if (position <= previous) fail("RECORD", "occurrence lists must be strictly increasing");
      previous = position;
      work.occurrence_positions += 1;
    }
    integer(f.counts_by_id[id], 1, total, "final frequency");
    if (f.counts_by_id[id] !== positions.length) fail("RECORD", "final frequency must match its occurrence-list length");
    positionCount += positions.length;
    work.final_frequency_bindings += 1;
    work.dictionary_entries += 1;
  }
  if (positionCount !== total) fail("RECORD", "occurrence lists do not have the full stream cardinality");
  const finalIds = new Set();
  let lastValue = null;
  for (const id of f.sorted_ids) {
    integer(id, 0, n - 1, "sorted value id");
    if (finalIds.has(id)) fail("RECORD", "sorted_ids is not a permutation");
    finalIds.add(id);
    const value = core.dictionary[id].value;
    if (lastValue !== null) {
      work.order_comparisons += 1;
      if (cmpDecimal(lastValue, value) >= 0) fail("RECORD", "sorted_ids must be in increasing numerical order");
    }
    lastValue = value;
  }
  const cells = physicalSeed(seed);
  if (core.seed_token_ids.length !== cells.length) fail("RECORD", "seed has the wrong number of physical cells");
  const active = new Set();
  let maximumId = null;
  for (let i = 0; i < cells.length; i += 1) {
    const id = integer(core.seed_token_ids[i], 0, n - 1, "seed token id");
    if (core.dictionary[id].value !== cells[i] || core.dictionary[id].first_step !== 0) fail("RECORD", "initial cell binding is invalid");
    active.add(id);
    if (maximumId === null) maximumId = id;
    else {
      work.order_comparisons += 1;
      if (cmpDecimal(core.dictionary[maximumId].value, core.dictionary[id].value) < 0) maximumId = id;
    }
    work.seed_cell_bindings += 1;
  }
  let positivePrefix = 0;
  function advancePrefix(through) {
    for (;;) {
      work.positive_prefix_checks += 1;
      const id = valueMap.get(String(positivePrefix + 1));
      if (id === undefined || core.dictionary[id].first_step > through) return;
      positivePrefix += 1;
    }
  }
  advancePrefix(0);
  let start = cells.length, columnPairs = 0;


  for (let index = 0; index < core.tables.length; index += 1) {
    const row = core.tables[index], step = index + 1;
    shape(row, ["step", "token_start", "token_end", "label_ids", "counts", "new_value_ids",
      "distinct_after", "positive_prefix_after", "maximum_value_id_after"], [], "table");
    requireArray(row.label_ids, "table.label_ids");
    requireArray(row.counts, "table.counts");
    requireArray(row.new_value_ids, "table.new_value_ids");
    const width = row.label_ids.length;
    if (row.step !== step || row.token_start !== start || row.token_end !== start + 2 * width ||
        width !== active.size || row.counts.length !== width || row.token_end > total) {
      fail("RECORD", "table shape or complete boundary is invalid");
    }
    const seen = new Set();
    let previousValue = null;
    for (let column = 0; column < width; column += 1) {
      const id = integer(row.label_ids[column], 0, n - 1, "table label id");
      if (!active.has(id) || seen.has(id)) fail("RECORD", "table must list each previously written value once");
      seen.add(id);
      const value = core.dictionary[id].value;
      if (previousValue !== null) {
        work.order_comparisons += 1;
        if (cmpDecimal(previousValue, value) >= 0) fail("RECORD", "table columns must have increasing numerical labels");
      }
      previousValue = value;
      integer(row.counts[column], 1, total, "stored count cell");
      work.column_pairs += 1;
      work.support_links += 1;
    }
    let priorNewPosition = -1;
    for (const id of row.new_value_ids) {
      integer(id, 0, n - 1, "new value id");
      const entry = core.dictionary[id];
      if (active.has(id) || entry.first_step !== step || entry.first_position < start ||
          entry.first_position >= start + width || entry.first_position <= priorNewPosition) {
        fail("RECORD", "new-value discovery binding is invalid");
      }
      priorNewPosition = entry.first_position;
      active.add(id);
      work.order_comparisons += 1;
      if (cmpDecimal(core.dictionary[maximumId].value, entry.value) < 0) maximumId = id;
      work.new_value_links += 1;
    }
    advancePrefix(step);
    if (row.distinct_after !== active.size || row.positive_prefix_after !== positivePrefix ||
        row.maximum_value_id_after !== maximumId) fail("RECORD", "table support summary is invalid");
    start = row.token_end;
    columnPairs += width;
    work.table_records += 1;
  }
  if (start !== total || active.size !== n || positivePrefix !== f.positive_prefix) {
    fail("RECORD", "completed frontier does not match all saved tables");
  }
  // Bind every serialized token to its saved occurrence list. Do not compare a
  // table's count cells with prefix frequencies: that would replay the recurrence.
  const cursors = Array(n).fill(0);
  function bind(id, position, step) {
    if (core.occurrences[id][cursors[id]] !== position) fail("RECORD", "forward stream / occurrence index mismatch");
    if (cursors[id] === 0 && core.dictionary[id].first_step !== step) fail("RECORD", "first-table binding mismatch");
    cursors[id] += 1;
    work.forward_token_bindings += 1;
  }
  for (let i = 0; i < core.seed_token_ids.length; i += 1) bind(core.seed_token_ids[i], i, 0);
  for (const row of core.tables) {
    const width = row.label_ids.length;
    for (let column = 0; column < width; column += 1) {
      const id = valueMap.get(String(row.counts[column]));
      if (id === undefined) fail("RECORD", "a count cell is missing from the dictionary");
      bind(id, row.token_start + column, row.step);
    }
    for (let column = 0; column < width; column += 1) bind(row.label_ids[column], row.token_start + width + column, row.step);
  }
  for (let id = 0; id < n; id += 1) {
    if (cursors[id] !== core.occurrences[id].length) fail("RECORD", "an occurrence list has unbound positions");
  }
  const requiredWork = {
    seed_tokens_written: cells.length, tables_constructed: core.tables.length,
    frozen_count_reads: columnPairs, value_map_lookups: cells.length + columnPairs,
    occurrence_positions_appended: total, frequency_increments: total,
    dictionary_insertions: n, row_cells_saved: 2 * columnPairs
  };
  for (const key of Object.keys(requiredWork)) {
    if (core.work[key] !== requiredWork[key]) fail("RECORD", "construction work cardinality mismatch: " + key);
  }
  requireArray(record.sessions, "sessions");
  integer(record.sessions.length, 1, LIMITS.sessions, "session count");
  for (let i = 0; i < record.sessions.length; i += 1) {
    const session = record.sessions[i];
    shape(session, ["session_id", "opening", "counters", "events"], [], "session");
    if (session.session_id !== i) fail("RECORD", "session ids must be contiguous");
    shape(session.opening, ["mode", "structural_work"], [], "session.opening");
    if (session.opening.mode !== (i === 0 ? "construct" : "resume")) fail("RECORD", "invalid session opening mode");
    if (i === 0) {
      if (session.opening.structural_work !== null) fail("RECORD", "constructor has no structural reopening work");
    } else counterObject(session.opening.structural_work, OPEN_KEYS, "historical opening work");
    counterObject(session.counters, ["advances"].concat(QUERY_KEYS), "session.counters");
    requireArray(session.events, "session.events");
    integer(session.events.length, 0, LIMITS.events_per_session, "event count");
    const expectedCounters = { advances: 0, ...zeros(QUERY_KEYS) };
    for (let j = 0; j < session.events.length; j += 1) {
      const event = session.events[j];
      shape(event, ["event_id", "method", "args", "outcome"], [], "event");
      if (event.event_id !== j || !METHODS.has(event.method) || !plain(event.args) || !plain(event.outcome)) {
        fail("RECORD", "invalid historical event envelope");
      }
      shape(event.outcome.reference, ["session_id", "event_id"], [], "event reference");
      if (event.outcome.reference.session_id !== i || event.outcome.reference.event_id !== j) {
        fail("RECORD", "historical event reference mismatch");
      }
      counterObject(event.outcome.query_work, QUERY_KEYS, "historical query work");
      if (event.method === "advance") {
        expectedCounters.advances += 1;
        for (const key of QUERY_KEYS) if (event.outcome.query_work[key] !== 0) fail("RECORD", "advance is not a saved-reader query");
      } else if (event.outcome.query_work.calls !== 1) fail("RECORD", "historical query call count mismatch");
      addCounters(expectedCounters, event.outcome.query_work);
      work.historical_events += 1;
      work.historical_work_fields += QUERY_KEYS.length;
    }
    for (const key of Object.keys(expectedCounters)) {
      if (session.counters[key] !== expectedCounters[key]) fail("RECORD", "session work sum mismatch");
    }
  }
  return work;
}
module.exports = Object.freeze({ SCHEMA, LIMITS, createHardCount, openHardCount });
