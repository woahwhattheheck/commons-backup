'use strict';
/* Exact finite graph-isomorphism transcript index. Classical GMW protocol;
   declared finite parity verifier, no cryptographic deployment. */
const SCHEMA='commons.gi_transcript_index/v1';
const clone=x=>JSON.parse(JSON.stringify(x));
function nat(x,name,max){if(!Number.isSafeInteger(x)||x<0||x>max)throw new TypeError(name+' out of range');return x;}
function decimal(x,name){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>1024)throw new TypeError(name+' must be a bounded canonical decimal');return BigInt(x);}
function permutation(p,n){if(!Array.isArray(p)||p.length!==n||new Set(p).size!==n)throw new TypeError('not a permutation');p.forEach(x=>nat(x,'permutation entry',n-1));return p.slice();}
function parity(x){let p=0;while(x){p^=x&1;x>>>=1;}return p;}
function inverse(p){const q=[];p.forEach((x,i)=>q[x]=i);return q;}
function compose(p,q){return q.map(x=>p[x]);}
function pairs(n){const a=[];for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)a.push([i,j]);return a;}
function allPermutations(n){const out=[],a=[],used=Array(n).fill(false);function walk(){if(a.length===n){out.push(a.slice());return;}for(let x=0;x<n;x++)if(!used[x]){used[x]=true;a.push(x);walk();a.pop();used[x]=false;}}walk();return out;}
function buildIndex(input){
 if(!input||typeof input!=='object')throw new TypeError('input required');
 const n=nat(input.n,'n',7);if(n<2)throw new RangeError('n >= 2');
 const edgePairs=pairs(n), pairIndex=new Map(edgePairs.map((p,i)=>[p.join(','),i]));
 if(!Array.isArray(input.graph0_edges))throw new TypeError('edges required');
 let graph0=0;const edges=input.graph0_edges.map(e=>{if(!Array.isArray(e)||e.length!==2)throw new TypeError('edge');const [a,b]=e;nat(a,'edge',n-1);nat(b,'edge',n-1);if(a>=b)throw new TypeError('ordered distinct endpoints required');const bit=1<<pairIndex.get(e.join(','));if(graph0&bit)throw new TypeError('duplicate edge');graph0|=bit;return e.slice();});
 const sigma=permutation(input.witness_permutation,n), sigmaInv=inverse(sigma),v=input.verifier;
 if(!v||!Array.isArray(v.edge_parity_indices))throw new TypeError('verifier required');
 const cb=nat(v.coin_bits,'coin_bits',4),C=2**cb;
 const ci=nat(v.coin_parity_mask,'coin_parity_mask',C-1);
 let edgeParityMask=0;for(const i of v.edge_parity_indices){nat(i,'edge parity index',edgePairs.length-1);if(edgeParityMask&(1<<i))throw new TypeError('duplicate parity index');edgeParityMask|=1<<i;}
 const ps=allPermutations(n),m=ps.length,N=C*m;if(2*N>200000)throw new RangeError('trial cap');
 const rank=new Map(ps.map((p,i)=>[p.join(','),i]));
 const work={permutations:m,graph_edge_images:0,permutation_compositions:0,challenge_cells:0,coupling_rows:0,simulator_trials:0};
 function image(p,es=edges){let mask=0;for(const [x,y]of es){let a=p[x],b=p[y];if(a>b)[a,b]=[b,a];mask|=1<<pairIndex.get(a+','+b);work.graph_edge_images++;}return mask;}
 const graph1=image(sigma),graph1Edges=edgePairs.filter((_,i)=>graph1&(1<<i)),images=ps.map(p=>image(p)),images1=ps.map(p=>image(p,graph1Edges)),orbitMasks=Array.from(new Set(images)).sort((a,b)=>a-b),orbitMap=new Map(orbitMasks.map((x,i)=>[x,i]));
 const fibers=orbitMasks.map(()=>[]),imageOrbit=images.map((x,i)=>{const k=orbitMap.get(x);fibers[k].push(i);return k;});
 const simulatorOrbit=[imageOrbit,images1.map(mask=>{const o=orbitMap.get(mask);if(o===undefined)throw new Error('public orbit mismatch');return o;})];
 const plus=ps.map(p=>{work.permutation_compositions++;return rank.get(compose(p,sigma).join(','));});
 const minus=ps.map(p=>{work.permutation_compositions++;return rank.get(compose(p,sigmaInv).join(','));});
 const challenge=Array.from({length:C},(_,coin)=>orbitMasks.map(mask=>{work.challenge_cells++;return parity(mask&edgeParityMask)^parity(coin&ci);}));
 const realToTrial=Array(N),trialToReal=Array(2*N).fill(-1),accepted=Array.from({length:C},()=>[]),rejected=Array.from({length:C},()=>[]);
 const certificateRows=[];
 for(let coin=0;coin<C;coin++){
  const bcounts=[0,0];for(let rho=0;rho<m;rho++){
   const b=challenge[coin][imageOrbit[rho]],tau=b?minus[rho]:rho,trial=(2*coin+b)*m+tau,id=coin*m+rho;
   if(trialToReal[trial]!==-1)throw new Error('coupling not injective');
   realToTrial[id]=trial;trialToReal[trial]=id;work.coupling_rows++;bcounts[b]++;
  }
  let zeros=0;for(let b=0;b<2;b++)for(let tau=0;tau<m;tau++){
   const trial=(2*coin+b)*m+tau,rho=b?plus[tau]:tau,actual=challenge[coin][simulatorOrbit[b][tau]],kept=actual===b;
   if(simulatorOrbit[b][tau]!==imageOrbit[rho])throw new Error('public image coupling mismatch');
   if(kept){if(trialToReal[trial]!==coin*m+rho)throw new Error('coupling mismatch');accepted[coin].push(trial);}
   else{if(trialToReal[trial]!==-1)throw new Error('rejection mismatch');rejected[coin].push(trial);}
   zeros++;work.simulator_trials++;
  }
  if(accepted[coin].length!==m||rejected[coin].length!==m)throw new Error('unbalanced coin');
  certificateRows.push({coin,real_choices:m,simulator_trials:zeros,accepted:m,rejected:m,challenge_counts:bcounts,acceptance_probability:{numerator:'1',denominator:'2'},conditional_view_mass:{numerator:'1',denominator:String(m)}});
 }
 const record={schema:SCHEMA,input:clone(input),n,edge_pairs:edgePairs,graph0_mask:graph0,graph1_mask:graph1,witness:sigma,coin_values:C,permutation_count:m,permutations:ps,orbit_masks:orbitMasks,orbit_fibers:fibers,image_orbit:imageOrbit,simulator_orbit_by_guess:simulatorOrbit,compose_witness:plus,compose_inverse_witness:minus,challenge,real_to_trial:realToTrial,trial_to_real:trialToReal,accepted_by_coin:accepted,rejected_by_coin:rejected,certificate_rows:certificateRows,summary:{real_choices:N,simulator_trials:2*N,accepted:N,rejected:N,orbit_size:orbitMasks.length,automorphisms:fibers[orbitMap.get(graph0)].length,real_view_mass:{numerator:'1',denominator:String(N)},statistical_distance:{numerator:'0',denominator:'1'},expected_attempts:{numerator:'2',denominator:'1'}},work};
 return {record,scope:'Exact one-round finite instance and fixed-coin rejection simulator. No general SZK/PZK transformation, new protocol theorem or deployment claim.'};
}
function openIndex(saved){
 if(!saved||saved.schema!==SCHEMA)throw new TypeError('schema');
 const r=clone(saved),n=nat(r.n,'n',7);if(n<2)throw new RangeError('n');
 const m=nat(r.permutation_count,'permutation_count',5040),C=nat(r.coin_values,'coin_values',16),N=m*C;
 if(!m||!C||2*N>200000)throw new RangeError('sizes');
 const arrays=[['permutations',m],['image_orbit',m],['compose_witness',m],['compose_inverse_witness',m],['real_to_trial',N],['trial_to_real',2*N],['challenge',C],['accepted_by_coin',C],['rejected_by_coin',C],['certificate_rows',C]];
 for(const [k,len]of arrays)if(!Array.isArray(r[k])||r[k].length!==len)throw new TypeError('shape '+k);
 if(!Array.isArray(r.orbit_masks)||!r.orbit_masks.length||r.orbit_fibers.length!==r.orbit_masks.length)throw new TypeError('orbit shape');
 const O=r.orbit_masks.length;
 if(!Array.isArray(r.simulator_orbit_by_guess)||r.simulator_orbit_by_guess.length!==2)throw new TypeError('public images');r.simulator_orbit_by_guess.forEach(a=>{if(!Array.isArray(a)||a.length!==m)throw new TypeError('public image size');a.forEach(x=>nat(x,'public orbit',O-1));});
 const permRanks=new Map();r.permutations.forEach((p,i)=>{permutation(p,n);const key=p.join(',');if(permRanks.has(key))throw new TypeError('duplicate permutation');permRanks.set(key,i);});
 const orbitByMask=new Map(r.orbit_masks.map((x,i)=>{nat(x,'graph mask',2**(n*(n-1)/2)-1);return[x,i];}));
 if(orbitByMask.size!==O)throw new TypeError('duplicate orbit mask');
 r.image_orbit.forEach(x=>nat(x,'orbit',O-1));r.compose_witness.forEach(x=>nat(x,'composition',m-1));r.compose_inverse_witness.forEach(x=>nat(x,'composition',m-1));
 r.real_to_trial.forEach(x=>nat(x,'trial',2*N-1));r.trial_to_real.forEach(x=>{if(x!==-1)nat(x,'real',N-1);});
 r.orbit_fibers.forEach(a=>{if(!Array.isArray(a))throw new TypeError('fiber');a.forEach(x=>nat(x,'fiber rank',m-1));});
 r.challenge.forEach(a=>{if(!Array.isArray(a)||a.length!==O)throw new TypeError('challenge row');a.forEach(x=>nat(x,'bit',1));});
 const acceptedRanks=[],rejectedRanks=[];for(let c=0;c<C;c++){for(const k of ['accepted_by_coin','rejected_by_coin']){const a=r[k][c];if(a.length!==m)throw new TypeError('trial fiber size');a.forEach(x=>{nat(x,'trial',2*N-1);if(Math.floor(x/(2*m))!==c)throw new TypeError('coin binding');});if(new Set(a).size!==m)throw new TypeError('duplicate trial');}acceptedRanks.push(new Map(r.accepted_by_coin[c].map((x,i)=>[x,i])));rejectedRanks.push(new Map(r.rejected_by_coin[c].map((x,i)=>[x,i])));}
 const work={permutation_rows_indexed:m,trial_rank_rows_indexed:2*N,saved_lookups:0,condition_cell_scans:0,transcript_materializations:0,run_digits:0,graph_images:0,challenge_recomputations:0,coupling_reconstructions:0};
 const coin=x=>nat(x,'coin',C-1), realID=x=>nat(x,'real id',N-1),trialID=x=>nat(x,'trial id',2*N-1);
 function edges(mask){return r.edge_pairs.filter((_,i)=>mask&(1<<i)).map(x=>x.slice());}
 function view(id){realID(id);const c=Math.floor(id/m),rho=id%m,trial=r.real_to_trial[id],b=Math.floor(trial/m)%2,tau=trial%m,o=r.image_orbit[rho];work.saved_lookups+=4;work.transcript_materializations++;return {real_id:id,coin:c,commitment_orbit:o,commitment_mask:r.orbit_masks[o],commitment_edges:edges(r.orbit_masks[o]),challenge:b,response_rank:tau,response_permutation:r.permutations[tau].slice(),prover_rank:rho,prover_permutation:r.permutations[rho].slice(),accepted_simulator_trial:trial,unconditional_mass:clone(r.summary.real_view_mass)};}
 function trial(id){trialID(id);const c=Math.floor(id/(2*m)),b=Math.floor(id/m)%2,tau=id%m,o=r.simulator_orbit_by_guess[b][tau],actual=r.challenge[c][o],v=r.trial_to_real[id];work.saved_lookups+=4;return {trial_id:id,coin:c,guessed_challenge:b,permutation_rank:tau,commitment_orbit:o,commitment_mask:r.orbit_masks[o],actual_challenge:actual,accepted:v>=0,real_id:v>=0?v:null,conditional_trial_mass:{numerator:'1',denominator:String(2*m)}};}
 function condition(f={}){if(!f||typeof f!=='object')throw new TypeError('condition');for(const k of Object.keys(f))if(!['coin','orbit','challenge'].includes(k))throw new TypeError('unknown condition');if(f.coin!==undefined)coin(f.coin);if(f.orbit!==undefined)nat(f.orbit,'orbit',O-1);if(f.challenge!==undefined)nat(f.challenge,'challenge',1);const cells=[];let count=0;for(let c=0;c<C;c++)if(f.coin===undefined||c===f.coin)for(let o=0;o<O;o++)if(f.orbit===undefined||o===f.orbit){work.condition_cell_scans++;if(f.challenge===undefined||r.challenge[c][o]===f.challenge){const length=r.orbit_fibers[o].length;cells.push({coin:c,orbit:o,challenge:r.challenge[c][o],count:length});count+=length;}}return {filter:clone(f),count:String(count),cells};}
 function conditionalSelect(f,rankText){const q=condition(f);let rank=decimal(rankText,'rank');if(rank>=BigInt(q.count))throw new RangeError('rank');for(const c of q.cells){if(rank<BigInt(c.count)){const rho=r.orbit_fibers[c.orbit][Number(rank)];work.saved_lookups++;return {rank:rankText,order:'coin, orbit, lexicographic prover permutation',condition:q.filter,view:view(c.coin*m+rho)};}rank-=BigInt(c.count);}throw new Error('missing row');}
 function conditionalRank(f,id){const q=condition(f),v=view(id);let rank=0;for(const c of q.cells){if(c.coin===v.coin&&c.orbit===v.commitment_orbit){const z=r.orbit_fibers[c.orbit].indexOf(v.prover_rank);if(z<0)throw new Error('fiber absent');return {rank:String(rank+z),count:q.count,real_id:id};}rank+=c.count;}return null;}
 function runSelect(c,failures,rankText){coin(c);nat(failures,'failures',128);const base=BigInt(m),total=base**BigInt(failures+1);let z=decimal(rankText,'rank');if(z>=total)throw new RangeError('run rank');const digits=Array(failures+1);for(let i=failures;i>=0;i--){digits[i]=Number(z%base);z/=base;work.run_digits++;}const ids=digits.map((d,i)=>(i<failures?r.rejected_by_coin[c]:r.accepted_by_coin[c])[d]);work.saved_lookups+=ids.length;const last=ids[failures];return {coin:c,failures,rank:rankText,count:total.toString(),trial_ids:ids,trial_fiber_ranks:digits,final_real_id:r.trial_to_real[last],final_view:view(r.trial_to_real[last]),trial_sequence_mass_given_coin:{numerator:'1',denominator:(BigInt(2*m)**BigInt(failures+1)).toString()}};}
 function runRank(ids){if(!Array.isArray(ids)||!ids.length||ids.length>129)throw new TypeError('run');ids.forEach(trialID);const c=Math.floor(ids[0]/(2*m));let z=0n;for(let i=0;i<ids.length;i++){if(Math.floor(ids[i]/(2*m))!==c)throw new TypeError('coins change in rewind run');const d=(i+1===ids.length?acceptedRanks[c]:rejectedRanks[c]).get(ids[i]);if(d===undefined)throw new TypeError('not failures then success');z=z*BigInt(m)+BigInt(d);work.run_digits++;}return {coin:c,failures:ids.length-1,rank:z.toString(),count:(BigInt(m)**BigInt(ids.length)).toString()};}
 return {
 summary:()=>clone({n,coin_values:C,permutations:m,orbit_size:O,...r.summary,construction_work:r.work}),
 permutation:(rank)=>{nat(rank,'permutation rank',m-1);work.saved_lookups++;return r.permutations[rank].slice();},
 permutationRank:(p)=>{permutation(p,n);work.saved_lookups++;return permRanks.get(p.join(','));},
 orbit:(o)=>{nat(o,'orbit',O-1);work.saved_lookups+=2;return clone({orbit:o,mask:r.orbit_masks[o],edges:edges(r.orbit_masks[o]),prover_ranks:r.orbit_fibers[o],challenge_by_coin:r.challenge.map(a=>a[o])});},
 orbitForMask:(mask)=>{nat(mask,'mask',2**(n*(n-1)/2)-1);work.saved_lookups++;return orbitByMask.has(mask)?orbitByMask.get(mask):null;},
 pageOrbits:(offset,limit)=>{nat(offset,'offset',O);nat(limit,'limit',128);return r.orbit_masks.slice(offset,offset+limit).map((mask,j)=>{const o=offset+j;work.saved_lookups+=2;return {orbit:o,mask,fiber_count:r.orbit_fibers[o].length};});},
 view,trial,condition,conditionalSelect,conditionalRank,runSelect,runRank,
 pageTrials:(c,acceptedFlag,offset,limit)=>{coin(c);if(typeof acceptedFlag!=='boolean')throw new TypeError('accepted flag');nat(offset,'offset',m);nat(limit,'limit',256);const a=(acceptedFlag?r.accepted_by_coin:r.rejected_by_coin)[c].slice(offset,offset+limit);return a.map(trial);},
 stoppingLaw:(attempt)=>{nat(attempt,'attempt',4096);if(!attempt)throw new RangeError('attempt positive');const den=(1n<<BigInt(attempt)).toString();return {attempt,first_success:{numerator:'1',denominator:den},no_success_after_attempt:{numerator:'1',denominator:den},expected_attempts:{numerator:'2',denominator:'1'},convention:'Verifier coins fixed once; independent uniform guess and permutation on each attempt.'};},
 work:()=>clone(work),snapshot:()=>clone(r),
 publicSnapshot:()=>clone({schema:'commons.gi_public_simulator/v1',n:r.n,edge_pairs:r.edge_pairs,graph0_mask:r.graph0_mask,graph1_mask:r.graph1_mask,coin_values:C,permutation_count:m,permutations:r.permutations,orbit_masks:r.orbit_masks,simulator_orbit_by_guess:r.simulator_orbit_by_guess,challenge:r.challenge,accepted_by_coin:r.accepted_by_coin,rejected_by_coin:r.rejected_by_coin})
 };
}
function openSimulator(saved){
 if(!saved||saved.schema!=='commons.gi_public_simulator/v1')throw new TypeError('public simulator schema');
 const allowed=['schema','n','edge_pairs','graph0_mask','graph1_mask','coin_values','permutation_count','permutations','orbit_masks','simulator_orbit_by_guess','challenge','accepted_by_coin','rejected_by_coin'];
 if(Object.keys(saved).some(k=>!allowed.includes(k)))throw new TypeError('extra public field');
 const r=clone(saved),n=nat(r.n,'n',7),m=nat(r.permutation_count,'m',5040),C=nat(r.coin_values,'coins',16);
 if(n<2||!m||!C||2*m*C>200000||r.permutations.length!==m||r.challenge.length!==C||r.simulator_orbit_by_guess.length!==2)throw new TypeError('shape');
 const O=r.orbit_masks.length;if(!O)throw new TypeError('orbit');
 r.permutations.forEach(p=>permutation(p,n));
 r.simulator_orbit_by_guess.forEach(a=>{if(a.length!==m)throw new TypeError('image size');a.forEach(x=>nat(x,'orbit',O-1));});
 r.challenge.forEach(a=>{if(a.length!==O)throw new TypeError('challenge size');a.forEach(x=>nat(x,'bit',1));});
 const ar=[],rr=[];for(let c=0;c<C;c++)for(const [key,out]of [['accepted_by_coin',ar],['rejected_by_coin',rr]]){const a=r[key][c];if(!Array.isArray(a)||a.length!==m||new Set(a).size!==m)throw new TypeError('trial list');a.forEach(x=>{nat(x,'trial',2*m*C-1);if(Math.floor(x/(2*m))!==c)throw new TypeError('coin');});out.push(new Map(a.map((x,i)=>[x,i])));}
 const work={trial_rank_rows_indexed:2*m*C,saved_lookups:0,run_digits:0,graph_images:0,challenge_recomputations:0,coupling_rows_read:0};
 function trial(id){nat(id,'trial',2*m*C-1);const coin=Math.floor(id/(2*m)),b=Math.floor(id/m)%2,tau=id%m,o=r.simulator_orbit_by_guess[b][tau],actual=r.challenge[coin][o],mask=r.orbit_masks[o];work.saved_lookups+=4;return {trial_id:id,coin,guessed_challenge:b,response_rank:tau,response_permutation:r.permutations[tau].slice(),commitment_orbit:o,commitment_mask:mask,commitment_edges:r.edge_pairs.filter((_,i)=>mask&(1<<i)).map(x=>x.slice()),actual_challenge:actual,accepted:b===actual,trial_mass_given_coin:{numerator:'1',denominator:String(2*m)}};}
 return {summary:()=>({n,permutations:m,coin_values:C,public_fields:allowed.slice(),witness_present:false,real_coupling_present:false}),
 trial,
 runSelect:(coin,failures,rankText)=>{nat(coin,'coin',C-1);nat(failures,'failures',128);let z=decimal(rankText,'rank');const base=BigInt(m),total=base**BigInt(failures+1);if(z>=total)throw new RangeError('rank');const digits=Array(failures+1);for(let i=failures;i>=0;i--){digits[i]=Number(z%base);z/=base;work.run_digits++;}const ids=digits.map((d,i)=>(i<failures?r.rejected_by_coin[coin]:r.accepted_by_coin[coin])[d]);work.saved_lookups+=ids.length;return {coin,failures,rank:rankText,count:total.toString(),trial_ids:ids,final_transcript:trial(ids[failures]),trial_sequence_mass_given_coin:{numerator:'1',denominator:(BigInt(2*m)**BigInt(failures+1)).toString()}};},
 runRank:ids=>{if(!Array.isArray(ids)||!ids.length||ids.length>129)throw new TypeError('run');const coin=Math.floor(ids[0]/(2*m));nat(coin,'coin',C-1);let z=0n;for(let i=0;i<ids.length;i++){nat(ids[i],'trial',2*m*C-1);if(Math.floor(ids[i]/(2*m))!==coin)throw new TypeError('changing coins');const d=(i+1===ids.length?ar[coin]:rr[coin]).get(ids[i]);if(d===undefined)throw new TypeError('run outcome order');z=z*BigInt(m)+BigInt(d);work.run_digits++;}return {coin,failures:ids.length-1,rank:z.toString(),count:(BigInt(m)**BigInt(ids.length)).toString()};},
 work:()=>clone(work),snapshot:()=>clone(r)
 };
}
module.exports={buildIndex,openIndex,openSimulator};
