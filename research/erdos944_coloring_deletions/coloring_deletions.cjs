"use strict";
const SCHEMA="commons.coloring-deletion-kernel.v1", SHARD="commons.coloring-deletion-rows.v1";
const LIMITS={vertices:12,edges:24,blocks:3,rows:100000,shard_rows:4096,conditions:12,condition_members:300000,page:64};
function fail(s){throw Error(s);}
function int(x,n,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)fail(n+" outside bounds");return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function pc(x){let n=0;for(;x;x&=x-1)n++;return n;}
function ids(x,n){const a=[];for(let i=0;i<n;i++)if(x&(1<<i))a.push(i);return a;}
function rankInt(x){if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>100)fail("canonical decimal rank required");return BigInt(x);}
function buildIndex(input){
 const n=int(input.vertex_count,"vertices",1,LIMITS.vertices),q=int(input.max_blocks,"blocks",1,LIMITS.blocks);
 if(!Array.isArray(input.edges)||input.edges.length>LIMITS.edges)fail("edges");
 const edges=input.edges.map(e=>{if(!Array.isArray(e)||e.length!==2)fail("edge");const a=int(e[0],"endpoint",0,n-1),b=int(e[1],"endpoint",a+1,n-1);return[a,b];});
 if(new Set(edges.map(e=>e.join(","))).size!==edges.length)fail("duplicate edge");
 if(typeof input.provenance!=="object"||!input.provenance)fail("provenance required");
 const m=edges.length,full=(1<<m)-1,lower=Array.from({length:n},()=>[]);
 edges.forEach(([a,b],i)=>lower[b].push([a,1<<i]));
 const binomial=Array.from({length:m+1},(_,a)=>Array(a+1).fill("1"));
 for(let a=2;a<=m;a++)for(let b=1;b<a;b++)binomial[a][b]=(BigInt(binomial[a-1][b-1])+BigInt(binomial[a-1][b])).toString();
 const falling=Array(q+1).fill("1");for(let j=1;j<=q;j++)falling[j]=(BigInt(falling[j-1])*BigInt(q-j+1)).toString();
 const rows=[],group=new Map(),colors=Array(n).fill(0),hist=Array.from({length:m+1},()=>Array(q+1).fill(0));
 const work={search_nodes:0,edge_comparisons:0,rows:0,kernel_classes:0,binomial_cells:(m+1)*(m+2)/2,incidence_coefficient_additions:0,old_graph_builds:0,old_partition_coefficient_replays:0};
 function visit(v,max,mono,code){work.search_nodes++;if(v===n){
  if(rows.length>=LIMITS.rows)fail("row budget");const j=max+1,c=pc(mono),id=rows.length;
  rows.push([code,j,mono,c,-1]);hist[c][j]++;if(!group.has(mono))group.set(mono,[]);group.get(mono).push(id);return;
 }
 for(let c=0;c<=Math.min(q-1,max+1);c++){colors[v]=c;let next=mono;for(const[a,bit]of lower[v]){work.edge_comparisons++;if(colors[a]===c)next|=bit;}visit(v+1,Math.max(max,c),next,code*q+c);}
 }
 visit(0,-1,0,0);work.rows=rows.length;
 const classes=[...group.keys()].sort((a,b)=>a-b).map((mask,i)=>{const members=group.get(mask),by_blocks=Array(q+1).fill(0);for(const r of members){rows[r][4]=i;by_blocks[rows[r][1]]++;}return{mask,size:pc(mask),members,by_blocks};});
 work.kernel_classes=classes.length;
 const incidence=Array.from({length:m+1},()=>Array(q+1).fill(0n));
 for(let c=0;c<=m;c++)for(let j=1;j<=q;j++)if(hist[c][j])for(let h=c;h<=m;h++){incidence[h][j]+=BigInt(hist[c][j])*BigInt(binomial[m-c][h-c]);work.incidence_coefficient_additions++;}
 const spectrum=incidence.map((a,h)=>({deletions:h,by_blocks:a.map(String),canonical:a.reduce((x,y)=>x+y,0n).toString(),labelled:a.reduce((x,y,j)=>x+y*BigInt(falling[j]),0n).toString()}));
 const singles=edges.map((e,i)=>{const a=classes.filter(c=>(c.mask&~(1<<i))===0).reduce((z,c)=>z.map((v,j)=>v+c.by_blocks[j]),Array(q+1).fill(0));return{edge_id:i,endpoints:e,by_blocks:a,canonical:a.reduce((x,y)=>x+y,0),labelled:a.reduce((x,y,j)=>x+BigInt(y)*BigInt(falling[j]),0n).toString()};});
 const shards=[];for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 const index={schema:SCHEMA,graph:{vertex_count:n,edges,max_blocks:q,full_edge_mask:full},provenance:copy(input.provenance),inherited:copy(input.inherited||null),ordering:{partition:"restricted-growth strings in lexicographic order; vertex 0 has color 0",joint:"partition row first, then lexicographic increasing lists of extra deleted edge IDs",color_classes:"canonical unlabelled nonempty blocks; named q-color count multiplies by (q)_j"},binomial,falling,classes,histogram:hist,deletion_incidence:spectrum,single_edge_deletions:singles,summary:{partitions:rows.length,kernel_classes:classes.length,minimum_required_deletions:Math.min(...classes.map(c=>c.size)),edge_count:m,vertex_count:n,max_blocks:q},construction:work,row_shards:shards.map(s=>({start:s.start,count:s.rows.length}))};
 return{index,shards};
}
function openIndex(saved,shards){
 const index=copy(saved);if(index.schema!==SCHEMA)fail("schema");
 const n=int(index.graph.vertex_count,"vertices",1,LIMITS.vertices),q=int(index.graph.max_blocks,"blocks",1,LIMITS.blocks),m=int(index.graph.edges.length,"edges",0,LIMITS.edges),full=(1<<m)-1;
 const rows=[];if(!Array.isArray(shards)||shards.length!==index.row_shards.length)fail("shard count");
 for(let i=0;i<shards.length;i++){const s=shards[i],expected=index.row_shards[i];if(s.schema!==SHARD||s.start!==rows.length||s.start!==expected.start||s.rows.length!==expected.count)fail("shard range");rows.push(...copy(s.rows));}
 if(rows.length!==index.summary.partitions||rows.length>LIMITS.rows)fail("row count");
 let last=-1;const codeMap=new Map();rows.forEach((r,i)=>{if(!Array.isArray(r)||r.length!==5)fail("row shape");int(r[0],"code",0,q**n-1);if(r[0]<=last)fail("row order");last=r[0];int(r[1],"block count",1,q);int(r[2],"required mask",0,full);int(r[3],"required size",0,m);int(r[4],"class",0,index.classes.length-1);codeMap.set(r[0],i);});
 const seen=new Set();index.classes.forEach((c,i)=>{int(c.mask,"class mask",0,full);if(!Array.isArray(c.members))fail("class members");for(const r of c.members){int(r,"member",0,rows.length-1);if(seen.has(r)||rows[r][4]!==i||rows[r][2]!==c.mask)fail("class linkage");seen.add(r);}});
 if(seen.size!==rows.length)fail("class coverage");
 if(index.binomial.length!==m+1||index.falling.length!==q+1)fail("coefficient shape");
 index.binomial.forEach((a,i)=>{if(a.length!==i+1)fail("binomial shape");a.forEach(rankInt);});index.falling.forEach(rankInt);
 const caches=[],cacheMap=new Map();let totalMembers=0;
 const work={rows_indexed:rows.length,queries:0,condition_row_scans:0,partition_decodes:0,binomial_lookups:0,selection_binary_steps:0,combination_steps:0,condition_cache_hits:0,rank_member_checks:0,new_partitions:0,new_edge_comparisons:0,new_kernel_classes:0,new_binomial_cells:0};
 const choose=(a,b)=>{work.binomial_lookups++;return b<0||b>a?0n:BigInt(index.binomial[a][b]);};
 function decode(code){work.partition_decodes++;const a=Array(n);for(let i=n-1;i>=0;i--){a[i]=code%q;code=Math.floor(code/q);}return a;}
 function condition(raw){
  if(!raw||typeof raw!=="object")fail("condition");const exact=Object.hasOwn(raw,"deleted");
  if(exact===Object.hasOwn(raw,"budget"))fail("provide exactly one of deleted or budget");
  const include=raw.must_delete===undefined?0:int(raw.must_delete,"must_delete",0,full),keep=raw.must_keep===undefined?0:int(raw.must_keep,"must_keep",0,full);
  const blocks=raw.blocks===undefined?Array.from({length:q},(_,i)=>i+1):raw.blocks;
  if(!Array.isArray(blocks)||new Set(blocks).size!==blocks.length)fail("blocks");blocks.forEach(x=>int(x,"block",1,q));
  const fixed=raw.fixed===undefined?[]:raw.fixed;if(!Array.isArray(fixed)||fixed.length>n)fail("fixed");
  const fv=new Set();for(const pair of fixed){if(!Array.isArray(pair)||pair.length!==2)fail("fixed pair");int(pair[0],"vertex",0,n-1);int(pair[1],"canonical color",0,q-1);if(fv.has(pair[0]))fail("duplicate fixed vertex");fv.add(pair[0]);}
  const c={mode:exact?"exact":"budget",value:exact?int(raw.deleted,"deleted",0,full):int(raw.budget,"budget",0,m),include,keep,blocks:[...blocks].sort((a,b)=>a-b),fixed:copy(fixed).sort((a,b)=>a[0]-b[0])},key=JSON.stringify(c);
  if(cacheMap.has(key)){work.condition_cache_hits++;return caches[cacheMap.get(key)];}
  if(caches.length>=LIMITS.conditions)fail("condition cache cap");
  const members=[];let total=0n,labelled=0n;
  const impossible=!!(include&keep)||(exact&&((c.value&include)!==include||!!(c.value&keep)));
  for(let r=0;r<rows.length;r++){work.condition_row_scans++;const row=rows[r];if(impossible||!c.blocks.includes(row[1])||(row[2]&keep))continue;
   if(c.fixed.length){const a=decode(row[0]);if(c.fixed.some(([v,color])=>a[v]!==color))continue;}
   let base,free,k,w;if(exact){if(row[2]&~c.value)continue;base=c.value;free=0;k=0;w=1n;}
   else{base=row[2]|include;free=full&~(base|keep);k=c.value-pc(base);w=choose(pc(free),k);if(!w)continue;}
   total+=w;labelled+=w*BigInt(index.falling[row[1]]);members.push([r,base,free,k,w.toString(),total.toString()]);
  }
  if(totalMembers+members.length>LIMITS.condition_members)fail("condition member cap");
  totalMembers+=members.length;const result={id:caches.length,condition:c,count:total.toString(),named_color_count_without_fixed_label_semantics:labelled.toString(),members};caches.push(result);cacheMap.set(key,result.id);return result;
 }
 function cache(i){return caches[int(i,"condition id",0,caches.length-1)];}
 function combinationSelect(free,k,r){const avail=ids(free,m),out=[];let at=0;for(let j=0;j<k;j++)for(let p=at;p<avail.length;p++){work.combination_steps++;const w=choose(avail.length-p-1,k-j-1);if(r<w){out.push(avail[p]);at=p+1;break;}r-=w;}return out;}
 function selected(id,rank){const c=cache(id),r=rankInt(rank);if(r>=BigInt(c.count))fail("rank out of range");
  let lo=0,hi=c.members.length-1;while(lo<hi){work.selection_binary_steps++;const mid=(lo+hi)>>1;if(BigInt(c.members[mid][5])>r)hi=mid;else lo=mid+1;}
  const entry=c.members[lo],prior=lo?BigInt(c.members[lo-1][5]):0n,extra=combinationSelect(entry[2],entry[3],r-prior),row=rows[entry[0]];
  let deleted=entry[1];extra.forEach(e=>deleted|=1<<e);const colors=decode(row[0]),blocks=Array.from({length:row[1]},()=>[]);colors.forEach((c,v)=>blocks[c].push(v));
  return{condition:id,rank,row:entry[0],code:row[0],colors,blocks,required_edge_mask:row[2],deleted_edge_mask:deleted,deleted_edges:ids(deleted,m),extra_edges:extra};
 }
 function ranked(id,rowId,deleted){const c=cache(id);int(rowId,"row",0,rows.length-1);int(deleted,"deleted",0,full);let p=-1;for(let i=0;i<c.members.length;i++){work.rank_member_checks++;if(c.members[i][0]===rowId){p=i;break;}}if(p<0)return null;
  const e=c.members[p];if((deleted&e[1])!==e[1]||(deleted&~(e[1]|e[2])))return null;const extra=deleted&~e[1];if(pc(extra)!==e[3])return null;
  const avail=ids(e[2],m),selectedIds=ids(extra,m);let r=0n,at=0;
  for(let j=0;j<selectedIds.length;j++){const pos=avail.indexOf(selectedIds[j]);for(let p=at;p<pos;p++){work.combination_steps++;r+=choose(avail.length-p-1,selectedIds.length-j-1);}at=pos+1;}
  return((p?BigInt(c.members[p-1][5]):0n)+r).toString();
 }
 return{
  summary(){work.queries++;return copy({summary:index.summary,construction:index.construction,inherited:index.inherited,single_edge_deletions:index.single_edge_deletions,deletion_incidence:index.deletion_incidence});},
  row(r){work.queries++;int(r,"row",0,rows.length-1);const x=rows[r];return{row:r,code:x[0],blocks:x[1],required_mask:x[2],required_size:x[3],class_id:x[4],colors:decode(x[0])};},
  rowForColors(a){work.queries++;if(!Array.isArray(a)||a.length!==n)fail("colors");let code=0,max=-1;for(const c of a){int(c,"restricted-growth color",0,Math.min(q-1,max+1));max=Math.max(max,c);code=code*q+c;}return codeMap.get(code)??null;},
  kernel(i){work.queries++;return copy(index.classes[int(i,"class",0,index.classes.length-1)]);},
  condition(c){work.queries++;const x=condition(c);return{id:x.id,condition:copy(x.condition),count:x.count,named_color_count_without_fixed_label_semantics:x.named_color_count_without_fixed_label_semantics,represented_rows:x.members.length};},
  select(id,r){work.queries++;return selected(id,r);},
  rank(id,rowId,deleted){work.queries++;return ranked(id,rowId,deleted);},
  page(id,start,count){work.queries++;const c=cache(id),s=rankInt(start);int(count,"page",0,LIMITS.page);if(s>BigInt(c.count))fail("page start");const a=[];for(let j=0;j<count&&s+BigInt(j)<BigInt(c.count);j++)a.push(selected(id,(s+BigInt(j)).toString()));return a;},
  caches(){work.queries++;return copy(caches);},
  work(){return copy(work);}
 };
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
