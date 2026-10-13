'use strict';

// Extend a provenance-established nonzero Hankel prefix without recomputing it.
const INPUT_SCHEMA = 'commons.ppl036.morphic_hankel_index/v1';
const SCHEMA = 'commons.ppl036.morphic_hankel_extension/v1';
const ARCHIVE_SCHEMA = 'commons.ppl036.morphic_hankel_extension_archive/v1';
const BLOCK_SCHEMA = 'commons.ppl036.morphic_hankel_order_block/v1';
const MORPHISM = Object.freeze({'1': '12', '2': '23', '3': '14', '4': '32'});
const LIMITS = Object.freeze({
  max_order: 64, max_carriers: 4096, max_determinant_rows: 32768,
  max_shift_digits: 1024, max_determinant_digits: 512,
  max_page: 64, max_queries: 32, orders_per_block: 16,
  max_snapshot_nodes: 1000000, max_snapshot_chars: 16000000,
});

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(label + ' must be a plain object');
  }
  return value;
}
function fields(value, allowed, required) {
  object(value, 'options');
  if (Object.keys(value).some(key => !allowed.includes(key))
      || required.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new TypeError('Expected fields: ' + allowed.join(', '));
  }
}
function integer(value, label, low, high) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(label + ' must be an integer in [' + low + ', ' + high + ']');
  }
  return value;
}
function array(value, label, low, high) {
  if (!Array.isArray(value) || value.length < low || value.length > high) {
    throw new RangeError(label + ' has an unsupported length');
  }
  return value;
}
function decimal(value, label) {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)
      || value.length > LIMITS.max_shift_digits) {
    throw new TypeError(label + ' must be a bounded canonical nonnegative decimal');
  }
  return value;
}
function determinant(value, label, requireNonzero) {
  if (typeof value !== 'string' || !/^(0|-?[1-9][0-9]*)$/.test(value)
      || value.replace(/^-/, '').length > LIMITS.max_determinant_digits
      || (requireNonzero && value === '0')) {
    throw new TypeError(label + ' must be a bounded recorded determinant' + (requireNonzero ? ' different from zero' : ''));
  }
  return BigInt(value);
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function boundedClone(value) {
  let nodes = 0, chars = 0;
  function copy(item, depth) {
    if (++nodes > LIMITS.max_snapshot_nodes || depth > 24) throw new RangeError('Snapshot structure cap exceeded');
    if (item === null || typeof item === 'boolean') return item;
    if (typeof item === 'string') {
      chars += item.length;
      if (chars > LIMITS.max_snapshot_chars) throw new RangeError('Snapshot character cap exceeded');
      return item;
    }
    if (typeof item === 'number' && Number.isSafeInteger(item)) return item;
    if (Array.isArray(item)) return item.map(value => copy(value, depth + 1));
    object(item, 'snapshot member');
    const result = {};
    for (const key of Object.keys(item)) {
      chars += key.length;
      if (chars > LIMITS.max_snapshot_chars) throw new RangeError('Snapshot character cap exceeded');
      Object.defineProperty(result, key, {
        value: copy(item[key], depth + 1), enumerable: true, configurable: true, writable: true,
      });
    }
    return result;
  }
  return copy(value, 0);
}

function loadBase(input) {
  const saved = boundedClone(input);
  object(saved, 'base index');
  if (saved.schema !== INPUT_SCHEMA || saved.seed !== '1') throw new TypeError('Unsupported base schema or seed');
  object(saved.morphism, 'base morphism');
  if (Object.keys(saved.morphism).length !== 4
      || Object.keys(MORPHISM).some(letter => saved.morphism[letter] !== MORPHISM[letter])) {
    throw new Error('The exact four-letter morphism is required');
  }
  const summary = object(saved.summary, 'base summary');
  const baseOrder = integer(summary.completed_through_order, 'completed base order', 1, LIMITS.max_order);
  const firstZero = object(saved.first_zero, 'base first-zero record');
  if (summary.status !== 'complete' || summary.requested_max_order !== baseOrder
      || summary.all_shifts_nonzero_through_order !== baseOrder
      || firstZero.status !== 'none_in_completed_orders'
      || firstZero.completed_through_order !== baseOrder || firstZero.requested_max_order !== baseOrder) {
    throw new Error('A declared complete nonzero base prefix is required');
  }
  const language = object(saved.language, 'base language');
  const blockSize = integer(language.block_size, 'base block size', 1, 128);
  const depth = integer(language.substitution_depth, 'base substitution depth', 0, 7);
  if (language.complete !== true || language.max_factor_length !== 2 * baseOrder - 1
      || blockSize !== 2 ** depth || blockSize < language.max_factor_length - 1) {
    throw new Error('Base factor-language bounds are inconsistent');
  }
  const pairRows = array(language.adjacent_pairs, 'base adjacent pairs', 1, 16);
  const pairs = pairRows.map(row => {
    object(row, 'pair record');
    if (typeof row.pair !== 'string' || !/^[1-4]{2}$/.test(row.pair)) throw new Error('Invalid base pair token');
    decimal(row.known_shift, 'base pair occurrence');
    return row;
  });
  if (new Set(pairs.map(row => row.pair)).size !== pairs.length) throw new Error('Duplicate base pair');
  const images = {};
  for (const row of array(language.letter_expansions, 'base letter images', 4, 4)) {
    object(row, 'letter image');
    if (!Object.prototype.hasOwnProperty.call(MORPHISM, row.letter)
        || Object.prototype.hasOwnProperty.call(images, row.letter)
        || typeof row.image !== 'string' || row.image.length !== blockSize || !/^[1-4]+$/.test(row.image)) {
      throw new Error('Invalid or duplicate recorded letter image');
    }
    images[row.letter] = row.image;
  }
  const carriers = array(language.carriers, 'base carriers', 1, LIMITS.max_carriers);
  for (let i = 0; i < carriers.length; i++) {
    const row = array(carriers[i], 'base carrier', 4, 4);
    if (typeof row[0] !== 'string' || row[0].length !== 2 * baseOrder - 1 || !/^[1-4]+$/.test(row[0])
        || (i > 0 && carriers[i - 1][0] >= row[0])) throw new Error('Invalid base carrier word order');
    decimal(row[1], 'base carrier occurrence');
    integer(row[2], 'base carrier pair', 0, pairs.length - 1);
    integer(row[3], 'base carrier offset', 0, 2 * blockSize - row[0].length);
  }
  const orders = array(saved.orders, 'base orders', baseOrder, baseOrder);
  const levels = [null];
  let rowCount = 0;
  for (let n = 1; n <= baseOrder; n++) {
    const order = object(orders[n - 1], 'base order');
    if (order.order !== n || order.factor_length !== 2 * n - 1 || order.complete !== true) {
      throw new Error('Invalid complete base-order header');
    }
    const rows = array(order.rows, 'base determinant rows', 1, carriers.length);
    rowCount += rows.length;
    if (rowCount > LIMITS.max_determinant_rows) throw new RangeError('Base determinant row cap exceeded');
    const stats = object(order.summary, 'base order summary');
    if (stats.factor_count !== rows.length || stats.zero !== 0) throw new Error('Base order count/zero declaration is inconsistent');
    integer(stats.positive, 'base positive count', 0, rows.length);
    integer(stats.negative, 'base negative count', 0, rows.length);
    if (stats.positive + stats.negative !== rows.length) throw new Error('Base sign counts are inconsistent');
    integer(stats.largest_absolute_determinant_digits, 'base determinant size summary', 1, LIMITS.max_determinant_digits);
    const byWord = new Map(), values = [];
    let previous = null;
    for (let r = 0; r < rows.length; r++) {
      const row = array(rows[r], 'base determinant row', 6, 6);
      integer(row[0], 'base row carrier', 0, carriers.length - 1);
      const word = carriers[row[0]][0].slice(0, 2 * n - 1);
      if (previous !== null && previous >= word) throw new Error('Base factors must be strictly ordered and unique');
      previous = word;
      values.push(determinant(row[1], 'base determinant', true));
      if (n === 1) {
        if (row.slice(2).some(value => value !== null)) throw new Error('Invalid order-one minor references');
      } else {
        for (let c = 2; c <= 4; c++) integer(row[c], 'base minor reference', 0, levels[n - 1].rows.length - 1);
        if (n === 2) {
          if (row[5] !== -1) throw new Error('Invalid empty determinant marker');
        } else integer(row[5], 'base inner reference', 0, levels[n - 2].rows.length - 1);
      }
      byWord.set(word, r);
    }
    levels.push({order: n, rows, values, byWord, summary: stats});
  }
  return {saved, baseOrder, blockSize, depth, pairs, images, carriers, levels, rowCount};
}

function extendMorphicHankelIndex(input, options) {
  fields(options, ['maxOrder'], ['maxOrder']);
  const base = loadBase(input);
  if (base.baseOrder === LIMITS.max_order) throw new RangeError('The base already reaches the order cap');
  const target = integer(options.maxOrder, 'maxOrder', base.baseOrder + 1, LIMITS.max_order);
  const stats = {
    source_pair_records_loaded: base.pairs.length, source_pair_closure_steps: 0,
    source_letter_images_loaded: 4, source_image_characters_loaded: 4 * base.blockSize,
    source_block_reconstruction_steps: 0, block_extension_steps: 0,
    block_concatenations: 0, new_block_characters: 0,
    candidate_windows: 0, distinct_max_factors: 0,
    source_determinants_loaded: base.rowCount, source_determinants_recomputed: 0,
    reused_rows_remapped: 0, carrier_search_comparisons: 0,
    new_prefix_candidates: 0, new_determinant_evaluations: 0,
    condensation_products: 0, condensation_subtractions: 0,
    exact_division_checks: 0, integer_divisions: 0,
  };
  const result = {
    schema: SCHEMA, status: 'in_progress', stage: 'extend_blocks', error: null,
    source: {
      schema: INPUT_SCHEMA, base_max_order: base.baseOrder, determinant_rows: base.rowCount,
      block_size: base.blockSize, substitution_depth: base.depth,
      loaded_letter_images: clone(base.saved.language.letter_expansions),
      provenance: 'Caller-established source identity and mathematical claims; loading is structural only.',
    },
    extension_stats: stats,
    index: {
      schema: INPUT_SCHEMA, morphism: clone(MORPHISM), seed: '1',
      limits: {
        max_order: LIMITS.max_order, max_carriers: LIMITS.max_carriers,
        max_determinant_rows: LIMITS.max_determinant_rows,
        max_shift_digits: LIMITS.max_shift_digits, max_page: LIMITS.max_page,
        max_queries: LIMITS.max_queries,
      },
      summary: {
        schema: INPUT_SCHEMA, status: 'incomplete', requested_max_order: target,
        completed_through_order: 0, all_shifts_nonzero_through_order: 0,
        max_factor_length: 2 * target - 1, factor_language_complete: false,
        max_factor_count: 0, stopped: null, retained_error: null, orders: [], extension_stats: stats,
      },
      language: {complete: false},
      determinant_columns: ['carrier', 'determinant', 'left', 'center', 'right', 'inner'],
      determinant_reference_rules: {
        left_center_right: 'Row indices in order n-1, at factor offsets 0,1,2.',
        inner: 'Row index in order n-2 at offset 2; -1 denotes empty determinant 1 at n=2.',
        order_one: 'All four minor columns are null.',
        factor: 'Prefix of carrier of length 2*n-1.',
      },
      source_row_reuse: {
        through_order: base.baseOrder,
        rule: 'Same order and row index; determinant and four minor columns preserved. Carrier witness index remapped.',
      },
      orders: [], queries: [], first_zero: null,
    },
  };
  const index = result.index, summary = index.summary;
  try {
    let images = base.images, blockSize = base.blockSize, depth = base.depth;
    const length = 2 * target - 1;
    while (blockSize < length - 1) {
      const next = {};
      for (const letter of Object.keys(MORPHISM)) {
        const pair = MORPHISM[letter];
        next[letter] = images[pair[0]] + images[pair[1]];
        stats.block_concatenations++;
        stats.new_block_characters += next[letter].length;
      }
      images = next; blockSize *= 2; depth++;
      stats.block_extension_steps++;
    }
    result.stage = 'build_longer_carriers';
    const candidates = new Map(), coverageWords = [];
    for (let pairIndex = 0; pairIndex < base.pairs.length; pairIndex++) {
      const pair = base.pairs[pairIndex];
      const word = images[pair.pair[0]] + images[pair.pair[1]];
      const covered = [];
      for (let offset = 0; offset <= word.length - length; offset++) {
        const factor = word.slice(offset, offset + length);
        stats.candidate_windows++;
        covered.push(factor);
        if (!candidates.has(factor)) {
          if (candidates.size >= LIMITS.max_carriers) throw new RangeError('New carrier cap reached');
          const shift = (BigInt(blockSize) * BigInt(pair.known_shift) + BigInt(offset)).toString();
          decimal(shift, 'new carrier occurrence');
          candidates.set(factor, [factor, shift, pairIndex, offset]);
        }
      }
      coverageWords.push(covered);
    }
    const carriers = [...candidates.values()].sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
    const carrierMap = new Map(carriers.map((row, i) => [row[0], i]));
    stats.distinct_max_factors = carriers.length;
    index.language = {
      complete: true, max_factor_length: length, block_size: blockSize,
      substitution_depth: depth,
      block_coverage_inequality: 'block_size >= max_factor_length - 1',
      reachable_letters: clone(base.saved.language.reachable_letters),
      adjacent_pairs: clone(base.pairs),
      letter_expansions: Object.keys(MORPHISM).map(letter => ({letter, image: images[letter]})),
      carrier_columns: ['factor', 'known_shift', 'pair_index', 'offset'],
      carriers,
      pair_coverage: coverageWords.map((words, pair_index) => ({
        pair_index, carrier_indices: words.map(word => carrierMap.get(word)),
      })),
      witness_scope: 'A known occurrence inherited from a recorded adjacent-pair witness; not necessarily the earliest.',
      completeness_basis: 'Retained complete pair closure and its occurrence proof, followed by the block coverage argument.',
    };
    summary.factor_language_complete = true;
    summary.max_factor_count = carriers.length;
    result.stage = 'remap_retained_rows';
    function firstCarrier(prefix) {
      let low = 0, high = carriers.length;
      while (low < high) {
        const middle = Math.floor((low + high) / 2);
        stats.carrier_search_comparisons++;
        if (carriers[middle][0] < prefix) low = middle + 1;
        else high = middle;
      }
      if (low === carriers.length || !carriers[low][0].startsWith(prefix)) {
        throw new Error('A retained factor has no longer carrier extension');
      }
      return low;
    }
    const levels = base.levels;
    for (let n = 1; n <= base.baseOrder; n++) {
      const level = levels[n];
      const rows = [];
      for (const [word, rowIndex] of level.byWord) {
        const old = level.rows[rowIndex];
        rows.push([firstCarrier(word), old[1], old[2], old[3], old[4], old[5]]);
        stats.reused_rows_remapped++;
      }
      level.rows = rows;
      const order = {order: n, factor_length: 2 * n - 1, complete: true, summary: clone(level.summary), rows};
      index.orders.push(order);
      summary.orders.push({...clone(level.summary), order: n, factor_length: 2 * n - 1, complete: true});
      summary.completed_through_order = n;
      summary.all_shifts_nonzero_through_order = n;
    }

    let retainedRows = base.rowCount;
    for (let n = base.baseOrder + 1; n <= target; n++) {
      result.stage = 'compute_order_' + n;
      const factorLength = 2 * n - 1, factors = [];
      let previous = null;
      for (let carrier = 0; carrier < carriers.length; carrier++) {
        const word = carriers[carrier][0].slice(0, factorLength);
        stats.new_prefix_candidates++;
        if (word !== previous) {
          factors.push({word, carrier});
          previous = word;
        }
      }
      if (retainedRows + factors.length > LIMITS.max_determinant_rows) {
        throw new RangeError('Extended determinant row cap reached before the next order');
      }
      const orderStats = {factor_count: 0, positive: 0, negative: 0, zero: 0, largest_absolute_determinant_digits: 0};
      const rows = [], values = [], byWord = new Map();
      const order = {order: n, factor_length: factorLength, complete: false, summary: orderStats, rows};
      index.orders.push(order);
      levels[n] = {order: n, rows, values, byWord, summary: orderStats};
      function reference(level, word, label) {
        const row = level.byWord.get(word);
        if (row === undefined) throw new Error('Missing ' + label + ' minor factor at order ' + n);
        return row;
      }
      for (let r = 0; r < factors.length; r++) {
        const {word, carrier} = factors[r];
        const prior = levels[n - 1];
        const left = reference(prior, word.slice(0, factorLength - 2), 'left');
        const center = reference(prior, word.slice(1, factorLength - 1), 'center');
        const right = reference(prior, word.slice(2), 'right');
        const inner = n === 2 ? -1 : reference(levels[n - 2], word.slice(2, factorLength - 2), 'inner');
        const denominator = n === 2 ? 1n : levels[n - 2].values[inner];
        if (denominator === 0n) throw new Error('A zero inner determinant blocks this recurrence');
        const numerator = prior.values[left] * prior.values[right] - prior.values[center] * prior.values[center];
        stats.condensation_products += 2;
        stats.condensation_subtractions++;
        stats.exact_division_checks++;
        if (numerator % denominator !== 0n) throw new Error('Nonexact condensation division');
        const value = numerator / denominator;
        stats.integer_divisions++;
        stats.new_determinant_evaluations++;
        const text = value.toString(), digits = text.replace(/^-/, '').length;
        if (digits > LIMITS.max_determinant_digits) throw new RangeError('New determinant digit cap reached');
        rows.push([carrier, text, left, center, right, inner]);
        values.push(value);
        byWord.set(word, r);
        orderStats.factor_count = rows.length;
        orderStats.largest_absolute_determinant_digits = Math.max(orderStats.largest_absolute_determinant_digits, digits);
        if (value > 0n) orderStats.positive++;
        else if (value < 0n) orderStats.negative++;
        else {
          orderStats.zero++;
          if (index.first_zero === null) {
            const witness = carriers[carrier];
            index.first_zero = {
              status: 'found', order: n, row: r, factor: word, determinant: '0',
              known_occurrence: {
                shift: witness[1], carrier, pair_index: witness[2],
                offset: witness[3], substitution_depth: depth,
              },
              minor_rows: {
                order_minus_one: {left, center, right},
                order_minus_two: inner,
              },
              minimality: 'Smallest order over all nonnegative shifts; the occurrence shift is a witness, not a minimum.',
            };
          }
        }
      }
      order.complete = true;
      retainedRows += rows.length;
      summary.completed_through_order = n;
      summary.orders.push({...clone(orderStats), order: n, factor_length: factorLength, complete: true});
      if (orderStats.zero > 0) {
        result.status = 'counterexample_found';
        summary.status = 'counterexample_found';
        summary.stopped = 'first_zero_row_completed';
        break;
      }
      summary.all_shifts_nonzero_through_order = n;
    }
    if (result.status === 'in_progress') {
      result.status = 'complete';
      summary.status = 'complete';
    }
    result.stage = 'complete';
  } catch (error) {
    result.status = 'incomplete';
    result.error = {stage: result.stage, message: String(error.message ?? error)};
    summary.status = 'incomplete';
    summary.stopped = 'retained_error';
    summary.retained_error = clone(result.error);
  }
  if (index.first_zero === null) {
    index.first_zero = {
      status: 'none_in_completed_orders',
      completed_through_order: summary.completed_through_order,
      requested_max_order: target,
    };
  }
  return clone(result);
}

function packMorphicHankelExtension(input) {
  const result = boundedClone(input);
  object(result, 'extension result');
  if (result.schema !== SCHEMA) throw new TypeError('Unsupported extension result schema');
  const index = object(result.index, 'extended index');
  if (index.schema !== INPUT_SCHEMA || index.language?.complete !== true) {
    throw new Error('Packing requires a complete longer factor language');
  }
  const baseOrder = integer(result.source?.base_max_order, 'source base order', 1, LIMITS.max_order - 1);
  const target = integer(index.summary?.requested_max_order, 'requested order', baseOrder + 1, LIMITS.max_order);
  const allOrders = array(index.orders, 'extended orders', baseOrder, target);
  for (let i = 0; i < allOrders.length; i++) {
    if (allOrders[i]?.order !== i + 1 || (i < baseOrder && allOrders[i].complete !== true)) {
      throw new Error('Packing requires an ordered complete retained base');
    }
  }
  const blocks = [], manifest = [];
  for (let start = baseOrder; start < allOrders.length; start += LIMITS.orders_per_block) {
    const orders = allOrders.slice(start, start + LIMITS.orders_per_block);
    const first = orders[0].order, last = orders[orders.length - 1].order;
    const filename = 'orders' + first + '_' + Math.min(first + LIMITS.orders_per_block - 1, target) + '.json';
    blocks.push({
      schema: BLOCK_SCHEMA, filename, base_max_order: baseOrder,
      first_order: first, last_order: last, orders,
    });
    manifest.push({filename, first_order: first, last_order: last, order_count: orders.length});
  }
  const archive = {
    schema: ARCHIVE_SCHEMA, extension_status: result.status, extension_stage: result.stage,
    extension_error: result.error, source: result.source, extension_stats: result.extension_stats,
    index: {...index, orders: allOrders.slice(0, baseOrder)}, blocks: manifest,
    assembly: 'All listed blocks are required; archive.index alone is not the complete index.',
  };
  return {archive, blocks};
}

function assembleMorphicHankelExtensionArchive(input, inputBlocks) {
  const archive = boundedClone(input);
  const blocks = boundedClone(inputBlocks);
  object(archive, 'archive');
  if (archive.schema !== ARCHIVE_SCHEMA) throw new TypeError('Unsupported archive schema');
  const index = object(archive.index, 'archive index');
  if (index.schema !== INPUT_SCHEMA || index.language?.complete !== true) {
    throw new Error('Invalid archive index header');
  }
  const baseOrder = integer(archive.source?.base_max_order, 'archive base order', 1, LIMITS.max_order - 1);
  const target = integer(index.summary?.requested_max_order, 'archive target order', baseOrder + 1, LIMITS.max_order);
  array(index.orders, 'archive base orders', baseOrder, baseOrder);
  const manifest = array(archive.blocks, 'block manifest', 0, Math.ceil((target - baseOrder) / LIMITS.orders_per_block));
  array(blocks, 'order blocks', manifest.length, manifest.length);
  for (let i = 0; i < index.orders.length; i++) {
    if (index.orders[i]?.order !== i + 1 || index.orders[i].complete !== true) {
      throw new Error('Archive base is not an ordered complete prefix');
    }
  }
  let nextOrder = baseOrder + 1;
  const filenames = new Set();
  for (let i = 0; i < blocks.length; i++) {
    const part = object(blocks[i], 'order block'), wanted = object(manifest[i], 'manifest entry');
    if (part.schema !== BLOCK_SCHEMA || part.base_max_order !== baseOrder
        || typeof part.filename !== 'string' || part.filename !== wanted.filename
        || filenames.has(part.filename)) throw new Error('Block schema, source or filename mismatch');
    filenames.add(part.filename);
    const count = integer(wanted.order_count, 'manifest order count', 1, LIMITS.orders_per_block);
    if (wanted.first_order !== nextOrder || wanted.last_order !== nextOrder + count - 1
        || part.first_order !== wanted.first_order || part.last_order !== wanted.last_order
        || part.last_order > target) throw new Error('Block order range mismatch or gap');
    const orders = array(part.orders, 'block orders', count, count);
    for (const order of orders) {
      if (order?.order !== nextOrder) throw new Error('Block order records are not contiguous');
      index.orders.push(order);
      nextOrder++;
    }
  }
  const completed = integer(index.summary?.completed_through_order, 'completed archive order', baseOrder, target);
  if (index.orders.length < completed || index.orders.length > Math.min(completed + 1, target)) {
    throw new Error('Assembled records do not match the declared complete prefix');
  }
  for (let i = 0; i < completed; i++) {
    if (index.orders[i].complete !== true) throw new Error('A declared complete order is incomplete');
  }
  if (index.summary.status === 'complete' && (completed !== target || index.orders.length !== target)) {
    throw new Error('A declared complete archive omits requested orders');
  }
  // Determinants, factors and proofs are not recomputed. The saved reader performs
  // its own bounded structural checks when this assembled index is opened.
  return index;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    extendMorphicHankelIndex, packMorphicHankelExtension,
    assembleMorphicHankelExtensionArchive,
    SCHEMA, INPUT_SCHEMA, ARCHIVE_SCHEMA, BLOCK_SCHEMA, LIMITS,
  };
}
