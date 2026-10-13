"use strict";

/*
 * Fixed-length binary primitive words. Classical Mobius count; rotations distinct.
 * No I/O, dependencies or claim about the full language's context-freeness.
 */
const PRIMITIVE_WORD_LIMITS = Object.freeze({
  max_length: 1024,
  max_snapshot_chars: 1000000,
  max_provenance_chars: 16384,
  max_page_words: 32
});
const SCHEMA = "commons.binary_primitive_word_index/v1";
function fail(s) { throw new RangeError(s); }
function small(x, name, lo, hi) {
  if (typeof x !== "number" || !Number.isSafeInteger(x) || x < lo || x > hi)
    fail(name + " is outside its integer bounds");
  return x;
}
function natural(x, name) {
  if (typeof x === "number") {
    if (!Number.isSafeInteger(x) || x < 0) fail(name + " must be exact and nonnegative");
    x = String(x);
  } else if (typeof x === "bigint") x = x.toString();
  if (typeof x !== "string" || x.length > 310 || !/^(0|[1-9][0-9]*)$/.test(x))
    fail(name + " must be a canonical natural integer with at most 310 digits");
  return BigInt(x);
}
function clone(x) { return JSON.parse(JSON.stringify(x)); }
function copyProvenance(x) {
  if (x === undefined) return null;
  const t = JSON.stringify(x);
  if (typeof t !== "string" || t.length > PRIMITIVE_WORD_LIMITS.max_provenance_chars)
    fail("provenance is too large");
  return JSON.parse(t);
}
function binary(s, max, exact) {
  if (typeof s !== "string" || s.length > max || !/^[01]*$/.test(s) ||
      (exact && s.length !== max)) fail("invalid binary word or prefix length");
  return s;
}
function mobiusFactor(k, work) {
  const original = k, factors = [];
  for (let p = 2; p * p <= k; p++) {
    work.factor_trial_divisions++;
    if (k % p !== 0) continue;
    let exponent = 0;
    do { k /= p; exponent++; work.factor_exact_divisions++; } while (k % p === 0);
    factors.push({prime:p, exponent});
  }
  if (k > 1) factors.push({prime:k, exponent:1});
  return {quotient:original, factors,
    mu:factors.some(f => f.exponent > 1) ? 0 : (factors.length % 2 ? -1 : 1)};
}
function compilePrimitiveWords(options) {
  if (!options || typeof options !== "object") fail("options required");
  const n = small(options.length, "length", 1, PRIMITIVE_WORD_LIMITS.max_length);
  const work = {compiler_calls:1, divisor_candidates:0, divisor_rows:0,
    factor_trial_divisions:0, factor_exact_divisions:0, power_doublings:0,
    total_terms:0, enumerated_binary_words:0};
  const divisors = [];
  for (let d = 1; d <= n; d++) {
    work.divisor_candidates++;
    if (n % d === 0) {
      divisors.push({period:d, ...mobiusFactor(n / d, work)});
      work.divisor_rows++;
    }
  }
  const powers = ["1"];
  let p = 1n;
  for (let i = 1; i <= n; i++) {
    p *= 2n; powers.push(p.toString()); work.power_doublings++;
  }
  let total = 0n;
  const totalLedger = divisors.map(row => {
    const term = BigInt(row.mu) * BigInt(powers[row.period]);
    total += term; work.total_terms++;
    return {period:row.period, mu:row.mu, completions:powers[row.period],
      signed_term:term.toString()};
  });
  const snapshot = {
    schema:SCHEMA, length:n, alphabet:["0","1"],
    conventions:{nonempty:true, lexicographic:"0<1", rank_base:0,
      rotations_identified:false, proper_power_exponent_minimum:2},
    divisors, powers_of_two:powers, primitive_total:total.toString(),
    composite_total:(p-total).toString(), total_ledger:totalLedger,
    provenance:copyProvenance(options.provenance)
  };
  const text = JSON.stringify(snapshot);
  if (text.length > PRIMITIVE_WORD_LIMITS.max_snapshot_chars) fail("snapshot size cap");
  return {status:"EXACT_INDEX", snapshot, work, snapshot_chars:text.length};
}
function openRetainedPrimitiveWords(value) {
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  if (typeof raw !== "string" || raw.length > PRIMITIVE_WORD_LIMITS.max_snapshot_chars)
    fail("snapshot size cap");
  const s = JSON.parse(raw);
  if (!s || s.schema !== SCHEMA) fail("snapshot schema");
  const n = small(s.length, "length", 1, PRIMITIVE_WORD_LIMITS.max_length);
  if (JSON.stringify(s.alphabet) !== '["0","1"]' ||
      !s.conventions || s.conventions.nonempty !== true ||
      s.conventions.lexicographic !== "0<1" || s.conventions.rank_base !== 0 ||
      s.conventions.rotations_identified !== false ||
      s.conventions.proper_power_exponent_minimum !== 2) fail("snapshot conventions");
  if (!Array.isArray(s.powers_of_two) || s.powers_of_two.length !== n + 1)
    fail("power table length");
  const stats = {saved_integer_fields:0, saved_divisor_rows:0, queries:0,
    prefix_queries:0, membership_queries:0, rank_queries:0, selection_queries:0,
    page_queries:0, character_appends:0, compatibility_tests:0,
    state_terms_evaluated:0, period_character_tests:0,
    selected_words_created:0, page_words_returned:0,
    compiler_calls:0, power_doublings:0, factorizations:0,
    enumerated_binary_words:0};
  function savedNat(x, name) {
    if (typeof x !== "string") fail(name + " must be a saved decimal string");
    stats.saved_integer_fields++;
    return natural(x, name);
  }
  const powers = s.powers_of_two.map((x,i) => savedNat(x, "power " + i));
  if (powers[0] !== 1n) fail("power zero");
  if (!Array.isArray(s.divisors) || !s.divisors.length || s.divisors.length > n)
    fail("divisor table shape");
  let last = 0;
  const rows = s.divisors.map(row => {
    const d = small(row.period, "period", 1, n);
    if (d <= last || n % d !== 0 || row.quotient !== n / d ||
        ![-1,0,1].includes(row.mu) || !Array.isArray(row.factors)) fail("divisor row");
    last = d;
    for (const f of row.factors) {
      small(f.prime, "factor", 2, n);
      small(f.exponent, "exponent", 1, 10);
    }
    stats.saved_divisor_rows++;
    return {period:d, mu:row.mu};
  });
  if (rows[0].period !== 1 || last !== n) fail("divisor endpoints");
  const total = savedNat(s.primitive_total, "total");
  const composite = savedNat(s.composite_total, "composite total");
  if (total + composite !== powers[n]) fail("saved total partition");
  // No factor, Mobius, power recurrence, divisor completeness or ledger proof replay.
  copyProvenance(s.provenance);
  function zeroState() {
    return {prefix:"", compatible:rows.map(() => true), count:total};
  }
  function move(state, bit) {
    const length = state.prefix.length, nextLength = length + 1;
    if (nextLength > n) fail("prefix exceeds length");
    const active = new Array(rows.length);
    let count = 0n;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i], d = row.period;
      let ok = state.compatible[i];
      if (ok && length >= d) {
        stats.compatibility_tests++;
        ok = state.prefix[length-d] === bit;
      }
      active[i] = ok;
      if (ok) {
        count += BigInt(row.mu) * powers[Math.max(0,d-nextLength)];
        stats.state_terms_evaluated++;
      }
    }
    if (count < 0n) fail("negative prefix count: untrusted saved arithmetic");
    stats.character_appends++;
    return {prefix:state.prefix+bit, compatible:active, count};
  }
  function stateFor(prefix) {
    binary(prefix,n,false);
    let state = zeroState();
    for (const bit of prefix) state = move(state,bit);
    return state;
  }
  function prefixResult(prefix) {
    const state = stateFor(prefix), ledger = [];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i], free = Math.max(0,row.period-prefix.length);
      const c = state.compatible[i] ? powers[free] : 0n;
      let conflict = null;
      if (!state.compatible[i]) {
        for (let j = row.period; j < prefix.length; j++) {
          stats.period_character_tests++;
          if (prefix[j] !== prefix[j-row.period]) {
            conflict = {position:j, previous_position:j-row.period,
              symbol:prefix[j], previous_symbol:prefix[j-row.period]}; break;
          }
        }
      }
      ledger.push({period:row.period, mu:row.mu, compatible:state.compatible[i],
        free_positions:free, completions:c.toString(),
        signed_term:(BigInt(row.mu)*c).toString(), first_conflict:conflict});
    }
    return {prefix, length:prefix.length, primitive_completions:state.count.toString(),
      all_completions:powers[n-prefix.length].toString(),
      composite_completions:(powers[n-prefix.length]-state.count).toString(), ledger};
  }
  function membershipResult(word) {
    binary(word,n,true);
    const periods = [];
    let rootLength = n;
    for (const row of rows) {
      let conflict = null;
      for (let j = row.period; j < n; j++) {
        stats.period_character_tests++;
        if (word[j] !== word[j-row.period]) {
          conflict = {position:j, previous_position:j-row.period}; break;
        }
      }
      periods.push({period:row.period, compatible:conflict === null,
        first_conflict:conflict});
      if (conflict === null && row.period < rootLength) rootLength = row.period;
    }
    return {word, primitive:rootLength===n, primitive_root:word.slice(0,rootLength),
      root_length:rootLength, repetitions:n/rootLength, periods};
  }
  function rankResult(word, trace) {
    binary(word,n,true);
    let state = zeroState(), rank = 0n;
    const steps = [];
    for (let i=0; i<n; i++) {
      const zero = move(state,"0"), bit = word[i], before=rank;
      if (bit==="1") { rank += zero.count; state = move(state,"1"); }
      else state=zero;
      if (trace) steps.push({position:i, symbol:bit,
        zero_completions:zero.count.toString(),
        rank_before:before.toString(), rank_after:rank.toString(),
        selected_prefix_completions:state.count.toString()});
    }
    if (state.count !== 0n && state.count !== 1n)
      fail("invalid terminal count: untrusted saved arithmetic");
    return {word, primitive:state.count===1n, rank:state.count===1n?rank.toString():null,
      insertion_rank:rank.toString(), trace:trace?steps:undefined};
  }
  function selectResult(rank, trace) {
    const input = natural(rank,"rank");
    if (input >= total) fail("rank out of range");
    let residual=input, state=zeroState();
    const steps=[];
    for (let i=0; i<n; i++) {
      const zero=move(state,"0"), before=residual;
      let bit;
      if (residual < zero.count) { bit="0"; state=zero; }
      else { bit="1"; residual-=zero.count; state=move(state,"1"); }
      if (trace) steps.push({position:i, symbol:bit,
        zero_completions:zero.count.toString(), rank_before:before.toString(),
        rank_after:residual.toString(), selected_prefix_completions:state.count.toString()});
    }
    if (residual!==0n || state.count!==1n) fail("invalid selection: untrusted saved arithmetic");
    stats.selected_words_created++;
    return {rank:input.toString(), word:state.prefix, trace:trace?steps:undefined};
  }
  return Object.freeze({
    summary() { stats.queries++; return {schema:SCHEMA,length:n,alphabet:["0","1"],
      primitive_total:total.toString(),composite_total:composite.toString(),
      all_words:powers[n].toString(), divisor_rows:rows.length, power_rows:powers.length,
      rotations_identified:false, reader_validation:"structural and total-partition checks only"}; },
    source() { stats.queries++; return clone(s.provenance); },
    prefix(prefix) { stats.queries++;stats.prefix_queries++;return prefixResult(prefix); },
    membership(word) { stats.queries++;stats.membership_queries++;return membershipResult(word); },
    rank(word, options={}) {
      stats.queries++;stats.rank_queries++;
      return rankResult(word,options.trace===true);
    },
    select(rank,options={}) {
      stats.queries++;stats.selection_queries++;
      return selectResult(rank,options.trace===true);
    },
    page(options={}) {
      stats.queries++;stats.page_queries++;
      const start=natural(options.start===undefined?"0":options.start,"start");
      const limit=small(options.limit===undefined?16:options.limit,"limit",0,
        PRIMITIVE_WORD_LIMITS.max_page_words);
      if(start>total)fail("page start beyond total");
      const records=[];
      for(let r=start;r<total&&records.length<limit;r++)records.push(selectResult(r,false));
      stats.page_words_returned+=records.length;
      const next=start+BigInt(records.length);
      return {start:start.toString(),total:total.toString(),records,
        next_start:next<total?next.toString():null};
    },
    snapshot() { stats.queries++;return clone(s); },
    statistics() { return clone(stats); }
  });
}
module.exports = {PRIMITIVE_WORD_LIMITS, compilePrimitiveWords, openRetainedPrimitiveWords};
