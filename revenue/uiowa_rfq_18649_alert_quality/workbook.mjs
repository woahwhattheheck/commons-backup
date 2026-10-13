/** Export a reviewed report snapshot with editable operational follow-through. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [reportPath, outputPath, previewDir] = process.argv.slice(2);
if (!reportPath || !outputPath) {
  throw new Error('Usage: node workbook.mjs REPORT.json OUTPUT.xlsx [PREVIEW_DIRECTORY]');
}
const report = JSON.parse(await fs.readFile(reportPath, 'utf8'));
if (report.schema !== 'uiowa.alert-quality-report/v1' || report.evidence_class !== 'SYNTHETIC') {
  throw new Error('Expected the synthetic v1 alert-quality report produced by alert_quality.py');
}
const wb = Workbook.create();
const palette = {ink: '#25354A', muted: '#5D6A7C', header: '#344D6B', input: '#FFF2CC'};
const literal = value => {
  if (value === null || value === undefined) return 'UNKNOWN';
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'string' && /^[\s]*[=+@-]/.test(value)) return "'" + value;
  return value;
};
const column = index => {
  let result = '';
  for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) {
    result = String.fromCharCode(65 + (n - 1) % 26) + result;
  }
  return result;
};
function sheet(name, title, description, headers, rows, widths) {
  const s = wb.worksheets.add(name);
  const last = column(headers.length - 1);
  const end = Math.max(6, rows.length + 5);
  s.showGridLines = false;
  s.getRange(`A1:${last}${end}`).format.font = {name: 'Arial', size: 10, color: palette.ink};
  s.getRange('A2').values = [[title]];
  s.getRange('A2').format.font = {name: 'Arial', size: 14, bold: true, color: palette.ink};
  s.getRange('A3').values = [[description]];
  s.getRange('A3').format.font = {name: 'Arial', size: 10, italic: true, color: palette.muted};
  s.getRange(`A5:${last}5`).values = [headers];
  s.getRange(`A5:${last}5`).format = {
    fill: palette.header, font: {name: 'Arial', size: 10, bold: true, color: '#FFFFFF'},
    wrapText: true, horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 32,
  };
  if (rows.length) {
    s.getRange(`A6:${last}${end}`).values = rows.map(row => row.map(literal));
    s.getRange(`A6:${last}${end}`).format.verticalAlignment = 'top';
    s.getRange(`A6:${last}${end}`).format.wrapText = true;
    s.getRange(`A6:${last}${end}`).format.rowHeight = 54;
    s.tables.add(`A5:${last}${end}`, true, `${name}Records`);
  }
  widths.forEach((width, i) => {s.getRange(`${column(i)}1:${column(i)}${end}`).format.columnWidth = width;});
  if (rows.length > 10 || headers.length > 7) s.freezePanes.freezeRows(5);
  return s;
}
const definitions = {
  notifications: 'Observed notification records', observed_episodes: 'Explicitly grouped or unlinked episodes',
  confirmed_duplicates: 'Evidence-linked repeat deliveries', reviewed_redundant: 'Reviewed as redundant',
  reviewed_useful: 'Reviewed as useful', unreviewed: 'Usefulness unknown',
  redundant_share_of_reviewed: 'Redundant / (redundant + useful), excludes unknown',
  explicitly_unowned_episodes: 'Explicitly unowned episodes', unknown_owner_episodes: 'Ownership unknown',
  impacting_episodes: 'Episodes with recorded impact', completed_response_sample_n: 'Completed response sample (n)',
  median_action_minutes_completed_only: 'Median useful response (minutes), completed only',
};
const overviewRows = Object.entries(report.summary).map(([key, value]) => [definitions[key] || key, value]);
const overview = sheet('Overview', 'Alert usefulness and response readiness',
  'SYNTHETIC preparation. Snapshot of the analyzed history; no University findings.',
  ['Measure', 'Observed value'], overviewRows, [69, 24]);
overview.tabColor = palette.header;
overview.getRange('B6:B17').format.numberFormat = '#,##0';
overview.getRange('B17').format.numberFormat = '0.0';
overview.getRange(`B${6 + Object.keys(report.summary).indexOf('redundant_share_of_reviewed')}`).format.numberFormat = '0.0%';
overview.getRange('A6:B17').format.rowHeight = 24;
overview.getRange('A20').values = [['Observation window (UTC)']];
overview.getRange('A21').values = [[`${report.window.start} to ${report.window.end} (end excluded)`]];
overview.getRange('A23').values = [['Meaningful action differs from acknowledgement. Unknown response is never zero.']];
overview.getRange('A25').values = [['Workbook inputs: amber cells in Actions and Interview.']];
overview.getRange('A27').values = [['To change evidence, rerun the analyzer and regenerate this snapshot. Retain annotated copies separately.']];
overview.getRange('A20:B28').format.font = {name:'Arial',size:10,color:palette.ink};
overview.getRange('A20:A28').format.wrapText = true;
overview.getRange('A27:B28').format.rowHeight = 30;

const actions = sheet('Actions', 'Evidence-linked improvement register',
  'Amber fields are editable review notes. Each proposed change retains its episode and evidence IDs.',
  ['Recommendation ID','Episode','Proposed change','Outcome to measure','Evidence IDs','Assigned role','Decision and rationale','Next step / retained result'],
  report.recommendations.map(r => [r.id,r.episode_id,r.proposed_change,r.outcome_check,r.evidence_ids,'','','']),
  [42,18,64,66,38,25,50,55]);
actions.getRange(`F6:H${5 + report.recommendations.length}`).format.fill = palette.input;
actions.getRange(`A6:H${5 + report.recommendations.length}`).format.rowHeight = 54;

const epKeys = ['episode_id','service','incident_id','impact','notifications','confirmed_duplicates','ack_minutes','action_minutes','response_state','latency_basis','owner_status','owner','runbook_status','escalation_status','notification_ids'];
const episodes = sheet('Episodes', 'Episode evidence and response',
  'Latencies are minutes from the first observed notification. Partial history produces a lower bound.',
  ['Episode','Service','Incident','Impact','Notifications','Duplicates','Ack (min)','Useful action (min)','Response evidence','Latency basis','Ownership','Assigned role','Runbook','Escalation','Notification IDs'],
  report.episodes.map(r => epKeys.map(k => r[k])), [20,16,20,12,16,14,15,18,42,38,18,24,20,20,38]);
episodes.getRange(`E6:F${5 + report.episodes.length}`).format.numberFormat = '#,##0';
episodes.getRange(`G6:H${5 + report.episodes.length}`).format.numberFormat = '0.0';

const evidence = sheet('Evidence', 'Retained example evidence',
  `Source snapshot SHA-256: ${report.input_sha256}`,
  ['Evidence ID','Locator','Excerpt'], report.evidence.map(r => [r.id,r.locator,r.excerpt]), [25,64,108]);
evidence.getRange(`A6:C${5 + report.evidence.length}`).format.rowHeight = 42;
const prompts = [
  ['Grouping','Which retained incident or correlation record links these notifications? Could the same rule have fired for a separate incident?'],
  ['Usefulness','What useful action did each notification enable? Which repeats added no information?'],
  ['Escalation','Did a later route reach someone able to act? Preserve useful escalation when reducing repeats.'],
  ['Ownership','Which role is accountable for first useful response? What evidence distinguishes unowned from unknown ownership?'],
  ['Response','What changed after acknowledgement? Retain action timestamps and a description of meaningful work.'],
  ['Runbook','Which diagnostic step helped during an observed task? A link alone does not prove usefulness.'],
  ['Coverage','Which exports, routes or intervals are missing? Could the true first notification precede this window?'],
  ['Outcomes','What comparison will show reduced wasted effort or faster useful response without suppressing incident detection?'],
];
const interview = sheet('Interview', 'Operational interview worksheet',
  'Use role names and evidence locators. Missing records remain unknown; no individual performance scoring.',
  ['Topic','Prompt','Recorded observation','Evidence locator','Follow-up'], prompts.map(r => [...r,'','','']), [19,100,65,54,65]);
interview.getRange(`C6:E${5 + prompts.length}`).format.fill = palette.input;
interview.getRange(`A6:E${5 + prompts.length}`).format.rowHeight = 65;

wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Overview!A5:B17',include:'values',tableMaxRows:13,tableMaxCols:2,maxChars:2500})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:10},maxChars:1000})).ndjson);
await fs.mkdir(path.dirname(outputPath), {recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(outputPath);
if (previewDir) {
  await fs.mkdir(previewDir,{recursive:true});
  for (const [name, range] of [['Overview','A1:B28'],['Actions','A1:D9'],['Episodes','A1:J11'],['Evidence','A1:C11'],['Interview','A1:C10']]) {
    const rendered = await wb.render({sheetName:name,range,scale:1,format:'png'});
    await fs.writeFile(path.join(previewDir,name+'.png'),new Uint8Array(await rendered.arrayBuffer()));
  }
}
console.log(JSON.stringify({workbook:outputPath,episodes:report.episodes.length,recommendations:report.recommendations.length}));
