import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [input, outputDir] = process.argv.slice(2);
if (!input || !outputDir) throw new Error('Usage: build_workbook.mjs worked-input.json output-directory');
const p = JSON.parse(await fs.readFile(input, 'utf8'));
const wb = Workbook.create();
const portfolio = wb.worksheets.add('Portfolio');
const checks = wb.worksheets.add('Checks');
const runs = wb.worksheets.add('Runs');
const improvements = wb.worksheets.add('Improvements');
const source = wb.worksheets.add('Original source');
const sheets = [portfolio, checks, runs, improvements, source];
const ink = '#20354B', inputFill = '#FFF4CF', muted = '#E9EFF4';
const set = (s, address, rows) => { s.getRange(address).values = rows; };
const form = (s, address, formula) => { s.getRange(address).formulas = [[formula]]; };
const dateValue = value => value ? new Date(value + 'T00:00:00Z') : null;
function base(s, end, title, widths) {
  s.showGridLines = false;
  s.getRange(`A1:${end}`).format.font = {name:'Arial',size:10,color:'#1F2937'};
  s.getRange(`A1:${end}`).format.verticalAlignment='center';
  set(s,'A2',[[title]]);s.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:ink};
  s.getRange(`A2:${end.match(/[A-Z]+/)[0]}2`).format.borders={bottom:{style:'thin',color:ink}};
  widths.forEach((width,i)=>s.getRangeByIndexes(0,i,Number(end.match(/\d+/)[0]),1).format.columnWidth=width);
}
function header(s,row,labels){
  const r=s.getRangeByIndexes(row-1,0,1,labels.length);r.values=[labels];
  r.format={fill:ink,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:32};
}
function warning(s,range){
  s.getRange(range).conditionalFormats.add('containsText',{text:'INVALID',format:{fill:'#FCE8E6',font:{color:'#B42318',bold:true}}});
}
const behaviorById = Object.fromEntries(p.behaviors.map(b=>[b.id,b]));
const aStart=14,aEnd=aStart+p.assertions.length-1,cStart=7,cEnd=cStart+p.checks.length-1,rStart=7,rEnd=rStart+p.runs.length-1;
if (!p.checks.length || !p.runs.length) throw new Error('Workbook demonstration requires at least one check and run; use CLI for empty inventories.');
base(portfolio,`M${aEnd+5}`,'Testing portfolio',[24,15,23,27,12,16,58,14,16,12,23,20,60]);portfolio.tabColor=ink;
set(portfolio,'A3',[['SYNTHETIC EXAMPLE. Run records are fictional; this workbook does not execute checks or authorize a release.']]);
set(portfolio,'A4',[['As of',dateValue(p.as_of),'Required revision',p.required_revision,'Max age (days)',p.max_age_days,'Impact known?',p.impact_known]]);
portfolio.getRange('B4').format.numberFormat='yyyy-mm-dd';
for(const address of ['B4','D4','F4','H4'])portfolio.getRange(address).format.fill=inputFill;
set(portfolio,'A6',[['Assertion status','Count']]);portfolio.getRange('A6:B6').format.fill=muted;
const states=['SUPPORTED','OPEN_FAILURE','UNTESTED','UNCERTAIN','OUT_OF_SCOPE'];
states.forEach((state,i)=>{set(portfolio,`A${7+i}`,[[state]]);form(portfolio,`B${7+i}`,`=COUNTIFS(K${aStart}:K${aEnd},A${7+i})`);});
set(portfolio,'D6',[['Input status','Count']]);portfolio.getRange('D6:E6').format.fill=muted;
set(portfolio,'D7',[['Invalid input rows']]);form(portfolio,'E7',`=COUNTIFS('Runs'!L${rStart}:L${rEnd},"INVALID")+COUNTIFS(K${aStart}:K${aEnd},"MISSING_SCOPE_REASON")`);
set(portfolio,'D8',[['Current supporting runs']]);form(portfolio,'E8',`=SUM('Runs'!M${rStart}:M${rEnd})`);
set(portfolio,'D9',[['Open failures']]);form(portfolio,'E9',`=SUM('Runs'!N${rStart}:N${rEnd})`);
set(portfolio,'G6',[['Selection effort','Value']]);portfolio.getRange('G6:H6').format.fill=muted;
set(portfolio,'G7',[['Known selected minutes']]);form(portfolio,'H7',`=SUMIFS('Checks'!G${cStart}:G${cEnd},'Checks'!J${cStart}:J${cEnd},1)`);
set(portfolio,'G8',[['Selected with unknown effort']]);form(portfolio,'H8',`=COUNTIFS('Checks'!K${cStart}:K${cEnd},"UNKNOWN")`);
set(portfolio,'G10',[['Amber fields are editable. Fix invalid rows before interpreting totals.']]);
header(portfolio,13,['Assertion ID','Service','Behavior ID','Level','Required?','Inventory complete?','Assertion','Current passes','Open failures','Check count','Evidence state','Reported claim','Scope reason (if not required)']);
set(portfolio,`A${aStart}`,p.assertions.map(a=>[a.id,behaviorById[a.behavior_id].service,a.behavior_id,a.level,a.required,a.inventory_complete,a.statement,null,null,null,null,a.reported_coverage??'not supplied',a.scope_reason??null]));
portfolio.getRange(`A${aStart}:G${aEnd}`).format.fill=inputFill;portfolio.getRange(`M${aStart}:M${aEnd}`).format.fill=inputFill;
portfolio.getRange(`A${aStart}:M${aEnd}`).format.wrapText=true;portfolio.getRange(`A${aStart}:M${aEnd}`).format.rowHeight=58;
for(let row=aStart;row<=aEnd;row++){
  form(portfolio,`H${row}`,`=COUNTIFS('Runs'!C${rStart}:C${rEnd},A${row},'Runs'!M${rStart}:M${rEnd},1)`);
  form(portfolio,`I${row}`,`=COUNTIFS('Runs'!C${rStart}:C${rEnd},A${row},'Runs'!N${rStart}:N${rEnd},1)`);
  form(portfolio,`J${row}`,`=COUNTIFS('Checks'!B${cStart}:B${cEnd},A${row})`);
  form(portfolio,`K${row}`,`=IF(COUNTIFS('Runs'!C${rStart}:C${rEnd},A${row},'Runs'!L${rStart}:L${rEnd},"INVALID")>0,"INVALID_RUN_DATA",IF(NOT(E${row}),IF(M${row}="","MISSING_SCOPE_REASON","OUT_OF_SCOPE"),IF(I${row}>0,"OPEN_FAILURE",IF(H${row}>0,"SUPPORTED",IF(AND(J${row}=0,F${row}),"UNTESTED","UNCERTAIN")))))`);
}
portfolio.getRange(`K${aStart}:K${aEnd}`).conditionalFormats.add('containsText',{text:'OPEN_FAILURE',format:{fill:'#FCE8E6',font:{color:'#B42318'}}});
warning(portfolio,`K${aStart}:K${aEnd}`);
set(portfolio,`A${aEnd+2}`,[['SUPPORTED is limited to the assertion and recorded revision. A later pass does not resolve an earlier failure.']]);
set(portfolio,`A${aEnd+3}`,[['Inventory completeness and requirement scope are declarations. Record scope reasons and all claim boundaries in the JSON input.']]);
portfolio.freezePanes.freezeRows(13);portfolio.freezePanes.freezeColumns(1);

