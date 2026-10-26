// Copies the showcase screenshots into public/screens (gitignored) and checks they are the expected 1920×1080 PNGs.
import {copyFileSync, mkdirSync, openSync, readSync, closeSync, readdirSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', '..', 'showcase', 'screens');
const dst = join(here, '..', 'public', 'screens');
mkdirSync(dst, {recursive: true});

const size = (file) => {
  const fd = openSync(file, 'r');
  const buf = Buffer.alloc(24);
  readSync(fd, buf, 0, 24, 0);
  closeSync(fd);
  if (buf.toString('ascii', 1, 4) !== 'PNG') throw new Error(`${file} is not a PNG`);
  return [buf.readUInt32BE(16), buf.readUInt32BE(20)];
};

const files = readdirSync(src).filter((f) => f.endsWith('.png'));
for (const f of files) {
  const [w, h] = size(join(src, f));
  if (w !== 1920 || h !== 1080) throw new Error(`${f} is ${w}×${h}; the crops assume 1920×1080`);
  copyFileSync(join(src, f), join(dst, f));
}
console.log(`screens: ${files.length} PNGs (1920×1080) → public/screens`);
