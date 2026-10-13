'use strict';
function rows(descriptors,read){const out=[];for(const d of descriptors){if(d.start!==out.length)throw new TypeError('shard start');const a=JSON.parse(read(d.path));if(!Array.isArray(a)||a.length!==d.count)throw new TypeError('shard length');out.push(...a);}return out;}
function loadIndex(manifest,read){if(manifest.schema!=='commons.complementary_zdd_manifest/v1')throw new TypeError('manifest');return{...manifest.base,nodes:rows(manifest.nodes,read),states:rows(manifest.states,read)};}
function loadReader(manifest,read){if(manifest.schema!=='commons.complementary_zdd_reader_manifest/v1')throw new TypeError('reader manifest');return{...manifest.base,outputs:rows(manifest.outputs,read),conditions:rows(manifest.conditions,read)};}
module.exports={loadIndex,loadReader};
