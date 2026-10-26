// Procedural sound bed for the film: no samples, no external audio, deterministic output.
// Writes public/audio/score.wav (48 kHz, 16-bit stereo, exactly the film's length). Cue frames come from src/timeline.json.
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const tl = JSON.parse(readFileSync(join(here, '..', 'src', 'timeline.json'), 'utf8'));
const SR = 48000;
const DUR = tl.durationInFrames / tl.fps;
const N = Math.round(DUR * SR);
const L = new Float32Array(N);
const R = new Float32Array(N);
const sfxL = new Float32Array(N);
const sfxR = new Float32Array(N);
const sec = (frame) => frame / tl.fps;
const TAU = Math.PI * 2;

// Deterministic noise.
let seed = 0x5eed;
const rand = () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));

// 1. Pad: an open D chord (D2 A2 D3 E3 A3) that breathes with the sections and lifts to D major (F#3) for the end card.
const S = tl.sections;
const endAt = sec(S.end.from);
const swells = Object.values(S).map((s) => sec(s.from));
const voices = [
  {f: 73.42, a: 0.34},
  {f: 110.0, a: 0.26},
  {f: 146.83, a: 0.2},
  {f: 164.81, a: 0.12, fadeOutAt: endAt},
  {f: 185.0, a: 0.12, fadeInAt: endAt},
  {f: 220.0, a: 0.1},
];
for (const [vi, v] of voices.entries()) {
  const det = 0.12 + vi * 0.03;
  let pl = rand() * TAU;
  let pr = rand() * TAU;
  for (let i = 0; i < N; i++) {
    const t = i / SR;
    let env = smooth(t / 3.2) * (1 - smooth((t - (DUR - 2.2)) / 2.2));
    if (v.fadeOutAt) env *= 1 - smooth((t - v.fadeOutAt + 0.3) / 1.2);
    if (v.fadeInAt) env *= smooth((t - v.fadeInAt + 0.2) / 1.0);
    let sw = 0;
    for (const s0 of swells) if (t >= s0) sw = Math.max(sw, Math.exp(-(t - s0) / 2.2) * 0.35);
    const trem = 1 + 0.08 * Math.sin(TAU * 0.11 * t + vi);
    const g = v.a * env * (0.75 + sw) * trem;
    pl += (TAU * (v.f - det)) / SR;
    pr += (TAU * (v.f + det)) / SR;
    L[i] += g * (Math.sin(pl) + 0.18 * Math.sin(2 * pl) + 0.05 * Math.sin(3 * pl));
    R[i] += g * (Math.sin(pr) + 0.18 * Math.sin(2 * pr) + 0.05 * Math.sin(3 * pr));
  }
}

// 2. Air on transitions: noise through a swept band-pass (state-variable filter), peaking on the cut.
const whoosh = (at, gain = 0.16) => {
  const pre = 0.32;
  const post = 0.34;
  const i0 = Math.max(0, Math.round((at - pre) * SR));
  const i1 = Math.min(N, Math.round((at + post) * SR));
  let low = 0;
  let band = 0;
  const pan = 0.5 + (rand() - 0.5) * 0.5;
  for (let i = i0; i < i1; i++) {
    const t = i / SR - (at - pre);
    const u = t / (pre + post);
    const fc = 350 + 2200 * Math.sin(Math.PI * u);
    const f = 2 * Math.sin((Math.PI * fc) / SR);
    const q = 0.55;
    const x = rand() * 2 - 1;
    low += f * band;
    const high = x - low - q * band;
    band += f * high;
    const env = t < pre ? Math.pow(t / pre, 2) : Math.exp(-(t - pre) / 0.1);
    const s = band * env * gain;
    sfxL[i] += s * (1 - pan) * 2 * 0.7;
    sfxR[i] += s * pan * 2 * 0.7;
  }
};

// 3. A soft tick when a focus outline starts drawing.
const tick = (at, gain = 0.06) => {
  const i0 = Math.round(at * SR);
  for (let i = i0; i < Math.min(N, i0 + SR * 0.12); i++) {
    const t = (i - i0) / SR;
    const env = Math.min(1, t / 0.002) * Math.exp(-t / 0.028);
    const s = gain * env * (Math.sin(TAU * 1480 * t) + 0.35 * Math.sin(TAU * 2960 * t));
    sfxL[i] += s;
    sfxR[i] += s;
  }
};

