"use strict";
const SCHEMA="squarefree-power-representations/v1",copy=x=>JSON.parse(JSON.stringify(x));
function fail(s){throw new TypeError(s);}
function nat(x,lo,hi,label){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(label+" outside bounds");return x;}
function compile(input){
 const start=nat(input.start,3,2147483647,"start"),count=nat(input.count,1,8192,"count"),end=start+2*(count-1);
 if(start%2!==1||end>2147483647)fail("odd supported interval required");
 const basis=input.basis;if(!basis||!Array.isArray(basis.primes)||!input.provenance)fail("identified complete prime basis required");
 const limit=nat(basis.limit,2,1000000,"basis limit");if(limit*limit<end-1)fail("prime completeness bound too small");
 let prev=1;for(const p of basis.primes){nat(p,2,limit,"prime");if(p<=prev)fail("ordered distinct prime premise required");prev=p;}
 const work={prime_square_products:0,intervals_formed:0,merged_integer_positions:0,square_multiple_visits:0,first_obstructions:0,row_candidate_lookups:0,segment_search_steps:0,accepted_pairs:0,prefix_additions:0,old_basis_constructions:0,primality_tests:0};
 const powers=[];for(let v=1;v<end;v*=2)powers.push(v);
 const intervals=powers.map(v=>{work.intervals_formed++;return [Math.max(1,start-v),end-v];}).sort((a,b)=>a[0]-b[0]);
 const segments=[];for(const [lo,hi] of intervals){const last=segments.at(-1);if(last&&lo<=last.hi+1)last.hi=Math.max(last.hi,hi);else segments.push({lo,hi});}
 for(const seg of segments)work.merged_integer_positions+=seg.hi-seg.lo+1;
 if(work.merged_integer_positions>600000)fail("candidate interval union exceeds budget");
 const square_records=[];for(const p of basis.primes){const q=p*p;work.prime_square_products++;if(q>end-1)break;square_records.push([p,q]);}
 for(const seg of segments){
  seg.least_square_prime=new Array(seg.hi-seg.lo+1).fill(0);
  for(const [p,q] of square_records){if(q>seg.hi)break;for(let x=Math.ceil(seg.lo/q)*q;x<=seg.hi;x+=q){work.square_multiple_visits++;const j=x-seg.lo;if(seg.least_square_prime[j]===0){seg.least_square_prime[j]=p;work.first_obstructions++;}}}
 }
 function obstruction(x){let lo=0,hi=segments.length-1;while(lo<=hi){work.segment_search_steps++;const mid=(lo+hi)>>1,s=segments[mid];if(x<s.lo)hi=mid-1;else if(x>s.hi)lo=mid+1;else return s.least_square_prime[x-s.lo];}fail("candidate not in interval union");}
 const rows=[],prefix=[0],histogram=new Array(powers.length+1).fill(0),by_exponent=new Array(powers.length).fill(0);
 for(let i=0;i<count;i++){const n=start+2*i;let mask=0,total=0;for(let e=0;e<powers.length;e++){const remainder=n-powers[e];if(remainder<1)continue;work.row_candidate_lookups++;if(obstruction(remainder)===0){mask+=2**e;total++;by_exponent[e]++;work.accepted_pairs++;}}rows.push([mask,total]);histogram[total]++;prefix.push(prefix.at(-1)+total);work.prefix_additions++;}
 return {schema:SCHEMA,start,end,count,powers,basis:{limit,primes:basis.primes.slice()},provenance:copy(input.provenance),square_records,segments,rows,prefix,histogram,by_exponent,total_pairs:prefix.at(-1),work};
}
function openIndex(snapshot){
 if(!snapshot||snapshot.schema!==SCHEMA)fail("unsupported schema");
 const d=copy(snapshot),start=nat(d.start,3,2147483647,"start"),count=nat(d.count,1,8192,"count");if(start%2!==1||d.end!==start+2*(count-1))fail("bad range");
 if(!Array.isArray(d.powers)||d.powers.length<1||d.powers.length>31)fail("bad powers");
 for(let e=0;e<d.powers.length;e++)if(d.powers[e]!==2**e)fail("bad power labels");
 if(!Array.isArray(d.rows)||d.rows.length!==count||!Array.isArray(d.prefix)||d.prefix.length!==count+1||d.prefix[0]!==0)fail("bad row dimensions");
 const work={queries:0,rows_loaded:0,obstruction_positions_loaded:0,condition_rows_scanned:0,conditions_created:0,condition_cache_hits:0,rank_search_steps:0,bit_visits:0,segment_search_steps:0,saved_square_reads:0,witness_divisions:0,witness_remainder_checks:0,returned_representations:0,returned_number_records:0,sieve_multiple_visits:0,prime_square_products:0,old_basis_constructions:0,primality_tests:0};
 for(let i=0;i<count;i++){const r=d.rows[i];if(!Array.isArray(r)||r.length!==2)fail("bad row");nat(r[0],0,2**d.powers.length-1,"mask");nat(r[1],0,d.powers.length,"count");if(d.prefix[i+1]!==d.prefix[i]+r[1])fail("prefix disagreement");work.rows_loaded++;}
 if(d.total_pairs!==d.prefix.at(-1))fail("total disagreement");
 if(!Array.isArray(d.segments)||d.segments.length>31)fail("bad segments");let previous=0;const sq=new Map(d.square_records);
 for(const s of d.segments){nat(s.lo,1,d.end-1,"segment low");nat(s.hi,s.lo,d.end-1,"segment high");if(s.lo<=previous||!Array.isArray(s.least_square_prime)||s.least_square_prime.length!==s.hi-s.lo+1)fail("bad segment coverage");previous=s.hi;for(const p of s.least_square_prime){if(p!==0&&!sq.has(p))fail("unknown obstruction prime");work.obstruction_positions_loaded++;}}
 const conditions=new Map();
 function norm(f={}){
  if(!f||typeof f!=="object"||Array.isArray(f))fail("filter required");
  for(const k of Object.keys(f))if(!["min_count","max_count","required","excluded"].includes(k))fail("unknown filter key");
  const list=x=>x===undefined?[]:[...new Set(x.map(e=>nat(e,0,d.powers.length-1,"exponent")))].sort((a,b)=>a-b);
  const out={min_count:f.min_count===undefined?0:nat(f.min_count,0,d.powers.length,"minimum"),max_count:f.max_count===undefined?d.powers.length:nat(f.max_count,0,d.powers.length,"maximum"),required:list(f.required),excluded:list(f.excluded)};
  if(out.min_count>out.max_count)fail("reversed count interval");return out;
 }
 function condition(f){
  const filter=norm(f),key=JSON.stringify(filter);if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}if(conditions.size>=24)fail("24 condition budget");
  const ids=[],prefix=[0],req=filter.required.reduce((a,e)=>a+2**e,0),exc=filter.excluded.reduce((a,e)=>a+2**e,0);
  for(let i=0;i<count;i++){work.condition_rows_scanned++;const [m,c]=d.rows[i];if(c>=filter.min_count&&c<=filter.max_count&&(m&req)===req&&(m&exc)===0){ids.push(i);prefix.push(prefix.at(-1)+c);}}
  const result={filter,ids,prefix,total_pairs:prefix.at(-1)};conditions.set(key,result);work.conditions_created++;return result;
 }
 function rowIndex(n){nat(n,start,d.end,"n");if((n-start)%2!==0)fail("n is not a retained odd integer");return (n-start)/2;}
 function value(x){
  nat(x,1,d.end-1,"remainder");let lo=0,hi=d.segments.length-1;
  while(lo<=hi){work.segment_search_steps++;const mid=(lo+hi)>>1,s=d.segments[mid];if(x<s.lo)hi=mid-1;else if(x>s.hi)lo=mid+1;else{
   const p=s.least_square_prime[x-s.lo];if(p===0)return {value:x,status:"squarefree",segment:mid,offset:x-s.lo,complete_prime_bound:d.basis.limit};
   const square=sq.get(p);work.saved_square_reads++;work.witness_remainder_checks++;if(x%square!==0)fail("saved obstruction fails queried divisibility");work.witness_divisions++;
   return {value:x,status:"not_squarefree",segment:mid,offset:x-s.lo,prime:p,square,quotient:x/square};
  }}return {value:x,status:"outside_saved_remainder_union"};
 }
 function number(i,details=false){
  const n=start+2*i,[mask,total]=d.rows[i],exponents=[];for(let e=0;e<d.powers.length;e++){work.bit_visits++;if(mask&2**e)exponents.push(e);}work.returned_number_records++;
  const out={row:i,n,mask,count:total,exponents,global_pair_prefix:d.prefix[i]};
  if(details){out.candidates=[];for(let e=0;e<d.powers.length;e++){const remainder=n-d.powers[e];if(remainder<1)continue;const certificate=value(remainder);if((certificate.status==="squarefree")!==Boolean(mask&2**e))fail("queried candidate contradicts saved row");out.candidates.push({exponent:e,power:d.powers[e],remainder,certificate});}}
  return out;
 }
 function pair(i,e){
  const [mask]=d.rows[i];nat(e,0,d.powers.length-1,"exponent");const n=start+2*i,power=d.powers[e],remainder=n-power;if(remainder<1)return {status:"nonpositive_remainder",n,exponent:e,remainder};
  if(!(mask&2**e))return {status:"rejected",n,exponent:e,power,remainder,certificate:value(remainder)};
  work.returned_representations++;return {status:"found",n,exponent:e,power,remainder,certificate:value(remainder)};
 }
 function lower(ids,i){let lo=0,hi=ids.length;while(lo<hi){work.rank_search_steps++;const m=(lo+hi)>>1;if(ids[m]<i)lo=m+1;else hi=m;}return lo;}
 function query(q){
  if(!q||typeof q!=="object")fail("query required");work.queries++;
  if(q.op==="summary")return {schema:SCHEMA,start,end:d.end,count,powers:d.powers,total_pairs:d.total_pairs,histogram:d.histogram,by_exponent:d.by_exponent,segments:d.segments.map(s=>[s.lo,s.hi]),basis_limit:d.basis.limit,construction_work:d.work};
  if(q.op==="value")return value(q.value);
  if(q.op==="number")return number(rowIndex(q.n),q.details===true);
  if(q.op==="pair")return pair(rowIndex(q.n),q.exponent);
  if(q.op==="conditions")return [...conditions.values()];
  const c=condition(q.filter);
  if(q.op==="family")return {filter:c.filter,numbers:c.ids.length,pairs:c.total_pairs};
  if(q.op==="selectNumber"){const r=nat(q.rank,0,c.ids.length-1,"number rank");return {rank:r,filter:c.filter,...number(c.ids[r],q.details===true)};}
  if(q.op==="rankNumber"){const i=rowIndex(q.n),r=lower(c.ids,i);return r<c.ids.length&&c.ids[r]===i?{status:"found",rank:r,filter:c.filter,...number(i)}:{status:"outside_filter",n:q.n,filter:c.filter};}
  if(q.op==="page"){const r=nat(q.start??0,0,c.ids.length,"start"),limit=nat(q.limit??20,0,1000,"limit");return {start:r,total:c.ids.length,filter:c.filter,records:c.ids.slice(r,r+limit).map(i=>number(i))};}
  if(q.op==="selectPair"){
   const rank=nat(q.rank,0,c.total_pairs-1,"pair rank");let lo=0,hi=c.ids.length;while(lo<hi){work.rank_search_steps++;const mid=(lo+hi)>>1;if(c.prefix[mid+1]<=rank)lo=mid+1;else hi=mid;}
   const i=c.ids[lo];let local=rank-c.prefix[lo];for(let e=0;e<d.powers.length;e++){work.bit_visits++;if(d.rows[i][0]&2**e){if(local===0)return {rank,number_rank:lo,filter:c.filter,...pair(i,e)};local--;}}fail("pair prefix contradicts mask");
  }
  if(q.op==="rankPair"){
   const i=rowIndex(q.n),r=lower(c.ids,i);if(r===c.ids.length||c.ids[r]!==i)return {status:"outside_filter",n:q.n,filter:c.filter};
   const v=pair(i,q.exponent);if(v.status!=="found")return {...v,filter:c.filter};let local=0;for(let e=0;e<q.exponent;e++){work.bit_visits++;if(d.rows[i][0]&2**e)local++;}return {rank:c.prefix[r]+local,number_rank:r,filter:c.filter,...v};
  }
  if(q.op==="range"){
   const lo=nat(q.lower,0,2147483647,"lower"),hi=nat(q.upper,lo,2147483647,"upper");
   const a=Math.max(0,Math.ceil((lo-start)/2)),b=Math.min(count,Math.floor((hi-start)/2)+1),l=lower(c.ids,a),r=lower(c.ids,Math.max(a,b));
   return {lower:lo,upper:hi,filter:c.filter,numbers:r-l,pairs:c.prefix[r]-c.prefix[l],condition_index_range:[l,r]};
  }
  fail("unknown operation");
 }
 return Object.freeze({query:q=>copy(query(q)),stats:()=>({...work,condition_count:conditions.size})});
}
module.exports={compile,openIndex};
