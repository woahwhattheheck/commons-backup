'use strict';
const SCHEMA='commons.blowup_subsets/v1',SHARD='commons.blowup_subset_rows/v1';
const LIMITS=Object.freeze({parts:8,part_size:12,vertices:60,occupancies:100000,shard_rows:4096,conditions:32,page:64});
const clone=x=>JSON.parse(JSON.stringify(x));
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function natural(x){if(typeof x==='number'){if(!Number.isSafeInteger(x)||x<0)throw new RangeError('unsafe rank');return BigInt(x);}if(typeof x==='bigint'){if(x<0n)throw new RangeError('negative rank');return x;}if(typeof x!=='string'||x.length>100||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError('canonical rank');return BigInt(x);}
function decode(code,radices){return radices.map(r=>{const x=code%r;code=Math.floor(code/r);return x;});}
function buildIndex(partSizes,baseEdges){
 if(!Array.isArray(partSizes))throw new TypeError('part sizes');const m=integer(partSizes.length,2,LIMITS.parts,'parts');
 const sizes=partSizes.map(x=>integer(x,1,LIMITS.part_size,'part size')),n=sizes.reduce((a,b)=>a+b,0);integer(n,2,LIMITS.vertices,'vertices');
 const radices=sizes.map(x=>x+1),rowCount=radices.reduce((a,b)=>a*b,1);integer(rowCount,1,LIMITS.occupancies,'occupancy budget');
 if(!Array.isArray(baseEdges))throw new TypeError('base edges');
 const seen=new Set(),edges=baseEdges.map(e=>{if(!Array.isArray(e)||e.length!==2)throw new TypeError('edge pair');const a=integer(e[0],0,m-1,'endpoint'),b=integer(e[1],0,m-1,'endpoint');if(a===b)throw new TypeError('loop');const pair=a<b?[a,b]:[b,a],key=pair.join(':');if(seen.has(key))throw new TypeError('duplicate edge');seen.add(key);return pair;}).sort((x,y)=>x[0]-y[0]||x[1]-y[1]);
 const offsets=[];let offset=0;for(const size of sizes){offsets.push(offset);offset+=size;}
 const maxPart=Math.max(...sizes),pascal=[];
 for(let k=0;k<=maxPart;k++){const row=Array(k+1).fill(1n);for(let j=1;j<k;j++)row[j]=pascal[k-1][j-1]+pascal[k-1][j];pascal.push(row);}
 const triangles=[];let tripleChecks=0;
 for(let a=0;a<m;a++)for(let b=a+1;b<m;b++)for(let c=b+1;c<m;c++){tripleChecks++;if(seen.has(a+':'+b)&&seen.has(a+':'+c)&&seen.has(b+':'+c))triangles.push([a,b,c]);}
 const totalEdges=edges.reduce((s,[a,b])=>s+sizes[a]*sizes[b],0),rows=[],hist=new Map();
 const work={occupancies:0,occupancy_coordinates:0,edge_products:0,binomial_factors:0,base_triples_checked:tripleChecks,histogram_additions:0};
 for(let code=0;code<rowCount;code++){
  const x=decode(code,radices),size=x.reduce((a,b)=>a+b,0);work.occupancy_coordinates+=m;
  let edgeCount=0;for(const [a,b] of edges){edgeCount+=x[a]*x[b];work.edge_products++;}
  let multiplicity=1n;for(let p=0;p<m;p++){multiplicity*=pascal[sizes[p]][x[p]];work.binomial_factors++;}
  rows.push([size,edgeCount,multiplicity.toString()]);work.occupancies++;
  const key=size+':'+edgeCount,old=hist.get(key)||{size,edges:edgeCount,occupancies:0,count:0n};
  old.count+=multiplicity;old.occupancies++;hist.set(key,old);work.histogram_additions++;
 }
 const buckets=[...hist.values()].sort((a,b)=>a.size-b.size||a.edges-b.edges).map(x=>({...x,count:x.count.toString()}));
 const profiles=[];
 for(let k=0;k<=n;k++){
  const subset=buckets.filter(x=>x.size===k),first=subset[0],last=subset[subset.length-1];
  profiles.push({size:k,min_edges:first.edges,max_edges:last.edges,min_count:first.count,min_occupancies:first.occupancies,max_count:last.count,max_occupancies:last.occupancies,
   total:subset.reduce((s,x)=>s+BigInt(x.count),0n).toString(),occupancies:subset.reduce((s,x)=>s+x.occupancies,0)});
 }
 const shards=[];
 for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 const index={schema:SCHEMA,part_sizes:sizes,offsets,radices,vertices:n,base_edges:edges,total_edges:totalEdges,base_triangles:triangles,
  row_count:rowCount,row_schema:['subset size','induced edges','labelled multiplicity'],row_order:'mixed radix occupancy code, part0 least significant',
  shards:shards.map(s=>({start:s.start,length:s.rows.length})),pascal:pascal.map(row=>row.map(String)),buckets,size_profiles:profiles,
  labelled_subsets:buckets.reduce((s,b)=>s+BigInt(b.count),0n).toString(),work};
 return {index,shards};
}
function openIndex(index,shards){
 const data=clone(index);if(data.schema!==SCHEMA)throw new TypeError('schema');
 const m=integer(data.part_sizes.length,2,LIMITS.parts,'parts'),sizes=data.part_sizes.map(x=>integer(x,1,LIMITS.part_size,'part size'));
 const n=integer(data.vertices,2,LIMITS.vertices,'vertices'),radices=data.radices;
 if(radices.length!==m||data.offsets.length!==m||!Array.isArray(shards)||shards.length!==data.shards.length)throw new TypeError('shape');
 if(sizes.reduce((a,b)=>a+b,0)!==n||radices.some((r,i)=>r!==sizes[i]+1))throw new TypeError('size consistency');
 const rowCount=integer(data.row_count,1,LIMITS.occupancies,'rows');if(radices.reduce((a,b)=>a*b,1)!==rowCount)throw new TypeError('row cardinality');
 const rows=[];let start=0;
 shards.forEach((value,i)=>{const s=clone(value),meta=data.shards[i];if(s.schema!==SHARD||s.start!==start||meta.start!==start||s.rows.length!==meta.length)throw new TypeError('shard ordering');for(const row of s.rows){if(!Array.isArray(row)||row.length!==3)throw new TypeError('row shape');integer(row[0],0,n,'size');integer(row[1],0,data.total_edges,'edges');natural(row[2]);rows.push(row);}start+=s.rows.length;});
 if(start!==rowCount)throw new TypeError('missing rows');
 const P=data.pascal.map((r,i)=>{if(r.length!==i+1)throw new TypeError('Pascal shape');return r.map(natural);});
 if(P.length<=Math.max(...sizes)||data.size_profiles.length!==n+1)throw new TypeError('summary shape');
 const partOf=Array(n),vertices=sizes.map((size,p)=>Array.from({length:size},(_,i)=>data.offsets[p]+i));
 for(let p=0;p<m;p++)for(const v of vertices[p]){integer(v,0,n-1,'label');if(partOf[v]!==undefined)throw new TypeError('part overlap');partOf[v]=p;}
 const work={rows_indexed:rows.length,pascal_cells_indexed:P.reduce((s,r)=>s+r.length,0),queries:0,condition_rows_scanned:0,occupancies_decoded:0,binomial_lookups:0,conditional_products:0,prefix_additions:0,conditions_created:0,condition_cache_hits:0,binary_search_steps:0,combination_steps:0,
  occupancy_rows_built:0,edge_products:0,histogram_cells_built:0};
 const cache=new Map();
 function choose(a,b){work.binomial_lookups++;return b<0||b>a?0n:P[a][b];}
 function occupancy(code){work.occupancies_decoded++;return decode(code,radices);}
 function labels(a){if(!Array.isArray(a))throw new TypeError('labels');const sorted=a.map(x=>integer(x,0,n-1,'vertex')).sort((a,b)=>a-b);if(sorted.some((x,i)=>i&&x===sorted[i-1]))throw new TypeError('duplicate vertex');return sorted;}
 function makeCondition(q={}){
  if(!q||typeof q!=='object'||Array.isArray(q))throw new TypeError('condition object');
  for(const key of Object.keys(q))if(!['min_size','max_size','min_edges','max_edges','required','excluded'].includes(key))throw new TypeError('unknown condition');
  const lo=q.min_size===undefined?0:integer(q.min_size,0,n,'min size'),hi=q.max_size===undefined?n:integer(q.max_size,0,n,'max size');
  const le=q.min_edges===undefined?0:integer(q.min_edges,0,data.total_edges,'min edges'),he=q.max_edges===undefined?data.total_edges:integer(q.max_edges,0,data.total_edges,'max edges');
  if(lo>hi||le>he)throw new RangeError('reversed bounds');
  const required=labels(q.required||[]),excluded=labels(q.excluded||[]),key=JSON.stringify([lo,hi,le,he,required,excluded]);
  if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}if(cache.size>=LIMITS.conditions)throw new RangeError('condition cap');
  const req=new Set(required),ban=new Set(excluded),incompatible=required.some(x=>ban.has(x));
  const fixed=vertices.map(vs=>vs.filter(v=>req.has(v))),free=vertices.map(vs=>vs.filter(v=>!req.has(v)&&!ban.has(v)));
  let count=0n;const admitted=[];
  for(let code=0;code<rows.length;code++){
   work.condition_rows_scanned++;const [size,edges,weight]=rows[code];if(incompatible||size<lo||size>hi||edges<le||edges>he)continue;
   let ways;
   if(required.length===0&&excluded.length===0)ways=BigInt(weight);
   else {const x=occupancy(code);ways=1n;for(let p=0;p<m;p++){ways*=choose(free[p].length,x[p]-fixed[p].length);work.conditional_products++;if(ways===0n)break;}}
   if(ways){count+=ways;work.prefix_additions++;admitted.push([code,ways.toString(),count.toString()]);}
  }
  const record={key,min_size:lo,max_size:hi,min_edges:le,max_edges:he,required,excluded,fixed,free,count:count.toString(),occupancy_count:admitted.length,rows:admitted};
  cache.set(key,record);work.conditions_created++;return record;
 }
 function familySummary(c){const {rows,fixed,free,...summary}=c;return clone(summary);}
 function findRank(c,rank){let lo=0,hi=c.rows.length;while(lo<hi){work.binary_search_steps++;const mid=(lo+hi)>>1;if(BigInt(c.rows[mid][2])<=rank)lo=mid+1;else hi=mid;}return lo;}
 function findCode(c,code){let lo=0,hi=c.rows.length;while(lo<hi){work.binary_search_steps++;const mid=(lo+hi)>>1;if(c.rows[mid][0]<code)lo=mid+1;else hi=mid;}return lo;}
 function combinationSelect(pool,k,rank){
  const selected=[];let begin=0;
  for(let remaining=k;remaining>0;remaining--){
   for(let j=begin;j<=pool.length-remaining;j++){work.combination_steps++;const block=choose(pool.length-j-1,remaining-1);if(rank<block){selected.push(pool[j]);begin=j+1;break;}rank-=block;}
  }
  return selected;
 }
 function combinationRank(pool,selected){
  let rank=0n,begin=0;for(let i=0;i<selected.length;i++){const at=pool.indexOf(selected[i]);if(at<begin)throw new TypeError('invalid free subset');for(let j=begin;j<at;j++){work.combination_steps++;rank+=choose(pool.length-j-1,selected.length-i-1);}begin=at+1;}return rank;
 }
 function select(q,rank){
  const c=makeCondition(q),r=natural(rank);if(r>=BigInt(c.count))throw new RangeError('rank outside family');const at=findRank(c,r),entry=c.rows[at],before=at?BigInt(c.rows[at-1][2]):0n;
  const code=entry[0],x=occupancy(code),ways=x.map((k,p)=>choose(c.free[p].length,k-c.fixed[p].length)),ranks=Array(m);let local=r-before;
  for(let p=m-1;p>=0;p--){ranks[p]=local%ways[p];local/=ways[p];}
  const partSubsets=x.map((k,p)=>c.fixed[p].concat(combinationSelect(c.free[p],k-c.fixed[p].length,ranks[p])).sort((a,b)=>a-b));
  return {rank:r.toString(),total:c.count,code,occupancy:x,size:rows[code][0],edges:rows[code][1],within_occupancy:(r-before).toString(),part_ranks:ranks.map(String),part_subsets:partSubsets,vertices:partSubsets.flat()};
 }
 return Object.freeze({
  summary(){work.queries++;return {vertices:n,part_sizes:sizes.slice(),base_edges:clone(data.base_edges),total_edges:data.total_edges,base_triangles:clone(data.base_triangles),occupancies:rowCount,labelled_subsets:data.labelled_subsets,buckets:data.buckets.length,construction_work:clone(data.work)};},
  profiles(){work.queries++;return clone(data.size_profiles);},
  distribution(size){work.queries++;integer(size,0,n,'size');return clone(data.buckets.filter(x=>x.size===size));},
  occupancy(code){work.queries++;integer(code,0,rowCount-1,'code');return {code,counts:occupancy(code),size:rows[code][0],edges:rows[code][1],multiplicity:rows[code][2]};},
  classify(subset){work.queries++;const vs=labels(subset),x=Array(m).fill(0);for(const v of vs)x[partOf[v]]++;let code=0,scale=1;for(let p=0;p<m;p++){code+=x[p]*scale;scale*=radices[p];}return {vertices:vs,code,occupancy:x,size:rows[code][0],edges:rows[code][1],multiplicity:rows[code][2]};},
  family(q={}){work.queries++;return familySummary(makeCondition(q));},
  select(q,rank){work.queries++;return select(q,rank);},
  rank(q,subset){
   work.queries++;const c=makeCondition(q),vs=labels(subset),set=new Set(vs),x=Array(m).fill(0);for(const v of vs)x[partOf[v]]++;
   if(c.required.some(v=>!set.has(v))||c.excluded.some(v=>set.has(v)))return {vertices:vs,rank:null,reason:'forced-label condition'};
   let code=0,scale=1;for(let p=0;p<m;p++){code+=x[p]*scale;scale*=radices[p];}
   const at=findCode(c,code);if(at===c.rows.length||c.rows[at][0]!==code)return {vertices:vs,rank:null,reason:'size or edge condition'};
   const freeSelected=c.free.map(pool=>pool.filter(v=>set.has(v))),ways=x.map((k,p)=>choose(c.free[p].length,k-c.fixed[p].length));
   const partRanks=freeSelected.map((chosen,p)=>combinationRank(c.free[p],chosen));let local=0n;for(let p=0;p<m;p++)local=local*ways[p]+partRanks[p];
   const before=at?BigInt(c.rows[at-1][2]):0n;return {vertices:vs,code,occupancy:x,size:rows[code][0],edges:rows[code][1],part_ranks:partRanks.map(String),within_occupancy:local.toString(),rank:(before+local).toString(),total:c.count};
  },
  page(q,start=0,limit=8){work.queries++;const c=makeCondition(q),r=natural(start);integer(limit,0,LIMITS.page,'limit');if(r>BigInt(c.count))throw new RangeError('page start');const out=[];for(let i=0;i<limit&&r+BigInt(i)<BigInt(c.count);i++)out.push(select(q,r+BigInt(i)));return {start:r.toString(),total:c.count,rows:out};},
  conditions(){return {records:[...cache.values()].map(clone)};},
  work(){return clone(work);}
 });
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
