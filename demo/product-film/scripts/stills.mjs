// Renders individual frames for review: node scripts/stills.mjs [frame ...] (default: a frame from every beat and cut).
// Output: out/stills/fNNNN.png
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import {mkdirSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT = [0, 20, 45, 90, 150, 188, 250, 290, 330, 410, 455, 492, 520, 570, 610, 700, 760, 800, 860, 900, 940, 975, 1030, 1090, 1130, 1200, 1250, 1320, 1400, 1430, 1465, 1520, 1555, 1590, 1620, 1649];
const frames = process.argv.slice(2).map(Number);
const list = frames.length ? frames : DEFAULT;
const outDir = join(root, 'out', 'stills');
mkdirSync(outDir, {recursive: true});

const serveUrl = await bundle({entryPoint: join(root, 'src', 'index.ts'), publicDir: join(root, 'public')});
const composition = await selectComposition({serveUrl, id: 'ProductFilm', inputProps: {withAudio: false}});
for (const frame of list) {
  const output = join(outDir, `f${String(frame).padStart(4, '0')}.png`);
  await renderStill({serveUrl, composition, frame, output, inputProps: {withAudio: false}});
  process.stdout.write(`${frame} `);
}
console.log(`\n${list.length} stills → out/stills`);
