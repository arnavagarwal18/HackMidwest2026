// Sentence, chip and jump rendering. The Instructor chat panel reuses these for its own answers.
//
// A "jump context" is { index, jumper }: index from buildMeasurementIndex(analysis), jumper from createJumper(...).
// A sentence is { text, cites | measurement_ids, jump: { bar, time_s }, checked }.
import { button, element } from '../dom.js';
import { chipLabel, resolveId, resolveJump } from './measurements.js';

// A small chip for one cited measurement id; clicking it jumps to that bar or time.
export function renderChip(id, jumpContext) {
  const place = resolveId(id, jumpContext.index);
  if (!place) {
    console.warn(`A sentence cites ${id}, which is not in this take's results.`);
    return element('span', id, 'chip chip-unknown', { title: 'Not found in this take' });
  }
  const chip = button(chipLabel(id, place), () => jumpContext.jumper.jumpTo(place), 'chip');
  chip.dataset.cites = id;
  return chip;
}

// One sentence as an <li>: the text (a jump button when it has a jump), then chips.
export function renderSentence(sentence, jumpContext) {
  const item = element('li', '', 'sentence');
  const place = resolveJump(sentence.jump, jumpContext.index);
  item.append(place ? button(sentence.text, () => jumpContext.jumper.jumpTo(place), 'sentence-text') : element('span', sentence.text, 'sentence-text'));
  (sentence.cites ?? sentence.measurement_ids ?? []).forEach((id) => item.append(renderChip(id, jumpContext)));
  return item;
}

export function renderSentenceList(sentences, jumpContext) {
  const list = element('ul', '', 'sentences');
  sentences.forEach((sentence) => list.append(renderSentence(sentence, jumpContext)));
  return list;
}
