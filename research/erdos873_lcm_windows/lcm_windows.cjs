"use strict";
const SCHEMA="commons.contiguous-lcm-index.v1",SHARD="commons.contiguous-lcm-runs.v1";
const LIMITS={values:50000,primes:8,cap:12,runs:1000000,shard_rows:4096,conditions:12,condition_members:1500000,page:64,digits:2048,max_length:1000000};
function fail(s){throw Error(s);}
function int(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function cp(x){return JSON.parse(JSON.stringify(x));}
function nat(x,name,maxDigits=LIMITS.digits){if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>maxDigits)fail(name+" must be canonical nonnegative decimal");return BigInt(x);}
function signed(x){if(typeof x!=="string"||!/^(0|-?[1-9][0-9]*)$/.test(x)||x.replace("-","").length>LIMITS.digits)fail("canonical signed numerator required");return BigInt(x);}
function threshold(x){if(!x||typeof x!=="object")fail("threshold object");const p=signed(x.numerator),q=nat(x.denominator,"denominator");if(q===0n)fail("positive denominator required");return{numerator:x.numerator,denominator:x.denominator,p,q};}
function buildIndex(input){
 if(!Array.isArray(input.primes)||input.primes.length<1||input.primes.length>LIMITS.primes||!Array.isArray(input.caps)||input.caps.length!==input.primes.length)fail("prime/cap shape");
 const primes=input.primes.map((p,i)=>int(p,"prime premise",i?input.primes[i-1]+1:2,1000000)),caps=input.caps.map(c=>int(c,"cap",0,LIMITS.cap)),radices=caps.map(c=>c+1),strides=[];let size=1;for(const r of radices){strides.push(size);size*=r;if(size>LIMITS.values)fail("product box too large");}
 if(!Array.isArray(input.values)||input.values.length!==size||!input.provenance)fail("complete identified box required");
 const values=cp(input.values),seen=new Set(),byCode=Array(size),digits=Array(size);let previous=0n;
 const work={codes_decoded:0,exponent_digits:0,join_calls:0,coordinate_maxima:0,coalesced_runs:0,emitted_runs:0,new_product_values:0,new_factorizations:0,new_totients:0,new_primality_tests:0};
 values.forEach(row=>{if(!Array.isArray(row)||row.length!==2)fail("value row");const value=nat(row[0],"positive sorted value");if(value<=previous)fail("strict positive increasing values");previous=value;const code=int(row[1],"code",0,size-1);if(seen.has(code))fail("duplicate code");seen.add(code);byCode[code]=row[0];let rem=code;digits[code]=radices.map(r=>{const d=rem%r;rem=Math.floor(rem/r);work.exponent_digits++;return d;});work.codes_decoded++;});
 function join(a,b){work.join_calls++;let code=0;for(let p=0;p<caps.length;p++){work.coordinate_maxima++;code+=Math.max(digits[a][p],digits[b][p])*strides[p];}return code;}
 const groups=Array(size);let carry=[],totalRuns=0,maxRuns=0;
 for(let i=size-1;i>=0;i--){const code=values[i][1],out=[[i,i,code]];
  for(const [lo,hi,old]of carry){const next=join(code,old),last=out[out.length-1];if(last[2]===next){last[1]=hi;work.coalesced_runs++;}else out.push([lo,hi,next]);}
  totalRuns+=out.length;if(totalRuns>LIMITS.runs)fail("run cap");maxRuns=Math.max(maxRuns,out.length);groups[i]=out;carry=out;
 }
 const rows=[],starts=[0];for(let i=0;i<size;i++){for(const [lo,hi,code]of groups[i])rows.push([i,lo,hi,code]);starts.push(rows.length);}work.emitted_runs=rows.length;
 const shards=[];for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 return{index:{schema:SCHEMA,primes,caps,radices,strides,values,provenance:cp(input.provenance),starts,summary:{values:size,contiguous_nonempty_windows:(BigInt(size)*BigInt(size+1)/2n).toString(),run_rows:rows.length,max_runs_per_start:maxRuns,maximum_value:values.at(-1)[0],largest_code:size-1},ordering:{positions:"zero-based source ranks",windows:"increasing start, then increasing inclusive end",threshold:"strict LCM < numerator/positive denominator",empty_windows:"excluded; only fully contained windows counted"},construction:work,row_shards:shards.map(s=>({start:s.start,count:s.rows.length}))},shards};
}
function openIndex(saved,shards){
 const index=cp(saved);if(index.schema!==SCHEMA)fail("schema");const n=int(index.summary.values,"values",1,LIMITS.values);
 if(!Array.isArray(index.values)||index.values.length!==n||index.starts.length!==n+1||index.starts[0]!==0)fail("index shape");
 const byCode=Array(n),codeSeen=new Set();let previous=0n;
 for(const row of index.values){const v=nat(row[0],"value");if(v<=previous)fail("value order");previous=v;int(row[1],"code",0,n-1);if(codeSeen.has(row[1]))fail("code duplicate");codeSeen.add(row[1]);byCode[row[1]]=v;}
 const rows=[];if(!Array.isArray(shards)||shards.length!==index.row_shards.length)fail("shards");
 for(let i=0;i<shards.length;i++){const s=shards[i],e=index.row_shards[i];if(s.schema!==SHARD||s.start!==rows.length||s.start!==e.start||s.rows.length!==e.count)fail("shard range");rows.push(...cp(s.rows));}
 if(rows.length!==index.summary.run_rows||rows.length>LIMITS.runs||index.starts[n]!==rows.length)fail("run total");
 for(let i=0;i<n;i++){int(index.starts[i],"start pointer",0,rows.length-1);int(index.starts[i+1],"end pointer",index.starts[i]+1,rows.length);let next=i;
  for(let j=index.starts[i];j<index.starts[i+1];j++){const r=rows[j];if(r.length!==4||r[0]!==i||r[1]!==next)fail("endpoint partition");int(r[2],"end",r[1],n-1);int(r[3],"code",0,n-1);next=r[2]+1;}
  if(next!==n)fail("endpoint coverage");
 }
 const caches=[],keys=new Map();let memberCount=0;
 const work={rows_indexed:rows.length,values_indexed:n,queries:0,condition_run_scans:0,threshold_comparisons:0,conditional_prefix_additions:0,selection_steps:0,direct_window_steps:0,rank_member_checks:0,profile_difference_updates:0,profile_prefix_additions:0,condition_cache_hits:0,new_exponent_joins:0,new_lcm_run_rows:0,new_product_values:0};
 function condition(raw){
  if(!raw||typeof raw!=="object")fail("condition");const t=threshold(raw.threshold),a=raw.start_min===undefined?0:int(raw.start_min,"start_min",0,n-1),b=raw.start_max===undefined?n-1:int(raw.start_max,"start_max",a,n-1),lo=raw.length_min===undefined?1:int(raw.length_min,"length_min",1,LIMITS.max_length),hi=raw.length_max===undefined?n:int(raw.length_max,"length_max",lo,LIMITS.max_length);
  const c={threshold:{numerator:t.numerator,denominator:t.denominator},start_min:a,start_max:b,length_min:lo,length_max:hi},key=JSON.stringify(c);
  if(keys.has(key)){work.condition_cache_hits++;return caches[keys.get(key)];}
  if(caches.length>=LIMITS.conditions)fail("condition cap");
  const members=[];let total=0n;
  for(let k=index.starts[a];k<index.starts[b+1];k++){work.condition_run_scans++;const r=rows[k],left=Math.max(r[1],r[0]+lo-1),right=Math.min(r[2],r[0]+hi-1);if(left>right)continue;work.threshold_comparisons++;if(byCode[r[3]]*t.q>=t.p)continue;
   total+=BigInt(right-left+1);members.push([r[0],left,right,r[3],total.toString()]);work.conditional_prefix_additions++;
  }
  if(memberCount+members.length>LIMITS.condition_members)fail("condition member cap");memberCount+=members.length;
  const cch={id:caches.length,condition:c,count:total.toString(),members};keys.set(key,cch.id);caches.push(cch);return cch;
 }
 function cache(id){return caches[int(id,"condition",0,caches.length-1)];}
 function window(start,length){int(start,"start",0,n-1);int(length,"length",1,n-start);const end=start+length-1;let lo=index.starts[start],hi=index.starts[start+1]-1;
  while(lo<hi){work.direct_window_steps++;const mid=(lo+hi)>>1;if(rows[mid][2]>=end)hi=mid;else lo=mid+1;}
  const r=rows[lo];return{start,end,length,first_value:index.values[start][0],last_value:index.values[end][0],lcm:byCode[r[3]].toString(),exponent_code:r[3],run_row:lo};
 }
 function select(id,rank){const c=cache(id),r=nat(rank,"rank",100);if(r>=BigInt(c.count))fail("rank out of range");let lo=0,hi=c.members.length-1;
  while(lo<hi){work.selection_steps++;const mid=(lo+hi)>>1;if(BigInt(c.members[mid][4])>r)hi=mid;else lo=mid+1;}
  const x=c.members[lo],prior=lo?BigInt(c.members[lo-1][4]):0n,end=x[1]+Number(r-prior);return{condition:id,rank,start:x[0],end,length:end-x[0]+1,lcm:byCode[x[3]].toString(),exponent_code:x[3]};
 }
 function rank(id,start,end){const c=cache(id);int(start,"start",0,n-1);int(end,"end",start,n-1);
  for(let i=0;i<c.members.length;i++){work.rank_member_checks++;const x=c.members[i];if(x[0]===start&&x[1]<=end&&end<=x[2])return((i?BigInt(c.members[i-1][4]):0n)+BigInt(end-x[1])).toString();if(x[0]>start)break;}return null;
 }
 return{
  summary(){work.queries++;return cp({summary:index.summary,construction:index.construction,ordering:index.ordering});},
  sourceValue(position){work.queries++;return cp(index.values[int(position,"position",0,n-1)]);},
  run(row){work.queries++;const r=rows[int(row,"run",0,rows.length-1)];return{row,start:r[0],end_min:r[1],end_max:r[2],exponent_code:r[3],lcm:byCode[r[3]].toString()};},
  window(start,length){work.queries++;return window(start,length);},
  condition(raw){work.queries++;const c=condition(raw);return{id:c.id,condition:cp(c.condition),count:c.count,member_runs:c.members.length};},
  select(id,r){work.queries++;return select(id,r);},
  rank(id,start,end){work.queries++;return rank(id,start,end);},
  page(id,start,count){work.queries++;const c=cache(id),r=nat(start,"rank",100);int(count,"page",0,LIMITS.page);if(r>BigInt(c.count))fail("page start");const a=[];for(let i=0;i<count&&r+BigInt(i)<BigInt(c.count);i++)a.push(select(id,(r+BigInt(i)).toString()));return a;},
  lengthProfile(id){work.queries++;const c=cache(id),diff=Array(n+2).fill(0n);for(const x of c.members){diff[x[1]-x[0]+1]++;diff[x[2]-x[0]+2]--;work.profile_difference_updates+=2;}let running=0n;const out=[];for(let k=1;k<=n;k++){running+=diff[k];work.profile_prefix_additions++;out.push([k,running.toString()]);}return{condition:id,counts:out};},
  caches(){work.queries++;return cp(caches);},
  work(){return cp(work);}
 };
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
