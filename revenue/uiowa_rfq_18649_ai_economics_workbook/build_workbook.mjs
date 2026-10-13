import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const input = JSON.parse(await fs.readFile(process.argv[2] || 'inputs.json', 'utf8'));
const outDir = process.argv[3] || 'outputs/commons-economics-20260926';
const fields = ['monthly_tasks','adoption_fraction','baseline_minutes','author_minutes',
  'checking_minutes','rework_fraction','rework_minutes','attempts_per_task',
  'generation_cash_per_attempt','loaded_hourly_rate','integration_hours','setup_cash',
  'support_hours','maintenance_hours','platform_cash','cash_conversion_fraction'];
if (input.scenarios.length !== 4 || input.scenarios.some(s=>Object.keys(s.inputs).length!==16 || fields.some(f=>!(f in s.inputs)))) throw Error('This workbook requires the four-case, 16-input contract.');
const wb = Workbook.create();
const summary = wb.worksheets.add('Economics');
const inputs = wb.worksheets.add('Inputs');
const sensitivity = wb.worksheets.add('Sensitivity');
const bounds = wb.worksheets.add('Range bounds');
const num = '#,##0.00;(#,##0.00);"-"';
const navy = '#19334A', blue = '#1454A3', green = '#207247';
function values(sheet, cell, rows) { sheet.getRange(cell).write(rows); }
function formula(sheet, cell, text) { sheet.getRange(cell).formulas = [[text]]; }
function title(sheet, name, lastCol='G', lastRow=50) {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font.name = 'Arial';
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.font.size = 10;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.rowHeight = 21;
  sheet.getRange(`A1:${lastCol}${lastRow}`).format.verticalAlignment = 'center';
  sheet.getRange(`A1:${lastCol}2`).format.fill = navy;
  sheet.getRange(`A1:${lastCol}2`).format.font.color = '#FFFFFF';
  sheet.getRange('A1').values = [[name]];
  sheet.getRange('A1').format.font.size = 16;
  sheet.getRange(`A1:A${lastRow}`).format.columnWidth = 40;
  sheet.getRange(`B1:${lastCol}${lastRow}`).format.columnWidth = 18;
}
function header(sheet, range) {
  sheet.getRange(range).format.fill = navy;
  sheet.getRange(range).format.font.color = '#FFFFFF';
  sheet.getRange(range).format.font.bold = true;
  sheet.getRange(range).format.wrapText = true;
  sheet.getRange(range).format.rowHeight = 30;
}
function need(refs, expr) {
 const h="'Inputs'!$B$5";
 return `IF(AND(COUNT(${refs.join(',')})=${refs.length},ISNUMBER(${h}),${h}>0,INT(${h})=${h}),${expr},"UNKNOWN")`;
}
const rowOf = i => 12+i*6;
const active = (i, point='D') => `'Inputs'!${point}${rowOf(i)}`;
function economic(refs, cash=false) {
  const [n,a,b,d,c,p,r,t,g,w,I,S,U,M,F,z]=refs;
  const h="'Inputs'!$B$5";
  const capacity=`(${h}*(${n}*${a}*(${b}-${d}-${c}-${p}*${r})/60-${U}-${M})-${I})`;
  const cost=`(${h}*(${n}*${a}*${t}*${g}+${F})+${S})`;
  return need(cash?refs:refs.slice(0,15),`${capacity}*${w}${cash?'*'+z:''}-${cost}`);
}

