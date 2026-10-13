import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const [reportPath,outputDir]=process.argv.slice(2);
if(!reportPath||!outputDir)throw new Error('Usage: build_workbook.mjs worked-report.json output-directory');
const report=JSON.parse(await fs.readFile(reportPath,'utf8'));
if(report.stages.length!==13||report.stages.some((s,i)=>Number(s.source.stage_order)!==i+1))throw new Error('Workbook expects the published 13-stage example in order');
const wb=Workbook.create(),timing=wb.worksheets.add('Timing'),evidence=wb.worksheets.add('Evidence'),source=wb.worksheets.add('Source timing');
const dark='#243B53',amber='#FFF4CF',light='#E9EFF4';
const put=(s,a,v)=>{s.getRange(a).values=v;},formula=(s,a,v)=>{s.getRange(a).formulas=[[v]];};
function layout(s,end,title,widths){
  s.showGridLines=false;s.getRange(`A1:${end}`).format.font={name:'Arial',size:10,color:'#243040'};s.getRange(`A1:${end}`).format.verticalAlignment='center';
  put(s,'A2',[[title]]);s.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:dark};
  s.getRange(`A2:${end.match(/[A-Z]+/)[0]}2`).format.borders={bottom:{style:'thin',color:dark}};
  widths.forEach((w,i)=>s.getRangeByIndexes(0,i,Number(end.match(/\d+/)[0]),1).format.columnWidth=w);
}
function header(s,row,values){
  const r=s.getRangeByIndexes(row-1,0,1,values.length);r.values=[values];r.format={fill:dark,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',wrapText:true,rowHeight:38};
}
const rows=report.stages.map(s=>s.source),first=10,last=22;
layout(timing,'K27','Change trace timing',[24,46,18,20,22,25,25,25,21,22,20]);timing.tabColor=dark;
put(timing,'A3',[['SYNTHETIC. Intervals are elapsed calendar hours, not person-hours. Missing acceptance evidence and timing remain unknown.']]);
put(timing,'A4',[['Advance triage (hours)',3,null,'Maximum valid advance',null,null,'Scenario input']]);timing.getRange('B4').format.fill=amber;
formula(timing,'E4',"=('Source timing'!D8-'Source timing'!C8)*24");
formula(timing,'H4','=IF(AND(ISNUMBER(B4),B4>=0,B4<=E4),"VALID","INVALID_ADVANCE")');
timing.getRange('B4').dataValidation={rule:{type:'decimal',operator:'between',formula1:0,formula2:'$E$4'}};
put(timing,'A6',[['Observed endpoint hours',null,null,'Known queue hours',null,null,null,'Known work-span hours']]);
formula(timing,'B6',"=(MAX('Source timing'!E7:E19)-MIN('Source timing'!C7:C19))*24");formula(timing,'E6','=SUM(D10:D22)');formula(timing,'I6','=SUM(E10:E22)');
put(timing,'A7',[['Scenario endpoint hours',null,null,'Scenario queue hours',null,null,null,'Missing timing stages']]);
formula(timing,'B7','=IF(H4="VALID",(MAX(H10:H22)-MIN(F10:F22))*24,"INVALID_ADVANCE")');formula(timing,'E7','=IF(H4="VALID",SUM(I10:I22),"INVALID_ADVANCE")');formula(timing,'I7','=COUNTIFS(D10:D22,"UNKNOWN")');
timing.getRange('A6:B7').format.fill=light;timing.getRange('D6:E7').format.fill=light;timing.getRange('H6:I7').format.fill=light;
header(timing,9,['Stage','Name','Evidence status','Observed queue hours','Observed work-span hours','Scenario queue entry (UTC)','Scenario work start (UTC)','Scenario work end (UTC)','Scenario queue hours','Scenario work-span hours','Queue delta hours']);
put(timing,'A10',rows.map(r=>[Number(r.stage_order),r.stage_name,r.status]));
for(let r=first;r<=last;r++){
  const sr=r-3;
  formula(timing,`D${r}`,`=IF(AND(ISNUMBER('Source timing'!C${sr}),ISNUMBER('Source timing'!D${sr})),('Source timing'!D${sr}-'Source timing'!C${sr})*24,"UNKNOWN")`);
  formula(timing,`E${r}`,`=IF(AND(ISNUMBER('Source timing'!D${sr}),ISNUMBER('Source timing'!E${sr})),('Source timing'!E${sr}-'Source timing'!D${sr})*24,"UNKNOWN")`);
  for(const [target,sourceCol,stage] of [['F','C',3],['G','D',2],['H','E',2]])formula(timing,`${target}${r}`,`=IF(ISNUMBER('Source timing'!${sourceCol}${sr}),IF($H$4="VALID",'Source timing'!${sourceCol}${sr}-IF(A${r}=${stage},$B$4/24,0),"INVALID_ADVANCE"),"")`);
  formula(timing,`I${r}`,`=IF($H$4<>"VALID","INVALID_ADVANCE",IF(AND(ISNUMBER(F${r}),ISNUMBER(G${r})),(G${r}-F${r})*24,"UNKNOWN"))`);
  formula(timing,`J${r}`,`=IF($H$4<>"VALID","INVALID_ADVANCE",IF(AND(ISNUMBER(G${r}),ISNUMBER(H${r})),(H${r}-G${r})*24,"UNKNOWN"))`);
  formula(timing,`K${r}`,`=IF($H$4<>"VALID","INVALID_ADVANCE",IF(AND(ISNUMBER(D${r}),ISNUMBER(I${r})),I${r}-D${r},"UNKNOWN"))`);
}
timing.getRange('A10:K22').format.rowHeight=42;timing.getRange('A10:K22').format.wrapText=true;
timing.getRange('D10:E22').format.numberFormat='0.000000';timing.getRange('I10:K22').format.numberFormat='0.000000';timing.getRange('F10:H22').format.numberFormat='yyyy-mm-dd hh:mm';
for(const a of ['B6:B7','E6:E7','I6','E4'])timing.getRange(a).format.numberFormat='0.000000';
put(timing,'A24',[['Scenario: triage starts and ends earlier; stage 3 receives its handoff earlier. All later work starts and ends stay fixed.']]);
put(timing,'A25',[['At a three-hour advance, triage waiting falls by three hours and the next queue grows by three hours. End-to-end observed time is unchanged.']]);
put(timing,'A26',[['Set the amber input to zero to restore observed timing. Evidence conclusions never change with the timing assumption.']]);
timing.getRange('H4').conditionalFormats.add('containsText',{text:'INVALID',format:{fill:'#FCE8E6',font:{color:'#B42318',bold:true}}});
timing.freezePanes.freezeRows(9);timing.freezePanes.freezeColumns(2);

layout(source,'H22','Source timing and stated intervals',[12,46,25,25,25,22,22,28]);
put(source,'A3',[['Source: repaired 041 synthetic trace, Git blob '+report.source.git_blob+'. Original offset-qualified timestamp strings remain in the CSV and JSON report.']]);
put(source,'A4',[['UTC date cells are typed copies of those original timestamps. Source active_hours is an elapsed span label; it does not establish labor effort.']]);
header(source,6,['Stage','Name','Queue entry (UTC)','Work start (UTC)','Work end (UTC)','Stated queue hours','Stated active_hours','Evidence reference']);
put(source,'A7',rows.map(r=>[Number(r.stage_order),r.stage_name,...['queue_enter','work_start','work_end'].map(k=>r[k]?new Date(r[k]):null),r.queue_wait_hours===''?null:Number(r.queue_wait_hours),r.active_hours===''?null:Number(r.active_hours),r.evidence_ref]));
source.getRange('A7:H19').format.rowHeight=45;source.getRange('A7:H19').format.wrapText=true;source.getRange('C7:E19').format.numberFormat='yyyy-mm-dd hh:mm';source.getRange('F7:G19').format.numberFormat='0.00';source.freezePanes.freezeRows(6);source.freezePanes.freezeColumns(2);

layout(evidence,'O22','Evidence and interview follow-up',[10,42,18,24,60,65,30,25,65,20,65,65,65,24,24]);
put(evidence,'A3',[['SYNTHETIC. Source conclusions are retained. Add interview responses in the amber column without overwriting the source statements.']]);
put(evidence,'A4',[['Source change '+rows[0].change_id+', group '+rows[0].group+'. Evidence identifiers refer to the original fictional example.']]);
header(evidence,6,['Stage','Name','Status','Owner role','Documented expectation','Observed activity','Evidence reference','Evidence type','Evidence meaning','Exception','Gap or conflict','Follow-up question','Reviewer response','Handoff from','Handoff to']);
put(evidence,'A7',rows.map(r=>[Number(r.stage_order),r.stage_name,r.status,r.owner_role,r.documented_expected,r.observed_activity,r.evidence_ref,r.evidence_type,r.evidence_semantics,r.exception_type,r.gap_or_conflict,r.follow_up_question,null,r.handoff_from,r.handoff_to]));
evidence.getRange('A7:O19').format.rowHeight=70;evidence.getRange('A7:O19').format.wrapText=true;evidence.getRange('M7:M19').format.fill=amber;
evidence.getRange('C7:C19').conditionalFormats.add('containsText',{text:'UNKNOWN',format:{fill:amber,font:{bold:true}}});evidence.getRange('C7:C19').conditionalFormats.add('containsText',{text:'CONFLICT',format:{fill:'#FCE8E6',font:{color:'#B42318',bold:true}}});
evidence.freezePanes.freezeRows(6);evidence.freezePanes.freezeColumns(3);

wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Timing!A4:K7',include:'values,formulas',tableMaxRows:4,tableMaxCols:11,maxChars:3500})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
await fs.mkdir(outputDir,{recursive:true});
for(const [sheet,range,label] of [[timing,'A1:K26','Timing'],[source,'A1:H19','Source-timing'],[evidence,'A1:H19','Evidence-left'],[evidence,'I6:O19','Evidence-right']]){
  const png=await wb.render({sheetName:sheet.name,range,scale:1,format:'png'});await fs.writeFile(path.join(outputDir,label+'.png'),new Uint8Array(await png.arrayBuffer()));
}
await(await SpreadsheetFile.exportXlsx(wb)).save(path.join(outputDir,'change-trace.xlsx'));
console.log(JSON.stringify({output:path.join(outputDir,'change-trace.xlsx'),status:'exported'}));
