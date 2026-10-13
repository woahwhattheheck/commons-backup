'use strict';
const test=require('node:test');const assert=require('node:assert/strict');
const ui=require('./chess_ui.js');
const meta={orientation:'white',moves:[{from:'g1',to:'f3',choice:0},{from:'g1',to:'h3',choice:1}]};
test('white and black board axes are deterministic 180-degree views',()=>{
  const white=ui.boardAxes('white'),black=ui.boardAxes('black');
  assert.deepEqual([white.files[0]+white.ranks[0],white.files.at(-1)+white.ranks.at(-1)],['a8','h1']);
  assert.deepEqual([black.files[0]+black.ranks[0],black.files.at(-1)+black.ranks.at(-1)],['h1','a8']);
});
test('authored move maps to its exact ordinary choice including index zero',()=>{
  assert.equal(ui.choiceForMove(meta,'g1','f3'),0);assert.equal(ui.choiceForMove(meta,'g1','h3'),1);
});
test('un-authored square pair is not invented',()=>assert.equal(ui.choiceForMove(meta,'g1','e2'),null));
test('piece glyphs are presentation only',()=>{assert.equal(ui.pieceGlyph('N'),'♘');assert.equal(ui.pieceGlyph('n'),'♞');assert.equal(ui.pieceGlyph('x'),'');});
