"use strict";
const SCHEMA="binomial-prime-valuation-index/v1";
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name);return x;}
function decimal(s,name){if(typeof s!=="string"||!/^(0|[1-9][0-9]*)$/.test(s))throw new TypeError(name+" decimal string required");return BigInt(s);}
function construct(input){
 const N=integer(input.max_n,"max_n",2,4096),primes=input.primes;
 if(!Array.isArray(primes)||!primes.length||primes[0]!==2)throw new TypeError("complete prime prefix premise");
 primes.forEach((p,i)=>{integer(p,"prime premise",2,N);if(i&&p<=primes[i-1])throw new RangeError("ordered prime premises");});
 integer(input.next_prime,"next prime premise",N+1,Number.MAX_SAFE_INTEGER);
 const limits=Object.assign({max_rows:200000,max_factorial_cells:250000,max_valuation_cells:3000000,max_nonzero_factors:1000000},input.limits||{});
 Object.entries(limits).forEach(([k,v])=>integer(v,k,1,Number.MAX_SAFE_INTEGER));
 const count=Math.floor(N*N/4),P=primes.length;
 if(count>limits.max_rows||(N+1)*P>limits.max_factorial_cells||count*P>limits.max_valuation_cells)throw new RangeError("predeclared construction cap");
 const work={factorial_cells:0,legendre_floor_divisions:0,legendre_additions:0,rows:0,valuation_cells:0,valuation_subtractions:0,nonzero_factors:0,threshold_floor_divisions:0,least_prime_histogram_additions:0,exception_index_entries:0,primality_tests:0,sieve_steps:0,binomial_integer_products:0};
 const factorial=[];
 for(const p of primes){
  const row=[0];++work.factorial_cells;
  for(let n=1;n<=N;n++){
   let q=n,v=0;
   for(;;){q=Math.floor(q/p);++work.legendre_floor_divisions;if(!q)break;v+=q;++work.legendre_additions;}
   row.push(v);++work.factorial_cells;
  }
  factorial.push(row);
 }
 const rows=[],offsets=Array(N+2).fill(0),byN=[],leastCounts=Array(P).fill(0),exceptions=[];
 for(let n=0;n<=N;n++){
  offsets[n]=rows.length;let ne=0;
  for(let k=1;k<=Math.floor(n/2);k++){
   const factors=[];let least=-1,total=0,squarefree=true;
   for(let pi=0;pi<P;pi++){
    const e=factorial[pi][n]-factorial[pi][k]-factorial[pi][n-k];
    ++work.valuation_cells;work.valuation_subtractions+=2;
    if(e<0)throw new Error("negative binomial valuation");
    if(e){if(work.nonzero_factors>=limits.max_nonzero_factors)throw new RangeError("nonzero factor cap");
     if(least<0)least=pi;factors.push([pi,e]);total+=e;if(e>1)squarefree=false;++work.nonzero_factors;}
   }
   if(least<0)throw new Error("positive-k binomial coefficient has no prime divisor");
   const threshold=Math.max(Math.floor(n/k),k);++work.threshold_floor_divisions;
   const exceptional=primes[least]>threshold,id=rows.length;
   rows.push([n,k,least,threshold,exceptional?1:0,total,squarefree?1:0,factors]);
   ++leastCounts[least];++work.least_prime_histogram_additions;++work.rows;
   if(exceptional){exceptions.push(id);++ne;++work.exception_index_entries;}
  }
  byN.push({n,start:offsets[n],end:rows.length,count:rows.length-offsets[n],exceptional:ne});
 }
 offsets[N+1]=rows.length;
 if(rows.length!==count)throw new Error("triangle cardinality");
 return {schema:SCHEMA,max_n:N,primes:primes.slice(),next_prime:input.next_prime,
  prime_contract:"Input is the complete prime prefix through max_n with the next prime supplied as a boundary premise; no primality or completeness proof is recomputed.",
  domain:"2<=n<=max_n, 1<=k<=floor(n/2)",order:"increasing n, then increasing k; zero-based ranks",
  row_fields:["n","k","least_prime_index","threshold","exceptional_bit","total_prime_exponent","squarefree_bit","positive_factors_as_prime_index_exponent_pairs"],
  factorial_valuations:factorial,rows,row_offsets:offsets,by_n:byN,
  least_prime_counts:leastCounts,exception_row_ids:exceptions,limits,provenance:input.provenance||{},work};
}
function open(s){
 if(!s||s.schema!==SCHEMA||!Array.isArray(s.rows)||!Array.isArray(s.primes)||!Array.isArray(s.factorial_valuations))throw new TypeError("snapshot");
 const N=s.max_n,P=s.primes.length;
 if(s.rows.length!==Math.floor(N*N/4)||s.row_offsets.length!==N+2||s.factorial_valuations.length!==P)throw new TypeError("snapshot shape");
 const work={queries:0,conditions_compiled:0,condition_cache_hits:0,saved_row_scans:0,valuation_filter_checks:0,factor_binary_probes:0,conditional_entries:0,rank_binary_probes:0,row_lookups:0,factorial_lookups:0,factor_output_pairs:0,exact_power_squarings:0,exact_power_multiplies:0,exact_factor_products:0,modular_power_squarings:0,modular_power_multiplies:0,modular_factor_products:0,modular_reductions:0,constructor_calls:0,new_factorial_cells:0,new_binomial_valuation_cells:0,primality_tests:0,sieve_steps:0};
 const caches=new Map();
 function rowId(n,k){integer(n,"n",2,N);integer(k,"k",1,Math.floor(n/2));return s.row_offsets[n]+k-1;}
 function get(id){integer(id,"row id",0,s.rows.length-1);++work.row_lookups;return s.rows[id];}
 function valuationCore(r,pi){
  let lo=0,hi=r[7].length;
  while(lo<hi){const m=Math.floor((lo+hi)/2);++work.factor_binary_probes;if(r[7][m][0]<pi)lo=m+1;else hi=m;}
  return lo<r[7].length&&r[7][lo][0]===pi?r[7][lo][1]:0;
 }
 function describe(id,includeFactors=true){
  const r=get(id),out={id,n:r[0],k:r[1],least_prime_index:r[2],least_prime:s.primes[r[2]],threshold:r[3],exceptional:!!r[4],distinct_prime_factors:r[7].length,total_prime_exponent:r[5],squarefree:!!r[6]};
  if(includeFactors)out.factors=r[7].map(([pi,e])=>{++work.factor_output_pairs;return{prime_index:pi,prime:s.primes[pi],exponent:e};});
  return out;
 }
 function normalize(o={}){
  const c={min_n:o.min_n===undefined?2:integer(o.min_n,"min_n",2,N),max_n:o.max_n===undefined?N:integer(o.max_n,"max_n",2,N),
   min_k:o.min_k===undefined?1:integer(o.min_k,"min_k",1,Math.floor(N/2)),max_k:o.max_k===undefined?Math.floor(N/2):integer(o.max_k,"max_k",1,Math.floor(N/2)),
   least_prime_min:o.least_prime_min===undefined?2:integer(o.least_prime_min,"least_prime_min",2,N),least_prime_max:o.least_prime_max===undefined?N:integer(o.least_prime_max,"least_prime_max",2,N),
   exceptional:o.exceptional===undefined?null:o.exceptional,squarefree:o.squarefree===undefined?null:o.squarefree,
   min_distinct_factors:o.min_distinct_factors===undefined?1:integer(o.min_distinct_factors,"min_distinct_factors",0,P),
   max_distinct_factors:o.max_distinct_factors===undefined?P:integer(o.max_distinct_factors,"max_distinct_factors",0,P),valuations:[]};
  if((c.exceptional!==null&&typeof c.exceptional!=="boolean")||(c.squarefree!==null&&typeof c.squarefree!=="boolean"))throw new TypeError("boolean condition");
  if(c.min_n>c.max_n||c.min_k>c.max_k||c.least_prime_min>c.least_prime_max||c.min_distinct_factors>c.max_distinct_factors)throw new RangeError("contradictory bounds");
  if(o.valuations!==undefined){
   if(!Array.isArray(o.valuations)||o.valuations.length>P)throw new TypeError("valuation conditions");
   c.valuations=o.valuations.map(v=>({prime_index:integer(v.prime_index,"prime_index",0,P-1),min:v.min===undefined?0:integer(v.min,"valuation min",0,N),max:v.max===undefined?N:integer(v.max,"valuation max",0,N)})).sort((a,b)=>a.prime_index-b.prime_index);
   c.valuations.forEach((v,i)=>{if(v.min>v.max||(i&&v.prime_index===c.valuations[i-1].prime_index))throw new RangeError("duplicate or contradictory valuation");});
  }
  return c;
 }
 function compile(options){
  const c=normalize(options),key=JSON.stringify(c);
  if(caches.has(key)){++work.condition_cache_hits;return caches.get(key);}
  ++work.conditions_compiled;const ids=[];
  for(let id=0;id<s.rows.length;id++){
   ++work.saved_row_scans;const r=s.rows[id],least=s.primes[r[2]];
   if(r[0]<c.min_n||r[0]>c.max_n||r[1]<c.min_k||r[1]>c.max_k||least<c.least_prime_min||least>c.least_prime_max||
    (c.exceptional!==null&&!!r[4]!==c.exceptional)||(c.squarefree!==null&&!!r[6]!==c.squarefree)||r[7].length<c.min_distinct_factors||r[7].length>c.max_distinct_factors)continue;
   let pass=true;
   for(const v of c.valuations){++work.valuation_filter_checks;const e=valuationCore(r,v.prime_index);if(e<v.min||e>v.max){pass=false;break;}}
   if(pass){ids.push(id);++work.conditional_entries;}
  }
  const cache={key,condition:c,count:String(ids.length),row_ids:ids};caches.set(key,cache);return cache;
 }
 function locate(ids,id){let lo=0,hi=ids.length;while(lo<hi){const m=Math.floor((lo+hi)/2);++work.rank_binary_probes;if(ids[m]<id)lo=m+1;else hi=m;}return lo;}
 function power(base,e,mod){
  let answer=1n,b=BigInt(base),left=e;
  if(mod!==null){b%=mod;answer%=mod;work.modular_reductions+=2;}
  while(left>0){
   if(left%2){answer*=b;if(mod!==null){answer%=mod;++work.modular_power_multiplies;++work.modular_reductions;}else ++work.exact_power_multiplies;}
   left=Math.floor(left/2);
   if(left){b*=b;if(mod!==null){b%=mod;++work.modular_power_squarings;++work.modular_reductions;}else ++work.exact_power_squarings;}
  }
  return answer;
 }
 return{
  summary(){++work.queries;return{max_n:N,domain:s.domain,order:s.order,primes:s.primes,next_prime:s.next_prime,rows:s.rows.length,exceptions:s.exception_row_ids.length,exception_row_ids:s.exception_row_ids,least_prime_counts:s.least_prime_counts,construction_work:s.work};},
  family(options){++work.queries;const c=compile(options);return{condition:c.condition,count:c.count};},
  select(rank,options){++work.queries;const c=compile(options),r=decimal(rank,"rank");if(r>=BigInt(c.row_ids.length))throw new RangeError("rank");return{condition:c.condition,count:c.count,rank:rank,row:describe(c.row_ids[Number(r)])};},
  rank(n,k,options){++work.queries;const id=rowId(n,k),c=compile(options),r=locate(c.row_ids,id),member=c.row_ids[r]===id;return{condition:c.condition,count:c.count,member,rank:member?String(r):null,row:describe(id,false)};},
  page(start,limit,options){++work.queries;const c=compile(options),r=decimal(start,"start");integer(limit,"limit",0,200);if(r>BigInt(c.row_ids.length))throw new RangeError("page");const end=Math.min(c.row_ids.length,Number(r)+limit);return{condition:c.condition,count:c.count,start,rows:c.row_ids.slice(Number(r),end).map((id,j)=>({rank:String(Number(r)+j),row:describe(id)})),next_rank:String(end),complete:end===c.row_ids.length};},
  row(n,k){++work.queries;return describe(rowId(n,k));},
  valuation(n,k,primeIndex){++work.queries;integer(primeIndex,"prime_index",0,P-1);const r=get(rowId(n,k));return{n,k,prime_index:primeIndex,prime:s.primes[primeIndex],exponent:valuationCore(r,primeIndex)};},
  factorial(n,primeIndex){++work.queries;integer(n,"n",0,N);integer(primeIndex,"prime_index",0,P-1);++work.factorial_lookups;return{n,prime_index:primeIndex,prime:s.primes[primeIndex],exponent:s.factorial_valuations[primeIndex][n]};},
  integer(n,k){++work.queries;const id=rowId(n,k),r=get(id);let value=1n;for(const [pi,e]of r[7]){value*=power(s.primes[pi],e,null);++work.exact_factor_products;}return{row:describe(id,false),value:value.toString()};},
  modulo(n,k,modulus){++work.queries;const mod=decimal(modulus,"modulus");if(mod===0n)throw new RangeError("positive modulus required");const id=rowId(n,k),r=get(id);let value=1n%mod;++work.modular_reductions;for(const [pi,e]of r[7]){value=value*power(s.primes[pi],e,mod)%mod;++work.modular_factor_products;++work.modular_reductions;}return{row:describe(id,false),modulus,residue:value.toString()};},
  byN(n){++work.queries;integer(n,"n",0,N);return s.by_n[n];},
  caches(){return [...caches.values()];},
  work(){return Object.assign({},work);}
 };
}
module.exports={SCHEMA,construct,open};
