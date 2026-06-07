'use strict';
const fs = require('fs');
const path = require('path');

const taskFile = path.join(process.cwd(), '.claude', 'tasks.md');

let content;
try { content = fs.readFileSync(taskFile, 'utf-8'); } catch { process.exit(0); }

const match = content.match(/^Status:\s*(\S+)/m);
const status = match ? match[1].toLowerCase() : 'none';

if (status === 'pending') {
  const MAX_BYTES = 8192;
  const body = content.trim();
  const output = body.length > MAX_BYTES
    ? body.slice(0, MAX_BYTES) + '\n... [truncated — edit .claude/tasks.md to review full task]'
    : body;

  process.stdout.write([
    '=== PENDING ORCHESTRATOR TASK ===',
    output,
    '=================================',
    'You have a pending task from the orchestrator. Review it above and begin implementation.',
    '',
  ].join('\n'));
}
