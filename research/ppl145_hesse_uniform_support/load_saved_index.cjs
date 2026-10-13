'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {openIndex}=require('./hesse_uniform_support.cjs');
function json(directory,name){return JSON.parse(fs.readFileSync(path.join(directory,name),'utf8'));}
function loadCertificate(directory=__dirname){const m=json(directory,'certificate_manifest.json');const d=m.base;d.records=m.records.flatMap(p=>json(directory,p.path));return d;}
function loadReaderEvidence(directory=__dirname){const m=json(directory,'reader_manifest.json');const d=m.base;d.caches.classifications=m.classifications.flatMap(p=>json(directory,p.path));return d;}
function loadSavedIndex(directory=__dirname){return openIndex(loadCertificate(directory));}
module.exports={loadCertificate,loadReaderEvidence,loadSavedIndex};
