#!/usr/bin/env node
/** Current JavaScript SDK view of the original Python component assessment. */
import fs from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const run = promisify(execFile);
const sourceDirectory = dirname(fileURLToPath(import.meta.url));
const navy = '#16324F', pale = '#DCE6F1';
const bridge = [
  'import sys',
  'from pathlib import Path',
  'sys.path.insert(0, sys.argv[1])',
  'from components import load, json_bytes',
  'from workbook import workbook_payload',
  'sys.stdout.buffer.write(json_bytes(workbook_payload(load(Path(sys.argv[2])))))',
].join('\n');

export async function loadWorkbookInput(input) {
  const python = process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3';
  const { stdout } = await run(python, ['-B', '-c', bridge, sourceDirectory, resolve(input)],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  return JSON.parse(stdout);
}

function merged(sheet, address, text, format) {
  const range = sheet.getRange(address);
  range.merge();
  sheet.getRange(address.split(':')[0]).values = [[text]];
  if (format) range.format = format;
}

function typedValue(value, column) {
  return /(_on|_until)$/.test(column) && value
    ? new Date(value + 'T00:00:00Z') : value;
}

export function buildWorkbook(payload) {
  const report = payload.report;
  const workbook = Workbook.create();
  const cover = workbook.worksheets.add('Overview');
  const sheets = new Map(payload.sheets.map(spec => [spec.name, workbook.worksheets.add(spec.name)]));
  const decisions = workbook.worksheets.add('Decisions');
  const ends = new Map();

  cover.showGridLines = false;
  cover.tabColor = navy;
  cover.getRange('A1:H30').format = {
    columnWidth: 13, rowHeight: 23, wrapText: true,
    font: { name: 'Arial', size: 11 }, verticalAlignment: 'center',
  };
  merged(cover, 'A1:H2', 'COMPONENT MAINTENANCE | FICTIONAL REHEARSAL',
    { fill: navy, font: { bold: true, color: '#FFFFFF', size: 15 } });
  merged(cover, 'A3:H4', 'UIOWA-056 | Supplied-record assessment as of ' + report.as_of +
    '. No real University data, product recommendations, live probes, or authority to change systems.');

  for (const spec of payload.sheets) {
    const sheet = sheets.get(spec.name);
    const end = Math.max(4, spec.values.length + 3);
    ends.set(spec.name, end);
    sheet.showGridLines = false;
    const area = sheet.getRangeByIndexes(0, 0, end, spec.columns.length);
    area.format = {
      columnWidth: 20, rowHeight: 54, wrapText: true,
      font: { name: 'Arial', size: 11 }, verticalAlignment: 'top',
    };
    const lastColumn = columnName(spec.columns.length);
    merged(sheet, 'A1:' + lastColumn + '1', spec.name + ' | Generated snapshot; retain evidence IDs',
      { fill: navy, font: { bold: true, color: '#FFFFFF', size: 14 }, verticalAlignment: 'center' });
    merged(sheet, 'A2:' + lastColumn + '2',
      'Fictional supplied records. UNKNOWN or blank is not a low maturity score or a clean bill of health. Modify canonical input and regenerate to change assessed states.');
    const header = sheet.getRangeByIndexes(2, 0, 1, spec.columns.length);
    header.values = [spec.columns.map(name => name.replaceAll('_', ' '))];
    header.format = { fill: pale, font: { bold: true }, rowHeight: 64,
      horizontalAlignment: 'center', verticalAlignment: 'center' };
    if (spec.values.length) {
      sheet.getRangeByIndexes(3, 0, spec.values.length, spec.columns.length).values =
        spec.values.map(row => row.map((value, index) => typedValue(value, spec.columns[index])));
      sheet.tables.add('A3:' + lastColumn + end, true, 'T' + spec.name);
    }
    header.format.font.color = navy;
    spec.columns.forEach((column, index) => {
      const range = sheet.getRangeByIndexes(3, index, Math.max(1, spec.values.length), 1);
      if (/(_on|_until)$/.test(column)) range.setNumberFormat('yyyy-mm-dd');
      if (column.startsWith('effort_')) range.setNumberFormat('0.0');
      if (['priority', 'advisory_record_count'].includes(column)) range.setNumberFormat('0');
      if (['evidence_ids', 'reasons', 'coordination_notes', 'change', 'locator'].includes(column)) {
        range.format.columnWidth = 38;
        range.format.rowHeight = 108;
      }
    });
    sheet.getRangeByIndexes(0, 0, 1, spec.columns.length).format.rowHeight = 34;
    if (spec.values.length) {
      sheet.getRangeByIndexes(3, 0, spec.values.length, spec.columns.length).format.autofitRows();
      for (let row = 3; row < end; row++) {
        const line = sheet.getRangeByIndexes(row, 0, 1, spec.columns.length);
        line.format.rowHeight += 6;
      }
    }
    sheet.freezePanes.freezeRows(3);
    sheet.freezePanes.freezeColumns(['Components', 'Advisories', 'Roadmap'].includes(spec.name) ? 2 : 1);
  }

  for (const [address, text] of [
    ['A6:B6', 'Recorded components'], ['C6:D6', 'Maintenance items'],
    ['E6:F6', 'Unestimated items'], ['G6:H6', 'Known effort (person-days)'],
  ]) merged(cover, address, text);
  for (const address of ['A7:B8', 'C7:D8', 'E7:F8', 'G7:H8']) cover.getRange(address).merge();
  const compEnd = ends.get('Components'), roadEnd = ends.get('Roadmap');
  cover.getRange('A7').formulas = [['=COUNTA(Components!A4:A' + compEnd + ')']];
  cover.getRange('C7').formulas = [['=COUNTA(Roadmap!A4:A' + roadEnd + ')']];
  cover.getRange('E7').formulas = [['=COUNTA(Roadmap!A4:A' + roadEnd + ')-COUNT(Roadmap!G4:G' + roadEnd + ')']];
  cover.getRange('G7').formulas = [['=SUM(Roadmap!G4:G' + roadEnd + ')&" to "&SUM(Roadmap!H4:H' + roadEnd + ')&" days"']];
  cover.getRange('A6:H8').format = { fill: '#E7F0F8', font: { bold: true }, horizontalAlignment: 'center' };
  cover.getRange('A6:H6').format.rowHeight = 36;
  cover.getRange('A7:H8').format.font.size = 16;
  cover.getRange('A10:B14').values = [
    ['Support state', 'Components'], ['supported', null], ['ending_soon', null],
    ['unsupported', null], ['unknown', null],
  ];
  cover.getRange('A10:B10').format = { fill: pale, font: { bold: true } };
  for (let row = 11; row <= 14; row++) {
    cover.getRange('B' + row).formulas = [['=COUNTIF(Components!E4:E' + compEnd + ',A' + row + ')']];
  }
  const notes = [
    [10, 'READING THE WORKBOOK'],
    [11, 'Components: version, service scope, declared support and qualified evidence.'],
    [12, 'Advisories: applicability, reported exposure and disposition stay separate.'],
    [13, 'Roadmap: one row per shared component; effort is not multiplied by services.'],
    [14, 'Decisions: editable preparation notes only. Evidence: source IDs and dates.'],
  ];
  for (const [row, text] of notes) merged(cover, 'D' + row + ':H' + row, text);
  cover.getRange('A11:H14').format.rowHeight = 36;
  cover.getRange('D10:H10').format.font.bold = true;
  merged(cover, 'A16:H18', report.limitations);
  merged(cover, 'A20:H21',
    'Practice-reference context: https://csrc.nist.gov/projects/ssdf — outcome-based secure-development guidance, not a certification checklist. The thresholds in this instrument are configurable preparation assumptions, not NIST requirements.');
  merged(cover, 'A23:H24', 'Canonical input SHA-256: ' + payload.canonical_input_sha256);
  merged(cover, 'A26:D26', 'Services: ' + report.summary.service_count);
  merged(cover, 'E26:H26', 'Advisory records: ' + report.summary.advisory_record_count);
  merged(cover, 'A27:D28', 'Evidence freshness: ' + report.parameters.max_evidence_age_days + ' days');
  merged(cover, 'E27:H28', 'Planning horizon: ' + report.parameters.horizon_days + ' days');
  merged(cover, 'A30:H30', 'Unestimated items are additional; known effort is not a complete project duration.');
  cover.getRange('A30:H30').format.rowHeight = 36;
  cover.freezePanes.freezeRows(4);

  decisions.showGridLines = false;
  const lastDecision = Math.max(30, payload.decisions.length + 1);
  decisions.getRange('A1:F' + lastDecision).format = {
    columnWidth: 24, rowHeight: 42, wrapText: true,
    font: { name: 'Arial', size: 11 }, verticalAlignment: 'center',
  };
  decisions.getRange('D1:E' + lastDecision).format.columnWidth = 38;
  decisions.getRange('A1:F1').values = [[
    'Component', 'Owner role', 'Proposed decision', 'Rationale / constraints',
    'Evidence reference', 'Next review date',
  ]];
  decisions.getRange('A1:F1').format = {
    fill: navy, font: { bold: true, color: '#FFFFFF' }, horizontalAlignment: 'center',
  };
  if (payload.decisions.length) {
    decisions.getRangeByIndexes(1, 0, payload.decisions.length, 6).values = payload.decisions;
    decisions.tables.add('A1:F' + (payload.decisions.length + 1), true, 'TDecisions');
    decisions.getRangeByIndexes(1, 2, payload.decisions.length, 1).dataValidation = {
      rule: { type: 'list', values: ['Investigate', 'Plan', 'Defer', 'No change'] },
    };
  }
  decisions.getRange('B2:F' + lastDecision).format.font.color = '#1D4ED8';
  decisions.getRange('F2:F' + lastDecision).setNumberFormat('yyyy-mm-dd');
  decisions.freezePanes.freezeRows(1);
  return workbook;
}

function columnName(index) {
  let result = '';
  for (let n = index; n > 0; n = Math.floor((n - 1) / 26)) result = String.fromCharCode(65 + (n - 1) % 26) + result;
  return result;
}

async function exportExclusive(workbook, destination) {
  const output = resolve(destination);
  const temporary = await fs.mkdtemp(resolve(dirname(output), '.component-workbook-'));
  const staging = resolve(temporary, 'workbook.xlsx');
  try {
    const file = await SpreadsheetFile.exportXlsx(workbook);
    await file.save(staging);
    const bytes = await fs.readFile(staging);
    const handle = await fs.open(output, 'wx', 0o600);
    try { await handle.writeFile(bytes); await handle.sync(); }
    finally { await handle.close(); }
  } finally {
    // Read owned export files before removing them, including the SDK sidecar.
    for (const path of [staging, staging + '.inspect.ndjson']) {
      try { await fs.readFile(path); await fs.unlink(path); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    await fs.rmdir(temporary);
  }
}

async function main(args) {
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
    console.log('Usage: node workbook.mjs INPUT.json --out NEW_WORKBOOK.xlsx');
    return;
  }
  if (args.length !== 3 || args[1] !== '--out') throw new Error('Usage: node workbook.mjs INPUT.json --out NEW_WORKBOOK.xlsx');
  const [input, , destination] = args;
  try {
    await fs.lstat(destination);
    throw new Error('workbook exists; select a new output path');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const payload = await loadWorkbookInput(input);
  const workbook = buildWorkbook(payload);
  workbook.recalculate();
  await exportExclusive(workbook, destination);
  console.log(JSON.stringify({ workbookCreated: true, sheetCount: 7,
    canonicalInputSha256: payload.canonical_input_sha256, assessmentSha256: payload.assessment_sha256 }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).catch(error => {
    console.error('Workbook not completed: ' + (error.stderr?.trim() || error.message));
    process.exitCode = 2;
  });
}
