import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const [input, output, font = 'Arial'] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node build.mjs prepared-deck.json output.pptx [font]');
const deck = JSON.parse(await fs.readFile(input, 'utf8'));
const presentation = Presentation.create({slideSize: {width: 1280, height: 720}});
const text = (slide, name, value, x, y, w, h, size, color = '#19313D', bold = false) => {
  const shape = slide.shapes.add({geometry: 'textbox', name,
    position: {left: x, top: y, width: w, height: h},
    fill: 'none', line: {fill: 'none', width: 0}});
  shape.text = value;
  shape.text.style = {typeface: font, fontSize: size, color, bold, autoFit: 'none'};
  return shape;
};
for (const [index, source] of deck.slides.entries()) {
  const slide = presentation.slides.add();
  slide.background.fill = '#FFFFFF';
  text(slide, 'title', source.title, 64, 42, 1152, 105, 42, '#163B49', true);
  for (const [i, bullet] of (source.bullets ?? []).entries()) {
    text(slide, `point-${i}`, bullet, 64, 166 + i * 75, 1152, 70, 28);
  }
  for (const [i, claim] of (source.claims ?? []).entries()) {
    let content;
    if ('value' in claim) content = `${claim.cites}   ${claim.measure.replaceAll('_', ' ')}: ${claim.value} ${claim.unit ?? ''}`;
    else if ('phase' in claim) content = `${claim.cites}   ${claim.phase}: ${claim.text}`;
    else content = `${claim.cites}   ${claim.text}`;
    text(slide, `claim-${i}`, content, 64, 418 + i * 46, 1152, 44, 23,
      claim.value === 'UNKNOWN' ? '#8C490A' : '#006653');
  }
  const links = source.track === 'core' ? source.appendix_support ?? [] :
    deck.slides.filter(s => (s.appendix_support ?? []).includes(source.id)).map(s => s.id);
  links.forEach((id, i) => text(slide, `jump-${id}`,
    `${source.track === 'core' ? 'Supporting detail' : 'Return'} ${id}`,
    64 + i * 275, 628, 260, 34, 22, '#205D90'));
  text(slide, 'fiction-label', `SYNTHETIC EXAMPLE. No University findings.   ${source.id}   ${index + 1}/${deck.slides.length}`,
    64, 678, 1152, 25, 17, '#56646C');
  slide.speakerNotes.textFrame.setText([
    deck.meta.fiction_notice ?? '',
    `Slide ${source.id}. Source report: ${deck.meta.report_ref}.`,
    ...(source.speaker_notes ?? []),
    'Exact claim records:', JSON.stringify(source.claims ?? [], null, 2),
  ].join('\n\n'));
}
await fs.mkdir(path.dirname(path.resolve(output)), {recursive: true});
await (await PresentationFile.exportPptx(presentation)).save(output);
console.log(`WROTE ${deck.slides.length} editable slides`);
