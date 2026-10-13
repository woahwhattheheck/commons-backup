"use strict";

/*
 * Positive mixed-recurrence sums from Zhi-Wei Sun, arXiv:0901.3075.
 * The source theorem supplies injectivity for integer a >= 2 and positive indices.
 * This module indexes the finite sum family; it does not classify prime remainders.
 */
const PELL_SUM_LIMITS = Object.freeze({
  max_parameter: 1000000,
  max_decimal_digits: 1000,
  max_saved_term_digits: 1008,
  max_terms: 4096,
  max_snapshot_chars: 2000000,
  max_provenance_chars: 32768,
  max_page_rows: 128,
  max_selection_rounds: 128
});
const SCHEMA = "commons.sun_positive_mixed_sum_index/v1";
function fail(s) { throw new RangeError(s); }
function nat(v, name, digits = PELL_SUM_LIMITS.max_decimal_digits) {
  if (typeof v === "bigint") { if (v < 0n) fail(name + " must be nonnegative"); }
  else if (typeof v === "number") {
    if (!Number.isSafeInteger(v) || v < 0) fail(name + " must be a safe nonnegative integer");
    v = BigInt(v);
  } else if (typeof v === "string" && /^(0|[1-9][0-9]*)$/.test(v)) {
    if (v.length > digits) fail(name + " is too long");
    v = BigInt(v);
  } else fail(name + " must be a canonical natural integer");
  if (v.toString().length > digits) fail(name + " is too long");
  return v;
}
function small(v, name, lower, upper) {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < lower || v > upper) fail(name + " out of range");
  return v;
}
function obj(v, name) {
  if (!v || typeof v !== "object" || Array.isArray(v)) fail(name + " must be an object");
  return v;
}
function copy(v) { return JSON.parse(JSON.stringify(v)); }
function provenance(v) {
  if (typeof v === "string") v = JSON.parse(v);
  obj(v, "provenance");
  const s = JSON.stringify(v);
  if (s.length > PELL_SUM_LIMITS.max_provenance_chars) fail("provenance too long");
  return JSON.parse(s);
}
function upperIndex(values, target, left, right, stats) {
  let lo = left, hi = right + 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (stats) stats.binary_comparisons++;
    if (values[mid] <= target) lo = mid + 1; else hi = mid;
  }
  return lo - 1;
}
function pairRow(values, a, i, j) {
  return {first_index:i,second_index:j,first:values[i].toString(),
    second:values[j].toString(),weighted_second:(a * values[j]).toString(),
    sum:(values[i] + a * values[j]).toString()};
}
function compilePositiveMixedSums(input) {
  obj(input, "input");
  const parameter = small(input.parameter, "parameter", 2, PELL_SUM_LIMITS.max_parameter);
  const a = BigInt(parameter), cap = nat(input.cap, "cap"), origin = provenance(input.provenance);
  const termBudget = input.max_terms === undefined ? PELL_SUM_LIMITS.max_terms :
    small(input.max_terms, "max_terms", 2, PELL_SUM_LIMITS.max_terms);
  const work = {recurrence_steps:0,frontier_rows:0,frontier_decrements:0,
    pairs_enumerated:0,prime_tests:0};
  const values = [0n,1n], threshold = cap - a;
  while (values[values.length - 1] <= threshold) {
    if (values.length >= termBudget)
      return {status:"INCOMPLETE_BUDGET",reason:"term_limit",snapshot:null,work};
    values.push(a * values[values.length - 1] + values[values.length - 2]);
    work.recurrence_steps++;
  }
  const last = values.length - 2, rows = [];
  let j = last, total = 0;
  for (let i = 1; i <= last; i++) {
    while (j >= 1 && values[i] + a * values[j] > cap) { j--; work.frontier_decrements++; }
    if (j < 1) fail("internal first-index boundary");
    rows.push({first_index:i,second_index_max:j,count:String(j),
      largest_sum:(values[i] + a * values[j]).toString(),
      next_sum:(values[i] + a * values[j+1]).toString()});
    total += j; work.frontier_rows++;
  }
  const snapshot = {
    schema:SCHEMA,status:"EXACT_POSITIVE_MIXED_SUM_INDEX",
    parameter,cap:cap.toString(),
    convention:{seed:["0","1"],recurrence:"u[k+1]=a*u[k]+u[k-1]",
      first_index_min:1,second_index_min:1,coefficient_roles:"u[i]+a*u[j]",
      order:"increasing numerical sum",rank_base:0,
      uniqueness:"Sun's positive-index theorem; not a new pair-collision census",
      prime_classification:false},
    terms:values.map((v,i)=>({index:i,value:v.toString(),
      recurrence_predecessors:i<2?null:[i-1,i-2]})),
    boundary:{last_permitted_first_index:last,
      first_excluded_index:last+1,first_excluded_value:values[last+1].toString(),
      threshold_for_first_coordinate:threshold.toString()},
    rows,summary:{parameter,cap:cap.toString(),recurrence_terms:values.length,
      first_index_rows:rows.length,total_sums:String(total),
      minimum_sum:total?String(parameter+1):null,
      maximum_sum:rows.length?rows.reduce((b,r)=>BigInt(r.largest_sum)>b?BigInt(r.largest_sum):b,0n).toString():null,
      contains_all_positive_index_sums_through_cap:true,
      pair_table_materialized:false,prime_tests:0},
    provenance:origin,work,limits:{...PELL_SUM_LIMITS}
  };
  const chars = JSON.stringify(snapshot).length;
  if (chars > PELL_SUM_LIMITS.max_snapshot_chars)
    return {status:"INCOMPLETE_BUDGET",reason:"snapshot_char_limit",snapshot:null,work,snapshot_chars:chars};
  return {status:snapshot.status,snapshot,summary:copy(snapshot.summary),work:copy(work),snapshot_chars:chars};
}
function openRetainedPositiveMixedSums(input) {
  if (typeof input === "string") {
    if (input.length > PELL_SUM_LIMITS.max_snapshot_chars) fail("snapshot too large");
    input = JSON.parse(input);
  }
  obj(input, "snapshot");
  const encoded = JSON.stringify(input);
  if (encoded.length > PELL_SUM_LIMITS.max_snapshot_chars) fail("snapshot too large");
  const snap = JSON.parse(encoded);
  if (snap.schema !== SCHEMA || snap.status !== "EXACT_POSITIVE_MIXED_SUM_INDEX") fail("unsupported snapshot");
  const parameter = small(snap.parameter,"parameter",2,PELL_SUM_LIMITS.max_parameter);
  const a = BigInt(parameter), cap = nat(snap.cap,"cap");
  provenance(snap.provenance);
  if (!Array.isArray(snap.terms) || snap.terms.length < 2 || snap.terms.length > PELL_SUM_LIMITS.max_terms) fail("invalid terms");
  const stats = {
    saved_seed_checks:2,saved_recurrence_checks:0,saved_boundary_checks:0,
    saved_frontier_checks:0,indexed_terms:snap.terms.length,indexed_rows:0,
    queries:0,summary_queries:0,source_queries:0,term_queries:0,frontier_queries:0,
    count_queries:0,decode_queries:0,rank_queries:0,selection_queries:0,
    page_queries:0,page_rows_returned:0,
    count_row_steps:0,count_frontier_decrements:0,decode_steps:0,
    selection_rounds:0,selection_row_midpoints:0,selection_sort_comparisons:0,
    binary_comparisons:0,heap_comparisons:0,heap_initial_rows:0,pair_records_created:0,
    compiler_calls:0,recurrence_terms_generated:0,frontier_rows_constructed:0,
    complete_pair_tables_materialized:0,prime_tests:0
  };
  const values = snap.terms.map((r,i)=>{
    obj(r,"term");
    if (r.index !== i) fail("term index");
    const v=nat(r.value,"term value",PELL_SUM_LIMITS.max_saved_term_digits);
    const wanted=i<2?null:[i-1,i-2];
    if (JSON.stringify(r.recurrence_predecessors)!==JSON.stringify(wanted)) fail("term predecessors");
    return v;
  });
  if (values[0] !== 0n || values[1] !== 1n) fail("seed mismatch");
  for (let i=2;i<values.length;i++) {
    if (values[i] !== a*values[i-1]+values[i-2]) fail("saved recurrence mismatch");
    stats.saved_recurrence_checks++;
  }
  const last=values.length-2;
  if (values[last+1] <= cap-a || (last>=1 && values[last]>cap-a)) fail("excluded boundary");
  const boundary={last_permitted_first_index:last,first_excluded_index:last+1,
    first_excluded_value:values[last+1].toString(),threshold_for_first_coordinate:(cap-a).toString()};
  for (const k of Object.keys(boundary)) if (snap.boundary?.[k]!==boundary[k]) fail("boundary metadata");
  stats.saved_boundary_checks++;
  if (!Array.isArray(snap.rows) || snap.rows.length!==last) fail("frontier row count");
  let total=0,prior=last,maximum=0n;
  const maxima=snap.rows.map((r,z)=>{
    obj(r,"row");const i=z+1,j=small(r.second_index_max,"second_index_max",1,last);
    if (r.first_index!==i || j>prior || r.count!==String(j)) fail("frontier index/count");
    const low=values[i]+a*values[j],high=values[i]+a*values[j+1];
    if (low>cap || high<=cap || r.largest_sum!==low.toString() || r.next_sum!==high.toString()) fail("frontier arithmetic");
    if (low>maximum) maximum=low;
    prior=j;total+=j;stats.saved_frontier_checks++;return j;
  });
  const summary={parameter,cap:cap.toString(),recurrence_terms:values.length,
    first_index_rows:last,total_sums:String(total),minimum_sum:total?String(parameter+1):null,
    maximum_sum:total?maximum.toString():null,
    contains_all_positive_index_sums_through_cap:true,pair_table_materialized:false,prime_tests:0};
  for (const k of Object.keys(summary)) if (snap.summary?.[k]!==summary[k]) fail("summary mismatch");
  const convention={seed:["0","1"],recurrence:"u[k+1]=a*u[k]+u[k-1]",
    first_index_min:1,second_index_min:1,coefficient_roles:"u[i]+a*u[j]",
    order:"increasing numerical sum",rank_base:0,
    uniqueness:"Sun's positive-index theorem; not a new pair-collision census",prime_classification:false};
  for (const k of Object.keys(convention)) if (JSON.stringify(snap.convention?.[k])!==JSON.stringify(convention[k])) fail("convention mismatch");
  stats.indexed_rows=last;
  function query(kind) { stats.queries++;stats[kind]++; }
  function permitted(v,name) { const n=nat(v,name);if(n>cap)fail(name+" above compiled cap");return n; }
  function rankValue(v,allowEnd) {
    const n=nat(v,"rank");
    if (n>BigInt(total) || (!allowEnd && n===BigInt(total))) fail("rank out of range");
    return Number(n);
  }
  function options(v) {
    if (v===undefined) v={};obj(v,"page options");
    const start=v.start===undefined?0:rankValue(v.start,true);
    const limit=v.limit===undefined?PELL_SUM_LIMITS.max_page_rows:small(v.limit,"limit",1,PELL_SUM_LIMITS.max_page_rows);
    return {start,limit};
  }
  function record(i,j) { stats.pair_records_created++;return pairRow(values,a,i,j); }
  function countInternal(x) {
    if (x<0n || last===0) return 0;
    if (x>=cap) return total;
    let j=last,answer=0;
    for(let i=1;i<=last;i++) {
      stats.count_row_steps++;
      while(j>=1 && values[i]+a*values[j]>x) {j--;stats.count_frontier_decrements++;}
      if(j===0)break;
      answer+=j;
    }
    return answer;
  }
  function selectInternal(wanted,opts) {
    if(opts===undefined)opts={};obj(opts,"selection options");
    if(opts.trace!==undefined && typeof opts.trace!=="boolean")fail("trace must be boolean");
    const limit=opts.max_rounds===undefined?PELL_SUM_LIMITS.max_selection_rounds:
      small(opts.max_rounds,"max_rounds",0,PELL_SUM_LIMITS.max_selection_rounds);
    const lo=Array(last).fill(1),hi=maxima.slice(),trace=[];
    let rank=wanted,remaining=total,round=0;
    while(remaining>0) {
      if(round>=limit)return {status:"INCOMPLETE_QUERY",reason:"selection_round_limit",rank:String(wanted),
        remaining:String(remaining),local_rank:String(rank),rounds:round,trace:opts.trace?trace:undefined};
      const mids=[];
      for(let r=0;r<last;r++)if(lo[r]<=hi[r]) {
        const mid=Math.floor((lo[r]+hi[r])/2),weight=hi[r]-lo[r]+1;
        mids.push({row:r,second:mid,weight,value:values[r+1]+a*values[mid]});
        stats.selection_row_midpoints++;
      }
      mids.sort((x,y)=>{stats.selection_sort_comparisons++;return x.value<y.value?-1:x.value>y.value?1:x.row-y.row;});
      let accumulated=0,pivot=mids[0];
      for(const x of mids){accumulated+=x.weight;if(accumulated*2>=remaining){pivot=x;break;}}
      const cuts=[];
      let less=0,atMost=0;
      for(let r=0;r<last;r++)if(lo[r]<=hi[r]) {
        const delta=pivot.value-values[r+1];
        const bound=delta<0n?-1n:delta/a;
        const le=upperIndex(values,bound,lo[r],hi[r],stats);
        let lt=le;
        if(le>=lo[r] && values[r+1]+a*values[le]===pivot.value)lt=le-1;
        less+=Math.max(0,lt-lo[r]+1);atMost+=Math.max(0,le-lo[r]+1);
        cuts.push({r,lt,le});
      }
      if(atMost-less!==1)fail("positive-sum uniqueness premise violated");
      const entry={round:round+1,remaining_before:String(remaining),local_rank_before:String(rank),
        pivot:{first_index:pivot.row+1,second_index:pivot.second,sum:pivot.value.toString()},
        less:String(less),at_most:String(atMost),decision:null,remaining_after:null,local_rank_after:null};
      round++;stats.selection_rounds++;
      if(rank<less) {
        for(const c of cuts)hi[c.r]=c.lt;
        remaining=less;entry.decision="lower";
      } else if(rank>=atMost) {
        for(const c of cuts)lo[c.r]=c.le+1;
        rank-=atMost;remaining-=atMost;entry.decision="upper";
      } else {
        entry.decision="found";entry.remaining_after="1";entry.local_rank_after="0";
        if(opts.trace)trace.push(entry);
        return {status:"EXACT_SELECTION",rank:String(wanted),...record(pivot.row+1,pivot.second),
          rounds:round,trace:opts.trace?trace:undefined};
      }
      entry.remaining_after=String(remaining);entry.local_rank_after=String(rank);
      if(opts.trace)trace.push(entry);
    }
    fail("selection exhausted");
  }
  function pagePairs(o) {
    const op=options(o);
    if(op.start===total)return {status:"EXACT_PAGE",start:String(op.start),total:String(total),count:0,records:[],next_start:null};
    const selected=selectInternal(op.start,{});
    if(selected.status!=="EXACT_SELECTION")return selected;
    const threshold=BigInt(selected.sum),heap=[];
    function cmp(x,y){stats.heap_comparisons++;return x.value<y.value?-1:x.value>y.value?1:x.i-y.i;}
    function push(x){
      heap.push(x);let p=heap.length-1;
      while(p>0){const parent=(p-1)>>1;if(cmp(heap[parent],heap[p])<=0)break;[heap[parent],heap[p]]=[heap[p],heap[parent]];p=parent;}
    }
    function pop(){
      const answer=heap[0],end=heap.pop();if(heap.length){heap[0]=end;let p=0;for(;;){let l=p*2+1;if(l>=heap.length)break;let r=l+1,b=r<heap.length&&cmp(heap[r],heap[l])<0?r:l;if(cmp(heap[p],heap[b])<=0)break;[heap[p],heap[b]]=[heap[b],heap[p]];p=b;}}return answer;
    }
    for(let r=0;r<last;r++){
      const delta=threshold-values[r+1],bound=delta<=0n?-1n:(delta-1n)/a;
      const j=upperIndex(values,bound,1,maxima[r],stats)+1;
      if(j<=maxima[r]){push({i:r+1,j,value:values[r+1]+a*values[j]});stats.heap_initial_rows++;}
    }
    const records=[];
    while(heap.length && records.length<op.limit){
      const x=pop(),r=record(x.i,x.j);records.push({rank:String(op.start+records.length),...r});
      if(x.j<maxima[x.i-1])push({i:x.i,j:x.j+1,value:values[x.i]+a*values[x.j+1]});
    }
    stats.page_rows_returned+=records.length;
    return {status:"EXACT_PAGE",start:String(op.start),total:String(total),count:records.length,records,
      next_start:op.start+records.length===total?null:String(op.start+records.length)};
  }
  function savedPage(array,v,kind) {
    if(v===undefined)v={};obj(v,"page options");
    const start=v.start===undefined?0:Number(nat(v.start,"start"));
    if(!Number.isSafeInteger(start)||start>array.length)fail("page start");
    const limit=v.limit===undefined?PELL_SUM_LIMITS.max_page_rows:small(v.limit,"limit",1,PELL_SUM_LIMITS.max_page_rows);
    const records=copy(array.slice(start,start+limit));
    stats.page_rows_returned+=records.length;
    return {kind,start:String(start),total:String(array.length),count:records.length,records,
      next_start:start+records.length===array.length?null:String(start+records.length)};
  }
  return Object.freeze({
    summary(){query("summary_queries");return copy(summary);},
    source(){query("source_queries");return copy(snap.provenance);},
    termPage(o){query("term_queries");return savedPage(snap.terms,o,"terms");},
    frontierPage(o){query("frontier_queries");return savedPage(snap.rows,o,"frontier");},
    countAtMost(x){query("count_queries");const v=permitted(x,"bound");return {bound:v.toString(),count:String(countInternal(v))};},
    countInterval(lower,upper){query("count_queries");const l=permitted(lower,"lower"),u=permitted(upper,"upper");if(l>u)fail("reversed interval");return{lower:l.toString(),upper:u.toString(),count:String(countInternal(u)-countInternal(l-1n))};},
    decode(sum){
      query("decode_queries");const target=permitted(sum,"sum");let i=1,j=last;
      while(i<=last&&j>=1){stats.decode_steps++;const s=values[i]+a*values[j];
        if(s===target)return {represented:true,...record(i,j)};
        if(s<target)i++;else j--;
      }return {represented:false,sum:target.toString()};
    },
    rank(firstIndex,secondIndex){
      query("rank_queries");const i=small(firstIndex,"first_index",1,last),j=small(secondIndex,"second_index",1,maxima[i-1]);
      const r=record(i,j);return{rank:String(countInternal(BigInt(r.sum)-1n)),...r};
    },
    select(rank,opts){query("selection_queries");return selectInternal(rankValue(rank,false),opts);},
    page(opts){query("page_queries");return pagePairs(opts);},
    snapshot(){return copy(snap);},
    statistics(){return copy(stats);}
  });
}
module.exports = {PELL_SUM_LIMITS,compilePositiveMixedSums,openRetainedPositiveMixedSums};
