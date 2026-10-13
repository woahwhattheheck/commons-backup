'use strict';
const LEFT='commons.hinted_left/v1',SCHEMA='commons.hinted_resilience/v1';
const LIMITS=Object.freeze({outer:20,inner:12,witness_cells:2000000,conditions:128,page:128});
const clone=x=>JSON.parse(JSON.stringify(x));
function int(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function pop(x){let n=0;for(;x;x&=x-1)n++;return n;}
function bits(mask,len){return Array.from({length:len},(_,i)=>i).filter(i=>(mask&(2**i))!==0);}
function leftContract(left){
 if(!Array.isArray(left)||left.length<2)throw new TypeError('left rows required');
 const n=int(left.length,2,LIMITS.outer,'outer size'),t=typeof left[0]==='string'?left[0].length:0;
 int(t,1,Math.min(LIMITS.inner,n-1),'inner size');
 if((2**t)*n*n>LIMITS.witness_cells)throw new RangeError('witness-cell budget exceeded');
 for(const row of left)if(typeof row!=='string'||row.length!==t||!/^[01]+$/.test(row))throw new TypeError('left must be rectangular binary strings');
 return {n,t};
}
function prepareLeft(left){
 const {n,t}=leftContract(left),rowMasks=left.map(row=>[...row].reduce((s,x,j)=>s+(x==='1'?2**j:0),0));
 return {schema:LEFT,n,t,left:left.slice(),row_masks:rowMasks,phase1_work:{matrix_entries_read:n*t,row_masks_created:n}};
}
function preparedContract(prepared){
 if(!prepared||prepared.schema!==LEFT)throw new TypeError('prepared schema');
 const {n,t}=leftContract(prepared.left);
 if(prepared.n!==n||prepared.t!==t||!Array.isArray(prepared.row_masks)||prepared.row_masks.length!==n)throw new TypeError('prepared shape');
 prepared.row_masks.forEach(x=>int(x,0,2**t-1,'prepared row mask'));return {n,t};
}
function attachHints(prepared,right){
 const p=clone(prepared),{n,t}=preparedContract(p);
 if(!Array.isArray(right)||right.length!==t||right.some(row=>typeof row!=='string'||row.length!==n||!/^[01]+$/.test(row)))throw new TypeError('right must have t binary rows of length n');
 const rightColumns=Array.from({length:n},(_,c)=>right.reduce((s,row,j)=>s+(row[c]==='1'?2**j:0),0));
 const witnesses=[],baseColumns=Array(n).fill(0);
 for(let r=0;r<n;r++)for(let c=0;c<n;c++){
  const mask=p.row_masks[r]&rightColumns[c];witnesses.push(mask);if(mask)baseColumns[c]+=2**r;
 }
 const profiles=[],bucketMap=new Map(),best=Array(t+1).fill(null);
 const work={right_entries_read:t*n,right_column_masks_created:n,base_witness_intersections:n*n,
  failure_witness_intersections:0,failure_profiles:0,positive_base_entries:witnesses.filter(Boolean).length};
 for(let deleted=0;deleted<2**t;deleted++){
  const residual=witnesses.map(w=>{work.failure_witness_intersections++;return w&~deleted;});
  const columns=Array(n).fill(0),lost=[];
  for(let e=0;e<n*n;e++){const r=Math.floor(e/n),c=e%n;if(residual[e])columns[c]+=2**r;else if(witnesses[e])lost.push(e);}
  const weight=pop(deleted),profile={deleted,weight,witness_masks:residual,column_masks:columns,lost_entries:lost};
  profiles.push(profile);work.failure_profiles++;
  const key=weight+':'+lost.length;if(!bucketMap.has(key))bucketMap.set(key,[]);bucketMap.get(key).push(deleted);
  if(best[weight]===null||lost.length<best[weight].lost)best[weight]={weight,lost:lost.length,deleted:[deleted]};
  else if(lost.length===best[weight].lost)best[weight].deleted.push(deleted);
 }
 const buckets=[...bucketMap].map(([key,deleted])=>{const[weight,lost]=key.split(':').map(Number);return {weight,lost,deleted};}).sort((a,b)=>a.weight-b.weight||a.lost-b.lost);
 return {schema:SCHEMA,prepared:p,right:right.slice(),right_column_masks:rightColumns,base_witness_masks:witnesses,base_column_masks:baseColumns,
  profiles,buckets,best_by_weight:best,phase2_work:work,
  conventions:{entries:'ordered row-column positions, entry=r*n+c',witnesses:'intermediate labels 0..t-1',deletions:'only intermediate nodes may be removed',family_order:'numerical deletion mask',phases:'left input; hint matrix; selected output column'}};
}
function openIndex(snapshot){
 const data=clone(snapshot);if(data.schema!==SCHEMA)throw new TypeError('schema mismatch');
 const {n,t}=preparedContract(data.prepared),N=2**t,rowLimit=2**n-1;
 if(!Array.isArray(data.right)||data.right.length!==t||data.right.some(x=>typeof x!=='string'||x.length!==n||!/^[01]+$/.test(x)))throw new TypeError('right shape');
 if(data.right_column_masks.length!==n||data.base_column_masks.length!==n||data.base_witness_masks.length!==n*n||data.profiles.length!==N)throw new TypeError('index dimensions');
 data.right_column_masks.forEach(x=>int(x,0,N-1,'right mask'));data.base_column_masks.forEach(x=>int(x,0,rowLimit,'base column'));data.base_witness_masks.forEach(x=>int(x,0,N-1,'base witness'));
 data.profiles.forEach((p,d)=>{
  if(p.deleted!==d||p.witness_masks.length!==n*n||p.column_masks.length!==n||!Array.isArray(p.lost_entries))throw new TypeError('profile shape');
  int(p.weight,0,t,'saved weight');p.witness_masks.forEach(x=>int(x,0,N-1,'saved witness'));p.column_masks.forEach(x=>int(x,0,rowLimit,'saved column'));
  let old=-1;for(const e of p.lost_entries){int(e,0,n*n-1,'lost entry');if(e<=old)throw new TypeError('lost entry order');old=e;}
 });
 if(!Array.isArray(data.best_by_weight)||data.best_by_weight.length!==t+1||!Array.isArray(data.buckets))throw new TypeError('summary shape');
 const cache=new Map(),work={saved_profiles_indexed:N,saved_witness_cells_indexed:N*n*n,queries:0,profile_lookups:0,witness_lookups:0,condition_profiles_scanned:0,condition_entry_lookups:0,conditions_created:0,condition_cache_hits:0,binary_search_steps:0,base_witness_intersections:0,failure_witness_intersections:0,profiles_rebuilt:0};
 function deleted(d){return int(d,0,N-1,'deleted');}
 function entry(e){if(!Array.isArray(e)||e.length!==2)throw new TypeError('entry=[row,column] required');return int(e[0],0,n-1,'row')*n+int(e[1],0,n-1,'column');}
 function entries(a){if(!Array.isArray(a))throw new TypeError('entry array required');return [...new Set(a.map(entry))].sort((a,b)=>a-b);}
 function condition(q={}){
  if(!q||typeof q!=='object'||Array.isArray(q))throw new TypeError('condition object required');
  for(const key of Object.keys(q))if(!['zero_entries','one_entries','min_weight','max_weight','min_lost','max_lost'].includes(key))throw new TypeError('unknown condition');
  const zero=entries(q.zero_entries||[]),one=entries(q.one_entries||[]);
  const minW=q.min_weight===undefined?0:int(q.min_weight,0,t,'min_weight'),maxW=q.max_weight===undefined?t:int(q.max_weight,0,t,'max_weight');
  const minL=q.min_lost===undefined?0:int(q.min_lost,0,n*n,'min_lost'),maxL=q.max_lost===undefined?n*n:int(q.max_lost,0,n*n,'max_lost');
  if(minW>maxW||minL>maxL)throw new RangeError('reversed bounds');
  const key=JSON.stringify([zero,one,minW,maxW,minL,maxL]);
  if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}
  if(cache.size>=LIMITS.conditions)throw new RangeError('condition budget exceeded');
  const masks=[];
  for(const p of data.profiles){
   work.condition_profiles_scanned++;
   if(p.weight<minW||p.weight>maxW||p.lost_entries.length<minL||p.lost_entries.length>maxL)continue;
   let good=true;
   for(const e of zero){work.condition_entry_lookups++;if(p.witness_masks[e]!==0){good=false;break;}}
   if(good)for(const e of one){work.condition_entry_lookups++;if(p.witness_masks[e]===0){good=false;break;}}
   if(good)masks.push(p.deleted);
  }
  const c={key,zero_entries:zero.map(e=>[Math.floor(e/n),e%n]),one_entries:one.map(e=>[Math.floor(e/n),e%n]),min_weight:minW,max_weight:maxW,min_lost:minL,max_lost:maxL,count:masks.length,deleted_masks:masks};
  cache.set(key,c);work.conditions_created++;return c;
 }
 function lower(a,x){let lo=0,hi=a.length;while(lo<hi){work.binary_search_steps++;const mid=(lo+hi)>>1;if(a[mid]<x)lo=mid+1;else hi=mid;}return lo;}
 function brief(d){const p=data.profiles[d];work.profile_lookups++;return {deleted:d,intermediates:bits(d,t),weight:p.weight,lost:p.lost_entries.length,column_masks:p.column_masks.slice()};}
 return Object.freeze({
  summary(){work.queries++;return {n,t,phases:'M, V, selected column',failure_profiles:N,positive_base_entries:data.phase2_work.positive_base_entries,bucket_count:data.buckets.length,phase1_work:clone(data.prepared.phase1_work),phase2_work:clone(data.phase2_work)};},
  matrices(){work.queries++;return {left:data.prepared.left.slice(),right:data.right.slice()};},
  column(index,d=0){work.queries++;int(index,0,n-1,'column');deleted(d);const p=data.profiles[d];work.profile_lookups++;return {index,deleted:d,mask:p.column_masks[index],rows:bits(p.column_masks[index],n)};},
  witness(row,column,d=0){work.queries++;int(row,0,n-1,'row');int(column,0,n-1,'column');deleted(d);const mask=data.profiles[d].witness_masks[row*n+column];work.witness_lookups++;return {row,column,deleted:d,mask,intermediates:bits(mask,t),paths:bits(mask,t).map(j=>({source:row,intermediate:j,target:column})),reachable:mask!==0};},
  profile(d){work.queries++;deleted(d);work.profile_lookups++;return clone(data.profiles[d]);},
  profilePage(start=0,limit=16){work.queries++;int(start,0,N,'start');int(limit,0,LIMITS.page,'limit');return {start,total:N,rows:Array.from({length:Math.min(limit,N-start)},(_,i)=>brief(start+i))};},
  buckets(){work.queries++;return clone(data.buckets);},
  bestByWeight(){work.queries++;return clone(data.best_by_weight);},
  failures(q={}){work.queries++;return clone(condition(q));},
  failureSelect(q,rank){work.queries++;int(rank,0,N-1,'rank');const c=condition(q);if(rank>=c.count)throw new RangeError('rank outside failure family');return {rank,...brief(c.deleted_masks[rank])};},
  failureRank(q,d){work.queries++;deleted(d);const c=condition(q),j=lower(c.deleted_masks,d);return {deleted:d,rank:j<c.count&&c.deleted_masks[j]===d?j:null};},
  failurePage(q,start=0,limit=16){work.queries++;const c=condition(q);int(start,0,c.count,'start');int(limit,0,LIMITS.page,'limit');return {start,total:c.count,rows:c.deleted_masks.slice(start,start+limit).map((d,i)=>({rank:start+i,...brief(d)}))};},
  conditions(){return {records:[...cache.values()].map(clone)};},
  work(){return clone(work);}
 });
}
module.exports={LEFT,SCHEMA,LIMITS,prepareLeft,attachHints,openIndex};
