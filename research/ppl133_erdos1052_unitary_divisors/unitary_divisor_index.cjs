"use strict";

/*
 * Exact unitary-divisor navigation from an identified prime-power factorization.
 * Mathematical convention: Subbarao and Warren, Canadian Mathematical Bulletin
 * 9(2) (1966), 147-153, introduction. No finiteness or novelty claim.
 * Prime-basis completeness/primality and saved product identities are explicit
 * input premises. This module performs no sieve, primality test, I/O, or search
 * through known unitary-perfect numbers.
 */

const UNITARY_DIVISOR_LIMITS = Object.freeze({
  factors: 28, half_records: 16384, exponent: 4096, factorial_bound: 4096,
  prime_basis_rows: 4096, integer_digits: 256, arithmetic_digits: 272,
  page_size: 128, source_id_characters: 2048, select_cache: 128, count_cache: 512
});
const SCHEMA = "commons.unitary_divisor_mitm/v1";
function fail(message) { throw new RangeError(message); }
function object(x,name) {
  if(!x || typeof x!=="object" || Array.isArray(x))fail(name+" must be an object");
  return x;
}
function list(x,name,length) {
  if(!Array.isArray(x) || (length!==undefined && x.length!==length))fail(name+" has the wrong array shape");
  return x;
}
function uint(x,name,digits=UNITARY_DIVISOR_LIMITS.integer_digits,min=0n) {
  let s;
  if(typeof x==="bigint")s=x.toString();
  else if(typeof x==="number" && Number.isSafeInteger(x))s=String(x);
  else if(typeof x==="string")s=x;
  else fail(name+" must be a safe integer, BigInt, or canonical decimal string");
  if(s.length>digits || !/^(0|[1-9][0-9]*)$/.test(s))fail(name+" violates the bounded decimal contract");
  const n=BigInt(s);if(n<min)fail(name+" is below its minimum");return n;
}
function dec(x,name,digits=UNITARY_DIVISOR_LIMITS.arithmetic_digits,min=0n) {
  if(typeof x!=="string")fail(name+" must be a decimal string");
  return uint(x,name,digits,min);
}
function signedDec(x,name) {
  if(typeof x!=="string" || x.length>UNITARY_DIVISOR_LIMITS.arithmetic_digits+1 ||
      !/^(0|-?[1-9][0-9]*)$/.test(x))fail(name+" must be a bounded signed decimal string");
  return BigInt(x);
}
function sourceId(x) {
  if(typeof x!=="string" || x.length===0 || x.length>UNITARY_DIVISOR_LIMITS.source_id_characters)
    fail("source_id must be a nonempty bounded string");
  return x;
}
function exponent(x) {
  if(!Number.isSafeInteger(x) || x<1 || x>UNITARY_DIVISOR_LIMITS.exponent)fail("exponent is outside its bounds");
  return x;
}
function copy(x){return JSON.parse(JSON.stringify(x));}
function normalizeBasis(input) {
  object(input,"prime_basis");
  const sid=sourceId(input.source_id),bound=uint(input.complete_through,"complete_through");
  const rows=list(input.primes,"primes");
  if(rows.length>UNITARY_DIVISOR_LIMITS.prime_basis_rows)fail("prime basis has too many rows");
  let previous=1n;
  const primes=rows.map((x,i)=>{
    const p=uint(x,"prime basis row "+i,UNITARY_DIVISOR_LIMITS.integer_digits,2n);
    if(p<=previous || p>bound)fail("prime basis must be strictly increasing within complete_through");
    previous=p;return String(p);
  });
  return {source_id:sid,complete_through:String(bound),primes};
}
function counters() {
  return {
    constructors:0, saved_opens:0, prime_basis_rows_read:0, factor_rows_read:0,
    prime_power_multiplications:0, factor_product_multiplications:0, sigma_product_multiplications:0,
    subset_product_multiplications:0, half_sort_comparisons:0, half_prefix_additions:0,
    sqrt_iterations:0, sqrt_bound_products:0, aggregate_products:0,
    half_records_loaded:0, mask_coverage_entries:0, prefix_equalities_checked:0,
    count_queries:0, prefix_queries:0, interval_queries:0, rank_queries:0, select_queries:0, page_queries:0,
    threshold_scans:0, threshold_left_rows:0, threshold_product_comparisons:0, threshold_sum_products:0,
    count_cache_hits:0, select_cache_hits:0, selection_bisection_steps:0,
    membership_modulos:0, membership_divisions:0, gcd_modulos:0, witness_products:0,
    heap_seed_comparisons:0, heap_seed_products:0, heap_comparisons:0, heap_pushes:0, heap_pops:0,
    heap_advance_products:0, returned_divisors:0, full_divisor_families_enumerated:0,
    primality_tests:0, sieve_runs:0
  };
}
function checkedProduct(a,b,digits,name) {
  const p=a*b;if(p.toString().length>digits)fail(name+" exceeds the digit cap");return p;
}
function primePower(p,e,work) {
  let result=1n,base=p,remaining=e;
  while(remaining>0) {
    if(remaining%2===1){result=checkedProduct(result,base,UNITARY_DIVISOR_LIMITS.integer_digits,"prime power");work.prime_power_multiplications++;}
    remaining=Math.floor(remaining/2);
    if(remaining>0){base=checkedProduct(base,base,UNITARY_DIVISOR_LIMITS.integer_digits,"prime power");work.prime_power_multiplications++;}
  }
  return result;
}
function integerSqrt(n,work) {
  if(n<2n)return n;
  let x=1n<<BigInt(Math.ceil(n.toString(2).length/2));
  while(true) {
    const y=(x+n/x)/2n;work.sqrt_iterations++;
    if(y>=x)return x;
    x=y;
  }
}
function kindName(options) {
  const kind=options.kind===undefined?"proper":options.kind;
  if(kind!=="all" && kind!=="proper")fail("kind must be all or proper");
  return kind;
}
function flag(options,key) {
  const x=options[key]===undefined?false:options[key];
  if(typeof x!=="boolean")fail(key+" must be boolean");
  return x;
}