title(inputs,'AI workflow assumptions','H',112);
values(inputs,'A4',[['Case selected (1–4)',1],['Horizon months',input.horizon_months],['Currency',input.currency],['Input basis',input.input_basis]]);
inputs.getRange('B4:B7').format.font.color=blue;
inputs.getRange('B4:B7').format.fill='#FFF2CC';
inputs.getRange('B4').dataValidation={rule:{type:'list',values:['1','2','3','4']}};
inputs.getRange('B7').dataValidation={rule:{type:'list',values:['SYNTHETIC','PLANNING_ASSUMPTIONS','MEASURED_INPUTS']}};
values(inputs,'D4',input.scenarios.map((s,i)=>[i+1,s.id,s.group,s.label,s.notes]));
inputs.getRange('E4:E7').format.columnWidth=25;
inputs.getRange('G4:G7').format.columnWidth=48;
inputs.getRange('H4:H7').format.columnWidth=65;
inputs.getRange('G4:H7').format.wrapText=true;
inputs.getRange('A4:H7').format.rowHeight=62;
values(inputs,'A9',[['Edit blue case inputs. Blank low/base/high means UNKNOWN. Sources and evidence basis travel with exported inputs.']]);
values(inputs,'A11',[['Input / case','Unit','Low','Base','High','Evidence basis','Source','Collection note']]);
header(inputs,'A11:H11');
for(let i=0;i<fields.length;i++){
  const f=fields[i], r=rowOf(i), example=input.scenarios[0].inputs[f];
  values(inputs,`A${r}`,[[f,example.unit]]);
  inputs.getRange(`A${r}:H${r}`).format.fill='#E7EDF2';
  inputs.getRange(`A${r}:H${r}`).format.font.bold=true;
  for(const col of ['C','D','E']){
    const choose=`CHOOSE($B$4,${col}${r+1},${col}${r+2},${col}${r+3},${col}${r+4})`;
    const selected=['C','D','E'].map(c=>`CHOOSE($B$4,${c}${r+1},${c}${r+2},${c}${r+3},${c}${r+4})`);
    const valid=`AND(COUNT(${selected.join(',')})=3,${selected[0]}>=0,${selected[0]}<=${selected[1]},${selected[1]}<=${selected[2]}${example.unit==='fraction'?`,${selected[2]}<=1`:''})`;
    // Validate only the active case; blanks are never silently converted to zero.
    formula(inputs,`${col}${r}`,`=IF(${valid},${choose},"UNKNOWN")`);
  }
  input.scenarios.forEach((s,j)=>{
    const cell=s.inputs[f];
    values(inputs,`A${r+j+1}`,[[s.id,cell.unit,...['low','base','high'].map(k=>cell.range?Number(cell.range[k]):null),cell.basis,cell.source,'']]);
  });
  inputs.getRange(`C${r+1}:G${r+4}`).format.font.color=blue;
  inputs.getRange(`G${r+1}:H${r+4}`).format.wrapText=true;
  inputs.getRange(`A${r+1}:H${r+4}`).format.rowHeight=48;
  inputs.getRange(`C${r+1}:E${r+4}`).format.fill='#FFF8DE';
  inputs.getRange(`C${r}:E${r+4}`).setNumberFormat(example.unit==='fraction'?'0.0%':num);
  inputs.getRange(`F${r+1}:F${r+4}`).dataValidation={rule:{type:'list',values:['synthetic','assumed','observed','unknown']}};
}
inputs.getRange('B11:B112').format.columnWidth=26;
inputs.getRange('F11:F112').format.columnWidth=18;
inputs.getRange('G11:G112').format.columnWidth=65;
inputs.freezePanes.freezeRows(11);

