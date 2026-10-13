'use strict';

// Queries already recorded PPL036 determinant tables.
// Structural loading does not re-prove the source's mathematical claims.
const SCHEMA = 'commons.ppl036.morphic_hankel_reader/v1';
const INPUT_SCHEMA = 'commons.ppl036.morphic_hankel_index/v1';
const MORPHISM = Object.freeze({'1': '12', '2': '23', '3': '14', '4': '32'});
const LIMITS = Object.freeze({
  max_order: 64, max_carriers: 4096, max_rows: 32768,
  max_shift_digits: 1024, max_determinant_digits: 512,
  max_page: 64, max_queries: 32,
});

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}
function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}
function fields(value, allowed, required) {
  object(value, 'query');
  if (Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError('Expected query fields: ' + allowed.join(', '));
  }
}
function integer(value, label, lower, upper) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)
      || value < lower || value > upper) {
    throw new RangeError(label + ' must be an integer in [' + lower + ', ' + upper + ']');
  }
  return value;
}
function naturalText(value, label, allowBigInt) {
  const text = allowBigInt && typeof value === 'bigint' ? value.toString() : value;
  if (typeof text !== 'string' || !/^(0|[1-9][0-9]*)$/.test(text)
      || text.length > LIMITS.max_shift_digits) {
    throw new RangeError(label + ' must be a nonnegative canonical decimal within the digit cap');
  }
  return text;
}
function boundedArray(value, label, minimum, maximum) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    throw new RangeError(label + ' has an unsupported array length');
  }
  return value;
}

