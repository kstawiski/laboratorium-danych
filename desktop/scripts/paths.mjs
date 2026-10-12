import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const desktop = fileURLToPath(new URL('../', import.meta.url));
export const repo = path.resolve(desktop, '..');
export const platform = { linux: 'linux', darwin: 'mac', win32: 'win' }[process.platform];
export const target = `${platform}-${process.arch}`;
export const runtime = path.join(desktop, 'runtime', target);
export const python = path.join(runtime, 'python', process.platform === 'win32' ? 'python.exe' : 'bin/python3');
