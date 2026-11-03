// Turn a screencast (frames with their own timestamps) into a constant 30 fps video.
//
//   node capture/frames2mp4.mjs rec/web [--width 1920]
//
// Each frame is shown until the next one arrived, so pauses in the page stay pauses.

import { readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { join, resolve } from 'node:path';

const dir = resolve(process.argv[2]);
const width = process.argv.includes('--width') ? Number(process.argv[process.argv.indexOf('--width') + 1]) : 1920;
const frames = JSON.parse(await readFile(join(dir, 'frames.json'), 'utf8'));
const lines = [];
for (let i = 0; i < frames.length; i++) {
  const d = i + 1 < frames.length ? frames[i + 1].t - frames[i].t : 0.5;
  lines.push(`file 'frames/${frames[i].name}'`, `duration ${Math.max(0.001, d).toFixed(4)}`);
}
lines.push(`file 'frames/${frames[frames.length - 1].name}'`);
await writeFile(join(dir, 'concat.txt'), lines.join('\n'));
const out = join(dir, `${dir.split('/').pop()}.mp4`);
const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(dir, 'concat.txt'),
  '-vf', `fps=30,scale=${width}:-2:flags=lanczos`, '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', out], { stdio: 'inherit' });
if (r.status !== 0) process.exit(r.status);
console.log(out);