function openMorphicHankelReader(snapshot) {
  object(snapshot, 'snapshot');
  if (snapshot.schema !== INPUT_SCHEMA || snapshot.seed !== '1') {
    throw new TypeError('Unsupported source schema or seed');
  }
  object(snapshot.morphism, 'source morphism');
  if (Object.keys(snapshot.morphism).length !== 4
      || Object.keys(MORPHISM).some(key => snapshot.morphism[key] !== MORPHISM[key])) {
    throw new TypeError('The source must use the exact four-letter morphism');
  }
  const declared = object(snapshot.summary, 'source summary');
  const requested = integer(declared.requested_max_order, 'requested source order', 1, LIMITS.max_order);
  const completed = integer(declared.completed_through_order, 'completed source order', 1, requested);
  const nonzero = integer(declared.all_shifts_nonzero_through_order, 'declared nonzero bound', 0, completed);
  if (!['complete', 'counterexample_found', 'incomplete'].includes(declared.status)) {
    throw new TypeError('Unsupported declared source status');
  }
  if (declared.status === 'complete' && (completed !== requested || nonzero !== completed)) {
    throw new Error('The declared complete bounds are inconsistent');
  }
  if (declared.status === 'counterexample_found' && nonzero !== completed - 1) {
    throw new Error('The declared first-zero bounds are inconsistent');
  }
  const language = object(snapshot.language, 'source language');
  if (language.complete !== true) throw new Error('A complete source factor language is required');
  const maxLength = integer(language.max_factor_length, 'source factor length', 1, 2 * LIMITS.max_order - 1);
  const depth = integer(language.substitution_depth, 'source substitution depth', 0, 7);
  const blockSize = integer(language.block_size, 'source block size', 1, 128);
  if (maxLength !== 2 * requested - 1 || blockSize !== 2 ** depth || blockSize < maxLength - 1) {
    throw new Error('The source factor-length/block configuration is inconsistent');
  }
  const pairRows = boundedArray(language.adjacent_pairs, 'adjacent pairs', 1, 16);
  const pairs = pairRows.map(row => {
    object(row, 'pair row');
    if (typeof row.pair !== 'string' || !/^[1-4]{2}$/.test(row.pair)) {
      throw new TypeError('Invalid recorded adjacent-pair token');
    }
    return row.pair;
  });
  if (new Set(pairs).size !== pairs.length) throw new Error('Duplicate recorded pair token');

  const carrierRows = boundedArray(language.carriers, 'carriers', 1, LIMITS.max_carriers);
  const carriers = carrierRows.map((row, index) => {
    boundedArray(row, 'carrier row', 4, 4);
    if (typeof row[0] !== 'string' || row[0].length !== maxLength || !/^[1-4]+$/.test(row[0])) {
      throw new TypeError('Invalid recorded carrier word');
    }
    if (index > 0 && carrierRows[index - 1][0] >= row[0]) {
      throw new Error('Carrier words must be strictly lexicographically ordered');
    }
    return [
      row[0], naturalText(row[1], 'recorded occurrence', false),
      integer(row[2], 'carrier pair index', 0, pairs.length - 1),
      integer(row[3], 'carrier offset', 0, 2 * blockSize - maxLength),
    ];
  });

  const sourceOrders = boundedArray(snapshot.orders, 'source orders', completed, LIMITS.max_order);
  const levels = [null];
  let copiedRows = 0;
  for (let order = 1; order <= completed; order++) {
    const original = object(sourceOrders[order - 1], 'source order');
    if (original.order !== order || original.factor_length !== 2 * order - 1 || original.complete !== true) {
      throw new Error('A declared completed order has an inconsistent header');
    }
    const rows = boundedArray(original.rows, 'determinant rows', 1, carriers.length);
    copiedRows += rows.length;
    if (copiedRows > LIMITS.max_rows) throw new RangeError('Total source row cap exceeded');
    const copied = rows.map(row => {
      boundedArray(row, 'determinant row', 6, 6);
      for (const cell of row) {
        if (cell === null) continue;
        if (typeof cell === 'number' && Number.isSafeInteger(cell)) continue;
        if (typeof cell === 'string' && cell.length <= LIMITS.max_determinant_digits + 1) continue;
        throw new TypeError('Recorded row cells must be bounded primitive values');
      }
      return row.slice();
    });
    levels.push({order, factor_length: original.factor_length, rows: copied});
  }
  const sourceSummary = {
    schema: INPUT_SCHEMA, declared_status: declared.status,
    requested_max_order: requested, completed_through_order: completed,
    declared_all_shifts_nonzero_through_order: nonzero,
    source_orders_beyond_complete_prefix: sourceOrders.length - completed,
    max_factor_length: maxLength, carrier_count: carriers.length, copied_rows: copiedRows,
    validation: 'structural_only',
    mathematical_claims: 'Retained from the source; not re-proved by this reader.',
  };

  const indexes = new Map();
  const windows = new Map();
  const queries = [];
  const accessed = new Map();
  const stats = {
    carriers_copied: carriers.length, determinant_rows_copied: copiedRows,
    orders_indexed: 0, rows_indexed: 0, order_cache_hits: 0,
    windows_created: 0, windows_extended: 0, window_cache_hits: 0,
    symbol_evaluations: 0, binary_transition_steps: 0,
    record_reads: 0, unique_records_read: 0,
    compiler_calls: 0, determinant_evaluations: 0, factor_language_expansions: 0,
  };

  function sourceLevel(order) {
    integer(order, 'order', 1, completed);
    return levels[order];
  }

  function indexOrder(order) {
    if (indexes.has(order)) {
      stats.order_cache_hits++;
      return indexes.get(order);
    }
    const level = levels[order];
    const lookup = new Map();
    let previousWord = null;
    for (let rowIndex = 0; rowIndex < level.rows.length; rowIndex++) {
      const row = level.rows[rowIndex];
      integer(row[0], 'row carrier index', 0, carriers.length - 1);
      if (typeof row[1] !== 'string' || !/^(0|-?[1-9][0-9]*)$/.test(row[1])
          || row[1].replace(/^-/, '').length > LIMITS.max_determinant_digits) {
        throw new TypeError('Invalid recorded determinant decimal');
      }
      if (order === 1) {
        if (row.slice(2).some(value => value !== null)) {
          throw new Error('Order-one minor references must be null');
        }
      } else {
        for (let column = 2; column <= 4; column++) {
          integer(row[column], 'order-minus-one reference', 0, levels[order - 1].rows.length - 1);
        }
        if (order === 2) {
          if (row[5] !== -1) throw new Error('Order-two inner reference must be the empty determinant marker');
        } else {
          integer(row[5], 'order-minus-two reference', 0, levels[order - 2].rows.length - 1);
        }
      }
      const word = carriers[row[0]][0].slice(0, level.factor_length);
      if (previousWord !== null && previousWord >= word) {
        throw new Error('Recorded factors must be unique and lexicographically ordered');
      }
      previousWord = word;
      lookup.set(word, rowIndex);
    }
    indexes.set(order, lookup);
    stats.orders_indexed++;
    stats.rows_indexed += level.rows.length;
    return lookup;
  }

  function reserveQuery(operation) {
    if (queries.length >= LIMITS.max_queries) {
      throw new RangeError('Query cap reached; export the current reader snapshot');
    }
    const record = {id: queries.length + 1, operation, status: 'in_progress'};
    queries.push(record);
    return record;
  }

  function symbolAt(position) {
    let state = '1';
    for (const digit of position.toString(2)) {
      state = MORPHISM[state][digit === '0' ? 0 : 1];
      stats.binary_transition_steps++;
    }
    stats.symbol_evaluations++;
    return state;
  }

  function factorAt(shift, length) {
    const existing = windows.get(shift);
    if (existing && existing.length >= length) {
      stats.window_cache_hits++;
      return existing.slice(0, length);
    }
    let word = existing ?? '';
    if (existing === undefined) stats.windows_created++;
    else stats.windows_extended++;
    const start = BigInt(shift);
    for (let offset = word.length; offset < length; offset++) {
      word += symbolAt(start + BigInt(offset));
    }
    windows.set(shift, word);
    return word;
  }

  function recordAt(order, rowIndex) {
    const row = levels[order].rows[rowIndex];
    const carrier = carriers[row[0]];
    const key = order + ':' + rowIndex;
    stats.record_reads++;
    if (!accessed.has(key)) {
      accessed.set(key, {
        order, row: rowIndex, carrier: row[0],
        factor: carrier[0].slice(0, 2 * order - 1), determinant: row[1],
        source_occurrence: {
          shift: carrier[1], pair_index: carrier[2], pair: pairs[carrier[2]],
          offset: carrier[3], substitution_depth: depth,
        },
        minor_rows: order === 1 ? null : {
          order_minus_one: {left: row[2], center: row[3], right: row[4]},
          order_minus_two: row[5],
        },
      });
      stats.unique_records_read = accessed.size;
    }
    return accessed.get(key);
  }

  function at(query) {
    fields(query, ['shift', 'order'], ['shift', 'order']);
    const shift = naturalText(query.shift, 'shift', true);
    const level = sourceLevel(query.order);
    const record = reserveQuery('at');
    Object.assign(record, {shift, order: query.order});
    try {
      const lookup = indexOrder(query.order);
      const symbolsBefore = stats.symbol_evaluations;
      const word = factorAt(shift, level.factor_length);
      const rowIndex = lookup.get(word);
      record.factor = word;
      if (rowIndex === undefined) {
        throw new Error('Requested factor is absent from the recorded complete order');
      }
      const sourceRecord = recordAt(query.order, rowIndex);
      Object.assign(record, {
        status: 'found', factor_row: rowIndex, determinant: sourceRecord.determinant,
        reused_determinant: true, new_symbol_evaluations: stats.symbol_evaluations - symbolsBefore,
        source_record_key: query.order + ':' + rowIndex,
      });
      return clone({...record, source_record: sourceRecord});
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  function factorPage(query) {
    fields(query, ['order', 'offset', 'limit'], ['order']);
    const level = sourceLevel(query.order);
    const offset = integer(query.offset === undefined ? 0 : query.offset, 'offset', 0, level.rows.length);
    const limit = integer(query.limit === undefined ? 16 : query.limit, 'limit', 1, LIMITS.max_page);
    const record = reserveQuery('factor_page');
    Object.assign(record, {order: query.order, offset, limit});
    try {
      indexOrder(query.order);
      const end = Math.min(level.rows.length, offset + limit);
      const rows = [];
      for (let row = offset; row < end; row++) rows.push(recordAt(query.order, row));
      Object.assign(record, {
        status: 'complete', returned_rows: rows.length, total_factors: level.rows.length,
        next_offset: end < level.rows.length ? end : null,
        source_record_keys: rows.map(row => row.order + ':' + row.row),
      });
      return clone({...record, rows});
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  function summary() {
    return clone({
      schema: SCHEMA, source: sourceSummary, stats,
      indexed_orders: [...indexes.keys()].sort((a, b) => a - b),
      cached_shifts: windows.size, retained_queries: queries.length,
    });
  }

  function snapshotReader() {
    return clone({
      schema: SCHEMA, limits: LIMITS, summary: summary(), queries,
      accessed_source_records: [...accessed.values()],
      cached_windows: [...windows.entries()].map(([shift, factor]) => ({shift, factor})),
      source_data: 'Source table remains a separate artifact; this contains the new reader activity.',
      provenance: 'Schema and bounds do not authenticate a file or re-prove its mathematics.',
    });
  }

  return Object.freeze({schema: SCHEMA, at, factorPage, summary, snapshot: snapshotReader});
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {openMorphicHankelReader, LIMITS, SCHEMA, INPUT_SCHEMA};
}
