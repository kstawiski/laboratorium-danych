import fs from 'node:fs/promises';
import path from 'node:path';
import { desktop } from './paths.mjs';

// For the interrupted on-disk preparation only. Preserve namespace mount points.
for (const name of ['node_modules', 'runtime', '.cache/npm']) {
  const dir = path.join(desktop, name);
  const names = await fs.readdir(dir).catch(error => { if (error.code === 'ENOENT') return []; throw error; });
  for (const entry of names) await fs.rm(path.join(dir, entry), { recursive: true });
  console.log(`Removed stale contents: desktop/${name}`);
}