title(summary,'AI workflow economics','D',54);
values(summary,'A4',[['Case selected'],['Horizon months'],['Currency'],['Result basis','MODELED_NOT_OBSERVED']]);
formula(summary,'B4',"=INDEX('Inputs'!$E$4:$E$7,'Inputs'!$B$4)");
summary.getRange('B4').format.font.color=green;
formula(summary,'B5',"='Inputs'!B5");formula(summary,'B6',"='Inputs'!B6");
values(summary,'A9',[['Metric','Base result','Meaning']]);header(summary,'A9:C9');
const v=fields.map((_,i)=>active(i));
const [n,a,b,d,c,p,r,t,g,w,I,S,U,M,F,z]=v;
const h="'Inputs'!$B$5";
const specs=[
 ['Assisted tasks / month',`${n}*${a}`,'All attempts, including unsuccessful outputs'],
 ['Baseline hours / month',`B10*${b}/60`,'Comparable accepted output'],
 ['Assisted hours / month',`B10*(${d}+${c}+${p}*${r})/60`,'Authoring, verification and repair'],
 ['Net capacity hours / month',`B11-B12-${U}-${M}`,'Includes recurring support and maintenance'],
 ['Net capacity hours / horizon',`${h}*B13-${I}`,'Signed capacity after initial integration'],
 ['External cash / month',`B10*${t}*${g}+${F}`,'Generation and fixed platform costs'],
 ['External cash / horizon',`${h}*B15+${S}`,'Includes setup cash'],
 ['One-time economic cost',`${I}*${w}+${S}`,'Integration capacity value plus setup cash'],
 ['Economic net / month',`B13*${w}-B15`,'Opportunity value after external cash'],
 ['Economic net / horizon',`${h}*B18-B17`,'Capacity valuation, not observed cash savings'],
 ['Cash conversion net / horizon',`B14*${w}*${z}-B16`,'Uses the explicit signed cash-conversion assumption'],
 ['Economic margin / assisted task',`(${b}-${d}-${c}-${p}*${r})*${w}/60-${t}*${g}`,'Negative margin cannot be cured by volume'],
 ['Fixed economic cost / month',`(${U}+${M})*${w}+${F}`,'Support, maintenance and fixed cash']
];
specs.forEach(([label,expr,note],i)=>{
  values(summary,`A${10+i}`,[[label,null,note]]);
  formula(summary,`B${10+i}`,'='+need(i===10?v:v.slice(0,15),expr));
});
values(summary,'A25',[['Break-even','Base result','Interpretation']]);header(summary,'A25:C25');
const br=[
 ['Assisted tasks / month',`IF(B21>0,(B22+B17/${h})/B21,IF(AND(B21=0,B22+B17/${h}=0),0,"n.a."))`,'Exact threshold'],
 ['Whole assisted tasks / month','IF(ISNUMBER(B26),ROUNDUP(B26,0),"n.a.")','Ceiling of the exact threshold'],
 ['Required adoption fraction',`IF(AND(ISNUMBER(B26),${n}>0),B26/${n},"n.a.")`,'Above 100% is unattainable at current volume'],
 ['Maximum checking minutes',`IF(AND(B10>0,${w}>0),${b}-${d}-${p}*${r}-60/${w}*(${t}*${g}+(B22+B17/${h})/B10),"n.a.")`,'A negative result cannot justify skipping required checks'],
 ['Simple payback months','IF(B18>0,B17/B18,IF(AND(B17=0,B18=0),0,"n.a."))','Steady-state economic payback, not cash payback']
];
br.forEach(([label,expr,note],i)=>{values(summary,`A${26+i}`,[[label,null,note]]);formula(summary,`B${26+i}`,'='+need(v.slice(0,15),expr));});
summary.getRange('B28').setNumberFormat('0.0%');
values(summary,'A33',[['Independent ranges','Minimum','Maximum']]);header(summary,'A33:C33');
values(summary,'A34',[['Economic net / horizon'],['Cash conversion net / horizon']]);
for(const [row,col]of [[34,'R'],[35,'S']])for(const [out,fn]of [['B','MIN'],['C','MAX']])formula(summary,`${out}${row}`,`=IF(COUNT('Range bounds'!${col}6:${col}37)=32,${fn}('Range bounds'!${col}6:${col}37),"UNKNOWN")`);
values(summary,'A38',[['Range assumptions are independent bounds, not probabilities or confidence intervals.'],['Select each of the four cases in Inputs. All active formulas, sensitivities and ranges recalculate.'],['Keep capacity value separate from cash. All supplied cases are fictional training assumptions.'],['Export edited inputs to the canonical calculator for exact-decimal reports and comparison of all cases.'],['Blue cells are editable inputs. Blank measurements remain UNKNOWN; explicit zero remains zero.']]);
summary.getRange('A38:D42').format.rowHeight=26;
summary.getRange('A1:A54').format.columnWidth=43;
summary.getRange('B1:B54').format.columnWidth=25;
summary.getRange('C1:C54').format.columnWidth=65;
summary.getRange('B10:C35').setNumberFormat(num);
summary.getRange('B28').setNumberFormat('0.0%');
summary.getRange('C10:C30').format.wrapText=true;
summary.getRange('A10:C30').format.rowHeight=30;
summary.getRange('B19:B20').format.font.bold=true;
summary.getRange('B19:B20').format.fill='#E7EDF2';