function factorialPrimePowerInput(options) {
  object(options,"options");
  const bound=uint(options.n,"factorial n");
  if(bound>BigInt(UNITARY_DIVISOR_LIMITS.factorial_bound))fail("factorial bound is too large");
  const basis=normalizeBasis(options.prime_basis);
  if(BigInt(basis.complete_through)<bound)fail("prime basis does not declare coverage through the factorial bound");
  const chosen=basis.primes.filter(p=>BigInt(p)<=bound);
  if(chosen.length>UNITARY_DIVISOR_LIMITS.factors)fail("factorial needs too many prime-power blocks");
  const rows=[],factors=[];
  let divisions=0;
  for(const text of chosen) {
    const p=BigInt(text),powers=[],quotients=[];
    let power=p,e=0n;
    while(power<=bound) {
      const q=bound/power;divisions++;
      powers.push(String(power));quotients.push(String(q));e+=q;power*=p;
    }
    if(e<1n || e>BigInt(UNITARY_DIVISOR_LIMITS.exponent))fail("factorial exponent is outside the constructor limit");
    rows.push({prime:text,powers,quotients,exponent:Number(e)});
    factors.push({prime:text,exponent:Number(e)});
  }
  return {
    schema:"commons.factorial_prime_power_input/v1",
    source_id:sourceId(options.source_id),factorial_bound:String(bound),prime_basis:basis,
    factors,valuation_rows:rows,
    work:{prime_basis_rows_read:basis.primes.length,valuation_divisions:divisions,prime_power_rows:rows.length,
      primality_tests:0,sieve_runs:0,factorial_product_steps:0},
    premise:"The identified prime list is complete through its declared bound; it is not resieved or primality-tested here."
  };
}

