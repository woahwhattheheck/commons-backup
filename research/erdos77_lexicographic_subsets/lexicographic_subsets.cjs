'use strict';
const SCHEMA='commons.cycle_lexicographic_subsets/v1',clone=x=>JSON.parse(JSON.stringify(x));
function nat(x,n,max){if(!Number.isSafeInteger(x)||x<0||x>max)throw new TypeError(n+' out of range');return x;}
function big(x){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>20000)throw new TypeError('canonical integer text');return BigInt(x);}
function compile(input){
 if(!input||input.schema!=='commons.cycle_lexicographic_subset_input/v1'||input.base_vertices!==5)throw new TypeError('input');
 const depth=nat(input.depth,'depth',10),patterns=input.base_independent_family;if(!Array.isArray(patterns)||patterns.length!==11)throw new TypeError('base family');
 let last=-1;const multiplicities=[0,0,0];for(const p of patterns){nat(p.mask,'pattern mask',31);if(p.mask<=last||!Array.isArray(p.vertices)||p.vertices.length!==p.size||p.size>2)throw new TypeError('pattern shape');last=p.mask;multiplicities[p.size]++;}
 if(multiplicities.join(',')!=='1,5,5')throw new TypeError('C5 family multiplicities');
 const levels=[{depth:0,vertices:1,maximum:1,coefficients:['1','1'],total:'2',nonempty_powers:[['1'],['0','1'],['0','0','1']]}];
 const work={base_records_read:patterns.length,levels_composed:0,convolution_products:0,convolution_additions:0,weighted_coefficient_additions:0,coefficient_cells:2,power_cells:6,old_graph_enumeration:0,old_independent_set_tests:0,old_induced_degrees:0,graph_vertices_enumerated:0,graph_edges_enumerated:0};
 let prev=[1n,1n];
 for(let d=1;d<=depth;d++){
  const m=prev.length-1;if(2*m>1024)throw new RangeError('degree cap');const q=prev.slice();q[0]=0n;const square=Array(2*m+1).fill(0n);
  for(let i=1;i<=m;i++)for(let j=1;j<=m;j++){square[i+j]+=q[i]*q[j];work.convolution_products++;work.convolution_additions++;}
  const p=Array(2*m+1).fill(0n);p[0]=1n;
  for(let k=1;k<p.length;k++){p[k]=5n*(q[k]||0n)+5n*square[k];work.weighted_coefficient_additions++;}
  const powers=[[1n],q,square];work.levels_composed++;work.coefficient_cells+=p.length;work.power_cells+=powers.reduce((s,a)=>s+a.length,0);
  if(work.coefficient_cells+work.power_cells>100000)throw new RangeError('cell cap');
  levels.push({depth:d,vertices:5**d,maximum:p.length-1,coefficients:p.map(String),total:p.reduce((a,b)=>a+b,0n).toString(),nonempty_powers:powers.map(a=>a.map(String))});prev=p;
 }
 return{schema:SCHEMA,input:clone(input),levels,summary:{depth,vertices:levels[depth].vertices,maximum_independent:levels[depth].maximum,maximum_clique:levels[depth].maximum,maximum_family_count:levels[depth].coefficients.at(-1),total_each_mode:levels[depth].total,counts_shared_by_digit_isomorphism:true},work};
}
function openIndex(saved){
 if(!saved||saved.schema!==SCHEMA)throw new TypeError('schema');const r=clone(saved),D=nat(r.input.depth,'depth',10),patterns=r.input.base_independent_family;
 if(r.levels.length!==D+1)throw new TypeError('levels');const coeff=r.levels.map((x,d)=>{if(x.depth!==d||x.vertices!==5**d||x.maximum!==2**d||x.coefficients.length!==2**d+1)throw new TypeError('level shape');return x.coefficients.map(big);});
 const powers=r.levels.map(x=>x.nonempty_powers.map(a=>a.map(big))),totals=r.levels.map(x=>big(x.total)),map=r.input.clique_digit_map,inv=Array(5);
 if(!Array.isArray(map)||map.length!==5||new Set(map).size!==5)throw new TypeError('digit permutation');for(let i=0;i<5;i++){nat(map[i],'digit map',4);inv[map[i]]=i;}
 const work={saved_levels:r.levels.length,saved_coefficient_cells:coeff.reduce((s,x)=>s+x.length,0),coefficient_reads:0,pattern_visits:0,allocation_products:0,allocation_cache_hits:0,rank_additions:0,tree_nodes:0,vertex_digit_operations:0,selected_sets:0,returned_vertices:0,marginal_products:0,marginal_divisions:0,new_convolutions:0,new_level_polynomials:0,graph_edge_enumeration:0};
 const allocations=new Map();
 function params(o={}){const d=o.depth===undefined?D:nat(o.depth,'depth',D),mode=o.mode===undefined?'independent':o.mode,k=o.size===undefined?null:o.size;if(mode!=='independent'&&mode!=='clique')throw new TypeError('mode');if(k!==null)nat(k,'size',2**d);return{d,mode,k};}
 function c(d,k){work.coefficient_reads++;return coeff[d][k]||0n;}
 function mass(d,j,k){work.coefficient_reads++;return powers[d][j][k]||0n;}
 function allocation(d,k,a){const key=d+':'+k+':'+a;if(allocations.has(key)){work.allocation_cache_hits++;return allocations.get(key);}const z=c(d-1,a)*c(d-1,k-a);allocations.set(key,z);work.allocation_products++;return z;}
 function transform(v,d,permutation){let out=0,place=1;for(let i=0;i<d;i++){out+=permutation[v%5]*place;v=Math.floor(v/5);place*=5;work.vertex_digit_operations++;}return out;}
 function profile(depth=D){nat(depth,'depth',D);return clone(r.levels[depth]);}
 function select(options,rankText){
  const {d,mode,k}=params(options);let rank=big(rankText),size=k;const total=k===null?totals[d]:c(d,k),original=rank;if(rank>=total)throw new RangeError('rank');
  if(size===null){size=0;while(rank>=c(d,size)){rank-=c(d,size);size++;}}
  const trace=[];
  function go(level,need,z,offset){
   work.tree_nodes++;if(level===0){if(need===0&&z===0n)return[];if(need===1&&z===0n)return[offset];throw new Error('leaf rank');}
   let chosen=null;for(const p of patterns){work.pattern_visits++;const count=mass(level,p.size,need);if(z<count){chosen=p;break;}z-=count;}
   if(!chosen)throw new Error('pattern rank');
   const block=5**(level-1);if(chosen.size===0){trace.push({depth:level,offset,pattern:chosen.mask,sizes:[],ranks:[]});return[];}
   if(chosen.size===1){trace.push({depth:level,offset,pattern:chosen.mask,sizes:[need],ranks:[z.toString()]});return go(level-1,need,z,offset+chosen.vertices[0]*block);}
   const m=2**(level-1),lower=Math.max(1,need-m),upper=Math.min(m,need-1);let a=lower;
   for(;a<=upper;a++){const count=allocation(level,need,a);if(z<count)break;z-=count;}if(a>upper)throw new Error('allocation rank');
   const b=need-a,rightCount=c(level-1,b),leftRank=z/rightCount,rightRank=z%rightCount;
   trace.push({depth:level,offset,pattern:chosen.mask,sizes:[a,b],ranks:[leftRank.toString(),rightRank.toString()]});
   return go(level-1,a,leftRank,offset+chosen.vertices[0]*block).concat(go(level-1,b,rightRank,offset+chosen.vertices[1]*block));
  }
  let vertices=go(d,size,rank,0);if(mode==='clique')vertices=vertices.map(v=>transform(v,d,map));vertices.sort((a,b)=>a-b);
  work.selected_sets++;work.returned_vertices+=vertices.length;return{depth:d,mode,size,cardinality_filter:k,rank:original.toString(),count:total.toString(),vertices,trace};
 }
 function rank(options,vertices){
  const {d,mode,k}=params(options);if(!Array.isArray(vertices)||vertices.length>1024)throw new TypeError('vertex list');let a=vertices.map(v=>nat(v,'vertex',5**d-1));if(new Set(a).size!==a.length)throw new TypeError('duplicate vertex');if(k!==null&&a.length!==k||a.length>2**d)return null;
  if(mode==='clique')a=a.map(v=>transform(v,d,inv));a.sort((x,y)=>x-y);const trace=[];
  function go(level,vs,offset){
   work.tree_nodes++;if(level===0)return vs.length<=1?0n:null;
   const block=5**(level-1),groups=new Map();for(const v of vs){const digit=Math.floor((v-offset)/block);if(!groups.has(digit))groups.set(digit,[]);groups.get(digit).push(v);}
   const digits=Array.from(groups.keys()).sort((x,y)=>x-y),pm=digits.reduce((m,x)=>m|(1<<x),0),p=patterns.find(x=>x.mask===pm);if(!p)return null;let z=0n;
   for(const q of patterns){work.pattern_visits++;if(q.mask===pm)break;z+=mass(level,q.size,vs.length);work.rank_additions++;}
   if(!p.size){trace.push({depth:level,offset,pattern:pm,size:0,local_rank:z.toString()});return z;}
   const left=go(level-1,groups.get(digits[0]),offset+digits[0]*block);if(left===null)return null;
   if(p.size===1){z+=left;trace.push({depth:level,offset,pattern:pm,size:vs.length,local_rank:z.toString()});return z;}
   const a=groups.get(digits[0]).length,b=groups.get(digits[1]).length,m=2**(level-1);
   for(let x=Math.max(1,vs.length-m);x<a;x++){z+=allocation(level,vs.length,x);work.rank_additions++;}
   const right=go(level-1,groups.get(digits[1]),offset+digits[1]*block);if(right===null)return null;
   z+=left*c(level-1,b)+right;work.rank_additions++;trace.push({depth:level,offset,pattern:pm,sizes:[a,b],local_rank:z.toString()});return z;
  }
  let z=go(d,a,0);if(z===null)return null;if(k===null)for(let j=0;j<a.length;j++){z+=c(d,j);work.rank_additions++;}
  return{depth:d,mode,size:a.length,cardinality_filter:k,rank:z.toString(),count:(k===null?totals[d]:c(d,k)).toString(),trace};
 }
 function marginal(options,vertex){
  const {d,mode,k}=params(options);nat(vertex,'vertex',5**d-1);let weighted=0n,total=k===null?totals[d]:c(d,k);
  if(k===null)for(let j=1;j<coeff[d].length;j++){weighted+=BigInt(j)*c(d,j);work.marginal_products++;}else{weighted=BigInt(k)*total;work.marginal_products++;}
  const n=BigInt(5**d);if(weighted%n)throw new Error('nonintegral transitive marginal');work.marginal_divisions++;const yes=weighted/n;
  return{depth:d,mode,cardinality_filter:k,vertex,containing:yes.toString(),avoiding:(total-yes).toString(),total:total.toString(),reason:'Coordinatewise cycle rotations act transitively; count incidences and divide by vertex count.'};
 }
 function adjacency(x,y,depth=D){nat(depth,'depth',D);nat(x,'x',5**depth-1);nat(y,'y',5**depth-1);if(x===y)return{adjacent:false,first_difference:null};let place=5**(depth-1);for(let pos=0;pos<depth;pos++){const a=Math.floor(x/place)%5,b=Math.floor(y/place)%5;work.vertex_digit_operations+=2;if(a!==b){const delta=(a-b+5)%5;return{adjacent:delta===1||delta===4,first_difference:pos,digits:[a,b]};}place/=5;}throw new Error('distinct vertices');}
 return{summary:()=>clone({...r.summary,construction_work:r.work}),profile,select,rank,marginal,adjacency,
 page:(options,offset,limit)=>{nat(limit,'limit',32);const o=params(options),start=big(offset),total=o.k===null?totals[o.d]:c(o.d,o.k);if(start>total)throw new RangeError('offset');const out=[];for(let i=0;i<limit&&start+BigInt(i)<total;i++)out.push(select(options,(start+BigInt(i)).toString()));return out;},
 exportAllocationCache:()=>Array.from(allocations,([key,count])=>({key,count:count.toString()})),work:()=>clone(work)};
}
module.exports={compile,openIndex};
