'use strict';

// Fixed morphism from Shallit's Open Problem 9.
// HANKEL_INDEX_API.md proves the finite-language coverage and determinant rule.
const SCHEMA = 'commons.ppl036.morphic_hankel_index/v1';
const MORPHISM = Object.freeze({'1': '12', '2': '23', '3': '14', '4': '32'});
const LIMITS = Object.freeze({
  max_order: 64, max_carriers: 4096, max_determinant_rows: 32768,
  max_shift_digits: 1024, max_page: 64, max_queries: 32,
});

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function objectWithFields(value, allowed, required) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError('Expected an object with fields: ' + allowed.join(', '));
  }
  return value;
}

function integer(value, label, lower, upper) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)
      || value < lower || value > upper) {
    throw new RangeError(label + ' must be an integer in [' + lower + ', ' + upper + ']');
  }
  return value;
}

function shiftText(value) {
  const result = typeof value === 'bigint' ? value.toString() : value;
  if (typeof result !== 'string' || !/^(0|[1-9][0-9]*)$/.test(result)
      || result.length > LIMITS.max_shift_digits) {
    throw new RangeError('shift must be a nonnegative canonical decimal string or BigInt within the digit cap');
  }
  return result;
}

function createMorphicHankelIndex(input) {
  objectWithFields(input, ['maxOrder'], ['maxOrder']);
  const requestedOrder = integer(input.maxOrder, 'maxOrder', 1, LIMITS.max_order);
  const maxLength = 2 * requestedOrder - 1;
  let blockSize = 1;
  let depth = 0;
  while (blockSize < maxLength - 1) {
    blockSize *= 2;
    depth++;
  }
  const letters = [];
  const pairs = [];
  let expansions = [];
  let carriers = [];
  let pairCoverage = [];
  const levels = [null];
  const determinantValues = [null];
  const wordMaps = [new Map([['', 0]])];
  const queries = [];
  let status = 'building';
  let completedOrder = 0;
  let nonzeroThrough = 0;
  let languageComplete = false;
  let stopped = null;
  let retainedError = null;
  const stats = {
    letter_states: 0, pair_states: 0, pair_boundary_images: 0,
    substitution_characters_built: 0, candidate_windows: 0,
    distinct_max_factors: 0, prefix_candidates: 0,
    determinant_evaluations: 0, complete_factor_rows: 0,
    condensation_steps: 0, integer_products: 0,
    exact_division_checks: 0, integer_divisions: 0,
    lookup_queries: 0, factor_pages: 0,
    symbol_evaluations: 0, binary_transition_steps: 0,
    query_determinant_recomputations: 0,
  };

  function summary() {
    return clone({
      schema: SCHEMA, status, requested_max_order: requestedOrder,
      completed_through_order: completedOrder,
      all_shifts_nonzero_through_order: nonzeroThrough,
      max_factor_length: maxLength, factor_language_complete: languageComplete,
      max_factor_count: carriers.length, stopped, retained_error: retainedError,
      orders: levels.slice(1).map(level => ({
        order: level.order, factor_length: level.factor_length,
        complete: level.complete, ...level.summary,
      })),
      stats,
    });
  }

  try {
    // Every new letter is reached by a binary-position transition.
    const byLetter = new Map();
    const seed = {letter: '1', known_shift: '0', kind: 'seed',
      parent_letter: null, digit: null};
    letters.push(seed);
    byLetter.set('1', seed);
    for (let head = 0; head < letters.length; head++) {
      const parent = letters[head];
      const image = MORPHISM[parent.letter];
      for (let digit = 0; digit < 2; digit++) {
        const letter = image[digit];
        if (byLetter.has(letter)) continue;
        const record = {
          letter, known_shift: (2n * BigInt(parent.known_shift) + BigInt(digit)).toString(),
          kind: 'binary_position', parent_letter: parent.letter, digit,
        };
        byLetter.set(letter, record);
        letters.push(record);
      }
    }
    stats.letter_states = letters.length;

    // All adjacent pairs are internal images or images across a pair boundary.
    const byPair = new Map();
    for (const letter of letters) {
      const word = MORPHISM[letter.letter];
      if (byPair.has(word)) continue;
      const record = {
        pair: word, known_shift: (2n * BigInt(letter.known_shift)).toString(),
        kind: 'letter_internal', source_letter: letter.letter, source_pair_index: null,
      };
      byPair.set(word, pairs.length);
      pairs.push(record);
    }
    for (let head = 0; head < pairs.length; head++) {
      const parent = pairs[head];
      const word = MORPHISM[parent.pair[0]][1] + MORPHISM[parent.pair[1]][0];
      stats.pair_boundary_images++;
      if (byPair.has(word)) continue;
      const record = {
        pair: word, known_shift: (2n * BigInt(parent.known_shift) + 1n).toString(),
        kind: 'pair_boundary', source_letter: null, source_pair_index: head,
      };
      byPair.set(word, pairs.length);
      pairs.push(record);
    }
    stats.pair_states = pairs.length;

    let images = Object.fromEntries(letters.map(row => [row.letter, row.letter]));
    for (let level = 0; level < depth; level++) {
      const next = {};
      for (const letter of letters) {
        let value = '';
        for (const symbol of images[letter.letter]) value += MORPHISM[symbol];
        next[letter.letter] = value;
        stats.substitution_characters_built += value.length;
      }
      images = next;
    }
    expansions = letters.map(row => ({letter: row.letter, image: images[row.letter]}));

    const byWord = new Map();
    const candidates = [];
    for (let pairIndex = 0; pairIndex < pairs.length; pairIndex++) {
      const pair = pairs[pairIndex];
      const image = images[pair.pair[0]] + images[pair.pair[1]];
      const coveredWords = [];
      for (let offset = 0; offset + maxLength <= image.length; offset++) {
        const word = image.slice(offset, offset + maxLength);
        const witness = BigInt(pair.known_shift) * BigInt(blockSize) + BigInt(offset);
        coveredWords.push(word);
        stats.candidate_windows++;
        const previous = byWord.get(word);
        if (!previous) {
          if (byWord.size >= LIMITS.max_carriers) {
            throw new RangeError('Maximum-factor carrier cap reached');
          }
          byWord.set(word, {
            word, known_shift: witness.toString(), pair_index: pairIndex, offset,
          });
        } else if (witness < BigInt(previous.known_shift)) {
          byWord.set(word, {
            word, known_shift: witness.toString(), pair_index: pairIndex, offset,
          });
        }
      }
      candidates.push({pair_index: pairIndex, words: coveredWords});
    }
    carriers = [...byWord.values()].sort((a, b) => a.word < b.word ? -1 : a.word > b.word ? 1 : 0);
    const carrierIds = new Map(carriers.map((row, index) => [row.word, index]));
    pairCoverage = candidates.map(row => ({
      pair_index: row.pair_index,
      // Position in this array is the offset in the expanded pair.
      carrier_indices: row.words.map(word => carrierIds.get(word)),
    }));
    stats.distinct_max_factors = carriers.length;
    languageComplete = true;

    // Every shorter factor extends rightwards to a maximum-length factor.
    for (let order = 1; order <= requestedOrder; order++) {
      const length = 2 * order - 1;
      const prefixes = new Map();
      for (let carrier = 0; carrier < carriers.length; carrier++) {
        const word = carriers[carrier].word.slice(0, length);
        stats.prefix_candidates++;
        if (!prefixes.has(word)) prefixes.set(word, carrier);
      }
      const words = [...prefixes.keys()].sort();
      if (stats.determinant_evaluations + words.length > LIMITS.max_determinant_rows) {
        status = 'incomplete';
        stopped = {kind: 'determinant_row_cap', next_order: order,
          next_order_rows: words.length, cap: LIMITS.max_determinant_rows};
        break;
      }
      const map = new Map(words.map((word, index) => [word, index]));
      const level = {
        order, factor_length: length, complete: false, rows: [],
        summary: {factor_count: words.length, positive: 0, negative: 0, zero: 0,
          largest_absolute_determinant_digits: 0},
      };
      levels.push(level);
      determinantValues.push([]);
      wordMaps.push(map);

      for (let rowIndex = 0; rowIndex < words.length; rowIndex++) {
        const word = words[rowIndex];
        let determinant;
        let left = null;
        let center = null;
        let right = null;
        let inner = null;
        if (order === 1) {
          determinant = BigInt(word);
        } else {
          left = wordMaps[order - 1].get(word.slice(0, length - 2));
          center = wordMaps[order - 1].get(word.slice(1, length - 1));
          right = wordMaps[order - 1].get(word.slice(2));
          inner = order === 2 ? -1 : wordMaps[order - 2].get(word.slice(2, length - 2));
          if (left === undefined || center === undefined || right === undefined || inner === undefined) {
            throw new Error('A required minor is missing from the complete shorter-factor language');
          }
          const previous = determinantValues[order - 1];
          const numerator = previous[left] * previous[right] - previous[center] * previous[center];
          stats.condensation_steps++;
          stats.integer_products += 2;
          if (order === 2) {
            determinant = numerator; // The empty determinant is 1.
          } else {
            const denominator = determinantValues[order - 2][inner];
            if (denominator === 0n) {
              throw new Error('Zero denominator encountered beyond the declared first-zero stopping rule');
            }
            stats.exact_division_checks++;
            if (numerator % denominator !== 0n) {
              throw new Error('The integer condensation quotient is not exact');
            }
            determinant = numerator / denominator;
            stats.integer_divisions++;
          }
        }
        level.rows.push([prefixes.get(word), determinant.toString(), left, center, right, inner]);
        determinantValues[order].push(determinant);
        stats.determinant_evaluations++;
        const sign = determinant > 0n ? 'positive' : determinant < 0n ? 'negative' : 'zero';
        level.summary[sign]++;
        const digits = (determinant < 0n ? -determinant : determinant).toString().length;
        level.summary.largest_absolute_determinant_digits = Math.max(
          level.summary.largest_absolute_determinant_digits, digits);
      }
      level.complete = true;
      completedOrder = order;
      stats.complete_factor_rows += level.rows.length;
      if (level.summary.zero > 0) {
        status = 'counterexample_found';
        stopped = {kind: 'complete_first_zero_order', order,
          zero_factor_count: level.summary.zero};
        break;
      }
      nonzeroThrough = order;
    }
    if (status === 'building') status = 'complete';
  } catch (error) {
    status = 'incomplete';
    retainedError = {name: String(error.name), message: String(error.message ?? error)};
    stopped = {kind: 'compile_error', completed_through_order: completedOrder,
      partial_order: levels.length > completedOrder + 1 ? levels.length - 1 : null};
  }

  function completeLevel(order) {
    integer(order, 'order', 1, requestedOrder);
    const level = levels[order];
    if (!level || !level.complete || order > completedOrder) {
      throw new RangeError('This order has no complete determinant row; inspect summary()');
    }
    return level;
  }

  function factorRecord(order, rowIndex) {
    const row = levels[order].rows[rowIndex];
    const carrier = carriers[row[0]];
    return {
      row: rowIndex, factor: carrier.word.slice(0, 2 * order - 1),
      determinant: row[1],
      known_occurrence: {
        shift: carrier.known_shift, carrier: row[0], pair_index: carrier.pair_index,
        offset: carrier.offset, substitution_depth: depth,
      },
      minor_rows: order === 1 ? null : {
        order_minus_one: {left: row[2], center: row[3], right: row[4]},
        order_minus_two: row[5],
      },
    };
  }

  function reserveQuery(operation) {
    if (queries.length >= LIMITS.max_queries) {
      throw new RangeError('Retained query cap reached; export the existing snapshot');
    }
    const row = {id: queries.length + 1, operation, status: 'in_progress'};
    queries.push(row);
    return row;
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

  function at(query) {
    objectWithFields(query, ['shift', 'order'], ['shift', 'order']);
    const startText = shiftText(query.shift);
    const level = completeLevel(query.order);
    const record = reserveQuery('at');
    Object.assign(record, {shift: startText, order: query.order});
    stats.lookup_queries++;
    try {
      const start = BigInt(startText);
      let word = '';
      for (let offset = 0; offset < level.factor_length; offset++) {
        word += symbolAt(start + BigInt(offset));
      }
      record.factor = word;
      const rowIndex = wordMaps[query.order].get(word);
      if (rowIndex === undefined) {
        throw new Error('The directly evaluated factor is missing from the complete factor language');
      }
      Object.assign(record, {
        status: 'found', factor_row: rowIndex, determinant: level.rows[rowIndex][1],
        reused_determinant: true,
      });
      return clone(record);
    } catch (error) {
      record.status = 'incomplete';
      record.error = String(error.message ?? error);
      throw error;
    }
  }

  function factorPage(query) {
    objectWithFields(query, ['order', 'offset', 'limit'], ['order']);
    const level = completeLevel(query.order);
    const offset = integer(query.offset === undefined ? 0 : query.offset, 'offset', 0, level.rows.length);
    const limit = integer(query.limit === undefined ? 16 : query.limit, 'limit', 1, LIMITS.max_page);
    const record = reserveQuery('factor_page');
    stats.factor_pages++;
    const end = Math.min(level.rows.length, offset + limit);
    const rows = [];
    for (let index = offset; index < end; index++) rows.push(factorRecord(query.order, index));
    Object.assign(record, {
      status: 'complete', order: query.order, offset, limit,
      returned_rows: rows.length, next_offset: end < level.rows.length ? end : null,
      total_factors: level.rows.length, row_indices: rows.map(row => row.row),
    });
    return clone({...record, rows});
  }

  function firstZero() {
    for (let order = 1; order <= completedOrder; order++) {
      if (levels[order].summary.zero === 0) continue;
      const rowIndex = levels[order].rows.findIndex(row => row[1] === '0');
      return clone({
        status: 'found', order, ...factorRecord(order, rowIndex),
        minimality: 'Smallest order over all nonnegative shifts; the occurrence shift is a witness, not a minimum.',
      });
    }
    return {status: 'none_in_completed_orders', completed_through_order: completedOrder,
      requested_max_order: requestedOrder};
  }

  function snapshot() {
    return clone({
      schema: SCHEMA, morphism: MORPHISM, seed: '1', limits: LIMITS,
      summary: summary(),
      language: {
        complete: languageComplete, max_factor_length: maxLength,
        block_size: blockSize, substitution_depth: depth,
        block_coverage_inequality: 'block_size >= max_factor_length - 1',
        reachable_letters: letters, adjacent_pairs: pairs, letter_expansions: expansions,
        carrier_columns: ['factor', 'known_shift', 'pair_index', 'offset'],
        carriers: carriers.map(row => [row.word, row.known_shift, row.pair_index, row.offset]),
        pair_coverage: pairCoverage,
        witness_scope: 'A proved occurrence; no earliest-occurrence claim.',
      },
      determinant_columns: ['carrier', 'determinant', 'left', 'center', 'right', 'inner'],
      determinant_reference_rules: {
        left_center_right: 'Row indices in order n-1, at factor offsets 0,1,2.',
        inner: 'Row index in order n-2 at offset 2; -1 denotes empty determinant 1 at n=2.',
        order_one: 'All four minor columns are null.',
        factor: 'Prefix of carrier of length 2*n-1.',
      },
      orders: levels.slice(1),
      queries, first_zero: firstZero(),
    });
  }

  return Object.freeze({
    schema: SCHEMA, requested_max_order: requestedOrder, summary, at, factorPage,
    firstZero, snapshot,
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {createMorphicHankelIndex, MORPHISM, LIMITS, SCHEMA};
}
