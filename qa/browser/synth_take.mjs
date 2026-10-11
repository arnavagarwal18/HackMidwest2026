// Writes a short synthetic "played" take (16-bit mono WAV): a sine with two harmonics per note, so the back end can transcribe it.
// Concert pitches of Twinkle, Twinkle bars 1-2 (C C G G A A G); the take starts with a short silence.
import { writeFileSync } from 'node:fs';

const SAMPLE_RATE = 22050;
const NOTE_SECONDS = 0.6;
const LEAD_SILENCE_SECONDS = 0.5;
const CONCERT_HZ = [261.63, 261.63, 392.0, 392.0, 440.0, 440.0, 392.0];

export function synthTakeWav(path, notesHz = CONCERT_HZ) {
  const noteSamples = Math.round(NOTE_SECONDS * SAMPLE_RATE);
  const lead = Math.round(LEAD_SILENCE_SECONDS * SAMPLE_RATE);
  const samples = new Int16Array(lead + notesHz.length * noteSamples);
  notesHz.forEach((hz, n) => {
    for (let i = 0; i < noteSamples; i++) {
      const t = i / SAMPLE_RATE;
      const envelope = Math.min(1, i / 400, (noteSamples - i) / 400);
      const wave = Math.sin(2 * Math.PI * hz * t) + 0.5 * Math.sin(4 * Math.PI * hz * t) + 0.25 * Math.sin(6 * Math.PI * hz * t);
      samples[lead + n * noteSamples + i] = Math.round(8000 * envelope * wave);
    }
  });
  const header = Buffer.alloc(44);
  header.write('RIFF', 0); header.writeUInt32LE(36 + samples.byteLength, 4); header.write('WAVEfmt ', 8);
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
  header.writeUInt32LE(SAMPLE_RATE, 24); header.writeUInt32LE(SAMPLE_RATE * 2, 28); header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
  header.write('data', 36); header.writeUInt32LE(samples.byteLength, 40);
  writeFileSync(path, Buffer.concat([header, Buffer.from(samples.buffer)]));
}
