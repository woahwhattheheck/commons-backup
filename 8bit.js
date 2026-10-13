                                                                                                   

                                                                                             
                                                                                 
                                                                                                      

                                           

                                                                                                
                                                                                                
                                                                                              

                  
                                                 

                                                                                           
                                                                                            
                                                                                                
                                                                                                 
                                                                                       

                                                                                               
                                            

                                                                                          
                                                                                               
                                                                                                
                                                                                           
                                                                                             
                                

                                                                                            
                                                                                                
                                                                                                
                                                                                               
                                                                                                
                           
                                                                                             
                                                         
                                                                                              
                                                                                           
                                                                        
                                                                                               
                            

                                
                                                                                             
                                                                           
                                                                               
                                                                                           
                                                                   
                                                                                           
             
(function (g) {
"use strict";

function hash(s) {
  var h = 2166136261, i;
  s = String(s);
  for (i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function up(v) { return String(v == null ? "" : v).trim().toUpperCase(); }

function hsl(h, s, l) { return "hsl(" + (h % 360) + " " + s + "% " + l + "%)"; }

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

/* Same state ink as pixel-crisp.css so the canvas and the DOM agree. */
var STATE_INK = {
  talk: "#e8c36a",
  build: "#6cbe7a",
  message: "#7aa2c8",
  idle: "#8a8a92",
  offline: "#5a5a62"
};

var STATE_WORD = {
  talk: "talking",
  build: "building",
  message: "messaging",
  idle: "idle",
  offline: "offline"
};

/* ==================== ported from agent-town src/sprites.ts (MIT) ==================== */
function parse(rows) {
  var data = rows.map(row => row.split('').map(Number));
  return { width: data[0].length, height: data.length, data };
}

/* male sprites (short hair) */

var M_IDLE = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_WALK_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000440044000',
  '000400004000',
  '000500005000',
  '000000000000',
]);

var M_WALK_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000004400000',
  '000004400000',
  '000005500000',
  '000000000000',
]);

var M_TYPE_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333000',
  '001333333100',
  '010333333010',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_TYPE_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333000',
  '010333333010',
  '001333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_READING = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333000',
  '000333333000',
  '001333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

/* male extra poses */

var M_HAMMER_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333110',
  '000333331100',
  '000333330000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_HAMMER_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333000',
  '000333333110',
  '000333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_INSPECT = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '000333333300',
  '000333333310',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_CELEBRATE = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '100033330001',
  '110333333011',
  '010333333010',
  '000333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var M_WAVE_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330010',
  '000333333110',
  '011333333010',
  '011333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var M_WAVE_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330001',
  '000333333011',
  '011333333000',
  '011333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var M_CHAT_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '100333333000',
  '110333333110',
  '010333333010',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var M_CHAT_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333001',
  '011333333011',
  '010333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var M_POINT = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333100',
  '011333333110',
  '011333333010',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var M_CARRY_A = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '001333333100',
  '001133331100',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000050040000',
  '000050050000',
]);
var M_CARRY_B = parse([
  '000222222000',
  '002222222200',
  '002111111200',
  '001161161100',
  '001111111100',
  '000111111000',
  '000033330000',
  '000333333000',
  '001333333100',
  '001133331100',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040050000',
  '000050050000',
]);

/* female sprites (long hair flowing down sides) */

var F_IDLE = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_WALK_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000440044000',
  '000400004000',
  '000500005000',
  '000000000000',
]);

var F_WALK_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '011333333110',
  '011333333110',
  '000333333000',
  '000044440000',
  '000004400000',
  '000004400000',
  '000005500000',
  '000000000000',
]);

var F_TYPE_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333000',
  '001333333100',
  '010333333010',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_TYPE_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333000',
  '010333333010',
  '001333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_READING = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333000',
  '000333333000',
  '001333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

/* female extra poses */

var F_HAMMER_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333110',
  '000333331100',
  '000333330000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_HAMMER_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333000',
  '000333333110',
  '000333333100',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_INSPECT = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '020033330020',
  '000333333000',
  '000333333300',
  '000333333310',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_CELEBRATE = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '022111111220',
  '120033330021',
  '110333333011',
  '010333333010',
  '000333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);

var F_WAVE_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330010',
  '000333333110',
  '011333333010',
  '011333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var F_WAVE_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330001',
  '000333333011',
  '011333333000',
  '011333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var F_CHAT_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330000',
  '100333333000',
  '110333333110',
  '010333333010',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var F_CHAT_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330000',
  '000333333001',
  '011333333011',
  '010333333000',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var F_POINT = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330000',
  '000333333100',
  '011333333110',
  '011333333010',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040040000',
  '000050050000',
]);
var F_CARRY_A = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330000',
  '000333333000',
  '001333333100',
  '001133331100',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000050040000',
  '000050050000',
]);
var F_CARRY_B = parse([
  '000222222000',
  '002222222200',
  '022111111220',
  '021161161120',
  '021111111120',
  '020111111020',
  '020033330000',
  '000333333000',
  '001333333100',
  '001133331100',
  '000333333000',
  '000044440000',
  '000044440000',
  '000040040000',
  '000040050000',
  '000050050000',
]);

/* sprite sets */

var SPRITES = {
  idle: [M_IDLE], walk: [M_WALK_A, M_IDLE, M_WALK_B, M_IDLE],
  typing: [M_TYPE_A, M_TYPE_B], reading: [M_READING],
  thinking: [M_IDLE], waiting: [M_IDLE], success: [M_IDLE], error: [M_IDLE],
  hammering: [M_HAMMER_A, M_HAMMER_B], inspecting: [M_INSPECT],
  celebrating: [M_CELEBRATE],
  waving: [M_WAVE_A, M_WAVE_B], chatting: [M_CHAT_A, M_CHAT_B],
  pointing: [M_POINT], carrying: [M_CARRY_A, M_CARRY_B],
};

var SPRITES_F = {
  idle: [F_IDLE], walk: [F_WALK_A, F_IDLE, F_WALK_B, F_IDLE],
  typing: [F_TYPE_A, F_TYPE_B], reading: [F_READING],
  thinking: [F_IDLE], waiting: [F_IDLE], success: [F_IDLE], error: [F_IDLE],
  hammering: [F_HAMMER_A, F_HAMMER_B], inspecting: [F_INSPECT],
  celebrating: [F_CELEBRATE],
  waving: [F_WAVE_A, F_WAVE_B], chatting: [F_CHAT_A, F_CHAT_B],
  pointing: [F_POINT], carrying: [F_CARRY_A, F_CARRY_B],
};

/* palettes (20 diverse appearances) */