base(checks,`K${cEnd+4}`,'Declared check inventory',[12,14,14,20,40,24,16,18,16,15,18]);
set(checks,'A3',[['SYNTHETIC. A repeated equivalence key is a consolidation candidate only when assertion, layer and boundary also match.']]);
set(checks,'A4',[['Changed scope is an editable declaration per check. Unknown impact selects all checks; unresolved failures remain selected.']]);
header(checks,6,['Check ID','Assertion ID','Behavior ID','Level','Boundary','Equivalence key','Effort minutes','In changed scope?','Open failures','Selected (1=yes)','Selected effort']);
set(checks,`A${cStart}`,p.checks.map(c=>[c.id,c.assertion_id,c.behavior_id,c.level,c.boundary,c.equivalence_key,c.effort_minutes,behaviorById[c.behavior_id].components.some(v=>p.changed_components.includes(v))]));
checks.getRange(`A${cStart}:H${cEnd}`).format.fill=inputFill;checks.getRange(`A${cStart}:K${cEnd}`).format.wrapText=true;checks.getRange(`A${cStart}:K${cEnd}`).format.rowHeight=42;
for(let row=cStart;row<=cEnd;row++){
  form(checks,`I${row}`,`=COUNTIFS('Runs'!B${rStart}:B${rEnd},A${row},'Runs'!N${rStart}:N${rEnd},1)`);
  form(checks,`J${row}`,`=IF(OR(NOT('Portfolio'!$H$4),H${row},I${row}>0),1,0)`);
  form(checks,`K${row}`,`=IF(J${row},IF(ISNUMBER(G${row}),G${row},"UNKNOWN"),"not selected")`);
}
checks.freezePanes.freezeRows(6);checks.freezePanes.freezeColumns(1);

