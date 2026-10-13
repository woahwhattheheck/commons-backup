'use strict';
const SCHEMA='commons.tree_embeddings/v1', SHARD='commons.tree_embedding_rows/v1';
const LIMITS=Object.freeze({parts:8,part_size:12,host_vertices:60,tree_vertices:16,templates:200000,shard_rows:4096,conditions:32,page:32});
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new TypeError(name+' outside contract');return x;}
function decimal(x,name){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError(name+' must be canonical nonnegative decimal');return BigInt(x);}
function copy(x){return JSON.parse(JSON.stringify(x));}
function graph(n,edges,name){if(!Array.isArray(edges))throw new TypeError(name);const seen=new Set(),out=[],adj=Array.from({length:n},()=>[]);for(const e of edges){if(!Array.isArray(e)||e.length!==2)throw new TypeError(name);let [a,b]=e;integer(a,0,n-1,name);integer(b,0,n-1,name);if(a===b)throw new TypeError(name+' loop');if(a>b)[a,b]=[b,a];const key=a+','+b;if(seen.has(key))throw new TypeError(name+' duplicate');seen.add(key);out.push([a,b]);adj[a].push(b);adj[b].push(a);}out.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);for(const a of adj)a.sort((x,y)=>x-y);return {edges:out,adj};}
function decode(code,b,h){const a=[];for(let i=0;i<h;i++){a.push(code%b);code=Math.floor(code/b);}if(code)throw new TypeError('template overflow');return a;}
function buildIndex(input){
 const sizes=input.part_sizes;if(!Array.isArray(sizes))throw new TypeError('part sizes');const b=integer(sizes.length,1,LIMITS.parts,'parts'),w=sizes.map(x=>integer(x,1,LIMITS.part_size,'part size')),n=w.reduce((a,x)=>a+x,0);integer(n,1,LIMITS.host_vertices,'host size');
 const h=integer(input.tree_vertices,1,LIMITS.tree_vertices,'tree size'),host=graph(b,input.base_edges,'base edges'),tree=graph(h,input.tree_edges,'tree edges');
 if(tree.edges.length!==h-1)throw new TypeError('tree needs h-1 edges');const parent=Array(h).fill(-2),order=[0];parent[0]=-1;for(let at=0;at<order.length;at++)for(const v of tree.adj[order[at]])if(parent[v]===-2){parent[v]=order[at];order.push(v);}if(order.length!==h)throw new TypeError('tree disconnected');
 const offsets=[0];for(const s of w)offsets.push(offsets.at(-1)+s);
 const work={falling_cells:0,search_nodes:0,complete_templates:0,capacity_rejections:0,weight_factors:0,profile_additions:0};
 const falling=[];for(let s=0;s<=Math.max(...w);s++){let z=1n;const a=['1'];work.falling_cells++;for(let k=1;k<=h;k++){z=k>s?0n:z*BigInt(s-k+1);a.push(z.toString());work.falling_cells++;}falling.push(a);}
 const assigned=Array(h).fill(0),counts=Array(b).fill(0),rows=[],profiles=new Map();let positive=0;
 function visit(depth,code){work.search_nodes++;if(depth===h){if(rows.length>=LIMITS.templates)throw new RangeError('template budget exceeded');work.complete_templates++;let z=1n;for(let p=0;p<b;p++){z*=BigInt(falling[w[p]][counts[p]]);work.weight_factors++;}if(z>0n)positive++;else work.capacity_rejections++;rows.push([code,z.toString()]);const key=counts.join(',');if(!profiles.has(key))profiles.set(key,{occupancy:counts.slice(),templates:0,embeddings:0n});const pr=profiles.get(key);pr.templates++;pr.embeddings+=z;work.profile_additions++;return;}
 const v=order[depth],choices=depth===0?Array.from({length:b},(_,i)=>i):host.adj[assigned[parent[v]]];for(const p of choices){assigned[v]=p;counts[p]++;visit(depth+1,code+p*b**v);counts[p]--;}}
 visit(0,0);rows.sort((a,c)=>a[0]-c[0]);let total=0n;for(const row of rows){total+=BigInt(row[1]);row.push(total.toString());}
 const shards=[];for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 const index={schema:SCHEMA,part_sizes:w,offsets,host_vertices:n,base_edges:host.edges,tree_vertices:h,tree_edges:tree.edges,traversal:order,parent,falling,row_count:rows.length,row_schema:['part_code','labelled_injections','cumulative_injections'],row_order:'increasing code; tree vertex 0 is least-significant base-part digit',positive_templates:positive,zero_templates:rows.length-positive,total_embeddings:total.toString(),profiles:[...profiles.values()].sort((a,c)=>a.occupancy.join(',').localeCompare(c.occupancy.join(','))).map(p=>({...p,embeddings:p.embeddings.toString()})),shards:shards.map(s=>({start:s.start,rows:s.rows.length})),work};
 return {index,shards};
}
function openIndex(index,shards){
 const x=copy(index),ss=copy(shards);if(x.schema!==SCHEMA||!Array.isArray(ss))throw new TypeError('schema');
 const b=integer(x.part_sizes.length,1,LIMITS.parts,'parts'),h=integer(x.tree_vertices,1,LIMITS.tree_vertices,'tree size'),n=integer(x.host_vertices,1,LIMITS.host_vertices,'host size');
 if(x.offsets.length!==b+1||x.offsets[0]!==0||x.offsets[b]!==n)throw new TypeError('offsets');for(let p=0;p<b;p++){integer(x.part_sizes[p],1,LIMITS.part_size,'part size');if(x.offsets[p+1]-x.offsets[p]!==x.part_sizes[p])throw new TypeError('offsets');}
 const rows=[],byCode=new Map(),work={rows_indexed:0,structural_prefix_checks:0,queries:0,conditions:0,condition_cache_hits:0,saved_row_scans:0,template_decodes:0,falling_lookups:0,condition_weight_products:0,condition_prefix_additions:0,binary_steps:0,permutation_steps:0,edge_witness_lookups:0,rank_template_scans:0,new_templates:0,new_falling_cells:0,new_base_edges:0};
 let prev=-1,sum=0n;
 for(let i=0;i<ss.length;i++){const s=ss[i],meta=x.shards[i];if(!meta||s.schema!==SHARD||s.start!==rows.length||meta.start!==s.start||meta.rows!==s.rows.length)throw new TypeError('shard span');for(const r of s.rows){if(!Array.isArray(r)||r.length!==3)throw new TypeError('row shape');integer(r[0],0,b**h-1,'part code');if(r[0]<=prev)throw new TypeError('row order');prev=r[0];sum+=decimal(r[1],'weight');if(sum!==decimal(r[2],'cumulative'))throw new TypeError('saved cumulative');byCode.set(r[0],rows.length);rows.push(r);work.rows_indexed++;work.structural_prefix_checks++;}}
 if(ss.length!==x.shards.length||rows.length!==x.row_count||sum!==decimal(x.total_embeddings,'total'))throw new TypeError('index coverage');
 function parts(code){work.template_decodes++;return decode(code,b,h);}
 function ff(s,k){work.falling_lookups++;if(k<0||k>s)return 0n;if(!x.falling[s]||x.falling[s][k]===undefined)throw new TypeError('falling table');return decimal(x.falling[s][k],'falling');}
 function hostPart(v){integer(v,0,n-1,'host label');let p=0;while(v>=x.offsets[p+1])p++;return p;}
 const cache=new Map();
 function normalize(condition={}){if(!condition||typeof condition!=='object'||Array.isArray(condition))throw new TypeError('condition');for(const k of Object.keys(condition))if(k!=='fixed'&&k!=='root_parts')throw new TypeError('unknown condition');
 const fixed=condition.fixed===undefined?[]:copy(condition.fixed);if(!Array.isArray(fixed))throw new TypeError('fixed');const seen=new Set();for(const p of fixed){if(!Array.isArray(p)||p.length!==2)throw new TypeError('fixed pair');integer(p[0],0,h-1,'tree label');integer(p[1],0,n-1,'host label');if(seen.has(p[0]))throw new TypeError('duplicate fixed tree label');seen.add(p[0]);}fixed.sort((a,c)=>a[0]-c[0]);
 const roots=condition.root_parts===undefined?Array.from({length:b},(_,i)=>i):copy(condition.root_parts);if(!Array.isArray(roots))throw new TypeError('root parts');for(const p of roots)integer(p,0,b-1,'root part');if(new Set(roots).size!==roots.length)throw new TypeError('duplicate root part');roots.sort((a,c)=>a-c);return {fixed,root_parts:roots};}
 function conditionData(c={}){const c0=normalize(c),key=JSON.stringify(c0);if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}if(cache.size>=LIMITS.conditions)throw new RangeError('condition cache cap');
 const req=c0.fixed.map(([v,u])=>[v,u,hostPart(u)]),used=Array.from({length:b},()=>new Set());for(const [,u,p] of req)used[p].add(u);const duplicate=new Set(req.map(r=>r[1])).size!==req.length;
 const admitted=[];let total=0n;for(let i=0;i<rows.length;i++){work.saved_row_scans++;const row=rows[i];if(row[1]==='0'||duplicate)continue;const a=parts(row[0]);if(!c0.root_parts.includes(a[0])||req.some(([v,,p])=>a[v]!==p))continue;
 let z;if(req.length===0)z=BigInt(row[1]);else {z=1n;for(let p=0;p<b;p++){const occupancy=a.filter(v=>v===p).length,fixedCount=used[p].size;z*=ff(x.part_sizes[p]-fixedCount,occupancy-fixedCount);work.condition_weight_products++;}}
 if(z){total+=z;admitted.push([i,z.toString(),total.toString()]);work.condition_prefix_additions++;}}
 const result={id:cache.size,condition:c0,total:total.toString(),template_count:admitted.length,admitted};cache.set(key,result);work.conditions++;return result;}
 function groupInfo(a,c){const fixed=new Map(c.fixed),out=[];for(let p=0;p<b;p++){const vs=[];for(let v=0;v<h;v++)if(a[v]===p&&!fixed.has(v))vs.push(v);const used=new Set(c.fixed.filter(([,u])=>hostPart(u)===p).map(([,u])=>u));const available=[];for(let u=x.offsets[p];u<x.offsets[p+1];u++)if(!used.has(u))available.push(u);out.push({vertices:vs,available,weight:ff(available.length,vs.length)});}return out;}
 function unperm(available,k,rank){const pool=available.slice(),out=[];for(let j=0;j<k;j++){work.permutation_steps++;const block=ff(pool.length-1,k-j-1),digit=Number(rank/block);rank%=block;out.push(pool.splice(digit,1)[0]);}return out;}
 function rankperm(available,selected){const pool=available.slice();let r=0n;for(let j=0;j<selected.length;j++){work.permutation_steps++;const d=pool.indexOf(selected[j]);if(d<0)throw new TypeError('noninjective or invalid part mapping');r+=BigInt(d)*ff(pool.length-1,selected.length-j-1);pool.splice(d,1);}return r;}
 function findEntry(data,rank){let lo=0,hi=data.admitted.length;while(lo<hi){work.binary_steps++;const mid=(lo+hi)>>1;if(BigInt(data.admitted[mid][2])>rank)hi=mid;else lo=mid+1;}return lo;}
 function select0(rank,c){const data=conditionData(c),r=decimal(rank,'rank');if(r>=BigInt(data.total))throw new RangeError('rank');const pos=findEntry(data,r),entry=data.admitted[pos],row=rows[entry[0]],a=parts(row[0]),groups=groupInfo(a,data.condition);let within=r-(pos?BigInt(data.admitted[pos-1][2]):0n),remainder=within;const digits=Array(b);for(let p=b-1;p>=0;p--){digits[p]=remainder%groups[p].weight;remainder/=groups[p].weight;}
 const map=Array(h).fill(-1);for(const [v,u] of data.condition.fixed)map[v]=u;for(let p=0;p<b;p++){const picked=unperm(groups[p].available,groups[p].vertices.length,digits[p]);groups[p].vertices.forEach((v,j)=>map[v]=picked[j]);}
 return {rank:r.toString(),condition_id:data.id,template_row:entry[0],part_code:row[0],parts:a,within_template:within.toString(),part_ranks:digits.map(String),mapping:map};}
 function rank0(mapping,c){if(!Array.isArray(mapping)||mapping.length!==h)throw new TypeError('mapping size');for(const u of mapping)integer(u,0,n-1,'host label');if(new Set(mapping).size!==h)throw new TypeError('mapping must be injective');const data=conditionData(c);if(data.condition.fixed.some(([v,u])=>mapping[v]!==u))throw new TypeError('fixed mapping mismatch');const a=mapping.map(hostPart),code=a.reduce((z,p,v)=>z+p*b**v,0),rowid=byCode.get(code);if(rowid===undefined)throw new TypeError('not an edge-preserving template');const pos=data.admitted.findIndex(e=>{work.rank_template_scans++;return e[0]===rowid;});if(pos<0)throw new TypeError('mapping excluded by condition');const groups=groupInfo(a,data.condition);let within=0n;const digits=[];for(let p=0;p<b;p++){const d=rankperm(groups[p].available,groups[p].vertices.map(v=>mapping[v]));digits.push(d.toString());within=within*groups[p].weight+d;}
 const rank=(pos?BigInt(data.admitted[pos-1][2]):0n)+within;return {rank:rank.toString(),condition_id:data.id,template_row:rowid,part_code:code,within_template:within.toString(),part_ranks:digits};}
 return {
 summary(){work.queries++;return copy({schema:x.schema,part_sizes:x.part_sizes,host_vertices:n,tree_vertices:h,tree_edges:x.tree_edges,row_count:x.row_count,positive_templates:x.positive_templates,zero_templates:x.zero_templates,total_embeddings:x.total_embeddings,profiles:x.profiles.length});},
 profiles(){work.queries++;return copy(x.profiles);},
 template(row){work.queries++;integer(row,0,rows.length-1,'row');return {row,code:rows[row][0],parts:parts(rows[row][0]),weight:rows[row][1],cumulative:rows[row][2]};},
 family(c){work.queries++;const d=conditionData(c);return copy({id:d.id,condition:d.condition,total:d.total,template_count:d.template_count});},
 select(rank,c){work.queries++;return select0(rank,c);},
 rank(mapping,c){work.queries++;return rank0(mapping,c);},
 page(start,count,c){work.queries++;const d=conditionData(c),r=decimal(start,'start');integer(count,0,LIMITS.page,'page count');if(r>BigInt(d.total))throw new RangeError('start');const out=[];for(let j=0;j<count&&r+BigInt(j)<BigInt(d.total);j++)out.push(select0((r+BigInt(j)).toString(),c));return {total:d.total,start:r.toString(),values:out};},
 witness(mapping){work.queries++;const ranked=rank0(mapping,{});const edges=x.tree_edges.map(([u,v])=>{work.edge_witness_lookups++;return {tree_edge:[u,v],host_edge:[mapping[u],mapping[v]],base_edge:[hostPart(mapping[u]),hostPart(mapping[v])].sort((a,c)=>a-c)};});return {mapping:copy(mapping),rank:ranked.rank,edges};},
 conditions(){work.queries++;return copy([...cache.values()]);},
 work(){return copy(work);}
 };
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
