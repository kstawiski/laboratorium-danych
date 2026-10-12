import fs from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { desktop, repo, target, runtime, python } from './paths.mjs';

async function digest(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

async function run(command, args, env = process.env) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', windowsHide: true, env });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}`)));
  });
}

const lock = JSON.parse(await fs.readFile(path.join(desktop, 'scripts/python-lock.json'), 'utf8'));
const spec = lock.targets[target];
if (!spec) throw new Error(`Unsupported native build target: ${target}`);
const cache = path.join(desktop, '.cache');
await fs.mkdir(path.join(cache, 'downloads'), { recursive: true });
const name = `cpython-${lock.version}+${lock.release}-${spec.triple}-install_only.tar.gz`;
const archive = path.join(cache, 'downloads', name);
const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${lock.release}/${encodeURIComponent(name)}`;
try {
  await fs.access(archive);
} catch {
  console.log(`Downloading ${url}`);
  // curl uses the host's configured HTTPS proxy; Windows/macOS runners also provide it.
  const partial = archive + '.partial';
  try {
    await run('curl', ['--fail', '--location', '--retry', '3', '--output', partial, url]);
    await fs.rename(partial, archive);
  } finally {
    await fs.rm(partial, { force: true });
  }
}
const checksum = await digest(archive);
if (checksum !== spec.sha256) {
  await fs.rm(archive, { force: true });
  throw new Error(`SHA-256 mismatch for ${name}: ${checksum}`);
}
console.log(`Verified SHA-256 ${checksum}`);
const requirements = path.join(repo, 'app/requirements.txt');
const stamp = JSON.stringify({ target, runtime: spec.sha256, requirements: await digest(requirements) });
const stampFile = path.join(runtime, '.prepared.json');
if (await fs.readFile(stampFile, 'utf8').catch(() => '') === stamp) {
  await run(python, ['-m', 'pip', 'check']);
  console.log(`Already prepared: ${target}`);
  process.exit(0);
}
await fs.rm(runtime, { recursive: true, force: true });
await fs.mkdir(runtime, { recursive: true });
// Na Windows GNU tar z Git Bash traktuje „D:” jako host zdalny; systemowy bsdtar obsługuje litery dysków.
const tarCommand = process.platform === 'win32' ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe') : 'tar';
await run(tarCommand, ['-xzf', archive, '-C', runtime]);
const env = { ...process.env, PYTHONNOUSERSITE: '1', PYTHONPATH: '', PYTHONHOME: '',
  PIP_CACHE_DIR: path.join(cache, 'pip'), PIP_DISABLE_PIP_VERSION_CHECK: '1',
  TMPDIR: path.join(cache, 'pip/tmp'), TMP: path.join(cache, 'pip/tmp'), TEMP: path.join(cache, 'pip/tmp'),
  PYTHONDONTWRITEBYTECODE: '1' };
await fs.mkdir(env.TMPDIR, { recursive: true });
await run(python, ['-m', 'pip', 'install', '--no-compile', '-r', requirements], env);
await run(python, ['-m', 'pip', 'check'], env);
await run(python, ['-c', 'import streamlit, pandas, numpy, plotly, openai, httpx, openpyxl, yaml; print("Python runtime ready")'], env);
await fs.writeFile(stampFile, stamp);
console.log(`Prepared ${target}: ${python}`);