base(runs,`N${rEnd+4}`,'Run evidence',[12,12,14,14,25,14,13,39,15,35,32,14,17,16]);
set(runs,'A3',[['SYNTHETIC. Every run is bound to one declared check, assertion and behavior. Evidence locators are not independently authenticated.']]);
set(runs,'A4',[['A failure closes only with a resolution date, source and disposition. Historical failures remain visible across revisions.']]);
header(runs,6,['Run ID','Check ID','Assertion ID','Behavior ID','Revision','Observed on','Result','Evidence locator','Resolved on','Resolution source','Disposition','Input validity','Current support (1=yes)','Open failure (1=yes)']);
set(runs,`A${rStart}`,p.runs.map(r=>[r.id,r.check_id,r.assertion_id,r.behavior_id,r.revision,dateValue(r.observed_on),r.result,r.artifacts.join('; '),dateValue(r.resolution?.resolved_on),r.resolution?.source_locator??null,r.resolution?.disposition??null]));
runs.getRange(`A${rStart}:K${rEnd}`).format.fill=inputFill;runs.getRange(`A${rStart}:N${rEnd}`).format.wrapText=true;runs.getRange(`A${rStart}:N${rEnd}`).format.rowHeight=54;
for(const col of ['F','I'])runs.getRange(`${col}${rStart}:${col}${rEnd}`).format.numberFormat='yyyy-mm-dd';
runs.getRange(`G${rStart}:G${rEnd}`).dataValidation={rule:{type:'list',values:['pass','fail','blocked','unknown']}};
for(let row=rStart;row<=rEnd;row++){
  const binding=`COUNTIFS('Checks'!A${cStart}:A${cEnd},B${row},'Checks'!B${cStart}:B${cEnd},C${row},'Checks'!C${cStart}:C${cEnd},D${row})=1`;
  const resolution=`OR(AND(I${row}="",J${row}="",K${row}=""),AND(G${row}="fail",ISNUMBER(I${row}),I${row}>=F${row},I${row}<='Portfolio'!$B$4,J${row}<>"",K${row}<>""))`;
  form(runs,`L${row}`,`=IF(AND(A${row}<>"",COUNTIFS(A${rStart}:A${rEnd},A${row})=1,${binding},ISNUMBER(F${row}),F${row}<='Portfolio'!$B$4,E${row}<>"",H${row}<>"",OR(G${row}="pass",G${row}="fail",G${row}="blocked",G${row}="unknown"),${resolution}),"VALID","INVALID")`);
  form(runs,`M${row}`,`=IF(AND(L${row}="VALID",G${row}="pass",E${row}='Portfolio'!$D$4,F${row}>='Portfolio'!$B$4-'Portfolio'!$F$4),1,0)`);
  form(runs,`N${row}`,`=IF(AND(G${row}="fail",OR(I${row}="",L${row}="INVALID")),1,0)`);
}
warning(runs,`L${rStart}:L${rEnd}`);runs.freezePanes.freezeRows(6);runs.freezePanes.freezeColumns(1);

