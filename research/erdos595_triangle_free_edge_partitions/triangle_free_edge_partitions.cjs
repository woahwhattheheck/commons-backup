'use strict';
function nat(x,name,max){if(!Number.isSafeInteger(x)||x<0||(max!==undefined&&x>max))throw new RangeError(name);return x;}
function big(x,name){if(typeof x==='number'&&!Number.isSafeInteger(x))throw new TypeError(name);if(typeof x!=='number'&&typeof x!=='bigint'&&!(typeof x==='string'&&/^\d+$/.test(x)))throw new TypeError(name);const b=BigInt(x);if(b<0n)throw new RangeError(name);return b;}
function compile(input){
 const n=nat(input.vertices,'vertices',12),edges=input.edges,m=edges.length,lim=input.limits||{};nat(m,'edges',16);
 const size=2**m;if(size*(m+1)>(lim.max_cells||1000000))throw new RangeError('coefficient budget');
 const at=Array.from({length:n},()=>Array(n).fill(-1));for(let i=0;i<m;i++){const [a,b]=edges[i];nat(a,'vertex',n-1);nat(b,'vertex',n-1);if(a>=b||at[a][b]>=0)throw new Error('edge shape');at[a][b]=at[b][a]=i;}
 const triangles=[],work={vertex_triples:0,triangle_constraints:0,triangle_tests:0,edge_masks:0,candidate_blocks:0,retained_branches:0,coefficient_additions:0,coefficient_cells:size*(m+1),old_graph_enumeration:0,old_independence:0,old_octahedron_tests:0};
 for(let a=0;a<n;a++)for(let b=a+1;b<n;b++)for(let c=b+1;c<n;c++){work.vertex_triples++;const ids=[at[a][b],at[a][c],at[b][c]];if(ids.every(x=>x>=0))triangles.push({id:triangles.length,vertices:[a,b,c],edge_ids:ids,mask:ids.reduce((s,x)=>s|(1<<x),0)});}
 work.triangle_constraints=triangles.length;
 const bad=Array(size).fill(-1);for(let s=0;s<size;s++){work.edge_masks++;for(const t of triangles){work.triangle_tests++;if((s&t.mask)===t.mask){bad[s]=t.id;break;}}}
 const branches=Array.from({length:size},()=>[]),rows=Array.from({length:size},()=>Array(m+1).fill(0n));rows[0][0]=1n;
 for(let s=1;s<size;s++){const e=s&-s;for(let b=s;b;b=(b-1)&s){if(!(b&e))continue;work.candidate_blocks++;if(bad[b]===-1){branches[s].push(b);if(++work.retained_branches>(lim.max_branch_records||1000000))throw new RangeError('branch budget');}}
 branches[s].sort((a,b)=>a-b);for(const b of branches[s]){const child=rows[s^b];for(let k=1;k<=m;k++){rows[s][k]+=child[k-1];work.coefficient_additions++;}}}
 const full=size-1,minimum=rows[full].findIndex(x=>x>0n),totals=rows.map(row=>String(row.reduce((a,b)=>a+b,0n)));
 return{format:'triangle-edge-partitions-v1',input,edge_count:m,full_mask:full,triangles,first_bad_triangle:bad,branches,rows:rows.map(row=>row.map(String)),partition_totals:totals,summary:{vertices:n,edges:m,edge_subgraphs:size,triangles:triangles.length,triangle_free_masks:bad.filter(x=>x<0).length,minimum_full_blocks:minimum,full_partition_coefficients:rows[full].map(String),full_partitions:totals[full]},construction_work:work};
}
function openIndex(saved){
 if(saved.format!=='triangle-edge-partitions-v1')throw new Error('format');const m=saved.edge_count,full=saved.full_mask,fallingCache=new Map(),paletteCache=new Map();
 const w={coefficient_reads:0,branch_reads:0,rank_additions:0,selected_partitions:0,falling_multiplications:0,palette_multiplications:0,palette_additions:0,injection_divisions:0,color_label_comparisons:0,edge_decodes:0,new_triangle_tests:0,new_partition_coefficients:0,new_branches:0};
 function mask(s){return nat(s,'edge mask',full);}
 function coef(s,k){w.coefficient_reads++;return BigInt(saved.rows[s][k]);}
 function profile(s){mask(s);return{mask:s,coefficients:saved.rows[s],total:saved.partition_totals[s],minimum_blocks:saved.rows[s].findIndex(x=>x!=='0')};}
 function blockEdges(b){const ids=[];for(let i=0;i<m;i++){w.edge_decodes++;if(b&(1<<i))ids.push(i);}return ids;}
 function partitionSelect(s,k,rank){
  mask(s);nat(k,'blocks',m);let r=big(rank,'rank'),total=coef(s,k);if(r>=total)throw new RangeError('partition rank');const original=s,originalRank=String(r),count=k,blocks=[],trace=[];
  while(s){let chosen=false;for(const b of saved.branches[s]){w.branch_reads++;const c=coef(s^b,k-1),before=String(r);if(r>=c){r-=c;}else{trace.push({remaining:s,block:b,completions:String(c),rank_before:before});blocks.push(b);s^=b;k--;chosen=true;break;}}if(!chosen)throw new Error('saved partition inconsistency');}
  if(k!==0)throw new Error('saved terminal inconsistency');w.selected_partitions++;return{mask:original,block_count:count,rank:originalRank,total:String(total),blocks,edge_ids:blocks.map(blockEdges),trace};
 }
 function canonicalBlocks(s,blocks){mask(s);if(!Array.isArray(blocks)||blocks.length>m)throw new RangeError('blocks');let used=0;const a=blocks.slice();for(const b of a){mask(b);if(!b||(used&b)||(b&s)!==b)throw new RangeError('partition shape');used|=b;}if(used!==s)throw new RangeError('partition coverage');a.sort((a,b)=>(a&-a)-(b&-b));return a;}
 function partitionRank(s,blocks){
  const a=canonicalBlocks(s,blocks),original=s;let rank=0n,k=a.length;const trace=[];
  for(const b of a){if(saved.first_bad_triangle[b]>=0)return{mask:original,blocks:a,rank:null,triangle:saved.triangles[saved.first_bad_triangle[b]]};let found=false,add=0n;for(const c of saved.branches[s]){w.branch_reads++;if(c===b){found=true;break;}if(c>b)break;add+=coef(s^c,k-1);w.rank_additions++;}if(!found)throw new Error('saved branch absent');rank+=add;trace.push({remaining:s,block:b,added:String(add),rank:String(rank)});s^=b;k--;}
  return{mask:original,block_count:a.length,blocks:a,rank:String(rank),trace};
 }
 function falling(q){const key=String(q);if(fallingCache.has(key))return fallingCache.get(key);const row=[1n];for(let k=1;k<=m;k++){row.push(q<BigInt(k)?0n:row[k-1]*(q-BigInt(k-1)));w.falling_multiplications++;}fallingCache.set(key,row);return row;}
 function paletteProfile(s,qValue){mask(s);const q=big(qValue,'palette'),key=s+':'+q;if(paletteCache.has(key))return paletteCache.get(key);const f=falling(q),buckets=[];let total=0n;for(let k=0;k<=m;k++){const count=coef(s,k)*f[k];w.palette_multiplications++;buckets.push({blocks:k,partitions:saved.rows[s][k],injections:String(f[k]),count:String(count),start:String(total)});total+=count;w.palette_additions++;}const p={mask:s,palette:String(q),count:String(total),buckets};paletteCache.set(key,p);return p;}
 function injectionSelect(q,k,rank){let r=rank,count=falling(q)[k];const used=[],labels=[],trace=[];for(let i=0;i<k;i++){const block=count/(q-BigInt(i));w.injection_divisions++;const digit=r/block;r%=block;let color=digit;for(const u of used){w.color_label_comparisons++;if(u<=color)color++;else break;}labels.push(color);used.push(color);used.sort((a,b)=>a<b?-1:a>b?1:0);trace.push({position:i,unused_rank:String(digit),color:String(color),suffix_count:String(block)});count=block;}return{labels,trace};}
 function injectionRank(q,labels){let rank=0n,count=falling(q)[labels.length];const used=[],trace=[];for(let i=0;i<labels.length;i++){const color=labels[i];if(color<0n||color>=q||used.includes(color))throw new RangeError('color injection');let digit=color;for(const u of used){w.color_label_comparisons++;if(u<color)digit--;}const block=count/(q-BigInt(i));w.injection_divisions++;rank+=digit*block;trace.push({position:i,color:String(color),unused_rank:String(digit),rank:String(rank)});used.push(color);count=block;}return{rank,trace};}
 function colorSelect(s,qValue,rankValue){const q=big(qValue,'palette'),p=paletteProfile(s,q),rank=big(rankValue,'rank');if(rank>=BigInt(p.count))throw new RangeError('color rank');const b=p.buckets.find(b=>rank>=BigInt(b.start)&&rank<BigInt(b.start)+BigInt(b.count)),local=rank-BigInt(b.start),factor=BigInt(b.injections);const partitionRankValue=local/factor,injectionRankValue=local%factor,part=partitionSelect(s,b.blocks,partitionRankValue),inj=injectionSelect(q,b.blocks,injectionRankValue),colors=Array(m).fill(null);
 for(let j=0;j<part.blocks.length;j++)for(const e of part.edge_ids[j])colors[e]=String(inj.labels[j]);
 return{mask:s,palette:String(q),rank:String(rank),total:p.count,block_count:b.blocks,partition_rank:String(partitionRankValue),injection_rank:String(injectionRankValue),blocks:part.blocks,block_colors:inj.labels.map(String),edge_colors:colors,partition_trace:part.trace,injection_trace:inj.trace};
 }
 function colorRank(s,qValue,colors){
  mask(s);const q=big(qValue,'palette');if(!Array.isArray(colors)||colors.length!==m)throw new RangeError('color array');const groups=new Map();
  for(let e=0;e<m;e++){w.edge_decodes++;if(s&(1<<e)){const c=big(colors[e],'color');if(c>=q)throw new RangeError('color');groups.set(String(c),(groups.get(String(c))||0)|(1<<e));}else if(colors[e]!==null)throw new RangeError('inactive edge color');}
  const entries=[...groups.entries()].sort((a,b)=>(a[1]&-a[1])-(b[1]&-b[1])),blocks=entries.map(x=>x[1]),labels=entries.map(x=>BigInt(x[0])),p=partitionRank(s,blocks);if(p.rank===null)return{mask:s,palette:String(q),rank:null,triangle:p.triangle};const inj=injectionRank(q,labels),profile=paletteProfile(s,q),b=profile.buckets[blocks.length],rank=BigInt(b.start)+BigInt(p.rank)*BigInt(b.injections)+inj.rank;
  return{mask:s,palette:String(q),rank:String(rank),blocks,block_colors:labels.map(String),partition_rank:p.rank,injection_rank:String(inj.rank),partition_trace:p.trace,injection_trace:inj.trace};
 }
 function partitionPage(s,k,start,limit){nat(limit,'limit',100);let r=big(start,'start'),count=coef(mask(s),nat(k,'blocks',m));if(r>count)throw new RangeError('start');const rows=[];while(rows.length<limit&&r<count){rows.push(partitionSelect(s,k,r));r++;}return{mask:s,blocks:k,start:String(start),count:String(count),rows,next:r<count?String(r):null};}
 function colorPage(s,q,start,limit){nat(limit,'limit',30);let r=big(start,'start'),count=BigInt(paletteProfile(s,q).count);if(r>count)throw new RangeError('start');const rows=[];while(rows.length<limit&&r<count){rows.push(colorSelect(s,q,r));r++;}return{mask:s,palette:String(q),start:String(start),count:String(count),rows,next:r<count?String(r):null};}
 function triangleWitness(s){mask(s);const id=saved.first_bad_triangle[s];return{mask:s,triangle_free:id<0,first_triangle:id<0?null:saved.triangles[id]};}
 function exportCaches(){return{falling:[...fallingCache].map(([palette,row])=>({palette,row:row.map(String)})),palette:[...paletteCache.values()]};}
 return{summary:()=>saved.summary,profile,triangleWitness,partitionSelect,partitionRank,partitionPage,paletteProfile,colorSelect,colorRank,colorPage,exportCaches,work:()=>({...w})};
}
module.exports={compile,openIndex};
