'use strict';
const clone=x=>JSON.parse(JSON.stringify(x));
function compileFamily(input){
 if(input.half_length!==8||input.coordinate_count!==16)throw new TypeError('this finite implementation uses half length 8');
 const sizes=Array(65536).fill(0);for(let s=1;s<65536;s++)sizes[s]=sizes[s>>1]+(s&1);
 const candidates=[],codes=[],work={maskSizeCells:65536,circulantCandidates:256,generatorRows:0,gramCells:0,codewords:0,codewordXors:0,columnBits:0,externalCodeExamples:0};
 for(let seed=0;seed<256;seed++){
  const right=Array.from({length:8},(_,i)=>((seed<<i)|(seed>>(8-i)))&255);
  const rows=right.map((a,i)=>(a<<8)|(1<<i));work.generatorRows+=8;
  const failures=[];for(let i=0;i<8;i++)for(let j=i;j<8;j++){work.gramCells++;if(sizes[rows[i]&rows[j]]&1)failures.push([i,j]);}
  const selfdual=failures.length===0,doubly_even_generators=rows.every(w=>sizes[w]%4===0),type_ii=selfdual&&doubly_even_generators;
  candidates.push({seed,selfdual,doubly_even_generators,type_ii,gram_failures:failures});
  if(!type_ii)continue;
  const words=Array(256).fill(0),weights=Array(17).fill(0);weights[0]=1;
  for(let m=1;m<256;m++){const b=m&-m,i=31-Math.clz32(b);words[m]=words[m^b]^rows[i];work.codewordXors++;weights[sizes[words[m]]]++;}
  work.codewords+=256;
  const columns=Array.from({length:16},(_,j)=>{let c=0;for(let i=0;i<8;i++){work.columnBits++;if(rows[i]&(1<<j))c|=1<<i;}return c;});
  codes.push({seed,generator_rows:rows,columns,codewords_by_message:words,weight_counts:weights,minimum_nonzero_weight:weights.findIndex((x,i)=>i>0&&x>0)});
 }
 return {format:'binary-circulant-type-ii-family/v1',input:clone(input),coordinate_mask_sizes:sizes,candidates,codes,work};
}
function compileProfile(family,seed){
 const code=family.codes.find(c=>c.seed===seed);if(!code)throw new RangeError('seed outside retained Type II family');
 const spans=[{basis:Array(8).fill(0),rank:0}],ids=new Map([[Array(8).fill(0).join(','),0]]),transitions=new Map(),states=Array(65536).fill(0);
 const work={coordinateMasks:65536,transitionRequests:0,transitionHits:0,newTransitions:0,newSpans:0,basisXors:0,pivotInsertions:0,histogramCells:65536,codewordReconstructions:0,gramReconstructions:0};
 function extend(id,j){
  const key=id+':'+j;work.transitionRequests++;if(transitions.has(key)){work.transitionHits++;return transitions.get(key);}
  const basis=spans[id].basis.slice();let v=code.columns[j],rank=spans[id].rank;
  for(let p=7;p>=0;p--)if((v&(1<<p))&&basis[p]){v^=basis[p];work.basisXors++;}
  if(v){const p=31-Math.clz32(v);basis[p]=v;rank++;work.pivotInsertions++;for(let q=0;q<8;q++)if(q!==p&&(basis[q]&(1<<p))){basis[q]^=v;work.basisXors++;}}
  const bkey=basis.join(',');let next=ids.get(bkey);if(next===undefined){next=spans.length;ids.set(bkey,next);spans.push({basis,rank});work.newSpans++;}
  transitions.set(key,next);work.newTransitions++;return next;
 }
 for(let mask=1;mask<65536;mask++){const b=mask&-mask,j=31-Math.clz32(b);states[mask]=extend(states[mask^b],j);}
 const histogram=Array.from({length:17},()=>Array(9).fill(0));
 for(let erased=0;erased<65536;erased++){const lost=8-spans[states[65535^erased]].rank;histogram[family.coordinate_mask_sizes[erased]][lost]++;}
 return {format:'binary-circulant-coordinate-span-profile/v1',seed,spans,span_id_by_coordinate_mask:states,erasure_size_by_kernel_dimension:histogram,work};
}
function createReader(family,profiles){
 const codes=new Map(family.codes.map(c=>[c.seed,c])),bySeed=new Map(profiles.map(p=>[p.seed,p]));
 if(profiles.length!==codes.size||profiles.some(p=>!codes.has(p.seed))||bySeed.size!==profiles.length)throw new TypeError('complete distinct profile list required');
 const seeds=family.codes.map(c=>c.seed),cache=new Map(),work={conditionsBuilt:0,conditionHits:0,profileRowsScanned:0,spanRankReads:0,selectBlockRows:0,rankBlockRows:0,marginalRows:0,marginalBitChecks:0,compatibleWordReads:0,newProfiles:0,newCodewords:0,newGramCells:0};
 const maskOf=(a=[])=>{if(!Array.isArray(a))throw new TypeError('coordinate list');let m=0;for(const x of a){if(!Number.isInteger(x)||x<0||x>15)throw new RangeError('coordinate outside 0..15');if(m&(1<<x))throw new TypeError('duplicate coordinate');m|=1<<x;}return m;};
 const listOf=m=>{const a=[];for(let j=0;j<16;j++)if(m&(1<<j))a.push(j);return a;};
 const rankAt=(p,mask)=>{work.spanRankReads++;return p.spans[p.span_id_by_coordinate_mask[mask]].rank;};
 function normalize(q){
  const selected=q.seeds===undefined?seeds.slice():q.seeds.slice();if(!Array.isArray(q.seeds===undefined?[]:q.seeds)||selected.some(x=>!codes.has(x))||new Set(selected).size!==selected.length)throw new TypeError('distinct retained seeds required');selected.sort((a,b)=>a-b);
  const require=maskOf(q.require_erased),forbid=maskOf(q.forbid_erased);
  const bound=(name,fallback)=>{const x=q[name]===undefined?fallback:q[name];if(!Number.isSafeInteger(x))throw new TypeError('integer bounds');return x;};
  return {seeds:selected,require,forbid,min_size:Math.max(0,bound('min_size',0)),max_size:Math.min(16,bound('max_size',16)),min_loss:Math.max(0,bound('min_loss',0)),max_loss:Math.min(8,bound('max_loss',8))};
 }
 function admits(c,p,m){
  const n=family.coordinate_mask_sizes[m];if((m&c.require)!==c.require||(m&c.forbid)||n<c.min_size||n>c.max_size)return false;
  const loss=8-rankAt(p,65535^m);return loss>=c.min_loss&&loss<=c.max_loss;
 }
 function condition(q){
  const c=normalize(q),key=JSON.stringify(c);if(cache.has(key)){work.conditionHits++;return cache.get(key);}
  const perSeed=[],hist=Array.from({length:17},()=>Array(9).fill(0));let total=0;
  const empty=(c.require&c.forbid)||c.min_size>c.max_size||c.min_loss>c.max_loss;
  for(const seed of c.seeds){
   const p=bySeed.get(seed),blocks=Array(256).fill(0);let count=0;
   if(!empty)for(let m=0;m<65536;m++){work.profileRowsScanned++;if(admits(c,p,m)){blocks[m>>8]++;count++;hist[family.coordinate_mask_sizes[m]][8-rankAt(p,65535^m)]++;}}
   perSeed.push({seed,count,block_counts:blocks});total+=count;
  }
  const o={...c,key,count:total,per_seed:perSeed,histogram:hist};cache.set(key,o);work.conditionsBuilt++;return o;
 }
 function pattern(seed,erased){
  const p=bySeed.get(seed);if(!p||!Number.isInteger(erased)||erased<0||erased>65535)throw new RangeError('seed/erasure mask');
  const erasedRank=rankAt(p,erased),knownRank=rankAt(p,65535^erased);
  return {seed,erased_mask:erased,erased_coordinates:listOf(erased),erased_size:family.coordinate_mask_sizes[erased],punctured_dimension:knownRank,shortened_zero_on_erased_dimension:8-erasedRank,ambiguity_dimension:8-knownRank,compatible_words_when_consistent:String(2**(8-knownRank)),unique_erasure_recovery:knownRank===8};
 }
 function select(q,rank){
  if(typeof rank!=='string'||!/^(0|[1-9][0-9]*)$/.test(rank)||rank.length>64)throw new TypeError('decimal rank');
  const c=condition(q);let r=BigInt(rank);if(r>=BigInt(c.count))return {status:'OUT_OF_RANGE',count:String(c.count),rank};
  for(const row of c.per_seed){if(r>=BigInt(row.count)){r-=BigInt(row.count);continue;}
   for(let block=0;block<256;block++){if(r>=BigInt(row.block_counts[block])){r-=BigInt(row.block_counts[block]);continue;}
    for(let m=block*256;m<(block+1)*256;m++){work.selectBlockRows++;if(admits(c,bySeed.get(row.seed),m)){if(r===0n)return {status:'OK',rank,count:String(c.count),...pattern(row.seed,m)};r--;}}
   }
  }throw new Error('retained block counts inconsistent');
 }
 function rank(q,seed,erased){
  const c=condition(q),row=c.per_seed.find(x=>x.seed===seed);if(!row||!Number.isInteger(erased)||erased<0||erased>65535||!admits(c,bySeed.get(seed),erased))return {status:'NOT_IN_CONDITION'};
  let r=0;for(const a of c.per_seed){if(a.seed===seed)break;r+=a.count;}
  const block=erased>>8;for(let j=0;j<block;j++)r+=row.block_counts[j];
  for(let m=block*256;m<erased;m++){work.rankBlockRows++;if(admits(c,bySeed.get(seed),m))r++;}
  return {status:'OK',rank:String(r),count:String(c.count),seed,erased_mask:erased};
 }
 function page(q,offset,limit){if(typeof offset!=='string'||!/^(0|[1-9][0-9]*)$/.test(offset)||offset.length>64||!Number.isInteger(limit)||limit<1||limit>128)throw new TypeError('page arguments');const c=condition(q),o=BigInt(offset);if(o>BigInt(c.count))return {status:'OUT_OF_RANGE',count:String(c.count)};const rows=[];for(let r=o;r<BigInt(c.count)&&rows.length<limit;r++)rows.push(select(q,String(r)));return {status:'OK',count:String(c.count),offset,rows,next_offset:o+BigInt(rows.length)<BigInt(c.count)?String(o+BigInt(rows.length)):null};}
 function marginals(q){const c=condition(q),a=Array(16).fill(0);for(const seed of c.seeds){const p=bySeed.get(seed);for(let m=0;m<65536;m++){work.marginalRows++;if(admits(c,p,m))for(let j=0;j<16;j++){work.marginalBitChecks++;if(m&(1<<j))a[j]++;}}}return {count:String(c.count),coordinates:a.map((count,coordinate)=>({coordinate,count:String(count)}))};}
 function compatible(seed,erased,received){
  const code=codes.get(seed);if(!code||!Number.isInteger(erased)||erased<0||erased>65535||!Number.isInteger(received)||received<0||received>65535)throw new RangeError('seed and 16-bit masks');
  const known=65535^erased,rows=[];for(let message=0;message<256;message++){work.compatibleWordReads++;const word=code.codewords_by_message[message];if((word&known)===(received&known))rows.push({message,word,weight:family.coordinate_mask_sizes[word]});}
  return {seed,erased_mask:erased,received_mask:received,known_mask:known,status:rows.length===0?'INCONSISTENT':rows.length===1?'UNIQUE':'AMBIGUOUS',count:String(rows.length),rows,pattern:pattern(seed,erased)};
 }
 return Object.freeze({summary:()=>({scope:'all 256 circulant [I8|A] candidates, retained Type II subfamily only',order:'seed ascending, then numeric erasure mask ascending',codes:family.codes.map(c=>({seed:c.seed,weight_counts:c.weight_counts,minimum_nonzero_weight:c.minimum_nonzero_weight,profile_spans:bySeed.get(c.seed).spans.length})),candidate_count:256}),
  condition:q=>clone(condition(q)),select,rank,page,marginals,compatible,pattern,
  snapshot:()=>({format:'circulant-erasure-reader/v1',conditions:Array.from(cache.values()).map(clone),work:clone(work)}),work:()=>clone(work)});
}
module.exports={compileFamily,compileProfile,createReader};