function buildHalf(factors,start,count,work) {
  const rows=[{value:1n,mask:0}];
  for(let bit=0;bit<count;bit++) {
    const before=rows.length,power=BigInt(factors[start+bit].power),weight=2**bit;
    for(let j=0;j<before;j++) {
      rows.push({value:rows[j].value*power,mask:rows[j].mask+weight});
      work.subset_product_multiplications++;
    }
  }
  rows.sort((a,b)=>{work.half_sort_comparisons++;return a.value<b.value?-1:a.value>b.value?1:0;});
  const prefix=[0n],byMask=new Map();
  for(let i=0;i<rows.length;i++) {
    if(i && rows[i-1].value>=rows[i].value)fail("prime-power premise produced a half-product collision");
    prefix.push(prefix[i]+rows[i].value);work.half_prefix_additions++;
    byMask.set(rows[i].mask,i);
  }
  return {factor_start:start,factor_count:count,rows,prefix,byMask};
}
function halfSnapshot(half) {
  return {factor_start:half.factor_start,factor_count:half.factor_count,
    rows:half.rows.map(r=>[String(r.value),r.mask.toString(16)]),prefix_sums:half.prefix.map(String)};
}

function createUnitaryDivisorIndex(options) {
  object(options,"options");
  const sid=sourceId(options.source_id),basis=normalizeBasis(options.prime_basis);
  const input=list(options.factors,"factors");
  if(input.length>UNITARY_DIVISOR_LIMITS.factors)fail("too many prime-power factors");
  const work=counters();work.constructors=1;work.prime_basis_rows_read=basis.primes.length;
  const admitted=new Set(basis.primes);
  const normalized=input.map((x,i)=>{
    object(x,"factor "+i);
    const p=String(uint(x.prime,"factor prime",UNITARY_DIVISOR_LIMITS.integer_digits,2n));
    if(!admitted.has(p))fail("factor prime is absent from the identified prime basis");
    return {prime:p,exponent:exponent(x.exponent)};
  }).sort((a,b)=>BigInt(a.prime)<BigInt(b.prime)?-1:BigInt(a.prime)>BigInt(b.prime)?1:0);
  let n=1n,sigma=1n;
  const np=[1n],sp=[1n],factors=[];
  for(let i=0;i<normalized.length;i++) {
    const f=normalized[i];
    if(i && normalized[i-1].prime===f.prime)fail("duplicate prime bases are not independent unitary blocks");
    const power=primePower(BigInt(f.prime),f.exponent,work);
    n=checkedProduct(n,power,UNITARY_DIVISOR_LIMITS.integer_digits,"factor product");work.factor_product_multiplications++;
    sigma=checkedProduct(sigma,power+1n,UNITARY_DIVISOR_LIMITS.arithmetic_digits,"unitary sum");work.sigma_product_multiplications++;
    factors.push({...f,power:String(power)});np.push(n);sp.push(sigma);work.factor_rows_read++;
  }
  const split=Math.floor(factors.length/2);
  const halves=[buildHalf(factors,0,split,work),buildHalf(factors,split,factors.length-split,work)];
  const total=1n<<BigInt(factors.length),root=integerSqrt(n,work);
  const square=root*root,successorSquare=(root+1n)*(root+1n);work.sqrt_bound_products+=2;
  if(square>n || successorSquare<=n)fail("integer square-root bound failed");
  const halfProduct=halves[0].rows.at(-1).value*halves[1].rows.at(-1).value;
  const halfSumProduct=halves[0].prefix.at(-1)*halves[1].prefix.at(-1);work.aggregate_products+=2;
  if(halfProduct!==n || halfSumProduct!==sigma)fail("half-product accounting failed");
  const data={
    schema:SCHEMA,source_id:sid,prime_basis:basis,factors,split,
    n:String(n),sqrt_n:String(root),unitary_count:String(total),proper_unitary_count:String(total-1n),
    sigma_unitary:String(sigma),proper_unitary_sum:String(sigma-n),
    unitary_perfect:sigma===2n*n,excess_sigma_over_twice_n:String(sigma-2n*n),
    halves:halves.map(halfSnapshot),
    arithmetic:{factor_product_prefixes:np.map(String),sigma_product_prefixes:sp.map(String),
      half_product:String(halfProduct),half_sum_product:String(halfSumProduct),
      sqrt_square:String(square),sqrt_successor_square:String(successorSquare)}
  };
  return instantiate(data,halves,work);
}