const iStart=7,iEnd=iStart+p.improvements.length-1;
base(improvements,`G${iEnd+4}`,'Improvement assumptions',[13,17,18,18,58,60,25]);
set(improvements,'A3',[['SYNTHETIC. Gain and effort are analyst assumptions, not measured release confidence. Compare alternatives for the same assertion set.']]);
set(improvements,'A4',[['Edit gain and effort here for discussion. Run the CLI for same-scope dominance comparisons and retained source locators.']]);
header(improvements,6,['Proposal ID','Assertion IDs','Expected gain','Effort minutes','Action','Rationale','Input completeness']);
set(improvements,`A${iStart}`,p.improvements.map(v=>[v.id,v.assertion_ids.join('; '),v.expected_gain,v.effort_minutes,v.action,v.rationale]));
improvements.getRange(`A${iStart}:F${iEnd}`).format.fill=inputFill;improvements.getRange(`A${iStart}:G${iEnd}`).format.wrapText=true;improvements.getRange(`A${iStart}:G${iEnd}`).format.rowHeight=70;
improvements.getRange(`C${iStart}:C${iEnd}`).dataValidation={rule:{type:'list',values:['high','medium','low','unknown']}};
for(let row=iStart;row<=iEnd;row++)form(improvements,`G${row}`,`=IF(OR(C${row}="unknown",C${row}="",NOT(ISNUMBER(D${row}))),"UNKNOWN_ASSUMPTIONS",IF(D${row}<0,"INVALID_EFFORT","ASSESSED"))`);
warning(improvements,`G${iStart}:G${iEnd}`);improvements.freezePanes.freezeRows(6);

const original=p.source.rows;const sEnd=7+original.length-1;
base(source,`G${sEnd+5}`,'Published source table',[15,70,20,20,55,55,65]);
set(source,'A3',[['Source: https://github.com/woahwhattheheck/commons/blob/'+p.source.revision+'/revenue/uiowa_rfq_18649_build_board/45-testing-portfolio-example.csv']]);
set(source,'A4',[['Original source blob: '+p.source.git_blob+'. Original values below remain separate from the fictional run-record extension.']]);
header(source,6,['Service','Behavior','Test level','Coverage claim','Passing establishes','Passing does not establish','Portfolio note']);
set(source,'A7',original.map(r=>Object.values(r)));source.getRange(`A7:G${sEnd}`).format.wrapText=true;source.getRange(`A7:G${sEnd}`).format.rowHeight=88;source.freezePanes.freezeRows(6);

// Recalculate and inspect the actual authoring result. These diagnostics are not worksheet content.
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Portfolio!A6:H11',include:'values,formulas',tableMaxRows:6,tableMaxCols:8,maxChars:6000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:2000})).ndjson);
await fs.mkdir(outputDir,{recursive:true});
for(const [sheet,end] of [[portfolio,`M${aEnd}`],[checks,`K${cEnd}`],[runs,`N${rEnd}`],[improvements,`G${iEnd}`],[source,`G${sEnd}`]]){
  const preview=await wb.render({sheetName:sheet.name,range:`A1:${end}`,scale:1,format:'png'});
  await fs.writeFile(path.join(outputDir,sheet.name.replaceAll(' ','-')+'.png'),new Uint8Array(await preview.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(path.join(outputDir,'testing-portfolio.xlsx'));
console.log(JSON.stringify({output:path.join(outputDir,'testing-portfolio.xlsx'),sheets:sheets.map(s=>s.name),status:'exported'}));
