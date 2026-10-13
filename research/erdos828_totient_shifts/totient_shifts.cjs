'use strict';
const SCHEMA='commons.totient_shifts/v1',SHARD='commons.totient_shift_rows/v1';
const LIMITS=Object.freeze({primes:10,prime_value:1000000,exponent:8,rows:100000,shard_rows:2048,point_caches:32,window_caches:8,page:32,digits:2048});
function int(x,a,b,name){if(!Number.isSafeInteger(x)||x<a||x>b)throw new TypeError(name+' outside contract');return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function natural(s,name){if(typeof s!=='string'||!/^(0|[1-9][0-9]*)$/.test(s)||s.length>LIMITS.digits)throw new TypeError(name+' nonnegative decimal');return BigInt(s);}
function signed(s,name){if(typeof s!=='string'||!/^(0|-?[1-9][0-9]*)$/.test(s)||s.replace('-','').length>LIMITS.digits)throw new TypeError(name+' signed decimal');return BigInt(s);}
function mod(a,m){const r=a%m;return r<0n?r+m:r;}
function floor(a,b){let q=a/b;if(a<0n&&a%b!==0n)q--;return q;}
function ceil(a,b){return -floor(-a,b);}
function gcd(a,b){while(b){const r=a%b;a=b;b=r;}return a;}
function buildIndex(input){
 if(!Array.isArray(input.primes)||!Array.isArray(input.caps)||typeof input.prime_premise!=='string'||!input.prime_premise.length)throw new TypeError('identified prime premise and arrays required');
 const b=int(input.primes.length,1,LIMITS.primes,'prime count');if(input.caps.length!==b)throw new TypeError('caps length');const primes=input.primes.map(p=>int(p,2,LIMITS.prime_value,'prime')),caps=input.caps.map(c=>int(c,0,LIMITS.exponent,'exponent'));
 for(let i=1;i<b;i++)if(primes[i]<=primes[i-1])throw new TypeError('prime bases must increase');const size=caps.reduce((z,c)=>z*(c+1),1);if(size>LIMITS.rows)throw new RangeError('row cap');
 const tables=[],work={prime_tests:0,prime_power_cells:0,search_nodes:0,product_multiplications:0,rows:0,residue_reductions:0,kernel_classes:0,period_quotients:0};
 let maximalN=1n,period=1n;
 for(let i=0;i<b;i++){const p=BigInt(primes[i]),t=[];let power=1n;for(let e=0;e<=caps[i];e++){if(e)power*=p;const phi=e===0?1n:(power/p)*(p-1n);t.push([power.toString(),phi.toString()]);work.prime_power_cells++;}tables.push(t);maximalN*=BigInt(t.at(-1)[0]);period*=BigInt(t.at(-1)[1]);}
 const rows=[];
 function visit(i,n,phi,code,stride){work.search_nodes++;if(i===b){const r=mod(-n,phi);rows.push([n.toString(),phi.toString(),r.toString(),code,-1]);work.rows++;work.residue_reductions++;return;}
 for(let e=0;e<=caps[i];e++){work.product_multiplications+=2;visit(i+1,n*BigInt(tables[i][e][0]),phi*BigInt(tables[i][e][1]),code+e*stride,stride*(caps[i]+1));}}
 visit(0,1n,1n,0,1);rows.sort((a,b)=>BigInt(a[0])<BigInt(b[0])?-1:BigInt(a[0])>BigInt(b[0])?1:0);
 const classes=[],map=new Map();let incidences=0n;
 for(let i=0;i<rows.length;i++){const r=rows[i],key=r[1]+':'+r[2];let k=map.get(key);if(k===undefined){k=classes.length;map.set(key,k);const m=BigInt(r[1]);if(period%m)throw new Error('period is not a multiple of saved totient');const q=period/m;classes.push({modulus:r[1],residue:r[2],rows:[],occurrences_per_period:q.toString()});work.kernel_classes++;work.period_quotients++;}r[4]=k;classes[k].rows.push(i);incidences+=BigInt(classes[k].occurrences_per_period);}
 const g=gcd(incidences,period),shards=[];for(let start=0;start<rows.length;start+=LIMITS.shard_rows)shards.push({schema:SHARD,start,rows:rows.slice(start,start+LIMITS.shard_rows)});
 const index={schema:SCHEMA,primes,caps,prime_premise:input.prime_premise,prime_power_tables:tables,maximum_n:maximalN.toString(),period:period.toString(),period_claim:'valid common period in signed parameter a, not asserted least',row_count:rows.length,row_schema:['n','phi_n','least_nonnegative_shift_residue','exponent_code','kernel_class_id'],row_order:'increasing positive n',classes,period_pair_count:incidences.toString(),mean_matches:{numerator:(incidences/g).toString(),denominator:(period/g).toString()},shards:shards.map(s=>({start:s.start,rows:s.rows.length})),work};
 return {index,shards};
}
function openIndex(index,shards){
 const x=copy(index),ss=copy(shards);if(x.schema!==SCHEMA||!Array.isArray(ss))throw new TypeError('schema');const b=int(x.primes.length,1,LIMITS.primes,'primes');if(x.caps.length!==b)throw new TypeError('caps');const period=natural(x.period,'period'),maximum=natural(x.maximum_n,'maximum');if(period<1n||maximum<1n)throw new TypeError('positive period and maximum');
 const work={rows_indexed:0,queries:0,point_kernels_scanned:0,point_row_checks:0,window_row_scans:0,window_eligible_rows:0,window_class_counts:0,window_divisions:0,window_prefix_additions:0,point_cache_hits:0,window_cache_hits:0,selection_binary_steps:0,quotient_witnesses:0,exponent_decodes:0,new_prime_tests:0,new_product_rows:0,new_totients:0,new_kernel_classes:0};
 const rows=[],byN=new Map();let prev=0n;
 for(let i=0;i<ss.length;i++){const s=ss[i],meta=x.shards[i];if(!meta||s.schema!==SHARD||s.start!==rows.length||meta.start!==s.start||meta.rows!==s.rows.length)throw new TypeError('shard span');for(const r of s.rows){if(!Array.isArray(r)||r.length!==5)throw new TypeError('row shape');const n=natural(r[0],'n'),phi=natural(r[1],'phi'),res=natural(r[2],'residue');if(n<=prev||phi<1n||res>=phi)throw new TypeError('row order or residue');prev=n;int(r[3],0,LIMITS.rows-1,'code');int(r[4],0,x.classes.length-1,'class');rows.push(r);byN.set(r[0],rows.length-1);work.rows_indexed++;}}
 if(ss.length!==x.shards.length||rows.length!==x.row_count||rows.length>LIMITS.rows||prev!==maximum)throw new TypeError('coverage');
 for(let i=0;i<x.classes.length;i++){const c=x.classes[i],m=natural(c.modulus,'modulus'),r=natural(c.residue,'residue');if(m<1n||r>=m||!Array.isArray(c.rows))throw new TypeError('class');for(const j of c.rows){int(j,0,rows.length-1,'class row');if(rows[j][4]!==i||rows[j][1]!==c.modulus||rows[j][2]!==c.residue)throw new TypeError('class row binding');}}
 function bounds(range={}){if(!range||typeof range!=='object'||Array.isArray(range))throw new TypeError('range');for(const k of Object.keys(range))if(!['min_n','max_n'].includes(k))throw new TypeError('unknown range field');const lo=range.min_n===undefined?1n:natural(range.min_n,'min_n'),hi=range.max_n===undefined?maximum:natural(range.max_n,'max_n');if(lo<1n||hi<lo||hi>maximum)throw new TypeError('n range');return {min_n:lo.toString(),max_n:hi.toString()};}
 function inRange(r,range){const n=BigInt(r[0]);return n>=BigInt(range.min_n)&&n<=BigInt(range.max_n);}
 function selected(i,a){const r=rows[i],aa=signed(a,'a'),q=(BigInt(r[0])+aa)/BigInt(r[1]);work.quotient_witnesses++;return {row:i,n:r[0],phi_n:r[1],parameter:aa.toString(),quotient:q.toString(),exponent_code:r[3],class_id:r[4]};}
 const points=new Map(),windows=new Map();
 function pointData(a,range){const aa=signed(a,'a'),phase=mod(aa,period),bd=bounds(range),key=phase+':'+bd.min_n+':'+bd.max_n;if(points.has(key)){work.point_cache_hits++;return points.get(key);}if(points.size>=LIMITS.point_caches)throw new RangeError('point cache cap');const admitted=[],matched=[];
 for(let i=0;i<x.classes.length;i++){work.point_kernels_scanned++;const c=x.classes[i];if(mod(phase,BigInt(c.modulus))!==BigInt(c.residue))continue;let used=false;for(const j of c.rows){work.point_row_checks++;if(inRange(rows[j],bd)){admitted.push(j);used=true;}}if(used)matched.push(i);}
 admitted.sort((a,b)=>a-b);const d={id:points.size,phase:phase.toString(),range:bd,total:String(admitted.length),matched_classes:matched,admitted};points.set(key,d);return d;}
 function pointSelect0(a,rank,range){const d=pointData(a,range),r=natural(rank,'rank');if(r>=BigInt(d.admitted.length))throw new RangeError('rank');return {rank:r.toString(),point_id:d.id,...selected(d.admitted[Number(r)],a)};}
 function pointRank0(a,n,range){const nn=natural(n,'n').toString(),rowid=byN.get(nn),d=pointData(a,range);if(rowid===undefined)throw new TypeError('n outside finite family');let lo=0,hi=d.admitted.length;while(lo<hi){work.selection_binary_steps++;const mid=(lo+hi)>>1;if(d.admitted[mid]<rowid)lo=mid+1;else hi=mid;}if(d.admitted[lo]!==rowid)throw new TypeError('n not admitted');return {rank:String(lo),point_id:d.id,row:rowid,n:nn};}
 function windowData(a,b,range){const low=signed(a,'window low'),high=signed(b,'window high');if(high<low)throw new TypeError('window order');const bd=bounds(range),key=[low,high,bd.min_n,bd.max_n].join(':');if(windows.has(key)){work.window_cache_hits++;return windows.get(key);}if(windows.size>=LIMITS.window_caches)throw new RangeError('window cache cap');
 const classes=[],local=new Map(),blocks=[];let total=0n;
 for(let i=0;i<rows.length;i++){work.window_row_scans++;if(!inRange(rows[i],bd))continue;work.window_eligible_rows++;const id=rows[i][4];let ci=local.get(id);if(ci===undefined){const c=x.classes[id],m=BigInt(c.modulus),r=BigInt(c.residue),first=r+ceil(low-r,m)*m,count=first>high?0n:floor(high-first,m)+1n;work.window_class_counts++;work.window_divisions+=first>high?1:2;ci=classes.length;local.set(id,ci);classes.push({class_id:id,first:first.toString(),count:count.toString()});}
 const c=classes[ci],count=BigInt(c.count);if(count){total+=count;blocks.push([i,ci,total.toString()]);work.window_prefix_additions++;}}
 const d={id:windows.size,low:low.toString(),high:high.toString(),range:bd,total:total.toString(),classes,blocks};windows.set(key,d);return d;}
 function windowSelect0(a,b,rank,range){const d=windowData(a,b,range),r=natural(rank,'rank');if(r>=BigInt(d.total))throw new RangeError('rank');let lo=0,hi=d.blocks.length;while(lo<hi){work.selection_binary_steps++;const mid=(lo+hi)>>1;if(BigInt(d.blocks[mid][2])>r)hi=mid;else lo=mid+1;}const block=d.blocks[lo],c=d.classes[block[1]],offset=r-(lo?BigInt(d.blocks[lo-1][2]):0n),aValue=BigInt(c.first)+offset*BigInt(x.classes[c.class_id].modulus);return {rank:r.toString(),window_id:d.id,within_n_rank:offset.toString(),...selected(block[0],aValue.toString())};}
 function windowRank0(a,b,n,parameter,range){const nn=natural(n,'n').toString(),aa=signed(parameter,'parameter'),rowid=byN.get(nn),d=windowData(a,b,range);if(rowid===undefined)throw new TypeError('n outside finite family');let lo=0,hi=d.blocks.length;while(lo<hi){work.selection_binary_steps++;const mid=(lo+hi)>>1;if(d.blocks[mid][0]<rowid)lo=mid+1;else hi=mid;}const block=d.blocks[lo];if(!block||block[0]!==rowid)throw new TypeError('n excluded');const c=d.classes[block[1]],m=BigInt(x.classes[c.class_id].modulus),delta=aa-BigInt(c.first);if(delta<0n||delta%m!==0n||delta/m>=BigInt(c.count))throw new TypeError('parameter excluded');const within=delta/m,rank=(lo?BigInt(d.blocks[lo-1][2]):0n)+within;return {rank:rank.toString(),window_id:d.id,row:rowid,n:nn,within_n_rank:within.toString()};}
 return {
 summary(){work.queries++;return copy({schema:x.schema,primes:x.primes,caps:x.caps,row_count:x.row_count,classes:x.classes.length,maximum_n:x.maximum_n,period:x.period,period_pair_count:x.period_pair_count,mean_matches:x.mean_matches});},
 row(i){work.queries++;int(i,0,rows.length-1,'row');const r=rows[i];return {row:i,n:r[0],phi_n:r[1],residue:r[2],code:r[3],class_id:r[4]};},
 factorization(i){work.queries++;int(i,0,rows.length-1,'row');const r=rows[i];let code=r[3];const factors=[];for(let p=0;p<b;p++){const e=code%(x.caps[p]+1);code=Math.floor(code/(x.caps[p]+1));if(e)factors.push({prime:x.primes[p],exponent:e,prime_power:x.prime_power_tables[p][e][0],totient_factor:x.prime_power_tables[p][e][1]});}work.exponent_decodes++;return {row:i,n:r[0],phi_n:r[1],factors,prime_premise:x.prime_premise};},
 kernel(i){work.queries++;int(i,0,x.classes.length-1,'class');return copy({id:i,...x.classes[i]});},
 point(a,range){work.queries++;const d=pointData(a,range);return copy({id:d.id,phase:d.phase,range:d.range,total:d.total,matched_classes:d.matched_classes.length});},
 pointSelect(a,rank,range){work.queries++;return pointSelect0(a,rank,range);},
 pointRank(a,n,range){work.queries++;return pointRank0(a,n,range);},
 pointPage(a,start,count,range){work.queries++;const d=pointData(a,range),r=natural(start,'start');int(count,0,LIMITS.page,'page');if(r>BigInt(d.admitted.length))throw new RangeError('start');const values=[];for(let j=0;j<count&&r+BigInt(j)<BigInt(d.admitted.length);j++)values.push(pointSelect0(a,(r+BigInt(j)).toString(),range));return {total:d.total,start:r.toString(),values};},
 window(a,b,range){work.queries++;const d=windowData(a,b,range);return copy({id:d.id,low:d.low,high:d.high,range:d.range,total:d.total,admitted_n:d.blocks.length,classes:d.classes.length});},
 windowSelect(a,b,rank,range){work.queries++;return windowSelect0(a,b,rank,range);},
 windowRank(a,b,n,parameter,range){work.queries++;return windowRank0(a,b,n,parameter,range);},
 windowPage(a,b,start,count,range){work.queries++;const d=windowData(a,b,range),r=natural(start,'start');int(count,0,LIMITS.page,'page');if(r>BigInt(d.total))throw new RangeError('start');const values=[];for(let j=0;j<count&&r+BigInt(j)<BigInt(d.total);j++)values.push(windowSelect0(a,b,(r+BigInt(j)).toString(),range));return {total:d.total,start:r.toString(),values};},
 caches(){work.queries++;return copy({points:[...points.values()],windows:[...windows.values()]});},
 work(){return copy(work);}
 };
}
module.exports={SCHEMA,SHARD,LIMITS,buildIndex,openIndex};