function normalizeSnapshot(snapshot,work) {
  object(snapshot,"snapshot");
  if(snapshot.schema!==SCHEMA)fail("unsupported saved schema");
  const sid=sourceId(snapshot.source_id),basis=normalizeBasis(snapshot.prime_basis);
  work.prime_basis_rows_read=basis.primes.length;
  const admitted=new Set(basis.primes),input=list(snapshot.factors,"factors");
  if(input.length>UNITARY_DIVISOR_LIMITS.factors)fail("too many saved factors");
  let previous=1n;
  const factors=input.map((f,i)=>{
    object(f,"factor");const p=dec(f.prime,"factor prime",UNITARY_DIVISOR_LIMITS.integer_digits,2n);
    if(p<=previous || !admitted.has(String(p)))fail("saved factors do not match an ordered prime basis");
    previous=p;const e=exponent(f.exponent),power=dec(f.power,"factor power",UNITARY_DIVISOR_LIMITS.integer_digits,2n);
    work.factor_rows_read++;return {prime:String(p),exponent:e,power:String(power)};
  });
  const split=Math.floor(factors.length/2);
  if(snapshot.split!==split)fail("saved split is not the canonical half split");
  const n=dec(snapshot.n,"n",UNITARY_DIVISOR_LIMITS.integer_digits,1n),root=dec(snapshot.sqrt_n,"sqrt_n",UNITARY_DIVISOR_LIMITS.integer_digits);
  if((factors.length===0)!==(n===1n))fail("empty factorization and n=1 must agree");
  const total=1n<<BigInt(factors.length);
  if(dec(snapshot.unitary_count,"unitary_count")!==total || dec(snapshot.proper_unitary_count,"proper_unitary_count")!==total-1n)
    fail("saved counts do not match subset-mask coverage");
  const sigma=dec(snapshot.sigma_unitary,"sigma_unitary",UNITARY_DIVISOR_LIMITS.arithmetic_digits,1n);
  if(sigma<n || dec(snapshot.proper_unitary_sum,"proper_unitary_sum")!==sigma-n ||
     snapshot.unitary_perfect!==(sigma===2n*n) || signedDec(snapshot.excess_sigma_over_twice_n,"excess")!==sigma-2n*n)
    fail("saved sum classification is inconsistent");
  const arithmetic=object(snapshot.arithmetic,"arithmetic");
  const np=list(arithmetic.factor_product_prefixes,"factor_product_prefixes",factors.length+1).map(x=>dec(x,"factor prefix",UNITARY_DIVISOR_LIMITS.integer_digits,1n));
  const sp=list(arithmetic.sigma_product_prefixes,"sigma_product_prefixes",factors.length+1).map(x=>dec(x,"sigma prefix",UNITARY_DIVISOR_LIMITS.arithmetic_digits,1n));
  if(np[0]!==1n || sp[0]!==1n || np.at(-1)!==n || sp.at(-1)!==sigma)fail("saved product-prefix endpoints disagree");
  for(let i=1;i<np.length;i++)if(np[i]<=np[i-1] || sp[i]<=sp[i-1])fail("saved product prefixes must increase");
  const square=root*root,successorSquare=(root+1n)*(root+1n);work.sqrt_bound_products+=2;
  if(square>n || successorSquare<=n || dec(arithmetic.sqrt_square,"sqrt square")!==square ||
     dec(arithmetic.sqrt_successor_square,"sqrt successor square")!==successorSquare)
    fail("saved square root is not the exact floor");
  const halfInput=list(snapshot.halves,"halves",2);
  const halves=halfInput.map((x,h)=>{
    object(x,"half");
    const start=h===0?0:split,count=h===0?split:factors.length-split,length=2**count;
    if(x.factor_start!==start || x.factor_count!==count || length>UNITARY_DIVISOR_LIMITS.half_records)
      fail("saved half metadata is invalid");
    const rr=list(x.rows,"half rows",length),pp=list(x.prefix_sums,"prefix sums",length+1);
    const prefix=pp.map(v=>dec(v,"prefix sum")),rows=[],byMask=new Map();
    if(prefix[0]!==0n)fail("prefix sums must start at zero");
    let last=0n;
    for(let i=0;i<length;i++) {
      const row=list(rr[i],"half row",2),value=dec(row[0],"half product",UNITARY_DIVISOR_LIMITS.integer_digits,1n),hex=row[1];
      if(value<=last || value>n)fail("saved half products must strictly increase within n");
      if(typeof hex!=="string" || hex.length>4 || !/^(0|[1-9a-f][0-9a-f]*)$/.test(hex))fail("noncanonical half mask");
      const mask=parseInt(hex,16);
      if(mask>=length || byMask.has(mask))fail("half mask is repeated or outside its bit universe");
      if(prefix[i+1]!==prefix[i]+value)fail("saved prefix sum does not match its row");
      work.prefix_equalities_checked++;
      rows.push({value,mask});byMask.set(mask,i);last=value;work.half_records_loaded++;work.mask_coverage_entries++;
    }
    if(rows[0].value!==1n || rows[0].mask!==0 || rows.at(-1).mask!==length-1)fail("half endpoints do not match empty/full masks");
    return {factor_start:start,factor_count:count,rows,prefix,byMask};
  });
  const halfProduct=halves[0].rows.at(-1).value*halves[1].rows.at(-1).value;
  const halfSumProduct=halves[0].prefix.at(-1)*halves[1].prefix.at(-1);work.aggregate_products+=2;
  if(halfProduct!==n || halfSumProduct!==sigma || dec(arithmetic.half_product,"half product")!==halfProduct ||
     dec(arithmetic.half_sum_product,"half sum product")!==halfSumProduct)fail("saved half totals disagree");
  // Coverage, sortedness, prefix equalities, and aggregate identities are checked.
  // Individual p^a values, mask-to-product identities, primality, completeness of
  // the prime basis, and external source identity remain identified premises.
  const data={schema:SCHEMA,source_id:sid,prime_basis:basis,factors,split,n:String(n),sqrt_n:String(root),
    unitary_count:String(total),proper_unitary_count:String(total-1n),
    sigma_unitary:String(sigma),proper_unitary_sum:String(sigma-n),unitary_perfect:snapshot.unitary_perfect,
    excess_sigma_over_twice_n:String(sigma-2n*n),halves:halves.map(halfSnapshot),
    arithmetic:{factor_product_prefixes:np.map(String),sigma_product_prefixes:sp.map(String),
      half_product:String(halfProduct),half_sum_product:String(halfSumProduct),
      sqrt_square:String(square),sqrt_successor_square:String(successorSquare)}};
  return {data,halves};
}
function openRetainedUnitaryDivisorIndex(snapshot) {
  const work=counters();work.saved_opens=1;
  const normalized=normalizeSnapshot(snapshot,work);
  return instantiate(normalized.data,normalized.halves,work);
}

