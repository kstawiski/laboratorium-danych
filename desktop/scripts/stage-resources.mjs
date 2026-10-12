import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { desktop, repo, python } from './paths.mjs';

await fs.access(python).catch(() => { throw new Error('Run npm run prepare:python first.'); });
const staged = path.join(desktop, 'staged');
await fs.mkdir(staged, { recursive: true });
for (const entry of await fs.readdir(staged)) {
  await fs.rm(path.join(staged, entry), { recursive: true });
}
const excluded = new Set(['tests', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
  '.venv', 'venv', 'logs', 'cache', '.git', '.pytest_tmp', '.coverage', 'htmlcov', 'secrets.toml']);
function filter(source) {
  const base = path.basename(source);
  return !excluded.has(base) && !base.startsWith('.env') && !/\.(pyc|pyo|log|key)$/.test(base);
}
for (const [source, name] of [['app', 'app'], ['exercises/dane', 'dane']]) {
  await fs.cp(path.join(repo, source), path.join(staged, name), { recursive: true, filter, dereference: true });
}
// Records the actual concurrently edited app snapshot used for this build.
const files = [];
async function manifest(dir) {
  for (const item of (await fs.readdir(dir, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, item.name);
    if (item.isDirectory()) await manifest(full);
    else files.push({ file: path.relative(staged, full).split(path.sep).join('/'),
      sha256: createHash('sha256').update(await fs.readFile(full)).digest('hex') });
  }
}
await manifest(staged);
await fs.writeFile(path.join(staged, 'manifest.json'), JSON.stringify(files, null, 2) + '\n');
console.log(`Staged app and synthetic data (${files.length} files); tests, caches, logs and secrets excluded.`);
