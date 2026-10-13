"use strict";
const SCHEMA="normalized-prime-gap-order/v1",copy=x=>JSON.parse(JSON.stringify(x));
function fail(s){throw new TypeError(s);}
function nat(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function sign(a,b){return a<b?-1:a>b?1:0;}
function gcd(a,b){while(b){const r=a%b;a=b;b=r;}return a;}
function frac(a,b){const g=gcd(a,b);return {n:String(a/g),d:String(b/g)};}
function compile(input){
 if(!input||!Array.isArray(input.primes)||input.primes.length<4||input.primes.length>4096||!input.provenance)fail("identified prime list required");
 let prev=1;for(const p of input.primes){nat(p,2,10000000,"prime");if(p<=prev)fail("increasing prime premise required");prev=p;}
 const first=nat(input.first_index,2,input.primes.length-2,"first index"),last=nat(input.last_index,first,input.primes.length-2,"last index");
 const work={gap_subtractions:0,integer_powers:0,power_cache_hits:0,sort_comparisons:0,adjacent_certificates:0,logarithm_series_terms:0,prime_tests:0,old_sieve_work:0};
 const rows=[];for(let n=first;n<=last;n++){const gap=input.primes[n+1]-input.primes[n];nat(gap,1,512,"gap");work.gap_subtractions++;rows.push({n,prime:input.primes[n],next_prime:input.primes[n+1],gap});}
 const powers=new Map();function power(b,e){const k=b+":"+e;if(powers.has(k)){work.power_cache_hits++;return powers.get(k);}const v=BigInt(b)**BigInt(e);work.integer_powers++;powers.set(k,v);return v;}
 function cmp(a,b){const left=power(b.n,a.gap),right=power(a.n,b.gap);return {left,right,comparison:sign(left,right)};}
 const sorted=rows.slice().sort((a,b)=>{work.sort_comparisons++;return cmp(a,b).comparison||a.n-b.n;});
 const adjacent=[],groups=[];let group=null;
 for(let i=0;i<sorted.length;i++){
  let comparison=-1;if(i){const a=sorted[i-1],b=sorted[i],c=cmp(a,b);if(c.comparison>0)fail("order contradiction");comparison=c.comparison;adjacent.push({left_n:a.n,right_n:b.n,left_power:String(c.left),right_power:String(c.right),comparison});work.adjacent_certificates++;}
  if(!i||comparison!==0){group={id:groups.length,start_rank:i,indices:[]};groups.push(group);}group.indices.push(sorted[i].n);
 }
 const gap_histogram={};for(const r of rows)gap_histogram[r.gap]=(gap_histogram[r.gap]||0)+1;
 return {schema:SCHEMA,first_index:first,last_index:last,prime_count:input.primes.length,primes:input.primes.slice(),provenance:copy(input.provenance),rows,order:sorted.map(r=>r.n),groups,adjacent,gap_histogram,work};
}
function openIndex(snapshot){
 if(!snapshot||snapshot.schema!==SCHEMA)fail("bad schema");const d=copy(snapshot),first=nat(d.first_index,2,4094,"first"),last=nat(d.last_index,first,4094,"last"),count=last-first+1;
 if(!Array.isArray(d.rows)||d.rows.length!==count||!Array.isArray(d.order)||d.order.length!==count||!Array.isArray(d.adjacent)||d.adjacent.length!==count-1)fail("bad dimensions");
 const byN=new Map(),rankByN=new Map(),groupByN=new Map();
 for(let i=0;i<count;i++){const r=d.rows[i];if(r.n!==first+i)fail("nonconsecutive rows");nat(r.prime,2,10000000,"prime");nat(r.next_prime,r.prime+1,10000000,"next prime");nat(r.gap,1,512,"gap");byN.set(r.n,r);}
 d.order.forEach((n,i)=>{nat(n,first,last,"ordered index");if(rankByN.has(n))fail("repeated ordered index");rankByN.set(n,i);});
 let cursor=0;if(!Array.isArray(d.groups))fail("groups required");for(let g=0;g<d.groups.length;g++){const x=d.groups[g];if(x.id!==g||x.start_rank!==cursor||!Array.isArray(x.indices)||x.indices.length===0)fail("bad group");for(const n of x.indices){if(d.order[cursor++]!==n)fail("bad group coverage");groupByN.set(n,g);}}
 if(cursor!==count)fail("incomplete groups");
 for(let i=0;i<d.adjacent.length;i++){const a=d.adjacent[i];if(a.left_n!==d.order[i]||a.right_n!==d.order[i+1]||typeof a.left_power!=="string"||typeof a.right_power!=="string"||!/^[1-9][0-9]*$/.test(a.left_power)||!/^[1-9][0-9]*$/.test(a.right_power))fail("bad adjacent certificate");const cmp=sign(BigInt(a.left_power),BigInt(a.right_power));if(cmp>0||cmp!==a.comparison||(cmp===0)!==(groupByN.get(a.left_n)===groupByN.get(a.right_n)))fail("inconsistent saved adjacency");}
 const work={queries:0,rows_loaded:count,adjacent_integer_comparisons:d.adjacent.length,condition_rows_scanned:0,conditions_created:0,condition_cache_hits:0,threshold_integer_powers:0,threshold_power_cache_hits:0,threshold_comparisons:0,range_order_powers:0,series_values:0,series_cache_hits:0,series_terms:0,series_floor_divisions:0,series_tail_bounds:0,log_cache_hits:0,gap_subtractions:0,constructor_order_powers:0,sort_comparisons:0,prime_tests:0,old_sieve_work:0};
 const conditions=new Map(),seriesCache=new Map(),logCache=new Map();
 function normalize(f={}){
  if(!f||typeof f!=="object"||Array.isArray(f))fail("filter required");for(const k of Object.keys(f))if(!["first_index","last_index","min_gap","max_gap"].includes(k))fail("unknown filter");
  const x={first_index:f.first_index===undefined?first:nat(f.first_index,first,last,"filter first"),last_index:f.last_index===undefined?last:nat(f.last_index,first,last,"filter last"),min_gap:f.min_gap===undefined?1:nat(f.min_gap,1,512,"min gap"),max_gap:f.max_gap===undefined?512:nat(f.max_gap,1,512,"max gap")};
  if(x.first_index>x.last_index||x.min_gap>x.max_gap)fail("reversed filter");return x;
 }
 function condition(f){const filter=normalize(f),key=JSON.stringify(filter);if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}if(conditions.size>=16)fail("16 condition limit");
  const indices=d.order.filter(n=>{work.condition_rows_scanned++;const r=byN.get(n);return n>=filter.first_index&&n<=filter.last_index&&r.gap>=filter.min_gap&&r.gap<=filter.max_gap;});
  const c={filter,indices};conditions.set(key,c);work.conditions_created++;return c;
 }
 function record(n){nat(n,first,last,"index");const r=byN.get(n),g=d.groups[groupByN.get(n)];return {...r,global_rank:rankByN.get(n),global_group:g.id,global_tie_indices:g.indices};}
 function threshold(t){if(!t||typeof t!=="object")fail("threshold required");return {a:nat(t.a,0,64,"threshold numerator"),d:t.d===undefined?1:nat(t.d,1,16,"threshold denominator"),b:nat(t.b,2,1000000,"threshold log argument")};}
 function cdf(c,t){
  const value=threshold(t),cache=new Map(),trace=[];
  function power(b,e){const k=b+":"+e;if(cache.has(k)){work.threshold_power_cache_hits++;return cache.get(k);}const v=BigInt(b)**BigInt(e);work.threshold_integer_powers++;cache.set(k,v);return v;}
  function cmp(j){const n=c.indices[j],r=byN.get(n),left=power(value.b,value.d*r.gap),right=power(n,value.a),comparison=sign(left,right);work.threshold_comparisons++;trace.push({position:j,n,gap:r.gap,left_power:String(left),right_power:String(right),comparison});return comparison;}
  function bound(strict){let lo=0,hi=c.indices.length;while(lo<hi){const mid=(lo+hi)>>1,x=cmp(mid);if(strict?x<=0:x<0)lo=mid+1;else hi=mid;}return lo;}
  const less=bound(false),through=bound(true);
  return {threshold:value,filter:c.filter,total:c.indices.length,less,equal:through-less,greater:c.indices.length-through,equal_indices:c.indices.slice(less,through),strict_fraction:frac(BigInt(less),BigInt(c.indices.length||1)),empty_family:c.indices.length===0,trace};
 }
 function series(a,b){
  const divisor=gcd(a,b);a/=divisor;b/=divisor;const key=a+":"+b;if(seriesCache.has(key)){work.series_cache_hits++;return seriesCache.get(key);}
  const S=1n<<128n,T=48,aa=a*a,bb=b*b;let pa=a,pb=b,L=0n,round=0;const floors=[];
  for(let j=0;j<T;j++){const numerator=2n*S*pa,denominator=pb*BigInt(2*j+1),q=numerator/denominator;floors.push(String(q));L+=q;if(numerator%denominator!==0n)round++;pa*=aa;pb*=bb;work.series_terms++;work.series_floor_divisions++;}
  const tn=2n*S*pa*bb,td=BigInt(2*T+1)*pb*(bb-aa),tail=(tn+td-1n)/td,U=L+BigInt(round)+tail;work.series_tail_bounds++;work.series_values++;
  const out={a:String(a),b:String(b),terms:T,scale:String(S),term_floors:floors,lower:String(L),rounding_units:round,tail_numerator:String(tn),tail_denominator:String(td),tail_ceiling:String(tail),upper:String(U)};seriesCache.set(key,out);return out;
 }
 function logarithm(n){
  if(logCache.has(n)){work.log_cache_hits++;return logCache.get(n);}
  let k=0,p=1;while(2*p<=n){p*=2;k++;}const log2=series(1n,3n),local=series(BigInt(n-p),BigInt(n+p));
  const lower=BigInt(k)*BigInt(log2.lower)+BigInt(local.lower),upper=BigInt(k)*BigInt(log2.upper)+BigInt(local.upper);
  if(lower<=0n)fail("log lower bound not positive");const out={n,k,power_of_two:p,scale:log2.scale,lower:String(lower),upper:String(upper),log2,local};logCache.set(n,out);return out;
 }
 function query(q){
  if(!q||typeof q!=="object")fail("query required");work.queries++;
  if(q.op==="summary")return {schema:SCHEMA,first_index:first,last_index:last,records:count,tie_groups:d.groups.length,nontrivial_ties:d.groups.filter(g=>g.indices.length>1),gap_histogram:d.gap_histogram,minimum:record(d.order[0]),maximum:record(d.order.at(-1)),construction_work:d.work};
  if(q.op==="record")return record(q.n);
  if(q.op==="groups")return d.groups.filter(g=>q.nontrivial!==true||g.indices.length>1);
  if(q.op==="adjacent"){const start=nat(q.start??0,0,d.adjacent.length,"start"),limit=nat(q.limit??20,0,2000,"limit");return {start,total:d.adjacent.length,records:d.adjacent.slice(start,start+limit)};}
  if(q.op==="approximate"){
   const r=record(q.n),log=logarithm(r.n),num=BigInt(r.gap)*BigInt(log.scale);return {...r,lower:frac(num,BigInt(log.upper)),upper:frac(num,BigInt(log.lower)),log_certificate:log};
  }
  if(q.op==="conditions")return [...conditions.values()];
  const c=condition(q.filter);
  if(q.op==="family")return {filter:c.filter,count:c.indices.length};
  if(q.op==="select"){const rank=nat(q.rank,0,c.indices.length-1,"rank");return {rank,filter:c.filter,...record(c.indices[rank])};}
  if(q.op==="rank"){const n=nat(q.n,first,last,"index"),rank=c.indices.indexOf(n);return rank<0?{status:"outside_filter",n,filter:c.filter}:{status:"found",rank,filter:c.filter,...record(n)};}
  if(q.op==="page"){const start=nat(q.start??0,0,c.indices.length,"start"),limit=nat(q.limit??20,0,2000,"limit");return {start,total:c.indices.length,filter:c.filter,records:c.indices.slice(start,start+limit).map(record)};}
  if(q.op==="cdf")return cdf(c,q.threshold);
  if(q.op==="range"){
   const lo=threshold(q.lower),hi=threshold(q.upper),left=BigInt(hi.b)**BigInt(lo.a*hi.d),right=BigInt(lo.b)**BigInt(hi.a*lo.d);work.range_order_powers+=2;if(left>right)fail("reversed threshold range");
   const below=cdf(c,lo),through=cdf(c,hi);return {interval:"[lower,upper)",filter:c.filter,count:through.less-below.less,lower:below,upper:through,order_certificate:{left_power:String(left),right_power:String(right)}};
  }
  fail("unknown operation");
 }
 return Object.freeze({query:q=>copy(query(q)),stats:()=>({...work,condition_count:conditions.size,series_cache_entries:seriesCache.size,log_cache_entries:logCache.size})});
}
module.exports={compile,openIndex};
