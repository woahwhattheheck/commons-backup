(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.LanternChess=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function boardAxes(orientation){
    const files=['a','b','c','d','e','f','g','h'];
    const ranks=['8','7','6','5','4','3','2','1'];
    if(orientation==='black'){files.reverse();ranks.reverse();}
    return {files,ranks};
  }
  function choiceForMove(meta,from,to){
    if(!meta||!Array.isArray(meta.moves))return null;
    const found=meta.moves.find(move=>move.from===from&&move.to===to);
    return found===undefined?null:found.choice;
  }
  function pieceGlyph(piece){
    return ({K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'})[piece]||'';
  }
  return {boardAxes,choiceForMove,pieceGlyph};
});
