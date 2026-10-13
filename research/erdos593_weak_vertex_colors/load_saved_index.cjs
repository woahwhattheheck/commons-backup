'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {openIndex}=require('./weak_vertex_colors.cjs');
function loadSavedIndex(directory=__dirname){return openIndex(JSON.parse(fs.readFileSync(path.join(directory,'certificate.json'),'utf8')));}
module.exports={loadSavedIndex};