function instantiate(data,halves,work) {
  const n=BigInt(data.n),root=BigInt(data.sqrt_n),sigma=BigInt(data.sigma_unitary),total=BigInt(data.unitary_count);
  const left=halves[0],right=halves[1],powers=data.factors.map(f=>BigInt(f.power));
  const allMask=(1n<<BigInt(powers.length))-1n,leftMask=(1n<<BigInt(data.split))-1n;
  const countCache=new Map(),selectCache=new Map();
  function put(cache,key,value,limit) {
    if(cache.has(key))cache.delete(key);
    cache.set(key,value);
    if(cache.size>limit)cache.delete(cache.keys().next().value);
  }
  function threshold(x,wantSum,wantFrontier) {
    const cut=wantFrontier?new Array(left.rows.length).fill(0):null;
    if(x<1n)return {count:0n,sum:wantSum?0n:null,cut};
    if(x>=n){
      if(cut)cut.fill(right.rows.length);
      return {count:total,sum:wantSum?sigma:null,cut};
    }
    work.threshold_scans++;
    let j=right.rows.length-1,count=0n,sum=0n;
    for(let i=0;i<left.rows.length;i++) {
      work.threshold_left_rows++;
      while(j>=0) {
        const p=left.rows[i].value*right.rows[j].value;work.threshold_product_comparisons++;
        if(p<=x)break;
        j--;
      }
      if(j<0)break;
      const length=j+1;count+=BigInt(length);
      if(wantSum){sum+=left.rows[i].value*right.prefix[length];work.threshold_sum_products++;}
      if(cut)cut[i]=length;
    }
    put(countCache,String(x),count,UNITARY_DIVISOR_LIMITS.count_cache);
    return {count,sum:wantSum?sum:null,cut};
  }
  function countAll(x) {
    if(x<1n)return 0n;
    if(x>=n)return total;
    const key=String(x);
    if(countCache.has(key)){work.count_cache_hits++;return countCache.get(key);}
    return threshold(x,false,false).count;
  }
  function prefixRecord(x,kind,includeFrontier) {
    const r=threshold(x,true,includeFrontier),exclude=kind==="proper" && x>=n;
    return {bound:String(x),kind,count:String(r.count-(exclude?1n:0n)),sum:String(r.sum-(exclude?n:0n)),
      all_count:String(r.count),all_sum:String(r.sum),excluded_full_value:exclude?String(n):null,
      frontier:r.cut===null?null:{right_counts_by_left:r.cut,left_rows:left.rows.length,right_rows:right.rows.length,
        interpretation:"All-divisor row cutoffs before any proper-divisor exclusion."}};
  }
  function gcd(a,b) {
    while(b!==0n){const r=a%b;work.gcd_modulos++;a=b;b=r;}return a;
  }
  function witness(value,pair=null) {
    let li,ri,mask;
    if(pair!==null) {
      li=pair.left;ri=pair.right;
      mask=BigInt(left.rows[li].mask)|(BigInt(right.rows[ri].mask)<<BigInt(data.split));
    }else{
      let remaining=value;mask=0n;
      for(let i=0;i<powers.length;i++) {
        work.membership_modulos++;
        if(remaining%powers[i]===0n){remaining/=powers[i];work.membership_divisions++;mask|=1n<<BigInt(i);}
      }
      if(remaining!==1n)fail("selected value contradicts the supplied whole-power factorization");
      const lm=Number(mask&leftMask),rm=Number(mask>>BigInt(data.split));
      li=left.byMask.get(lm);ri=right.byMask.get(rm);
      if(li===undefined || ri===undefined)fail("saved mask index is incomplete");
      const represented=left.rows[li].value*right.rows[ri].value;work.witness_products++;
      if(represented!==value)fail("saved mask-to-product premise contradicts this query");
    }
    work.membership_modulos++;
    if(n%value!==0n)fail("saved table value is not a divisor of n");
    const quotient=n/value;work.membership_divisions++;
    const selected=[];
    for(let i=0;i<powers.length;i++)if(mask&(1n<<BigInt(i)))selected.push(i);
    return {value:String(value),proper:value<n,quotient:String(quotient),
      subset_mask_hex:mask.toString(16),complement_mask_hex:(allMask^mask).toString(16),
      selected_factor_indices:selected,left_row:li,right_row:ri,
      left_product:String(left.rows[li].value),right_product:String(right.rows[ri].value)};
  }
  function selectCore(rank) {
    const key=String(rank);
    if(selectCache.has(key)){
      work.select_cache_hits++;
      return {value:selectCache.get(key),trace:{method:"cached_rank",rank:key}};
    }
    let value,trace;
    if(rank===0n){value=1n;trace={method:"first_divisor"};}
    else if(rank===total-1n){value=n;trace={method:"last_divisor"};}
    else if(rank>=total/2n) {
      const reflected=total-1n-rank,lower=selectCore(reflected);
      value=n/lower.value;work.membership_divisions++;
      trace={method:"complement_reflection",reflected_rank:String(reflected),reflected_value:String(lower.value),
        reflected_trace:lower.trace};
    }else{
      let low=1n,high=root;const steps=[];
      while(low<high) {
        const mid=(low+high)/2n,count=countAll(mid);work.selection_bisection_steps++;
        steps.push([String(mid),String(count)]);
        if(count<=rank)low=mid+1n;else high=mid;
      }
      value=low;trace={method:"lower_half_bisection",initial_low:"1",initial_high:String(root),steps};
    }
    put(selectCache,key,value,UNITARY_DIVISOR_LIMITS.select_cache);
    return {value,trace};
  }
  function select(rankInput,options={}) {
    object(options,"select options");const kind=kindName(options);
    const rank=uint(rankInput,"rank",UNITARY_DIVISOR_LIMITS.arithmetic_digits),available=total-(kind==="proper"?1n:0n);
    if(rank>=available)fail("rank is outside the selected divisor family");
    work.select_queries++;
    const chosen=selectCore(rank),entry=witness(chosen.value);work.returned_divisors++;
    return {kind,rank:String(rank),...entry,selection:chosen.trace};
  }
  function rank(valueInput,options={}) {
    object(options,"rank options");const kind=kindName(options),value=uint(valueInput,"divisor",UNITARY_DIVISOR_LIMITS.integer_digits,1n);
    work.rank_queries++;work.membership_modulos++;
    const remainder=n%value;
    if(remainder!==0n)return {status:"not_divisor",kind,value:String(value),n:String(n),remainder:String(remainder)};
    const quotient=n/value;work.membership_divisions++;
    const common=gcd(value,quotient);
    if(common!==1n)return {status:"not_unitary",kind,value:String(value),quotient:String(quotient),gcd:String(common)};
    if(kind==="proper" && value===n)return {status:"not_proper",kind,value:String(value),quotient:String(quotient),gcd:"1"};
    const r=countAll(value-1n),entry=witness(value);
    put(selectCache,String(r),value,UNITARY_DIVISOR_LIMITS.select_cache);
    return {status:"found",kind,rank:String(r),...entry,gcd:"1"};
  }
  function page(startInput,options={}) {
    object(options,"page options");const kind=kindName(options),start=uint(startInput,"page start",UNITARY_DIVISOR_LIMITS.arithmetic_digits);
    const limit=options.limit===undefined?UNITARY_DIVISOR_LIMITS.page_size:options.limit;
    if(!Number.isSafeInteger(limit)||limit<1||limit>UNITARY_DIVISOR_LIMITS.page_size)fail("page limit is outside its bounds");
    const available=total-(kind==="proper"?1n:0n);
    if(start>available)fail("page starts beyond the selected divisor family");
    work.page_queries++;
    if(start===available)return {kind,start:String(start),returned:0,total:String(available),next_rank:null,start_selection:null,records:[]};
    const chosen=selectCore(start),heap=[];
    function less(a,b) {
      work.heap_comparisons++;
      return a.value<b.value || (a.value===b.value && (a.left<b.left || (a.left===b.left && a.right<b.right)));
    }
    function push(node) {
      work.heap_pushes++;heap.push(node);let i=heap.length-1;
      while(i>0){const p=Math.floor((i-1)/2);if(!less(heap[i],heap[p]))break;[heap[i],heap[p]]=[heap[p],heap[i]];i=p;}
    }
    function pop() {
      work.heap_pops++;
      const result=heap[0],last=heap.pop();
      if(heap.length){heap[0]=last;let i=0;while(true){
        const l=2*i+1,r=l+1;let best=i;
        if(l<heap.length&&less(heap[l],heap[best]))best=l;
        if(r<heap.length&&less(heap[r],heap[best]))best=r;
        if(best===i)break;[heap[i],heap[best]]=[heap[best],heap[i]];i=best;
      }}
      return result;
    }
    let j=right.rows.length;
    for(let i=0;i<left.rows.length;i++) {
      while(j>0) {
        const value=left.rows[i].value*right.rows[j-1].value;work.heap_seed_comparisons++;
        if(value<chosen.value)break;
        j--;
      }
      if(j<right.rows.length) {
        const value=left.rows[i].value*right.rows[j].value;work.heap_seed_products++;
        push({value,left:i,right:j});
      }
    }
    const rows=[];let cursor=start,previous=0n;
    while(rows.length<limit && cursor<available) {
      if(heap.length===0)fail("saved product streams ended before the declared count");
      const item=pop();
      if((rows.length===0&&item.value!==chosen.value) || (rows.length>0&&item.value<=previous))
        fail("saved product streams contradict numerical rank or uniqueness");
      if(kind==="proper" && item.value===n)fail("full divisor appeared before the proper-family endpoint");
      const entry=witness(item.value,item);work.returned_divisors++;
      rows.push({rank:String(cursor),...entry});previous=item.value;cursor++;
      const next=item.right+1;
      if(next<right.rows.length) {
        const value=left.rows[item.left].value*right.rows[next].value;work.heap_advance_products++;
        push({value,left:item.left,right:next});
      }
    }
    if(cursor<available && heap.length)put(selectCache,String(cursor),heap[0].value,UNITARY_DIVISOR_LIMITS.select_cache);
    return {kind,start:String(start),returned:rows.length,total:String(available),
      next_rank:cursor===available?null:String(cursor),start_selection:chosen.trace,records:rows};
  }
  return Object.freeze({
    summary(){
      return copy({schema:SCHEMA,source_id:data.source_id,prime_source_id:data.prime_basis.source_id,
        factor_count:data.factors.length,factors:data.factors,n:data.n,sqrt_n:data.sqrt_n,
        unitary_count:data.unitary_count,proper_unitary_count:data.proper_unitary_count,
        sigma_unitary:data.sigma_unitary,proper_unitary_sum:data.proper_unitary_sum,
        unitary_perfect:data.unitary_perfect,excess_sigma_over_twice_n:data.excess_sigma_over_twice_n,
        half_record_counts:halves.map(h=>h.rows.length),order:"Increasing numerical divisor value; zero-based rank."});
    },
    count(options={}){object(options,"count options");const kind=kindName(options);work.count_queries++;return String(total-(kind==="proper"?1n:0n));},
    prefix(bound,options={}){
      object(options,"prefix options");const kind=kindName(options),include=flag(options,"include_frontier");
      const x=uint(bound,"prefix bound");work.prefix_queries++;return prefixRecord(x,kind,include);
    },
    interval(lo,hi,options={}){
      object(options,"interval options");const kind=kindName(options),include=flag(options,"include_frontiers");
      const a=uint(lo,"interval lower bound"),b=uint(hi,"interval upper bound");
      if(a>b)fail("interval lower bound exceeds upper bound");work.interval_queries++;
      const lower=prefixRecord(a-1n,kind,include),upper=prefixRecord(b,kind,include);
      return {kind,lo:String(a),hi:String(b),count:String(BigInt(upper.count)-BigInt(lower.count)),
        sum:String(BigInt(upper.sum)-BigInt(lower.sum)),lower_prefix:lower,upper_prefix:upper};
    },
    rank,select,page,
    snapshot(){return copy(data);},
    work(){return {...work,count_cache_entries:countCache.size,select_cache_entries:selectCache.size};}
  });
}

module.exports={
  factorialPrimePowerInput,createUnitaryDivisorIndex,openRetainedUnitaryDivisorIndex,UNITARY_DIVISOR_LIMITS
};
