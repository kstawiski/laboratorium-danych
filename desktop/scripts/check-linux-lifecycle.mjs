// Local acceptance fault checks. Run under xvfb-run after the Linux build.
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { desktop } from './paths.mjs';

if (process.platform !== 'linux') throw new Error('Linux-only acceptance check');
const evidence = path.resolve(process.argv[2]);
const executable = path.join(desktop, 'dist/linux-unpacked/laboratorium-danych');
const profile = path.join(evidence, 'lifecycle-profile');
const log = path.join(profile, 'Laboratorium danych/logs/serwer.log');
await fs.mkdir(profile, { recursive: true });
const env = { ...process.env, XDG_CONFIG_HOME: profile };
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const launch = args => spawn(executable, ['--no-sandbox', ...args], { env, stdio: ['ignore', 'ignore', 'pipe'] });
function exit(child) {
  return new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('exit', (code, signal) => resolve({ code, signal }));
  });
}
function exists(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}
let first;
let serverPid;
try {
  first = launch([]);
  first.stderr.on('data', () => {});
  const exited = exit(first);
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const text = await fs.readFile(log, 'utf8').catch(() => '');
    serverPid = Number(text.match(/Server PID: (\d+)/)?.[1]);
    const port = Number(text.match(/Starting Python on http:\/\/127\.0\.0\.1:(\d+)/)?.[1]);
    if (serverPid && port && await fetch(`http://127.0.0.1:${port}/_stcore/health`).then(r => r.ok).catch(() => false)) break;
    await wait(250);
  }
  if (!serverPid || !exists(serverPid)) throw new Error('Server did not start');
  const second = launch([]);
  second.stderr.on('data', () => {});
  const secondExit = await Promise.race([exit(second), wait(10000).then(() => { second.kill('SIGKILL'); throw new Error('Second instance did not exit'); })]);
  if (secondExit.code !== 0 || !exists(first.pid)) throw new Error('Single instance check failed');
  console.log('PASS: second instance exits 0; first instance remains running.');
  first.kill('SIGKILL');
  await exited;
  const cleanupDeadline = Date.now() + 12000;
  while (Date.now() < cleanupDeadline && exists(serverPid)) {
    const state = await fs.readFile(`/proc/${serverPid}/stat`, 'utf8').catch(() => '');
    if (!state || state.split(') ')[1]?.startsWith('Z')) break;
    await wait(250);
  }
  const state = await fs.readFile(`/proc/${serverPid}/stat`, 'utf8').catch(() => '');
  if (state && !state.split(') ')[1]?.startsWith('Z')) throw new Error('Orphaned live Python after Electron SIGKILL');
  console.log('PASS: watchdog stops Python after forced Electron SIGKILL.');
} finally {
  if (first && exists(first.pid)) first.kill('SIGKILL');
  if (serverPid && exists(serverPid)) { try { process.kill(-serverPid, 'SIGKILL'); } catch {} }
}

const python = path.join(desktop, 'dist/linux-unpacked/resources/python/bin/python3');
const hidden = python + '.acceptance-hidden';
await fs.rename(python, hidden);
try {
  const missing = launch([`--smoke-test=${path.join(evidence, 'missing-runtime/smoke.png')}`]);
  let stderr = '';
  missing.stderr.on('data', chunk => { stderr += chunk; });
  const result = await Promise.race([exit(missing), wait(10000).then(() => { missing.kill('SIGKILL'); throw new Error('Missing-runtime test timed out'); })]);
  if (result.code !== 1 || !stderr.includes('Nie można uruchomić Laboratorium danych')) throw new Error(`Unexpected startup failure result: ${JSON.stringify(result)} ${stderr}`);
  console.log('PASS: missing Python produces Polish startup error and exit 1.');
} finally {
  await fs.rename(hidden, python);
}
