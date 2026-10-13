"use strict";

/*
 * Finite primitive-weird prime-template catalog and saved ordinary-divisor reader.
 * Criterion: Amato--Hasler--Melfi--Parton (2016), Theorem 3.1.1,
 * specialized to m=2^k, two primes, j=0. See PRIMITIVE_WEIRD_API.md.
 * Source prime completeness/primality and saved-catalog provenance are explicit
 * premises. This module performs no I/O, sieve or subset-sum enumeration.
 */

const PRIMITIVE_WEIRD_LIMITS = Object.freeze({
  max_k: 12, max_basis_limit: 16384, max_basis_primes: 2000,
  max_candidates: 2000, max_trial_divisions: 4000000,
  max_decimal_digits: 128, max_page_size: 256, max_source_id_chars: 2048
});
const SCHEMA = "commons.primitive_weird_prime_template.v1";
const DEC = /^(0|[1-9][0-9]*)$/;
const copy = x => JSON.parse(JSON.stringify(x));

function fail(s) { throw new Error(s); }
function object(x, name) {
  if (!x || typeof x !== "object" || Array.isArray(x)) fail(name+" must be an object");
  return x;
}
function integer(x, lo, hi, name) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) fail(name+" is outside its safe-integer range");
  return x;
}
function natural(x, name) {
  let s;
  if (typeof x === "bigint") s = x.toString();
  else if (typeof x === "number" && Number.isSafeInteger(x) && x >= 0) s = String(x);
  else if (typeof x === "string") s = x;
  else fail(name+" must be a nonnegative safe integer, BigInt or canonical decimal string");
  if (!DEC.test(s) || s.length > PRIMITIVE_WEIRD_LIMITS.max_decimal_digits)
    fail(name+" is not a bounded canonical nonnegative integer");
  return BigInt(s);
}
function savedDecimal(x, name, positive) {
  if (typeof x !== "string") fail(name+" must be a saved decimal string");
  const b = natural(x, name);
  if (positive && b === 0n) fail(name+" must be positive");
  return b;
}
function sourceId(x) {
  if (typeof x !== "string" || !x.trim() || x.length > PRIMITIVE_WEIRD_LIMITS.max_source_id_chars)
    fail("basis.source_id must identify the retained complete prime source");
  return x;
}
function readBasis(raw, k) {
  object(raw, "basis");
  const limit = integer(raw.limit, 2, PRIMITIVE_WEIRD_LIMITS.max_basis_limit, "basis.limit");
  const S = 2 ** (k+1)-1;
  if (limit < 2*S) fail("basis must claim completeness through at least 2*S");
  if (!Array.isArray(raw.primes) || raw.primes.length < 1 ||
      raw.primes.length > PRIMITIVE_WEIRD_LIMITS.max_basis_primes)
    fail("basis.primes must be a bounded nonempty array");
  const primes = raw.primes.map((p,i) => {
    integer(p, 2, limit, "basis prime");
    if ((i === 0 && p !== 2) || (i > 0 && (p <= raw.primes[i-1] || p % 2 === 0)))
      fail("basis must start with 2 and then strictly increasing odd entries");
    return p;
  });
  return {limit, primes, source_id:sourceId(raw.source_id),
    premise:"the listed integers are exactly all primes at most limit; not re-established here"};
}
function makeWork() {
  return {
    phase:"saved_reader",
    retained_basis_entries:0, retained_candidate_rows:0, retained_certificate_rows:0,
    retained_maximal_divisor_rows:0, retained_block_rows:0, retained_trial_rows:0,
    parameter_constructions:0, q_classifications:0, trial_divisions:0,
    prime_bound_comparisons:0, prime_source_primality_checks:0, sieve_operations:0,
    certificate_constructions:0, subset_sum_searches:0,
    query_calls:0, catalog_bound_comparisons:0, candidate_bound_comparisons:0,
    block_bound_divisions:0, divisor_bisection_steps:0,
    divisor_membership_remainders:0, divisor_block_identifications:0,
    divisor_frontier_min_comparisons:0, divisor_rows_returned:0,
    catalog_rows_returned:0, prime_trial_rows_returned:0
  };
}
function classifyQ(q, basis, work) {
  let last = null, trials = 0;
  const quotients=[],remainders=[];
  for (let i=0;i<basis.primes.length;i++) {
    const ell = basis.primes[i];
    work.prime_bound_comparisons++;
    if (ell*ell > q) return {
      kind:"prime", trial_count:trials, last_tested_prime:last,
      stopping_prime_index:i, stopping_prime:ell, stopping_prime_square:ell*ell,
      least_divisor:null, cofactor:null, tested_quotients:quotients, tested_remainders:remainders,
      basis_source_id:basis.source_id
    };
    if (work.trial_divisions >= PRIMITIVE_WEIRD_LIMITS.max_trial_divisions)
      fail("trial-division limit reached");
    work.trial_divisions++; trials++; last=ell;
    const quotient=Math.floor(q/ell), remainder=q%ell;
    quotients.push(quotient); remainders.push(remainder);
    if (remainder === 0) return {
      kind:"composite", trial_count:trials, last_tested_prime:last,
      stopping_prime_index:i, stopping_prime:ell, stopping_prime_square:ell*ell,
      least_divisor:ell, cofactor:quotient, tested_quotients:quotients, tested_remainders:remainders,
      basis_source_id:basis.source_id
    };
  }
  fail("retained prime basis has no stopping prime: completeness premise is insufficient");
}
function primitiveCertificate(k, S, p, q, delta) {
  const two=1n << BigInt(k), P=BigInt(p), Q=BigInt(q), s=BigInt(S), a=BigInt(delta);
  const N=two*P*Q, sigma=s*(P+1n)*(Q+1n);
  const half=N/2n, noP=N/P, noQ=N/Q;
  const rows=[
    {removed_prime:2, value:half.toString(),
      sigma:((two-1n)*(P+1n)*(Q+1n)).toString(),
      deficiency:(two*(P+Q+1n)-a).toString(),
      identity:"2^k*(p+q+1)-delta"},
    {removed_prime:p, value:noP.toString(),
      sigma:(s*(Q+1n)).toString(), deficiency:(Q-s).toString(), identity:"q-S"},
    {removed_prime:q, value:noQ.toString(),
      sigma:(s*(P+1n)).toString(), deficiency:(P-s).toString(), identity:"p-S"}
  ];
  if (sigma-2n*N !== a || !(s < a && a < P && P < Q))
    fail("internal primitive-weird criterion mismatch");
  for (const row of rows)
    if (BigInt(row.deficiency) <= 0n ||
        2n*BigInt(row.value)-BigInt(row.sigma) !== BigInt(row.deficiency))
      fail("internal maximal-divisor deficiency mismatch");
  const blocks=[
    {odd_part:"1", exponent_min:0, exponent_max:k, count:k+1},
    {odd_part:String(p), exponent_min:0, exponent_max:k, count:k+1},
    {odd_part:String(q), exponent_min:0, exponent_max:k, count:k+1},
    {odd_part:(P*Q).toString(), exponent_min:0, exponent_max:k-1, count:k}
  ];
  return {
    N:N.toString(), sigma:sigma.toString(), delta:a.toString(),
    proper_divisor_sum:(sigma-N).toString(),
    powers_of_two_sum:String(S), delta_minus_S:(a-s).toString(),
    p_minus_delta:(P-a).toString(),
    obstruction:{
      target:"delta", eligible_proper_divisors:"2^j, 0<=j<=k",
      eligible_divisor_sum:String(S), next_possible_proper_divisor:String(p),
      statement:"delta exceeds the total of all eligible divisors and is below every other proper divisor"
    },
    maximal_proper_divisors:rows,
    conclusion:"primitive weird; in fact every proper divisor is deficient",
    proper_divisor_count:4*k+3, divisor_blocks:blocks
  };
}
function compilePrimitiveWeirdIndex(input) {
  object(input,"input");
  const k=integer(input.k,1,PRIMITIVE_WEIRD_LIMITS.max_k,"k");
  const S=2**(k+1)-1, basis=readBasis(input.basis,k);
  const pValues=basis.primes.filter(p=>S<p && p<2*S);
  if (pValues.length > PRIMITIVE_WEIRD_LIMITS.max_candidates) fail("candidate cap exceeded");
  const work=makeWork(); work.phase="constructor";
  work.retained_basis_entries=basis.primes.length;
  const rows=[], certified=[];
  for (let i=0;i<pValues.length;i++) {
    const p=pValues[i], d=p-S;
    const quotient=Math.floor(S*S/d), remainder=S*S%d, q=S+quotient, delta=S+remainder;
    work.parameter_constructions++;
    if (!(d>0 && d<S && d%2===0 && remainder>0 && remainder<d && q>p))
      fail("internal parameter bounds failed");
    const primality=classifyQ(q,basis,work); work.q_classifications++;
    const templateN=((1n<<BigInt(k))*BigInt(p)*BigInt(q)).toString();
    let certificate=null;
    if (primality.kind==="prime") {
      certificate=primitiveCertificate(k,S,p,q,delta);
      work.certificate_constructions++;
      certified.push(i);
    }
    rows.push({
      candidate_index:i, p, p_basis_index:basis.primes.indexOf(p), d,
      quotient_floor:quotient, remainder, q, delta,
      template_N:templateN,
      status:certificate ? "certified_primitive_weird" : "composite_q_template_not_certified",
      q_primality:primality, certificate
    });
  }
  certified.sort((a,b)=>BigInt(rows[a].template_N)<BigInt(rows[b].template_N)?-1:1);
  work.retained_candidate_rows=rows.length;
  work.retained_trial_rows=work.trial_divisions;
  work.retained_certificate_rows=certified.length;
  work.retained_maximal_divisor_rows=3*certified.length;
  work.retained_block_rows=4*certified.length;
  const snapshot={
    schema:SCHEMA, k, S, p_interval:{lower_exclusive:S,upper_exclusive:2*S},
    q_global_upper_bound:S+Math.floor(S*S/2),
    basis,
    construction:{
      parameterization:"q=S+floor(S^2/(p-S)); delta=S+(S^2 mod(p-S))",
      criterion:"S < delta < p < q; p and q distinct odd primes; N=2^k*p*q",
      published_specialization:"Amato--Hasler--Melfi--Parton (2016), Theorem 3.1.1, m=2^k, two primes, j=0",
      composite_scope:"a composite q only fails this prime-template certificate; no classification of template_N as non-weird"
    },
    counts:{candidate_count:rows.length,certified_count:certified.length,
      composite_q_count:rows.length-certified.length},
    rows, certified_indices_by_N:certified, construction_work:copy(work),
    finite_scope:"complete only for the stated one-q-per-p template and supplied complete prime basis; no odd-weird or infinitude conclusion"
  };
  return buildInterface(snapshot,work);
}
function validateSnapshot(raw) {
  object(raw,"snapshot");
  if (raw.schema!==SCHEMA) fail("unsupported snapshot schema");
  const k=integer(raw.k,1,PRIMITIVE_WEIRD_LIMITS.max_k,"snapshot.k");
  const S=2**(k+1)-1;
  if(raw.S!==S || !raw.p_interval || raw.p_interval.lower_exclusive!==S ||
      raw.p_interval.upper_exclusive!==2*S ||
      raw.q_global_upper_bound!==S+Math.floor(S*S/2)) fail("snapshot parameter envelope mismatch");
  const basis=readBasis(raw.basis,k);
  if(!Array.isArray(raw.rows) || raw.rows.length>PRIMITIVE_WEIRD_LIMITS.max_candidates)
    fail("snapshot rows exceed the candidate cap");
  const expectedP=basis.primes.filter(p=>S<p&&p<2*S);
  if(expectedP.length!==raw.rows.length) fail("snapshot omits a source-prime candidate");
  const work=makeWork();work.retained_basis_entries=basis.primes.length;
  let certificateCount=0;
  const ns=new Set();
  for(let i=0;i<raw.rows.length;i++){
    const row=object(raw.rows[i],"candidate");
    if(row.candidate_index!==i||row.p!==expectedP[i]) fail("candidate source coverage/order mismatch");
    integer(row.p_basis_index,0,basis.primes.length-1,"p basis index");
    if(basis.primes[row.p_basis_index]!==row.p) fail("candidate source-prime index mismatch");
    integer(row.d,2,S-1,"d");
    integer(row.quotient_floor,1,S*S,"quotient");
    integer(row.remainder,1,S-1,"remainder");
    integer(row.q,row.p+1,raw.q_global_upper_bound,"q");
    integer(row.delta,S+1,row.p-1,"delta");
    savedDecimal(row.template_N,"template_N",true);
    const qp=object(row.q_primality,"q_primality");
    if(qp.kind!=="prime"&&qp.kind!=="composite") fail("invalid q classification tag");
    integer(qp.trial_count,0,basis.primes.length,"trial_count");
    integer(qp.stopping_prime_index,0,basis.primes.length-1,"stopping prime index");
    if(basis.primes[qp.stopping_prime_index]!==qp.stopping_prime ||
        qp.basis_source_id!==basis.source_id) fail("q witness basis binding mismatch");
    integer(qp.stopping_prime_square,4,basis.limit*basis.limit,"stopping prime square");
    if(qp.trial_count===0 ? qp.last_tested_prime!==null :
       qp.last_tested_prime!==basis.primes[qp.trial_count-1])
      fail("q witness tested-prefix mismatch");
    if(!Array.isArray(qp.tested_quotients)||!Array.isArray(qp.tested_remainders)||
        qp.tested_quotients.length!==qp.trial_count||qp.tested_remainders.length!==qp.trial_count)
      fail("complete tested quotient/remainder prefix required");
    for(let t=0;t<qp.trial_count;t++){
      integer(qp.tested_quotients[t],1,row.q,"tested quotient");
      integer(qp.tested_remainders[t],0,basis.primes[t]-1,"tested remainder");
      work.retained_trial_rows++;
      const finalComposite=qp.kind==="composite"&&t===qp.trial_count-1;
      if(finalComposite ? qp.tested_remainders[t]!==0 : qp.tested_remainders[t]===0)
        fail("saved nondivisor/divisor remainder pattern mismatch");
    }
    if(qp.kind==="composite"){
      if(row.status!=="composite_q_template_not_certified" || row.certificate!==null ||
          qp.trial_count!==qp.stopping_prime_index+1 ||
          qp.least_divisor!==qp.stopping_prime) fail("composite record structure mismatch");
      integer(qp.cofactor,2,row.q,"composite cofactor");
      if(qp.cofactor!==qp.tested_quotients[qp.trial_count-1])fail("cofactor/prefix binding mismatch");
    }else{
      if(row.status!=="certified_primitive_weird" || qp.trial_count!==qp.stopping_prime_index ||
          qp.least_divisor!==null || qp.cofactor!==null) fail("prime record structure mismatch");
      const c=object(row.certificate,"certificate");
      for(const f of ["N","sigma","delta","proper_divisor_sum","powers_of_two_sum","delta_minus_S","p_minus_delta"])
        savedDecimal(c[f],"certificate."+f,true);
      if(c.N!==row.template_N||c.delta!==String(row.delta)||
          c.powers_of_two_sum!==String(S)||c.proper_divisor_count!==4*k+3)
        fail("certificate scalar binding mismatch");
      object(c.obstruction,"obstruction");
      if(c.obstruction.target!=="delta"||c.obstruction.eligible_divisor_sum!==String(S)||
          c.obstruction.next_possible_proper_divisor!==String(row.p))
        fail("obstruction binding mismatch");
      if(!Array.isArray(c.maximal_proper_divisors)||c.maximal_proper_divisors.length!==3)
        fail("three maximal proper-divisor witnesses required");
      const removed=[2,row.p,row.q];
      for(let j=0;j<3;j++){
        const v=object(c.maximal_proper_divisors[j],"maximal divisor");
        if(v.removed_prime!==removed[j]) fail("maximal divisor order mismatch");
        for(const f of ["value","sigma","deficiency"])savedDecimal(v[f],"maximal divisor."+f,true);
      }
      if(!Array.isArray(c.divisor_blocks)||c.divisor_blocks.length!==4)
        fail("four dyadic divisor blocks required");
      for(let j=0;j<4;j++){
        const b=object(c.divisor_blocks[j],"divisor block");
        savedDecimal(b.odd_part,"odd_part",true);
        if(b.exponent_min!==0||b.exponent_max!==(j===3?k-1:k)||
            b.count!==b.exponent_max+1) fail("dyadic block exponent contract mismatch");
      }
      if(c.divisor_blocks[0].odd_part!=="1" ||
         c.divisor_blocks[1].odd_part!==String(row.p) ||
         c.divisor_blocks[2].odd_part!==String(row.q)) fail("dyadic block source bindings mismatch");
      if(ns.has(c.N))fail("duplicate certified N");
      ns.add(c.N);certificateCount++;
    }
  }
  const ids=raw.certified_indices_by_N;
  if(!Array.isArray(ids)||ids.length!==certificateCount)fail("certified index size mismatch");
  const seen=new Set();let prior=-1n;
  for(const id of ids){
    integer(id,0,raw.rows.length-1,"certified index");
    if(seen.has(id)||raw.rows[id].certificate===null)fail("invalid certified index");
    seen.add(id);const n=BigInt(raw.rows[id].template_N);
    if(n<=prior)fail("certified N order is not strict");
    prior=n;
  }
  object(raw.counts,"counts");
  if(raw.counts.candidate_count!==raw.rows.length||raw.counts.certified_count!==certificateCount||
      raw.counts.composite_q_count!==raw.rows.length-certificateCount)fail("saved count mismatch");
  object(raw.construction,"construction");
  object(raw.construction_work,"construction_work");
  work.retained_candidate_rows=raw.rows.length;
  work.retained_certificate_rows=certificateCount;
  work.retained_maximal_divisor_rows=3*certificateCount;
  work.retained_block_rows=4*certificateCount;
  return {snapshot:copy(raw),work};
}
function openRetainedPrimitiveWeirdIndex(snapshot) {
  const v=validateSnapshot(snapshot);
  return buildInterface(v.snapshot,v.work);
}
function buildInterface(snapshot,work) {
  const rows=snapshot.rows, ids=snapshot.certified_indices_by_N;
  const nValues=ids.map(i=>BigInt(rows[i].template_N));
  const byN=new Map(ids.map(i=>[rows[i].template_N,rows[i]]));
  function bound(value,inclusive) {
    let lo=0,hi=nValues.length;
    while(lo<hi){const mid=(lo+hi)>>1;work.catalog_bound_comparisons++;
      if(nValues[mid]<value||(inclusive&&nValues[mid]===value))lo=mid+1;else hi=mid;}
    return lo;
  }
  function pBound(p) {
    let lo=0,hi=rows.length;
    while(lo<hi){const mid=(lo+hi)>>1;work.candidate_bound_comparisons++;
      if(rows[mid].p<p)lo=mid+1;else hi=mid;}
    return lo;
  }
  function selectedN(N) {
    const x=natural(N,"N"),row=byN.get(x.toString());
    if(!row)fail("N has no certified record in this saved catalog");
    return {N:x,row,blocks:row.certificate.divisor_blocks};
  }
  function smallRank(x,upper,name,allowEnd) {
    const n=natural(x,name),hi=BigInt(upper);
    if(n>hi||(!allowEnd&&n===hi))fail(name+" is outside the indexed family");
    return Number(n);
  }
  function size(x) {
    return integer(x,1,PRIMITIVE_WEIRD_LIMITS.max_page_size,"page limit");
  }
  function blockCount(block,T) {
    if(T<1n)return 0;
    const b=BigInt(block.odd_part);
    if(T<b)return 0;
    work.block_bound_divisions++;
    const ratio=T/b;
    return Math.min(block.count,ratio.toString(2).length);
  }
  function countAtMost(blocks,T) {
    let c=0;for(const b of blocks)c+=blockCount(b,T);return c;
  }
  function identify(blocks,value,rank) {
    for(let i=0;i<blocks.length;i++){
      work.divisor_block_identifications++;
      const b=blocks[i],base=BigInt(b.odd_part);
      if(value%base!==0n)continue;
      const ratio=value/base;
      if(ratio>0n&&(ratio&(ratio-1n))===0n){
        const exponent=ratio.toString(2).length-1;
        if(exponent>=b.exponent_min&&exponent<=b.exponent_max)
          return {rank,value:value.toString(),block_index:i,odd_part:b.odd_part,exponent};
      }
    }
    fail("saved divisor blocks do not contain selected value; provenance premise failed");
  }
  function divisorSelect(state,rank) {
    let lo=1n,hi=state.N-1n;
    while(lo<hi){work.divisor_bisection_steps++;
      const mid=(lo+hi)>>1n;
      if(countAtMost(state.blocks,mid)>rank)hi=mid;else lo=mid+1n;}
    return identify(state.blocks,lo,rank);
  }
  return Object.freeze({
    summary() {
      work.query_calls++;
      return {
        schema:SCHEMA,k:snapshot.k,S:snapshot.S,counts:copy(snapshot.counts),
        p_interval:copy(snapshot.p_interval),q_global_upper_bound:snapshot.q_global_upper_bound,
        least_certified_N:nValues.length?nValues[0].toString():null,
        greatest_certified_N:nValues.length?nValues[nValues.length-1].toString():null,
        ordering:"catalog by strictly increasing N; candidates by p",
        proper_divisor_count_per_certificate:4*snapshot.k+3,
        prime_source_id:snapshot.basis.source_id,
        scope:snapshot.finite_scope
      };
    },
    candidate(p) {
      work.query_calls++;integer(p,2,PRIMITIVE_WEIRD_LIMITS.max_basis_limit,"p");
      const i=pBound(p);
      if(i===rows.length||rows[i].p!==p)return {p,status:"not_a_retained_candidate"};
      work.catalog_rows_returned++;return copy(rows[i]);
    },
    primeTrialPage(p,start=0,limit=64) {
      work.query_calls++;integer(p,2,PRIMITIVE_WEIRD_LIMITS.max_basis_limit,"p");
      const i=pBound(p);
      if(i===rows.length||rows[i].p!==p)fail("p is not a retained candidate");
      const row=rows[i],q=row.q_primality,total=q.trial_count,
        s=smallRank(start,total,"trial start",true),l=size(limit),end=Math.min(total,s+l);
      work.prime_trial_rows_returned+=end-s;
      return {p:row.p,q:row.q,classification:q.kind,total,start:s,
        basis_source_id:snapshot.basis.source_id,
        rows:Array.from({length:end-s},(_,j)=>{const t=s+j;return {
          trial_index:t,prime:snapshot.basis.primes[t],
          quotient:q.tested_quotients[t],remainder:q.tested_remainders[t]};}),
        stopping_prime:q.stopping_prime,stopping_prime_square:q.stopping_prime_square,
        next:end<total?end:null};
    },
    candidatePage(start=0,limit=64) {
      work.query_calls++;const s=smallRank(start,rows.length,"start",true),l=size(limit);
      const end=Math.min(rows.length,s+l);
      work.catalog_rows_returned+=end-s;
      return {ordering:"increasing p",total:rows.length,start:s,rows:copy(rows.slice(s,end)),
        next:end<rows.length?end:null};
    },
    count(lower=0n,upper=null) {
      work.query_calls++;const lo=natural(lower,"lower");
      const hi=upper===null?null:natural(upper,"upper");
      if(hi!==null&&lo>hi)fail("lower exceeds upper");
      const first=bound(lo,false),end=hi===null?ids.length:bound(hi,true);
      return {lower:lo.toString(),upper:hi===null?null:hi.toString(),count:end-first,
        first_rank:first,end_rank_exclusive:end};
    },
    rank(N) {
      work.query_calls++;const n=natural(N,"N"),i=bound(n,false);
      return {N:n.toString(),found:i<nValues.length&&nValues[i]===n,
        rank:i<nValues.length&&nValues[i]===n?i:null,insertion_rank:i};
    },
    select(rank) {
      work.query_calls++;const r=smallRank(rank,ids.length,"rank",false);
      work.catalog_rows_returned++;
      return {rank:r,candidate:copy(rows[ids[r]])};
    },
    page(start=0,limit=64) {
      work.query_calls++;const s=smallRank(start,ids.length,"start",true),l=size(limit),
        end=Math.min(ids.length,s+l);
      work.catalog_rows_returned+=end-s;
      return {ordering:"increasing N",total:ids.length,start:s,
        rows:ids.slice(s,end).map((i,j)=>({rank:s+j,candidate:copy(rows[i])})),
        next:end<ids.length?end:null};
    },
    properDivisorCount(N,lower=1n,upper=null) {
      work.query_calls++;const state=selectedN(N),lo=natural(lower,"lower"),
        hi=upper===null?state.N-1n:natural(upper,"upper");
      if(lo>hi)fail("lower exceeds upper");
      const first=countAtMost(state.blocks,lo-1n),end=countAtMost(state.blocks,hi);
      return {N:state.N.toString(),lower:lo.toString(),upper:hi.toString(),
        count:end-first,first_rank:first,end_rank_exclusive:end,total:4*snapshot.k+3};
    },
    rankProperDivisor(N,value) {
      work.query_calls++;const state=selectedN(N),x=natural(value,"divisor");
      let member=false;
      if(x>0n&&x<state.N){work.divisor_membership_remainders++;member=state.N%x===0n;}
      const insertion=countAtMost(state.blocks,x-1n);
      return {N:state.N.toString(),value:x.toString(),found:member,
        rank:member?insertion:null,insertion_rank:insertion};
    },
    selectProperDivisor(N,rank) {
      work.query_calls++;const state=selectedN(N),
        r=smallRank(rank,4*snapshot.k+3,"divisor rank",false);
      work.divisor_rows_returned++;
      return {N:state.N.toString(),...divisorSelect(state,r)};
    },
    pageProperDivisors(N,start=0,limit=64) {
      work.query_calls++;const state=selectedN(N),total=4*snapshot.k+3,
        s=smallRank(start,total,"divisor start",true),l=size(limit);
      if(s===total)return {N:state.N.toString(),total,start:s,rows:[],next:null};
      const first=divisorSelect(state,s),threshold=BigInt(first.value)-1n;
      const frontier=state.blocks.map((b,i)=>{
        const e=blockCount(b,threshold);
        return {block_index:i,exponent:e,value:e<=b.exponent_max?BigInt(b.odd_part)<<BigInt(e):null};
      });
      const out=[],end=Math.min(total,s+l);
      for(let rank=s;rank<end;rank++){
        let pick=-1;
        for(let i=0;i<frontier.length;i++){
          if(frontier[i].value===null)continue;
          if(pick===-1)pick=i;
          else{work.divisor_frontier_min_comparisons++;
            if(frontier[i].value<frontier[pick].value)pick=i;}
        }
        if(pick===-1)fail("saved divisor frontier exhausted too early");
        const f=frontier[pick],b=state.blocks[pick];
        out.push({rank,value:f.value.toString(),block_index:pick,
          odd_part:b.odd_part,exponent:f.exponent});
        f.exponent++;
        f.value=f.exponent<=b.exponent_max?f.value*2n:null;
      }
      work.divisor_rows_returned+=out.length;
      return {N:state.N.toString(),total,start:s,rows:out,next:end<total?end:null};
    },
    snapshot() {return copy(snapshot);},
    work() {return copy(work);}
  });
}

module.exports = {
  compilePrimitiveWeirdIndex,
  openRetainedPrimitiveWeirdIndex,
  PRIMITIVE_WEIRD_LIMITS
};
