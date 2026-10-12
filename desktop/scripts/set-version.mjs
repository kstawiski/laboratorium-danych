import fs from 'node:fs/promises';
import path from 'node:path';
import { desktop } from './paths.mjs';

const version = (process.env.DESKTOP_TAG || '').replace(/^desktop-v/, '');
if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) throw new Error('Expected tag desktop-vX.Y.Z');
for (const name of ['package.json', 'package-lock.json']) {
  const file = path.join(desktop, name);
  const data = JSON.parse(await fs.readFile(file, 'utf8'));
  data.version = version;
  if (data.packages?.['']) data.packages[''].version = version;
  await fs.writeFile(file, JSON.stringify(data, null, 2) + '\n');
}
console.log(`Desktop version: ${version}`);
