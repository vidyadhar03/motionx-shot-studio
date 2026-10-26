// Pulls the frames listed in src/sheet.ts out of the rendered MP4 (so the sheet shows the real encode, not a re-render)
// and lays them out with timecodes: out/contact-sheet.jpg.
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const video = join(root, 'out', 'motionx-shot-studio-demo.mp4');
if (!existsSync(video)) throw new Error('Render the film first: npm run render');
const frames = [...readFileSync(join(root, 'src', 'sheet.ts'), 'utf8').matchAll(/\[(\d+), '/g)].map((m) => Number(m[1]));
const dir = join(root, 'public', 'contact');
mkdirSync(dir, {recursive: true});
for (const f of frames) {
  const out = join(dir, `f${String(f).padStart(4, '0')}.png`);
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', video, '-vf', `select=eq(n\\,${f}),scale=1152:648`, '-vframes', '1', out]);
}
const serveUrl = await bundle({entryPoint: join(root, 'src', 'index.ts'), publicDir: join(root, 'public')});
const composition = await selectComposition({serveUrl, id: 'ContactSheet'});
const output = join(root, 'out', 'contact-sheet.jpg');
await renderStill({serveUrl, composition, output, imageFormat: 'jpeg', jpegQuality: 88});
console.log(`contact sheet: ${frames.length} frames → out/contact-sheet.jpg`);
