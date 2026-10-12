import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { desktop } from './paths.mjs';

// Keep builder's large temporary files inside the authorized project cache.
const temp = path.join(desktop, '.cache/pip/build-tmp');
await fs.mkdir(temp, { recursive: true });
const require = createRequire(import.meta.url);
const metadata = require('electron-builder/package.json');
const packageDir = path.dirname(require.resolve('electron-builder/package.json'));
const cli = path.resolve(packageDir, typeof metadata.bin === 'string' ? metadata.bin : metadata.bin['electron-builder']);
const child = spawn(process.execPath, [cli, '--publish', 'never', ...process.argv.slice(2)], {
  stdio: 'inherit', windowsHide: true,
  env: { ...process.env, TMPDIR: temp, TMP: temp, TEMP: temp }
});
child.on('error', error => { console.error(error); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
