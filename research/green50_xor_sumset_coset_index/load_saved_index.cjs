'use strict';
function rows(manifest,read,key){let out=[];for(const s of manifest[key]){if(s.start!==out.length)throw new Error('shard start');const a=read(s.path);if(!Array.isArray(a)||a.length!==s.count)throw new Error('shard count');out=out.concat(a);}return out;}
function loadInput(manifest,read){if(manifest.format!=='xor-input-shards-v1')throw new Error('input format');const out={...manifest.input};out.catalog=rows(manifest,read,'catalog_shards').map(a=>({id:a[0],code_id:a[1],dimension:a[2],representative:a[3],vertices:a[4]}));return out;}
function loadData(manifest,read){if(manifest.format!=='xor-data-shards-v1')throw new Error('data format');const out={...manifest.data};out.profiles=rows(manifest,read,'profile_shards');return out;}
module.exports={loadInput,loadData};
