// Checks the rendered film: container/stream facts, a full decode with no errors, exact length, clean first/last frames.
import {execFileSync, spawnSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const tl = JSON.parse(readFileSync(join(root, 'src', 'timeline.json'), 'utf8'));
const video = process.argv[2] ?? join(root, 'out', 'motionx-shot-studio-demo.mp4');
const run = (cmd, args) => execFileSync(cmd, args, {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 1 << 26});

const probe = JSON.parse(run('ffprobe', ['-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', video]));
const v = probe.streams.find((s) => s.codec_type === 'video');
const a = probe.streams.find((s) => s.codec_type === 'audio');
const checks = [];
const check = (name, ok, detail) => checks.push({name, ok, detail});
check('codec h264', v.codec_name === 'h264', `${v.codec_name} ${v.profile}`);
check('pixel format yuv420p', v.pix_fmt === 'yuv420p', v.pix_fmt);
check('1920×1080', v.width === tl.width && v.height === tl.height, `${v.width}×${v.height}`);
check('30 fps', v.r_frame_rate === '30/1', v.r_frame_rate);
check(`${tl.durationInFrames} frames`, Number(v.nb_read_frames) === tl.durationInFrames, v.nb_read_frames);
const dur = Number(probe.format.duration);
check('duration 55 s (< 60 s)', Math.abs(dur - tl.durationInFrames / tl.fps) < 0.05 && dur < 60, `${dur.toFixed(3)} s container, video ${Number(v.duration).toFixed(3)} s`);
check('audio track (AAC)', a?.codec_name === 'aac', a ? `${a.codec_name} ${a.sample_rate} Hz ${a.channels} ch ${Number(a.duration).toFixed(3)} s` : 'none');

let decodeErr = '';
try {
  decodeErr = run('ffmpeg', ['-v', 'error', '-i', video, '-f', 'null', '-']).trim();
} catch (e) {
  decodeErr = String(e.stderr || e);
}
check('full decode without errors', decodeErr === '', decodeErr || 'clean');

// Luma maximum per frame, from ffmpeg's signalstats (printed on stderr).
const lumaMax = (inputArgs) =>
  spawnSync('ffmpeg', ['-hide_banner', ...inputArgs, '-i', video, '-vf', 'signalstats,metadata=mode=print', '-f', 'null', '-'], {encoding: 'utf8'}).stderr;
const ymax = (s) => [...s.matchAll(/YMAX=(\d+)/g)].map((m) => Number(m[1]));
const firstY = ymax(lumaMax(['-t', '0.02']))[0];
const lastY = [...new Set(ymax(lumaMax(['-sseof', '-0.2'])))];
check('first frame is the plain ground (no stray marks)', firstY <= 40, `YMAX ${firstY}`);
check('last frames are the settled end card', lastY.length === 1, `YMAX over last 0.2 s: ${lastY.join(', ')}`);

for (const c of checks) console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name.padEnd(48)} ${c.detail}`);
if (checks.some((c) => !c.ok)) process.exit(1);
