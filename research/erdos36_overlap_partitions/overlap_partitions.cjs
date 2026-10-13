'use strict';
const SCHEMA='commons.overlap_partitions/v1',SHARD='commons.overlap_partition_rows/v1';
const LIMITS=Object.freeze({half_size:10,rows:200000,shard_rows:4096,conditions:32,page:64,origin_digits:2048});
function int(x,a,b,name){if(!Number.isSafeInteger(x)||x<a||x>b)throw new TypeError(name+' outside contract');return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function dec(s,name){if(typeof s!=='string'||!/^(0|[1-9][0-9]*)$/.test(s))throw new TypeError(name+' decimal string');return BigInt(s);}
function origin(s){if(typeof s!=='string'||s.replace('-','').length>LIMITS.origin_digits||!/^(0|-?[1-9][0-9]*)$/.test(s))throw new TypeError('origin signed decimal');return BigInt(s);}
function reflect(mask,L){let r=0;for(let i=0;i<L;i++)if(mask&(1<<i))r|=1<<(L-1-i);return r;}
function positions(mask,L){const a=[];for(let i=0;i<L;i++)if(mask&(1<<i))a.push(i+1);return a;}
function buildIndex(input){
 const n=int(input.half_size,1,LIMITS.half_size,'half size'),L=2*n,full=2**L-1,offset=L-1,rows=[],hist=Array(n+1).fill(0);
 const work={partitions:0,pair_increments:0,profile_cells:0,symmetry_images:0,orbit_records:0};
 function visit(next,left,mask){if(left===0){if(rows.length>=LIMITS.rows)throw new RangeError('row cap');const A=positions(mask,L),B=positions(full^mask,L),counts=Array(2*L-1).fill(0);for(const a of A)for(const b of B){counts[a-b+offset]++;work.pair_increments++;}const maximum=Math.max(...counts);rows.push([mask,counts.map(x=>x.toString(16)).join(''),maximum,-1]);hist[maximum]++;work.partitions++;work.profile_cells+=counts.length;return;}
 for(let p=next;p<=L-left;p++)visit(p+1,left-1,mask|(1<<p));}
 visit(0,n,0);rows.sort((a,b)=>a[0]-b[0]);const byMask=new Map(rows.map((r,i)=>[r[0],i])),orbits=[],orbitByCanonical=new Map();
 for(let i=0;i<rows.length;i++){const mask=rows[i][0],rev=reflect(mask,L),images=[mask,full^mask,rev,full^rev];work.symmetry_images+=4;const canonical=Math.min(...images);let id=orbitByCanonical.get(canonical);
 if(id===undefined){id=orbits.length;orbitByCanonical.set(canonical,id);const members=[...new Set(images)].sort((a,b)=>a-b).map(x=>byMask.get(x));orbits.push({canonical_mask:canonical,members,maximum:rows[i][2]});work.orbit_records++;}rows[i][3]=id;}
 const minimum=hist.findIndex(x=>x>0),minimizers=[];for(let i=0;i<rows.length;i++)if(rows[i][2]===minimum)minimizers.push(i);
 const shards=[];for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 const index={schema:SCHEMA,half_size:n,length:L,full_mask:full,profile_shift_range:[-offset,offset],profile_encoding:'one lowercase hexadecimal digit per signed shift in increasing order',row_schema:['A_mask','signed_overlap_hex','maximum_overlap','symmetry_orbit_id'],row_order:'increasing numeric A mask; bit j represents integer j+1',row_count:rows.length,histogram:hist,minimum_overlap:minimum,minimizer_rows:minimizers,orbits,orbit_group:['identity','swap_A_B','reflection_x_to_L_plus_1_minus_x','swap_then_reflection'],shards:shards.map(s=>({start:s.start,rows:s.rows.length})),work};
 return {index,shards};
}
function openIndex(index,shards){
 const x=copy(index),ss=copy(shards);if(x.schema!==SCHEMA||!Array.isArray(ss))throw new TypeError('schema');const n=int(x.half_size,1,LIMITS.half_size,'half size'),L=2*n,full=2**L-1,offset=L-1;
 if(x.length!==L||x.full_mask!==full)throw new TypeError('host mismatch');
 const work={rows_indexed:0,queries:0,condition_scans:0,shift_lookups:0,conditions:0,condition_cache_hits:0,participation_bit_checks:0,pair_candidate_checks:0,symmetry_lookups:0,new_partition_rows:0,new_correlation_increments:0,new_orbit_construction:0};
 const rows=[],byMask=new Map();let previous=-1;
 for(let si=0;si<ss.length;si++){const s=ss[si],meta=x.shards[si];if(!meta||s.schema!==SHARD||s.start!==rows.length||meta.start!==s.start||meta.rows!==s.rows.length)throw new TypeError('shard span');for(const r of s.rows){if(!Array.isArray(r)||r.length!==4)throw new TypeError('row shape');int(r[0],0,full,'mask');if(r[0]<=previous)throw new TypeError('row order');previous=r[0];if(typeof r[1]!=='string'||r[1].length!==2*L-1||!/^[0-9a]+$/.test(r[1]))throw new TypeError('profile encoding');int(r[2],0,n,'maximum');int(r[3],0,x.orbits.length-1,'orbit');byMask.set(r[0],rows.length);rows.push(r);work.rows_indexed++;}}
 if(ss.length!==x.shards.length||rows.length!==x.row_count||rows.length>LIMITS.rows)throw new TypeError('coverage');
 function row(i){int(i,0,rows.length-1,'row');return rows[i];}
 function value(r,k){work.shift_lookups++;return Math.abs(k)>offset?0:parseInt(r[1][k+offset],16);}
 function normalize(c={}){if(!c||typeof c!=='object'||Array.isArray(c))throw new TypeError('condition');for(const key of Object.keys(c))if(!['in_A','in_B','maximum','shifts'].includes(key))throw new TypeError('unknown condition field');
 const take=(name)=>{const a=c[name]===undefined?[]:copy(c[name]);if(!Array.isArray(a))throw new TypeError(name);for(const p of a)int(p,1,L,name);if(new Set(a).size!==a.length)throw new TypeError('duplicate '+name);return a.sort((a,b)=>a-b);};
 const inA=take('in_A'),inB=take('in_B'),maximum=c.maximum===undefined?[0,n]:copy(c.maximum);if(!Array.isArray(maximum)||maximum.length!==2)throw new TypeError('maximum');int(maximum[0],0,n,'maximum');int(maximum[1],maximum[0],n,'maximum');
 const shifts=c.shifts===undefined?[]:copy(c.shifts);if(!Array.isArray(shifts))throw new TypeError('shifts');const seen=new Set();for(const q of shifts){if(!Array.isArray(q)||q.length!==3)throw new TypeError('shift condition');int(q[0],-1000000000,1000000000,'shift');int(q[1],0,n,'lower overlap');int(q[2],q[1],n,'upper overlap');if(seen.has(q[0]))throw new TypeError('duplicate shift');seen.add(q[0]);}shifts.sort((a,b)=>a[0]-b[0]);return {in_A:inA,in_B:inB,maximum,shifts};}
 const cache=new Map();
 function conditionData(c){const condition=normalize(c),key=JSON.stringify(condition);if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}if(cache.size>=LIMITS.conditions)throw new RangeError('condition cap');let reqA=0,reqB=0;for(const p of condition.in_A)reqA|=1<<(p-1);for(const p of condition.in_B)reqB|=1<<(p-1);const admitted=[];
 for(let i=0;i<rows.length;i++){work.condition_scans++;const r=rows[i];if((reqA&reqB)!==0||(r[0]&reqA)!==reqA||(r[0]&reqB)!==0||r[2]<condition.maximum[0]||r[2]>condition.maximum[1])continue;if(condition.shifts.every(([k,lo,hi])=>{const a=value(r,k);return a>=lo&&a<=hi;}))admitted.push(i);}
 const d={id:cache.size,condition,total:String(admitted.length),admitted};cache.set(key,d);work.conditions++;return d;}
 function selected(i){const r=row(i);return {row:i,A_mask:r[0],A:positions(r[0],L),B:positions(full^r[0],L),maximum:r[2],orbit_id:r[3]};}
 function select0(rank,c){const d=conditionData(c),r=dec(rank,'rank');if(r>=BigInt(d.admitted.length))throw new RangeError('rank');return {rank:r.toString(),condition_id:d.id,...selected(d.admitted[Number(r)])};}
 function mappingMask(A){if(!Array.isArray(A)||A.length!==n)throw new TypeError('A size');let mask=0;for(const p of A){int(p,1,L,'A entry');if(mask&(1<<(p-1)))throw new TypeError('duplicate A entry');mask|=1<<(p-1);}return mask;}
 function rank0(A,c){const mask=mappingMask(A),id=byMask.get(mask);if(id===undefined)throw new TypeError('missing partition');const d=conditionData(c);let lo=0,hi=d.admitted.length;while(lo<hi){const mid=(lo+hi)>>1;if(d.admitted[mid]<id)lo=mid+1;else hi=mid;}if(d.admitted[lo]!==id)throw new TypeError('partition excluded');return {rank:String(lo),condition_id:d.id,row:id,A_mask:mask};}
 return {
 summary(){work.queries++;return copy({schema:x.schema,n,length:L,partitions:x.row_count,minimum:x.minimum_overlap,minimizers:x.minimizer_rows.length,orbits:x.orbits.length,histogram:x.histogram});},
 row(i){work.queries++;return selected(i);},
 profile(i){work.queries++;const r=row(i);return {row:i,shifts:Array.from({length:2*L-1},(_,j)=>j-offset),counts:Array.from(r[1],ch=>parseInt(ch,16)),maximum:r[2]};},
 family(c){work.queries++;const d=conditionData(c);return copy({id:d.id,condition:d.condition,total:d.total});},
 select(rank,c){work.queries++;return select0(rank,c);},
 rank(A,c){work.queries++;return rank0(A,c);},
 page(start,count,c){work.queries++;const d=conditionData(c),r=dec(start,'start');int(count,0,LIMITS.page,'page size');if(r>BigInt(d.admitted.length))throw new RangeError('start');const values=[];for(let j=0;j<count&&r+BigInt(j)<BigInt(d.admitted.length);j++)values.push(select0((r+BigInt(j)).toString(),c));return {start:r.toString(),total:d.total,values};},
 orbit(id){work.queries++;int(id,0,x.orbits.length-1,'orbit');work.symmetry_lookups++;const o=x.orbits[id];return {id,canonical_mask:o.canonical_mask,maximum:o.maximum,members:o.members.map(selected)};},
 symmetry(i,operation){work.queries++;int(operation,0,3,'operation');const r=row(i);let mask=r[0];if(operation>=2)mask=reflect(mask,L);if(operation%2===1)mask=full^mask;work.symmetry_lookups++;const target=byMask.get(mask);return {operation:x.orbit_group[operation],from_row:i,to_row:target,profile_reversal:operation===1||operation===2,...selected(target)};},
 pairs(i,k,translation='0'){work.queries++;const r=row(i);int(k,-1000000000,1000000000,'shift');const z=origin(translation),pairs=[];for(const a of positions(r[0],L)){work.pair_candidate_checks++;const b=a-k;if(b>=1&&b<=L&&(r[0]&(1<<(b-1)))===0)pairs.push({a:(z+BigInt(a)).toString(),b:(z+BigInt(b)).toString(),untranslated:[a,b]});}return {row:i,shift:k,translation:z.toString(),saved_overlap:value(r,k),pairs};},
 participation(c){work.queries++;const d=conditionData(c),counts=Array(L).fill(0);for(const i of d.admitted)for(let p=0;p<L;p++){work.participation_bit_checks++;if(rows[i][0]&(1<<p))counts[p]++;}return {condition_id:d.id,total:d.total,positions:counts.map((a,j)=>({position:j+1,in_A:String(a),in_B:String(d.admitted.length-a)}))};},
 conditions(){work.queries++;return copy([...cache.values()]);},
 work(){return copy(work);}
 };
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