title(sensitivity,'One-input sensitivity','E',41);
values(sensitivity,'A3',[['Case selected']]);formula(sensitivity,'B3',"='Economics'!B4");
values(sensitivity,'A4',[['All other inputs stay at base. Values use the selected case and the current horizon.']]);
values(sensitivity,'A5',[['Input','Endpoint','Economic net','Cash conversion net']]);header(sensitivity,'A5:D5');
fields.forEach((f,i)=>['C','E'].forEach((point,j)=>{
 const row=6+i*2+j, refs=v.map((ref,k)=>k===i?active(i,point):ref);
 values(sensitivity,`A${row}`,[[f,j?'High':'Low']]);
 formula(sensitivity,`C${row}`,'='+economic(refs));formula(sensitivity,`D${row}`,'='+economic(refs,true));
}));
sensitivity.getRange('C6:D37').setNumberFormat(num);
sensitivity.getRange('C1:D41').format.columnWidth=25;
sensitivity.freezePanes.freezeRows(5);

title(bounds,'Independent range endpoints','S',39);
values(bounds,'A3',[['Case selected']]);formula(bounds,'B3',"='Economics'!B4");
values(bounds,'A4',[['32 endpoint combinations cover sign reversals in volume, adoption, rate and conversion. Not a forecast distribution.']]);
values(bounds,'A5',[['Corner',...fields,'Economic net','Cash conversion net']]);header(bounds,'A5:S5');
bounds.getRange('A5:S5').format.rowHeight=48;
const free=[0,1,9,15];
for(let corner=0;corner<32;corner++){
 const row=6+corner, favorable=corner>=16;
 values(bounds,`A${row}`,[[corner+1]]);
 fields.forEach((f,i)=>{
  const bit=free.indexOf(i), high=bit>=0?Boolean(corner&(1<<bit)):(i===2?favorable:!favorable);
  const col=String.fromCharCode(66+i), ref=active(i,high?'E':'C');
  formula(bounds,`${col}${row}`,`=IF(ISNUMBER(${ref}),${ref},"UNKNOWN")`);
 });
 const refs=fields.map((_,i)=>`${String.fromCharCode(66+i)}${row}`);
 formula(bounds,`R${row}`,'='+economic(refs));formula(bounds,`S${row}`,'='+economic(refs,true));
}
bounds.getRange('B6:S37').setNumberFormat(num);
bounds.getRange('B6:Q37').format.font.color=green;
bounds.getRange('A1:A39').format.columnWidth=12;
bounds.freezePanes.freezeRows(5);bounds.freezePanes.freezeColumns(1);
for(const sheet of [summary,sensitivity,bounds])sheet.getUsedRange().conditionalFormats.add('containsText',{text:'UNKNOWN',format:{fill:'#FFF2CC',font:{color:'#9C5700'}}});

await fs.mkdir(outDir,{recursive:true});
const cases=[];
for(let i=1;i<=4;i++){
 inputs.getRange('B4').values=[[i]];wb.recalculate();
 cases.push({id:input.scenarios[i-1].id,base:summary.getRange('B10:B22').values.map(r=>r[0]),bounds:summary.getRange('B34:C35').values,break_even:summary.getRange('B26:B30').values.map(r=>r[0]),sensitivity:sensitivity.getRange('C6:D37').values});
}
inputs.getRange('B4').values=[[1]];wb.recalculate();
await fs.writeFile(path.join(outDir,'formula-results.json'),JSON.stringify(cases,null,2));
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:2000});
console.log(errors.ndjson);
for(const [sheetName,range,file]of [['Economics','A1:C36','economics'],['Inputs','A11:G22','inputs'],['Sensitivity','A1:D16','sensitivity'],['Range bounds','A1:F10','bounds']]){
 const image=await wb.render({sheetName,range,scale:1.5,format:'png'});
 await fs.writeFile(path.join(outDir,file+'.png'),new Uint8Array(await image.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(outDir,'AI_workflow_economics.xlsx'));
console.log(JSON.stringify({workbook:path.join(outDir,'AI_workflow_economics.xlsx'),cases:cases.length}));
