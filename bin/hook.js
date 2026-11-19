#!/usr/bin/env node

/**
 * Cross-platform fail-safe launcher for Skill Vault lifecycle hooks (scripts/hook_runner.py).
 */

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'scripts', 'hook_runner.py');
const candidates = process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
const extraArgs = process.argv.slice(2);

function runWith(idx) {
  if (idx >= candidates.length) {
    process.stdout.write('{}\n');
    process.exit(0);
  }
  const cmd = candidates[idx];
  const cmdArgs = cmd === 'py' ? ['-3', scriptPath, ...extraArgs] : [scriptPath, ...extraArgs];
  const child = spawn(cmd, cmdArgs, { stdio: 'inherit' });

  child.on('error', (err) => {
    if (err && err.code === 'ENOENT') {
      runWith(idx + 1);
      return;
    }
    process.stdout.write('{}\n');
    process.exit(0);
  });

  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

runWith(0);
