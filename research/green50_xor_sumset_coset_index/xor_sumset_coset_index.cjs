'use strict';
function nat(x,name,max){if(!Number.isSafeInteger(x)||x<0||(max!==undefined&&x>max))throw new RangeError(name+' out of range');return x;}
function rankValue(x){if(typeof x==='number'&&!Number.isSafeInteger(x))throw new TypeError('rank must be exact');if(typeof x!=='number'&&typeof x!=='bigint'&&!(typeof x==='string'&&/^\d+$/.test(x)))throw new TypeError('rank must be nonnegative');const b=BigInt(x);if(b<0n)throw new RangeError('negative rank');return b;}
function compile(input){
 const n=nat(input.dimension,'dimension',6),q=2**n,K=nat(input.max_length,'length',10),lim=input.limits||{};
 if(!Array.isArray(input.variants)||!input.variants.length||input.variants.length>(lim.max_variants||32))throw new RangeError('variant budget');
 if(!Array.isArray(input.catalog)||input.catalog.length>(lim.max_catalog||30000))throw new RangeError('catalog budget');
 const w={coset_mask_vertex_insertions:0,convolution_additions:0,coefficient_cells:0,support_cell_reads:0,profile_cache_hits:0,coset_containment_checks:0,coset_match_insertions:0,old_subspace_generation:0,old_coset_generation:0,old_covering_work:0,prime_work:0};
 const masks=input.catalog.map((c,i)=>{if(c.id!==i)throw new Error('catalog order');let mask=0n;for(const x of c.vertices){nat(x,'catalog vector',q-1);mask|=1n<<BigInt(x);w.coset_mask_vertex_insertions++;}return mask;});
 const profileMap=new Map(),profiles=[];
 function profile(row){
  let mask=0n;const values=[];for(let x=0;x<q;x++){w.support_cell_reads++;if(row[x]!==0n){mask|=1n<<BigInt(x);values.push(x);}}
  const key=mask.toString();if(profileMap.has(key)){w.profile_cache_hits++;return profileMap.get(key);}
  if(profiles.length>=(lim.max_profiles||400))throw new RangeError('profile budget');
  const ids=Array.from({length:n+1},()=>[]);for(let i=0;i<masks.length;i++){w.coset_containment_checks++;if((masks[i]&mask)===masks[i]){ids[input.catalog[i].dimension].push(i);w.coset_match_insertions++;}}
  let maximum=-1;for(let d=0;d<=n;d++)if(ids[d].length)maximum=d;
  const p={id:profiles.length,support_mask:key,values,size:values.length,coset_ids_by_dimension:ids,coset_counts:ids.map(a=>a.length),maximum_coset_dimension:maximum,maximum_coset_ids:maximum<0?[]:ids[maximum]};
  profiles.push(p);profileMap.set(key,p.id);return p.id;
 }
 const names=new Set(),variants=[];
 for(const [vi,v]of input.variants.entries()){
  if(typeof v.name!=='string'||names.has(v.name))throw new Error('variant name');names.add(v.name);
  if(!Array.isArray(v.values)||!v.values.length||v.values.some((x,i)=>!Number.isSafeInteger(x)||x<0||x>=q||(i&&x<=v.values[i-1])))throw new Error('nonempty sorted alphabet required');
  let row=Array(q).fill(0n);row[0]=1n;const rows=[],profile_ids=[],totals=[];
  for(let k=0;k<=K;k++){
   rows.push(row.map(String));w.coefficient_cells+=q;profile_ids.push(profile(row));let total=0n;for(const x of row)total+=x;totals.push(String(total));
   if(k<K){const next=Array(q).fill(0n);for(let x=0;x<q;x++)for(const a of v.values){next[x^a]+=row[x];w.convolution_additions++;}row=next;}
  }
  variants.push({id:vi,name:v.name,deleted:v.deleted,values:v.values,rows,profile_ids,totals});
 }
 return{format:'xor-sumset-coset-v1',dimension:n,ambient_size:q,max_length:K,input_provenance:input.provenance,catalog_masks:masks.map(String),variants,profiles,summary:{variants:variants.length,lengths:K+1,coefficient_cells:w.coefficient_cells,cosets:masks.length,distinct_support_profiles:profiles.length},construction_work:w};
}
function openIndex(saved,input){
 if(saved.format!=='xor-sumset-coset-v1'||input.format!=='xor-sumset-coset-input-v1'||saved.dimension!==input.dimension||saved.catalog_masks.length!==input.catalog.length)throw new Error('saved/input shape mismatch');
 const Q=saved.ambient_size,K=saved.max_length;
 const names=new Map(saved.variants.map(v=>[v.name,v])),work={coefficient_reads:0,prefix_xors:0,branch_candidates:0,rank_additions:0,selected_tuples:0,coset_record_reads:0,coset_vertex_reads:0,support_lookups:0,deletion_rows:0,new_convolutions:0,new_profile_compilations:0,new_coset_masks:0,old_catalog_generation:0};
 function variant(name){const v=names.get(name);if(!v)throw new RangeError('unknown variant');return v;}
 function length(k){return nat(k,'length',K);}
 function target(x){return nat(x,'target',Q-1);}
 function profile(v,k){return saved.profiles[v.profile_ids[k]];}
 function coefficient(v,k,x){work.coefficient_reads++;return BigInt(v.rows[k][x]);}
 function prefixState(v,k,prefix){if(!Array.isArray(prefix)||prefix.length>k)throw new RangeError('prefix length');let s=0;for(const a of prefix){if(!v.values.includes(a))throw new RangeError('prefix symbol');s^=a;work.prefix_xors++;}return s;}
 function prefixCount(name,k,x,prefix=[]){const v=variant(name);length(k);target(x);const s=prefixState(v,k,prefix);return{variant:name,length:k,target:x,prefix:prefix.slice(),prefix_xor:s,residual_target:x^s,count:String(coefficient(v,k-prefix.length,x^s))};}
 function tupleSelect(name,k,x,rank,prefix=[]){
  const v=variant(name);length(k);target(x);let s=prefixState(v,k,prefix),r=rankValue(rank),total=coefficient(v,k-prefix.length,x^s);
  if(r>=total)throw new RangeError('tuple rank out of range');const original=String(r),tuple=prefix.slice(),trace=[];
  while(tuple.length<k){const remaining=k-tuple.length-1;let chosen=false;for(const a of v.values){work.branch_candidates++;const count=coefficient(v,remaining,x^s^a),before=String(r);if(r>=count){r-=count;trace.push({position:tuple.length,symbol:a,count:String(count),rank_before:before,chosen:false});}else{trace.push({position:tuple.length,symbol:a,count:String(count),rank_before:before,chosen:true});tuple.push(a);s^=a;chosen=true;break;}}if(!chosen)throw new Error('saved coefficient inconsistency');}
  if(s!==x)throw new Error('saved terminal inconsistency');work.selected_tuples++;return{variant:name,length:k,target:x,prefix:prefix.slice(),rank:original,total:String(total),tuple,trace};
 }
 function tupleRank(name,k,x,tuple,prefix=[]){
  const v=variant(name);length(k);target(x);let s=prefixState(v,k,prefix);if(!Array.isArray(tuple)||tuple.length!==k||prefix.some((a,i)=>tuple[i]!==a))throw new RangeError('tuple shape');
  let r=0n;const trace=[];for(let i=prefix.length;i<k;i++){const a=tuple[i];if(!v.values.includes(a))throw new RangeError('tuple symbol');let add=0n;for(const b of v.values){if(b>=a)break;const c=coefficient(v,k-i-1,x^s^b);add+=c;work.rank_additions++;}r+=add;s^=a;trace.push({position:i,symbol:a,added:String(add),rank:String(r)});}
  return{variant:name,length:k,target:x,prefix:prefix.slice(),tuple:tuple.slice(),rank:s===x?String(r):null,xor:s,trace};
 }
 function sumset(name,k){const v=variant(name);length(k);const p=profile(v,k);return{variant:name,length:k,profile_id:p.id,values:p.values,size:p.size,ordered_tuple_total:v.totals[k],maximum_coset_dimension:p.maximum_coset_dimension,coset_counts:p.coset_counts};}
 function growth(name){const v=variant(name);return{variant:name,deleted:v.deleted,alphabet:v.values,alpha_numerator:v.values.length,alpha_denominator:Q,rows:Array.from({length:K+1},(_,k)=>sumset(name,k))};}
 function cosetPage(name,k,dimension,start=0,limit=20){
  const v=variant(name);length(k);nat(dimension,'coset dimension',saved.dimension);nat(start,'start');nat(limit,'limit',1000);const ids=profile(v,k).coset_ids_by_dimension[dimension];
  if(start>ids.length)throw new RangeError('start');const rows=ids.slice(start,start+limit).map(id=>{work.coset_record_reads++;return input.catalog[id];});return{variant:name,length:k,dimension,total:ids.length,start,rows,next:start+rows.length<ids.length?start+rows.length:null};
 }
 function coset(name,k,id){
  const v=variant(name);length(k);nat(id,'coset id',input.catalog.length-1);const c=input.catalog[id],p=profile(v,k);work.coset_record_reads++;let missing=null;const mask=BigInt(p.support_mask);for(const x of c.vertices){work.coset_vertex_reads++;if((mask&(1n<<BigInt(x)))===0n){missing=x;break;}}
  return{variant:name,length:k,...c,basis:input.codes[c.code_id].basis,contained:missing===null,first_missing:missing};
 }
 function tuplePage(name,k,x,start,limit,prefix=[]){
  nat(limit,'limit',50);const a=rankValue(start),c=BigInt(prefixCount(name,k,x,prefix).count);if(a>c)throw new RangeError('page start');const rows=[];let r=a;while(rows.length<limit&&r<c){rows.push(tupleSelect(name,k,x,r,prefix));r++;}return{variant:name,length:k,target:x,start:String(a),count:String(c),rows,next:r<c?String(r):null};
 }
 function sumsetRank(name,k,x){const s=sumset(name,k);target(x);work.support_lookups++;const i=s.values.indexOf(x);return{variant:name,length:k,value:x,rank:i<0?null:i};}
 function sumsetSelect(name,k,rank){const s=sumset(name,k);nat(rank,'sumset rank',s.size-1);work.support_lookups++;return{variant:name,length:k,rank,value:s.values[rank]};}
 function deletionImpact(k,x){length(k);target(x);return{length:k,target:x,rows:saved.variants.map(v=>{work.deletion_rows++;const p=profile(v,k);return{variant:v.name,deleted:v.deleted,coefficient:String(coefficient(v,k,x)),support_size:p.size,maximum_coset_dimension:p.maximum_coset_dimension,maximum_coset_count:p.maximum_coset_ids.length};})};}
 return{summary:()=>saved.summary,growth,sumset,prefixCount,tupleSelect,tupleRank,tuplePage,sumsetRank,sumsetSelect,cosetPage,coset,deletionImpact,profiles:()=>saved.profiles.map(p=>({id:p.id,size:p.size,coset_counts:p.coset_counts,maximum_coset_dimension:p.maximum_coset_dimension})),work:()=>({...work})};
}
module.exports={compile,openIndex};