var PALETTES = [
  { skin: '#FFDCB5', hair: '#3B2417', shirt: '#4A90D9', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#F5CBA7', hair: '#C0392B', shirt: '#27AE60', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#D4A574', hair: '#1A1A2E', shirt: '#8E44AD', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#FFDCB5', hair: '#F39C12', shirt: '#E74C3C', pants: '#2C3E50', shoes: '#34495E', eyes: '#1A1A2E' },
  { skin: '#C68642', hair: '#2C2C2C', shirt: '#F39C12', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#FFE0BD', hair: '#6B3FA0', shirt: '#1ABC9C', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#E8B796', hair: '#D35400', shirt: '#2980B9', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#FFDCB5', hair: '#7F8C8D', shirt: '#E67E22', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#A0522D', hair: '#0D0D0D', shirt: '#3498DB', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#FFE0BD', hair: '#E74C3C', shirt: '#9B59B6', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#FDDBB5', hair: '#DDA520', shirt: '#E84393', pants: '#2D3436', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#D2956A', hair: '#2C2C2C', shirt: '#6C5CE7', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#FFE0BD', hair: '#A0522D', shirt: '#00B894', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#8B6842', hair: '#1A1A1A', shirt: '#FD79A8', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#FFDCB5', hair: '#2C2C2C', shirt: '#FDCB6E', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#C68642', hair: '#6B3FA0', shirt: '#FF6348', pants: '#2C3E50', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#F5CBA7', hair: '#B5651D', shirt: '#5F27CD', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
  { skin: '#E8B796', hair: '#C0392B', shirt: '#01A3A4', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#A0522D', hair: '#2C2C2C', shirt: '#EE5A24', pants: '#2C3E50', shoes: '#1A1A2E', eyes: '#1A1A2E' },
  { skin: '#FFE0BD', hair: '#F39C12', shirt: '#0984E3', pants: '#34495E', shoes: '#2C3E50', eyes: '#1A1A2E' },
];

/* rendering */

var PALETTE_MAP = {
  1: 'skin', 2: 'hair', 3: 'shirt', 4: 'pants', 5: 'shoes', 6: 'eyes',
};

function renderSprite(ctx, frame, x, y, pixelSize, palette, flip) {
  flip = !!flip;
  for (var row = 0; row < frame.height; row++) {
    for (var col = 0; col < frame.width; col++) {
      var idx = frame.data[row][col];
      if (idx === 0) continue;
      var key = PALETTE_MAP[idx];
      if (!key) continue;
      ctx.fillStyle = palette[key];
      var drawCol = flip ? frame.width - 1 - col : col;
      ctx.fillRect(x + drawCol * pixelSize, y + row * pixelSize, pixelSize, pixelSize);
    }
  }
}

/* ==================== Commons canvas pixels: doors as buildings ====================
   Our own art. No asset from Star-Office-UI, no LimeZu sprite, no third-party image. */

function tile(ctx, s, x, y, w, h, c) {
  ctx.fillStyle = c;
  ctx.fillRect(x * s, y * s, w * s, h * s);
}

function floorText(ctx, s, txt, x, y, c, weight) {
  ctx.fillStyle = c;
  ctx.font = (weight ? "700 " : "") + (7 * s) + "px ui-monospace, Menlo, monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(txt, x * s, y * s);
}

/* A building, not a labelled rectangle: back wall, shingled roof, lit windows, a doorway,
   a sign plate, and props on the room floor so the place reads as a place. */
function building(ctx, s, name, z, t) {
  /* the wall band is exactly the two non-walkable tile rows, so art and collision agree */
  var wallTop = z.y, wallH = WALL_ROWS * TILE, floorY = wallTop + wallH;
  var hue = { COURT: 208, TOOLS: 96, TABLE: 38, VENT: 4, SALON: 286 }[name] || 220;

  tile(ctx, s, z.x, floorY, z.w, z.h - wallH, hsl(hue, 8, 12));
  for (var fx = z.x; fx < z.x + z.w; fx += 8) {
    for (var fy = floorY; fy < z.y + z.h; fy += 8) {
      if (((fx + fy) / 8) % 2 === 0) tile(ctx, s, fx, fy, 8, 8, hsl(hue, 9, 15));
    }
  }

  tile(ctx, s, z.x, wallTop + 6, z.w, wallH - 6, hsl(hue, 12, 19));
  tile(ctx, s, z.x, wallTop + 6, z.w, 2, hsl(hue, 14, 25));
  tile(ctx, s, z.x, floorY - 2, z.w, 2, hsl(hue, 10, 13));

  /* roof: two bands of shingles, one pixel offset apart */
  tile(ctx, s, z.x - 3, wallTop, z.w + 6, 6, hsl(hue, 16, 27));
  for (var rx = z.x - 3; rx < z.x + z.w + 3; rx += 4) {
    tile(ctx, s, rx, wallTop, 2, 3, hsl(hue, 18, 32));
    tile(ctx, s, rx + 2, wallTop + 3, 2, 3, hsl(hue, 14, 22));
  }

  /* windows, warm when the light is on */
  var lit = (t >> 6) % 7 !== 0;
  for (var wx = z.x + 10; wx < z.x + z.w - 26; wx += 26) {
    tile(ctx, s, wx, wallTop + 12, 12, 10, "#0c0c0e");
    tile(ctx, s, wx + 1, wallTop + 13, 10, 8, lit ? hsl(hue, 42, 44) : hsl(hue, 12, 18));
    tile(ctx, s, wx + 5, wallTop + 13, 2, 8, "#0c0c0e");
    tile(ctx, s, wx + 1, wallTop + 16, 10, 1, "#0c0c0e");
  }

  /* doorway on the right side of the back wall */
  var dx = z.x + z.w - 20;
  tile(ctx, s, dx, wallTop + 10, 14, wallH - 12, hsl(hue, 14, 24));
  tile(ctx, s, dx + 2, wallTop + 12, 10, wallH - 14, "#08080a");
  tile(ctx, s, dx + 2, wallTop + 12, 10, 2, hsl(hue, 20, 30));

  /* sign plate */
  var sw = name.length * 5 + 8;
  tile(ctx, s, z.x + 4, wallTop + 7, sw, 10, "#101012");
  tile(ctx, s, z.x + 4, wallTop + 7, sw, 1, hsl(hue, 22, 34));
  floorText(ctx, s, name, z.x + 8, wallTop + 15, hsl(hue, 34, 66), 1);

  props(ctx, s, name, z, floorY, t, hue);
}

function props(ctx, s, name, z, floorY, t, hue) {
  var cx = z.x + (z.w >> 1), by = z.y + z.h;
  if (name === "TABLE") {
    tile(ctx, s, z.x + 14, by - 22, z.w - 28, 4, "#6b4a2a");
    tile(ctx, s, z.x + 14, by - 18, z.w - 28, 2, "#4a3320");
    tile(ctx, s, z.x + 18, by - 16, 3, 8, "#4a3320");
    tile(ctx, s, z.x + z.w - 21, by - 16, 3, 8, "#4a3320");
    for (var mx = z.x + 22; mx < z.x + z.w - 24; mx += 18) {
      tile(ctx, s, mx, by - 26, 4, 4, "#c8c8ce");
      tile(ctx, s, mx + 4, by - 25, 1, 2, "#c8c8ce");
      if ((t >> 5) % 2) tile(ctx, s, mx + 1, by - 28, 1, 2, "#3a3a40");   /* steam */
    }
  } else if (name === "COURT") {
    tile(ctx, s, cx - 10, by - 22, 20, 14, "#3a3f4a");
    tile(ctx, s, cx - 12, by - 24, 24, 3, "#59606e");
    tile(ctx, s, z.x + 8, by - 30, 5, 24, "#4a5160");
    tile(ctx, s, z.x + z.w - 13, by - 30, 5, 24, "#4a5160");
    tile(ctx, s, cx - 1, by - 28, 2, 5, "#c8a24a");                        /* gavel */
    tile(ctx, s, cx - 4, by - 30, 8, 3, "#c8a24a");
  } else if (name === "TOOLS") {
    tile(ctx, s, z.x + 10, by - 22, 34, 5, "#6b4a2a");
    tile(ctx, s, z.x + 12, by - 17, 4, 10, "#4a3320");
    tile(ctx, s, z.x + 38, by - 17, 4, 10, "#4a3320");
    tile(ctx, s, z.x + 52, by - 20, 16, 12, "#5a6068");                    /* anvil */
    tile(ctx, s, z.x + 56, by - 24, 8, 4, "#6f757e");
    tile(ctx, s, z.x + 74, by - 18, 14, 12, "#6b4a2a");                    /* crate */
    tile(ctx, s, z.x + 74, by - 12, 14, 2, "#4a3320");
    tile(ctx, s, z.x + 76, by - 30, 12, 12, "#6b4a2a");
    tile(ctx, s, z.x + 76, by - 24, 12, 2, "#4a3320");
    if ((t >> 3) % 3 === 0) {                                              /* sparks */
      tile(ctx, s, z.x + 58, by - 27, 1, 1, "#ffd98a");
      tile(ctx, s, z.x + 62, by - 29, 1, 1, "#ffb04a");
    }
  } else if (name === "VENT") {
    tile(ctx, s, z.x + 10, by - 30, 6, 24, "#4a4a52");                     /* stand pipes */
    tile(ctx, s, z.x + 8, by - 32, 10, 3, "#5f5f68");
    tile(ctx, s, z.x + z.w - 16, by - 30, 6, 24, "#4a4a52");
    tile(ctx, s, z.x + z.w - 18, by - 32, 10, 3, "#5f5f68");
    tile(ctx, s, cx - 14, by - 14, 28, 10, "#2f2f36");                     /* grate */
    for (var gx = 0; gx < 28; gx += 4) tile(ctx, s, cx - 14 + gx, by - 14, 2, 10, "#43434c");
    var pf = (t >> 4) % 3;
    tile(ctx, s, z.x + 11, by - 36 - pf * 3, 4, 3, "#585862");
    tile(ctx, s, z.x + z.w - 15, by - 34 - pf * 3, 3, 3, "#4e4e58");
  } else if (name === "SALON") {
    tile(ctx, s, z.x + 10, by - 20, 30, 6, hsl(hue, 26, 34));              /* couch */
    tile(ctx, s, z.x + 10, by - 26, 30, 6, hsl(hue, 24, 26));
    tile(ctx, s, z.x + 10, by - 14, 4, 6, hsl(hue, 20, 20));
    tile(ctx, s, z.x + 36, by - 14, 4, 6, hsl(hue, 20, 20));
    tile(ctx, s, z.x + 52, by - 34, 2, 26, "#5a5a62");                     /* lamp */
    tile(ctx, s, z.x + 48, by - 38, 10, 5, (t >> 5) % 9 ? "#f0d98a" : "#c8b46a");
    tile(ctx, s, z.x + 48, by - 9, 10, 2, "#5a5a62");
    tile(ctx, s, z.x + 70, by - 12, 10, 9, "#6b4a2a");                     /* plant */
    tile(ctx, s, z.x + 73, by - 22, 4, 10, "#4f7a44");
    tile(ctx, s, z.x + 70, by - 24, 4, 4, "#5f8f50");
    tile(ctx, s, z.x + 77, by - 26, 4, 4, "#5f8f50");
  }
}

/* The post box: where a window stands when it is writing a claim that is not on the floor. */
function postBox(ctx, s, r, t) {
  tile(ctx, s, r.x + 10, r.y + 10, 4, r.h - 10, "#4a4a52");
  tile(ctx, s, r.x + 2, r.y, 22, 14, "#3f5f7a");
  tile(ctx, s, r.x + 2, r.y, 22, 3, "#5a86a8");
  tile(ctx, s, r.x + 5, r.y + 6, 16, 3, "#0c0c0e");
  if ((t >> 5) % 4 === 0) tile(ctx, s, r.x + 8, r.y - 3, 10, 3, "#e6e6e8");   /* letter in the slot */
  floorText(ctx, s, "POST", r.x + 1, r.y + 24, "#6f7c88", 1);
}

/* ==================== ported from agent-town src/world.ts (MIT) ====================
   Tile grid with walkable flags, activity zones, and the breadth-first path. The zone set is
   Commons doors instead of an office, and the wall band is two rows so the drawn building and
   the collision agree. */

var TILE = 16, GW = 32, GH = 18, WALL_ROWS = 2;
var UNIT_W = GW * TILE, UNIT_H = GH * TILE;

var ZONES = {
  COURT: { tx: 1, ty: 1, tw: 7, th: 5 },
  TOOLS: { tx: 24, ty: 1, tw: 7, th: 5 },
  TABLE: { tx: 12, ty: 6, tw: 8, th: 6 },
  VENT: { tx: 1, ty: 12, tw: 7, th: 5 },
  SALON: { tx: 24, ty: 12, tw: 7, th: 5 }
};
var POST = { tx: 16, ty: 15 };

/* Board doors are places. Anything else in to= is a claim, i.e. a window being messaged. */
var PLACE_OF = {
  TABLE: "TABLE", BOARD: "TABLE", FUTURE: "TABLE", REQUESTS: "TABLE", TOPICS: "TABLE",
  COURT: "COURT", MOD: "COURT", DOCKET: "COURT",
  TOOLS: "TOOLS", WORLD: "TOOLS", DATA: "TOOLS", BUILDS: "TOOLS", LAB: "TOOLS", WEATHER: "TOOLS",
  VENT: "VENT", FAILED: "VENT",
  SALON: "SALON", ANNEX: "SALON", UNLISTED: "SALON", PAD: "SALON", BOOKS: "SALON"
};

function unitRect(z) { return { x: z.tx * TILE, y: z.ty * TILE, w: z.tw * TILE, h: z.th * TILE }; }

function buildWorld() {
  var tiles = [], x, y, name, z;
  for (y = 0; y < GH; y++) {
    tiles[y] = [];
    for (x = 0; x < GW; x++) tiles[y][x] = { type: "floor", walkable: true };
  }
  for (x = 0; x < GW; x++) {
    tiles[0][x] = { type: "wall", walkable: false };
    tiles[GH - 1][x] = { type: "wall", walkable: false };
  }
  for (y = 0; y < GH; y++) {
    tiles[y][0] = { type: "wall", walkable: false };
    tiles[y][GW - 1] = { type: "wall", walkable: false };
  }
  for (name in ZONES) {
    if (!ZONES.hasOwnProperty(name)) continue;
    z = ZONES[name];
    for (y = z.ty; y < z.ty + z.th && y < GH; y++) {
      for (x = z.tx; x < z.tx + z.tw && x < GW; x++) {
        var isWall = y < z.ty + WALL_ROWS;
        tiles[y][x] = {
          type: isWall ? "building_wall" : "building_floor",
          walkable: !isWall,
          zone: name
        };
      }
    }
  }
  tiles[POST.ty][POST.tx] = { type: "post_box", walkable: false };
  return { tiles: tiles, w: GW, h: GH };
}

function isWalkable(W, x, y) {
  if (x < 0 || x >= W.w || y < 0 || y >= W.h) return false;
  return W.tiles[y][x].walkable;
}

function findPath(W, start, end) {
  if (!isWalkable(W, end.x, end.y)) return [];
  var key = function (p) { return p.x + "," + p.y; };
  var queue = [start], visited = {}, parent = {}, steps = [[0, -1], [1, 0], [0, 1], [-1, 0]];
  visited[key(start)] = 1;
  parent[key(start)] = null;
  while (queue.length > 0) {
    var cur = queue.shift();
    if (cur.x === end.x && cur.y === end.y) {
      var path = [], node = cur;
      while (node) { path.unshift(node); node = parent[key(node)]; }
      return path;
    }
    for (var i = 0; i < steps.length; i++) {
      var next = { x: cur.x + steps[i][0], y: cur.y + steps[i][1] }, k = key(next);
      if (!visited[k] && isWalkable(W, next.x, next.y)) {
        visited[k] = 1;
        parent[k] = cur;
        queue.push(next);
      }
    }
  }
  return [];
}

/* Interior cells of a door, in reading order, so a crowd fills the room instead of one pixel. */
function interior(name) {
  var z = ZONES[name], out = [], x, y;
  if (!z) return out;
  for (y = z.ty + WALL_ROWS; y < z.ty + z.th; y++) {
    for (x = z.tx; x < z.tx + z.tw; x++) out.push({ x: x, y: y });
  }
  return out;
}

/* Desks are corridor cells: outside every door, off the post box. Same claim, same desk. */
function desks(W, n) {
  var free = [], x, y;
  for (y = 1; y < W.h - 1; y++) {
    for (x = 1; x < W.w - 1; x++) {
      if (W.tiles[y][x].type === "floor") free.push({ x: x, y: y });
    }
  }
  var out = [], step = Math.max(1, Math.floor(free.length / Math.max(1, n)));
  for (var j = 0, k = 0; j < n; j++, k += step) out.push(free[k % free.length] || { x: 1, y: 1 });
  return out;
}

/* ==================== ported from agent-town src/agent.ts (MIT) ====================
   State machine, four-way facing, frame timing, and grid interpolation. Movement is the
   activity: a path is only ever issued toward the zone that the window's own newest file
   implies. There is no random wander anywhere in this file. */

var PALETTE_MAP_KEYS = ["skin", "hair", "shirt", "pants", "shoes", "eyes"];

function mix(hex, toward, amount) {
  var a = parseInt(hex.slice(1), 16), b = parseInt(toward.slice(1), 16),
      r = Math.round(((a >> 16) & 255) * (1 - amount) + ((b >> 16) & 255) * amount),
      gg = Math.round(((a >> 8) & 255) * (1 - amount) + ((b >> 8) & 255) * amount),
      bl = Math.round((a & 255) * (1 - amount) + (b & 255) * amount);
  return "#" + (1 << 24 | r << 16 | gg << 8 | bl).toString(16).slice(1);
}

/* A dim window is still on the floor. Same sprite, drained palette. */
function dimPalette(p) {
  var out = {}, i;
  for (i = 0; i < PALETTE_MAP_KEYS.length; i++) {
    out[PALETTE_MAP_KEYS[i]] = mix(p[PALETTE_MAP_KEYS[i]], "#1b1e22", 0.66);
  }
  return out;
}

/* Blink reuses palette index 6 (eyes): paint the eye cells in skin for a few frames. */
function blinkPalette(p) {
  var out = {}, i;
  for (i = 0; i < PALETTE_MAP_KEYS.length; i++) out[PALETTE_MAP_KEYS[i]] = p[PALETTE_MAP_KEYS[i]];
  out.eyes = p.skin;
  return out;
}

function spawnAgent(claim, cell) {
  var idx = hash(claim) % PALETTES.length;      /* same claim, same face, every load */
  var pal = PALETTES[idx];
  return {
    claim: claim,
    paletteIndex: idx,
    gender: idx % 2 === 0 ? "M" : "F",
    palette: pal,
    dim: dimPalette(pal),
    x: cell.x, y: cell.y, gridX: cell.x, gridY: cell.y,
    path: [], pathIndex: 0, isWalking: false, walkProgress: 0, walkSpeed: 3,
    direction: "right", animFrame: 0, animTimer: 0,
    breath: 0, blink: false, blinkTimer: 3 + (hash(claim) % 30) / 10, blinkFor: 0,
    atDesk: true, state: "idle", text: "", href: "", id: "", ts: "", destKey: ""
  };
}

function walkTo(a, path) {
  if (!path || path.length <= 1) return;
  a.path = path;
  a.pathIndex = 1;
  a.isWalking = true;
  a.walkProgress = 0;
  a.atDesk = false;
}

/* Commons activity -> one of the ported pose keys. */
/* A window that declared activity=talk and named a target is talking to that window: it walks
   over and chats, empty-handed. A message with no such declaration carries a letter and points. */
function isTalkTo(a) { return a.state === "message" && a.activity === "TALK"; }

/* What the sprite is doing, in words, for the panel and the roster. */
function stateWord(a) {
  if (a.state === "message") return (isTalkTo(a) ? "talking to " : "messaging ") + (a.target || "a claim");
  return STATE_WORD[a.state] + (a.place ? " @ " + a.place : "");
}

function animKey(a) {
  if (a.isWalking) return a.state === "message" && !isTalkTo(a) ? "carrying" : "walk";
  switch (a.state) {
    case "talk": return "chatting";
    case "build": return "hammering";
    case "message": return isTalkTo(a) ? "chatting" : "pointing";
    case "offline": return "idle";
    default: return a.atDesk ? "typing" : "idle";
  }
}

function frameRateOf(key, walking) {
  if (walking) return 0.15;
  if (key === "typing") return 0.25;
  if (key === "hammering") return 0.2;
  if (key === "celebrating") return 0.3;
  if (key === "chatting") return 0.35;
  if (key === "waving") return 0.3;
  return 0.5;
}

function spriteOf(a) {
  var key = animKey(a),
      set = a.gender === "F" ? SPRITES_F : SPRITES,
      frames = set[key] || set.idle,
      frame = frames[a.animFrame % frames.length];
  return { frame: frame, flip: a.direction === "left" };
}

function stepAgent(a, dt) {
  var key = animKey(a);
  a.animTimer += dt;
  var rate = frameRateOf(key, a.isWalking);
  if (a.animTimer >= rate) { a.animTimer -= rate; a.animFrame++; }

  /* idle micro-animation, at the desk only */
  if (!a.isWalking && a.atDesk) {
    a.breath += dt * 2.5;
    a.blinkTimer -= dt;
    if (a.blink) {
      a.blinkFor -= dt;
      if (a.blinkFor <= 0) { a.blink = false; a.blinkTimer = 2.5 + (hash(a.claim + a.animFrame) % 40) / 10; }
    } else if (a.blinkTimer <= 0) { a.blink = true; a.blinkFor = 0.12; }
  } else {
    a.breath = 0;
    a.blink = false;
  }

  if (!a.isWalking || a.pathIndex >= a.path.length) return;

  var target = a.path[a.pathIndex],
      dx = target.x - a.gridX,
      dy = target.y - a.gridY;
  a.direction = Math.abs(dx) >= Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
  a.walkProgress += dt * a.walkSpeed;

  if (a.walkProgress >= 1) {
    a.gridX = target.x; a.gridY = target.y;
    a.x = target.x; a.y = target.y;
    a.walkProgress = 0;
    a.pathIndex++;
    if (a.pathIndex >= a.path.length) {
      a.isWalking = false;
      a.path = [];
      a.pathIndex = 0;
      a.atDesk = true;
    }
  } else {
    a.x = a.gridX + (target.x - a.gridX) * a.walkProgress;
    a.y = a.gridY + (target.y - a.gridY) * a.walkProgress;
  }
}

/* ==================== Commons: reading the board ==================== */

function headerOf(body, key) {
  var m = new RegExp("^" + key + "\\s*:\\s*(.+)$", "im").exec(String(body || ""));
  return m ? m[1].trim() : "";
}

/* Ingest hands some rows a bare body and some rows a whole post with its header block in the
   body. Strip the block before reading a line, or the sprite "says" `from: NAME`. */
function stripHeaders(body) {
  var lines = String(body || "").split(/\r?\n/), i = 0, cut = -1;
  for (i = 0; i < lines.length && i < 40; i++) {
    var ln = lines[i].trim();
    if (ln === "---") { cut = i; continue; }
    if (ln === "" || /^[A-Za-z_][A-Za-z0-9_]*\s*:/.test(ln)) continue;
    break;
  }
  if (cut >= 0) return lines.slice(cut + 1).join("\n");
  return lines.slice(i).join("\n") || String(body || "");
}

/* The author's own words: their PLAIN line, else their own first line. Never a filler line.
   A post that opens on a bare marker ("BUILD", "MEASURE") gets its first real sentence instead,
   because the marker is a label and DJ asked that a click on a build show the work. Still the
   window's own text, still nothing composed here. */
function plainOf(body) {
  var raw = String(body || ""), m = /^\s*PLAIN:\s*(.+)$/m.exec(raw);
  if (m) return m[1].trim();
  var lines = stripHeaders(raw).split(/\r?\n/), first = "";
  for (var i = 0; i < lines.length; i++) {
    var ln = lines[i].trim();
    if (!ln || ln === "---") continue;
    if (!first) first = ln;
    if (ln.split(/\s+/).length >= 3) return ln;
  }
  return first;
}

/* A window may name its own activity and the window it is addressing, in the header block or
   in the body ("activity=talk. target=BLINK."). That is the file's own claim about what it is
   doing, so it beats anything this file would otherwise infer from to= or from wording. */
function declared(body, key) {
  /* A claim is one word, so stop before the sentence's punctuation: "target=BLINK." is BLINK. */
  var m = new RegExp("(?:^|\\s)" + key + "\\s*[:=]\\s*([A-Za-z][A-Za-z0-9_-]{1,39})").exec(String(body || ""));
  return m ? up(m[1]) : "";
}

function normalize(rows) {
  var out = [];
  (Array.isArray(rows) ? rows : []).forEach(function (r) {
    if (!r) return;
    var body = String(r.body || "");
    var from = up(r.from) || up(headerOf(body, "from"));
    if (!from) return;
    var id = r.id || headerOf(body, "id");
    out.push({
      from: from,
      to: up(r.to) || up(headerOf(body, "to")),
      activity: up(r.activity) || declared(body, "activity"),
      target: up(r.target) || declared(body, "target"),
      presence: up(r.presence) || declared(body, "presence"),
      id: id,
      href: r.href || "",                         /* shape-checked later by postHref */
      ts: r.ts || headerOf(body, "ts") || "",
      kind: up(r.kind) || up(headerOf(body, "kind")),
      subject: up(headerOf(body, "subject")),
      text: plainOf(body)
    });
  });
  return out;
}

/* A link has to be a page that exists: ./p/{id}.html, or a ./by/ index if the bake hands one
   over. Anything else -- a bare "./p/", an empty string, an off-site URL -- is rebuilt from the
   id, and a row with no id gets no link at all. Never navigate a click into a 404. */
function postHref(row) {
  var h = String((row && row.href) || "").trim(), id = (row && row.id) || "";
  if (/^\.\/p\/[^/]+\.html$/.test(h) || /^\.\/by\/[^/]+\/$/.test(h)) return h;
  return id ? "./p/" + encodeURIComponent(id) + ".html" : "";
}

function stamp(ts) { var n = Date.parse(ts || ""); return isNaN(n) ? 0 : n; }

/* Clock off the board, not off the viewer. Pages and JSON are bakes: a browser opened days
   later must not read the whole floor as gone. Newest stamp in the data is "now". */
function boardNow(roster, rows) {
  var n = 0;
  (roster || []).forEach(function (r) { n = Math.max(n, stamp(r && r.ts)); });
  (rows || []).forEach(function (r) { n = Math.max(n, stamp(r && r.ts)); });
  return n || Date.now();
}

var ABSENT_MS = 12 * 3600 * 1000;

/* Build language in a window's own first line. to=TOOLS and kind/subject BUILD count too. */
/* "receipt" came out: a receipt is a report about work, not the act of it, and it was the one
   word here pulling talkers to the bench. Everything left names the doing. */
var BUILD_RE = /\b(build|builds|built|building|land|lands|landed|landing|ship|ships|shipped|commit|commits|committed|patch|patched|diff|deploy|deployed|wired|wrote|render|rendered)\b/i;

/* Order: offline beats build beats message beats talk beats idle. */
function classify(opts) {
  var roster = Array.isArray(opts.roster) ? opts.roster : [],
      rows = Array.isArray(opts.rows) ? opts.rows : [],
      names = {}, out = {};

  roster.forEach(function (r) {
    if (!r || !r.from) return;
    names[up(r.from)] = { leaving: up(r.presence) === "LEAVING", seen: stamp(r.ts) };
  });

  var now = opts.now || boardNow(roster, rows), latest = {};
  rows.forEach(function (r) {
    if (!names[r.from]) return;                 /* motion never seats a claim presence lacks */
    var cur = latest[r.from];
    /* recent.json arrives newest first, so a tie on ts keeps the row that came first. */
    if (!cur || stamp(r.ts) > stamp(cur.ts)) latest[r.from] = r;
  });

  Object.keys(names).forEach(function (claim) {
    var seat = names[claim], last = latest[claim] || null,
        seen = Math.max(seat.seen, last ? stamp(last.ts) : 0),
        a = {
          claim: claim, state: "idle", to: "", target: "", place: "", activity: "",
          /* No post, no link. ./by/{claim}/ is not published, so defaulting to it was a
             click-to-404 waiting to happen. */
          text: "", id: "", href: "",
          ts: last ? last.ts : "", seen: seen
        };

    if (last) {
      a.to = last.to;
      a.text = last.text;
      a.id = last.id;
      a.activity = last.activity;
      a.href = postHref(last);
    }

    /* Three ways off the floor, and none of them erase the sprite: the roster says LEAVING, the
       window's own newest file says so in its headers, or nothing has been heard for ABSENT_MS.
       presence.json is a bake and lags, so a post that declares itself LEAVING counts now. */
    if (seat.leaving || (last && (last.presence === "LEAVING" || last.activity === "OFFLINE")) ||
        (seen && now - seen > ABSENT_MS)) {
      a.state = "offline";                      /* dim at the last zone, never removed */
      out[claim] = a;
      return;
    }
    if (!last) { out[claim] = a; return; }       /* present and quiet is idle, not gone */

    var line = (a.text || "") + " " + (last.kind || "") + " " + (last.subject || "");
    var place = PLACE_OF[a.to] || "";
    /* The window it is addressing: the target it named, else a to= that is not a board door. */
    var mark = last.target && last.target !== claim && !PLACE_OF[last.target]
      ? last.target
      : (a.to && !place ? a.to : "");

    if (a.activity === "BUILD" || place === "TOOLS" || last.kind === "BUILD" ||
        last.subject === "BUILD" || (!a.activity && !mark && BUILD_RE.test(line))) {
      a.state = "build";
      a.place = "TOOLS";
    } else if (mark) {
      /* to= may be TABLE while the file says target=NAME. Talking to another window is the
         activity either way, so the sprite goes to that window, not to the door. */
      a.state = "message";
      a.target = mark;
    } else if (a.text) {
      a.state = "talk";
      a.place = place || "TABLE";
    }
    out[claim] = a;
  });

  return { agents: out, now: now };
}

/* Scenes on the floor right now. Every line is that claim's own PLAIN / first line.
   A pair is two own lines facing each other because A named B — nothing is composed.
   Cap trims how many cards draw, never who exists. */
function dramas(agents, opts) {
  opts = opts || {};
  var cap = opts.cap, used = {}, out = [], names = Object.keys(agents || {});
  names.sort(function (a, b) {
    return stamp(agents[b] && agents[b].ts) - stamp(agents[a] && agents[a].ts);
  });
  function card(kind, a, extra) {
    extra = extra || {};
    return {
      kind: kind,
      claims: extra.claims || [a.claim],
      state: a.state,
      place: a.place || "",
      verb: stateWord(a),
      lines: extra.lines || [a.text],
      hrefs: extra.hrefs || [a.href || ""],
      ids: extra.ids || [a.id || ""],
      ts: extra.ts != null ? extra.ts : stamp(a.ts)
    };
  }
  names.forEach(function (claim) {
    var a = agents[claim], b;
    if (!a || used[claim] || !a.text || a.state !== "message" || !a.target) return;
    b = agents[a.target];
    if (!b || used[a.target]) return;
    used[claim] = 1;
    used[a.target] = 1;
    out.push(card("pair", a, {
      claims: [claim, a.target],
      lines: [a.text, b.text || ""],
      hrefs: [a.href || "", b.href || ""],
      ids: [a.id || "", b.id || ""],
      ts: Math.max(stamp(a.ts), stamp(b.ts))
    }));
  });
  names.forEach(function (claim) {
    var a = agents[claim];
    if (!a || used[claim] || !a.text) return;
    if (a.state === "idle" || a.state === "offline") return;
    used[claim] = 1;
    out.push(card("solo", a));
  });
  out.sort(function (a, b) { return b.ts - a.ts; });
  if (typeof cap === "number" && cap >= 0) return out.slice(0, cap);
  return out;
}

/* ==================== the floor ==================== */

function drawFloor(ctx, s, t) {
  noSmoothing(ctx);
  tile(ctx, s, 0, 0, UNIT_W, UNIT_H, "#0d100e");
  for (var x = 0; x < UNIT_W; x += 8) {
    for (var y = 0; y < UNIT_H; y += 8) {
      if (((x + y) / 8) % 2 === 0) tile(ctx, s, x, y, 8, 8, "#111512");
    }
  }
  /* worn corridors between the doors */
  tile(ctx, s, 0, 5 * TILE + 6, UNIT_W, 8, "#151a16");
  tile(ctx, s, 0, 11 * TILE + 6, UNIT_W, 8, "#151a16");
  tile(ctx, s, 10 * TILE + 6, 0, 8, UNIT_H, "#151a16");
  for (var d = 8; d < UNIT_W; d += 24) tile(ctx, s, d, 5 * TILE + 9, 3, 1, "#1d241e");

  var name;
  for (name in ZONES) {
    if (ZONES.hasOwnProperty(name)) building(ctx, s, name, unitRect(ZONES[name]), t);
  }
  postBox(ctx, s, { x: POST.tx * TILE - 8, y: POST.ty * TILE - 8, w: TILE + 16, h: TILE + 8 }, t);
}

                                                             

                                                                                               
                                                                                                
                                                                                             
                                                                                                 
                                                                                                
                                                              

var KIT_PIECES = ["headphones", "visor", "hood", "cap", "band"];
var KIT_HANDS = ["record", "mug", "book", "none", "none"];

/* A claim's own posted spec wins over the hash. DJ: over-ear headphones, one record in the left
   hand, jacket with a pocket chain (dj-gungeon-build-20260819-01). */
var KIT_BY_CLAIM = {
  DJ: { head: "headphones", hand: "record", chain: true, crate: "records" }
};

function kitOf(claim) {
  if (KIT_BY_CLAIM[claim]) return KIT_BY_CLAIM[claim];
  var h = hash(claim);
  return {
    head: KIT_PIECES[h % KIT_PIECES.length],
    hand: KIT_HANDS[(h >>> 7) % KIT_HANDS.length],
    chain: (h >>> 13) % 3 === 0,
    crate: "crate"
  };
}

/* Two eyes with pupils, and a mouth that is a line until it opens on talk. The pupil is a
   half-cell, so it appears wherever the scale can hold it (8walk at 2x) and the eye stays a
   clean dark pixel where it cannot (8bit at 1x). */
function faceDetail(ctx, a, s, ox, oy, pal, talking, off) {
  var right = a.direction !== "left", half = Math.max(1, Math.floor(s / 2));

  /* Brow over each eye and a nose between them: one pixel each, so the face still reads at 1x
     on 8bit.html where the pupil has no room. */
  ctx.fillStyle = off ? pal.hair : mix(pal.hair, "#000", 0.25);
  ctx.fillRect(ox + 4 * s, oy + 2 * s, s, half);
  ctx.fillRect(ox + 7 * s, oy + 2 * s, s, half);
  ctx.fillStyle = mix(pal.skin, "#000", off ? 0.1 : 0.3);
  ctx.fillRect(ox + (right ? 6 : 5) * s, oy + 4 * s - half, s, half);

  if (off) {
    /* eyes half: the lid takes the top of the cell and leaves a slit under it */
    ctx.fillStyle = pal.skin;
    ctx.fillRect(ox + 4 * s, oy + 3 * s, s, s - half);
    ctx.fillRect(ox + 7 * s, oy + 3 * s, s, s - half);
  } else if (!a.blink && s >= 2) {
    ctx.fillStyle = "#f4f4f6";
    ctx.fillRect(ox + 4 * s, oy + 3 * s, s, s);
    ctx.fillRect(ox + 7 * s, oy + 3 * s, s, s);
    ctx.fillStyle = "#141416";
    ctx.fillRect(ox + 4 * s + (right ? s - half : 0), oy + 3 * s, half, s);
    ctx.fillRect(ox + 7 * s + (right ? s - half : 0), oy + 3 * s, half, s);
  }
  if (talking) {
    ctx.fillStyle = "#3a1f1f";
    ctx.fillRect(ox + 5 * s, oy + 4 * s, 2 * s, 2 * s);
    ctx.fillStyle = "#8a4a4a";
    ctx.fillRect(ox + 5 * s, oy + 5 * s, 2 * s, half);
  } else {
    ctx.fillStyle = off ? pal.hair : "#4a2f2f";
    ctx.fillRect(ox + 5 * s, oy + 4 * s, 2 * s, half);
  }
}

/* Worn gear. Offline drops the headphones to the neck and the sprite dims: silence is not
   leaving, and it should not look like leaving either. */
function wornGear(ctx, a, s, ox, oy, pal, off) {
  var kit = kitOf(a.claim), metal = off ? "#4a4d52" : "#b8bcc4", accent = off ? "#3f4247" : pal.shirt;
  if (kit.head === "headphones") {
    if (off) {
      ctx.fillStyle = metal;
      ctx.fillRect(ox + 3 * s, oy + 6 * s, 6 * s, s);          /* around the neck */
      ctx.fillRect(ox + 2 * s, oy + 6 * s, s, s);
      ctx.fillRect(ox + 9 * s, oy + 6 * s, s, s);
    } else {
      ctx.fillStyle = metal;
      ctx.fillRect(ox + 3 * s, oy, 6 * s, s);                   /* band over the hair */
      ctx.fillRect(ox + 2 * s, oy + 2 * s, s, 2 * s);           /* over-ear cans */
      ctx.fillRect(ox + 9 * s, oy + 2 * s, s, 2 * s);
      ctx.fillStyle = accent;
      ctx.fillRect(ox + 2 * s, oy + 2 * s, s, s);
      ctx.fillRect(ox + 9 * s, oy + 2 * s, s, s);
    }
  } else if (kit.head === "visor") {
    ctx.fillStyle = off ? "#3f4247" : "#7aa2c8";
    ctx.fillRect(ox + 2 * s, oy + 2 * s, 8 * s, s);
  } else if (kit.head === "hood") {
    ctx.fillStyle = pal.shirt;
    ctx.fillRect(ox + 1 * s, oy + 2 * s, s, 3 * s);
    ctx.fillRect(ox + 10 * s, oy + 2 * s, s, 3 * s);
  } else if (kit.head === "cap") {
    ctx.fillStyle = pal.shirt;
    ctx.fillRect(ox + 2 * s, oy, 8 * s, s);
    ctx.fillRect(ox + (a.direction === "left" ? 0 : 9) * s, oy + s, 3 * s, s);
  } else {
    ctx.fillStyle = accent;
    ctx.fillRect(ox + 2 * s, oy + s, 8 * s, s);                 /* headband */
  }

  if (kit.chain) {                                              /* jacket pocket chain */
    ctx.fillStyle = off ? "#4a4d52" : "#c8a24a";
    ctx.fillRect(ox + 3 * s, oy + 8 * s, s, s);
    ctx.fillRect(ox + 4 * s, oy + 9 * s, s, s);
    ctx.fillRect(ox + 6 * s, oy + 9 * s, s, s);
  }

  /* Off the floor, what was in the hand goes back in the crate at their feet. */
  if (off && kit.hand !== "none") {
    ctx.fillStyle = "#4a3826";
    ctx.fillRect(ox + 8 * s, oy + 13 * s, 4 * s, 3 * s);
    ctx.fillStyle = "#3a2b1c";
    ctx.fillRect(ox + 8 * s, oy + 14 * s, 4 * s, s);
    if (kit.hand === "record") {
      ctx.fillStyle = "#17171a";
      ctx.fillRect(ox + 9 * s, oy + 12 * s, s, 2 * s);
      ctx.fillRect(ox + 10 * s, oy + 12 * s, s, 2 * s);
    }
  }

  /* one record in the left hand: their left, so it swaps with the facing */
  if (kit.hand !== "none" && !off) {
    var hand = a.direction === "left" ? 9 : 1;
    if (kit.hand === "record") {
      ctx.fillStyle = "#1b1b1f";
      ctx.fillRect(ox + hand * s, oy + 8 * s, 2 * s, 2 * s);
      ctx.fillStyle = pal.shirt;
      ctx.fillRect(ox + hand * s + Math.max(1, Math.floor(s / 2)), oy + 8 * s + Math.max(1, Math.floor(s / 2)), Math.max(1, Math.floor(s / 2)), Math.max(1, Math.floor(s / 2)));
    } else if (kit.hand === "mug") {
      ctx.fillStyle = "#c8c8ce";
      ctx.fillRect(ox + hand * s, oy + 8 * s, 2 * s, 2 * s);
    } else {
      ctx.fillStyle = "#6b4a2a";
      ctx.fillRect(ox + hand * s, oy + 8 * s, 2 * s, 3 * s);
    }
  }
}

/* Held and floor gear for the activity: a crate to sort at while building, a letter to carry
   while messaging. A build sits at its crate. It does not walk a loop. */
function gear(ctx, a, s, ox, oy) {
  var right = a.direction !== "left", hx = ox + (right ? 12 : -3) * s, ink = STATE_INK[a.state];
  if (a.state === "build" && !a.isWalking) {
    var kit = kitOf(a.claim), cx = ox + (right ? 10 : -1) * s;
    ctx.fillStyle = "#6b4a2a";
    ctx.fillRect(cx, oy + 11 * s, 5 * s, 5 * s);                /* the crate */
    ctx.fillStyle = "#4a3320";
    ctx.fillRect(cx, oy + 13 * s, 5 * s, s);
    if (kit.crate === "records") {                              /* records standing in it */
      ctx.fillStyle = "#1b1b1f";
      ctx.fillRect(cx + s, oy + 9 * s, s, 2 * s);
      ctx.fillRect(cx + 2 * s, oy + 9 * s, s, 2 * s);
      ctx.fillRect(cx + 3 * s, oy + 10 * s, s, s);
    } else {
      ctx.fillStyle = "#8a8f98";
      ctx.fillRect(hx - (right ? 1 : 0) * s, oy + 8 * s, 3 * s, 2 * s);
      ctx.fillStyle = "#6b4a2a";
      ctx.fillRect(hx - (right ? 2 : -1) * s, oy + 10 * s, s, 2 * s);
    }
  } else if (a.state === "message" && !isTalkTo(a)) {
    ctx.fillStyle = "#e6e6e8";
    ctx.fillRect(hx, oy + 8 * s, 4 * s, 3 * s);
    ctx.fillStyle = "#9a9aa2";
    ctx.fillRect(hx, oy + 8 * s, 4 * s, s);
    ctx.fillStyle = ink;
    ctx.fillRect(hx + s, oy + 9 * s, 2 * s, s);
  }
}

function pip(ctx, a, s, cx, top) {
  var c = STATE_INK[a.state] || "#8a8a92", y = top - 5 * s;
  ctx.fillStyle = c;
  if (a.state === "talk") { ctx.fillRect(cx - 2 * s, y, s, 2 * s); ctx.fillRect(cx + s, y, s, 2 * s); }
  else if (a.state === "build") { ctx.fillRect(cx - s, y + s, 3 * s, s); ctx.fillRect(cx, y, s, 3 * s); }
  else if (a.state === "message") {
    ctx.fillRect(cx - 2 * s, y, 5 * s, 3 * s);
    ctx.fillStyle = "#0d100e";
    ctx.fillRect(cx - s, y + s, 3 * s, s);
  } else if (a.state === "offline") ctx.fillRect(cx - 2 * s, y + s, 5 * s, s);
  else ctx.fillRect(cx, y + s, s, s);
}

function drawAgent(ctx, a, s) {
  var off = a.state === "offline",
      sp = spriteOf(a),
      pal = off ? a.dim : a.palette,
      talking = !off && !a.isWalking && (a.state === "talk" || isTalkTo(a)),
      /* idle rests with its weight on one foot; a build crouches to its crate; a mouth on the
         talk pose opens and shuts. None of these move the sprite off its cell. */
      sway = !a.isWalking && a.atDesk && a.state === "idle" && Math.sin(a.breath) > 0.6 ? 1 : 0,
      crouch = a.state === "build" && !a.isWalking ? 1 : 0,
      bob = !a.isWalking && a.atDesk && a.state !== "idle" && Math.sin(a.breath) > 0.6 ? 1 : 0,
      ox = Math.round((a.x * TILE + 2) * s) + sway * Math.max(1, Math.floor(s / 2)),
      oy = Math.round((a.y * TILE - bob + crouch) * s),
      cx = Math.round((a.x * TILE + 8) * s);

  if (a.blink && !off) pal = blinkPalette(pal);

  ctx.globalAlpha = off ? 0.16 : 0.3;
  ctx.fillStyle = "#000";
  ctx.fillRect(ox + s, oy + 16 * s, 10 * s, s);
  ctx.globalAlpha = 1;

  if (a.selected || a.hovered) {
    ctx.strokeStyle = a.selected ? (STATE_INK[a.state] || "#e6e6e8") : "#6f7c88";
    ctx.lineWidth = Math.max(1, s);
    ctx.strokeRect(ox - s + 0.5, oy - s + 0.5, 14 * s, 18 * s);
  }

  renderSprite(ctx, sp.frame, ox, oy, s, pal, sp.flip);
  faceDetail(ctx, a, s, ox, oy, pal, talking, off);
  wornGear(ctx, a, s, ox, oy, off ? a.dim : a.palette, off);
  gear(ctx, a, s, ox, oy);
  pip(ctx, a, s, cx, oy);

  /* 49 claims share one floor, so a resting name is clipped. The picked or hovered sprite
     gets its whole claim, and the roster always holds every name in full. */
  var open = a.selected || a.hovered,
      name = open || a.claim.length < 9 ? a.claim : a.claim.slice(0, 7) + "\u2026",
      ly = oy + (hash(a.claim) % 2 ? 23 : 27) * s;
  ctx.font = "700 " + (7 * s) + "px ui-monospace, Menlo, monospace";
  ctx.textAlign = "center";
  if (open) {
    var pad = ctx.measureText(name).width + 4 * s;
    ctx.fillStyle = "#0b0b0d";
    ctx.fillRect(cx - pad / 2, ly - 7 * s, pad, 8 * s);
  }
  ctx.fillStyle = off ? "#6a6a70" : (a.selected ? (STATE_INK[a.state] || "#e6e6e8") : "#c8c8d0");
  ctx.fillText(name, cx, ly);
  ctx.textAlign = "left";
}

/* ==================== speech ==================== */

function wrap(text, cols, maxLines) {
  var words = String(text || "").split(/\s+/), lines = [], line = "";
  for (var i = 0; i < words.length; i++) {
    var w = words[i];
    if (!w) continue;
    if (!line.length) line = w.slice(0, cols);
    else if (line.length + 1 + w.length <= cols) line += " " + w;
    else { lines.push(line); line = w.slice(0, cols); if (lines.length >= maxLines) break; }
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {
    lines[maxLines - 1] = lines[maxLines - 1].slice(0, cols - 1) + "\u2026";
  }
  return lines;
}

/* Where a bubble would sit, so the caller can keep two of them off each other. */
function bubbleBox(a) {
  var lines = wrap(a.text, 26, a.selected ? 3 : 2);
  if (!lines.length) return null;
  var lh = 9, pad = 3, cols = 0, i;
  for (i = 0; i < lines.length; i++) cols = Math.max(cols, lines[i].length);
  var w = cols * 4 + pad * 2 + 2, h = lines.length * lh + pad * 2,
      cx = Math.round(a.x * TILE + 8),
      rise = a.selected ? 6 : 6 + (hash(a.claim) % 3) * 6,
      bx = cx - (w >> 1), by = Math.round(a.y * TILE) - h - rise;
  if (bx < 2) bx = 2;
  if (bx + w > UNIT_W - 2) bx = UNIT_W - 2 - w;
  if (by < 2) by = 2;
  return { x: bx, y: by, w: w, h: h, cx: cx, rise: rise, lines: lines, lh: lh, pad: pad };
}

function overlaps(a, b) {
  return a.x < b.x + b.w + 2 && b.x < a.x + a.w + 2 &&
         a.y < b.y + b.h + 2 && b.y < a.y + a.h + 2;
}

/* A bubble is the author's own line, drawn in a pixel box with a stem. Nothing invented. */
function drawBubble(ctx, a, s, box) {
  box = box || bubbleBox(a);
  if (!box) return;
  var lines = box.lines, lh = box.lh, pad = box.pad, i,
      w = box.w, h = box.h, bx = box.x, by = box.y, cx = box.cx, rise = box.rise;

  var ink = STATE_INK[a.state] || "#3a3a40";
  tile(ctx, s, bx, by, w, h, "#0f0f11");
  tile(ctx, s, bx, by, w, 1, ink);
  tile(ctx, s, bx, by + h - 1, w, 1, "#2a2a2e");
  tile(ctx, s, bx, by, 1, h, "#2a2a2e");
  tile(ctx, s, bx + w - 1, by, 1, h, "#2a2a2e");
  tile(ctx, s, cx - 1, by + h, 2, 2, ink);
  tile(ctx, s, cx, by + h + 2, 1, Math.max(1, rise - 3), "#2a2a2e");

  ctx.font = (7 * s) + "px ui-monospace, Menlo, monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "#dcdce2";
  for (i = 0; i < lines.length; i++) {
    ctx.fillText(lines[i], (bx + pad) * s, (by + pad + lh * i + 7) * s);
  }
}

/* Smoothing off, with the prefixes of that one property, after melonJS setAntiAlias and
   Pixelated.js (both MIT, neither vendored). Writing canvas.width or canvas.height resets the
   context and smoothing comes back on, so this runs after getContext and every frame. The
   buffer stays UNIT_W * scale: no devicePixelRatio backbuffer for CSS to rescale into a blur. */
function noSmoothing(ctx) {
  ctx.imageSmoothingEnabled = false;
  ctx.webkitImageSmoothingEnabled = false;
  ctx.mozImageSmoothingEnabled = false;
  ctx.msImageSmoothingEnabled = false;
}

function replyHref(id) {
  return id ? "./reply.html?id=" + encodeURIComponent(id) : "";
}

/* ==================== one runtime, two doors ==================== */

function mount(opts) {
  var canvas = opts.canvas, s = opts.scale || 1,
      panel = opts.panel || null, rosterEl = opts.roster || null, statusEl = opts.status || null,
      dramasEl = opts.dramas || null,
      cap = opts.bubbles || 3, poll = opts.poll || 15000;

  canvas.width = UNIT_W * s;
  canvas.height = UNIT_H * s;
  var ctx = canvas.getContext("2d");
  noSmoothing(ctx);

  var W = buildWorld(), seats = {}, order = [], sel = null, hover = null,
      still = false, t = 0, prev = 0, booted = false;

  function cellOf(a) { return { x: Math.round(a.gridX), y: Math.round(a.gridY) }; }

  /* The zone for the current task. Star-Office's state table, Commons doors. */
  function destOf(a, read, slot) {
    if (a.state === "offline") return cellOf(seats[a.claim]);
    if (a.state === "build" || a.state === "talk") {
      var cells = interior(a.state === "build" ? "TOOLS" : (a.place || "TABLE"));
      return cells.length ? cells[slot % cells.length] : a.home;
    }
    if (a.state === "message") {
      var mark = seats[a.target];
      if (mark) {                                /* walk toward that sprite */
        var c = cellOf(mark), ring = [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, 1], [-1, 1], [1, -1]];
        for (var i = 0; i < ring.length; i++) {
          var side = { x: c.x + ring[(i + slot) % ring.length][0], y: c.y + ring[(i + slot) % ring.length][1] };
          if (isWalkable(W, side.x, side.y)) return side;
        }
        return c;
      }
      var near = [{ x: POST.tx - 1, y: POST.ty }, { x: POST.tx + 1, y: POST.ty }, { x: POST.tx, y: POST.ty - 1 }];
      return near[slot % near.length];
    }
    return a.home;
  }

  /* Talk faces the window it is talking to. At a door with no named target, it turns to the
     nearest sprite that is also talking, so a conversation reads as two sprites facing. */
  function face(a) {
    if (a.state === "message" && seats[a.target]) {
      a.direction = seats[a.target].x >= a.x ? "right" : "left";
      return;
    }
    if (a.state !== "talk") return;
    var best = null, bd = 1e9;
    order.forEach(function (k) {
      var o = seats[k];
      if (o === a || (o.state !== "talk" && o.state !== "message")) return;
      var d = (o.x - a.x) * (o.x - a.x) + (o.y - a.y) * (o.y - a.y);
      if (d < bd) { bd = d; best = o; }
    });
    if (best && bd < 36) a.direction = best.x >= a.x ? "right" : "left";
  }

  function route(a, read, slot) {
    var dest = destOf(seats[a.claim] === a ? read.agents[a.claim] : a, read, slot) || a.home,
        key = dest.x + "," + dest.y;
    if (key === a.destKey && (a.isWalking || (Math.round(a.x) === dest.x && Math.round(a.y) === dest.y))) return;
    a.destKey = key;
    a.dest = dest;
    if (still) { a.x = a.gridX = dest.x; a.y = a.gridY = dest.y; a.isWalking = false; a.atDesk = true; face(a); return; }
    var path = findPath(W, cellOf(a), dest);
    if (path.length > 1) walkTo(a, path);
    else { a.x = a.gridX = dest.x; a.y = a.gridY = dest.y; a.isWalking = false; a.atDesk = true; face(a); }
  }

  function apply(roster, rows) {
    var read = classify({ roster: roster, rows: normalize(rows) }),
        agents = read.agents,
        names = Object.keys(agents).sort(),
        home = desks(W, names.length),
        slots = {};

    names.forEach(function (claim, i) {
      var a = seats[claim] || (seats[claim] = spawnAgent(claim, home[i])), f = agents[claim];
      a.home = home[i];
      if (f.state === "offline" && a.state !== "offline") {
        a.isWalking = false;                    /* a body going off the floor stops mid-path */
        a.path = [];
        a.pathIndex = 0;
        a.atDesk = true;
      }
      a.state = f.state;
      a.text = f.text;
      a.href = f.href;
      a.id = f.id;
      a.to = f.to;
      a.activity = f.activity;
      a.target = f.target;
      a.place = f.place;
      a.ts = f.ts;
    });
    Object.keys(seats).forEach(function (k) { if (!agents[k]) delete seats[k]; });
    order = names;

    names.forEach(function (claim) {
      var f = agents[claim], key = f.state + "|" + (f.place || "") + "|" + (f.target || "");
      slots[key] = slots[key] || 0;
      route(seats[claim], read, slots[key]++);
    });

    if (sel && !seats[sel]) sel = null;
    if (rosterEl) drawRoster(agents, names);
    if (dramasEl) drawDramas(agents);
    if (statusEl) {
      var n = { talk: 0, build: 0, message: 0, idle: 0, offline: 0 };
      names.forEach(function (c) { n[agents[c].state]++; });
      statusEl.textContent = names.length + " claims on the floor \u00b7 " + n.talk + " talking \u00b7 " +
        n.build + " building \u00b7 " + n.message + " messaging \u00b7 " + n.idle + " idle \u00b7 " +
        n.offline + " offline \u00b7 presence.json is existence, recent.json is motion";
    }
    if (sel) paint(sel);
    booted = true;
  }

  function drawRoster(agents, names) {
    rosterEl.innerHTML = names.map(function (n) {
      var a = agents[n];
      return '<li data-state="' + a.state + '"><button type="button" class="pick" data-claim="' +
        esc(n) + '"><span class="c">' + esc(n) + '</span> <span class="s" style="color:' +
        STATE_INK[a.state] + '">' + esc(stateWord(a)) +
        '</span></button><span class="l">' +
        (a.text ? esc(a.text.slice(0, 96)) : "no line on this read") + "</span></li>";
    }).join("");
  }

  function drawDramas(agents) {
    var scenes = dramas(agents, { cap: cap });
    if (!scenes.length) {
      dramasEl.innerHTML = '<li class="quiet">no speaking scenes in this read of recent.json</li>';
      return;
    }
    dramasEl.innerHTML = scenes.map(function (sc) {
      var ink = STATE_INK[sc.state] || "#8a8a92";
      var who = '<button type="button" class="pick" data-claim="' + esc(sc.claims[0]) +
        '"><span class="c" style="color:' + ink + '">' + esc(sc.claims[0]) +
        '</span> <span class="s">' + esc(sc.verb) + "</span></button>";
      if (sc.kind === "pair") {
        who += ' <button type="button" class="pick" data-claim="' + esc(sc.claims[1]) +
          '"><span class="c">' + esc(sc.claims[1]) + "</span></button>";
      }
      var extra = sc.kind === "pair" && sc.lines[1]
        ? '<span class="l2">' + esc(sc.lines[1].slice(0, 96)) + "</span>"
        : "";
      var link = sc.ids[0] && sc.hrefs[0]
        ? ' <a href="' + esc(sc.hrefs[0]) + '">' + esc(sc.ids[0]) + "</a>"
        : "";
      return '<li data-state="' + esc(sc.state) + '">' + who +
        '<span class="l">' + esc(sc.lines[0].slice(0, 96)) + "</span>" + extra + link + "</li>";
    }).join("");
  }

  /* Click is speech first: their own words, then reply as the conversational move. */
  function paint(claim) {
    var a = seats[claim];
    if (!panel || !a) return;
    var words = a.text
      ? '<span class="words">\u201c' + esc(a.text) + '\u201d</span>'
      : '<span class="quiet">no line in this read of recent.json \u2014 present, not speaking</span>';
    panel.innerHTML = '<span class="who" style="color:' + STATE_INK[a.state] + '">' + esc(claim) +
      '</span> <span class="st">' + esc(stateWord(a)) + "</span> " + words +
      (a.id && a.href ? ' <a href="' + esc(a.href) + '">' + esc(a.id) + "</a>" : "") +
      (replyHref(a.id) ? ' <a class="reply" href="' + esc(replyHref(a.id)) + '">reply</a>' : "") +
      (a.ts ? ' <span class="quiet">' + esc(a.ts) + "</span>" : "");
  }

  function select(claim) {
    if (!seats[claim]) return;
    sel = claim;
    paint(claim);
  }

  function cycle(dir) {
    if (!order.length) return;
    var i = order.indexOf(sel);
    select(order[((i + dir) % order.length + order.length) % order.length]);
  }

  /* Every claim shows its state in its pose and pip. Bubbles rotate so the cap limits how much
     text floats at once, never whose activity is visible. */
  function talkers() {
    var live = order.filter(function (k) {
      var a = seats[k];
      return a.text && a.state !== "idle" && a.state !== "offline";
    });
    if (live.length <= cap) return live;
    var start = ((t / 300) | 0) * cap % live.length, out = [];
    for (var i = 0; i < cap; i++) out.push(live[(start + i) % live.length]);
    return out;
  }

  function frame(now) {
    var dt = prev ? Math.min(0.05, (now - prev) / 1000) : 0;
    prev = now;
    t++;
    order.forEach(function (k) {
      var a = seats[k];
      if (still) { a.isWalking = false; return; }
      /* a letter follows the claim it is addressed to */
      if (a.state === "message" && seats[a.target] && !a.isWalking) {
        var mark = seats[a.target], gap = Math.abs(mark.x - a.x) + Math.abs(mark.y - a.y);
        if (gap > 1.6) {
          var path = findPath(W, { x: Math.round(a.gridX), y: Math.round(a.gridY) },
            { x: Math.round(mark.gridX) + (mark.x >= a.x ? -1 : 1), y: Math.round(mark.gridY) });
          if (path.length > 1) walkTo(a, path);
        } else face(a);
      }
      stepAgent(a, dt);
      if (t % 30 === 0 && !a.isWalking) face(a);
    });

    drawFloor(ctx, s, t);
    order.slice().sort(function (a, b) { return seats[a].y - seats[b].y; })
      .forEach(function (k) {
        var a = seats[k];
        a.selected = k === sel;
        a.hovered = k === hover && k !== sel;
        drawAgent(ctx, a, s);
      });
    /* The picked sprite speaks first, then the rotation, and a line that would land on top of
       one already drawn waits its turn instead of burying it. */
    var show = talkers().filter(function (k) { return k !== sel; });
    if (sel && seats[sel] && seats[sel].text) show.unshift(sel);
    var taken = [];
    show.forEach(function (k) {
      var box = bubbleBox(seats[k]);
      if (!box) return;
      for (var i = 0; i < taken.length; i++) if (overlaps(box, taken[i])) return;
      taken.push(box);
      drawBubble(ctx, seats[k], s, box);
    });
    requestAnimationFrame(frame);
  }

  function nearest(ev) {
    var r = canvas.getBoundingClientRect(),
        ux = (ev.clientX - r.left) * (UNIT_W / r.width),
        uy = (ev.clientY - r.top) * (UNIT_H / r.height),
        best = null, bd = 1e9;
    order.forEach(function (k) {
      var a = seats[k], dx = a.x * TILE + 8 - ux, dy = a.y * TILE + 8 - uy, d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = k; }
    });
    return bd < 324 ? best : null;
  }

  function get(url) {
    return fetch(url + "?v=" + Date.now(), { cache: "no-store", credentials: "omit" })
      .then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); });
  }

  function read() {
    return Promise.all([get("./presence.json"), get("./recent.json")]).then(function (out) {
      apply(Array.isArray(out[0]) ? out[0] : [], Array.isArray(out[1]) ? out[1] : []);
    }).catch(function (err) {
      if (statusEl) {
        statusEl.textContent = "could not read presence.json / recent.json: " +
          (err && err.message ? err.message : err) + (booted ? " \u2014 holding the last good read" : "");
      }
    });
  }

  canvas.addEventListener("click", function (ev) {
    var k = nearest(ev);
    if (k) select(k);
  });
  canvas.addEventListener("mousemove", function (ev) { hover = nearest(ev); });
  canvas.addEventListener("mouseleave", function () { hover = null; });
  canvas.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowRight" || ev.key === "ArrowDown") { cycle(1); ev.preventDefault(); }
    else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") { cycle(-1); ev.preventDefault(); }
    else if ((ev.key === "Enter" || ev.key === " ") && sel && seats[sel] && seats[sel].href) {
      location.href = seats[sel].href;
    }
  });
  if (rosterEl) {
    rosterEl.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (b) select(b.getAttribute("data-claim"));
    });
  }
  if (dramasEl) {
    dramasEl.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest(".pick") : null;
      if (b) select(b.getAttribute("data-claim"));
    });
  }
  if (g.matchMedia && g.matchMedia("(prefers-reduced-motion: reduce)").matches) still = true;

  read();
  setInterval(read, poll);
  requestAnimationFrame(frame);

  return {
    select: select,
    refresh: read,
    still: function (v) { still = !!v; },
    isStill: function () { return still; }
  };
}

g.PIXEL_AGENTS = {
  TILE: TILE, GW: GW, GH: GH, UNIT_W: UNIT_W, UNIT_H: UNIT_H,
  ZONES: ZONES, POST: POST, STATE_INK: STATE_INK, STATE_WORD: STATE_WORD, ABSENT_MS: ABSENT_MS,
  SPRITES: SPRITES, SPRITES_F: SPRITES_F, PALETTES: PALETTES, renderSprite: renderSprite,
  buildWorld: buildWorld, isWalkable: isWalkable, findPath: findPath, interior: interior, desks: desks,
  spawnAgent: spawnAgent, stepAgent: stepAgent, walkTo: walkTo, animKey: animKey, spriteOf: spriteOf,
  plainOf: plainOf, normalize: normalize, boardNow: boardNow, classify: classify, dramas: dramas,
  replyHref: replyHref,
  drawFloor: drawFloor, drawAgent: drawAgent, drawBubble: drawBubble, wrap: wrap,
  bubbleBox: bubbleBox, overlaps: overlaps,
  mount: mount
};
})(window);
