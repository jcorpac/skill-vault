#!/usr/bin/env node

/**
 * Skill Vault CLI - Node.js thin runner
 * Spawns the underlying portable Python engine (scripts/skill_vault.py).
 */

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'scripts', 'skill_vault.py');
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

const child = spawn(pythonCmd, [scriptPath, ...process.argv.slice(2)], {
  stdio: 'inherit'
});

child.on('error', (err) => {
  if (err.code === 'ENOENT') {
    console.error(`\x1b[31m[Skill Vault Error]\x1b[0m Python 3 was not found on your system PATH. Please ensure Python 3 is installed.`);
  } else {
    console.error(`\x1b[31m[Skill Vault Error]\x1b[0m ${err.message}`);
  }
  process.exit(1);
});

child.on('exit', (code) => {
  process.exit(code ?? 0);
});
