"use strict";
const copy=x=>JSON.parse(JSON.stringify(x));
function integer(v,lo,hi,label){if(!Number.isSafeInteger(v)||v<lo||v>hi)throw new RangeError(label);return v;}
function natural(x){if(typeof x!=="string"||x.length>4096||! /^(0|[1-9][0-9]*)$/.test(x))throw new TypeError("decimal rank");return BigInt(x);}
function decode(code,b){const a=[];for(let p=0;p<5;p++){a.push(code%(b+1));code=Math.floor(code/(b+1));}return a;}
function compileCuts(input){
 const b=integer(input.part_size,1,12,"part size"),n=5*b,M=integer(input.total_edges,1,1000000,"edge premise"),radix=b+1;
 if(!Array.isArray(input.rows)||input.rows.length!==radix**5||!Array.isArray(input.pascal)||input.pascal.length<=b)throw new TypeError("complete saved input");
 const rows=[],map=new Map(),work={source_rows_read:0,canonical_rows:0,cut_cost_evaluations:0,canonical_weight_products:0,canonical_weight_divisions:0,bucket_additions:0,old_occupancies_built:0,old_edge_products:0,pascal_cells_built:0};
 for(let code=0;code<input.rows.length;code++){
  work.source_rows_read++;const old=input.rows[code],x0=code%radix;if(x0===0)continue;
  if(!Array.isArray(old)||old.length!==3)throw new TypeError("source row");const size=integer(old[0],0,n,"size"),inside=integer(old[1],0,M,"inside"),w=natural(old[2]);
  const crossing=2*b*size-2*inside,deleted=M-crossing;integer(deleted,0,M,"derived deletion count");work.cut_cost_evaluations++;
  const numerator=w*BigInt(x0);work.canonical_weight_products++;if(numerator%BigInt(b)!==0n)throw new Error("canonical weight not integral");const weight=numerator/BigInt(b);work.canonical_weight_divisions++;if(weight===0n)continue;
  const id=rows.length;rows.push([code,size,deleted,String(weight)]);work.canonical_rows++;
  if(!map.has(deleted))map.set(deleted,{deleted,count:0n,row_ids:[],prefixes:[]});const bucket=map.get(deleted);bucket.count+=weight;bucket.row_ids.push(id);bucket.prefixes.push(String(bucket.count));work.bucket_additions++;
 }
 const buckets=[...map.values()].sort((a,b)=>a.deleted-b.deleted).map(x=>({...x,count:String(x.count)})),total=buckets.reduce((a,x)=>a+BigInt(x.count),0n);
 return{format:"saved-c5-canonical-cut-index-v1",source:copy(input.source),part_size:b,vertices:n,total_edges:M,regular_degree:2*b,pascal:copy(input.pascal),rows,buckets,summary:{vertices:n,part_size:b,total_edges:M,source_rows:input.rows.length,canonical_rows:rows.length,cost_buckets:buckets.length,canonical_cuts:String(total),minimum_deletions:buckets[0].deleted,minimum_deletion_sets:buckets[0].count,maximum_cut:M-buckets[0].deleted},work};
}
function openIndex(s){
 if(!s||s.format!=="saved-c5-canonical-cut-index-v1"||s.rows.length!==s.summary.canonical_rows)throw new TypeError("snapshot");
 const b=s.part_size,n=s.vertices,M=s.total_edges,P=s.pascal.map(r=>r.map(BigInt)),byCode=new Map(s.rows.map((r,i)=>[r[0],i])),cache=new Map();
 const work={queries:0,rows_indexed:s.rows.length,condition_rows_scanned:0,occupancies_decoded:0,binomial_lookups:0,conditional_products:0,prefix_additions:0,conditions_created:0,cache_hits:0,combination_steps:0,rank_search_steps:0,repair_edge_visits:0,old_occupancies_built:0,old_edge_products:0,pascal_cells_built:0};
 function labels(a){if(!Array.isArray(a))throw new TypeError("labels");const out=a.map(v=>integer(v,0,n-1,"vertex")).sort((x,y)=>x-y);if(out.some((v,i)=>i&&v===out[i-1]))throw new TypeError("duplicate label");return out;}
 function choose(a,k){work.binomial_lookups++;return k<0||k>a?0n:P[a][k];}
 function occupancy(code){work.occupancies_decoded++;return decode(code,b);}
 function family(q={}){
  for(const key of Object.keys(q))if(!["min_deleted","max_deleted","min_size","max_size","required","excluded"].includes(key))throw new TypeError("filter key");
  const lo=q.min_deleted===undefined?0:integer(q.min_deleted,0,M,"min deleted"),hi=q.max_deleted===undefined?M:integer(q.max_deleted,0,M,"max deleted"),ls=q.min_size===undefined?0:integer(q.min_size,0,n,"min size"),hs=q.max_size===undefined?n:integer(q.max_size,0,n,"max size");
  if(lo>hi||ls>hs)throw new RangeError("reversed bounds");const required=labels(q.required||[]),excluded=labels(q.excluded||[]),key=JSON.stringify([lo,hi,ls,hs,required,excluded]);
  if(cache.has(key)){work.cache_hits++;return cache.get(key);}if(cache.size>=24)throw new RangeError("condition cap");
  const req=new Set([0,...required]),ban=new Set(excluded),incompatible=[...req].some(v=>ban.has(v)),fixed=[],free=[];
  for(let p=0;p<5;p++){const vs=Array.from({length:b},(_,i)=>p*b+i);fixed.push(vs.filter(v=>req.has(v)));free.push(vs.filter(v=>!req.has(v)&&!ban.has(v)));}
  const admitted=[];let total=0n;
  for(const bucket of s.buckets){if(bucket.deleted<lo||bucket.deleted>hi)continue;for(const rowId of bucket.row_ids){work.condition_rows_scanned++;const row=s.rows[rowId];if(incompatible||row[1]<ls||row[1]>hs)continue;let ways;
   if(required.length===0&&excluded.length===0)ways=BigInt(row[3]);else{const x=occupancy(row[0]);ways=1n;for(let p=0;p<5;p++){ways*=choose(free[p].length,x[p]-fixed[p].length);work.conditional_products++;if(ways===0n)break;}}
   if(ways){total+=ways;admitted.push([rowId,String(ways),String(total)]);work.prefix_additions++;}
  }}
  const c={key,min_deleted:lo,max_deleted:hi,min_size:ls,max_size:hs,required,excluded,fixed,free,rows:admitted,count:String(total)};cache.set(key,c);work.conditions_created++;return c;
 }
 function summary(c){const {rows,fixed,free,...a}=c;return{...copy(a),occupancy_rows:rows.length};}
 function combinationSelect(pool,k,rank){const out=[];let start=0;for(let rem=k;rem>0;rem--)for(let j=start;j<=pool.length-rem;j++){work.combination_steps++;const count=choose(pool.length-j-1,rem-1);if(rank<count){out.push(pool[j]);start=j+1;break;}rank-=count;}return out;}
 function combinationRank(pool,selected){let rank=0n,start=0;for(let i=0;i<selected.length;i++){const at=pool.indexOf(selected[i]);if(at<start)throw new TypeError("free subset");for(let j=start;j<at;j++){work.combination_steps++;rank+=choose(pool.length-j-1,selected.length-i-1);}start=at+1;}return rank;}
 function selected(c,r){
  if(r>=BigInt(c.count))throw new RangeError("rank");let lo=0,hi=c.rows.length;while(lo<hi){work.rank_search_steps++;const mid=(lo+hi)>>1;if(BigInt(c.rows[mid][2])<=r)lo=mid+1;else hi=mid;}
  const entry=c.rows[lo],row=s.rows[entry[0]],before=lo?BigInt(c.rows[lo-1][2]):0n,x=occupancy(row[0]),ways=x.map((v,p)=>choose(c.free[p].length,v-c.fixed[p].length)),partRanks=Array(5);let local=r-before;
  for(let p=4;p>=0;p--){partRanks[p]=local%ways[p];local/=ways[p];}
  const parts=x.map((v,p)=>c.fixed[p].concat(combinationSelect(c.free[p],v-c.fixed[p].length,partRanks[p])).sort((a,b)=>a-b));
  return{rank:String(r),count:c.count,code:row[0],occupancy:x,size:row[1],deleted:row[2],crossing:M-row[2],vertices:parts.flat(),part_ranks:partRanks.map(String),within_occupancy:String(r-before)};
 }
 function canonical(vertices){let vs=labels(vertices);const complemented=!vs.includes(0);if(complemented){const set=new Set(vs);vs=Array.from({length:n},(_,i)=>i).filter(v=>!set.has(v));}const x=Array(5).fill(0);for(const v of vs)x[Math.floor(v/b)]++;let code=0,mult=1;for(let p=0;p<5;p++){code+=x[p]*mult;mult*=b+1;}const id=byCode.get(code);if(id===undefined)throw new Error("saved canonical row");return{vertices:vs,occupancy:x,code,row_id:id,input_complemented:complemented};}
 function query(q){work.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"distribution":return s.buckets.map(x=>({deleted:x.deleted,count:x.count,occupancy_rows:x.row_ids.length}));
  case"family":return summary(family(q.filter));
  case"select":return selected(family(q.filter),natural(q.rank));
  case"page":{const c=family(q.filter),start=natural(q.start),limit=integer(q.limit,0,1000,"limit");if(start>BigInt(c.count))throw new RangeError("page");const records=[];for(let r=start;r<BigInt(c.count)&&records.length<limit;r++)records.push(selected(c,r));return{start:q.start,count:c.count,records};}
  case"classify":{const a=canonical(q.vertices),row=s.rows[a.row_id];return{...a,size:row[1],deleted:row[2],crossing:M-row[2]};}
  case"rank":{const c=family(q.filter),a=canonical(q.vertices),set=new Set(a.vertices);if(c.required.some(v=>!set.has(v))||c.excluded.some(v=>set.has(v)))return{...a,rank:null,reason:"label condition"};let at=-1;for(let i=0;i<c.rows.length;i++){work.rank_search_steps++;if(c.rows[i][0]===a.row_id){at=i;break;}}if(at<0)return{...a,rank:null,reason:"cost or size condition"};
   const ways=a.occupancy.map((v,p)=>choose(c.free[p].length,v-c.fixed[p].length)),ranks=c.free.map(pool=>combinationRank(pool,pool.filter(v=>set.has(v))));let local=0n;for(let p=0;p<5;p++)local=local*ways[p]+ranks[p];const before=at?BigInt(c.rows[at-1][2]):0n;return{...a,rank:String(before+local),count:c.count,within_occupancy:String(local),part_ranks:ranks.map(String)};}
  case"repair":{const a=selected(family(q.filter),natural(q.rank)),left=new Set(a.vertices),deleted=[],kept=[];for(const [p,t] of [[0,1],[0,4],[1,2],[2,3],[3,4]])for(let i=0;i<b;i++)for(let j=0;j<b;j++){work.repair_edge_visits++;const edge=[p*b+i,t*b+j];(left.has(edge[0])===left.has(edge[1])?deleted:kept).push(edge);}if(deleted.length!==a.deleted||kept.length!==a.crossing)throw new Error("saved cut count mismatch");return{...a,minimum:a.deleted===s.summary.minimum_deletions,deleted_edges:deleted,kept_edges:kept};}
  case"conditions":return{records:[...cache.values()].map(copy)};
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(work)};
}
module.exports={compileCuts,openIndex};