// 4. A warm two-note bell for a choice (take selected) and for the end card.
const bell = (at, notes, gain = 0.07) => {
  notes.forEach((f, k) => {
    const i0 = Math.round((at + k * 0.11) * SR);
    for (let i = i0; i < Math.min(N, i0 + SR * 2.4); i++) {
      const t = (i - i0) / SR;
      const env = Math.min(1, t / 0.004) * Math.exp(-t / 0.75);
      const s = gain * env * (Math.sin(TAU * f * t) + 0.22 * Math.sin(TAU * f * 2.76 * t) * Math.exp(-t / 0.2) + 0.1 * Math.sin(TAU * f * 2 * t));
      sfxL[i] += s * (k % 2 ? 0.8 : 1);
      sfxR[i] += s * (k % 2 ? 1 : 0.8);
    }
  });
};

// 5. A low, soft swell under the opening reveal and the end card.
const bloom = (at, gain = 0.2) => {
  const i0 = Math.max(0, Math.round((at - 0.05) * SR));
  for (let i = i0; i < Math.min(N, i0 + SR * 2.5); i++) {
    const t = (i - i0) / SR;
    const env = Math.min(1, t / 0.06) * Math.exp(-t / 0.7);
    const s = gain * env * Math.sin(TAU * (48 + 14 * Math.exp(-t / 0.15)) * t);
    sfxL[i] += s;
    sfxR[i] += s;
  }
};

for (const f of tl.sfx.whoosh) whoosh(sec(f));
for (const f of tl.sfx.tick) tick(sec(f));
bell(sec(tl.sfx.chime[0]), [659.25, 880.0]);
bell(sec(tl.sfx.chime[1]), [587.33, 880.0, 1174.66], 0.05);
bloom(sec(8));
bloom(sec(S.end.from + 5), 0.16);

// Small room for the effects bus: four damped combs and two all-passes per side (Schroeder).
const reverb = (input, offs) => {
  const out = new Float32Array(N);
  const combs = [1557, 1617, 1491, 1422].map((d) => ({d: d + offs, buf: new Float32Array(d + offs), i: 0, lp: 0}));
  for (let n = 0; n < N; n++) {
    let acc = 0;
    for (const c of combs) {
      const y = c.buf[c.i];
      c.lp = y * 0.6 + c.lp * 0.4;
      c.buf[c.i] = input[n] + c.lp * 0.78;
      c.i = (c.i + 1) % c.d;
      acc += y;
    }
    out[n] = acc * 0.25;
  }
  for (const d of [225 + offs, 556 + offs]) {
    const buf = new Float32Array(d);
    let i = 0;
    for (let n = 0; n < N; n++) {
      const b = buf[i];
      const y = -out[n] + b;
      buf[i] = out[n] + b * 0.5;
      i = (i + 1) % d;
      out[n] = y;
    }
  }
  return out;
};
const wetL = reverb(sfxL, 0);
const wetR = reverb(sfxR, 23);
for (let i = 0; i < N; i++) {
  L[i] += sfxL[i] + wetL[i] * 0.35;
  R[i] += sfxR[i] + wetR[i] * 0.35;
}

// Normalise to about -9 dBFS peak (≈ -19 LUFS integrated: a bed, not a score); 10 ms fades at both ends so the first and last samples are silent.
let peak = 0;
for (let i = 0; i < N; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
const norm = 0.35 / peak;
const fade = SR * 0.01;
const pcm = Buffer.alloc(44 + N * 4);
pcm.write('RIFF', 0);
pcm.writeUInt32LE(36 + N * 4, 4);
pcm.write('WAVEfmt ', 8);
pcm.writeUInt32LE(16, 16);
pcm.writeUInt16LE(1, 20);
pcm.writeUInt16LE(2, 22);
pcm.writeUInt32LE(SR, 24);
pcm.writeUInt32LE(SR * 4, 28);
pcm.writeUInt16LE(4, 32);
pcm.writeUInt16LE(16, 34);
pcm.write('data', 36);
pcm.writeUInt32LE(N * 4, 40);
for (let i = 0; i < N; i++) {
  const edge = Math.min(1, i / fade, (N - 1 - i) / fade);
  const q = (x) => Math.max(-32767, Math.min(32767, Math.round(x * norm * edge * 32767)));
  pcm.writeInt16LE(q(L[i]), 44 + i * 4);
  pcm.writeInt16LE(q(R[i]), 46 + i * 4);
}
const outDir = join(here, '..', 'public', 'audio');
mkdirSync(outDir, {recursive: true});
writeFileSync(join(outDir, 'score.wav'), pcm);
console.log(`audio: ${DUR.toFixed(3)} s procedural score → public/audio/score.wav (peak normalised from ${peak.toFixed(3)})`);
