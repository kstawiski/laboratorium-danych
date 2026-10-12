import fs from 'node:fs/promises';
import path from 'node:path';
import YAML from 'yaml';
import { repo } from './paths.mjs';

const document = YAML.parseDocument(await fs.readFile(path.join(repo, '.github/workflows/desktop.yml'), 'utf8'), { uniqueKeys: true });
if (document.errors.length) throw new Error(document.errors.map(e => e.message).join('\n'));
const workflow = document.toJS();
if (!workflow.on.workflow_dispatch || !workflow.on.push.tags.includes('desktop-v*')) throw new Error('Missing build triggers');
if (workflow.jobs.build.strategy.matrix.include.length !== 4) throw new Error('Expected four build targets');
console.log('desktop.yml: YAML parsed; unique keys, triggers and four-target matrix verified (not actionlint).');
