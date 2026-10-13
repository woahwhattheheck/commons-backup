'use strict';
// Finite selected-prime support for odd n = p + 2^k + 2^l.
// Prime values are identified premises; this module does not test primality.
const SCHEMA='selected-prime-two-powers/v1';
const copy=x=>JSON.parse(JSON.stringify(x));
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function nat(x,name){if(typeof x==='bigint'){if(x<0n)throw new RangeError(name);return x;}if(typeof x==='number'){if(!Number.isSafeInteger(x)||x<0)throw new RangeError(name);return BigInt(x);}if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>2000)throw new TypeError(name+' must be a canonical nonnegative integer');return BigInt(x);}
function pop(x){let c=0;while(x){c+=Number(x&1n);x>>=1n;}return c;}
function positions(x){const a=[];let j=0;while(x){if(x&1n)a.push(j);x>>=1n;j++;}return a;}
function pair(d){if(d<2n)return null;const a=positions(d);if(a.length===1)return[a[0]-1,a[0]-1];if(a.length===2)return a;return null;}
function buildIndex(input){
 const a=copy(input),pr=a.primes;
 if(!Array.isArray(pr)||pr.length<1||pr.length>16)throw new RangeError('one to sixteen identified primes required');
 pr.forEach((p,i)=>{integer(p,'prime premise',2,127);if(i&&p<=pr[i-1])throw new RangeError('prime premises must increase');});
 let B=1,b=0;while(B<=pr[pr.length-1]){B*=2;b++;}
 const L=integer(a.bits,'bits',b+1,256),H=L-b;
 if((B/2)*H*4>65536)throw new RangeError('stratum budget exceeded');
 const choose=Array.from({length:H+1},(_,n)=>['1',String(n),String(BigInt(n)*BigInt(n-1)/2n)]);
 const work={small_differences:0,local_residuals:0,strata:0,binomial_cells:3*(H+1),small_numbers_classified:B/2,large_numbers_enumerated:0,power_pairs_enumerated:0,prime_tests:0};
 const small=[],rows=[],buckets=new Map();
 function add(mask,diagonal,count){const k=mask+':'+diagonal;buckets.set(k,(buckets.get(k)||0n)+count);}
 for(let n=1;n<B;n+=2){let mask=0,diagonal=0;const reps=[];
  pr.forEach((p,i)=>{work.small_differences++;const q=pair(BigInt(n-p));if(q){mask|=1<<i;if(q[0]===q[1])diagonal|=1<<i;reps.push([p,...q]);}});
  small.push([n,mask,diagonal,reps]);add(mask,diagonal,1n);
 }
 for(let r=1;r<B;r+=2)for(let z=0;z<H;z++){
  const m=H-z-1;
  for(let w=0;w<=Math.min(2,m);w++){
   let mask=0,diagonal=0;
   pr.forEach((p,i)=>{work.local_residuals++;const borrow=p>r?1:0,low=r-p+borrow*B,t=pop(BigInt(low))+w+(borrow?z:1);if(t===1||t===2){mask|=1<<i;if(t===1)diagonal|=1<<i;}});
   const count=choose[m][w];rows.push([r,z,w,m,mask,diagonal,count]);add(mask,diagonal,BigInt(count));
  }
  const low=1n+BigInt(m)+BigInt(m)*BigInt(m-1)/2n,tail=(1n<<BigInt(m))-low;
  if(tail>0n){rows.push([r,z,-1,m,0,0,String(tail)]);add(0,0,tail);}
 }
 work.strata=rows.length;
 const spectrum=[...buckets].map(([k,c])=>[...k.split(':').map(Number),String(c)]).sort((x,y)=>x[0]-y[0]||x[1]-y[1]);
 let represented=0n,unordered=0n,ordered=0n;const perPrime=pr.map(()=>0n);
 for(const [mask,d,c]of spectrum){const q=BigInt(c);if(mask)represented+=q;unordered+=q*BigInt(pop(BigInt(mask)));ordered+=q*BigInt(2*pop(BigInt(mask))-pop(BigInt(d)));pr.forEach((_,i)=>{if(mask&(1<<i))perPrime[i]+=q;});}
 return{schema:SCHEMA,input:a,B,b,H,bits:L,maximum:String((1n<<BigInt(L))-1n),prime_premise:a.prime_premise,small_schema:['n','support_mask','diagonal_mask','representations[p,k,l]'],small,row_schema:['r','z','weight_or_minus1_for_at_least3','upper_bits','support_mask','diagonal_mask','count'],rows,choose,spectrum_schema:['support_mask','diagonal_mask','number_count'],spectrum,summary:{odd_numbers:String(1n<<BigInt(L-1)),represented:String(represented),unrepresented_by_selected_primes:String((1n<<BigInt(L-1))-represented),unordered_representations:String(unordered),ordered_representations:String(ordered),per_prime:pr.map((p,i)=>[p,String(perPrime[i])])},work};
}
function openIndex(saved){
 const d=typeof saved==='string'?JSON.parse(saved):copy(saved);
 if(!d||d.schema!==SCHEMA||!Array.isArray(d.rows)||!Array.isArray(d.small)||!Array.isArray(d.choose))throw new TypeError('invalid saved index');
 const pr=d.input.primes,L=integer(d.bits,'bits',2,256),H=integer(d.H,'H',1,255),B=integer(d.B,'B',4,128);
 if(d.b+H!==L||2**d.b!==B||d.choose.length!==H+1||d.small.length!==B/2||d.rows.length>65536)throw new RangeError('saved shape mismatch');
 if(!Array.isArray(pr)||pr.length<1||pr.length>16)throw new TypeError('saved prime list');pr.forEach((p,i)=>{integer(p,'prime premise',2,B-1);if(i&&p<=pr[i-1])throw new RangeError('saved prime ordering');});
 const maximum=nat(d.maximum,'maximum'),maskMax=(1<<pr.length)-1;if(maximum!==(1n<<BigInt(L))-1n)throw new RangeError('saved maximum');
 const choose=d.choose.map((r,n)=>{if(!Array.isArray(r)||r.length!==3)throw new TypeError('binomial row');return r.map(x=>nat(x,'binomial'));});
 d.rows.forEach(r=>{if(!Array.isArray(r)||r.length!==7)throw new TypeError('stratum row');integer(r[0],'r',1,B-1);integer(r[1],'z',0,H-1);integer(r[2],'weight',-1,2);integer(r[3],'upper bits',0,H-1);integer(r[4],'mask',0,maskMax);integer(r[5],'diagonal mask',0,maskMax);nat(r[6],'stratum count');if(!(r[0]&1)||r[3]!==H-r[1]-1||(r[5]&r[4])!==r[5])throw new RangeError('stratum coordinates');});
 d.small.forEach((r,i)=>{if(!Array.isArray(r)||r.length!==4||r[0]!==2*i+1||!Array.isArray(r[3]))throw new TypeError('small row');integer(r[1],'small mask',0,maskMax);integer(r[2],'small diagonal',0,maskMax);});
 const work={queries:0,rows_indexed:d.rows.length,small_rows_indexed:d.small.length,row_scans:0,small_scans:0,binomial_lookups:0,prefix_bits:0,count_cache_hits:0,binary_selection_steps:0,point_subtractions:0,new_strata:0,new_binomial_cells:0,new_prime_tests:0};
 const cache=new Map();
 function filter(f){if(f===undefined||f===null)return{exact:null,required:0,forbidden:0};if(typeof f!=='object'||Array.isArray(f))throw new TypeError('filter object');const exact=f.exact===undefined?null:integer(f.exact,'exact mask',0,maskMax),required=integer(f.required===undefined?0:f.required,'required',0,maskMax),forbidden=integer(f.forbidden===undefined?0:f.forbidden,'forbidden',0,maskMax);return{exact,required,forbidden};}
 function matches(mask,f){return(f.exact===null?mask!==0:mask===f.exact)&&(mask&f.required)===f.required&&(mask&f.forbidden)===0;}
 function C(n,k){work.binomial_lookups++;return k<0||k>n||k>2?0n:choose[n][k];}
 function lowWeight(t,m,w){
  if(t<0n)return 0n;if(t>=(1n<<BigInt(m))-1n)return C(m,w);
  let total=0n,remaining=w;
  for(let j=m-1;j>=0;j--){work.prefix_bits++;if((t>>BigInt(j))&1n){total+=C(j,remaining);remaining--;if(remaining<0)return total;}}
  return total+(remaining===0?1n:0n);
 }
 function upto(bound,f){
  if(bound<1n)return 0n;if(bound>maximum)bound=maximum;
  const key=bound+'|'+f.exact+'|'+f.required+'|'+f.forbidden;
  if(cache.has(key)){work.count_cache_hits++;return cache.get(key);}
  let total=0n;
  for(const row of d.small){work.small_scans++;if(BigInt(row[0])<=bound&&matches(row[1],f))total++;}
  for(const row of d.rows){work.row_scans++;if(!matches(row[4],f))continue;
   const [r,z,w,m]=row;if(bound<BigInt(B+r))continue;
   const h=(bound-BigInt(r))/BigInt(B),q=h-(1n<<BigInt(z));if(q<0n)continue;
   let u=q>>(BigInt(z)+1n);const cap=(1n<<BigInt(m))-1n;if(u>cap)u=cap;
   if(u===cap){total+=BigInt(row[6]);continue;}
   total+=w===-1?u+1n-lowWeight(u,m,0)-lowWeight(u,m,1)-lowWeight(u,m,2):lowWeight(u,m,w);
  }
  if(cache.size<4096)cache.set(key,total);return total;
 }
 function describe(n){
  if(n<1n||n>maximum||(n&1n)===0n)throw new RangeError('point must be an odd integer inside the saved domain');
  let mask=0,diagonal=0;const reps=[];
  pr.forEach((p,i)=>{work.point_subtractions++;const a=pair(n-BigInt(p));if(a){mask|=1<<i;if(a[0]===a[1])diagonal|=1<<i;reps.push({prime:p,exponents:a,ordered_multiplicity:a[0]===a[1]?1:2});}});
  return{n:String(n),support_mask:mask,diagonal_mask:diagonal,represented:mask!==0,representations:reps,absence_scope:mask?'not applicable':'only the supplied prime set'};
 }
 function select0(rank,f){
  const total=upto(maximum,f);if(rank>=total)throw new RangeError('rank outside selected family');
  let lo=1n,hi=maximum;
  while(lo<hi){work.binary_selection_steps++;const mid=(lo+hi)>>1n;if(upto(mid,f)>rank)hi=mid;else lo=mid+1n;}
  return{rank:String(rank),filter:copy(f),...describe(lo)};
 }
 return{
  summary(){work.queries++;return{...copy(d.summary),bits:L,maximum:d.maximum,primes:pr.slice(),strata:d.rows.length,spectrum:copy(d.spectrum),construction_work:copy(d.work)};},
  point(n){work.queries++;return describe(nat(n,'n'));},
  count(bound,f){work.queries++;const q=filter(f);return{bound:String(nat(bound,'bound')),filter:q,count:String(upto(nat(bound,'bound'),q))};},
  interval(lo,hi,f){work.queries++;const a=nat(lo,'lo'),b=nat(hi,'hi');if(a>b)throw new RangeError('reversed interval');const q=filter(f);return{lo:String(a),hi:String(b),filter:q,count:String(upto(b,q)-upto(a-1n,q))};},
  select(rank,f){work.queries++;return select0(nat(rank,'rank'),filter(f));},
  rank(n,f){work.queries++;const q=filter(f),v=nat(n,'n'),p=describe(v);if(!matches(p.support_mask,q))return{n:String(v),filter:q,rank:null,...p};return{filter:q,rank:String(upto(v-1n,q)),...p};},
  page(start,limit,f){work.queries++;const s=nat(start,'start');integer(limit,'limit',0,32);const q=filter(f),total=upto(maximum,q);if(s>total)throw new RangeError('page start');const out=[];for(let j=0;j<limit&&s+BigInt(j)<total;j++)out.push(select0(s+BigInt(j),q));return{start:String(s),total:String(total),filter:q,values:out};},
  stratum(i){work.queries++;integer(i,'stratum',0,d.rows.length-1);return{index:i,row:copy(d.rows[i])};},
  work(){return{...work,count_cache_entries:cache.size};}
 };
}
module.exports={buildIndex,openIndex,SCHEMA};
